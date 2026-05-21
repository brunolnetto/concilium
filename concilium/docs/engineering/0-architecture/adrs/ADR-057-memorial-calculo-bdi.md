# ADR-057: Memorial de Cálculo BDI — Auditabilidade Ponta a Ponta

**Status:** Implementado  
**Data:** 2026-05-16  
**Autor:** Engenheiro Sênior  
**Relacionado:** ADR-023 (BDI Diferenciado), ADR-039 (The Bridge), ADR-056 (Remediação Débito), ADR-055 (CBS/IBS)

---

## 1. Contexto

O cálculo do preço de venda de uma obra envolve uma cadeia longa de transformações:

```
Salário_base
    × (1 + Encargos)          → Custo_mensal_MO
    × permanência_meses        → Custo_campanha_MO
    × (1 + BDI_MO)            → Preço_venda_MO
                                   = Custo(74,35%) + Overhead(12,27%) + Tributos(13,38%)
```

Com a centralização de constantes (ADR-056) e o breakdown por categoria (ADR-023), cada etapa é now auditável em código. Porém, **nenhum artefato gerado pelo pipeline documenta esta cadeia de forma que um auditor externo, um cliente ou um engenheiro de campo possam verificar**:

- Quais alíquotas de encargos foram aplicadas e de que acordo coletivo derivam
- Qual BDI foi efetivamente usado — DEFAULT, override manual, perfil de projeto ou cenário CBS/IBS
- Quanto de cada R$1,00 cobrado vai para custo, overhead, margem e tributos
- Se os valores são consistentes entre si e com a legislação vigente

Esta rastreabilidade é requisito em:
1. **Licitações públicas** — TC.BR exige memorial de composição de preços com fonte de cada parâmetro
2. **Auditorias de contrato** — cliente pode questionar BDI aplicado e exigir detalhamento
3. **Governança interna** — ADR-005 (replanning) precisa saber qual BDI foi usado no baseline

---

## 2. Decisão

### D1 — `MemorialCalculoBDI` como artefato de domínio imutável

Introduzir `MemorialCalculoBDI` em `domain/models/memorial_bdi.py` — um conjunto de frozen dataclasses que capturam a cadeia completa de cálculo. O memorial é **gerado pelo pipeline** (não pela UI) e é **determinístico**: dado o mesmo canonical, sempre produz o mesmo memorial.

**Estrutura em 4 níveis:**

```
MemorialCalculoBDI
├── encargos_horista:   MemorialEncargos    (Grupos A–F + Judicial, total, vigência)
├── encargos_mensalista: MemorialEncargos
├── bdi_por_categoria: dict[str, MemorialBDICategoria]
│   ├── mao_obra:  MemorialBDICategoria    (OH%, T%, BDI%, fonte, override)
│   ├── material:  ...
│   ├── servicos:  ...
│   ├── indireto:  ...
│   └── diesel:    ...
├── decomposicao_por_categoria: dict[str, MemorialDecomposicao]
│   └── mao_obra:  MemorialDecomposicao    (custo%, overhead%, margem%, tributos%)
├── aplicacao_por_item: list[MemorialItemAplicacao]  (EAP item × BDI efetivo × preço)
└── meta: MemorialMeta                     (projeto_id, version, timestamp, fonte_bdi)
```

### D2 — Geração em Skill 08 (pós-consolidação)

Skill 08 é o ponto correto: tem acesso a `planejamento`, `equipes_diretas`, `resultado` e ao BDI efetivamente aplicado. Gera o memorial após `model_copy` e o persiste em `canonical.memorial_calculo_bdi`.

### D3 — Export como artefato duplo

O memorial é exportado em dois formatos:
1. **JSON** — `memorial_bdi.json` em `outputs/` — machine-readable para integração com ferramentas externas
2. **Excel** — aba `MEMORIAL.BDI` na planilha — human-readable com formatação auditável

A aba Excel **substitui** a aba `BDI` atual (que usa DEFAULT hardcoded) por uma versão que reflete o que foi realmente aplicado.

### D4 — Rastreabilidade de override (fonte do BDI)

`MemorialBDICategoria.fonte_bdi` documenta de onde vieram os valores:

| Valor | Significado |
|-------|------------|
| `DEFAULT_BDI_TABELA` | Nenhum override — valores padrão da empresa |
| `inputs.bdi_aplicado` | Override manual fornecido no run |
| `inputs.tax_scenario` | Cenário CBS/IBS (ADR-055) |
| `inputs.tabela_bdi` | TabelaBdi explícita nos inputs |
| `inputs.bdi_perfil` | PerfilBdiProjeto específico do projeto |

---

## 3. Data Model

### `MemorialEncargos`
```python
MemorialEncargos(
    regime="horista_clt",
    grupo_a=0.3780, grupo_b=0.4784, grupo_c=0.4053,
    grupo_d=0.1907, grupo_e=0.1022, grupo_f=0.1924,
    judicial=0.0300,
    total=1.7770,           # = 177,70%
    vigencia="2026-04-01",  # data de vigência da tabela
    fonte="domain/constants.py → EncargosRegime.DEFAULT_ENCARGOS",
)
```

### `MemorialBDICategoria`
```python
MemorialBDICategoria(
    categoria="mao_obra",
    # Overhead
    ac=0.050, df=0.015, r=0.010, cr=0.000, l=0.090,
    overhead_total=0.165,
    # Tributos
    cofins=0.030, iss=0.050, pis=0.0065, cssl=0.0199, ir=0.0274,
    tributos_total=0.1338,
    # Resultado
    bdi_total=0.3450,       # = 34,50%
    # Rastreabilidade
    fonte_bdi="DEFAULT_BDI_TABELA",
    regime_version="pre_reforma",
    override_aplicado=False,
)
```

### `MemorialDecomposicao`
```python
MemorialDecomposicao(
    categoria="mao_obra",
    custo_direto_pct=0.7435,   # 74,35% do preço vai ao custo direto
    overhead_ac_pct=0.0372,    #  3,72%
    overhead_df_pct=0.0112,    #  1,12%
    overhead_r_pct=0.0074,     #  0,74%
    overhead_cr_pct=0.0000,
    margem_l_pct=0.0669,       #  6,69% — margem líquida sobre preço
    tributo_cofins_pct=0.0300,
    tributo_iss_pct=0.0500,
    tributo_pis_pct=0.0065,
    tributo_cssl_pct=0.0199,
    tributo_ir_pct=0.0274,
    # checksum
    soma=1.0000,               # invariante: deve ser 1,0
)
```

---

## 4. Plano de Implementação

| Fase | Entrega | Arquivo |
|------|---------|---------|
| 1 | `MemorialCalculoBDI` e tipos auxiliares (frozen dataclasses) | `domain/models/memorial_bdi.py` |
| 2 | `MemorialBDIBuilder` — serviço puro que constrói o memorial | `domain/services/memorial_bdi_builder.py` |
| 3 | Skill 08 gera e persiste o memorial no canonical | `08-consolidacao-financeira/skill.py` |
| 4 | `canonical.memorial_calculo_bdi` field | `domain/models/canonical.py` |
| 5 | `render_memorial_bdi()` — aba Excel com 4 seções | `infrastructure/adapters/excel_adapter.py` |
| 6 | JSON artifact `memorial_bdi.json` em Skill 09 | `09-relatorio-e-artefatos/skill.py` |
| 7 | Testes unitários | `tests/unit/test_adr057_memorial_bdi.py` |

## Definition of Done

- [x] `MemorialCalculoBDI` imutável com invariante `soma=1.0` por categoria
- [x] `MemorialBDIBuilder.build()` puro — mesmo canonical → mesmo memorial
- [x] Skill 08 popula `canonical.memorial_calculo_bdi` em cada run
- [x] Excel aba `MEMORIAL.BDI` com seções: Encargos, BDI por categoria, Decomposição, Aplicação
- [x] JSON `memorial_bdi.json` gerado como artifact por Skill 09
- [x] `fonte_bdi` documenta override chain corretamente
- [x] Testes verificam invariante soma=1.0 e rastreabilidade de override
