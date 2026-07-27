# ADR-155 — Roster Real de Equipamento: Custo Individualizado sem Amarrar Identidade ao Cronograma

**Status:** Proposta
**Data:** 2026-07-26
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-154 (Roster Real de Mão-de-Obra — estrutura irmã, mesma disciplina de escopo), ADR-088 (Decomposição Sub-composicional de Equipamento — locação/manutenção), ADR-071 (Resource Contract Model — `RecursoContrato.custo_unit_semanal_eq`)

---

## Contexto

### Problema

P1. ADR-154 resolveu a individualização de custo real de mão-de-obra (roster de pessoas reais, com salário/encargos/data de admissão-desligamento) sem amarrar identidade ao cronograma — o pool RCPSP permanece fungível, o roster é só camada de custo. Falta a estrutura análoga para **equipamento**: hoje o custo de um contrato de locação é sempre agregado e calibrado (`custo_unit_semanal_eq`/`custo_locacao_mensal`), sem ligação com o contrato de locação real de um ativo físico específico (valor real negociado, data de início/fim do contrato daquele ativo).

P2. A mesma restrição de ADR-154 D2/P2 se aplica aqui: **não** amarrar isso a `InstanciaRecurso`/`segmentos_atividade`/`identidade_fisica_id` (ADR-153) — o pool de equipamento continua fungível durante o planejamento; qual ativo físico específico ocupa qual slot do cronograma é rastreabilidade opcional e dormente (ADR-153), não uma dependência da individualização de custo.

---

## Decisão

Estrutura estruturalmente análoga a ADR-154, com dois campos de custo em vez de um (locação + manutenção, seguindo a decomposição já estabelecida em ADR-088), e sem o equivalente de "encargos" (não há taxa social sobre equipamento — sub-decomposição de BDI é etapa downstream separada, fora de escopo aqui, mesma exclusão de ADR-154 D2 sobre BDI/impostos não entrarem no roster).

### D1 — Novo modelo `AtivoEquipamentoReal`

```python
class AtivoEquipamentoReal(BaseModel):
    """Ativo real de equipamento (roster) — ADR-155.

    Individualiza custo de equipamento a partir de um ativo real (contrato de
    locação real, com valores e datas reais), em vez do custo calibrado agregado
    por tipo (custo_unit_semanal_eq). Sem nenhuma ligação com InstanciaRecurso/
    segmentos_atividade/identidade_fisica_id (ADR-153) — o pool RCPSP continua
    fungível; isto é puramente um input de custo bottom-up.
    """

    ativo_id: str
    tipo_id: str
    custo_locacao_mensal_real: float = Field(ge=0)
    custo_manutencao_mensal_real: float = 0.0
    data_contrato_inicio: date
    data_contrato_fim: date | None = None  # None = contrato ainda ativo/aberto
```

### D2 — Funções puras `custo_real_eq_semanal` / `custo_real_eq_total`

```python
def custo_real_eq_semanal(
    roster: list[AtivoEquipamentoReal],
    tipo_id: str,
    semana_inicio: str,
    semana_fim: str,
) -> dict[str, float]:
    """Custo real de equipamento por semana — soma, por semana, o custo de cada
    ativo do roster ativo naquele tipo e naquele intervalo:

        custo_semana(t) = Σ_{ativo ativo em t} (custo_locacao_mensal_real
                           + custo_manutencao_mensal_real) / SEMANAS_POR_MES

    "Ativo em t" = [data_contrato_inicio, data_contrato_fim ou +∞] intersecta a
    semana ISO t (segunda a domingo) — mesma granularidade semanal de ADR-154 e
    do resto do motor RCPSP, sem proração diária.
    """
```

E `custo_real_eq_total(roster, tipo_id, semana_inicio, semana_fim) -> float` (soma de `custo_real_eq_semanal`).

Sem equivalente de `resolver_encargo`: não há taxa social sobre custo de equipamento — `custo_locacao_mensal_real + custo_manutencao_mensal_real` já é o valor real de contrato, ponto. BDI (ADR-023/088/090) é etapa downstream separada, aplicada sobre o custo agregado do projeto inteiro, não sobre o roster individual — mesma exclusão de escopo de ADR-154 D2 quanto a impostos/BDI não entrarem na camada de roster.

### D3 — Localização

`AtivoEquipamentoReal` em `src/concilium/domain/models/canonical/_roster_equipamento.py` (mesmo padrão de `_roster_mo.py`, ADR-154 D3). `custo_real_eq_semanal`/`custo_real_eq_total` em `src/concilium/domain/services/financial/roster_custo_equipamento.py`, ao lado de `roster_custo_mo.py`.

### D4 — Escopo explicitamente fechado: sem wiring ao pipeline real

Mesma disciplina de ADR-152 D3, ADR-153 A4, ADR-154 D4: função de domínio pura e testada, sem conectar a `RecursoContrato.custo_unit_semanal_eq` no pipeline real de skill-05, sem override em `Escopo`, sem UI. Sem ligação nenhuma com `InstanciaRecurso`/`segmentos_atividade`/`identidade_fisica_id` — o roster de equipamento não sabe (nem precisa saber) qual slot do cronograma cada ativo ocupou.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Amarrar o roster a `InstanciaRecurso`/segmento (saber "este ativo ocupou este slot nesta semana") | Rejeitado explicitamente — mesma decisão de ADR-154 A1; contradiz a fungibilidade do pool durante o planejamento |
| A2 | Incluir custo de mobilização/desmobilização por ativo no roster | Rejeitado — isso já é tratado no nível de `RecursoContrato`/`CadeiaPerpetuacao` (ADR-073/078/136); duplicar aqui criaria dois lugares para a mesma informação. Roster fica restrito ao custo recorrente (locação + manutenção), mesma disciplina de ADR-154 (que também excluiu mob/demob do roster de MO) |
| A3 | Modelar equipamento próprio (depreciação) junto com o roster de locação real | Rejeitado — decisão de negócio já tomada em ADR-127 A2 (fora de escopo por falta de caso de uso); esta ADR não reabre essa decisão, só individualiza o custo de locação real, que já é o modelo hoje adotado |
| A4 | Proração diária de início/fim de contrato | Rejeitado — mesma razão de ADR-154 A2: granularidade semanal é consistente com o resto do motor RCPSP |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Fecha a pergunta original sobre custo de contrato de equipamento locado | Custo real por ativo, com datas reais de contrato, calculável de forma testada |
| Estrutura irmã de ADR-154 | Mesmo padrão mental para MO e equipamento — mais fácil de manter e explicar |
| Zero acoplamento com scheduling | Pool RCPSP permanece fungível |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Sem wiring, roster ainda não é utilizável num projeto real | Mesma decisão já validada em ADR-152/153/154 |
| Equipamento próprio (não locado) continua sem modelagem | Fora de escopo — decisão de negócio já tomada em ADR-127 |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `AtivoEquipamentoReal` + `custo_real_eq_semanal`/`custo_real_eq_total` + testes | ⬜ |
| F2 (futura) | Wiring ao pipeline real (`RecursoContrato.custo_unit_semanal_eq`, override em projeto) — mesma decisão de produto pendente em ADR-154 F3 | ⬜ (não iniciada) |

## Definition of Done

### Fase 1 (TDD — teste antes da implementação)

- [ ] Ativo com contrato ativo durante toda a semana conta o custo cheio daquela semana (locação + manutenção)
- [ ] Ativo com contrato iniciado no meio do span só conta a partir da semana ISO de `data_contrato_inicio` (inclusive)
- [ ] Ativo com contrato encerrado no meio do span só conta até a semana ISO de `data_contrato_fim` (inclusive); depois disso, zero
- [ ] Ativo sem `data_contrato_fim` (`None`) conta em todas as semanas do span a partir do início
- [ ] Ativo de outro tipo (`tipo_id` diferente) é ignorado
- [ ] Custo soma locação + manutenção corretamente
- [ ] Múltiplos ativos do mesmo tipo somam corretamente por semana
- [ ] `custo_real_eq_total` é a soma de `custo_real_eq_semanal`
- [ ] Suíte completa sem regressão

---

## Relacionados

- ADR-154 — Roster Real de Mão-de-Obra (estrutura irmã, mesma disciplina de escopo e mesmos princípios)
- ADR-088 — Decomposição Sub-composicional de Equipamento (locação/manutenção como sub-propriedades, nomenclatura reaproveitada aqui)
- ADR-071 — Resource Contract Model (`RecursoContrato.custo_unit_semanal_eq`, ponto de integração futura — F2, não implementada aqui)
- ADR-127 — Regime de Contrato vs. Precificação Horária (decisão de que equipamento próprio/depreciação está fora de escopo, reafirmada aqui em A3)
- ADR-153 — Identidade Física de Recurso (decisão irmã: identidade de slot é rastreabilidade opcional e dormente; roster de custo real é camada totalmente separada)
