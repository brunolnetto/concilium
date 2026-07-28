# ADR-162 — Diagnóstico de Piso/Teto do Ponto de Equilíbrio: Decomposição Direta das Inequações

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

P2. **Dois modos de falha hoje indistintos.** `status_validacao="ERRO"` dispara sempre que `delta < 0`, sem dizer *por que*. Mas a inequação, decomposta, revela que o sinal de `Δ_i` é **matematicamente independente de `γ_i`** — depende só da razão capacidade×demanda `Q_i/ρ_i` vs `h·d·Σ_j m_ij`. Isso separa dois problemas de natureza distinta que a decomposição causal do ADR-060 já cobre de forma agregada (η, clima, calendário, cross-term, quantização) mas não rotula de forma direta e acionável no momento do schedule:

- **Violação de piso** (`Δ_i ≤ 0`): problema de **cronograma/capacidade** — frentes demais alocadas para a produtividade disponível. Ação corretiva está no espaço de `n(t)`/`t0` (ADR-061: `n_max*`, `t0*`).
- **Violação de teto** (`Δ_i ≥ Γ`, quando `Γ` existir): problema de **custo/precificação** — `γ_i` ou o PU de catálogo desalinhado com o custo real, gerando margem além do competitivo. Ação corretiva está no espaço de `L*`/preço (ADR-061: `L_requerido`).

P3. **A inequação, invertida, já é um limite de planejamento explícito**, sem precisar de nenhum dado novo. Como `Δ_i` é linear e decrescente em `Σ_j m_ij` (inclinação constante `-γ_i·h·d`):

```
Q_i/ρ_i − Γ/γ_i  <  Σ_j m_ij  <  Q_i/ρ_i
```

Hoje o pipeline calcula `Δ_i` só *depois* de o schedule já ter sido montado (skill 06, pós skill 04/05) e reporta erro a posteriori. O intervalo acima poderia ser consultado *antes* de alocar frentes, como bound de planejamento por atividade — não uma mudança de quando o schedule roda, mas uma validação adicional, complementar às existentes.

P4. A formalização do usuário usa `C̃^D_i` em base **semanal explícita por frentes** (`Σ_j h·d·m_ij`). O código hoje usa base **mensal** (`equipe.custo_fixo_mensal × permanencia_base`, `_ponto_equilibrio.py:320`) — granularidade agregada, sem abrir por semana/frente. Isso é suficiente para o piso (delta agregado), mas insuficiente para apontar *em qual semana* um eventual estouro de frentes ocorre (ramp-up vs ramp-down) — o mesmo problema que o cross-term de timing do ADR-061 (`t0*`, minimiza `Cov(n,p)`) já resolve por outro caminho (função objetivo global, não limite por-atividade-por-semana).

---

## Decisão

Esta ADR é uma **proposta de avaliação** (worktree separada, ver `Contexto`/instrução do usuário) — não implementa ainda. Define o desenho a avaliar antes de decidir se segue para `main`.

### D1 — Rotular a causa da violação de piso, sem novo cálculo

Quando `status_validacao == "ERRO"` (`delta < 0`), adicionar um campo derivado `causa_piso: Literal["CRONOGRAMA", "INDETERMINADO"]` em `PontoEquilibrio`, computado comparando o sinal de `(Q_i/ρ_i − h·d·Σ_j m_ij)` — que já é o próprio `delta/γ_i` quando `γ_i > 0` — com o histórico de frentes do item (`n_frentes` já existe em `_build_pe_for_equipe`). Não é uma segunda fonte de verdade: é uma re-leitura do mesmo `delta` já calculado, exposta com rótulo. `INDETERMINADO` cobre o caso `γ_i` não resolvido (ver Riscos).

### D2 — Introduzir o teto `Γ` como parâmetro configurável, com validação nova `VAL-PONTO-EQUILIBRIO-TETO` (AVISO)

`Γ` entra como campo de perfil (`config/contextos/<perfil>.json`, ao lado de `limiar_ponto_equilibrio` citado em `MEMORIAL_FORMULAS.md` §13), com fallback `None` (desabilitado) — perfis existentes não ganham um teto por default, evitando regressão silenciosa em contratos já aprovados. Quando configurado e `Δ_i ≥ Γ`, emite `VAL-PONTO-EQUILIBRIO-TETO` como AVISO (mesma filosofia não-bloqueante de todo o resto da skill 06 — ver `validador_cobertura_item.py:13-18`), nunca ERRO.

### D3 — Expor o intervalo de frentes-semana como campo informativo, não como gate de schedule

Adicionar `frentes_semana_min`/`frentes_semana_max` (derivados de `Q_i/ρ_i − Γ/γ_i` e `Q_i/ρ_i`) ao `PontoEquilibrio` quando `Γ` estiver configurado — informativo no relatório/UI (mesma seção EQUILIBRIO do Excel), **não** um bloqueio no momento de montar o schedule (skill 04/05). Avaliar no schedule é mudança de escopo maior (acoplaria RCPSP a um teto comercial) e fica fora desta proposta — a decisão aqui é só tornar o número visível cedo, não impor um novo gate de solver.

### D4 — Não migrar a base operacional de mensal para semanal-por-frente nesta ADR

A formalização por semana (`Σ_j m_ij`) é mais fiel, mas migrar `custo_fixo_total` de mensal para essa forma explícita é uma mudança de modelo de dados (precisa de `m_ij` por semana, não só `n_frentes` agregado) que toca `_build_pe_for_equipe` e potencialmente o schedule real (ADR-152, `project_ocupacao_semanal`, que já tem granularidade semanal e poderia alimentar isso). Fica registrado como Fase 2 candidata (ver Plano), condicionada a essa fonte de dados semanal já existir de fato ligada ao item de EAP.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Implementar `Γ` como ERRO bloqueante (nunca aprovar acima do teto) | Contraria a filosofia confirmada do resto da skill 06 (bloquear impediria a geração do relatório de diagnóstico); mantém o padrão AVISO com override no gate de aprovação |
| A2 | Migrar `custo_fixo_total` para base semanal por frentes já nesta ADR | Escopo maior que o pedido (mudança de modelo de dados, não só de diagnóstico); deferido para Fase 2 condicionada a fonte de dados semanal por item já existir |
| A3 | Usar o intervalo de frentes-semana (D3) como gate direto do solver RCPSP | Acoplaria restrição comercial ao motor de schedule; decisão de produto maior, fora do escopo de "extrair diagnóstico" que motivou esta ADR |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Diagnóstico mais direto | Separa "dói no cronograma" de "dói no preço" sem precisar rodar a decomposição causal completa do ADR-060 |
| Reaproveita 100% do cálculo existente | `causa_piso` e o intervalo de frentes-semana são releituras de `delta`/`custo_fixo_total`/`custo_venda_total` já calculados — nenhuma nova fonte de dados |
| Teto `Γ` fecha uma lacuna nomeada explicitamente pelo usuário | Hoje só existe piso; `Γ` opt-in por perfil evita regressão em contratos já calibrados |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| `γ_i` pode não ser diretamente recuperável (o código usa `custo_fixo_mensal`/`custo_total`, agregados, não sempre um `γ_i` unitário isolado) | `causa_piso="INDETERMINADO"` quando a decomposição não puder isolar `γ_i` de forma confiável — nunca inventar um valor |
| Confusão entre este teto por-atividade e o Semáforo de Margem (percentual, agregado) | Nomear a validação como `VAL-PONTO-EQUILIBRIO-TETO` (paralelo a `VAL-PONTO-EQUILIBRIO-PARTICAO`/`-MITIGACAO` já existentes) e documentar a distinção explicitamente no relatório |
| Perfis existentes sem `Γ` configurado não ganham nenhum benefício automático | Aceitável — opt-in deliberado; abrir issue de acompanhamento se algum perfil quiser adotar |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `causa_piso` (D1) + `Γ` como campo de perfil opcional + `VAL-PONTO-EQUILIBRIO-TETO` (D2) + testes | ⬜ (avaliação nesta worktree) |
| F2 | `frentes_semana_min`/`max` no relatório/Excel (D3) | ⬜ (depende de F1 aprovado) |
| F3 (futura, condicionada) | Migração de `custo_fixo_total` para base semanal explícita por frentes (D4), reaproveitando `project_ocupacao_semanal` (ADR-152) | ⬜ (não iniciada — precisa de decisão própria) |

## Definition of Done

### Fase 1
- [ ] `causa_piso` retorna `"CRONOGRAMA"` quando o sinal de `delta` é atribuível à razão `Q_i/ρ_i` vs frentes alocadas, `"INDETERMINADO"` quando `γ_i` não isolável
- [ ] `Γ` lido do perfil (`config/contextos/<perfil>.json`), `None` por default — nenhum perfil existente muda de comportamento sem opt-in
- [ ] `VAL-PONTO-EQUILIBRIO-TETO` emitido como AVISO (nunca ERRO) quando `Γ` configurado e `Δ_i ≥ Γ`
- [ ] Suíte completa sem regressão (golden tests inclusos)

---

## Relacionados

- ADR-060 — Diagnóstico de Ponto de Equilíbrio (decomposição causal agregada; esta ADR propõe um recorte direto/rápido complementar, não substituto)
- ADR-061 — Inversão/Backtracking de PE (espaço de correção `L*`/`η*`/`n_max*`/`t0*` — `causa_piso`/teto apontam para qual dessas inversas é relevante)
- ADR-076 — Calibração PU/Frentes (`frentes_nec`, mesmo espírito de expor um número acionável antes do erro)
- ADR-083 — Decomposição Causal do Gap de Pool (mesma família de `gap_*` em `PontoEquilibrio`)
- ADR-152 — Timelapse de Ocupação de Pool (fonte de dados semanal candidata para a Fase 3/D4)
