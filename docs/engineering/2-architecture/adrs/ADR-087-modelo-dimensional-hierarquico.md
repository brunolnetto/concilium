# ADR-087 — Modelo Dimensional Hierárquico: {natureza}.{atividade}.{categoria_insumo}.{propriedade}

**Status:** Implementado ✅ _(auditado 2026-06-09)_

> **Nota:** `CelulaAnalitica` com hierarquia `{natureza}.{atividade}.{categoria_insumo}.{propriedade}` implementada.
**Data:** 2026-05-29
**Autores:** Bruno Peixoto / Concilium
**Dependências:** ADR-069 (CuboAnalitico), ADR-086 (CuboPoolInstancial), ADR-085, ADR-023, ADR-030
**Supersede parcialmente:** ADR-069 (redefine a estrutura de células do CuboAnalitico)

---

## 1. Contexto

### 1.1 Problema: diesel como categoria de nível superior

O `CuboAnalitico` atual tem quatro categorias de topo:
`mao_obra | equipamento | diesel | material`

Diesel está no mesmo nível hierárquico que equipamento, mas semanticamente é uma
**propriedade de equipamento** — todo combustível consumido em obra pertence a um ativo
que o consome. Não existe consumo de diesel sem um equipamento operando.

Esta modelagem plana cria problemas:
1. **Hierarquia falsa**: diesel não é um tipo de insumo independente — é um atributo
   de custo/consumo de equipamentos.
2. **BDI inconsistente**: a taxa de diesel (21,5%) é aplicada a R$ que são inseparáveis
   do equipamento que os gerou; o modelo plano obscurece essa vinculação.
3. **Consultas incoerentes**: "qual o custo de mão-de-obra + equipamento + diesel por
   atividade?" exige somar três categorias distintas para um único tipo de análise
   (custo de operação de campo).
4. **Grandeza física orphaned**: `consumo_diesel_L` flutua como dado solto em células
   de categoria="diesel" sem âncora ao equipamento que o gerou.

### 1.2 Solução: hierarquia dimensional 4-nível

```
{natureza}.{atividade}.{categoria_insumo}.{propriedade}
```

Onde:
- **natureza**: `direto` | `indireto`
- **atividade**: item da EAP (para direto) ou categoria de indireto (ADM, TOP, …)
- **categoria_insumo**: `mao_obra` | `equipamento` | `material` | `verba`
- **propriedade**: dimensão específica da categoria

**Propriedades por categoria:**

| categoria_insumo | propriedades |
|---|---|
| `mao_obra` | `salario` · `encargos` · `horas_extras` · `funcao_id` |
| `equipamento` | `aluguel` · `combustivel` · `manutencao` · `consumo_L` · `equip_id` |
| `material` | `consumivel` · `insumo_id` · `coeficiente` |
| `verba` | `fixo` · `descricao` |

Diesel passa a ser `equipamento.combustivel` (custo R$) e `equipamento.consumo_L`
(grandeza física litros/semana). **Nenhum dado é perdido** — apenas reorganizado.

### 1.3 Relação com tempo

O eixo temporal (semana ISO) é **ortogonal** à hierarquia de custo, não um nível dela:

```
Consulta: custo por semana → slice em semana_iso
Consulta: custo por atividade → slice em atividade_id
Consulta: consumo de combustível → slice em propriedade="combustivel" + unidade_fisica="L"
```

A hierarquia dimensional define **o quê** é o custo; o tempo define **quando**.

---

## 2. Decisão

### D1 — Nova célula atômica `CelulaAnalitica` (substitui ADR-069 §D1)

```python
@dataclass(frozen=True)
class CelulaAnalitica:
    # ── Hierarquia dimensional ──
    natureza: Literal["direto", "indireto"]
    atividade_id: str                    # EAP item (direto) ou cat. indireta
    categoria_insumo: Literal["mao_obra", "equipamento", "material", "verba"]
    propriedade: str                     # ver tabela §1.2
    # ── Eixo temporal ──
    semana_iso: str                      # "2026-W23"
    # ── BDI decomposition ──
    componente_bdi: str                  # 11 componentes — inalterado
    # ── Medidas ──
    valor_rs: float                      # valor monetário (R$)
    valor_fisico: float = 0.0            # grandeza física (L para combustivel, horas para MO, etc.)
    unidade_fisica: str = ""             # "L" | "h" | "" para outros
```

**Mudanças vs ADR-069:**
- `categoria` (plana) → `categoria_insumo` + `propriedade` (hierárquica)
- `natureza` adicionado explicitamente
- `consumo_diesel_L` → `valor_fisico` + `unidade_fisica="L"` (generalizado para outras grandezas)

### D2 — Mapeamento de campos legados para nova hierarquia

| Campo legado (EquipeDireta) | Nova célula |
|---|---|
| `custo_mao_obra_mensal` | `categoria_insumo="mao_obra"`, `propriedade="salario_encargos"` |
| `custo_equipamentos_mensal` | `categoria_insumo="equipamento"`, `propriedade="aluguel"` |
| `custo_combustivel_total_mensal` | `categoria_insumo="equipamento"`, `propriedade="combustivel"` |
| `custo_material_mensal` | `categoria_insumo="material"`, `propriedade="consumivel"` |
| `consumo_litros_hora` | `categoria_insumo="equipamento"`, `propriedade="combustivel"`, `unidade_fisica="L"` |

### D3 — BDI aplicado por propriedade (detalhe em ADR-089)

O BDI é aplicado no nível de `(categoria_insumo, propriedade)`:
- `equipamento.aluguel` → `TabelaBdi.servicos` (35,5%)
- `equipamento.combustivel` → `TabelaBdi.diesel` (21,5%) — **preservado**
- `mao_obra.salario_encargos` → `TabelaBdi.mao_obra` (35,5%)
- `material.consumivel` → `TabelaBdi.material` (5%)

A separação de taxas BDI dentro da mesma `categoria_insumo` é o mecanismo que justifica
manter `propriedade` como dimensão explícita em vez de colapsar tudo em `equipamento`.

### D4 — `CuboAnalitico` continua como projeção derivada

`CuboAnalitico` continua sendo uma projeção computada sobre as células `CelulaAnalitica`.
A diferença é que o conjunto de células é mais rico (diesel aparece como propriedade de
equipamento) e as projeções/faces do ADR-069 são remapeadas:

| Face ADR-069 | Mudança |
|---|---|
| `categoria_componente` | `categoria_insumo × propriedade × componente_bdi` |
| `bar_diesel_temporal` | Sobrevive como `propriedade="combustivel"` + `valor_fisico` |
| `tempo_natureza` | Adiciona natureza como eixo explícito |

### D5 — `CuboPoolInstancial` alinha os componentes

Os campos `custo_comb` e `custo_eq` em `CelulaPoolInstancial` (ADR-086) são remapeados:
- `custo_eq` → `propriedade="aluguel"` dentro de `categoria_insumo="equipamento"`
- `custo_comb` → `propriedade="combustivel"` dentro de `categoria_insumo="equipamento"`

A distinção física é **preservada**: no pool, aluguel pode ser ativo em standby,
combustível só é consumido quando ativo. Isso continua sendo representável por
propriedades separadas dentro da mesma categoria.

---

## 3. Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| 1 | Novo `CelulaAnalitica` com `propriedade` + `valor_fisico`/`unidade_fisica`; deprecar `consumo_diesel_L` direto | 🔴 Aceito |
| 2 | `CuboAnaliticoBuilder` remapeia `_CUSTO_CAMPOS` para nova hierarquia + `_POOL_TO_ANA` | 🔴 Aceito |
| 3 | Faces do ADR-069 migram para `categoria_insumo × propriedade`; `bar_diesel_temporal` migra para `propriedade="combustivel"` | 🔴 Aceito |
| 4 | `EquipeDireta` evolui para sub-propriedades por equipamento (ADR-088); pools alinham idle logic | 🔴 Aceito |
| 5 | API `cubo-analitico/projecao` atualiza parâmetros; retro-compat via `categoria` legado | 🔴 Aceito |

## 4. Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| R1 | Manter diesel como categoria de topo (status quo) | Hierarquia semanticamente errada; diesel não é tipo de insumo |
| R2 | Colapsar diesel em equipamento sem separação de propriedade | Perde rastreabilidade BDI e grandeza física |
| R3 | Adicionar `categoria_pai` ao modelo plano | Complexidade sem semântica clara; a hierarquia é o modelo correto |

## 5. Consequências

### Positivas
- Diesel rastreável até o equipamento que o consume
- Grandeza física (L) como propriedade nomeada, extensível para outras grandezas (horas-máquina, etc.)
- Consultas naturais: "todo o custo de operação de campo para eap-1_5" = filtrar `categoria_insumo in [mao_obra, equipamento]`
- Extensível: `equipamento.manutencao` como nova propriedade sem mudar a arquitetura

### Negativas / Riscos
- Breaking change no `CuboAnalitico` (faces e clientes existentes)
- Migração de dados nos canonicals serializados (backward compat necessário)
- ADR-069 precisa de amendment formal

## 6. Relacionados

[[adr069-cubo-analitico]] [[adr086-cubo-pool-instancial]] [[adr088-decomposicao-equipamento]]
[[adr089-bdi-por-sub-propriedade]] [[adr030-cpu-team-composition-fuel-material]]
