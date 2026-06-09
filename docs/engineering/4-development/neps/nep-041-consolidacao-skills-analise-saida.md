# NEP-041: Consolidação de Skills de Análise, Saída e Financeiro

**Status:** Proposta 🟡  
**Data:** 2026-06-09  
**Autor:** Engenharia de Implementação  
**Categoria:** Refatoração de Skills / Pipeline de Análise e Financeiro  
**Relacionado:** ADR-070, ADR-021, ADR-026  
**Tipo:** Refactor estrutural

---

## Contexto

O pipeline de skills possui 15 skills numeradas de 01 a 15. A extremidade direita do grafo
(skills de análise, decisão e saída) acumula responsabilidades sobrepostas e dependências
de ordenação pura que não refletem dependências reais de dados.

A análise de impacto de 2026-06-09 identificou três problemas:

1. **15-relatorio-executivo** é um intermediário sem consumidor externo — produz relatórios
   que são lidos exclusivamente por **09-relatorio-e-artefatos**. Dois passos sequenciais
   para o mesmo destino final (Excel + JSON).

2. **14-explorador-cenarios** declara `depends_on = ["13-assessor-replanejamento"]` mas
   **não lê `replan_suggestions`** em nenhum ponto do código — lê `ponto_equilibrio`
   (produzido por skill-06 via ADR-082). A dependência é ordenação pura.

3. **11-avaliacao-intervencoes** e **12-registro-decisoes** pressupõem um loop de feedback
   do agente (geração de propostas → avaliação ROI×Effort → registro de decisão) que ainda
   não existe. Ficam dormentes à espera de ADR-070.

---

## Problema a Resolver

### P1 — Duas skills de saída sem consumidor intermediário

`15-relatorio-executivo` e `09-relatorio-e-artefatos` são os dois nós terminais do grafo.
15 produz `RelatorioCriticidade`, `RelatorioSensibilidade`, `RelatorioIntervencao` e
`BridgeWaterfall`. 09 lê esses quatro artefatos e os materializa no Excel (.xlsm) e JSON.
Nenhuma outra skill consome a saída de 15.

Impacto: invocação dupla, dois passos de validação, estado canônico intermediário sem valor.

### P2 — Dependência falsa entre 13 e 14

`skill.toml` de 14 lista `"13-assessor-replanejamento"` em `depends_on.skills`. A análise do
código (`skill.py` de 14) mostra que 14 lê `ponto_equilibrio[].levers_equilibrio` — fonte ADR-082,
produzida por skill-06/08 — e não `replan_suggestions`. A dependência garante apenas
que 13 execute primeiro. As duas skills são paralelas em termos de fluxo canônico.

Impacto: topologia serializada desnecessariamente; código de 14 é mais acoplado do que precisa.

### P3 — Skills 11 e 12 sem caminho de ativação

`11-avaliacao-intervencoes` requer `intervencoes_propostas` como input obrigatório — ninguém
gera essa lista no pipeline atual. `12-registro-decisoes` requer cinco campos humanos
(`objective`, `considered_interventions`, `selected_intervention`, `justification`,
`decided_by`) que nunca chegam via pipeline automatizado.

`11` aparece em `ANALYSIS_SKILLS` em `runner.py`. `12` tem side effects hard-coded em
`runtime.py` (linha ~1774) e `execution.py` (linha ~296) para persistir `decision_log.json`.
Nenhuma outra skill depende de `intervention_assessments` ou `decision_log`.

Impacto: código morto registrado como ativo; side effects no runtime para skills que não rodam.

---

## Solução em 3 Fases

### **Fase 1: Merge de 09 + 15 (absorver 15 em 09)**

**Objetivo**: Unificar renderização de relatórios e geração de Excel em uma única skill.

**Estratégia**: Manter o ID `09-relatorio-e-artefatos` (3 referências hard-coded no runtime
apontam para esse ID — renomear exigiria mudanças em `runtime.py` e `execution.py`). Absorver
a lógica de `15-relatorio-executivo` como estágio interno de 09.

**Mudanças em `09-relatorio-e-artefatos/skill.toml`**:

```toml
[skill]
id = "09-relatorio-e-artefatos"
phase = "Saída"
version = "2.0.0"
descricao = "Relatório executivo consolidado e artefatos de saída (Excel + JSON). Absorve 15."

[depends_on]
skills = ["08-consolidacao-financeira", "10-diagnostico-criticidade", "13-replanejamento-e-cenarios"]
canonical_sections = [
  "resultado_reconciliado", "resultado", "planejamento", "equipes_diretas", "indiretos",
  "cost_criticality_report", "replan_suggestions", "plan_space_result", "bridge_analysis"
]

[produces]
canonical_section = "relatorio_saida"
validations = [
  "VAL-ADAPTER-01", "VAL-ADAPTER-CRITICIDADE", "VAL-ADAPTER-EXCEL", "VAL-ADAPTER-EXCEL-LIVE",
  "VAL-REX-CRIT", "VAL-REX-SENS", "VAL-REX-INT", "VAL-REX-BRIDGE"
]
```

**Mudanças em `09-relatorio-e-artefatos/skill.py`**:
- Incorporar o bloco de construção de `RelatorioCriticidade`, `RelatorioSensibilidade`,
  `RelatorioIntervencao` e `BridgeWaterfall` que hoje reside em `15/skill.py`
- Escrever `relatorio_executivo` no canônico como subestrutura de `relatorio_saida`
- Manter a seção `canonical.relatorio_executivo` para compatibilidade com leitores existentes

**Deletar**: `src/concilium/application/skills/manifests/15-relatorio-executivo/`

**Impacto em código**: zero mudanças no runtime — ID mantido.

---

### **Fase 2: Merge de 13 + 14 → `13-replanejamento-e-cenarios`**

**Objetivo**: Unificar assessor de replanejamento e explorador de cenários em uma skill coesa
que produz tanto sugestões de reparo quanto análise do espaço de planos.

**Nova skill**: `13-replanejamento-e-cenarios`

**`skill.toml` proposto**:

```toml
[skill]
id = "13-replanejamento-e-cenarios"
phase = "Análise"
version = "1.0.0"
descricao = "Assessor de replanejamento e exploração do espaço de planos. Unifica 13 + 14."

[depends_on]
skills = ["08-consolidacao-financeira", "10-diagnostico-criticidade", "05-equipes-e-alocacao"]
canonical_sections = [
  "resultado", "resultado_reconciliado", "cost_criticality_report",
  "conflitos_pico", "indiretos", "equipes_diretas", "cronograma", "ponto_equilibrio"
]

[produces]
canonical_section = "replan_e_cenarios"
validations = [
  "VAL-REPLAN-01", "VAL-REPLAN-02",
  "VAL-PSE-01", "VAL-PSE-02", "VAL-PSE-PRECONDICAO"
]

[inputs]
required = []
optional = ["meta_margem_alvo", "semanas_reducao_alvo", "faixa_duracao_min_pct"]

[snapshots]
consumed = ["perfil"]
```

> **Nota sobre trigger**: 13 original rodava apenas em AMARELO/VERMELHO. 14 sempre rodava
> (escaneia oportunidades em VERDE também). A skill unificada deve sempre rodar — o status
> de entrada determina o comportamento interno (repair vs. scan), não a execução da skill.

**Retrocompatibilidade canônica**: a nova skill deve continuar populando
`canonical.replan_suggestions` e `canonical.plan_space_result` separadamente — Fase 1
(09+15) consome ambos. Opcionalmente criar `canonical.replan_e_cenarios` como wrapper.

**Deletar**: `src/concilium/application/skills/manifests/14-explorador-cenarios/`

**Atualizar `depends_on` em `09-relatorio-e-artefatos/skill.toml`**: substituir
`["13-assessor-replanejamento", "14-explorador-cenarios"]` por `["13-replanejamento-e-cenarios"]`.

**Impacto em código**: nenhuma referência hard-coded a 13 ou 14 no runtime — mudança restrita
ao manifest e aos arquivos de skill.

---

### **Fase 3: Congelar 11 e 12**

**Objetivo**: Remover skills inativas do pipeline e limpar side effects do runtime.
Manter os arquivos marcados como dormentes até ADR-070 ser implementado.

**Mudanças**:

1. `src/concilium/application/scenarios/runner.py`: remover `"11-avaliacao-intervencoes"`
   de `ANALYSIS_SKILLS`.

2. `src/concilium/application/runtime.py` (linha ~1774): remover bloco condicional
   `skill_id == "12-registro-decisoes"` que persiste `decision_log.json`.

3. `src/concilium/application/runtime/mixins/execution.py` (linha ~296): remover referência
   equivalente a `"12-registro-decisoes"`.

4. Adicionar header em ambos os `skill.toml`:
   ```toml
   [skill]
   status = "dormante"
   motivo = "Aguarda loop de feedback de agente (ADR-070). Não incluso no pipeline ativo."
   ```

**Nota**: não deletar os arquivos — o contrato de avaliação ROI×Effort de 11 e o protocolo
de registro de decisão de 12 são sementes válidas para a implementação de ADR-070.

---

### **Fase 4: Merge de 06 + 07 + 08 → `06-resultado-financeiro`**

**Objetivo**: Unificar o cluster financeiro — precificação unitária, custos indiretos e
consolidação de resultado — em uma única skill de "Planejamento Financeiro".

**Motivação**: 06 e 07 são siblings (ambos dependem só de 05, nenhum do outro). 08 depende
de ambos e não tem outro propósito além de consolidar suas saídas. Os três formam um cluster
coeso sem dependentes externos intermediários — ninguém consome `planejamento` ou `indiretos`
sem também consumir `resultado`.

**`skill.toml` proposto**:

```toml
[skill]
id = "06-resultado-financeiro"
phase = "Planejamento Financeiro"
gate = true  # herda gate de 06-precificacao-unitaria
version = "1.0.0"
descricao = "Precificação unitária, custos indiretos e consolidação financeira. Unifica 06+07+08."

[depends_on]
skills = ["05-equipes-e-alocacao"]
canonical_sections = ["eap", "equipes_diretas", "projeto"]

[produces]
canonical_section = "resultado_financeiro"
validations = [
  "VAL-POL-BDI", "VAL-POL-INDIRETO", "VAL-CONSOL-OK"
]

[inputs]
required = []
optional = [
  "bdi_aplicado",                    # de 06
  "composicoes_indireto",            # de 07
  "dados_mobilizacao",               # de 07
  "perc_encargos",                   # de 07
  "tabela_bdi", "bdi_lucro_impostos" # de 08
]

[snapshots]
consumed = ["catalogo", "perfil"]
```

**Retrocompatibilidade canônica**: a skill deve continuar populando
`canonical.planejamento`, `canonical.indiretos` e `canonical.resultado` separadamente —
downstream consumers (`10-diagnostico-criticidade`, `13-replanejamento-e-cenarios`,
`09-relatorio-e-artefatos`) leem essas seções pelo nome.

**Atualizar `depends_on`** nos consumers:
- `10-diagnostico-criticidade`: substituir `"06-precificacao-unitaria"` por `"06-resultado-financeiro"`
- `13-replanejamento-e-cenarios`: substituir `"08-consolidacao-financeira"` por `"06-resultado-financeiro"`
- `09-relatorio-e-artefatos`: substituir `"08-consolidacao-financeira"` por `"06-resultado-financeiro"`

**Deletar**: `07-custos-indiretos/` e `08-consolidacao-financeira/`. Renomear diretório de
`06-precificacao-unitaria/` para `06-resultado-financeiro/`.

**Impacto em código**: nenhuma referência hard-coded a 06, 07 ou 08 no runtime (exceto
`"09-relatorio-e-artefatos"` que já está tratado na Fase 1) — mudança restrita a manifests
e arquivos de skill.

---

### **Fase 5: Re-enumeração sequencial**

**Objetivo**: Eliminar as lacunas numéricas deixadas pelos merges e estabelecer uma
numeração contínua que reflita a ordem de execução do pipeline.

**Motivação**: após F1–F4 a sequência ativa seria `01–06, 09, 10, 13` — com lacunas em
07, 08, 11, 12, 14, 15. Grep confirmou que os IDs aparecem em ~100 strings em `src/` e
`tests/` além de manifests, docs e benchmarks. A re-enumeração é mais trabalho mas vale
pelo ganho de legibilidade a longo prazo.

**Mapeamento** (ordem de execução do pipeline):

| ID antes | ID depois | Status | Mudança de nome |
|---|---|---|---|
| `01-escopo-e-eap` | `01-escopo-e-eap` | ativo | nenhuma |
| `02-produtividade-climatica` | `02-produtividade-climatica` | ativo | nenhuma |
| `03-catalogo-de-recursos` | `03-catalogo-de-recursos` | ativo | nenhuma |
| `04-cronograma` | `04-cronograma` | ativo | nenhuma |
| `05-equipes-e-alocacao` | `05-equipes-e-alocacao` | ativo | nenhuma |
| `06-precificacao-unitaria` + `07-custos-indiretos` + `08-consolidacao-financeira` | `06-resultado-financeiro` | ativo (merge F4) | novo nome |
| `10-diagnostico-criticidade` | `07-diagnostico-criticidade` | ativo | renumerado |
| `13-assessor-replanejamento` + `14-explorador-cenarios` | `08-replanejamento-e-cenarios` | ativo (merge F2) | renumerado |
| `09-relatorio-e-artefatos` + `15-relatorio-executivo` | `09-relatorio-e-artefatos` | ativo (merge F1) | ID mantido |
| `11-avaliacao-intervencoes` | `10-avaliacao-intervencoes` | dormante | renumerado |
| `12-registro-decisoes` | `11-registro-decisoes` | dormante | renumerado |

> **Nota**: `09-relatorio-e-artefatos` mantém o número 09 porque tem 9 referências
> hard-coded em `runtime.py` e outras partes do código — manter o ID elimina essas mudanças.
> O resultado é uma sequência 01–09 (ativa) + 10–11 (dormante).

**Volume de mudanças por ID** (grep em `src/` + `tests/`):

| ID a remover/renomear | Ocorrências em src/ | Ocorrências em tests/ | Total |
|---|---|---|---|
| `06-precificacao-unitaria` → `06-resultado-financeiro` | 17 | 22 | **39** |
| `08-consolidacao-financeira` → deletar | 15 | 29 | **44** |
| `07-custos-indiretos` → deletar | 10 | 9 | **19** |
| `10-diagnostico-criticidade` → `07-diagnostico-criticidade` | 0 | 12 | **12** |
| `15-relatorio-executivo` → deletar | 4 | 5 | **9** |
| `12-registro-decisoes` → `11-registro-decisoes` | 3 | 4 | **7** |
| `11-avaliacao-intervencoes` → `10-avaliacao-intervencoes` | 2 | 2 | **4** |
| `13-assessor-replanejamento` → `08-replanejamento-e-cenarios` | 0 | 1 | **1** |
| `14-explorador-cenarios` → deletar | 0 | 1 | **1** |

Além de `src/` e `tests/`, atualizar:
- **Docs** (`.md`): `README.md`, `CHANGELOG.md`, ADRs referenciando IDs, NEPs existentes,
  sprint roadmap — 15+ arquivos
- **SKILL.md**: criar/renomear para cada skill nova ou renomeada (existem hoje em 05–12)
- **Benchmark artifacts** (`.json`): gerados — atualizam automaticamente no próximo run

**Execução recomendada**: sed em lote por ID, da skill com maior número para a menor,
para evitar colisões intermediárias.

```bash
# Exemplo de ordem segura (maior → menor para evitar double-replace):
# 15 → (deletar)
# 14 → (deletar)
# 13 → 08
# 12 → 11
# 11 → 10
# 10 → 07
# 09 → (sem mudança de número)
# 08 → (deletar)
# 07 → (deletar)
# 06 → (renomear)
```

---

## Grafo de Skills Após F1–F5

```
01-escopo-e-eap
├─→ 02-produtividade-climatica → 03-catalogo-de-recursos
├─→ 04-cronograma (← 02, 03)
└─→ 05-equipes-e-alocacao (← 04, 03)
         └─→ 06-resultado-financeiro (← 05)
                    ├─→ 07-diagnostico-criticidade (← 04, 05, 06)
                    │              └─→ 08-replanejamento-e-cenarios (← 05, 06, 07)
                    └──────────────────────────────→ 09-relatorio-e-artefatos (terminal)
                                                               ↑ (← 06, 07, 08)
```

**9 skills ativas** (01–09). 10 e 11 existem como dormantes.

---

## Resumo de Impacto

| Arquivo | Tipo de Mudança | Fase |
|---|---|---|
| `09-relatorio-e-artefatos/skill.toml` | atualizar `depends_on` e `validations` | F1 |
| `09-relatorio-e-artefatos/skill.py` | incorporar lógica de 15 | F1 |
| `15-relatorio-executivo/` | deletar diretório | F1 |
| `13-replanejamento-e-cenarios/skill.toml` | criar (merge de 13+14) | F2 |
| `13-replanejamento-e-cenarios/skill.py` | criar (merge de 13+14) | F2 |
| `13-assessor-replanejamento/` | deletar diretório | F2 |
| `14-explorador-cenarios/` | deletar diretório | F2 |
| `scenarios/runner.py` | remover 11 de `ANALYSIS_SKILLS` | F3 |
| `runtime.py` | remover side effect de 12 (~linha 1774) | F3 |
| `runtime/mixins/execution.py` | remover referência a 12 (~linha 296) | F3 |
| `11-avaliacao-intervencoes/skill.toml` | marcar como dormante | F3 |
| `12-registro-decisoes/skill.toml` | marcar como dormante | F3 |
| `06-resultado-financeiro/skill.toml` | criar (merge de 06+07+08) | F4 |
| `06-resultado-financeiro/skill.py` | criar (merge de 06+07+08) | F4 |
| `06-precificacao-unitaria/` | renomear para `06-resultado-financeiro/` | F4 |
| `07-custos-indiretos/` | deletar diretório | F4 |
| `08-consolidacao-financeira/` | deletar diretório | F4 |
| `10-diagnostico-criticidade/skill.toml` | atualizar `depends_on` para `06-resultado-financeiro` | F4 |
| `13-replanejamento-e-cenarios/skill.toml` | atualizar `depends_on` para `06-resultado-financeiro` | F4 |
| `09-relatorio-e-artefatos/skill.toml` | atualizar `depends_on` para `06-resultado-financeiro` | F4 |

| `10-diagnostico-criticidade/` → `07-diagnostico-criticidade/` | renomear diretório + ID | F5 |
| `08-replanejamento-e-cenarios/` | renomear de `13-` após merge F2 | F5 |
| `11-avaliacao-intervencoes/` → `10-avaliacao-intervencoes/` | renomear diretório + ID | F5 |
| `12-registro-decisoes/` → `11-registro-decisoes/` | renomear diretório + ID | F5 |
| `src/**/*.py`, `tests/**/*.py` | substituir ~136 strings de skill ID | F5 |
| `docs/**/*.md` | atualizar referências a IDs em ADRs, NEPs, README | F5 |
| `SKILL.md` de 06, 07, 08 | criar `06-resultado-financeiro/SKILL.md` | F5 |
| `SKILL.md` de 10, 13 | renomear/criar para 07 e 08 | F5 |

**Sem mudança em**: runtime side effects de 09 (`_handle_skill_09_side_effects`),
estrutura de validações, modelo canônico (`canonical.py`), skills 01–05.

---

## Checklist de Implementação

- [ ] **F1a**: Atualizar `09/skill.toml` — novos `depends_on` e `validations`
- [ ] **F1b**: Incorporar lógica de `15/skill.py` em `09/skill.py`
- [ ] **F1c**: Verificar que `canonical.relatorio_executivo` continua populado após merge
- [ ] **F1d**: Deletar `15-relatorio-executivo/`
- [ ] **F2a**: Criar `13-replanejamento-e-cenarios/skill.toml`
- [ ] **F2b**: Criar `13-replanejamento-e-cenarios/skill.py` (merge de 13 + 14)
- [ ] **F2c**: Confirmar que `canonical.replan_suggestions` e `canonical.plan_space_result` seguem populados
- [ ] **F2d**: Deletar `13-assessor-replanejamento/` e `14-explorador-cenarios/`
- [ ] **F2e**: Atualizar `depends_on` em `09/skill.toml` para `13-replanejamento-e-cenarios`
- [ ] **F3a**: Remover `"11-avaliacao-intervencoes"` de `ANALYSIS_SKILLS` em `runner.py`
- [ ] **F3b**: Remover side effect de `12` em `runtime.py` e `execution.py`
- [ ] **F3c**: Adicionar `status = "dormante"` nos `skill.toml` de 11 e 12
- [ ] **F4a**: Criar `06-resultado-financeiro/skill.toml` (merge de 06+07+08)
- [ ] **F4b**: Criar `06-resultado-financeiro/skill.py` incorporando lógica de 06, 07 e 08
- [ ] **F4c**: Confirmar que `canonical.planejamento`, `canonical.indiretos` e `canonical.resultado` seguem populados
- [ ] **F4d**: Deletar `07-custos-indiretos/` e `08-consolidacao-financeira/`
- [ ] **F4e**: Atualizar `depends_on` em 10, 13-replanejamento-e-cenarios e 09
- [ ] **F5a**: Renomear diretório `10-diagnostico-criticidade/` → `07-diagnostico-criticidade/`; atualizar `id` no skill.toml e SKILL.md
- [ ] **F5b**: Renomear diretório merged `13-…/` → `08-replanejamento-e-cenarios/`; atualizar ID
- [ ] **F5c**: Renomear `11-avaliacao-intervencoes/` → `10-avaliacao-intervencoes/`
- [ ] **F5d**: Renomear `12-registro-decisoes/` → `11-registro-decisoes/`
- [ ] **F5e**: Substituir strings de skill ID em `src/` e `tests/` (~136 ocorrências) — usar sed em ordem decrescente de número para evitar colisões
- [ ] **F5f**: Atualizar referências a IDs em docs (ADRs, NEPs, README, CHANGELOG, sprint roadmap)
- [ ] **F5g**: Criar `06-resultado-financeiro/SKILL.md`; criar/renomear SKILL.md de 07 e 08
- [ ] **Regressão**: rodar benchmarks completos (AGIS, VALE, ODFJELL) — resultados idênticos
- [ ] **Atualizar INDEX.md** de NEPs

---

## Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| `relatorio_executivo` ausente após merge de 09+15 | 15% | M | Manter campo canônico + teste de regressão |
| Trigger condicional de 13 perdido na skill unificada | 10% | B | Lógica de trigger internalizada no skill.py |
| Referência a 14 em test fixtures ou benchmark specs | 20% | B | Grep por `14-explorador` antes de deletar |
| ADR-070 implementado antes de 11/12 serem removidos | 30% | B | Fase 3 é prerequisito para ADR-070, não bloqueante |
| `canonical.indiretos` ausente após merge de 06+07+08 | 15% | M | Manter seção canônica separada + teste de regressão |
| Referência a `08-consolidacao-financeira` em test fixtures | 25% | B | Grep por `08-consolid` antes de deletar |

---

## Relação com ADR-070

ADR-070 propõe `GoResearchCampaignBundle` — campanha de pesquisa determinística com Pareto
multi-espaço. Quando implementado:

- **13-replanejamento-e-cenarios** (skill unificada desta NEP) será a versão simplificada do
  motor de busca — reparo greedy e scan de oportunidades como heurística rápida.
- **ADR-070** adicionará uma skill dedicada de exploração sistemática (campaign engine)
  acima de 13, consumindo seu output como baseline de comparação.
- **11** ressurgirá como etapa de avaliação ROI×Effort sobre o shortlist Pareto de ADR-070.
- **12** ressurgirá como commit formal de um cenário selecionado da campanha.

Esta NEP não bloqueia ADR-070 — limpa o terreno para ele.
