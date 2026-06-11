# ADR-107 — Generalização do Tipo de Combustível: DIESEL → COMBUSTIVEL com tipo_combustivel

**Status:** Implementado ✅ _(D1–D4, D6 concluídos 2026-06-10; D5 analytics aguarda ADR-106)_  
**Data:** 2026-06-09  
**Contexto:** MendesLobo Construtora — Concilium  
**Depende de:** ADR-030, ADR-082, ADR-085, ADR-090, ADR-092  
**Relacionado:** NEP-029 (calibração C_ref), ADR-058 (espaço analítico)

---

## 1. Contexto

### 1.1 Situação Atual

O sistema modela combustível exclusivamente como **DIESEL**, tratado como categoria de primeira classe em toda a pipeline:

```python
# catalogo.py
CategoriaCusto = Literal["MATERIAL", "DIESEL", "MAO_OBRA", "EQUIPAMENTO"]

# bdi.py
CategoriaBdi = Literal["MAO_OBRA", "MATERIAL", "SERVICOS", "INDIRETO", "DIESEL"]

# canonical.py — campo de custo unitário
class PrecoUnitarioCategoria(BaseModel):
    diesel: float = 0.0

# skill-05 — resolução de preço
def _resolve_preco_diesel(inputs, catalogo, ctx) -> float:
    for i in catalogo["insumos"]:
        if i["codigo"] == "DIESEL-S10":  # hardcoded
            ...
```

Referências hardcoded adicionais identificadas:

| Arquivo | Ocorrência | Impacto |
|---|---|---|
| `catalogo.py:14` | `CategoriaCusto.DIESEL` | Composição de CPUs |
| `canonical.py:475,485,494` | Campo `diesel` | Preço unitário por categoria |
| `bdi.py:29,74,82,106,138,171` | `CategoriaBdi.DIESEL` + `BDIOverride.diesel` | Fator BDI e simulação fiscal |
| `skill-05/_skill_helpers_a.py` | `_resolve_preco_diesel()`, `"DIESEL-S10"` | Resolução de preço único |
| `skill-04/skill.py` | `("MA-DIESEL-S10", "MA-DIESEL", "MA-DIESEL-ESCALA")` | Lookup de preço no catálogo |
| `skill-06/skill.py` | `"MA-DIESEL-S10"`, `"DIESEL"` em `_CATEGORIA_MAP` | Categorização de insumos |
| `projection.py:105,118` | Campo `"diesel_total"` | Breakdown analítico |
| `curva_abc_builder.py:42,44` | Chaves sintéticas `{eid}__DIESEL` | Cubo ABC |

### 1.2 Semente Arquitetural Existente

`ComponenteCombustivel` em `producao.py` já é **fuel-agnostic** — agrega `custo_horario_total` sem nomear o tipo de combustível:

```python
class ComponenteCombustivel(BaseModel):
    """Componente C da CPU: custo horário de combustível."""
    equipamentos: list[dict] = Field(default_factory=list)
    custo_horario_total: float = Field(ge=0)
```

Esta é a evidência de que o domínio de modelagem (CPU → produtividade) já abstraiu o tipo. O problema está nas camadas acima: skill inputs, canonical fields, BDI, e analytics.

### 1.3 Motivação Real

Projetos de construção civil utilizam múltiplos vetores energéticos com custos, tributação e consumos distintos:

| Combustível | Código insumo | Unidade de consumo | BDI relevante |
|---|---|---|---|
| Diesel S-10 | `DIESEL-S10` | L/h | DIESEL (TCO elevado) |
| Diesel S-500 | `DIESEL-S500` | L/h | MATERIAL ("DIESEL" delega para MATERIAL — ADR-090) |
| Gasolina C | `GASOLINA-C` | L/h | MATERIAL |
| GNV/CNG | `CNG` | kg/h ou m³/h | MATERIAL |
| HVO (biodiesel) | `HVO` | L/h | MATERIAL ou DIESEL |
| Elétrico | `ELETRICO` | kWh/h | MATERIAL |
| Hidrogênio | `H2` | kg/h | — (futuro) |

Com apenas `preco_diesel: float` como input, o sistema não consegue modelar:
- CPUs com equipamentos mistos (ex.: compactadora diesel + placa vibratória elétrica)
- Análise de sensibilidade por tipo de combustível
- Substituição progressiva de frota (diesel → HVO → elétrico)
- Diferenciação fiscal correta (PIS/COFINS diferem entre diesel S-10 e HVO)

---

## 2. Problema

### P1 — Categoria DIESEL hardcoded impede modelagem de frotas mistas

`CategoriaCusto = Literal["MATERIAL", "DIESEL", ...]` força todos os combustíveis ao mesmo bucket BDI. Uma CPU com escavadeira diesel + bomba hidráulica elétrica tem contribuições de custo que pertencem a BDI categories diferentes — mas o sistema coloca tudo em `DIESEL`.

### P2 — `consumo_litros_hora` é fisicamente incorreto para combustíveis não-líquidos

`AtributosInsumo.consumo_litros_hora: float | None` e `EquipamentoEquipe.consumo_litros_hora_estimado` assumem a unidade L/h. Veículos elétricos consomem kWh/h; CNG é kg/h ou m³/h. O campo atual produziria conversões dimensionalmente incoerentes.

### P3 — `preco_diesel` como scalar impede calibração por tipo

NEP-029 introduziu `custo_hora_total_referencia` (C_ref) para calibrar por projeto. Mas a resolução de preço ainda parte de `preco_diesel: float` — um escalar global. Com múltiplos combustíveis, seriam necessários múltiplos preços, e a calibração via C_ref precisaria ser feita por tipo.

### P4 — Cubo analítico não tem dimensão de tipo de combustível

`diesel_total` nos breakdowns e `{eid}__DIESEL` nas chaves do cubo ABC impedem consultas como:
- "Qual o custo por tipo de combustível neste projeto?"
- "Como mudaria a margem se substituíssemos 30% da frota por elétrico?"
- "Qual o impacto de um aumento de 15% no diesel S-10 vs. congelamento do GNV?"

### P5 — BDI fiscal diferencia diesel mas não outros combustíveis

A equação de BDI de equipamentos:
```
BDI_equip = 0.70 × BDI_mao_obra + 0.30 × BDI_diesel
```
pressupõe que todo combustível segue a tributação do diesel. HVO e GNV têm regimes fiscais distintos (ICMS-ST diferente, crédito de PIS/COFINS diferente).

---

## 3. Decisão

### D1 — Renomear `DIESEL` → `COMBUSTIVEL` em CategoriaCusto e CategoriaBdi

A categoria passa a ser genérica. O tipo específico de combustível é um **atributo** da instância, não uma categoria distinta.

```python
# ANTES
CategoriaCusto = Literal["MATERIAL", "DIESEL", "MAO_OBRA", "EQUIPAMENTO"]

# DEPOIS
CategoriaCusto = Literal["MATERIAL", "COMBUSTIVEL", "MAO_OBRA", "EQUIPAMENTO"]
```

**Backward compat:** Dados legados com `"DIESEL"` são lidos como `"COMBUSTIVEL"` via alias em Pydantic. Nenhuma migração de dados é necessária para leitura; geração de novos dados usa `"COMBUSTIVEL"`.

### D2 — Adicionar `tipo_combustivel` como campo opcional em ComposicaoItem e AtributosInsumo

```python
TipoCombustivel = Literal[
    "DIESEL_S10",
    "DIESEL_S500",
    "GASOLINA_C",
    "CNG",
    "HVO",
    "ELETRICO",
    "OUTRO",
]

class ComposicaoItem(BaseModel):
    insumo_id: str
    coeficiente: float
    categoria_custo: CategoriaCusto
    tipo_combustivel: TipoCombustivel | None = None
    # None = legado (assume DIESEL_S10 quando categoria=COMBUSTIVEL)

class AtributosInsumo(BaseModel):
    consumo_por_hora: float | None = None       # unidade definida por consumo_unidade
    consumo_unidade: Literal["L/h", "kg/h", "kWh/h", "m3/h"] = "L/h"
    tipo_combustivel: TipoCombustivel | None = None
    # backward compat: consumo_litros_hora ainda aceito via alias
```

### D3 — Substituir `preco_diesel: float` por `precos_combustivel: dict[TipoCombustivel, float]`

Nos inputs de skill-05 e em toda a cadeia de resolução de preço:

```python
# skill-05 inputs (antes)
inputs = {"preco_diesel": 6.20}

# skill-05 inputs (depois)
inputs = {
    "precos_combustivel": {
        "DIESEL_S10": 6.20,
        "CNG": 3.80,
        "ELETRICO": 0.75,    # R$/kWh
    }
}

# backward compat: se "preco_diesel" presente e "precos_combustivel" ausente,
# injeta {"DIESEL_S10": preco_diesel}
```

A resolução de preço:

```python
def _resolve_precos_combustivel(inputs, catalogo, ctx) -> dict[TipoCombustivel, float]:
    """Retorna {tipo_combustivel: preco_unitario} para todos os tipos usados."""
    # 1. Override explícito via inputs
    # 2. Lookup no catálogo por código (DIESEL-S10, CNG, ELETRICO, ...)
    # 3. Fallback: DIESEL_S10 → 6.20 (compatibilidade legada)
```

### D4 — Manter BDI unificado `COMBUSTIVEL` com breakdown opcional por tipo

Em vez de criar `CategoriaBdi.DIESEL`, `CategoriaBdi.CNG`, etc., a categoria BDI permanece única (`COMBUSTIVEL`). A taxa BDI para combustível é configurada **uma vez** por projeto, e o breakdown analítico expõe os tipos internamente.

Exceção futura: se tratamentos fiscais distintos entre tipos criarem taxas BDI materialmente diferentes (>2pp), um `combustivel_bdi_overrides: dict[TipoCombustivel, float]` pode ser adicionado ao `BDIOverride` sem quebrar a estrutura atual.

```python
class BDIOverride(BaseModel):
    material: float | None = None
    combustivel: float | None = None          # era "diesel"
    combustivel_por_tipo: dict[str, float] | None = None  # override fino
    mao_obra: float | None = None
    equipamentos: float | None = None
```

### D5 — Adicionar `tipo_combustivel` como dimensão no cubo analítico e breakdown

```python
# projection.py — _accumulate_equipes
totals = {
    "mao_obra": 0.0,
    "equipamentos": 0.0,
    "combustivel": 0.0,                        # total (era "diesel")
    "combustivel_por_tipo": {},                # {"DIESEL_S10": X, "CNG": Y}
    "materiais": 0.0,
    "total": 0.0,
}

# curva_abc_builder.py — chave sintética
combustivel_key = f"{eid}__{tipo_combustivel}"   # era f"{eid}__DIESEL"
custo_acum[combustivel_key]["categoria"] = "COMBUSTIVEL"
custo_acum[combustivel_key]["tipo_combustivel"] = tipo_combustivel
```

### D6 — Inferência automática de tipo_combustivel a partir do código do insumo (legado)

Para catálogos existentes que usam `"DIESEL-S10"` como `insumo_id` sem `tipo_combustivel` explícito:

```python
_INSUMO_TO_TIPO: dict[str, TipoCombustivel] = {
    "DIESEL-S10": "DIESEL_S10",
    "DIESEL-S500": "DIESEL_S500",
    "MA-DIESEL-S10": "DIESEL_S10",
    "MA-DIESEL": "DIESEL_S10",
    "GASOLINA-C": "GASOLINA_C",
    "CNG": "CNG",
    "GNV": "CNG",
    "ELETRICO": "ELETRICO",
    "HVO": "HVO",
}

def _infer_tipo_combustivel(insumo_id: str) -> TipoCombustivel:
    """Infere tipo_combustivel a partir do código do insumo — fallback para DIESEL_S10."""
    for key, tipo in _INSUMO_TO_TIPO.items():
        if key.upper() in insumo_id.upper():
            return tipo
    return "DIESEL_S10"  # backward compat
```

---

## 4. Modelo Operacional

### 4.1 Fluxo de custo com múltiplos combustíveis

```
Catálogo (insumo)
  └─ consumo_por_hora + consumo_unidade + tipo_combustivel
          │
          ▼
Skill-05: _resolve_precos_combustivel()
  precos = {"DIESEL_S10": 6.20, "ELETRICO": 0.75}
          │
          ▼
_calcular_custo_equipamento()
  custo_por_tipo = {tipo: consumo × preco × horas para cada tipo}
  custo_comb_total = sum(custo_por_tipo.values())
          │
          ▼
EquipeDireta
  custo_combustivel_total_mensal: float       (agregado, backward compat)
  custo_combustivel_por_tipo: dict[str,float] (novo)
          │
          ▼
Skill-06: PrecoUnitarioCategoria
  combustivel: float                          (total, era "diesel")
  combustivel_breakdown: dict[str,float]      (novo, opcional)
          │
          ▼
Cubo analítico
  dimension: tipo_combustivel
  metric: custo_combustivel
```

### 4.2 CPU com frota mista — exemplo

CPU `ESC-200-HIBRIDA` (escavadeira híbrida diesel+elétrico):

```json
{
  "codigo": "ESC-200-HIBRIDA",
  "composicao_itens": [
    {
      "insumo_id": "DIESEL-S10",
      "coeficiente": 18.5,
      "categoria_custo": "COMBUSTIVEL",
      "tipo_combustivel": "DIESEL_S10"
    },
    {
      "insumo_id": "ENERGIA-ELETRICA",
      "coeficiente": 12.0,
      "categoria_custo": "COMBUSTIVEL",
      "tipo_combustivel": "ELETRICO"
    }
  ]
}
```

O skill-05 resolveria os dois preços separadamente e acumularia em `custo_combustivel_por_tipo`.

---

## 5. Alternativas Rejeitadas

| ID | Alternativa | Motivo da Rejeição |
|---|---|---|
| A1 | Manter DIESEL e adicionar categorias `GASOLINA`, `CNG`, etc. separadas | Proliferação de categorias no enum; BDI precisaria de N categorias novas; complexidade exponencial |
| A2 | Tratar todos combustíveis como `MATERIAL` (sem categoria especial) | Diesel tem BDI diferente de material em ~80% dos projetos; perderia granularidade tributária real |
| A3 | Usar `insumo_id` como proxy para tipo (sem campo `tipo_combustivel`) | Frágil: depende de padrão de nomeação no catálogo; falha silenciosamente para insumos com nomes não padronizados |
| A4 | Migração big-bang (substituir todos os dados legados) | Alto risco; benchmarks existentes têm `DIESEL` hardcoded; backward compat via alias é superior |

---

## 6. Consequências

### Positivas

1. **Modela frotas mistas** com diesel, elétrico, GNV e HVO no mesmo projeto.
2. **Análise de sensibilidade por tipo** — "e se o diesel subir 20%?" vs. "e se migrarmos 30% da frota para GNV?".
3. **Sem migração de dados** — backward compat por alias; projetos legados continuam funcionando.
4. **Cubo analítico ganha dimensão** `tipo_combustivel` para drill-down em relatórios executivos.
5. **Suporte futuro a hidrogênio** sem nova breaking change — apenas adicionar `"H2"` ao enum.

### Negativas / Riscos

1. **Skill-05 mais complexo** — `_calcular_custo_equipamento` precisa iterar por tipo em vez de escalar.
2. **Propagação de tipo até canonical** — `EquipeDireta`, `EquipamentoEquipeDireta` ganham campos novos, aumentando tamanho do canônico.
3. **Risco de inconsistência** — se `tipo_combustivel=None` e `categoria_custo="COMBUSTIVEL"`, a inferência por `insumo_id` pode falhar para insumos não padronizados.
4. **Testes de benchmark** — projetos com `preco_diesel` no input precisam passar `precos_combustivel` ao longo do tempo.

### Mitigações

1. **D6 (inferência automática)** cobre 100% dos catálogos existentes sem migração.
2. **Alias Pydantic** para `"DIESEL"` → `"COMBUSTIVEL"` é transparente para leitores.
3. Validação `VAL-EQUIP-COMB-FUEL-TYPE` emite aviso quando tipo não é inferível, sem bloquear pipeline.
4. `preco_diesel` permanece aceito como input, convertido automaticamente para `precos_combustivel={"DIESEL_S10": preco_diesel}`.

---

## 7. Plano de Implementação

| Fase | Entregas | Arquivos Principais | Impacto |
|---|---|---|---|
| **F1** — Domínio | `TipoCombustivel` enum; alias `DIESEL→COMBUSTIVEL`; campos `tipo_combustivel`, `consumo_por_hora`, `consumo_unidade` | `catalogo.py`, `canonical.py`, `bdi.py` | Aditivo; sem breaking change |
| **F2** — Skill-05 | `_resolve_precos_combustivel()`; `_calcular_custo_equipamento` multi-tipo; `custo_combustivel_por_tipo` em EquipeDireta | `_skill_helpers_a.py` (skill-05) | Breaking para testes unitários de combustível |
| **F3** — Skill-06 | Renomear `"diesel"` → `"combustivel"` em `_CATEGORIA_MAP`; `combustivel_breakdown` em `PrecoUnitarioCategoria` | `_skill_helpers_a.py` (skill-06) | Breaking para campos de output |
| **F4** — Analytics | Renomear `diesel_total` → `combustivel_total`; adicionar `combustivel_por_tipo`; atualizar chaves ABC | `projection.py`, `curva_abc_builder.py`, `report_builder.py` | Breaking para consumidores de relatórios |
| **F5** — Overrides/BDI | Renomear `BDIOverride.diesel` → `combustivel`; adicionar `combustivel_por_tipo` | `bdi.py`, `overrides.py` | Breaking para overrides existentes |
| **F6** — Migração | Alias e conversores para projetos legados; script de validação de catálogos | Todos os benchmarks | Zero impacto (alias + inferência) |

---

## 8. Definition of Done

### Fase 1
- [ ] `TipoCombustivel` definido em `catalogo.py`
- [ ] `CategoriaCusto` aceita `"DIESEL"` como alias de `"COMBUSTIVEL"` (Pydantic validator)
- [ ] `ComposicaoItem.tipo_combustivel: TipoCombustivel | None` adicionado
- [ ] `AtributosInsumo.consumo_por_hora` + `consumo_unidade` + `tipo_combustivel` adicionados
- [ ] `consumo_litros_hora` mantido como alias de `consumo_por_hora` para backward compat

### Fase 2
- [ ] `_resolve_precos_combustivel()` retorna `dict[str, float]`
- [ ] `preco_diesel` em inputs ainda aceito (convertido automaticamente)
- [ ] `_calcular_custo_equipamento` itera por tipo de combustível
- [ ] `EquipeDireta.custo_combustivel_por_tipo: dict[str, float]` adicionado
- [ ] Validação `VAL-EQUIP-COMB-FUEL-TYPE` emite AVISO para tipos não reconhecidos
- [ ] Testes unitários de combustível atualizados

### Fase 3
- [ ] `_CATEGORIA_MAP["diesel"] = "combustivel"` (backward compat)
- [ ] `PrecoUnitarioCategoria.combustivel` (campo renomeado) + `combustivel_breakdown`
- [ ] `"DIESEL"` ainda processado como `"COMBUSTIVEL"` em `_process_eap_item`

### Fase 4
- [ ] `projection.py`: `"combustivel_total"` no breakdown + `"combustivel_por_tipo"`
- [ ] `curva_abc_builder.py`: chaves `{eid}__{tipo_combustivel}` + `categoria="COMBUSTIVEL"` + `tipo_combustivel` como campo
- [ ] Benchmark reports atualizados

### Fase 5
- [ ] `BDIOverride.combustivel` (era `diesel`) com alias backward compat
- [ ] `combustivel_por_tipo: dict[str, float] | None` em BDIOverride
- [ ] Equação de BDI de equipamentos atualizada: `BDI_equip = 0.70×BDI_mo + 0.30×BDI_combustivel`

### Fase 6
- [ ] `_infer_tipo_combustivel()` presente e testada
- [ ] Todos os 11 benchmarks processam sem erro após F1-F5
- [ ] Regressão: `pytest tests/ -k combustivel` — pass

---

## 9. Questões em Aberto

| ID | Questão | Decisão Sugerida |
|---|---|---|
| Q1 | Veículos elétricos: `custo_combustivel` ou novo campo `custo_energia`? | Manter como COMBUSTIVEL/ELETRICO — semântica de "custo de propulsão por hora" é uniforme |
| Q2 | BDI de equipamentos: o HVO tem o mesmo regime fiscal que o diesel S-10? | Sim para 2026; adicionar `combustivel_por_tipo` em BDIOverride para ajuste fino por projeto quando necessário |
| Q3 | O cubo analítico deve expor `tipo_combustivel` como dimensão ou atributo? | Dimensão — permite filtros e aggregations sem ETL adicional |
| Q4 | Deve existir um `TipoCombustivel.OUTRO` genérico? | Sim — para combustíveis regionais ou não catalogados, com AVISO de calibração |
| Q5 | `consumo_por_hora` com `consumo_unidade` é suficiente ou precisamos de fator de conversão para energia (MJ)? | Suficiente para v1; fator de conversão energética é feature de análise de carbono (ADR futuro) |
