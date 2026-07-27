# ADR-154 — Roster Real de Mão-de-Obra: Custo Individualizado sem Amarrar Identidade ao Cronograma

**Status:** Proposta
**Data:** 2026-07-26
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-097 (Tributação Social — encargos SINTRACON/INSS/IRRF), ADR-106 (`EquipeCustoEngine`/`LifecycleEngine`), ADR-071 (Resource Contract Model — `RecursoContrato.custo_unit_semanal_mo`)

---

## Contexto

### Problema

P1. O custo de mão-de-obra por função hoje é sempre **agregado e calibrado**: `custo_hora_total_referencia`/`custo_unit_semanal_mo` representa uma taxa de referência para a função inteira (ex.: "pedreiro"), sem nenhuma ligação com pessoas reais — quem efetivamente ocupa a função, com que salário, desde quando. Uma discussão de arquitetura (2026-07-26) mapeou isso como uma lacuna real: hoje não é possível calcular o custo de cada indivíduo que ocupa uma função do início ao fim de um contrato de trabalho mensal, com seus encargos reais, proporcional ao momento de entrada.

P2. A tentativa natural de resolver isso — amarrar identidade física a um slot do cronograma (`InstanciaRecurso`/`segmentos_atividade`, ver ADR-153 F1) — foi deliberadamente **rejeitada** como direção: o pool de recursos é fungível por design durante o planejamento (RCPSP resolve capacidade agregada, não "quem" ocupa cada posição), e misturar identidade real de pessoa com a mecânica de scheduling contradiz esse princípio. `InstanciaRecurso` já resolve elegantemente "instância + fungibilidade" (numera o slot, mas o ativo físico que o ocupa pode variar) — não deveria virar também um registro de identidade de pessoa real.

P3. O que de fato falta é uma **camada de custo bottom-up**, independente do scheduling: dado um conjunto de pessoas reais atribuídas a uma função (com salário-base, categoria sindical, data de admissão e, eventualmente, de desligamento), somar o custo real por semana do contrato — em vez de multiplicar `num_pessoas × custo_hora_total_referencia`.

---

## Decisão

Escopo desta ADR: **apenas mão-de-obra** (equipamento fica para uma ADR de continuação, estruturalmente análoga, se confirmado necessário).

### D1 — Novo modelo `MembroEquipeReal`

```python
class MembroEquipeReal(BaseModel):
    """Membro real de equipe (roster) — ADR-154.

    Individualiza custo de mão-de-obra a partir de uma pessoa real (salário,
    encargos, data de admissão/desligamento), em vez do custo calibrado
    agregado por função. Sem nenhuma ligação com InstanciaRecurso/segmentos/
    scheduling — o pool RCPSP continua fungível; isto é puramente um input
    de custo bottom-up.
    """

    individuo_id: str
    funcao_id: str
    salario_base_mensal: float = Field(ge=0)
    categoria_sindical: str | None = None  # resolvido via encargo_resolver, mesma precedência ADR-097
    percentual_encargos_local: float | None = None  # override explícito, mesma precedência
    data_admissao: date
    data_desligamento: date | None = None  # None = ainda ativo
```

### D2 — Função pura `custo_real_mo_semanal`

```python
def custo_real_mo_semanal(
    roster: list[MembroEquipeReal],
    funcao_id: str,
    semana_inicio: str,
    semana_fim: str,
) -> dict[str, float]:
    """Custo real de MO por semana — soma, por semana, o custo de cada membro do
    roster ativo naquela função e naquela semana:

        custo_semana(t) = Σ_{membro ativo em t} (salario_base_mensal / SEMANAS_POR_MES)
                           × (1 + resolver_encargo(membro))

    "Ativo em t" = [data_admissao, data_desligamento ou +∞] intersecta a semana ISO
    t (segunda a domingo) — mesma granularidade semanal usada em todo o resto do
    RCPSP (machine-weeks, permanencia_efetiva etc.), não um cálculo de fração de
    dias dentro da semana.

    Reaproveita `resolver_encargo` (ADR-097) — mesma precedência e mesmas taxas
    (ENCARGOS_CLT/ENCARGOS_MENSALISTA) usadas pelo resto da cadeia de custo.
    """
```

E o agregado `custo_real_mo_total(roster, funcao_id, semana_inicio, semana_fim) -> float` (soma de `custo_real_mo_semanal`).

Granularidade semanal deliberada: entrar no meio de uma semana ISO não gera rateio por dia — a pessoa é contabilizada na semana inteira em que sua admissão cai. Isso é consistente com a granularidade semanal usada em todo o resto do motor (nunca há fração de dia em `machine_weeks`, `permanencia_efetiva`, etc.) — introduzir proração diária aqui criaria uma granularidade inconsistente com o resto do sistema sem necessidade real demonstrada.

### D3 — Localização

`MembroEquipeReal` em `src/concilium/domain/models/canonical/_roster_mo.py` (novo arquivo, mesmo padrão de split de `canonical.py` já usado para `_pool_recursos.py`). `custo_real_mo_semanal`/`custo_real_mo_total` em `src/concilium/domain/services/financial/roster_custo_mo.py`, ao lado de `encargo_resolver.py` (mesma camada, reaproveita a mesma função).

### D4 — Escopo explicitamente fechado: sem wiring ao pipeline real

Mesma disciplina de ADR-152 D3 e ADR-153 A4: esta ADR entrega a função de domínio testada, **sem** conectar a `RecursoContrato.custo_unit_semanal_mo` no pipeline real de skill-05 (`_pool_contrato_construcao.py`), sem override em `Escopo`, sem UI. A função existe e está pronta para uso — decidir *como* uma pessoa real entra no roster de um projeto (formulário? planilha? override de projeto como `Escopo.logistica_consumiveis`?) é uma decisão de produto separada, não assumida aqui.

Sem ligação nenhuma com `InstanciaRecurso`/`segmentos_atividade`/`identidade_fisica_id` (ADR-153) — o roster não sabe (nem precisa saber) qual slot do cronograma cada pessoa ocupou. O RCPSP permanece inteiramente fungível.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Amarrar o roster a `InstanciaRecurso`/segmento (saber "esta pessoa ocupou este slot nesta semana") | Rejeitado explicitamente pelo usuário — contradiz a fungibilidade do pool durante o planejamento; ver P2 |
| A2 | Proração diária (fração de dias dentro da semana de admissão) | Rejeitado — introduziria granularidade sub-semanal inconsistente com o resto do motor RCPSP, que opera inteiramente em semanas; sem necessidade real demonstrada para essa precisão |
| A3 | Nova taxa de encargo específica para roster, em vez de reaproveitar `resolver_encargo` | Rejeitado — duplicaria lógica já centralizada (ADR-097 §D1/D2) e quebraria a garantia de que a mesma pessoa custa o mesmo em qualquer parte do sistema que calcule encargos |
| A4 | Conectar já nesta ADR ao pipeline real (`RecursoContrato.custo_unit_semanal_mo`) | Deferido — mesma disciplina de escopo de ADR-152/153; a decisão de *como* o roster é declarado num projeto real é produto, não implementação |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Responde à pergunta original do usuário | Custo individual real, com encargos e proporcional à data de entrada, calculável de forma testada |
| Zero acoplamento com scheduling | Pool RCPSP permanece fungível; roster é camada de dado puramente de custo |
| Reaproveita infraestrutura de encargos já auditada | `resolver_encargo` (ADR-097) é a mesma fonte de verdade usada em toda a cadeia de custo — nenhuma duplicação de regra fiscal |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Sem wiring, o roster ainda não é utilizável num projeto real | Mesma decisão já validada em ADR-152/153 — entrega é a função testada; integração é trabalho de produto futuro sob demanda |
| Granularidade semanal pode subestimar/superestimar levemente o custo de admissões no meio da semana | Aceitável — consistente com a granularidade de todo o resto do sistema; ver A2 |
| Equipamento (contrato de locação real por ativo) fica de fora desta ADR | Estrutura análoga pode ser adicionada em ADR de continuação, se confirmado necessário |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `MembroEquipeReal` + `custo_real_mo_semanal`/`custo_real_mo_total` + testes | ⬜ |
| F2 (futura) | Estrutura análoga para equipamento (roster de ativos com contrato de locação real) | ⬜ (não iniciada — ADR de continuação) |
| F3 (futura) | Wiring ao pipeline real (`RecursoContrato.custo_unit_semanal_mo`, override em projeto) | ⬜ (não iniciada — decisão de produto) |

## Definition of Done

### Fase 1 (TDD — teste antes da implementação)

- [ ] Membro ativo durante toda a semana conta o custo cheio daquela semana
- [ ] Membro admitido no meio do span do contrato só conta a partir da semana ISO de `data_admissao` (inclusive)
- [ ] Membro desligado no meio do span só conta até a semana ISO de `data_desligamento` (inclusive); depois disso, zero
- [ ] Membro sem `data_desligamento` (`None`) conta em todas as semanas do span a partir da admissão
- [ ] Membro de outra função (`funcao_id` diferente) é ignorado
- [ ] Encargo resolvido via `resolver_encargo` com a mesma precedência de ADR-097 (override explícito → `percentual_encargos_local` → categoria sindical)
- [ ] Múltiplos membros na mesma função somam corretamente por semana
- [ ] `custo_real_mo_total` é a soma de `custo_real_mo_semanal`
- [ ] Suíte completa sem regressão

---

## Relacionados

- ADR-097 — Tributação Social (fonte de verdade dos encargos, reaproveitada via `resolver_encargo`)
- ADR-106 — `EquipeCustoEngine`/`LifecycleEngine` (motor de custo agregado existente, que esta ADR complementa sem substituir)
- ADR-071 — Resource Contract Model (`RecursoContrato.custo_unit_semanal_mo`, ponto de integração futura — F3, não implementada aqui)
- ADR-153 — Identidade Física de Recurso (decisão irmã: identidade de slot é rastreabilidade opcional e dormente; roster de custo real é camada totalmente separada — nenhuma das duas depende da outra)
- Achado de conversa 2026-07-26: memórias `modelagem-recursos-pool-gaps-individualizacao` (lacuna original) e `feedback_pool_fungivel_planejamento_sem_identidade_instancia` (princípio que motivou D2/A1)
