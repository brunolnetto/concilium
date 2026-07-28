# NEP-029: Divergência estrutural na precificação unitária — dois caminhos incompatíveis e ausência de fonte canônica

**Status:** ✅ Resolvido — atalho por referência removido (2026-07-28)
**Prioridade:** ~~🔴 Crítico~~ — fechado
**Área:** Arquitetura e Skills  
**Tipo:** Bug + Governança + Dados  
**Esforço:** XL  
**Identificado em:** 2026-05-24

> **Resolução final (2026-07-28 — worktree ADR-162):** o atalho por
> `custo_hora_total_referencia` (S1, nota abaixo) foi **removido por completo**,
> nas 3 camadas onde existia: `_calibrar_custos_por_cref` (skill-05, dimensionamento
> standalone), `_custo_hora_equipe(..., custo_hora_referencia=...)` (skill-04,
> P_canonico) e `_resolve_custo_hora_ref_sem` (skill-05, contrato de pool).
> Motivo: verificado numericamente que o bottom-up puro, uma vez corrigido para
> respeitar a precedência do ADR-132 (`preco_h_unitario` embutido na composição
> sobre o catálogo geral de insumos — gap que fazia o bottom-up cru divergir até
> 35% do C_ref), já reproduz o custo de referência calibrado contra obra real
> (`PROD-REJEITO-COMP-EQ1-4`, Serra Verde) com delta < 0,003% — o atalho era
> redundante, não autoritativo. `custo_hora_total_referencia` deixa de ser lido
> por qualquer caminho de cálculo; o campo permanece nos JSONs de produção como
> histórico, sem consumidor. Fix aplicado em `_custos.py` (`_custo_hora_equipamentos`),
> `_dimensionamento_orquestracao.py` e `_pool_contrato_demanda.py`. Suíte completa
> sem regressão (14.441 testes, golden AGIS incluso). Decisão do usuário: "gostaria
> que a dedução fosse sempre bottom-up, e remover por todas este valor referencial."
> Achado lateral: o catálogo geral de insumos (`insumos/equipamento/E00XX.json`) já
> diverge hoje do preço embutido nas composições calibradas (até 54% em alguns
> casos) — inofensivo enquanto ADR-132 for respeitado, mas é débito de dado a
> reconciliar separadamente.

> **Nota de implementação (2026-06-09 — Sprint S1 parcial, superada pela resolução acima):**
> - ~~`_calibrar_custos_por_cref` em skill-05 `_build_dimensionamento`: usa
>   `custo_hora_total_referencia × h_sem × SEMANAS_POR_MES` como base, com frações
>   de `precos_unitarios_sbdi.{mo,eq,diesel}` — garante consistência com pool.~~
> - ✅ `gap_pool_overhead` no ponto de equilíbrio usa idle real das instâncias
>   (não mais diferença pool vs autônomo, que era falso positivo de n_frentes).
> - ✅ AGIS: autônomo e pool convergem; painel_equilibrio mostra apenas
>   praticabilidade (0.81M) — sem artefato de "overhead de pool".
> - ~~⚠️ CTC/LUNDIN/ROSH/PRIVATE_LOG: BLOQUEADOS porque `custo_hora_total_referencia`
>   foi calibrado da planilha AGIS; outros benchmarks precisam de C_ref próprio.~~
>   Não se aplica mais — nenhum benchmark depende de C_ref próprio agora.

---

## Contexto

O skill-06 (precificação unitária) pode calcular o preço unitário de dois modos distintos,
selecionados por `benchmark_mode`:

- **Modo A (`benchmark_mode=True`):** lê `cpu.precos_unitarios_sbdi` — valores pré-computados
  derivados da planilha AGIS/referência e armazenados diretamente no JSON da CPU.
- **Modo B (`benchmark_mode=False`, padrão):** recomputa o preço a partir de
  `cpu.composicao_itens × insumo.preco_unitario` via `_compute_preco_cat_from_cpu`.

Esses dois caminhos **não produzem os mesmos resultados** e não compartilham nenhuma fonte de
verdade comum. O catálogo mantém os dois em paralelo sem garantia de sincronismo.

---

## Problema Observado

### P1 — composicao_itens incompleta em CPUs de escavação 1aCat

A CPU `CPU-TERRA-ESCO-CARGA-1CAT-DMT2000` tem apenas um insumo de diesel na composição:

```json
"composicao_itens": [
  { "insumo_id": "MA-DIESEL-S10", "coeficiente": 0.1220, "categoria_custo": "DIESEL" }
]
```

Calculo: `0.1220 × R$ 5,397/L = R$ 0,66/m³`  
Referência (`precos_unitarios_sbdi.total`): `R$ 7,66/m³` → **gap de 11,6×**

Mão de obra e equipamentos estão ausentes da composição. No modo B, o skill-06 produz
um preço unitário gravemente subprecificado para este tipo de CPU.

### P2 — ADR-038 foi introduzido como patch do gap acima

Para compensar CPUs com composicao_itens incompleta, a `_apply_adr038_compensation`
sobrescreve o `preco_cat` com `custo_equipe / q` (custo total da equipe dividido pela
quantidade). Isso criou um efeito colateral algébrico:

```
preco_unitario_adr038 = custo_equipe_total / q
subtotal              = (custo_equipe_total / q) × q = custo_equipe_total
```

**A quantidade se cancela algebricamente.** Dois itens com a mesma CPU e mesma equipe,
mas quantidades diferentes (ex.: 107 k m³ e 337 k m³), recebem **subtotais idênticos**,
independentemente do volume. Isso viola o contrato fundamental de precificação
`subtotal_i = PU_i × Q_i`.

### P3 — ADR-038 pode estar ativo via override persistido

O default de `apply_adr038_compensation` foi alterado para `False` (NEP corretiva),
mas overrides salvos por projeto com `apply_adr038_compensation: true` continuam
ativando o comportamento. A prova: eap-1_1 (107 k m³) e eap-1_2 (337 k m³) apresentam
subtotais idênticos mesmo após a mudança de default.

### P4 — custo_material_mensal nunca é populado no skill-05

O skill-05 constrói `EquipeDireta` sem material:

```python
EquipeDireta(
    custo_mao_obra_mensal=...,
    custo_equipamentos_mensal=...,
    custo_combustivel_total_mensal=...,
    # custo_material_mensal → default 0.0, nunca preenchido
)
```

No skill-08, N4 (custo operacional do Bridge) é calculado como:

```python
custo_direto_equipe = sum(e.custo_total for e in canonical_in.equipes_diretas)
# custo_total inclui MO + EQ + combustível, mas não material
```

Efeito: `N1 (catálogo, inclui material) > N4 (equipes, sem material)` de forma sistemática.
O delta de −11,8% no Bridge AGIS é **causado inteiramente pela ausência de material em N4**,
não por ineficiência real de operação. O Bridge exibe AMARELO como falso positivo.

### P5 — MA-AGIS-CPU-TERRA-COMPAC-FINAL-ROCHA com gap de +19,6%

O insumo `MA-AGIS-CPU-TERRA-COMPAC-FINAL-ROCHA` tem `preco_unitario = R$ 17,263/m³`
enquanto `precos_unitarios_sbdi.total = R$ 14,437/m³`. Diferença de +R$ 2,83/m³ ×
24.721 m³ = ~R$ 69 k de sobreprecificação para este item.

### P6 — decomposição BDI incoerente nos MA-AGIS

CPUs que usam MA-AGIS como material agregado declaram `precos_unitarios_sbdi.material = 0.0`,
mas o modo B classifica todo o custo como `MATERIAL`. Isso altera a alíquota de BDI aplicada:
mão de obra e diesel têm BDIs distintos (ADR-023); classificar tudo como material distorce
o cálculo de markup.

---

## Evidência Quantitativa

Benchmark AGIS com `benchmark_mode=True`:

| Indicador | Referência | Calculado | Delta |
|-----------|-----------|-----------|-------|
| Custo direto | R$ 46.867.333 | R$ 46.771.430 | **−0,20%** |
| Custo indireto | R$ 19.584.539 | R$ 19.504.530 | −0,41% |
| Custo total | R$ 66.451.873 | R$ 66.275.960 | −0,26% |
| Preço de venda | R$ 76.961.262 | R$ 76.753.981 | −0,27% |

O modo A (sbdi) converge para a referência com δ < 0,5% em todos os indicadores.
O modo B (composicao_itens) com ADR-038 ativo produziu custos diretos de R$ 160 M no
projeto de produção AGIS (Transnordestina), aproximadamente **3,4× a escala do benchmark**
de teste, com pares de itens mostrando subtotais idênticos independentemente da quantidade.

---

## Causa Raiz

Ausência de uma fonte canônica única para o preço unitário de cada CPU. O catálogo
mantém dois registros paralelos (`precos_unitarios_sbdi` e `composicao_itens`) que
representam a mesma grandeza por caminhos diferentes, sem mecanismo de sincronismo ou
validação cruzada. O ADR-038 foi adicionado como patch operacional sem resolver a raiz,
e introduziu uma regressão algébrica que anula o efeito da quantidade.

---

## Objetivo

Estabelecer **um único caminho canônico** de derivação do preço unitário por CPU,
derivado de parâmetros operacionais rastreáveis (produção horária, composição de equipe,
preços de insumos) e validado contra a planilha de referência.

---

## Decisão

### D1 — Adotar `precos_unitarios_sbdi` como fonte primária de curto prazo

Tornar o skill-06 usar `precos_unitarios_sbdi` como padrão para todas as CPUs que
o possuem, independentemente de `benchmark_mode`. O modo `composicao_itens` passa a
ser fallback explícito para CPUs sem `precos_unitarios_sbdi` definido.

Critério de ativação do fallback: campo ausente ou `total == 0`.

### D2 — Derivar `precos_unitarios_sbdi` de parâmetros operacionais (longo prazo)

Criar rotina de geração de `precos_unitarios_sbdi` a partir de:

```
PU_mo        = Σ (num_pessoas × salario_hora) / producao_horaria
PU_equip     = Σ (custo_hora_equip) / producao_horaria  
PU_diesel    = consumo_hora × preco_diesel / producao_horaria
PU_material  = Σ (consumo_hora_material × preco_material) / producao_horaria
```

Isso elimina a dependência de valores manuais no JSON da CPU e garante que `sbdi`
seja automaticamente derivado quando `composicao_padrao_equipe` e
`producao_horaria` estiverem presentes.

### D3 — Remover ADR-038 como comportamento habilitável por override

A compensação ADR-038 produz resultados matematicamente incorretos (cancelamento de
quantidade) quando `custo_material_mensal` não escala com o volume de cada item.
Deve ser removida ou substituída por escala explícita via fator de produtividade.

Até a remoção definitiva: bloquear a possibilidade de ativação por override salvo.

### D4 — Popular `custo_material_mensal` no skill-05

O skill-05 deve calcular o custo de material por equipe a partir das `MaterialEquipe`
(`consumo_por_hora × preco_insumo / producao_horaria × horas_mes × num_equipes`).
Isso corrige N4 no Bridge e elimina o falso AMARELO sistêmico.

### D5 — Corrigir dados de catálogo

1. Completar `composicao_itens` de `CPU-TERRA-ESCO-CARGA-1CAT-DMT2000` com insumos
   de mão de obra e equipamento (hoje só tem diesel).
2. Corrigir `MA-AGIS-CPU-TERRA-COMPAC-FINAL-ROCHA` de R$ 17,26 para ≤ R$ 14,44/m³
   (alinhado com `precos_unitarios_sbdi`).
3. Alinhar decomposição BDI das CPUs MA-AGIS: `precos_unitarios_sbdi` deve refletir
   a categoria real do custo (MO + diesel, não material=0).
4. Popular `consumo_litros_hora` para `EQ-E0016` (atualmente ausente → custo de
   combustível zero nas equipes).

---

## Escopo

### Incluído

1. Mudança de lógica de precificação no skill-06 (D1).
2. Bloqueio de ADR-038 via override (D3).
3. Cálculo de `custo_material_mensal` no skill-05 (D4).
4. Correção de dados de catálogo afetados (D5).
5. Testes de regressão: benchmark AGIS deve manter δ ≤ 0,5% em modo normal e benchmark.

### Excluído

1. Reescrita completa da fórmula de custo de equipe no skill-05.
2. Mudança de formato de planilha de referência.
3. Alteração de critérios de status do Bridge (VERDE/AMARELO/VERMELHO).

---

## Plano de Implementação

### Fase 1 — Patch de curto prazo (D1 + D3)

1. Alterar skill-06 para usar `precos_unitarios_sbdi` como fonte primária quando disponível.
2. Remover ou bloquear ativação de ADR-038 via override persistido.
3. Regressão: benchmark AGIS com δ ≤ 0,5%.

### Fase 2 — Correção operacional (D4 + D5 parcial)

1. Popular `custo_material_mensal` no skill-05 via MaterialEquipe.
2. Corrigir `MA-AGIS-CPU-TERRA-COMPAC-FINAL-ROCHA` no catálogo.
3. Popular `consumo_litros_hora` para `EQ-E0016`.
4. Validar Bridge: δreal esperado < 2% para projeto AGIS de produção.

### Fase 3 — Derivação canônica (D2)

1. Criar rotina `derivar_precos_unitarios_sbdi(cpu, equipe, producao, insumos)`.
2. Integrar como passo do pipeline de manutenção de catálogo.
3. Validar que saída da rotina converge para valores atuais de `precos_unitarios_sbdi`
   dentro de ±1%.
4. Completar `composicao_itens` das CPUs de escavação (D5 completo).

---

## Critério de Aceite

1. Projeto AGIS (produção) com `benchmark_mode=False` produz custo direto dentro de
   ±2% do custo direto em `benchmark_mode=True`.
2. Pares de itens com a mesma CPU e quantidades diferentes apresentam subtotais
   **proporcionais à quantidade** (δ entre PU_1 e PU_2 < 0,1%).
3. Bridge AGIS exibe status VERDE (δreal < 10%) após popular `custo_material_mensal`.
4. Benchmark AGIS mantém status `APROVADO` com δ ≤ 0,5% em custo direto, indireto e venda.
5. ADR-038 não pode ser ativado por override de skill; tentativa gera `VAL-PLAN-ADR038-BLOCKED`.

---

## Riscos

1. CPUs sem `precos_unitarios_sbdi` ficam sem precificação após D1 (fallback para
   `composicao_itens` deve estar robusto).
2. Derivação canônica (D2) pode divergir de `precos_unitarios_sbdi` se parâmetros de
   equipe/produção não estiverem calibrados.
3. Correção de `MA-AGIS-COMPAC-FINAL-ROCHA` reduz custo do item em ~R$ 69 k —
   impacto controlado mas precisa de aceite do responsável pelo catálogo.

## Mitigações

1. Gate de fallback explícito no skill-06: logar `VAL-PLAN-SBDI-MISSING` para CPUs
   que usam fallback para `composicao_itens`.
2. Comparar saída de rotina de derivação D2 contra `precos_unitarios_sbdi` atual antes
   de substituir — rodar em modo dry-run primeiro.
3. Registrar alteração de catálogo com `motivo` e referência ao laudo desta NEP.

---

## Evidências Técnicas

1. `src/concilium/application/skills/manifests/06-precificacao-unitaria/skill.py`
2. `src/concilium/application/skills/manifests/06-precificacao-unitaria/_skill_helpers_a.py`
3. `src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers_a.py`
4. `src/concilium/application/skills/manifests/08-consolidacao-financeira/_skill_helpers_a.py`
5. `src/concilium/domain/services/bridge_analyzer.py`
6. `config/catalogos/mendeslobo/cpus/CPU-TERRA-ESCO-CARGA-1CAT-DMT2000.json`
7. `config/catalogos/mendeslobo/cpus/CPU-TERRA-COMPAC-FINAL-ROCHA.json`
8. `config/catalogos/mendeslobo/insumos/material/MA-AGIS-CPU-TERRA-COMPAC-PN.json`
9. `config/catalogos/mendeslobo/insumos/material/MA-DIESEL-S10.json`
10. `benchmarks/data/AGIS/artifacts/audit/benchmark_report.json`
11. `benchmarks/data/AGIS/audit/agis_discrepancy_action_plan.json`

---

## Resultado Esperado

Ao final da NEP-029, o pipeline produz um único preço unitário por item, derivado de
parâmetros operacionais rastreáveis, consistente entre modo normal e benchmark, com
subtotais proporcionais à quantidade e Bridge refletindo divergência real — não artefato
de dado ausente.
