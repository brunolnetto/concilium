# ADR-090 — BDI Sistemático: Diesel como Material e Decomposição de Indiretos por Categoria

**Status:** Aceito
**Data:** 2026-05-30
**Autores:** Bruno Peixoto / Concilium
**Amend:** ADR-087 (diesel move de equipamento.combustivel para material.combustivel),
           ADR-089 (remove TabelaBdi.diesel como campo separado, usa material)
**Novo:** sistemática BDI para indiretos por categoria_insumo
**Dependências:** ADR-087, ADR-088, ADR-089, ADR-023, ADR-009

---

## 1. Contexto

### 1.1 Dois problemas da implementação anterior (ADR-087/089)

**P1 — Diesel como sub-propriedade de equipamento cria complexidade sem benefício:**

ADR-087 posicionou diesel em `(equipamento, combustivel)`. Isso força o cascateamento
pela árvore hierárquica: para saber se o BDI_diesel (4%) se aplica, é preciso resolver
`categoria_insumo="equipamento"` E `propriedade="combustivel"`. O mesmo resultado é
obtido diretamente com `categoria_insumo="material"` — sem cascate, sem especificidade
desnecessária.

**P2 — BDI de indiretos é plano (taxa única) quando deveria ser por categoria:**

A BDI aplicada em `_calc_venda_com_bdi` usa `rate_indireto` para toda a soma
`custo_indireto_total`. Mas um custo indireto ADM tem:
- Funções (MO dos gestores) → BDI_mao_obra ≈ 30%
- Equipamentos (caminhão administrativo) → BDI_servicos ≈ 30%
- Verbas e mobilizações (overhead) → BDI_indireto ≈ 25%

Tratar tudo com 25% sub-precifica MO/EQ e sobre-precifica verbas.

### 1.2 O princípio unificador

O BDI é determinado pela **natureza econômica do fornecimento**, não pela posição na
hierarquia física:

| Natureza econômica | Taxa BDI | Exemplos |
|---|---|---|
| Prestação de serviço | ~30% (ISS + AC + DF + R + L) | MO, aluguel EQ, manutenção |
| Venda de insumo/mercadoria | 4% (só lucro) | material, diesel, areia, brita |
| Overhead administrativo | ~25% (AC + DF + R + L menor) | verbas, mobilizações indiretas |

Diesel é uma **venda de mercadoria consumida no processo** — mesma natureza que areia
ou brita. BDI = 4%, mesmo campo `TabelaBdi.material`.

Mobilizações de equipes indiretas são **custo administrativo de gestão do projeto** —
não terceirização. BDI = BDI_indireto.

---

## 2. Decisão

### D1 — Diesel como `(material, combustivel)` (amend ADR-087)

```
ANTES: equipamento.combustivel → BDI_diesel (redundante com material)
DEPOIS: material.combustivel   → BDI_material (4%)
```

`material.consumivel` = insumos de processo (areia, brita, cimento…)
`material.combustivel` = insumos energéticos consumidos no campo (diesel)

Ambos têm BDI_material = 4%. A distinção `combustivel` vs `consumivel` permanece como
propriedade para rastreabilidade de planejamento físico (litros, emissões, etc.).

### D2 — `TabelaBdi.diesel` removido; `CategoriaBdi` simplificada (amend ADR-089)

```python
# ANTES
CategoriaBdi = Literal["MAO_OBRA", "MATERIAL", "SERVICOS", "INDIRETO", "DIESEL"]
class TabelaBdi: diesel: ComponentesBdi  # 4% — igual ao material

# DEPOIS
CategoriaBdi = Literal["MAO_OBRA", "MATERIAL", "SERVICOS", "INDIRETO"]
# TabelaBdi.diesel removido — usar TabelaBdi.material
```

**Retrocompatibilidade:** `TabelaBdi.para_categoria("DIESEL")` delega para `material`.

### D3 — Lookup BDI unificado `_PROP_BDI_MAP` (amend ADR-089 + extensão para indiretos)

```python
_PROP_BDI_MAP: dict[tuple[str, str], str] = {
    # Direto e indireto — mesmo mapa
    ("mao_obra",    "salario_encargos"): "mao_obra",
    ("equipamento", "aluguel"):          "servicos",
    ("equipamento", "manutencao"):       "servicos",
    ("material",    "consumivel"):       "material",
    ("material",    "combustivel"):      "material",   # diesel = material
    ("verba",       "fixo"):             "indireto",
    ("verba",       "mobilizacao"):      "indireto",   # overhead, não serviço externo
}
```

### D4 — `Indireto` expõe sub-custos por `categoria_insumo`

Skill-07 computa e popula campos novos em `Indireto`:

```python
class Indireto(BaseModel):
    # ... campos existentes ...
    custo_mao_obra: float = 0.0      # Σ funcoes.custo_mensal × permanencia
    custo_equipamentos: float = 0.0  # Σ equip.custo_mensal (sem combustivel)
    custo_combustivel: float = 0.0   # Σ equip.custo_combustivel_mensal
    custo_verba: float = 0.0         # Σ verbas_mensais + verbas_fixas
    custo_mobilizacao: float = 0.0   # Σ mobilizacoes.custo_total
    # Invariante: custo_total ≈ custo_mao_obra + custo_equipamentos
    #                          + custo_combustivel + custo_verba + custo_mobilizacao
```

### D5 — BDI de indiretos por sub-categoria (amend skill-08)

```python
# ANTES: taxa plana
venda_indireto = custo_indireto_total * (1 + rate_indireto)

# DEPOIS: por categoria_insumo
for ind in canonical.indiretos:
    venda_indireto += (
        ind.custo_mao_obra     * (1 + bdi["mao_obra"])
        + ind.custo_equipamentos * (1 + bdi["servicos"])
        + ind.custo_combustivel  * (1 + bdi["material"])
        + ind.custo_verba        * (1 + bdi["indireto"])
        + ind.custo_mobilizacao  * (1 + bdi["indireto"])
    )
```

### D6 — `CelulaAnalitica` backward compat preservado

`c.categoria` para `(material, combustivel)` continua retornando `"diesel"` via property.
O `CuboAnalitico.consumo_diesel_temporal()` e `is_diesel()` continuam funcionando.

---

## 3. Plano de Implementação

| Fase | Entrega | Status |
|---|---|---|
| 1 | `TabelaBdi`: remove `diesel`, `para_categoria("DIESEL")` → delega para `material` | 🔴 |
| 2 | `CelulaAnalitica`: `is_diesel()` → `(material, combustivel)`; `categoria` → backward compat | 🔴 |
| 3 | `CuboAnaliticoBuilder._PROP_BDI_MAP/_POOL_TO_PROP`: combustivel → `(material, combustivel)` | 🔴 |
| 4 | `Indireto` model: add sub-cost fields; skill-07: compute them | 🔴 |
| 5 | skill-08 `_calc_venda_com_bdi`: BDI por sub-categoria de indireto | 🔴 |
| 6 | Testes + AGIS | 🔴 |

## 4. Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| R1 | Manter diesel em `equipamento.combustivel` | Cascateamento desnecessário; mesmo resultado com material |
| R2 | BDI_diesel separado de BDI_material (taxas diferentes) | Fiscalmente idênticos (4%); separação cria complexidade sem valor |
| R3 | Mobilizações de indireto com BDI_servicos | Mobilizações internas não são serviço terceirizado; ADM correto |

## 5. Relacionados

[[adr087-modelo-dimensional-hierarquico]] [[adr088-decomposicao-subcomposicional-equipamento]]
[[adr089-bdi-por-sub-propriedade]] [[adr023-bdi-diferenciado-por-categoria]]
[[adr009-indirect-costs-as-first-class]]
