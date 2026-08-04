# ADR-179 — Similaridade Determinística de Insumos para Detecção de Duplicatas

**Status:** ⚠️ Parcialmente Implementado _(Nível 1 — insumo ✅; Níveis 2/3 — produção/CPU, propostos)_
**Data:** 2026-08-04
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-178 (Gate de Plausibilidade Pré-Merge de Catálogo)

---

## Contexto

### Problema

P1. **O dedup de mão de obra hoje é por igualdade exata, não por similaridade.** `_pc_mo_duplicatas` (`_plausibility_checks.py`) e `_build_dup_map` (`cure_plausibility.py`) só marcam duplicata quando `(descrição normalizada, preço)` são **idênticos**. O usuário pediu, ao investigar a ADR-178, uma forma determinística de comparar `cpus → produtividade → {mao_obra, equipamentos, materiais}` par a par para achar similaridades — sinalizando consciência de que isso é um problema `O(n²)` (n(n-1)/2 comparações).

P2. **Achado que motivou a proposta**: `P0058` ("Sala Técnica", R$24.720/mês, import AGIS com encargos embutidos) e `MO-SALA-TEC` ("Sala Técnica", R$12.000/mês, salário-base ADR-009-normalizado) são a mesma função, mas o dedup exato nunca os junta — os preços diferem por um fator ≈ α de encargos (2,06), não são iguais.

P3. **Ao validar a primeira versão do score contra o catálogo `mendeslobo` real** (593 insumos, 285 MAO_OBRA), Dice não-ponderado sobre tokens de descrição gerou falso-positivo sistemático: pares como "Encarregado de Frente" (R$7.500) × "Encarregado de Obras" (R$3.737,80) — cargos genuinamente distintos — pontuavam alto só por compartilharem a palavra genérica "Encarregado", combinado com a razão de preço (2,006x) caindo por coincidência na faixa ampla de α [1,0–2,5] (que cobre boa parte de qualquer folha de pagamento real, não é um sinal discriminante por si só quando a descrição é fraca). Rodada inicial: 236 candidatos no `mendeslobo` (vs. 25 conhecidos), a maioria ruído.

P4. `O(n²)` não é o problema real de performance na escala atual (~800 insumos, ~250 produções — `n²` fica na casa de centenas de milhares de comparações, trivial). O problema é a métrica: uma similaridade mal calibrada gera ruído que nenhuma quantidade de otimização de performance resolve.

## Decisão

D1. **Score determinístico em 3 componentes, sem ML/embeddings/aleatoriedade**: `score = 0,75·desc_sim + 0,20·price_sim + 0,05·categoria_sim` (constantes em `domain/constants.py`, `SIMILARIDADE_PESO_*`). Descrição domina deliberadamente — preço sozinho nunca deve arrastar um par de score alto quando a descrição é fraca (fecha P3).

D2. **`desc_sim` é Dice ponderado por IDF**, não Dice simples. Tokens de conteúdo (stopwords pt-BR removidas — `de/da/do/e/em/com/para/...`) pesados por `idf(t) = ln((1+N)/(1+df(t))) + 1` (fórmula suavizada padrão, mesma de `TfidfVectorizer(smooth_idf=True)` — determinística, só estatística de corpus, sem aprendizado). Palavra em quase toda descrição ("operador", "auxiliar", "encarregado") pesa próximo do mínimo; palavra rara ("valetadeira", "motosserra") pesa perto do máximo. Isso é o que resolveu P3: validado contra o mesmo par real, "Encarregado de Frente" × "Encarregado de Obras" deixou de ultrapassar o piso de classificação.

D3. **`price_sim` combina duas hipóteses**: (a) preços diretamente próximos (`SIMILARIDADE_TOL_PRECO_DIRETO`, 15% — ruído de arredondamento/import) e (b) razão de preço compatível com a faixa de α de encargos (`ALPHA_MIN_ENCARGOS..ALPHA_MAX_ENCARGOS`, decai conforme se afasta de `ALPHA_CLT_TIPICO`=1,777) — mas (b) **só é considerada se `desc_sim ≥ SIMILARIDADE_DESC_MIN_HIPOTESE_ENCARGOS` (0,6)**. Sem esse gate, qualquer par de salários "normais" cai na faixa de α por coincidência (fecha P3 pela segunda metade — descrição fraca não é resgatada por preço).

D4. **Curto-circuito de referência declarada**: se `codigo_referencia_externa` de um insumo já lista o código do outro, score=1,0 direto (absorve o que o dedup antigo já sabia fazer, sem recomputar).

D5. ***Blocking* por `tipo`** (MAO_OBRA/EQUIPAMENTO/MATERIAL nunca comparados entre si) reduz o universo de comparação por bloco; dentro do bloco, o IDF é construído sobre as descrições daquele bloco especificamente (não do catálogo inteiro) — mantém o peso de palavra relevante ao vocabulário do bloco.

D6. **`_pc_mo_duplicatas` upgradeado** para usar `insumo_similarity`/`build_idf` em vez do match exato — mantém a semântica "estrela" (cada duplicata aponta para o primeiro item da lista com o qual casou, não encadeado) e a severidade `AVISO`, agora com `score`/`classificacao`/`desc_sim`/`price_sim` no `detalhe` para auditoria.

D7. **Duas classificações**: `score ≥ 0,80` → `duplicata_provavel` (alta confiança); `0,55 ≤ score < 0,80` → `revisar` (sinal fraco, precisa de julgamento humano); `< 0,55` → não relacionado. Nunca funde automaticamente — mesma decisão da ADR-178 A3 (não fundir os 25 duplicados sem revisão humana).

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Embeddings/similaridade semântica via modelo de linguagem | Rejeitada — quebra o requisito de determinismo (mesma entrada, mesma saída, sem dependência de modelo externo/versão); auditoria de merge de catálogo exige score explicável e reproduzível linha a linha. |
| A2 | Dice não-ponderado (v1 desta ADR) | Rejeitada após validação contra dado real (P3) — gera falso-positivo sistemático entre papéis distintos que compartilham palavra-tipo genérica. |
| A3 | Hipótese de encargos sem gate de `desc_sim` (v1) | Rejeitada — qualquer par de salários "normais" cai na faixa ampla de α por coincidência; preço nunca deve resgatar uma descrição fraca. |
| A4 | Implementar Níveis 2 (produção) e 3 (CPU) nesta mesma passada | Rejeitada por escopo (decisão do usuário) — Nível 1 (insumo) já é o mecanismo concreto que resolve o caso motivador (P2) e upgrada `_pc_mo_duplicatas`; Níveis 2/3 (Jaccard de recursos canonicalizados + cosseno de quantidade + melhor-par de produções) ficam propostos para uma fase seguinte. |
| A5 | Expor como novo modo em `auditar_catalogo` (`modo="similaridade"`) | Rejeitada por escopo nesta passada (decisão do usuário) — integração via upgrade de `_pc_mo_duplicatas` já expõe o resultado em qualquer chamada existente de `auditar_catalogo(modo="plausibilidade")`, sem nova superfície de tool. |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Fecha o caso motivador | `P0058`/`MO-SALA-TEC` agora são detectados (`duplicata_provavel`, score 0,937). |
| Achado de escala maior que o esperado | Validado contra `mendeslobo` real: ~73 pares de alta confiança (vs. 25 conhecidos antes) — revela um padrão sistemático de fator de encargos (~2,06x) espalhado por dezenas de papéis nunca linkados via `codigo_referencia_externa` nem capturados pelo match exato (ex.: `MO-ENCARREG-DREN`/`P0020`/`MO-P0020`, `MO-AUX-LAB`/`P0009`, `MO-OPER-RETRO`/`P0044`). |
| Reaproveitável fora de MAO_OBRA | `insumo_similarity`/`find_candidate_duplicates` são genéricos por `tipo` — EQUIPAMENTO/MATERIAL podem usar o mesmo motor quando alguém precisar (não wireado ainda, fora de escopo). |
| Explicável | Cada score carrega `desc_sim`/`price_sim`/`categoria_sim` — qualquer classificação é auditável linha a linha, sem caixa-preta. |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| 200 candidatos no `mendeslobo` (73 alta confiança + 127 revisar) é bastante para revisão manual | Aceito — severidade continua `AVISO` (não bloqueia nada hoje); `classificacao`/`score` no `detalhe` permitem triagem por confiança. Revisar em lote fica para o usuário decidir prioridade. |
| Pesos (0,75/0,20/0,05) e thresholds (0,80/0,55) são escolhas de engenharia, não derivados estatisticamente | Documentados como constantes centralizadas (`domain/constants.py`) — fáceis de re-tunar; validados contra dado real desta sessão, não só contra fixtures sintéticas. |
| `_pc_mo_duplicatas` agora é O(n²) em vez de O(n) — para 285 itens, ~40k comparações, trivial; não teria escalado bem para um catálogo de 10k+ MAO_OBRA sem *blocking* adicional | Aceito por ora — *blocking* por `tipo` já reduz o universo; se a escala crescer 10x+, *blocking* secundário por token-prefixo da descrição é a extensão natural (documentado, não implementado). |
| Materiais com `unidade` física diferente (m³ vs kg vs t) não são comparáveis por preço — `insumo_similarity` não trata isso hoje (só testado para MAO_OBRA) | Fora de escopo desta fase — quando EQUIPAMENTO/MATERIAL forem wireados, `_price_sim` precisa checar `unidade` igual antes de comparar preço de MATERIAL. |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `similarity.py` — `insumo_similarity`/`build_idf`/`find_candidate_duplicates` (Nível 1) | ✅ |
| F2 | Upgrade de `_pc_mo_duplicatas` para usar o motor de similaridade | ✅ |
| F3 | Nível 2 — similaridade de produção (Jaccard de recursos canonicalizados + cosseno de quantidade + proximidade de `valor_horario`, *blocking* por `categoria`) | ⬜ |
| F4 | Nível 3 — similaridade de CPU (melhor par de produções entre duas CPUs) | ⬜ |
| F5 | Novo modo `auditar_catalogo(modo="similaridade")` expondo o relatório cross-catálogo explicitamente | ⬜ |

## Definition of Done

### Fase 1-2
- [x] `insumo_similarity`/`find_candidate_duplicates` implementados com IDF ponderado
- [x] Teste de regressão do caso motivador (`P0058`/`MO-SALA-TEC`)
- [x] Teste de regressão do falso-positivo achado ao validar (palavra genérica + faixa de α)
- [x] `_pc_mo_duplicatas` upgradeado, mantendo semântica "estrela" e severidade `AVISO`
- [x] Suíte completa verde (14.8xx testes, sem regressão)

### Fase 3-5
- [ ] Similaridade de produção implementada e testada
- [ ] Similaridade de CPU implementada e testada
- [ ] `modo="similaridade"` exposto em `auditar_catalogo`

## Nota de Implementação

Validação contra dado real do `mendeslobo` foi parte do processo de design, não só verificação pós-hoc — a primeira versão (Dice não-ponderado, sem gate de `desc_sim` na hipótese de encargos) gerou 236 candidatos, a maioria falso-positivo; a versão com IDF + gate reduziu para 200, mas a composição mudou qualitativamente: a maior parte dos 73 "duplicata_provavel" são achados novos e prováveis (padrão de fator de encargos ~2,06x repetido em dezenas de pares), não ruído. Isso foi confirmado inspecionando manualmente uma amostra de ~20 pares nos dois extremos (score alto e score próximo do piso de "revisar").

`domain/constants.py` ganhou `ALPHA_CLT_TIPICO` (extraído do `ALPHA_CLT` que já existia hardcoded em `cure_plausibility.py`, agora centralizado) e a seção `SIMILARIDADE_*`.

---

## Relacionados

- ADR-178 — Gate de Plausibilidade Pré-Merge de Catálogo (este motor é o candidato natural para substituir/reforçar a checagem de duplicata elevada a `ERRO` no contexto de pré-merge, D5 daquela ADR — não wireado ainda, fica para quando F1-F5 da ADR-178 forem implementadas)
- Achado desta sessão — bug de `unidade` em `_pc_mo_salario_minimo`/`_pc_mo_zscore` (mesma sessão, ver `adr178-bug-checker-plausibilidade-unidade-e-gate-pre-merge` na memória do agente)
