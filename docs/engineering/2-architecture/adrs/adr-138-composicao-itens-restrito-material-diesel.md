# ADR-138 — Composição de Custo: `composicao_itens` Restrito a MATERIAL/DIESEL

**Status:** ⚠️ Parcialmente Implementado _(Fase 1 — MAO_OBRA/EQUIPAMENTO — ✅ concluída para `mendeslobo`/`rfi-r02`; Fase 2 — MATERIAL — ✅ concluída para as 30 CPUs de `mendeslobo` com BOM genuíno, ver §D7; DIESEL — ⏳ pendente, ver Plano de Implementação)_
**Data:** 2026-07-13
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-030 (composição tipada de equipes — `ComposicaoPadraoEquipe`/`FuncaoEquipe`/`EquipamentoEquipe`/`MaterialEquipe`), ADR-053 (separação CPU × Produtividade), NEP-032 D1 (hierarquia de fontes de precificação bottom-up)

---

## Contexto

### Problema

P1. **`CPU.composicao_itens`** (`domain/models/catalog/catalogo.py`) é uma lista plana de coeficientes (`insumo_id`, `coeficiente`, `categoria_custo` ∈ {MAO_OBRA, EQUIPAMENTO, MATERIAL, DIESEL}). Ela coexiste, na mesma CPU, com **`Producao.composicao_padrao_equipe`** (ADR-030) — o modelo estruturado de equipe (`funcoes`, `equipamentos`, `materiais`) usado pela precificação bottom-up canônica (NEP-032 D1, `_resolve_preco_cat_item`): *"Hierarquia de fontes: 1. `derivar_precos_unitarios_sbdi(producao, ...)` — bottom-up (Fonte 1); 2. `composicao_itens × preco_insumo` — fallback (Fonte 2)."*

P2. **Censo do catálogo `mendeslobo` (138 CPUs, 317 linhas de `composicao_itens`)** mostra que a coexistência é, na prática, redundância pura:

| Categoria | Linhas | Correspondência com `composicao_padrao_equipe` |
|---|---|---|
| MAO_OBRA | 133 | 132 têm `insumo_id` idêntico a um `funcao_id` já presente em `funcoes` |
| EQUIPAMENTO | 97 | 96 têm `insumo_id` idêntico a um `equip_id` já presente em `equipamentos` |
| MATERIAL | 73 | Sem equivalente — `MaterialEquipe` (ADR-030 D2) é consumo horário operacional, não BOM por unidade de produto |
| DIESEL | 14 | Sem equivalente — `EquipamentoEquipe` só tem taxa L/h agregada, sem insumo específico |

`rfi-r02` (75 CPUs) tem apenas 11 linhas de `composicao_itens` no total, todas DIESEL — zero MAO_OBRA/EQUIPAMENTO a remover ali (a migração é um no-op nesse catálogo, mas ele permanece elegível por consistência de escopo).

P3. **A redundância nunca é a fonte real de preço em `mendeslobo`/`rfi-r02` — mas é peso morto com risco de divergência silenciosa.** Verificação empírica (Step 0 deste ADR, script de snapshot de preços executado via `run_precificacao_unitaria` sobre os 213 CPUs de `mendeslobo`+`rfi-r02`): 100% resolvem pela Fonte 1 (`derivar_precos_unitarios_sbdi` com `sbdi.total > 0`) — a Fonte 2 é **dead code real** nesses dois catálogos hoje. Isso significa que, se um editor atualizar `composicao_padrao_equipe` (ex.: trocar um caminhão por outro) sem lembrar de replicar a mudança em `composicao_itens`, nada detecta a divergência — as duas representações silenciosamente descolam, e o preço mostrado pela Fonte 1 continua correto até o dia em que a Fonte 1 falhar e a Fonte 2 (obsoleta) assumir sem aviso.

P4. **A Fonte 2, hoje, também tem um bug latente de "falha silenciosa incompleta"**: quando de fato acionada (Fonte 1 falha) e `composicao_itens` não tem nenhuma linha MAO_OBRA ou EQUIPAMENTO, `_compute_preco_cat_from_cpu` retorna essas categorias como `0.0` — um preço incompleto apresentado como completo, sem nenhum `ValidacaoItem` de erro. Esse bug é pré-existente (não introduzido por este ADR).

P5. **Achado empírico do Step 0 que mudou o escopo desta ADR: a Fonte 2 NÃO é dead code em `config/catalogos/samples/`.** A verificação de P3 foi feita originalmente com a expectativa (baseada em análise preliminar) de que se estenderia a `samples`. Ao rodar o snapshot de preços sobre as 11 CPUs de `samples`, descobriu-se o oposto: **100% delas resolvem pela Fonte 2 hoje**, não pela Fonte 1. Causa raiz: os arquivos `config/catalogos/samples/produtividades/*.json` têm `valor_horario` preenchido mas **não têm `composicao_padrao_equipe`** — sem composição de equipe, o custo horário calculado é 0, `sbdi.total <= 0`, e `_compute_preco_cat_from_production` retorna `None` (Fonte 1 falha) para todas as 11. `composicao_itens` (que em `samples/cpus.json` tem as mesmas 22 linhas EQUIPAMENTO + 10 DIESEL + 6 MATERIAL, e nunca teve MAO_OBRA) é, portanto, a fonte real e ativa de preço em `samples` — não redundante.

Isso tem duas consequências diretas para esta ADR:
1. **`samples` não pode ser migrado nesta Fase 1** — remover as linhas EQUIPAMENTO de `samples/cpus.json` destruiria a única fonte de preço de equipamento que essas 11 CPUs têm hoje, quebrando o argumento de "byte-idêntico" que sustenta a Fase 1.
2. **O fail-loud da Fonte 2 (D2) só afeta 1 das 11 CPUs de `samples` independentemente da migração de dado** — dado o gate "E" de D2 (ver D2), 10 das 11 CPUs de `samples` têm ao menos uma linha EQUIPAMENTO em `composicao_itens` e continuam sendo precificadas exatamente como antes (mesmo `VAL-EQUIP-DECOMP` AVISO pré-existente, mão de obra assumida embutida no rate do equipamento — comportamento já estabelecido pelo ADR-023, não alterado por este ADR). Apenas `POCO-VISITA-PADRAO` — cujo `composicao_itens` é 100% MATERIAL (sem nenhuma linha EQUIPAMENTO nem MAO_OBRA; é um poço de visita construído em alvenaria manual, sem máquina) — passa a disparar `VAL-PLAN-MO-EQ-SEM-FONTE` e deixa de ser precificável. Isso é **intencional e aceito** (ver D6) — é a correção de um bug real de dado incompleto (mão de obra de alvenaria nunca contabilizada) nessa CPU específica, não uma regressão introduzida por esta ADR. Verificação: nenhum teste do repositório carrega `config/catalogos/samples` por `catalogo_id` para asserção de preço (`grep` não encontrou `load_catalogo("samples")`/`ProjectStore.init(..., "samples")` em `tests/`) — o impacto é isolado a essa única CPU de um catálogo de exemplo, sem regressão de teste.

### Fora de escopo desta ADR (Fase 2 original — MATERIAL migrado desde então, ver §D7)

Na formulação original desta ADR, MATERIAL e DIESEL não tinham outra fonte no modelo:
- **MATERIAL**: `MaterialEquipe` (ADR-030 D2) modela consumo direto **por hora de operação da equipe** (`consumo_por_hora`), não uma lista de materiais por unidade de produto (BOM) como `composicao_itens` MATERIAL representa. Migrar exigiria decidir se/como normalizar entre as duas bases (hora de operação × unidade de produto), o que foi tratado como decisão de dado/produto — resolvida e implementada em §D7 (Fase 2 MATERIAL): a normalização usa `consumo_por_hora = coeficiente × valor_horario`.
- **DIESEL**: `EquipamentoEquipe` (ADR-030 D1) tem apenas `consumo_litros_hora_estimado` agregado por equipamento — não há campo para o insumo de combustível específico (ex.: tipo de diesel, fornecedor) que `composicao_itens` DIESEL carrega. Isso **permanece** fora de escopo (ver §D7 nota final) — nenhum código ou dado de DIESEL foi tocado.

Essas linhas (MATERIAL + DIESEL, em todos os catálogos, incluindo `samples`) permaneciam em `composicao_itens` como a fonte primária dessas categorias. A partir de §D7, isso deixou de valer para MATERIAL em `mendeslobo` (30 CPUs migradas) — DIESEL e os demais catálogos/CPUs continuam como antes. Ver Plano de Implementação. A correção do dado incompleto de `samples/produtividades/*.json` (adicionar `composicao_padrao_equipe`) também é deixada fora de escopo — é um problema de dado de exemplo, não de arquitetura.

---

## Decisão

**D1 — `composicao_itens` passa a ser escopo exclusivo de MATERIAL/DIESEL nos catálogos onde a Fonte 1 já governa 100% dos casos.** MAO_OBRA e EQUIPAMENTO são removidos de `composicao_itens` em `mendeslobo` e `rfi-r02` via script idempotente `scripts/catalog/strip_composicao_itens_mo_eq.py` (dry-run por padrão, `--apply` para aplicar). `config/catalogos/test/` e `config/catalogos/samples/` são **explicitamente excluídos** desta migração — ver D4/D6.

**D2 — Fonte 2 (`_preco_cat_fallback_composicao`/`_compute_preco_cat_from_cpu`, em `_cpu_fallback.py`/`_preco_cpu.py`) falha alto em vez de retornar preço sem nenhuma cobertura de MO/EQ.** Quando a Fonte 2 é de fato acionada (Fonte 1 retornou `None`) e `composicao_itens` não tem **nenhuma** linha MAO_OBRA **e nenhuma** linha EQUIPAMENTO (as duas simultaneamente ausentes), o item não é precificado (`preco_cat = None`, mesmo contrato de retorno já usado quando a Fonte 1 falha) e é emitida `VAL-PLAN-MO-EQ-SEM-FONTE` (ERRO):

```python
def _fallback_sem_fonte_mo_eq(cpu_model: Any) -> bool:
    itens = cpu_model.composicao_completa
    tem_equipamento = any(ci.categoria_custo == "EQUIPAMENTO" for ci in itens)
    tem_mao_obra = any(ci.categoria_custo == "MAO_OBRA" for ci in itens)
    return not tem_equipamento and not tem_mao_obra
```

O gate é deliberadamente uma condição "E", não "OU" — a primeira versão implementada usava "OU" (qualquer uma das duas ausente já disparava ERRO), mas isso quebrou testes existentes e revelou uma tensão real: `tests/unit/test_adr023_bdi_diferenciado.py::TestSkill04EquipamentoDecomp` já cobre, de forma deliberada e testada, o caso "EQUIPAMENTO presente sem MAO_OBRA" — o mecanismo pré-existente `VAL-EQUIP-DECOMP` (ADR-023 §D3) assume que o rate do equipamento pode já embutir o custo do operador e emite um AVISO, não bloqueia. Bloquear esse caso com ERRO teria contradito um design já estabelecido. Simetricamente, "MAO_OBRA presente sem EQUIPAMENTO" é uma atividade legitimamente sem máquina (serviço manual). O gate "E" fecha exatamente o caso realmente órfão — nenhuma cobertura de nenhuma das duas categorias — sem reabrir essa discussão já resolvida pelo ADR-023. Isso segue a mesma filosofia "falha alto, não corrompe" já aplicada em `CatalogUpdater`/`atualizar_capacidade_gargalo` (que levantam `ValueError` em vez de gravar um valor calibrado incorreto). Esta decisão é deliberadamente **catálogo-agnóstica** (a skill de precificação não tem — e não deve ter — conhecimento de qual catálogo está processando); por isso ela também se aplica a `samples`, mesmo sem migração de dado ali — ver P5/D6.

**D3 — Documentação do modelo atualizada.** `ComposicaoItem`/`CPU.composicao_itens` (`catalogo.py`) passam a documentar o escopo reduzido, seguindo o precedente da nota ADR-053 já presente no docstring de `CPU`.

**D4 — `config/catalogos/test/` não é migrado.** Esse catálogo é usado como fixture viva por dezenas de testes de integração via `tests/conftest.py` (`_session_pipeline_sk03` e derivados — `ESCO-CARGA-*`, `COMPACT-ATERRO-100PN`, `REGULARIZACAO-SUBLEITO`, etc.). Verificação empírica: cada CPU de `test/cpus.json` tem `producao_horaria` e `composicao_padrao_equipe` embutidos diretamente no JSON da CPU (padrão pré-ADR-053, sintetizado em `Producao` por `_synthesize_missing_producoes`), então a Fonte 1 resolve normalmente ali também (confirmado: esses são exatamente os campos que faltam em `samples/produtividades/*.json` — a diferença entre os dois catálogos é ter ou não essa síntese) — a Fonte 2 não é o caminho real dessas fixtures. Migrar esse catálogo não traria risco de preço incorreto, mas foi deixado de fora por não fazer parte dos catálogos de produção.

**D5 — `cure_schema/_cure_contextual.py` para de sintetizar MAO_OBRA/EQUIPAMENTO em `composicao_itens`.** `_cure_contextual_sintetiza_composicao_via_equipe` sintetizava linhas MAO_OBRA/EQUIPAMENTO em `composicao_itens` vazio a partir de `Producao.composicao_padrao_equipe` quando não havia candidato MATERIAL único (`MA-{codigo}`). Sob D1, isso reintroduziria exatamente as linhas redundantes que esta ADR remove. A função passa a não sintetizar essas categorias — apenas registra `manual`/`skipped` (revisão econômica de MATERIAL/DIESEL, se aplicável) — e as funções de baixo nível dedicadas a essa síntese (`_cure_contextual_synthesize_composicao_from_equipe`, `_cure_contextual_synthesized_item`) foram removidas por ficarem sem chamador.

**D6 — `config/catalogos/samples/` não é migrado, e o fail-loud de D2 é aceito como correção de bug pré-existente em `POCO-VISITA-PADRAO`.** Ver P5. Não migrar preserva as linhas EQUIPAMENTO que hoje são a única fonte de preço de equipamento em 10 das 11 CPUs (a Fonte 2 continua funcionando ali exatamente como antes, incluindo o `VAL-EQUIP-DECOMP` AVISO já existente). O gate "E" de D2 significa que só `POCO-VISITA-PADRAO` (MATERIAL puro, sem EQUIPAMENTO nem MAO_OBRA) deixa de ser precificável via `run_precificacao_unitaria`, até que `samples/produtividades/POCO-VISITA-PADRAO-PROD-001.json` ganhe `composicao_padrao_equipe` (conserta a Fonte 1) ou `samples/cpus.json` ganhe uma linha MAO_OBRA em `composicao_itens` para essa CPU (Fonte 2 completa). Nenhum teste do repositório depende do preço computado de `samples` (verificado por busca textual) — o risco é isolado a uma única CPU de um catálogo de exemplo, não de produção.

**D7 — Fase 2 (MATERIAL): 30 CPUs de `mendeslobo` com BOM genuíno migradas para `MaterialEquipe`; 40 CPUs com placeholder AGIS deliberadamente excluídas; DIESEL permanece pendente.**

Censo re-executado sobre `composicao_itens` MATERIAL de `mendeslobo` (70 CPUs com ao menos uma linha MATERIAL) mostrou duas populações distintas:

| Grupo | CPUs | Padrão do `insumo_id` | Natureza |
|---|---|---|---|
| Placeholder AGIS | 40 | `MA-AGIS-CPU-<codigo>` | Artefato de modelagem de dado: preço = preço unitário legado da própria CPU (não é material real). Migrar duplicaria custo — contaria a CPU inteira como "material" dela mesma. |
| BOM genuíno | 30 | cimento, areia, brita, tubos de concreto/PVC, emulsão asfáltica, brita graduada/BGTC, geotêxtil, pavers, guias | Lista real de insumos por unidade de produto (BOM), com `coeficiente` correspondendo a quantidade real por unidade de CPU. |

Apenas o segundo grupo (30 CPUs, lista completa no PR/commit de dado) foi migrado. O grupo AGIS (40 CPUs) foi deliberadamente deixado intocado — suas linhas `composicao_itens` MATERIAL continuam exatamente como antes (mesmo comportamento de preço: `material=0.0` no cálculo bottom-up, já que a Fonte 1 nunca as usa, e a Fonte 2 nunca é acionada porque a Fonte 1 sempre resolve primeiro nesses catálogos — ver §P3). Migrar esse grupo exigiria antes resolver o problema de modelagem de dado (o placeholder é um substituto ad-hoc para "custo de material não detalhado", não um BOM real) — fora do escopo mecânico desta migração.

**Fórmula de conversão (price-preserving por construção):**

```
consumo_por_hora = coeficiente × Producao.valor_horario
```

`coeficiente` é quantidade por unidade de produto da CPU; `valor_horario` (ρ) é unidades de produto por hora; o produto é quantidade por hora — exatamente a definição de `MaterialEquipe.consumo_por_hora` (ADR-030 D2). Prova algébrica: a Fonte 1 calcula o preço de MATERIAL como `Σ(consumo_por_hora × preco_insumo) / valor_horario`; substituindo a fórmula acima, isso se reduz a `Σ(coeficiente × preco_insumo)` — exatamente o que a Fonte 2 (`_compute_preco_cat_from_cpu`) já calculava direto de `composicao_itens`, antes da migração. Verificação concreta: `CPU-SANEA-POCO-VISITA-PADRAO` tem `coeficiente=28.0` (sacos de cimento por poço) e `valor_horario=0.25` (poços/h) → `consumo_por_hora=7.0` sacos/h (28 sacos ÷ 4h para produzir 1 poço a 0,25 poço/h).

**Execução e verificação empírica (script `scripts/catalog/migrate_composicao_itens_material.py`, dry-run por padrão, `--apply` para aplicar, idempotente):**

- 30 CPUs migradas, 33 entradas `MaterialEquipe` adicionadas (28 CPUs com 1 material; `CPU-SANEA-DREN-MAN-DN300` com 2; `CPU-SANEA-POCO-VISITA-PADRAO` com 3), 33 linhas `composicao_itens` MATERIAL removidas (mesmo padrão de consolidação de fonte única da Fase 1 — evita a divergência silenciosa entre as duas representações que a Fase 1 já eliminou para MAO_OBRA/EQUIPAMENTO).
- Verificação price-preserving: para as 30 CPUs, o preço de MATERIAL pós-migração (Fonte 1, `VAL-PLAN-BOTTOM-UP`) bate com o preço pré-migração calculado pela Fonte 2 direto de `composicao_itens`, com tolerância 1e-4 relativa — confirmado, sem nenhuma divergência (a maior diferença observada foi de ordem 1e-7, ruído de ponto flutuante do `round(consumo_por_hora, 6)`).
- Gap de preço unitário fechado: soma das 30 CPUs, R$ 6.678,6265 (~R$ 6.678,63) — valor que antes da migração era silenciosamente `0.0` em cada uma dessas CPUs individualmente, apesar de haver BOM real e completo no catálogo.
- Blast radius: os outros 108 CPUs de `mendeslobo` (incluindo as 40 placeholder AGIS) permanecem byte-idênticos ao snapshot pré-migração — confirmado por comparação campo a campo (`material`, `diesel`, `mao_obra`, `equipamentos`, `total`, `validacoes`) sobre os 138 CPUs do catálogo.

**Nota de design (não bloqueante) — reaproveitamento de `MaterialEquipe.consumo_por_hora`:** esta migração reaproveita um campo cuja semântica original (ADR-030 D2) é *consumo operacional por hora da equipe* (ex.: água de umectação, aditivo de combustível) para representar algo conceitualmente diferente — uma quantidade de BOM por unidade de produto, convertida via `coeficiente × valor_horario`. A conversão é numericamente correta e price-preserving (provado acima e verificado empiricamente), mas é um esticamento semântico do campo: um leitor futuro de `Producao.composicao_padrao_equipe.materiais` não tem, hoje, nenhum sinal no próprio dado de que uma entrada é "consumo operacional direto" vs. "BOM convertido". Se o padrão de migrar BOM por este caminho se tornar comum, vale uma ADR própria para dar a essas entradas um campo/flag dedicado (ex.: `origem: "bom_convertido"` ou um tipo `MaterialBOM` separado de `MaterialEquipe`) em vez de continuar sobrecarregando a mesma estrutura para dois conceitos distintos.

**DIESEL permanece fora de escopo** — nenhum código ou dado de DIESEL foi tocado nesta Fase 2. `EquipamentoEquipe` ainda não tem campo para o insumo de combustível específico que `composicao_itens` DIESEL carrega (ver §Fora de escopo). Fica como próxima fase, se/quando decidida.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Manter `composicao_itens` como está (não remover MAO_OBRA/EQUIPAMENTO) | Peso morto permanente com risco de divergência silenciosa entre as duas representações (P3); não fecha o bug de preço incompleto na Fonte 2 (P4) |
| A2 | Remover MAO_OBRA/EQUIPAMENTO **e** também migrar MATERIAL/DIESEL para `composicao_padrao_equipe` nesta mesma ADR | `MaterialEquipe`/`EquipamentoEquipe` não têm hoje a granularidade necessária (Fora de escopo); decisão de dado/produto que merece ADR própria (Fase 2), não deve bloquear a Fase 1 |
| A3 | Migrar também `config/catalogos/test/` | Fixture viva de dezenas de testes de integração (D4); sem ganho de segurança de preço (Fonte 1 já resolve ali); risco desnecessário de quebrar testes não relacionados ao objetivo desta ADR |
| A4 | Ao fechar o bug da Fonte 2 (D2), rebaixar para AVISO em vez de ERRO | Contradiz a filosofia "falha alto, não corrompe" já estabelecida no código (`CatalogUpdater`); um preço com uma categoria de custo inteira faltando não deveria compor um total apresentado como confiável |
| A5 | Migrar `samples` também, já que estava no plano original | **Rejeitado após verificação empírica do Step 0** (P5): a Fonte 1 falha para 100% das CPUs de `samples` (produtividades sem `composicao_padrao_equipe`) — migrar quebraria a única fonte de preço ativa desse catálogo. Sem esse achado, esta ADR teria introduzido uma regressão de preço real; o Step 0 (verificação empírica obrigatória antes de qualquer mudança de dado) existe exatamente para capturar isso |
| A6 | Escopar o fail-loud de D2 para não disparar em `samples` (ex.: flag por catálogo) | Introduziria conhecimento de identidade de catálogo dentro da skill de precificação (`06-resultado-financeiro`), que hoje é — corretamente — agnóstica a isso; o preço incompleto de `samples` é um bug real que deve ser corrigido no dado (`samples/produtividades/*.json`), não escondido no código |

---

## Consequências

### Positivas

| Benefício | Detalhe |
|---|---|
| Elimina risco de divergência silenciosa em `mendeslobo`/`rfi-r02` | MAO_OBRA/EQUIPAMENTO têm agora exatamente uma fonte de verdade (`composicao_padrao_equipe`) |
| Fecha bug de preço incompleto silencioso (todos os catálogos) | Fonte 2 agora falha alto (`VAL-PLAN-MO-EQ-SEM-FONTE`) em vez de devolver `mao_obra=0.0`/`equipamentos=0.0` |
| Reduz 230 linhas de dado redundante em `mendeslobo` | Menor superfície de manutenção |
| Zero impacto de preço em `mendeslobo`/`rfi-r02` | Fonte 1 já governa 100% dos casos verificados; migração comprovada byte-idêntica (ver Test Plan do PR) |
| Descobre e documenta um bug de dado real em `samples` | Antes invisível (mão de obra sempre zerada silenciosamente); agora sinalizado explicitamente |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Fonte 2 deixa de calcular MAO_OBRA/EQUIPAMENTO para qualquer CPU futuro cuja Fonte 1 falhe em `mendeslobo`/`rfi-r02` | Deliberado (D2) — falhar alto é preferível a um preço incompleto; a mitigação real é garantir que `composicao_padrao_equipe`/`valor_horario` estejam sempre corretos |
| `samples/POCO-VISITA-PADRAO` (1 de 11 CPUs) deixa de ser precificável até correção de dado | Aceito (D6) — catálogo de exemplo, sem consumidor de teste ou produção identificado; as outras 10 CPUs de `samples` continuam precificando normalmente (gate "E" de D2); correção de dado (`composicao_padrao_equipe` em `samples/produtividades/`) é trivial e fica registrada como débito conhecido |
| `_cure_contextual.py` não repara mais automaticamente `composicao_itens` vazio via equipe | Escopo dessa curadoria já não fazia sentido para MAO_OBRA/EQUIPAMENTO sob D1; MATERIAL/DIESEL continuam cobertos pelo caminho `MA-{codigo}` existente |
| MATERIAL/DIESEL continuam sem redundância/checagem cruzada (Fase 2 pendente) | Ver Plano de Implementação — decisão de dado/produto explicitamente deferida |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| Fase 1 | Script de migração idempotente; remoção de MAO_OBRA/EQUIPAMENTO de `mendeslobo`/`rfi-r02` (NÃO `samples`, NÃO `test`); fail-loud na Fonte 2 (`VAL-PLAN-MO-EQ-SEM-FONTE`); `_cure_contextual.py` atualizado; docstrings de `ComposicaoItem`/`CPU` atualizadas; verificação byte-idêntica de preços pré/pós migração para `mendeslobo`/`rfi-r02` | ✅ Implementado |
| Fase 1-bis (débito registrado) | Corrigir `samples/produtividades/*.json` (adicionar `composicao_padrao_equipe` faltante) para que a Fonte 1 volte a funcionar; então migrar `samples/cpus.json` como as demais | ⏳ Pendente — não bloqueia esta ADR, catálogo de exemplo sem consumidor identificado |
| Fase 2 — MATERIAL | Converter BOM genuíno de `composicao_itens` para `MaterialEquipe` via `consumo_por_hora = coeficiente × valor_horario` (price-preserving); script `migrate_composicao_itens_material.py`; 30 CPUs de `mendeslobo` migradas, 40 CPUs placeholder AGIS explicitamente excluídas (ver §D7) | ✅ Implementado (`mendeslobo`) |
| Fase 2 — DIESEL | Decidir modelo de dado para DIESEL (insumo específico em `EquipamentoEquipe`, hoje só há `consumo_litros_hora_estimado` agregado); migrar ou formalizar `composicao_itens` como fonte permanente | ⏳ Pendente — decisão de dado/produto, não de código |

## Definition of Done

### Fase 1
- [x] `scripts/catalog/strip_composicao_itens_mo_eq.py` criado (dry-run padrão, `--apply`), idempotente, escopado a `mendeslobo`/`rfi-r02`
- [x] Migração aplicada em `mendeslobo`/`rfi-r02`; `config/catalogos/test/` e `config/catalogos/samples/` explicitamente não tocados
- [x] Teste TDD demonstrando o bug (preço incompleto silencioso) antes da correção, e comportamento correto (`VAL-PLAN-MO-EQ-SEM-FONTE`, ERRO) depois
- [x] `_cure_contextual.py` não sintetiza mais MAO_OBRA/EQUIPAMENTO em `composicao_itens`; testes atualizados
- [x] Docstrings de `ComposicaoItem`/`CPU.composicao_itens` atualizadas com o novo escopo
- [x] Verificação: preços computados para todo CPU de `mendeslobo`/`rfi-r02` são byte-idênticos antes/depois da migração
- [x] Achado de `samples` (Fonte 2 ativa, não dead code) investigado, documentado e excluído do escopo da Fase 1 com justificativa
- [x] Suíte de testes completa sem regressões; `ruff check`/`ty check src` limpos

### Fase 2 — MATERIAL
- [x] Censo re-executado sobre `composicao_itens` MATERIAL de `mendeslobo`: 70 CPUs, separadas em 40 placeholder AGIS (excluídas) e 30 BOM genuíno (migradas) — ver §D7
- [x] `scripts/catalog/migrate_composicao_itens_material.py` criado (dry-run padrão, `--apply`), idempotente
- [x] Teste TDD demonstrando o bug (`material == 0.0` para as 30 CPUs, apesar de BOM completo no catálogo) antes da migração, e comportamento correto (`VAL-PLAN-BOTTOM-UP`, preço não-zero) depois — `tests/unit/test_adr138_fase2_material_migration.py`
- [x] Migração aplicada: 30 CPUs, 33 `MaterialEquipe` adicionadas, 33 linhas `composicao_itens` MATERIAL removidas
- [x] Verificação price-preserving: preço de MATERIAL pós-migração bate com o cálculo direto de `composicao_itens` pré-migração (tolerância 1e-4 relativa) para as 30 CPUs
- [x] Verificação de blast radius: os outros 108 CPUs de `mendeslobo` (incluindo as 40 placeholder AGIS) permanecem byte-idênticos antes/depois
- [x] Suíte de testes completa sem regressões; `ruff check`/`ty check src` limpos
- [x] Nota de design registrada sobre reaproveitamento semântico de `MaterialEquipe.consumo_por_hora` (ver §D7, não bloqueante)

### Fase 2 — DIESEL (ainda pendente)
- [ ] Decisão de modelo de dado para DIESEL (insumo específico em `EquipamentoEquipe`)
- [ ] Migração das linhas restantes ou decisão formal de manter `composicao_itens` como fonte permanente para essa categoria
- [ ] (Fase 1-bis) Corrigir dado incompleto de `samples/produtividades/*.json` e migrar `samples/cpus.json`
