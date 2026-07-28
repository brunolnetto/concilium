# ADR-162 — Diagnóstico do Ponto de Equilíbrio: Decomposição Causal Cronograma × Precificação

**Status:** Proposta
**Data:** 2026-07-28
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-060 (Diagnóstico de Ponto de Equilíbrio), ADR-061 (Inversão/Backtracking de PE), ADR-076 (Calibração PU/Frentes), ADR-083 (Decomposição Causal do Gap de Pool)

---

## Contexto

### Problema

P1. **Formalização do usuário (conversa 28/07)** para o Ponto de Equilíbrio de negócios, por atividade `i`:

```
C^D_i      = custo de venda      = p_i^c · Q_i,  onde p_i^c = γ_i / ρ_i (PU catálogo)
C̃^D_i      = custo operacional   = Σ_j^{N_i} γ_i · h · d · m_ij   (base contrato semanal, N_i semanas, m_ij frentes na semana j)

Δ_i = C^D_i − C̃^D_i = γ_i · ( Q_i/ρ_i − h·d·Σ_j m_ij )

Critério racional: 0 < Δ_i < Γ
```

O piso (`Δ_i > 0`, venda cobre o operacional) **já existe** no código: `delta = custo_venda_total - custo_fixo_total` em `_build_pe_for_equipe` (`_ponto_equilibrio.py:325`), com `status_validacao = "OK" if delta >= 0 else "ERRO"` (linha 387). O teto de competitividade `Γ` **não existe** — nenhuma validação hoje limita o quão positivo `Δ_i` pode ficar. Os únicos bilaterais existentes no sistema são de outra métrica: o Semáforo de Margem (`m_alvo_min ≤ m ≤ m_alvo_max`, percentual sobre resultado/receita, `MEMORIAL_FORMULAS.md` §12.4) e o `θ_PE` legado (`Δ_pct = |C_unit,real − P_cpu|/C_unit,real > θ_PE`, 15% AGIS / 5% MendesLobo, §13) — nenhum é um teto absoluto sobre `Δ_i` por atividade.

### Nota de revisão (28/07) — correção de um argumento matemático incorreto

Uma versão anterior desta ADR afirmava que "o sinal de `Δ_i` é independente de `γ_i`" e, a partir disso, propunha rotular violação de **piso** como problema de **cronograma** e violação de **teto** como problema de **custo/precificação**. O usuário corretamente apontou a fragilidade do argumento: `Δ_i = γ_i·(...)` mostra `γ_i` como fator explícito, então chamar isso de "independência" sem qualificação era leviano.

Refazendo a conta com rigor: sob a fórmula P1 (um único `γ_i` alimentando *tanto* o preço de venda quanto o custo operacional), não é só o sinal que é invariante a `γ_i` — a **margem relativa inteira** também é:

```
Δ_i / C^D_i = 1 − (ρ_i · h · d · Σ_j m_ij) / Q_i
```

`γ_i` cancela por completo. Isso é mais forte do que "independência de sinal" e na verdade **invalida** a separação piso=cronograma / teto=custo: se `Γ` fosse percentual (preservando a mesma invariância do piso), a violação de teto seria **tão de cronograma quanto o piso** — nenhum dos dois enxergaria erro de precificação. E se `Γ` for absoluto em R$ (como D2 propõe), o que ele mede não é "preço mal calibrado", é só **escala do contrato** (`γ_i` grande = atividade cara em termos absolutos) — não um sinal de precificação errada.

Para existir de fato um modo de falha de precificação, o modelo precisa de **duas** taxas — a embutida no catálogo/venda (`γ_i^v`) e a real de execução (`γ_i^o`) — que já são, na prática, fontes distintas no código hoje: `custo_venda_total` vem do PU de catálogo; `custo_fixo_total`/`custo_operacional_real` vêm do custo real contratado da equipe. A formalização P1 com um único `γ_i` é a hipótese simplificadora "taxa de venda = taxa real"; a decisão desta ADR (D1) abandona essa hipótese e decompõe `Δ_i` nas duas taxas.

P2. **Decomposição aditiva correta (duas taxas).** Seja `H_i = h·d·Σ_j m_ij` o total de horas operacionais reais da atividade (quantidade física, vem do schedule — `n_frentes`/permanência já existentes em `_build_pe_for_equipe`, e `h`/`d` de `RegimeTrabalho`). Somando e subtraindo `γ_i^v·H_i`:

```
Δ_i = (γ_i^v/ρ_i)·Q_i − γ_i^o·H_i
    = γ_i^v·(Q_i/ρ_i − H_i)          +  (γ_i^v − γ_i^o)·H_i
    = T_cronograma                   +  T_precificacao
```

- **T_cronograma** `= γ_i^v·(Q_i/ρ_i − H_i)`: gap de capacidade/produtividade, precificado consistentemente pela taxa de venda — positivo quando o catálogo previa menos horas do que as realmente alocadas (excesso de frentes/lesão de produtividade), negativo no caso contrário.
- **T_precificacao** `= (γ_i^v − γ_i^o)·H_i`: proporcional ao **gap de taxa** ponderado pelas horas reais — positivo quando a taxa de venda excede a real (folga de margem por precificação favorável), negativo quando a taxa real excede a de catálogo (erosão por custo/encargo subestimado — mesma classe dos achados de BDI/`T_efetivo` já mapeados em `nep043-cr-reconciliacao`).

Esta decomposição, ao contrário da anterior, atribui a causa **por magnitude relativa dos dois termos**, não por qual limite (`0` ou `Γ`) foi cruzado — um estouro de piso pode ser majoritariamente `T_precificacao` (custo real muito acima do catalogado) tanto quanto majoritariamente `T_cronograma`, e o mesmo vale para um estouro de teto. A decomposição causal agregada do ADR-060 (η, clima, calendário, cross-term, quantização) continua sendo a análise de referência mais completa — esta ADR propõe um recorte mais rápido e direto, nas mesmas duas famílias de causa, sem precisar rodar o pipeline causal inteiro.

P3. **O intervalo de horas reais, reparametrizado pela taxa real (não pela taxa única).** Com `γ_i^o = custo_operacional_real / H_i` (quando `H_i > 0`), o critério `0 < Δ_i < Γ` vira diretamente um intervalo de horas reais toleradas:

```
(C^D_i − Γ) / γ_i^o  <  H_i  <  C^D_i / γ_i^o
```

equivalente, em frentes-semana, a dividir por `h·d`. Hoje o pipeline calcula `Δ_i` só *depois* de o schedule já ter sido montado (skill 06, pós skill 04/05) e reporta erro a posteriori; este intervalo poderia ser consultado *antes* de alocar frentes, como bound de planejamento por atividade — validação adicional, complementar às existentes, não uma mudança de quando o schedule roda.

P4. A formalização do usuário usa `C̃^D_i` em base **semanal explícita por frentes** (`Σ_j h·d·m_ij`). O código hoje usa base **mensal** (`equipe.custo_fixo_mensal × permanencia_base`, `_ponto_equilibrio.py:320`) — granularidade agregada, sem abrir por semana/frente. Isso é suficiente para o piso (delta agregado) e para a decomposição de P2 (que só precisa de `H_i` total, não por semana), mas insuficiente para apontar *em qual semana* um eventual estouro ocorre (ramp-up vs ramp-down) — o mesmo problema que o cross-term de timing do ADR-061 (`t0*`, minimiza `Cov(n,p)`) já resolve por outro caminho (função objetivo global, não limite por-atividade-por-semana).

---

## Decisão

Esta ADR é uma **proposta de avaliação** (worktree separada) — não implementa ainda. Define o desenho a avaliar antes de decidir se segue para `main`.

### D1 — Campo `causa_dominante`: decomposição Cronograma × Precificação, sem novo cálculo de origem

Adicionar a `PontoEquilibrio` um campo derivado `causa_dominante: Literal["CRONOGRAMA", "PRECIFICACAO", "INDETERMINADO"]`, computado sempre (não só quando `status_validacao == "ERRO"`) a partir de:

- `γ_i^v = p_i^c · ρ_i` (taxa de venda implícita, de `custo_venda_total`/`Q_i` e a produtividade de catálogo já usada em `_pe_pu_calibrado`)
- `H_i` (horas reais totais — deriva de `n_frentes`/`permanencia_base` já existentes em `_build_pe_for_equipe`, multiplicado por `h·d` do `RegimeTrabalho` do projeto)
- `γ_i^o = custo_operacional_real / H_i` (taxa real implícita, quando `H_i > 0`)

`causa_dominante = "CRONOGRAMA"` se `|T_cronograma| > |T_precificacao|`, `"PRECIFICACAO"` caso contrário, `"INDETERMINADO"` quando `H_i` não puder ser resolvido (ex.: fase de planejamento sem schedule real ainda montado — ver Riscos). Isso substitui o `causa_piso` binário da versão anterior desta ADR (que rotulava só por qual dos dois limites era cruzado, não pela causa real).

### D2 — Teto `Γ` como parâmetro configurável, com validação nova `VAL-PONTO-EQUILIBRIO-TETO` (AVISO)

`Γ` entra como campo de perfil (`config/contextos/<perfil>.json`, ao lado de `limiar_ponto_equilibrio` citado em `MEMORIAL_FORMULAS.md` §13), com fallback `None` (desabilitado) — perfis existentes não ganham um teto por default, evitando regressão silenciosa em contratos já aprovados. Quando configurado e `Δ_i ≥ Γ`, emite `VAL-PONTO-EQUILIBRIO-TETO` como AVISO (mesma filosofia não-bloqueante de todo o resto da skill 06 — ver `validador_cobertura_item.py:13-18`), nunca ERRO. Diferente da versão anterior, esta ADR **não afirma** que estourar `Γ` seja intrinsecamente um problema de preço — o campo `causa_dominante` (D1) é quem diagnostica isso caso a caso, para violação de piso ou de teto igualmente.

### D3 — Expor o intervalo de horas reais como campo informativo, não como gate de schedule

Adicionar `horas_reais_min`/`horas_reais_max` (derivados de `(C^D_i − Γ)/γ_i^o` e `C^D_i/γ_i^o`, P3) ao `PontoEquilibrio` quando `Γ` e `γ_i^o` estiverem disponíveis — informativo no relatório/UI (mesma seção EQUILIBRIO do Excel), **não** um bloqueio no momento de montar o schedule (skill 04/05). Acoplar ao RCPSP é mudança de escopo maior e fica fora desta proposta.

### D4 — Não migrar a base operacional de mensal para semanal-por-frente nesta ADR

A formalização por semana (`Σ_j m_ij`) é mais fiel para localizar em qual semana um estouro ocorre, mas migrar `custo_fixo_total` de mensal para essa forma explícita é mudança de modelo de dados maior (precisa de `m_ij` por semana, não só `n_frentes`/`H_i` agregados) que toca `_build_pe_for_equipe` e potencialmente o schedule real (ADR-152, `project_ocupacao_semanal`, que já tem granularidade semanal e poderia alimentar isso). Registrado como Fase 3 candidata (ver Plano), condicionada a essa fonte de dados semanal já existir de fato ligada ao item de EAP. Não é necessária para D1/D2/D3 — `H_i` agregado já basta para a decomposição causal.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Implementar `Γ` como ERRO bloqueante (nunca aprovar acima do teto) | Contraria a filosofia confirmada do resto da skill 06 (bloquear impediria a geração do relatório de diagnóstico); mantém o padrão AVISO com override no gate de aprovação |
| A2 | Migrar `custo_fixo_total` para base semanal por frentes já nesta ADR | Escopo maior que o pedido (mudança de modelo de dados, não só de diagnóstico); deferido para Fase 3 condicionada a fonte de dados semanal por item já existir |
| A3 | Usar o intervalo de horas reais (D3) como gate direto do solver RCPSP | Acoplaria restrição comercial ao motor de schedule; decisão de produto maior, fora do escopo de "extrair diagnóstico" que motivou esta ADR |
| A4 | Manter a atribuição de causa binária por limite cruzado (piso→cronograma, teto→custo), como na primeira versão desta ADR | **Refutada matematicamente** (ver Nota de revisão): sob taxa única, nenhuma leitura adimensional de `Δ_i` carrega informação de custo; a atribuição correta exige duas taxas (D1) e compara magnitude dos termos, não qual limite foi cruzado |
| A5 | Definir `Γ` como percentual (`Δ_i/C^D_i`) em vez de absoluto, para preservar invariância a `γ_i` | Rejeitada para esta ADR porque, sob a decomposição de duas taxas (P2), a invariância deixa de ser o critério relevante — `causa_dominante` já isola a componente de precificação independentemente da forma de `Γ`; manter `Γ` absoluto também é mais legível para o usuário de negócio ("quanto de margem em R$", não um percentual abstrato) |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Diagnóstico causal correto | `causa_dominante` separa "dói no cronograma" de "dói na precificação" com uma decomposição aditiva matematicamente válida (P2), não uma correlação espúria com qual limite foi cruzado |
| Reaproveita quase tudo do cálculo existente | `H_i`, `γ_i^v`, `γ_i^o` derivam de `n_frentes`/`permanencia_base`/`custo_venda_total`/`custo_operacional_real` já calculados; só `RegimeTrabalho.h`/`d` e a divisão final são novos |
| Teto `Γ` fecha uma lacuna nomeada explicitamente pelo usuário | Hoje só existe piso; `Γ` opt-in por perfil evita regressão em contratos já calibrados |
| Complementa (não duplica) o ADR-060 | `causa_dominante` é um recorte rápido de 2 categorias; a decomposição causal completa (η/clima/calendário/cross-term/quantização) continua sendo a análise de referência para investigação profunda |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| `H_i` pode não ser resolvível (schedule real ainda não montado, ou `custo_operacional_real == 0`) | `causa_dominante = "INDETERMINADO"` — nunca inventar `γ_i^o` a partir de dado ausente |
| `γ_i^v`/`γ_i^o` são taxas *implícitas* (derivadas por divisão), não armazenadas diretamente — sensíveis a arredondamento quando `Q_i`/`H_i` são pequenos | Aplicar o mesmo piso de materialidade já usado em `_pe_frentes_nec` (fallback conservador quando a razão é absurda) |
| Confusão entre este teto por-atividade e o Semáforo de Margem (percentual, agregado) | Nomear a validação como `VAL-PONTO-EQUILIBRIO-TETO` (paralelo a `VAL-PONTO-EQUILIBRIO-PARTICAO`/`-MITIGACAO` já existentes) e documentar a distinção explicitamente no relatório |
| Perfis existentes sem `Γ` configurado não ganham nenhum benefício automático de D2/D3 (mas D1/`causa_dominante` independe de `Γ` e já se aplica) | Aceitável — opt-in deliberado para o teto; `causa_dominante` já funciona hoje só com o piso existente |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `H_i`/`γ_i^v`/`γ_i^o` + `causa_dominante` (D1) + testes | ⬜ (avaliação nesta worktree) |
| F2 | `Γ` como campo de perfil opcional + `VAL-PONTO-EQUILIBRIO-TETO` (D2) + `horas_reais_min`/`max` no relatório/Excel (D3) | ⬜ (depende de F1 aprovado) |
| F3 (futura, condicionada) | Migração de `custo_fixo_total` para base semanal explícita por frentes (D4), reaproveitando `project_ocupacao_semanal` (ADR-152) | ⬜ (não iniciada — precisa de decisão própria) |

## Definition of Done

### Fase 1
- [ ] `causa_dominante` retorna `"CRONOGRAMA"` quando `|T_cronograma| > |T_precificacao|`, `"PRECIFICACAO"` no caso contrário
- [ ] `causa_dominante = "INDETERMINADO"` quando `H_i` não resolvível (`custo_operacional_real <= 0` ou schedule ausente) — nunca um valor inventado
- [ ] Teste de regressão prova a identidade `T_cronograma + T_precificacao == delta` (dentro de tolerância de arredondamento, mesmo padrão de `ε_tol` do roundtrip do ADR-061)
- [ ] Suíte completa sem regressão (golden tests inclusos)

### Fase 2
- [ ] `Γ` lido do perfil (`config/contextos/<perfil>.json`), `None` por default — nenhum perfil existente muda de comportamento sem opt-in
- [ ] `VAL-PONTO-EQUILIBRIO-TETO` emitido como AVISO (nunca ERRO) quando `Γ` configurado e `Δ_i ≥ Γ`
- [ ] `horas_reais_min`/`horas_reais_max` expostos no relatório/Excel quando `Γ` e `γ_i^o` disponíveis

---

## Relacionados

- ADR-060 — Diagnóstico de Ponto de Equilíbrio (decomposição causal agregada; esta ADR propõe um recorte mais rápido nas mesmas duas famílias de causa, complementar, não substituto)
- ADR-061 — Inversão/Backtracking de PE (espaço de correção `L*`/`η*`/`n_max*`/`t0*` — `causa_dominante` aponta qual dessas inversas é relevante: `PRECIFICACAO`→`L*`, `CRONOGRAMA`→`n_max*`/`t0*`)
- ADR-076 — Calibração PU/Frentes (`frentes_nec`, mesmo espírito de expor um número acionável antes do erro)
- ADR-083 — Decomposição Causal do Gap de Pool (mesma família de `gap_*` em `PontoEquilibrio`)
- ADR-152 — Timelapse de Ocupação de Pool (fonte de dados semanal candidata para a Fase 3/D4)
- [[nep043-cr-reconciliacao]] — precedente real de `T_precificacao` diferente de zero (BDI/`T_efetivo` divergente entre camadas antes da correção `716a155e`)
