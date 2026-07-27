# ADR-158 — Custo Real por Instância: Timeline Analítica Prod/Idle/Off

**Status:** Implementado
**Data:** 2026-07-27
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-152 (Timelapse de Ocupação — `project_ocupacao_semanal`), ADR-156 (Substituição Segura de MO), ADR-157 (Substituição Segura de EQ), ADR-085/106 (`LifecycleEngine` — metodologia prod/idle do pool)

---

## Contexto

### Problema

P1. As peças construídas nas ADRs 152/154/155/156/157 ainda não se juntam num único registro analítico: `project_ocupacao_semanal` (ADR-152) diz o status (prod/idle/off) de uma `InstanciaRecurso` por semana; `aplicar_roster_custo_real_mo`/`_eq` (ADR-156/157) calculam uma taxa média real por unidade×semana para o contrato inteiro, mas não aplicam isso por instância nem diferenciam prod de idle.

P2. **Decisão de design (confirmada em conversa)**: a peça final não deve reintroduzir identidade física por slot (rejeitada explicitamente — ADR-153 F1 permanece dormente, pool continua fungível). Em vez de tentar saber "qual pessoa/ativo real ocupou esta instância nesta semana", cada instância usa a **mesma taxa média real** que já vale para o tipo inteiro (`custo_unit_semanal_mo_novo`/`_eq_novo`, calculadas em ADR-156/157) — exatamente como o sistema calibrado já faz hoje (`custo_unit_semanal_mo`/`_eq` são idênticos para toda instância de um tipo; só o número de semanas ativas/ociosas varia por instância).

P3. O sistema calibrado diferencia prod de idle de forma assimétrica (`LifecycleEngine.calcular`, ADR-085/106): MO ociosa custa igual à ativa (CLT integral); equipamento ocioso custa uma taxa reduzida (só locação, sem manutenção — fallback calibrado `c_idle = cus_mo + cus_locacao`). O registro real por instância deve seguir a MESMA assimetria, não uma simplificação "tudo com taxa cheia".

---

## Decisão

### D1 — Nova função `custo_real_eq_idle_semanal` (taxa reduzida real, espelha o fallback calibrado)

```python
def custo_real_eq_idle_semanal(
    roster: list[AtivoEquipamentoReal],
    equip_id: str,
    semana_inicio: str,
    semana_fim: str,
) -> dict[str, float]:
    """Custo real de equipamento OCIOSO por semana — só locação, sem manutenção.

    Espelha o fallback calibrado (custo_idle_semanal_unit = cus_mo + cus_locacao,
    _pool_contrato_demanda.py::_resolve_gap_max_e_idle_efetivo): equipamento ocioso
    continua sob contrato de locação (custo fixo), mas não incorre manutenção
    ativa. Mesma estrutura de custo_real_eq_semanal (ADR-155), trocando o numerador
    para custo_locacao_mensal_real isolado.
    """
```

Localização: `domain/services/financial/roster_custo_equipamento.py` (adição à ADR-155, mesmo módulo).

### D2 — Nova função `custo_real_instancia_semanal`

```python
def custo_real_instancia_semanal(
    instancia: InstanciaRecurso,
    cus_mo_real: float,
    cus_eq_real: float,
    cus_eq_idle_real: float,
) -> dict[str, float]:
    """Custo real por semana de UMA instância, seguindo a mesma assimetria
    prod/idle/off do LifecycleEngine (ADR-085/106):

        status = project_ocupacao_semanal(instancia)[semana]   (ADR-152)

        "prod" -> cus_mo_real + cus_eq_real       (taxa ativa cheia)
        "idle" -> cus_mo_real + cus_eq_idle_real  (MO integral, EQ reduzido)
        "off"  -> 0.0

    `cus_mo_real`/`cus_eq_real` vêm da mesma taxa média real do contrato inteiro
    (RecursoContrato.custo_unit_semanal_mo/_eq PÓS aplicar_roster_custo_real_mo/eq,
    ADR-156/157) — não há atribuição de indivíduo/ativo a slot específico; o pool
    permanece fungível.
    """
```

Localização: `application/scheduling/pool_timelapse.py` (mesmo módulo de `project_ocupacao_semanal`, ADR-152 — reaproveitada diretamente aqui) ou um novo módulo dedicado — ver D3.

### D3 — Localização: novo módulo `application/scheduling/custo_real_instancia.py`

Módulo dedicado (não em `pool_timelapse.py`) porque `custo_real_instancia_semanal` depende de `RecursoContrato`/valores de custo (camada financeira), enquanto `pool_timelapse.py` é puramente sobre status de ocupação — mantém a separação de responsabilidades já estabelecida (ADR-152 é só timelapse, sem custo; este módulo é custo, importando `project_ocupacao_semanal` de `pool_timelapse.py`).

### D4 — Sem agregação/wiring nesta ADR

Não constrói um "cubo" ou relatório final (isso seria uma ADR de apresentação/analytics separada, ex. extensão da ADR-086). Não recalcula `custo_instancia_total` nem toca `InstanciaRecurso`/`RecursoContrato` diretamente — a função retorna um dict semana→custo, puro, pronto para consumo por uma camada de relatório futura. Mesma disciplina de "função pura primeiro, wiring depois" das ADRs anteriores.

### D5 — Invariante preservado (aprendido na investigação da sessão)

O sistema calibrado garante Σ(custo por instância) == custo do contrato **por construção** (atribuição direta, não validação a posteriori — `_custo_instancial_composicional.py:74-83`). Esta função preserva o mesmo princípio estrutural: como todas as instâncias de um tipo usam a MESMA `cus_mo_real`/`cus_eq_real`/`cus_eq_idle_real`, e as semanas prod/idle/off de cada instância particionam exatamente o span do contrato (ADR-152 — cada semana tem exatamente um status), a soma de `custo_real_instancia_semanal` de todas as instâncias de um contrato, semana a semana, reproduz corretamente `quantidade_contratada × (taxa da semana)` — o mesmo tipo de coerência aditiva que o sistema calibrado já tem, sem necessidade de nenhuma validação de reconciliação adicional.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Atribuir indivíduo/ativo real específico a cada instância/semana (via `identidade_fisica_id`, ADR-153) | Rejeitado explicitamente pelo usuário — reintroduziria identidade física no pool, contradizendo a fungibilidade de planejamento |
| A2 | Taxa cheia (sem redução) para EQ ocioso, ignorando a assimetria do `LifecycleEngine` | Rejeitado — o usuário pediu explicitamente que a metodologia coincida com a já aplicada no pool; simplificar aqui produziria um número inconsistente com o resto do sistema |
| A3 | Calcular `custo_real_eq_idle_semanal` como fração arbitrária de `custo_real_eq_semanal` (ex: ρ fixo) | Rejeitado — `rho_idle_eq` no sistema calibrado é só uma razão de relatório, nunca usada para calcular (achado da investigação); replicar isso introduziria uma aproximação onde já temos o dado real (`custo_locacao_mensal_real` isolado) |
| A4 | Construir already um cubo/relatório agregado nesta ADR | Rejeitado — escopo maior, decisão de apresentação separada; esta ADR entrega a função de cálculo testada |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Fecha o pedido original desta sessão | Cada instância ganha um registro de custo real ao longo do tempo, enriquecendo análise de projeto e do problema em geral |
| Metodologia consistente com o pool | Mesma assimetria prod/idle que o sistema calibrado já usa — números comparáveis lado a lado |
| Pool continua fungível | Nenhuma identidade física é usada ou necessária |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Sem wiring/relatório, ainda não é visível num projeto real | Mesma decisão já validada nas ADRs anteriores — função testada, consumo é trabalho futuro |
| Depende de `aplicar_roster_custo_real_mo`/`_eq` já terem sido aplicadas ao contrato (senão `cus_mo_real`/`cus_eq_real` seriam os calibrados, não os reais) | Documentado — quem chama esta função decide se passa taxa calibrada ou real; a função não impõe isso |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `custo_real_eq_idle_semanal` + `custo_real_instancia_semanal` + testes | ✅ |
| F2 (futura) | Agregação/relatório (cubo analítico) e wiring real | ⬜ (não iniciada) |

## Definition of Done

### Fase 1 (TDD — teste antes da implementação)

- [x] `custo_real_eq_idle_semanal` retorna só a fração de locação (sem manutenção), mesma granularidade semanal de ADR-155
- [x] `custo_real_instancia_semanal`: semana "prod" usa `cus_mo_real + cus_eq_real`
- [x] `custo_real_instancia_semanal`: semana "idle" usa `cus_mo_real + cus_eq_idle_real`
- [x] `custo_real_instancia_semanal`: semana "off" é zero
- [x] Soma de `custo_real_instancia_semanal` de todas instâncias de um contrato (semana a semana) bate com `quantidade_contratada × taxa esperada da semana`
- [x] Suíte completa sem regressão

---

## Relacionados

- ADR-152 — Timelapse de Ocupação (`project_ocupacao_semanal`, reaproveitada diretamente)
- ADR-155 — Roster Real de Equipamento (extensão: `custo_real_eq_idle_semanal`)
- ADR-156/157 — Substituição Segura de MO/EQ (fonte de `cus_mo_real`/`cus_eq_real`)
- ADR-085/106 — `LifecycleEngine` (metodologia prod/idle espelhada aqui)
- ADR-153 — Identidade Física de Recurso (decisão irmã — permanece dormente; esta ADR confirma que não era necessária para o objetivo real do usuário)
