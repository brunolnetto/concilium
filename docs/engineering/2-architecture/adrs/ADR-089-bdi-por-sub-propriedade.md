# ADR-089 — BDI por Sub-propriedade de Insumo: Diesel como Propriedade de Equipamento com Taxa Própria

**Status:** Aceito
**Data:** 2026-05-29
**Autores:** Bruno Peixoto / Concilium
**Amend:** ADR-023 (BDI Diferenciado por Categoria) — mantém as taxas, refatora o mapeamento
**Dependências:** ADR-087, ADR-088, ADR-023, ADR-055 (CBS/IBS)

---

## 1. Contexto

### 1.1 ADR-023: O que estabelece

ADR-023 estabeleceu quatro categorias de BDI:
- `mao_obra` → BDI ≈ 29,97% (TCU fórmula multiplicativa)
- `material` → BDI = 4,00% (só lucro)
- `servicos` → BDI ≈ 29,97% (mesmo que MO — equipamentos tratados como serviços)
- `diesel` → BDI = 4,00% (fornecimento de insumo, sem tributos sobre prestação)

A taxa diesel é justificada juridicamente: combustível é **fornecimento de mercadoria**,
não prestação de serviço — portanto sem ISS, CSSL, IR sobre o valor. Apenas lucro 4%.

### 1.2 Tensão com a nova hierarquia (ADR-087/088)

ADR-087 define `categoria_insumo="equipamento"` com propriedades `aluguel | combustivel |
manutencao`. Isso cria uma situação onde **uma única categoria tem duas taxas BDI diferentes**:

```
equipamento.aluguel     → BDI_servicos ≈ 29,97%
equipamento.combustivel → BDI_diesel    = 4,00%
equipamento.manutencao  → BDI_servicos ≈ 29,97%  (ou BDI específico futuro)
```

O modelo de BDI precisa ser **property-aware**: não basta saber `categoria_insumo`, é preciso
saber `propriedade` para aplicar a taxa correta.

### 1.3 Por que as taxas devem permanecer distintas

A diferença entre 4% e 29,97% não é calibração técnica — é fundamentação jurídico-tributária:

| Categoria fiscal | Tributo | BDI_servicos | BDI_diesel/material |
|---|---|---|---|
| Prestação de serviço | ISS | 5,00% | 0% |
| Lucro sobre serviço | CSSL + IR | 4,73% | 0% |
| Overhead operacional | AC + DF + R | 7,56% | 0% |
| Margem de lucro | L | 9,00% | 4,00% |
| **Total** | | **≈ 29,97%** | **4,00%** |

Colapsar diesel no BDI de equipamento (29,97%) **super-precifica o combustível** em 25 p.p.,
tornando a proposta não competitiva e tecnicamente incorreta do ponto de vista fiscal.

---

## 2. Decisão

### D1 — `TabelaBdi` mantém campo `diesel`; é remapeado por propriedade

`TabelaBdi.diesel: ComponentesBdi` é preservado. O que muda é como o BDI é **selecionado**
durante a construção do cubo analítico:

```python
# Antes (ADR-023 / cubo_analitico_builder.py):
_CUSTO_CAMPOS = [
    ("custo_mao_obra_mensal",        "mao_obra",   "mao_obra"),
    ("custo_equipamentos_mensal",    "equipamento", "servicos"),  # → TabelaBdi.servicos
    ("custo_combustivel_total_mensal","diesel",     "diesel"),   # → TabelaBdi.diesel
    ("custo_material_mensal",        "material",   "material"),
]

# Depois (ADR-089):
_PROP_BDI_MAP = {
    ("mao_obra",    "salario_encargos"): "mao_obra",
    ("equipamento", "aluguel"):          "servicos",
    ("equipamento", "combustivel"):      "diesel",    # ← taxa diesel preservada
    ("equipamento", "manutencao"):       "servicos",
    ("material",    "consumivel"):       "material",
    ("verba",       "fixo"):             "indireto",
}
```

### D2 — `CategoriaBdi` não muda (preserva retrocompatibilidade)

```python
CategoriaBdi = Literal["MAO_OBRA", "MATERIAL", "SERVICOS", "INDIRETO", "DIESEL"]
```

`DIESEL` permanece em `CategoriaBdi` e em `TabelaBdi`. A única mudança é que o
**roteamento** para `DIESEL` agora é feito via `(categoria_insumo, propriedade)` em vez
de `categoria_legado`. O campo `TabelaBdi.diesel` não é renomeado ou removido.

### D3 — `_build_custo_categorial_bottom_up` usa roteamento por propriedade

Em skill-08, a função que alimenta o preço bottom-up (ADR-085 D5) é atualizada:

```python
# Antes: sum de custo_inst_comb separado
cat["diesel"] += part.custo_inst_comb

# Depois: diesel vai para equipamentos mas com BDI_diesel aplicado
cat_equip_aluguel["servicos"] += part.custo_inst_eq     # BDI_servicos
cat_equip_comb["diesel"]      += part.custo_inst_comb   # BDI_diesel — preservado
# No cálculo de venda:
venda_direto = (
    cat["mao_obra"] * (1 + bdi["mao_obra"])
    + cat_equip_aluguel["servicos"] * (1 + bdi["servicos"])  # aluguel + manutencao
    + cat_equip_comb["diesel"] * (1 + bdi["diesel"])          # combustivel
    + cat["material"] * (1 + bdi["material"])
)
```

A lógica de **aplicação** fica clara: dois sub-grupos dentro de `equipamento`, cada um com
seu BDI correto.

### D4 — `decomposicao_no_preco` por propriedade

`ComponentesBdi.decomposicao_no_preco()` já decompõe em 11 componentes BDI. Para a nova
hierarquia, cada `(categoria_insumo, propriedade)` tem sua própria decomposição:

```
cell(natureza, atividade, equipamento, aluguel, semana, componente_bdi) → BDI_servicos
cell(natureza, atividade, equipamento, combustivel, semana, componente_bdi) → BDI_diesel
```

`equipamento.combustivel` terá apenas `custo_direto` e `margem_l` como componentes BDI
não-zero (diesel: AC=DF=R=tributos=0; apenas L=4%). As outras 10 frações serão zero.

### D5 — Extensão para ADR-055 CBS/IBS

Com a nova hierarquia, o crédito CBS/IBS por categoria pode ser especificado por propriedade:

```python
class TaxSimulationScenario(BaseModel):
    # ... existente ...
    # ADR-089: crédito por propriedade de equipamento
    credit_ratio_equip_aluguel: float = 0.0    # serviços — crédito sobre ISS
    credit_ratio_equip_combustivel: float = 0.0 # mercadoria — crédito sobre PIS/COFINS
```

Isso substitui `credit_ratio_diesel` (legado) por uma estrutura property-aware.

---

## 3. Resumo das Taxas (inalteradas em valores, refatoradas no mapeamento)

| `(categoria_insumo, propriedade)` | `TabelaBdi` usada | BDI efetivo | Fundamento |
|---|---|---|---|
| `mao_obra.salario_encargos` | `mao_obra` | ≈ 29,97% | Prestação de serviço (MO) |
| `equipamento.aluguel` | `servicos` | ≈ 29,97% | Locação de equipamento como serviço |
| `equipamento.combustivel` | `diesel` | 4,00% | **Fornecimento de mercadoria (combustível)** |
| `equipamento.manutencao` | `servicos` | ≈ 29,97% | Serviço de manutenção |
| `material.consumivel` | `material` | 4,00% | Fornecimento de material |
| `verba.fixo` | `indireto` | ≈ 25,21% | Verba administrativa/indireta |

### Comentário sobre `equipamento.combustivel` vs `material.consumivel` (ambos 4%)

Embora a taxa seja a mesma (4%), a distinção é semanticamente necessária:
- `material.consumivel` é um **insumo de processo** (p.ex. cimento, areia)
- `equipamento.combustivel` é um **insumo de operação de ativo** — rastreável ao equipamento
  que o consome, com grandeza física (L/h) e rastreabilidade de OEE

Colapsar os dois na mesma célula perderia a âncora ao equipamento e o planejamento físico.

---

## 4. Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| 1 | `_PROP_BDI_MAP` em `cubo_analitico_builder.py` + `CelulaAnalitica.propriedade` (ADR-087 F1) | 🔴 Aceito |
| 2 | `_build_custo_categorial_bottom_up` usa `_PROP_BDI_MAP` para BDI correto por sub-custo | 🔴 Aceito |
| 3 | `TaxSimulationScenario` migra `credit_ratio_diesel` → `credit_ratio_equip_combustivel` | 🔴 Aceito |
| 4 | Testes BDI: verificar que `diesel×4%` e `servicos×30%` coexistem dentro de `equipamento` | 🔴 Aceito |

## 5. Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| R1 | BDI único para `equipamento` (blend ponderado) | Super-precifica diesel; não defensável em licitação TCU |
| R2 | Remover `TabelaBdi.diesel`; usar `material` para diesel | Semântica errada — diesel tem valor L diferente de material; CategoriaBdi perde granularidade |
| R3 | BDI diesel = BDI servicos (uniformizar) | Aumenta preço em 25 p.p. para combustível; anti-competitivo e fiscalmente incorreto |

## 6. Relacionados

[[adr087-modelo-dimensional-hierarquico]] [[adr088-decomposicao-subcomposicional-equipamento]]
[[adr023-bdi-diferenciado-por-categoria]] [[adr055-tax-reform-bdi-cbs-ibs]]
