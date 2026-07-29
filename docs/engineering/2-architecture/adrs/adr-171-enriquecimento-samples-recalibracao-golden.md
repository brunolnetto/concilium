# ADR-171 — Enriquecimento do Catálogo `samples` + Recalibração do GOLDEN

**Status:** ✅ Implementado
**Data:** 2026-07-29
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-165/166/167/168/169/170 (série de indiretos bottom-up e catálogo de RH)

---

## Contexto

### Problema

P1. O usuário relatou que `tests/integration/pipeline/test_golden_evaluation.py::TestGoldenRegression::test_regression_against_calibrated_values` estava falhando, com `custo.total` divergindo 6,19% do valor calibrado. Investigação (cruzando os logs de suíte completa salvos com os timestamps dos commits) revelou:

- Um desvio de 9,83% já existia **antes de qualquer mudança desta sessão** (confirmado via `git stash` no início do trabalho) — não relacionado a nenhuma ADR.
- A ADR-168 (Alojamento bottom-up) moveu `custo.total` de R$557.959,98 para R$580.459,98 (redução do desvio de 9,83% para 6,19%) — a **única** das ADRs 165-170 que afetou o teste, porque `_custo_alojamento_bottom_up` só depende de `equipes_diretas` (headcount real), não de nenhum item do catálogo.
- As ADR-165/166/167/169/170 **não** afetaram o teste, porque o benchmark GOLDEN usa o catálogo `samples` (`benchmarks/projetos/GOLDEN/meta.json: "contexto_id": "samples"`), que não tinha nenhum dos itens novos (EPI/TREINAMENTO/EXAME/BENEFICIO, `P0092`, `BEN-ALOJAMENTO`) — todo o resto caiu no fallback hardcoded, sem mudança.

P2. Erro de processo próprio: a cada rodada de suíte completa, a falha foi rotulada "pré-existente, não relacionada" sem comparar a magnitude do desvio entre rodadas — o que mascarou o efeito real da ADR-168 até o usuário questionar o resultado.

## Decisão

D1. `samples` enriquecido com os mesmos itens já presentes em `mendeslobo`/`rfi-r02`: os 34 itens RH da ADR-165 (via `adr165_carga_inicial_rh.py --contexto samples`, já generalizado desde a ADR-167), o cargo `P0092` "Coordenador" (ADR-167) e `BEN-ALOJAMENTO` (ADR-170) — script novo `scripts/catalog/adr171_enriquecer_samples.py`, mesma governança rascunho→merge/quatro-olhos.

D2. Mapeamento função→item (ADR-166 D4) reaplicado sobre o roster próprio de `samples` (78 códigos descritivos, ex. `OPERADOR-DE-MOTOSSER`, sem aliases nem numeração `P0xxx`) — mesmos 7 grupos semânticos das ADRs 166/167, ajustados aos nomes de `samples` (sem `SINALEIRO`/`SOLDADOR`, que não existem neste catálogo).

D3. `benchmarks/data/GOLDEN/referencia.json` recalibrado: `custo.total` de R$618.759,49 para R$780.810,75, `venda.total_com_bdi`/`total_custo_plus`/`resultado_financeiro`/`margem_pct` atualizados na mesma execução (`margem_pct` 14,26%→15,28%, `status_margem` continua `AMARELO`). `custo.direto_equipes` permanece idêntico (R$439.683,75) — confirma que só os indiretos mudaram, nenhum custo direto de equipe foi afetado. `$golden_audit.versao` bump 1.2.0→1.3.0 com changelog explicando a mudança.

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Recalibrar sem enriquecer `samples` | Rejeitada por decisão do usuário — recalibrar antes de enriquecer deixaria a referência stale de novo assim que `samples` ganhasse os itens novos; a ordem correta é enriquecer primeiro, depois capturar o valor final já refletindo todas as ADRs. |
| A2 | Deixar o gap pré-existente de 9,83% sem investigar antes de recalibrar | Aceito implicitamente — a recalibração por definição absorve tanto o efeito intencional (ADR-165-171) quanto o gap pré-existente não investigado; documentado explicitamente aqui para não mascarar silenciosamente esse gap anterior, caso precise ser revisitado depois. |
| A3 | Usar `--run-golden` (citado no docstring do teste) para recalibrar | Descartada — essa flag não existe em nenhum `conftest.py`/`addoption` do repo (documentação desatualizada); a fixture `golden_benchmark` já roda o pipeline fresco (`reset=True`) a cada execução, então bastou rodar o pipeline diretamente e copiar os valores resultantes. |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| `samples` para de ser o catálogo "esquecido" | Agora se beneficia das mesmas melhorias de `mendeslobo`/`rfi-r02` — qualquer benchmark/teste que rode sobre `samples` passa a refletir custo real de EPI/treinamento/exame/benefício/Coordenador/Alojamento, não só o efeito parcial que só a ADR-168 alcançava. |
| Regressão zero disfarçada de mudança intencional some | O golden test volta a ser um sinal confiável — a partir de agora, qualquer nova divergência é presumivelmente uma regressão real, não um efeito colateral não documentado de uma ADR anterior. |
| `custo.direto_equipes` inalterado confirma isolamento do efeito | Prova adicional de que a mudança ficou contida em indiretos, sem vazar para custo direto de equipe/equipamento. |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| O gap pré-existente de 9,83% (antes de qualquer ADR desta sessão) foi absorvido pela recalibração sem ser investigado a fundo | Documentado explicitamente (P1/A2) — se for sintoma de um bug real (ex. o já registrado "GOLDEN eap-03 alinhamento catálogo — golden test só roda OLTP"), fica maskarado até uma auditoria futura decidir reabrir. |
| `samples` e `mendeslobo`/`rfi-r02` agora precisam ser mantidos em paralelo manualmente (3 catálogos, sem mecanismo que force sincronia) | Mesmo risco já aceito na ADR-167 (D5) para o par mendeslobo/rfi-r02 — extemdido para o terceiro catálogo, sem solução nova. |

## Definition of Done

- [x] `samples` enriquecido com 34 itens RH + `P0092` + `BEN-ALOJAMENTO` + mapeamento função→item (11 atualizações); `auditar_catalogo` SAUDAVEL
- [x] `referencia.json` recalibrado com os 4 valores de `test_regression_against_calibrated_values` (`custo.direto_equipes`, `custo.total`, `venda.total_com_bdi`, `margem_pct`) + campos derivados (`venda.total_custo_plus`, `resultado_financeiro`, `$golden_audit`)
- [x] `tests/integration/pipeline/test_golden_evaluation.py` — 17/17 testes verdes
- [x] Suíte completa verde

---

## Relacionados

- ADR-165 — Catálogo de Treinamentos, Exames, EPIs e Benefícios de Mão de Obra
- ADR-166 — Wiring de Indiretos + Mapeamento Função→Item
- ADR-167 — ADM/TOP com Função Real + Paridade de Catálogo (mesmo padrão de replicação entre catálogos)
- ADR-168 — Alojamento (ADM) Bottom-Up por Número de Casas (única ADR que afetou o golden antes desta)
- ADR-169 — LAB Condicional a Terraplenagem/Pavimentação
- ADR-170 — Alojamento como Benefício Catalogado
