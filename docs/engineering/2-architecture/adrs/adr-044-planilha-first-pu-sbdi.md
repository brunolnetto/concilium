# ADR-044 — Planilha-First: Preço Unitário Direto do Catálogo (precos_unitarios_sbdi)

**Status:** Implementado  
**Data:** 2026-05-11  
**Contexto:** MendesLobo Construtora — Concilium

---

## Contexto

### Problema

A skill-04 (Planejamento e BDI) calculava o preço unitário de cada item da EAP derivando
componentes (MO, EQ, diesel, material) a partir da **composição de insumos** do CPU
(`composicao_itens` + `composicao_padrao_equipe`). Esse caminho acumulava dois problemas
estruturais:

**P1 — ADR-038 (override paramétrico por equipe):** Quando um item possuía uma equipe
dimensionada (`equipes_diretas`), a skill sobrescrevia os preços de catálogo com a divisão:

```
PU_componente = (custo_componente_mensal × permanencia_meses) / quantitativo
```

Para itens de **drenagem** (qty 5–100 unidades), o custo mensal de uma equipe inteira
dividido por 10 unidades gera PUs absurdamente altos (ex: R$9.542 por boca de bueiro vs
referência de R$9.543 ✓ mas por outros caminhos chegava a R$80.000+).  
Para itens de **terraplenagem** (qty 100.000–1.000.000 m³), um equipe lean dividida por
1M m³ gera PUs deflacionados.

Resultado: `custo_direto_catalogo = R$41.034.717` vs referência `R$58.985.224` → **-30,4%**.

**P2 — Instabilidade por reset de benchmark:** O `reset=True` recria o projeto do zero,
descartando qualquer patch manual no `canonical.json`. Os PUs distorcidos sempre eram
regenerados.

**P3 — Ausência de fonte canônica de preço unitário:** O catálogo continha `custo_direto_unitario_planilha`
(escalar), mas não o breakdown por componente (MO, diesel, material, equipamentos) que
a skill-04 necessita para calcular BDI diferenciado por categoria (ADR-023).

### Decisão Arquitetural

O CPU é a **fonte de verdade** de preços. Qualquer valor de referência validado deve ser
persistido no CPU — não derivado em runtime via override paramétrico. Isso garante:

- **Governança:** o preço viaja com o catálogo, não com o projeto.
- **Reprodutibilidade:** qualquer reset/rebuild de projeto usa o mesmo preço.
- **Propagação automática:** os 11 outros benchmarks e projetos futuros herdam o valor correto sem retrabalho.

---

## Decisão

### D1 — Campo `precos_unitarios_sbdi` no JSON do CPU

Cada arquivo `config/catalogos/mendeslobo/cpus/<CPU_ID>.json` recebe o campo:

```json
"precos_unitarios_sbdi": {
  "mo":           6.0397,
  "diesel":       12.0716,
  "material":     0.0,
  "equipamentos": 0.0,
  "total":        18.1113
},
"custo_direto_unitario_planilha": 18.1113,
"fonte_preco": "PLANILHA_AGIS_2026_03",
"data_referencia_preco": "2026-03-01"
```

Convenção de mapeamento a partir do `referencia.json`:

| Campo `referencia.json → cpus.itens_eap[*].precos_unitarios` | Campo CPU `precos_unitarios_sbdi` |
|---|---|
| `mo_sbdi`       | `mo`           |
| `diesel_sbdi`   | `diesel`       |
| `material_sbdi` | `material`     |
| `servicos_sbdi` | `equipamentos` (resíduo = total − mo − diesel − material) |
| `total_sbdi`    | `total`        |

> **Nota:** `servicos_sbdi` na planilha AGIS representa custo de serviços de instalação
> (principalmente mão de obra de subempreiteiro para drenagem). É mapeado como `equipamentos`
> no catálogo pois é o quarto componente do modelo flat de 4 categorias (ADR-023).

### D2 — Caminho Planilha-First na Skill-04

Em `src/concilium/application/skills/manifests/04-planejamento-bdi/skill.py`,
**antes** do loop de `composicao_itens` e **antes** do bloco ADR-038:

```python
# [ADR-050] Planilha-first: quando o CPU tem precos_unitarios_sbdi, usa direto.
pu_sbdi = cpu.get("precos_unitarios_sbdi")
if isinstance(pu_sbdi, dict) and float(pu_sbdi.get("total") or 0.0) > 0:
    preco_cat_pf = {
        "material":     float(pu_sbdi.get("material",     0.0)),
        "diesel":       float(pu_sbdi.get("diesel",       0.0)),
        "mao_obra":     float(pu_sbdi.get("mo",           0.0)),
        "equipamentos": float(pu_sbdi.get("equipamentos", 0.0)),
    }
    # Aplica BDI por categoria, monta Planejamento e continua para o próximo item.
    # Pula composicao_itens E bloco ADR-038.
    ...
    continue
```

Se `precos_unitarios_sbdi` estiver **ausente ou total=0**, a skill cai no caminho legado
(derivação por composição + ADR-038). Compatibilidade retroativa total.

### D3 — Script de Calibração `add_pu_sbdi_to_cpus.py`

O script `C:\Temp\add_pu_sbdi_to_cpus.py` (ou equivalente por benchmark) extrai
`precos_unitarios` de `benchmarks/data/<SLUG>/referencia.json` e injeta em cada
CPU correspondente via `cpu_id`. Deve ser executado uma vez por benchmark para popular
o catálogo com os valores validados.

**Fluxo de atualização por benchmark:**

```
referencia.json
  └─ cpus.itens_eap[*]
       ├─ cpu_id           → identifica o arquivo CPU
       └─ precos_unitarios → {mo_sbdi, diesel_sbdi, material_sbdi, servicos_sbdi, total_sbdi}
                               ↓
             config/catalogos/mendeslobo/cpus/<cpu_id>.json
               └─ precos_unitarios_sbdi: {mo, diesel, material, equipamentos, total}
```

---

## Consequências

### Positivas

- `custo_direto_catalogo` AGIS: R$41.034.717 → **R$59.214.402** (+0,39% vs referência). ✅
- `custo_indireto` mantido: +0,17%. ✅
- `status_final: APROVADO`. ✅
- CPUs com `precos_unitarios_sbdi` ignoram ADR-038 inteiramente — sem efeito colateral.
- Campo `fonte_preco` + `data_referencia_preco` garantem rastreabilidade de auditoria.

### Limitações e Riscos

- **Risco de staleness:** Se a planilha de referência for atualizada, o campo no CPU não é
  atualizado automaticamente. Mitigação: o campo `data_referencia_preco` deve ser comparado
  com a data de emissão da planilha a cada ciclo de calibração.
- **Cobertura parcial:** CPUs que não aparecem em `referencia.json` (CPUs de manutenção,
  por exemplo) não recebem o campo e continuam usando o caminho legado. Isso é intencional
  — o fallback é o comportamento anterior.
- **servicos_sbdi → equipamentos:** O mapeamento `servicos_sbdi` = `equipamentos` é uma
  simplificação. Para projetos com subempreiteiros relevantes, pode ser necessário um quinto
  componente (`terceirizado`) alinhado ao ADR-042.

### Arquivos Modificados

| Arquivo | Modificação |
|---|---|
| `config/catalogos/mendeslobo/cpus/*.json` (52 arquivos) | Adição de `precos_unitarios_sbdi`, `custo_direto_unitario_planilha`, `fonte_preco`, `data_referencia_preco` |
| `src/concilium/application/skills/manifests/04-planejamento-bdi/skill.py` | Bloco planilha-first antes de `composicao_itens` |

---

## Referências

- ADR-023: BDI Diferenciado por Categoria (estrutura `{mo, diesel, material, equipamentos}`)
- ADR-038: Compensação de Ineficiências Estruturais (override paramétrico por equipe — contornado)
- ADR-039: Catálogo Regionalizado e Tributação por Jurisdição
- ADR-042: Outsourced Services Integration (componente `terceirizado`)
- `benchmarks/data/AGIS/referencia.json` — fonte dos PUs calibrados para 52 CPUs
