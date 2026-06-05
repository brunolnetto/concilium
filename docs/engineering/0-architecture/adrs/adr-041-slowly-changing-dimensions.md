# ADR-041 — SCD Type 2 para Rastreabilidade Histórica do Catálogo Master

**Status:** Implementado  
**Data:** 2026-05-08  
**Atualizado:** 2026-05-15  
**Contexto:** MendesLobo Construtora — Concilium

---

## Estado de Implementação (2026-05-15)

| Fase | Item | Status |
|---|---|---|
| F1 — Schema | `HistoricoPreco` com `preco_unitario`, `data_inicio_vigencia`, `data_fim_vigencia`, `fonte` | ✅ `domain/models/catalogo.py` |
| F1 | Campo `historico_precos: list[HistoricoPreco]` em `Insumo` | ✅ |
| F2 — Repositório | `preco_na_data(codigo, data)` com fallback para `preco_unitario` flat | ✅ `infrastructure/repositories/insumo.py` |
| F2 | Suporte dual: `historico_precos` (SCD-2) e `InsumoVersionado.versoes` (snapshot mensal) | ✅ |
| F3 — Escrita | `atualizar_preco()` fecha período anterior e abre novo | ✅ |
| F3 | Integrado ao `catalog promote` CLI | ✅ |
| F4 — Integração | Skills usam `preco_na_data(data=escopo.data_base_orcamento)` | ✅ |
| F5 — Índice | **`price_trend.py` — Índice de Tendência de Preços por categoria** | ✅ `application/catalog/price_trend.py` |
| F5 | CLI `concilium catalog tendencia --contexto --jurisdicao` | ✅ `commands_manage.py` |
| F5 | MCP tool `tendencia_precos_catalogo(contexto_id, jurisdicao_id)` | ✅ `mcp_server/tools/catalogo.py` |

### Índice de Tendência de Preços (Skill 20 / F5)

O módulo `price_trend.py` implementa o "Índice MendesLôbo":
- Compara `preco_unitario` atual com o registro mais antigo em `historico_precos` 
- Para contextos com SICRO regional, usa `regionalizacao[jurisdicao_id].preco` como preço atual
- Agrega variações por categoria (MAO_OBRA, EQUIPAMENTO, MATERIAL)
- Expõe via CLI (`catalog tendencia`) e MCP (`tendencia_precos_catalogo`)

### Limitação documentada

A cobertura de `historico_precos` é ainda parcial no catálogo atual (apenas insumos que passaram pelo workflow `catalog promote` ou foram atualizados pelo pipeline ADR-045 têm histórico). O índice ficará mais preciso conforme o catálogo acumula registros históricos via promoções regulares.

---

## Contexto

### Problema

O Catálogo Master deve ser uma fonte imutável de verdade histórica. No modelo atual, ao atualizar um preço ou produtividade no Master, o valor anterior é sobrescrito permanentemente:

- **P1 — Auditoria retroativa impossível:** Um orçamento aprovado em Janeiro/2026 usa o preço do cimento que estava no catálogo naquela data. Se em Março o preço foi atualizado, é impossível re-executar o orçamento de Janeiro e obter o mesmo resultado — o dado histórico foi perdido.
- **P2 — Sem análise de tendência interna:** A MendesLobo não possui índice de inflação interno de insumos. Para construir um índice que mostre como o custo de escavação hidráulica evoluiu de 2022 a 2026, precisaríamos do histórico de cada linha do catálogo — que não existe no modelo atual.
- **P3 — Reajustamento de contratos sem base:** Contratos de longa duração preveem reajustamento por índice (INPC, IPCA-C). Para contestar ou validar reajustes, é necessário comparar o preço pago vs. o preço que estava no catálogo na data de referência do contrato — impossível sem histórico.
- **P4 — Incoerência com ADR-040 (Promotion):** O workflow de promoção de overrides para o Master (ADR-040) não tem semântica clara de como "fechar" o período anterior e "abrir" o novo, gerando registros de promoção sem trilha auditável.

---

## Decisão

### D1 — Padrão SCD Type 2 para Atributos Críticos

Adoção do padrão **Slowly Changing Dimensions Type 2** para `preco_base` e `produtividade_referencia` no Catálogo Master. Cada mutação cria um novo registro com intervalo de validade, sem deletar o anterior:

| Operação | SCD Type 1 (atual) | SCD Type 2 (proposto) |
|---|---|---|
| Atualizar preço | Sobrescreve | Fecha registro atual (`valido_ate = hoje - 1d`), cria novo com `valido_de = hoje` |
| Ler preço atual | Lê o campo diretamente | Lê onde `valido_ate IS NULL` |
| Ler preço histórico | Impossível | Lê onde `data_ref BETWEEN valido_de AND valido_ate` |

### D2 — Estrutura de Dados do Histórico

Os insumos do catálogo passam a ter uma lista `historico_preco` além do `preco_base` (que reflete sempre o mais recente):

```json
{
  "codigo": "M0089",
  "descricao": "Cimento CP-II",
  "tipo": "MATERIAL",
  "unidade": "sc",
  "preco_base": 32.50,
  "historico_preco": [
    {
      "preco": 28.00,
      "valido_de": "2024-01-01",
      "valido_ate": "2024-11-30",
      "fonte": "Pesquisa mercado Nov/2024",
      "atualizado_por": "Bruno Lobo"
    },
    {
      "preco": 30.75,
      "valido_de": "2024-12-01",
      "valido_ate": "2025-12-31",
      "fonte": "SINAPI Dez/2024",
      "atualizado_por": "Ana Costa"
    },
    {
      "preco": 32.50,
      "valido_de": "2026-01-01",
      "valido_ate": null,
      "fonte": "SICRO/01-2026 + Pesquisa local",
      "atualizado_por": "Sistema"
    }
  ]
}
```

### D3 — API de Consulta Temporal no `RepositorioInsumo`

O repositório expõe `preco_em(codigo, data)` como método oficial de consulta histórica:

```python
def preco_em(self, codigo: str, data: date) -> float:
    """Retorna o preço vigente do insumo na data especificada.
    
    Usado pela Skill de Time-Travel (reprocessamento de orçamentos antigos)
    e pelo módulo de análise de tendência.
    """
    insumo = self._insumos[codigo]
    historico = insumo.get("historico_preco", [])
    for registro in reversed(historico):  # mais recente primeiro
        valido_de = date.fromisoformat(registro["valido_de"])
        valido_ate = date.fromisoformat(registro["valido_ate"]) if registro["valido_ate"] else date.max
        if valido_de <= data <= valido_ate:
            return registro["preco"]
    raise ValueError(f"Sem histórico de preço para '{codigo}' na data {data}")
```

### D4 — Integração com ADR-033 (Arbitragem Temporal)

O `Escopo.data_base_orcamento` (ADR-033) passa a alimentar diretamente o `preco_em()`. Ao re-executar uma skill em um escopo com `data_base_orcamento = date(2025, 6, 1)`, todos os preços são resolvidos para aquela data — garantindo reprodutibilidade total:

```python
# Na Skill de Precificação
preco = repositorio.preco_em(
    codigo=insumo_codigo,
    data=escopo.data_base_orcamento or date.today()
)
```

### D5 — Índice Mendes Lobo

A série `historico_preco` de todos os insumos permite construir índices de inflação interna por categoria (Terraplenagem, Pavimentação, Drenagem). Esses índices são calculados periodicamente pela Skill 20 (Análise de Tendência) e exportados como painel de inteligência de custos.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo da Rejeição |
|---|---|---|
| X1 | Versionamento do arquivo JSON inteiro via git | Granularidade insuficiente para consulta por insumo específico; requer parse do histórico git, que não é API de negócio. |
| X2 | SCD Type 1 com arquivo de log de mudanças separado | Mantém o risco de inconsistência entre o log e o catálogo; não é consultável via `preco_em()`. |
| X3 | Banco de dados relacional com tabela de histórico | Correta tecnicamente, mas introduz dependência de banco de dados que o modelo de filesystem atual não suporta (ADR-033 BlobStorage). |
| X4 | SCD Type 3 (colunas `preco_anterior` e `preco_atual`) | Suporta apenas o último histórico — inviável para análise de tendência de múltiplos anos. |

---

## Consequências

### Positivas

| ID | Consequência |
|---|---|
| C1 | **Auditoria perfeita:** Qualquer orçamento histórico pode ser reprocessado obtendo exatamente o mesmo resultado financeiro da época. |
| C2 | **Índice Mendes Lobo:** Base para criação de índices de inflação interna por categoria de serviço. |
| C3 | **Reajustamento defensável:** Comparação objetiva entre preço do contrato e preço de mercado na data de referência. |
| C4 | **Sinergia com ADR-040:** O workflow de promoção de overrides tem semântica clara — "fechar" o período vigente e "abrir" o novo. |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| **F1 — Schema** | Modelo `HistoricoPreco` em `domain/models/`; migração do catálogo existente | ✅ Existente |
| **F2 — Repositório** | `preco_na_data(codigo, data)` no `RepositorioInsumo` | ✅ Implementado |
| **F3 — Escrita** | `atualizar_preco()` implementando fechamento do registro anterior e abertura do novo | ✅ Implementado |
| **F4 — Integração** | Skills usando `preco_na_data(data=escopo.data_base_orcamento)` via ADR-033 | ✅ Implementado (2026-05-11) |
| **F5 — Índice** | Skill 20 calculando índice de inflação interna por categoria | ⏳ Pendente |

---

## Definition of Done

### Fase 1 — Schema (✅ Existente)
- [x] `HistoricoPreco` existe em `domain/models/catalogo.py` com campos `preco_unitario`, `valido_de`, `valido_ate`, `fonte`, `atualizado_por`.
- [x] Campo `historico_precos: list[HistoricoPreco]` existe no modelo `Insumo`.

### Fase 2 — Repositório (✅)
- [x] `preco_na_data(codigo, data)` implementado em `RepositorioInsumo`.
- [x] Consulta `historico_precos` por janela `valido_de ≤ data ≤ valido_ate`; fallback para `preco_unitario` se não encontrar.
- [ ] Método exposto via MCP para auditoria temporal.

### Fase 3 — Escrita (✅)
- [x] `atualizar_preco(codigo, novo_preco, data_vigencia, fonte)` implementado em `RepositorioInsumo`.
- [x] Fecha o registro mais recente (`valido_ate = data_vigencia - 1 dia`) antes de criar o novo.
- [x] Atualiza `preco_unitario` flat para compatibilidade com código que não usa `preco_na_data()`.
- [x] Persiste alteração no arquivo JSON do catálogo.

### Fase 4 — Integração (✅ 2026-05-11)
- [x] Skills recebem `data_base_orcamento` do `Escopo` e passam para `preco_na_data()`.
- [ ] Reprocessamento histórico produz resultados idênticos à execução original (testes de regressão pendentes).

### Fase 5 — Índice Mendes Lobo
- [ ] Skill 20 agrega `historico_precos` de todos os insumos e calcula deflator por categoria.
- [ ] Painel exportado em formato compatível com Power BI / Excel.

### Negativas / Riscos

| ID | Risco | Mitigação |
|---|---|---|
| R1 | Crescimento do tamanho dos arquivos JSON ao longo dos anos. | Arquivo de catálogo atual mantém apenas o `preco_base`; `historico_preco` migrado para arquivo separado `{codigo}_history.json` por insumo se necessário. |
| R2 | Complexidade no `RepositorioInsumo` para manter dois modos (atual + histórico). | `preco_base` continua como atalho para o preço atual; `preco_em()` é método adicional, não substituto obrigatório imediato. |
| R3 | Migração do catálogo existente — insumos sem histórico. | Script de migração que converte o `preco_base` atual em um registro `historico_preco` com `valido_de = "2026-01-01"` e `valido_ate = null`. |
