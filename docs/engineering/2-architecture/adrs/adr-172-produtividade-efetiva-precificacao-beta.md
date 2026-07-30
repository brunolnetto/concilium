# ADR-172 — Produtividade Efetiva de Precificação (β_i)

**Status:** ✅ Implementado
**Data:** 2026-07-29
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-060 (Diagnóstico de Ponto de Equilíbrio), ADR-061 (Inversão/Backtracking de PE), ADR-068 (separação clima/calendário), ADR-124 (separação planejamento vs. controle), ADR-148 (ineficiência horária diária), ADR-162 (decomposição causal cronograma × precificação), NEP-032 (precificação bottom-up), NEP-035 (decomposição causal η = η_s·η_p·η_w)

---

## Contexto

### Problema

P1. Discussão com stakeholder (29/07) sobre o Painel de Ajuste de Ponto de Equilíbrio: a proposta original dele era reajustar reativamente o preço unitário `p^u_i` por um fator `α`, aplicado manualmente sempre que o delta de equilíbrio (`Δ_i`) aparecesse positivo (déficit), recalculado até o cronograma "passar" no check `0 < Δ_i < Γ`.

P2. Investigação matemática (mesma sessão) provou que essa reatividade é sintoma de uma inconsistência estrutural, não uma coincidência de um projeto específico. Partindo da formalização do ADR-162 (P1):

```
Δ_i = p^u_i·Q_i − γ_i·h·d·Σⱼ₌₁ᴺⁱ m_ij
```

com `p^u_i = γ_i/ρ_i` (catálogo, NEP-032) e `Q_i = Σⱼ q_ij`, `q_ij = ρ_i·h·ηₚ,ⱼ·d·m_ij` (produção da semana `j`, onde `ηₚ,ⱼ = fator_clima_j × fator_calendario_j × fator_jornada` é a **praticabilidade** da semana — NEP-035/ADR-124), a substituição cancela `ρ_i` exatamente:

```
Δ_i = γ_i·h·d · Σⱼ m_ij·(ηₚ,ⱼ − 1)
```

Como `fator_clima`, `fator_calendario` e `fator_jornada` são clampados em `[0,1]` em todo o código (`_calendario.py:94`, `_custos.py:333,340`, `_custos.py:322` — ADR-148), o produto `ηₚ,ⱼ ≤ 1` sempre, e portanto `Δ_i ≤ 0` **sempre**, com igualdade só na execução ideal (`ηₚ,ⱼ=1` em toda semana ativa). Isso não é um risco a diagnosticar — é uma certeza matemática enquanto o preço for calculado com produtividade catalogada pura (`ρ_i`) e o custo já assumir a praticabilidade planejada (`ηₚ`) que a skill 04 usa para montar o cronograma (`_lookup_eficiencia` sobre tabelas `prat_semanal`/`prat_mensal`).

P3. O BDI (`ComponentesBdi`) tem um componente nomeado exatamente para esse propósito — `cr` ("contingência de risco") — mas a tabela default (`DEFAULT_BDI_TABELA`, `_components.py:151`) tem `cr=0.000`. O buffer efetivo hoje contra essa lacuna estrutural vem inteiramente de `l` (lucro, 9%) e `ac` (administração central, 5%) — dando um BDI total ≈29,96% (mão de obra/serviços), suficiente só enquanto a eficiência média ponderada do cronograma (`ε̄ = Σⱼ ηₚ,ⱼ·m_ij / Σⱼ m_ij`) não cair abaixo de `1/1,2996 ≈ 76,9%`. Abaixo disso, o projeto está consumindo lucro direto para cobrir uma lacuna que deveria estar coberta por uma reserva dedicada.

P4. Calibrar `cr` via loss-ratio (`Σ déficits / Σ base de venda`) é o mecanismo correto para risco **genuíno** (desvios imprevistos entre projetos, correlacionados serialmente, precisando de dados históricos multi-projeto para um quantil de confiança válido) — mas não serve para a parcela **determinística e já conhecida** da ineficiência: a skill 04, ao montar o cronograma, já sabe (via tabela) qual `ηₚ,ⱼ` está assumindo, semana a semana, para este item, neste projeto. Essa parcela não precisa de estatística nem de histórico entre projetos — precisa só que o preço leia o mesmo dado que o custo já lê.

### Nota de escopo — η_p, não η completo

NEP-035 decompõe `η = η_s · η_p · η_w`. ADR-124 já separa isso em "aplicável agora" vs. "fase futura":

```
η_plan    = η_p = fator_clima · fator_calendario · fator_jornada   (planejamento — aplicável agora)
η_control = η_s · η_plan · η_w                                      (controle — fase futura, requer dado de execução real)
```

`η_s` (alocação: `n_j/n_max`) e `η_w` (gestão: produção real/capacidade) são rotulados explicitamente como fatores de **controle**, sem significado diagnóstico no planejamento (`_eap.py:114-138`). Esta ADR usa **somente `η_p`** — os três fatores que o stakeholder nomeou (feriados = `fator_calendario`, ineficiência diária = `fator_jornada`, praticabilidade = `fator_clima`), já existentes e já calculados por semana em `DistribuicaoSemanal.eta_p` (`_custos.py:334,356`).

---

## Decisão

D1. Calcular, na precificação (skill 06 `_precificacao`, antes de o Ponto de Equilíbrio existir), um fator `β_i` por item de EAP:

```
β_i = Σⱼ(ηₚ,ⱼ · m_ij) / Σⱼ m_ij      (ponderado por num_equipes, só sobre semanas ativas)
```

usando o cronograma **já construído** para aquele item — `06-resultado-financeiro` depende de `05-equipes-e-alocacao`, que depende de `04-cronograma` (`skill.toml`), então `canonical_in.cronograma.scheduled_activities[i].distribuicao_semanal` já existe no momento em que a precificação roda, no mesmo passe de pipeline.

D2. A produtividade efetiva de precificação passa a ser `ρ_i · β_i` (equivalente a dividir `preco_cat` por `β_i`, já que `preco_cat = custo_categoria_h / ρ_i` é onde a divisão por produtividade acontece hoje — `pu_calculator.py:530-534`, `derivar_precos_unitarios_sbdi`). `β_i` é aplicado uma vez, no ponto de precificação já existente, sem re-rodar o cronograma e sem iteração.

D3. `β_i` é exposto como campo novo e independente — `Planejamento.beta_praticabilidade` — mantendo `produtividade_catalogo` (ADR-162 D1, `ρ_i` puro) intocado como referência estrutural. Nenhum dos dois se sobrescreve; ambos ficam auditáveis lado a lado.

D4. Fallback `β_i = 1.0` (sem correção) quando o cronograma do item não está disponível (item sem `ScheduledActivityCanonical` correspondente) ou não há semanas ativas — mesma filosofia de "nunca inventar um valor" do `causa_dominante` (ADR-162 D1): ausência de dado não vira um número arbitrário.

D5. `ρ_i` do catálogo mestre **nunca é sobrescrito**. `β_i` é específico do cronograma deste item, neste projeto, nesta rodada de pipeline — recalculado do zero a cada execução, nunca persistido de volta ao catálogo.

### D6 — Achado durante a verificação: `delta` também subestimava o custo em itens multi-frente (`EquipeDireta.custo_operacional_agregado`)

**Nota de implementação (29/07, mesma sessão).** Ao verificar D1-D5 contra o benchmark AGIS, `PontoEquilibrio.delta` (todos os itens com `num_equipes_base > 1`) ficou desproporcionalmente positivo (`delta_pct` de 250% a 565%, escalando quase exatamente com `num_equipes_base`) — um problema **pré-existente**, não introduzido por D1-D5, só exposto porque β_i corrigiu o outro lado da conta (antes, preço subestimado + custo subcontado se cancelavam parcialmente por coincidência).

Causa: `delta = custo_venda_total − custo_fixo_total`, onde `custo_venda_total = p^u_i·Q` é **agregado** (toda a quantidade do item, produzida por todas as `num_equipes_base` frentes combinadas), mas `custo_fixo_total = custo_fixo_mensal × permanencia_efetiva_meses` é uma referência de **1 frente** (nunca multiplicada por `num_equipes_base`) — convenção deliberada desde "ADR-091" para outros propósitos (`frentes_equivalentes = custo_operacional_real/custo_fixo_total`, ambos também 1-frente, ratio ≈1). Comparar um agregado (venda) contra uma referência de 1 frente (custo) subestima o lado do custo por um fator de aproximadamente `num_equipes_base`.

Uma correção óbvia (`custo_fixo_total × n_frentes`, mesmo padrão de `_pe_custo_autonomo_e_gap_pool`) foi **rejeitada**: reintroduz a mesma insensibilidade a rampa que a Fase 3 do ADR-162 (D4) já tinha eliminado de `permanencia_efetiva_meses` — multiplicar por uma constante nominal `n_frentes` não reconstrói corretamente o agregado quando o número de equipes varia semana a semana.

A correção certa: `EquipeDireta.custo_operacional_agregado` (novo campo) — a integral semana a semana do custo (mão de obra + equipamentos + diesel × `num_equipes` daquela semana, todas as frentes, sem idle/mob-desmob), calculada em `_calc_custo_cron` (skill 05) e **já existia** como valor descartado (`_sum_eq_weeks_and_cron_cost`, renomeado de `_custo_total` para `custo_operacional_agregado` — era prefixado como não-usado desde a correção D4 do ADR-162, que só precisava de `_sum_1frente_cost`). Robusto a rampa por construção, porque soma `num_equipes` real por semana, nunca uma constante nominal.

`_build_pe_for_equipe` passa a usar `custo_operacional_agregado` (com fallback em cascata: `custo_operacional_real × n_frentes` nominal, depois `custo_fixo_total`, garantindo que `delta_pct` nunca divida por zero) para `delta`, `causa_dominante` (D1 do ADR-162, `γ_i^o`) e `horas_reais_min`/`max` (D3 do ADR-162) — todos comparavam contra quantidades agregadas (`custo_venda_total`, `H_i` via `machine_weeks_brutas`) e agora usam um custo também agregado. `frentes_equivalentes`/`gap_escala_abs` continuam na base de 1 frente (`custo_fixo_total`, variável local) — propósito diferente (produtividade real vs. referência), não afetado.

Verificado contra AGIS: `delta_pct` deixa de escalar com `num_equipes_base` (antes: eap-1_0 com 6 frentes = 565%, eap-1_6 com 4 frentes = 331%; depois: 14,3% e 49,7% respectivamente, sem correlação com a contagem de frentes) e `causa_dominante` passa a mostrar uma distribuição real entre PRECIFICACAO/CRONOGRAMA/MISTO (antes, quase todo item caía em PRECIFICACAO, um sintoma do próprio mismatch de escala).

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Fator `α` reativo sobre `p^u_i`, aplicado manualmente após observar `Δ_i` negativo (proposta original do stakeholder) | Desleal ao pipeline idempotente de construção do cronograma — normaliza "ajustar e re-rodar até passar" como prática operacional; se persistido, contamina o catálogo (`ρ_i` estrutural absorvendo ruído operacional de uma execução específica) |
| A2 | Calibrar `cr` (BDI) via loss-ratio entre múltiplos projetos históricos | Correto para risco genuíno (desvio imprevisto, correlacionado serialmente, exige quantil de confiança sobre histórico multi-projeto) — mas a parcela que domina o problema hoje é **conhecida e determinística** dentro do próprio projeto (a skill 04 já assume `ηₚ<1` ao planejar); não precisa de dado entre-projetos. Mantido como trabalho futuro para a parcela residual de risco genuíno que sobra depois de `β_i` |
| A3 | Usar `η` completo (`η_s·η_p·η_w`), não só `η_p` | `η_s`/`η_w` são fatores de CONTROLE (ADR-124), sem significado no planejamento — dependem de dado de execução que não existe neste sistema (Concilium é ferramenta de estimativa/orçamento, não de acompanhamento de campo) |
| A4 | Escrever `ρ_i·β_i` de volta no catálogo mestre como nova produtividade "calibrada" | Mesma contaminação estrutural do A1 — `β_i` é uma propriedade do cronograma deste projeto, não do CPU em geral |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Preço consistente com custo | Preço e custo passam a ler a mesma praticabilidade planejada (`ηₚ`) — hoje só o custo lê |
| `Δ_i` deixa de ser estruturalmente negativo | `Δ_i` (sem_bdi) passa a refletir desvio genuíno entre planejado e realizado, não mais a lacuna matemática entre preço idealizado e custo realista — devolve ao `causa_dominante` (ADR-162 D1) seu significado diagnóstico original |
| Não contamina catálogo, não é reativo | `β_i` é calculado prospectivamente, de dado que a skill 04 já produziu, no mesmo passe — nenhuma iteração, nenhuma escrita de volta ao catálogo |
| `cr` do BDI fica mais legível | Depois de `β_i` absorver a parcela conhecida, o que sobrar para `cr` cobrir é, de fato, risco genuíno — parcela menor, mais fácil de calibrar com dado histórico real |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Muda o preço de venda (`subtotal.sem_bdi`) de praticamente todo item em todo projeto — mudança de alto impacto financeiro | Verificação numérica obrigatória contra o benchmark AGIS antes de mergear; `beta_praticabilidade` exposto explicitamente no relatório para auditoria imediata da correção aplicada |
| Pode exigir recalibração do GOLDEN (`test_golden_evaluation.py`) | Mesmo padrão já usado após ADR-165→171 — atualizar baseline com histórico documentado no próprio teste, não silenciosamente |
| `β_i` = 1.0 no fallback pode mascarar itens sem cronograma associado | `β_i=1.0` é neutro (sem correção), não um valor otimista — item cai de volta no comportamento pré-ADR-172, nunca pior |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `Planejamento.beta_praticabilidade`; helper de agregação ponderada (`_resolve_beta_praticabilidade`); threading `_process_eap_items → _process_eap_item → _resolve_preco_cat_item → _compute_preco_cat_from_production`; aplicação em `preco_cat` | ✅ Implementado |
| F2 | Testes dedicados (agregação ponderada, fallback, integração fim-a-fim) | ✅ Implementado |
| F3 | Verificação contra benchmark AGIS; recalibração do GOLDEN se necessário | ✅ Implementado (GOLDEN não precisou recalibrar — nenhum item do fixture usa Fonte 1/bottom-up) |
| F3.5 | D6 — `EquipeDireta.custo_operacional_agregado` (achado durante F3); corrige `delta`/`causa_dominante`/`horas_reais_min_max` para base agregada consistente com `custo_venda_total` | ✅ Implementado |
| F4 (futura) | Recalibração de `cr` (BDI) para a parcela residual de risco genuíno, via loss-ratio entre projetos (condicionada a histórico multi-projeto) | ⬜ (fora de escopo desta ADR) |

## Definition of Done

### Fase 1
- [x] `beta_praticabilidade: float = 1.0` em `Planejamento`
- [x] `_resolve_beta_praticabilidade(item_id, sched_por_item) -> float` — média ponderada por `num_equipes`, só semanas ativas, usa `DistribuicaoSemanal.eta_p` já existente
- [x] Fallback `1.0` quando item sem cronograma ou sem semanas ativas — nunca um valor inventado
- [x] `produtividade_catalogo` (ADR-162 D1) permanece intocado — `β_i` é campo novo, separado
- [x] `ρ_i` do catálogo mestre nunca é sobrescrito

### Fase 2
- [x] Teste prova `β_i=1.0` quando `ηₚ,ⱼ=1` em toda semana ativa (caso ideal, sem correção)
- [x] Teste prova `β_i` correto sob praticabilidade variável semana a semana, ponderado por `num_equipes` (não média simples)
- [x] Teste prova fallback `1.0` sem cronograma, item sem schedule, ou sem semanas ativas
- [x] Teste de integração prova que `preco_cat` reflete a divisão por `β_i` só na Fonte 1 (bottom-up); Fonte 2 sempre `β_i=1.0`
- [x] Teste prova `produtividade_catalogo`/`beta_praticabilidade` são campos independentes em `_build_planejamento_entry`

### Fase 3
- [x] Suíte completa sem regressão (14906 passed)
- [x] Benchmark AGIS: `β_i` verificado (0,875–0,938 nos 11 itens); `Δ_i` deixa de ser estruturalmente negativo
- [x] GOLDEN: sem itens usando precificação bottom-up (Fonte 1) — `β_i=1.0` em todos, nenhuma recalibração necessária

### Fase 3.5 (D6)
- [x] `EquipeDireta.custo_operacional_agregado` — integral semana a semana (`_calc_custo_cron`, já calculado, antes descartado), robusto a rampa por construção
- [x] `_build_pe_for_equipe` usa `custo_operacional_agregado` (com fallback em cascata, nunca ZeroDivisionError) para `delta`/`causa_dominante`/`horas_reais_min_max`
- [x] `frentes_equivalentes`/`gap_escala_abs` continuam na base de 1 frente — não afetados (teste dedicado prova isso explicitamente)
- [x] Invariante `delta == custo_venda_cpu − custo_fixo_equipe` (campo reportado) testado explicitamente
- [x] Verificado contra AGIS: `delta_pct` deixa de escalar com `num_equipes_base` (565%/331% → 14,3%/49,7%, sem correlação com contagem de frentes)
- [x] Suíte completa sem regressão após D6 (14906 passed; integração 117 passed)

---

## Relacionados

- ADR-060/061 — Diagnóstico e Backtracking de Ponto de Equilíbrio
- ADR-068 — Separação clima/calendário (`fator_clima`/`fator_calendario`)
- ADR-124 — Separação planejamento vs. controle (`η_plan` vs. `η_control`)
- ADR-148 — `fator_jornada` (ineficiência horária diária)
- ADR-162 — Decomposição causal cronograma × precificação (`causa_dominante`) — `β_i` restaura o significado diagnóstico de `Δ_i` que essa ADR pressupõe; D6 corrige um mismatch de escala (agregado vs. 1 frente) no próprio `delta`/`γ_i^o` que essa ADR consome; D4 (ADR-162 Fase 3) é o precedente direto de "não multiplicar por `n_frentes` nominal, usar integral semana a semana"
- NEP-032 — Precificação bottom-up (`p^u_i = γ_i/ρ_i`)
- NEP-035 — Decomposição causal `η = η_s·η_p·η_w`
