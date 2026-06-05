# ADR-027 — CPU Sensitivity Profile: Exposição a Custos como Atributo da CPU

**Status:** Implementado
**Data:** 2026-05-04
**Data Implementado:** 2026-05-04
**Implementadores:** models/canonical.py (CpuExposurePerfil), skills/09-cost-criticality/skill.py (derivar exposição da CPU), config/catalogos/agis/cpus.json (campo `sensitivity_perfil` opcional)
**Contexto:** MendesLobo Construtora — Concilium

---

## Contexto

### Problema

A dimensão `sensibilidade` em `09-cost-criticality` é calculada como:

```
sensitivity = custo_mao_obra_mensal × permanencia_meses / custo_total
```

Essa heurística usa somente o resultado consolidado da skill 03 — sem memória da CPU que originou aquela composição de custo. Consequência: duas atividades com o mesmo `sensitivity` heurístico podem ter perfis de risco completamente diferentes se uma delas usa equipamentos com preço indexado a combustível e a outra usa mão de obra com tabela sindical fixa.

Além disso, o `RelatorioSensibilidade` (ADR-026 §D4, skill 16) lista levers de margem por tipo de intervenção, mas não revela qual CPU cria maior exposição a risco de overrun — dado essencial para a decisão de substituir uma CPU por outra equivalente com menor volatilidade.

### Dimensões de exposição intrínseca de uma CPU

A composição `composicao_itens` de uma CPU determina três dimensões de volatilidade:

| Dimensão | Insumo | Volatilidade típica |
|---|---|---|
| `pct_equip` | `categoria_custo = "EQUIPAMENTO"` | Alta — indexado a câmbio + combustível |
| `pct_diesel` | `categoria_custo = "DIESEL"` | Muito alta — commodity de mercado |
| `pct_mo` | `categoria_custo = "MAO_OBRA"` | Baixa-média — tabela sindical negociada |
| `pct_material` | demais | Variável por tipo |

Uma CPU com 60% de custo em diesel tem sensibilidade estruturalmente maior do que uma com 60% de mão de obra — independentemente do custo total.

---

## Decisão

### D1 — `CpuExposurePerfil` como seção opcional do catálogo de CPUs

Adicionar campo opcional `sensitivity_perfil` ao JSON de cada CPU:

```json
{
  "codigo": "ESCO-CARGA-1CAT-DMT2000",
  "sensitivity_perfil": {
    "pct_equip": 0.38,
    "pct_diesel": 0.31,
    "pct_mo": 0.0,
    "pct_material": 0.31,
    "volatilidade_estimada": "ALTA",
    "indice_exposicao": 0.69
  }
}
```

O campo é **opcional e derivável** — quando ausente, skill 09 calcula `indice_exposicao` automaticamente a partir de `composicao_itens` cruzando com as categorias de custo dos insumos. Quando presente, usa o valor registrado (permite override editorial pelo engenheiro).

**Cálculo automático de `indice_exposicao`:**
```
indice_exposicao = pct_equip × 0.7 + pct_diesel × 1.0 + pct_mo × 0.2 + pct_material × 0.4
```

Pesos refletem volatilidade relativa de mercado: diesel é a maior exposição, equipamentos variam com câmbio, MO é parcialmente protegida por acordo sindical.

**Faixas de `volatilidade_estimada`:**
| indice_exposicao | volatilidade |
|---|---|
| ≥ 0.55 | ALTA |
| 0.30 – 0.55 | MEDIA |
| < 0.30 | BAIXA |

### D2 — `CpuExposurePerfil` no modelo canônico

```python
class CpuExposurePerfil(BaseModel):
    cpu_id: str
    pct_equip: float   # fração do custo em equipamentos
    pct_diesel: float  # fração em diesel/combustível
    pct_mo: float      # fração em mão de obra
    pct_material: float
    indice_exposicao: float   # soma ponderada pelas volatilidades relativas
    volatilidade_estimada: Literal["ALTA", "MEDIA", "BAIXA"]
    fonte: Literal["CATALOGO", "CALCULADO"]  # CATALOGO se veio do JSON, CALCULADO se derivado
```

`CanonicalModel` recebe nova seção:
```python
cpu_exposure_perfis: list[CpuExposurePerfil] = Field(default_factory=list)
```

Populada por skill 09 como efeito colateral da análise de sensibilidade.

### D3 — Skill 09 usa `indice_exposicao` como fonte primária de `sensibilidade`

Ordem de precedência para o campo `margin_sensitivity` de cada atividade:

1. `sensitivity_data` fornecido em `inputs` (override explícito do usuário) — **mantido**
2. `cpu_exposure_perfil.indice_exposicao` para o `cpu_id` da atividade — **novo**
3. Heurística `custo_mao_obra_mensal × permanencia_meses / custo_total` — **fallback**

Para obter o `cpu_id` de uma atividade, skill 09 percorre `canonical_in.eap` (que tem `item_id → cpu_id`) e `canonical_in.atividades` (que tem `atividade_id → eap_item_id`).

### D4 — `RelatorioSensibilidade` ganha seção `exposicao_por_cpu`

```python
class ItemExposureCpu(BaseModel):
    cpu_id: str
    descricao_cpu: str
    volatilidade: Literal["ALTA", "MEDIA", "BAIXA"]
    indice_exposicao: float
    atividades_afetadas: list[str]
    participacao_custo: float  # soma de cost_share das atividades afetadas
    recomendacao: str          # ex: "Considerar CPU alternativa com menor pct_diesel"

class RelatorioSensibilidade(BaseModel):
    ...
    exposicao_por_cpu: list[ItemExposureCpu] = []  # novo campo
```

Skill 16 popula esta seção agrupando as atividades por `cpu_id` e ordenando por `indice_exposicao DESC`.

---

## Alternativas Consideradas

| Alternativa | Razão para Rejeição |
|---|---|
| Adicionar `volatilidade_estimada` diretamente ao insumo | Insumo é granular demais — a volatilidade é propriedade da composição, não do item individual |
| Derivar no momento do carregamento do catálogo (`loaders.py`) | Exige acesso cruzado entre CPUs e insumos no loader; preferível manter derivação dentro da skill que consome |
| Adicionar como campo `extra` no JSON sem modelo canônico | Sem rastreabilidade — perderia auditoria entre versões de planejamento |

---

## Consequências

### Positivas
- Skill 09 passa de heurística de custo consolidado para análise baseada na composição real da CPU
- `RelatorioSensibilidade` (skill 16) expõe qual CPU é fonte de risco de overrun, habilitando decisão de substituição
- O campo `fonte: CALCULADO | CATALOGO` permite que o engenheiro de referências sobreponha o cálculo automático para CPUs que ele conhece melhor

### Negativas / Riscos
- Skill 09 agora depende indiretamente do catálogo (via `canonical_in.eap → cpu_id`). O catálogo já é snapshotado em `ArtifactMeta.catalog_snapshot_id` (ADR-024) — sem risco de inconsistência entre versões
- `composicao_itens` usa `categoria_custo` para classificar; se um insumo tem `categoria_custo` não mapeado, cai em `pct_material` — comportamento conservador correto

---

## Definition of Done

- [x] `models/canonical.py` — adicionar `CpuExposurePerfil`, campo `cpu_exposure_perfis` em `CanonicalModel`
- [x] `skills/09-cost-criticality/skill.py` — derivar `CpuExposurePerfil` para cada CPU usada no projeto; usar `indice_exposicao` como fonte de `margin_sensitivity`
- [x] `models/reports.py` — adicionar `ItemExposureCpu`, campo `exposicao_por_cpu` em `RelatorioSensibilidade`
- [x] `skills/16-relatorio-sensibilidade/skill.py` — popular `exposicao_por_cpu` agrupando atividades por CPU
- [x] Testes: `test_cpu_exposure_perfil_calculado`, `test_skill09_usa_cpu_exposure`, `test_skill16_exposicao_por_cpu`

---

## Referências

- **ADR-020:** Criticidade Multi-Dimensional — `CriticidadeProfile`, dimensão `sensibilidade`
- **ADR-026 §D4:** `RelatorioSensibilidade` — seção de levers de margem
- **ADR-024:** Catalog Lifecycle — `catalog_snapshot_id` para rastreabilidade
