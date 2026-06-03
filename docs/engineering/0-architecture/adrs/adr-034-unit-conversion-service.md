# ADR-034 — Serviço de Conversão de Unidades e Integridade Dimensional

**Status:** Implementado  
**Data:** 2026-05-07  
**Contexto:** MendesLobo Construtora — Concilium

---

## Contexto

### Problema

Durante a formalização do catálogo versionado (ADR-032) e do pipeline de ingestão (ADR-033), identificamos que o sistema era vulnerável a **anomalias de grandeza** — erros de ordem de magnitude causados por incompatibilidade dimensional silenciosa:

- **P1 — Mistura de escalas:** Engenheiros cadastram insumos em toneladas (`t`) no catálogo Master, enquanto a CPU correspondente usa quilogramas (`kg`). O pipeline multiplica coeficientes por preços de bases dimensionais diferentes, gerando orçamentos 1.000× fora da realidade.
- **P2 — VAL-CPU-INS-05 frágil:** A regra de validação de unidades encontrava unidades válidas mas não mapeadas em listas fixas, gerando falsos-negativos ou bloqueios indevidos.
- **P3 — Conversão de preço ≠ conversão de quantidade:** A conversão de um preço unitário (R$/h → R$/mês) é inversa à conversão de quantidade (1 mês = 176 h, portanto R$/h × 176 = R$/mês). Sem um serviço dedicado, essa assimetria era ignorada.
- **P4 — Aliases inconsistentes:** `'L'`, `'l'`, `'litro'` e `'lt'` coexistiam no catálogo sem normalização, corrompendo comparações de compatibilidade.
- **P5 — Lógica de unidades dispersa:** Validações em `ValidadorCPUInsumo`, cálculos nas Skills 03/04 e o `RepositorioInsumo` cada um implementavam sua própria lógica de unidade ad hoc, sem ponto único de verdade.

---

## Decisão

### D1 — Serviço de Domínio Autônomo (`ConversorUnidades`)

Criação de `concilium.domain.services.conversor_unidades` como serviço puro de domínio — sem dependência de modelos específicos (`Insumo`, `CPU`), operando apenas sobre escalares e strings.

```python
# src/concilium/domain/services/conversor_unidades.py

class UnidadeIncompativelError(ValueError):
    """Levantada quando não há caminho de conversão entre grandezas distintas."""
    pass

class ConversorUnidades:
    """Motor de conversão de unidades para engenharia de custos."""
```

### D2 — Tabela De-Para com Grandezas Fundamentais

O conversor mantém uma tabela interna `_TABELA` e um mapa de aliases `_ALIASES`. As grandezas cobertas são todas as fundamentais da construção pesada:

| Grandeza | Unidades suportadas |
|---|---|
| Massa | `t`, `kg`, `g` |
| Volume | `m3`, `litro` (alias: `l`) |
| Comprimento | `km`, `m`, `cm` |
| Tempo | `mes`, `dia`, `h` |
| Área | `m2` (sem conversão cruzada — apenas normalização) |
| Contagem | `unidade` (aliases: `un`, `und`, `unid`) |

### D3 — Falha Segura por Incompatibilidade Dimensional

Qualquer tentativa de converter entre grandezas fisicamente incompatíveis (ex: `kg` → `m`) lança `UnidadeIncompativelError` e interrompe o cálculo, impedindo a geração de dados financeiros corrompidos:

```python
@classmethod
def converter(cls, quantidade: float, origem: str, destino: str) -> float:
    u_origem = cls.normalizar(origem)
    u_destino = cls.normalizar(destino)
    if u_origem == u_destino:
        return quantidade
    if u_origem in cls._TABELA and u_destino in cls._TABELA[u_origem]:
        return quantidade * cls._TABELA[u_origem][u_destino]
    raise UnidadeIncompativelError(
        f"Sem caminho de conversão de '{origem}' para '{destino}'."
    )
```

### D4 — Normalização por Alias Map

Todas as entradas passam por `normalizar()` antes de qualquer operação, unificando variantes de digitação:

```python
_ALIASES = {
    "l": "litro", "lt": "litro",
    "ton": "t",
    "un": "unidade", "und": "unidade", "unid": "unidade",
    # ... demais aliases
}

@classmethod
def normalizar(cls, unidade: str) -> str:
    return cls._ALIASES.get(unidade.strip().lower(), unidade.strip().lower())
```

### D5 — Conversão de Preço é Inversa à de Quantidade

A conversão de preços unitários segue a lógica de razão inversa: se `1 mês = 176 h`, então `R$ 100/h = R$ 17.600/mês`. Método `converter_preco()` implementa essa inversão explicitamente para evitar erro conceitual em Skills de precificação:

```python
@staticmethod
def converter_preco(valor: float, origem: str, destino: str) -> float:
    """Converte preço R$/unidade. Usa o inverso do fator de quantidade."""
    fator = ConversorUnidades._TABELA[u_origem][u_destino]
    return valor / fator   # ← inversão intencional
```

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo da Rejeição |
|---|---|---|
| X1 | Biblioteca `pint` (Python units) | Overhead de dependência externa desnecessário; `pint` não conhece a semântica de "mês = 176 h" do ADR-023; curva de aprendizado para novos desenvolvedores. |
| X2 | Lógica de conversão embutida em cada Skill | Duplicação; inconsistências acumulam com o crescimento do framework; impossível testar de forma isolada. |
| X3 | Forçar uso de apenas uma unidade por grandeza no catálogo | Impede que a engenharia use unidades naturais (ex: `t` para solos, `kg` para aço); impacto alto na UX do cadastro. |

---

## Consequências

### Positivas

| ID | Consequência |
|---|---|
| C1 | `VAL-CPU-INS-05` não mais produz falsos-negativos em unidades válidas porém não mapeadas explicitamente. |
| C2 | Skills 03 e 04 normalizam coeficientes antes da multiplicação, eliminando erros de escala silenciosos. |
| C3 | Ponto único de manutenção para toda a lógica de métricas do framework. |
| C4 | `sao_compativeis()` e `eh_unidade_conhecida()` como predicados reutilizáveis em validações e MCP guards. |

### Negativas / Riscos

| ID | Risco | Mitigação |
|---|---|---|
| R1 | Tabela de conversão limitada — grandezas como `verba`, `vb`, `lote` são atômicas e não convertíveis. | Aceitar como `UNIDADE_OPACA`: sem conversão, sem erro, apenas normalização. |
| R2 | Novos aliases não cadastrados geram falha silenciosa (normalização retorna a string bruta). | Adicionar validação de warning no ingest pipeline ao encontrar unidade desconhecida. |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| **F1 — Serviço Base** | `ConversorUnidades`, `UnidadeIncompativelError`, tabela De-Para, aliases | ✅ Implementado |
| **F2 — Integração Validador** | Refatoração de `VAL-CPU-INS-05` em `ValidadorCPUInsumo` para usar o conversor | ✅ Implementado |
| **F3 — Integração Skills** | Normalização de coeficientes nas Skills 03 (Precificação Insumos) e 04 (BDI) | ✅ Implementado |
| **F4 — Testes** | Suite de testes unitários cobrindo conversões críticas e casos de erro | ✅ Implementado |

---

## Definition of Done

### Fase 1 — Serviço Base
- [x] `ConversorUnidades` criado em `domain/services/conversor_unidades.py`.
- [x] Suporte para Massa (`t`, `kg`, `g`), Volume (`m3`, `litro`), Comprimento (`km`, `m`, `cm`), Tempo (`mes`, `dia`, `h`).
- [x] `UnidadeIncompativelError` lançada em conversões entre grandezas distintas.
- [x] `normalizar()` com alias map completo.

### Fase 2 — Integração e Validação
- [x] `ValidadorCPUInsumo` refatorado para usar `sao_compativeis()` na regra `VAL-CPU-INS-05`.
- [x] Skills 03 e 04 usam `converter()` para normalizar coeficientes antes do cálculo de custo.
- [x] Testes unitários: conversões diretas, inversas, preço vs. quantidade, erros de incompatibilidade.
