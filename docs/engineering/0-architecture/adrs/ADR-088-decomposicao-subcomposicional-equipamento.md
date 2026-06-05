# ADR-088 — Decomposição Sub-composicional de Equipamento: Aluguel, Combustível e Manutenção como Sub-propriedades

**Status:** Aceito
**Data:** 2026-05-29
**Autores:** Bruno Peixoto / Concilium
**Dependências:** ADR-087, ADR-085, ADR-086, ADR-030, ADR-077, ADR-079
**Amend:** ADR-030 (expande D3 — antes separava combustível apenas no EquipeDireta)

---

## 1. Contexto

### 1.1 Estado atual (ADR-030 D3)

ADR-030 estabeleceu a separação `custo_equipamentos_mensal` vs `custo_combustivel_total_mensal`
no nível de `EquipeDireta` (equipe por atividade). Essa separação existe **apenas na raiz** —
não desce ao nível de cada `EquipamentoEquipeDireta` individual.

Consequências:
- Não é possível saber qual equipamento dentro de uma equipe consome quanto de combustível
  sem re-derivar da taxa `consumo_litros_hora × horas_mes`.
- O modelo de custo do pool (ADR-085) usa `custo_unit_semanal_eq` e `custo_unit_semanal_comb`
  como médias de contrato, perdendo a granularidade por equipamento.
- A taxa de standby (`custo_idle_semanal_unit`, ADR-079) é um escalar único para o contrato,
  sem distinção entre a fração aluguel-puro e a fração manutenção.

### 1.2 O que muda com a hierarquia dimensional (ADR-087)

ADR-087 define `categoria_insumo="equipamento"` com propriedades `aluguel | combustivel |
manutencao`. Para que o `CuboAnaliticoBuilder` possa emitir essas células, a fonte de dados
(`EquipamentoEquipeDireta` e `EquipeDireta`) precisa expor os sub-custos com a mesma
granularidade.

### 1.3 Três sub-custos distintos de um equipamento

| Sub-custo | Comportamento em standby | Comportamento em OFF |
|---|---|---|
| **Aluguel** (`custo_locacao`) | Cobrado integral (locação mínima) | Zero (contrato encerrado) |
| **Combustível** (`custo_combustivel`) | **Zero** (sem operação) | Zero |
| **Manutenção** (`custo_manutencao`) | Reduzida (apenas preventiva) ou zero | Zero |

Esta distinção é fundamental para o modelo de idle cost do ADR-085: no standby, o equipamento
incorre em aluguel mas não em combustível. O modelo atual trata `custo_idle_semanal_unit`
como escalar do contrato; com a sub-decomposição, o idle passa a ser:

```
custo_idle_instancia = custo_locacao_sem × idle_weeks
                     + 0                × idle_weeks  (combustivel)
                     + custo_manut_idle × idle_weeks  (manutenção reduzida)
```

---

## 2. Decisão

### D1 — `EquipamentoEquipeDireta` ganha sub-custos explícitos

```python
class EquipamentoEquipeDireta(BaseModel):
    # ... campos existentes mantidos para retrocompat ...
    equip_id: str
    descricao: str
    num_unidades: int
    # Custo mensal total (existente — mantido como computed property)
    custo_mensal: float = 0.0           # = custo_locacao + custo_manutencao (sem comb)
    # Sub-decomposição (ADR-088 novos campos)
    custo_locacao_mensal: float = 0.0   # aluguel puro do ativo (contrato de locação)
    custo_manutencao_mensal: float = 0.0 # manutenção prevista (lubrificação, filtros, etc.)
    custo_combustivel_mensal: float = 0.0 # derivado de consumo_litros_hora × horas × preco
    # Grandeza física (existente)
    consumo_litros_hora: float | None = None
    # Idle rates por sub-custo (ADR-088 novos campos; usado em ADR-085/086)
    custo_locacao_idle_mensal: float = 0.0   # aluguel durante standby (= custo_locacao em geral)
    custo_manutencao_idle_mensal: float = 0.0 # manutenção durante standby (geralmente 0)
    # rental_unit, custo_mobilizacao, custo_desmobilizacao — existentes, mantidos
```

**Invariante de consistência:**
```
custo_mensal ≈ custo_locacao_mensal + custo_manutencao_mensal
custo_mensal_total = custo_mensal + custo_combustivel_mensal
```

### D2 — `EquipeDireta` expõe sub-totais da equipe

```python
class EquipeDireta(BaseModel):
    # ... campos existentes mantidos ...
    # Novos campos de sub-decomposição (ADR-088)
    custo_locacao_mensal: float = 0.0      # Σ equipamentos.custo_locacao_mensal × num_unidades
    custo_manutencao_mensal: float = 0.0   # Σ equipamentos.custo_manutencao_mensal × num_unidades
    # custo_equipamentos_mensal (existente) = custo_locacao_mensal + custo_manutencao_mensal
    # custo_combustivel_total_mensal (existente) — preservado
```

### D3 — Skill-05 popula os sub-custos

Em `_calcular_custo_equipamento` (skill-05):
- Fonte do `custo_locacao`: `_converter_preco_equip(insumo, horas_dia, dias_uteis)` — já existente
- Fonte do `custo_manutencao`: `custo_manutencao_hora × horas_dia × dias_uteis` — já disponível
  em `EquipamentoEquipeDireta.custo_manutencao_hora` (ADR-077/NEP-031 L5)
- Fonte do `custo_combustivel`: já separado como `custo_combustivel_mensal`

```python
# Em _calcular_custo_equipamento (adição):
custo_locacao  = custo_base  # preco × horas (o "aluguel puro")
custo_manut    = custo_manutencao_hora * horas_mes  # ADR-077/NEP-031 L5 — já existe!
custo_comb     = consumo * horas_mes * preco_diesel  # já separado

return EquipamentoEquipeDireta(
    ...
    custo_locacao_mensal=round(custo_locacao, 2),
    custo_manutencao_mensal=round(custo_manut, 2),
    custo_combustivel_mensal=round(custo_comb, 2),
    custo_locacao_idle_mensal=round(custo_locacao, 2),   # aluguel integral em standby
    custo_manutencao_idle_mensal=0.0,                    # zero em standby (simplificação)
)
```

### D4 — Pool idle cost refinado por sub-propriedade

No ADR-085/086, a taxa de standby é:
```python
# Atual (ADR-085 D2):
c_idle_eq = c_idle_unit  # escalar do contrato (rho × custo_eq)

# Nova (ADR-088 D4):
c_idle_locacao = custo_unit_semanal_locacao        # integral em standby
c_idle_manut   = custo_unit_semanal_manutencao * 0 # zero em standby (simplificação)
c_idle_comb    = 0.0                               # zero — sem operação
# rho_idle_eq (ADR-085) agora reflete apenas locação/equipamento, não manutenção
```

### D5 — `RecursoContrato` adiciona taxas por sub-propriedade

```python
class RecursoContrato(BaseModel):
    # ... campos existentes ...
    # ADR-088: taxas por sub-propriedade (refinam custo_unit_semanal_eq)
    custo_unit_semanal_locacao: float = 0.0    # aluguel puro
    custo_unit_semanal_manutencao: float = 0.0 # manutenção
    # custo_unit_semanal_comb (existente) — combustível
    # custo_unit_semanal_mo (existente) — MO
    # custo_unit_semanal_eq (existente) = locacao + manutencao
```

### D6 — Retrocompatibilidade

`custo_equipamentos_mensal` e `custo_combustivel_total_mensal` (ADR-030) são **preservados**
como campos derivados (soma das sub-propriedades). Código existente continua funcionando.
A migração é **aditiva**, não destrutiva.

---

## 3. Impacto no Modelo de Custo Instancial (ADR-085)

A fórmula de custo instancial por componente (ADR-085 D3) evolui:

```
# Atual:
custo(I_k) = c_mo × prod_weeks
           + c_eq × prod_weeks        (aluguel + manutencao bundled)
           + c_comb × prod_weeks      (combustivel)
           + c_idle_mo × idle_weeks   (MO integral em standby)
           + c_idle_eq × idle_weeks   (aluguel reduzido = rho × c_eq)

# ADR-088:
custo(I_k) = c_mo × prod_weeks
           + (c_locacao + c_manut) × prod_weeks   (separados mas computáveis juntos)
           + c_comb × prod_weeks
           + c_idle_mo × idle_weeks              (MO integral — inalterado)
           + c_locacao × idle_weeks              (aluguel integral — clarificado)
           + 0 × idle_weeks                      (manutencao e comb — explicitamente zero)
```

A diferença prática: `rho_idle_eq = c_idle_eq / c_eq` agora pode ser derivado rigorosamente
como `c_locacao / (c_locacao + c_manut)` em vez de ser um parâmetro configurado no catálogo.

---

## 4. Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| 1 | Campos em `EquipamentoEquipeDireta`: custo_locacao/manut/comb_mensal + idle | 🔴 Aceito |
| 2 | Campos em `EquipeDireta`: custo_locacao/manutencao_mensal | 🔴 Aceito |
| 3 | `_calcular_custo_equipamento` (skill-05) popula sub-custos | 🔴 Aceito |
| 4 | `RecursoContrato` adiciona custo_unit_semanal_locacao/manutencao | 🔴 Aceito |
| 5 | ADR-085 `calcular_custo_instancia_composicional` usa sub-custos | 🔴 Aceito |
| 6 | Testes + rebaseline AGIS | 🔴 Aceito |

## 5. Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| R1 | Manter `custo_equipamentos_mensal` bundled | Não permite idle rigorous; manutencao e aluguel têm perfis de standby diferentes |
| R2 | Definir `rho_idle_eq` como configuração do catálogo | Heurístico; deve emergir da composição real de locação/manutenção |

## 6. Relacionados

[[adr087-modelo-dimensional-hierarquico]] [[adr089-bdi-por-sub-propriedade]]
[[adr085-custo-instancial-composicional-temporal]] [[adr030-cpu-team-composition-fuel-material]]
[[adr077-recurso-instancial-utilizacao]]
