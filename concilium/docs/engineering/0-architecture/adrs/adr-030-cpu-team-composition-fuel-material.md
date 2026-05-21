# ADR-030 — Composição Tipada de Equipes para CPU: Mão de Obra, Equipamento, Material e Combustível

**Status:** Implementado  
**Data:** 2026-05-05
**Data Implementado:** 2026-05-04
**Contexto:** MendesLobo Construtora — Concilium

---

## Contexto

### Problema

O modelo atual de composição de equipes para uma CPU possui três lacunas estruturais:

#### L1 — Material ausente da `ComposicaoPadraoEquipe`

`ComposicaoPadraoEquipe` especifica apenas `funcoes` (mão de obra) e `equipamentos`. O consumo de **materiais** por hora de produção (concreto, areia, brita, aço, tubos) está em `CPU.composicao_itens[*].categoria_custo == "MATERIAL"` — mas é uma lista de insumos com coeficiente, não um elemento da equipe. Não há como derivar o custo de material por turno sem varrer `composicao_itens` separadamente.

#### L2 — Combustível não é first-class na visão de equipe

`EquipamentoEquipeDireta.custo_combustivel_mensal` já é calculado em skill 03 a partir de `Insumo.atributos_especificos.consumo_litros_hora`. Porém:
- `EquipamentoEquipe` (a especificação no catálogo) não carrega `consumo_litros_hora` — isso obriga a consulta ao `Insumo` para qualquer estimativa
- `EquipeDireta` (saída de skill 03) não expõe `custo_combustivel_total_mensal` como campo de primeiro nível — o combustível está diluído em `custo_equipamentos_mensal`
- Não há fonte para **estimativa inicial** de combustível sem o catálogo completo carregado

#### L3 — Sem distinção entre estimativa inicial e valor refinado

O workflow atual requer o catálogo completo (insumos com preços calibrados) para qualquer cálculo de custo de equipe. Não existe caminho para produzir uma **estimativa paramétrica inicial** a partir da `ComposicaoPadraoEquipe` usando índices setoriais (custo/hora por tipo de equipamento, faixa salarial por função) antes que o catálogo detalhado esteja disponível.

### Evidências da planilha de referência (`rfi_catalog.xlsm`)

A aba **COMPOSIÇÃO** da planilha discrimina, por CPU, quatro dimensões de custo da equipe:

| Dimensão | Coluna na planilha | Mapeamento atual |
|---|---|---|
| Mão de obra (salário + encargos) | `CUSTO_MO_H` | `FuncaoEquipeDireta.custo_mensal_unitario` ✅ |
| Equipamento (operação + depreciação) | `CUSTO_EQ_H` | `EquipamentoEquipeDireta.custo_mensal` ✅ |
| Combustível (litros/hora × preço) | `CUSTO_COMB_H` | `EquipamentoEquipeDireta.custo_combustivel_mensal` ✅ mas não first-class |
| Material direto (consumo/hora × preço) | `CUSTO_MAT_H` | ❌ ausente em `ComposicaoPadraoEquipe` |

A planilha também discrimina, por equipamento na composição, `CONSUMO_L_H` (litros/hora) — dado que hoje só existe em `Insumo.atributos_especificos.consumo_litros_hora`, não na equipe.

---

## Decisão

### D1 — Enriquecer `EquipamentoEquipe` com `consumo_litros_hora_estimado`

Adicionar campo opcional à especificação de equipe no catálogo para permitir estimativas sem lookup de insumo:

```python
class EquipamentoEquipe(BaseModel):
    equip_id: str
    num_unidades: int = Field(ge=1)
    # ADR-030: consumo de combustível da equipe — sobreposição ao valor do Insumo
    consumo_litros_hora_estimado: float | None = Field(default=None, ge=0,
        description=(
            "Consumo de combustível por equipamento por hora, em L/h. "
            "Se fornecido, sobrepõe Insumo.atributos_especificos.consumo_litros_hora "
            "na derivação de custo de skill 03. "
            "Permite estimativas iniciais sem catálogo completo."
        )
    )
```

**Precedência de consumo_litros_hora em skill 03:**
1. `composicao_customizada[item_id].equipamentos[equip_id].consumo_litros_hora` (override de projeto)
2. `EquipamentoEquipe.consumo_litros_hora_estimado` (catálogo da CPU)
3. `Insumo.atributos_especificos.consumo_litros_hora` (catálogo do insumo)
4. `0.0` com `VAL-EQUIP-COMB-03` AVISO

### D2 — Adicionar `MaterialEquipe` em `ComposicaoPadraoEquipe`

Incluir consumo de materiais como parte declarativa da equipe padrão:

```python
class MaterialEquipe(BaseModel):
    """Consumo de material direto por hora de produção da CPU."""

    model_config = ConfigDict(extra="forbid")

    insumo_id: str
    consumo_por_hora: float = Field(gt=0,
        description="Quantidade consumida por hora de operação da equipe (ex: m³/h, kg/h, t/h)")
    unidade: str
    descricao: str | None = None


class ComposicaoPadraoEquipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    funcoes: list[FuncaoEquipe]
    equipamentos: list[EquipamentoEquipe]
    materiais: list[MaterialEquipe] = Field(default_factory=list)  # ADR-030
```

**Nota:** `composicao_itens` na CPU continua sendo a fonte de custo para skill 04 (BDI). `MaterialEquipe` é a especificação de consumo por hora para skill 03. Os dois devem ser consistentes — `VAL-EQUIP-MAT-01` verifica se todo `MaterialEquipe.insumo_id` está em `composicao_itens`.

### D3 — Expor `custo_combustivel_total_mensal` e `custo_material_mensal` em `EquipeDireta`

```python
class EquipeDireta(BaseModel):
    # ... campos existentes ...
    custo_mao_obra_mensal: float = 0.0
    custo_equipamentos_mensal: float = 0.0    # equipamento sem combustível
    custo_combustivel_total_mensal: float = 0.0  # ADR-030: soma de todos os combustíveis
    custo_material_mensal: float = 0.0           # ADR-030: materiais diretos da equipe
    custo_fixo_mensal: float = 0.0
    permanencia_meses: float = Field(default=0.0, ge=0)
    custo_total: float = 0.0
```

**Mudança de semântica:** `custo_equipamentos_mensal` passa a representar somente custo de equipamento **excluindo combustível**. `custo_total` continua incluindo todos os componentes. Retrocompatibilidade: os campos novos têm `default=0.0`, então canônicos antigos continuam válidos.

### D4 — Modo de estimativa inicial vs. valor refinado

Introduzir distinção explícita no output de skill 03:

```python
class EquipeDireta(BaseModel):
    # ...
    modo_estimativa: Literal["inicial", "refinado"] = "refinado"
    # "inicial": custo derivado de ComposicaoPadraoEquipe + índices de catálogo
    # "refinado": custo com override por projeto (composicao_customizada)
```

Skill 03 emite `modo_estimativa="inicial"` quando não há `composicao_customizada` para o item. Emite `"refinado"` quando usa o override.

### D5 — Validações novas

| Código | Status | Condição |
|--------|--------|----------|
| `VAL-EQUIP-MAT-01` | AVISO | `MaterialEquipe.insumo_id` não encontrado em `composicao_itens` da CPU |
| `VAL-EQUIP-MAT-02` | AVISO | `CPU.composicao_itens` tem item `MATERIAL` não coberto por nenhum `MaterialEquipe` |
| `VAL-EQUIP-COMB-01` | OK | `consumo_litros_hora` resolvido de `EquipamentoEquipe.consumo_litros_hora_estimado` |
| `VAL-EQUIP-COMB-02` | OK | `consumo_litros_hora` resolvido de `Insumo.atributos_especificos` |
| `VAL-EQUIP-COMB-03` | AVISO | `consumo_litros_hora` não encontrado; combustível zerado |
| `VAL-EQUIP-MODO-INICIAL` | INFO | Equipe calculada em modo estimativa inicial (sem override de projeto) |

### D6 — Workflow de estimativa inicial → refinamento

```
Fase de Estimativa Inicial (S0/S1)
  ├── Catálogo contém CPU com ComposicaoPadraoEquipe + MaterialEquipe
  ├── Skill 03: modo_estimativa="inicial"
  │   └── custo_combustivel_total_mensal derivado de EquipamentoEquipe.consumo_litros_hora_estimado
  └── Skill 04: custo_material derivado de composicao_itens (coeficiente × preco_unitario)

Fase de Refinamento (S1 → S2)
  ├── Engenheiro informa composicao_customizada por item (via MCP ou CLI)
  ├── Skill 03: modo_estimativa="refinado"
  │   └── custo_combustivel usa consumo medido da obra (override)
  └── Skill 04: pode receber bdi_perfil atualizado
```

---

## Validação

```
VAL-EQUIP-MAT-01: CPU "ESCO-CARGA-1CAT" tem MaterialEquipe
  com insumo_id="AREAO-M3" não listado em composicao_itens → AVISO

VAL-EQUIP-MAT-02: CPU "COMP-SOLO-PD95" tem composicao_itens MATERIAL
  (INS-AGU-PIST) sem cobertura em MaterialEquipe → AVISO

VAL-EQUIP-COMB-03: Equipamento "EQ-ROLO-PE-01" sem consumo_litros_hora
  em EquipamentoEquipe nem em Insumo; custo_combustivel_mensal=0 → AVISO
```

---

## ADRs Relacionados

- **ADR-006** (adr-006-team-composition): estratégia de replanning — usa `EquipeDireta`
- **ADR-010** (adr-010-activity-cost-breakdown-and-resource-allocation): breakdown de custos por atividade
- **ADR-011** (adr-011-computable-productivity): `ProdutividadeDetalhada` com `ComponenteCombustivel`
- **ADR-023** §D3 (`DecomposicaoEquipamento`): decompõe custo horário por sub-categoria BDI
- **ADR-027** (`CpuExposurePerfil`): exposição a custos — `pct_diesel` é derivado de `custo_combustivel_total_mensal / custo_total`

---

## Definition of Done

### Fase A — Modelos

- [x] `EquipamentoEquipe.consumo_litros_hora_estimado: float | None` adicionado a `models/catalogo.py`
- [x] `MaterialEquipe` model criado em `models/catalogo.py`
- [x] `ComposicaoPadraoEquipe.materiais: list[MaterialEquipe]` adicionado
- [x] `EquipeDireta.custo_combustivel_total_mensal: float = 0.0` adicionado a `models/canonical.py`
- [x] `EquipeDireta.custo_material_mensal: float = 0.0` adicionado
- [x] `EquipeDireta.modo_estimativa: Literal["inicial", "refinado"] = "refinado"` adicionado

### Fase B — Skill 03

- [x] Skill 03 usa `consumo_litros_hora_estimado` quando disponível (precedência D1)
- [x] Skill 03 calcula `custo_combustivel_total_mensal` somando todos os equipamentos
- [x] Skill 03 calcula `custo_material_mensal` a partir de `MaterialEquipe` × `preco_unitario` × `horas_mes`
- [x] Skill 03 emite `VAL-EQUIP-MAT-01/02` e `VAL-EQUIP-COMB-01/02/03`
- [x] Skill 03 preenche `modo_estimativa`

### Fase C — Testes

- [x] `ComposicaoPadraoEquipe` com `materiais` valida corretamente
- [x] `EquipamentoEquipe` com `consumo_litros_hora_estimado` sobrepõe valor do Insumo em skill 03
- [x] `EquipeDireta.custo_combustivel_total_mensal` == soma de `equipamentos[*].custo_combustivel_mensal`
- [x] `modo_estimativa == "inicial"` quando não há override; `"refinado"` com `composicao_customizada`
- [x] `VAL-EQUIP-COMB-03` emitido para equipamento sem consumo em nenhuma fonte
- [x] Todos os testes existentes de skill 03 continuam passando
