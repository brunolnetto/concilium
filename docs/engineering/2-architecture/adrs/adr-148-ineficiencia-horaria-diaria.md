# ADR-148 — Ineficiência Horária Diária: `horas_improdutivas_dia`

**Status:** ⚠️ Parcialmente Implementado _(F0–F5 de código completos e testados; execução do script F0 contra dados reais e migração de backends remotos ficam pendentes de decisão do operador — ver DoD)_
**Data:** 2026-07-23
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-068 (Calendário Operacional — `fator_calendario`), ADR-072 (Duração Produtiva), ADR-124 (Reformulação do Modelo de Eficiência: Planejamento vs. Controle)

---

## Contexto

### Problema

P1. **A jornada de trabalho hoje é modelada como capacidade cheia.** `RegimeTrabalho` (`domain/models/canonical/_base.py`) expõe apenas `dias_semana` e `horas_dia`, multiplicados diretamente pela produtividade horária (`P`) para gerar produção semanal (`producao_semanal_base = P × horas_dia × dias_semana`), calculado de forma quase idêntica em três pontos (`_scheduling.py:256,515`, `_validacao.py:182`) e consumido por `_compute_productive_weeks` (ADR-072). Não existe hoje nenhum fator que reduza a jornada nominal por perdas internas ao dia — tempo de deslocamento interno ao canteiro, preparação/organização de frente de serviço, pausas não formalizadas. A única redução de capacidade já modelada atua em granularidade de **dia inteiro ou fração de dia** (clima via `η_clima`, calendário/feriados via `δ`, ADR-068/ADR-124) — nunca em **hora dentro do dia**.

P2. **O modelo de eficiência de planejamento (ADR-124) já estabeleceu o padrão para este tipo de fator, mas ainda não o cobre.** `η_plan = η_clima · δ` é a decomposição vigente — dois fatores determinísticos/estocásticos aplicados na mesma camada operacional (`_build_dist_cell`, `_custos.py`). Uma perda de produtividade por ineficiência de jornada diária é conceitualmente do mesmo tipo que `δ` (determinística, controlável pelo gestor, sem dependência de dados de execução real), mas não tem hoje nenhuma superfície própria — ficaria oculta dentro de `horas_dia`, contaminando o significado desse campo, que outros consumidores (ex.: conversão de `rental_unit` em `pu_calculator.py`) tratam como jornada *contratual*, não produtiva.

---

## Decisão

D1. **Novo campo `horas_improdutivas_dia` em `RegimeTrabalho`** (`domain/models/canonical/_base.py`), representando um **tempo fixo por dia** (não um percentual da jornada) perdido por ineficiência estrutural:

```python
class RegimeTrabalho(BaseModel):
    model_config = ConfigDict(extra="ignore")
    dias_semana: int = Field(ge=1, le=7)
    horas_dia: int = Field(ge=1, le=24)
    # ge=0, não gt=0: 0.0 é o valor gravado pela migração F0 em specs legados
    # (D5) — a exigência "sempre > 0" do pedido original vale para specs NOVOS
    # (reforçada pelo default e pela camada de apresentação), não como invariante
    # de modelo, que precisa aceitar 0.0 para não quebrar retrocompatibilidade.
    horas_improdutivas_dia: float = Field(default=0.5, ge=0)

    @model_validator(mode="after")
    def _valida_horas_improdutivas(self) -> "RegimeTrabalho":
        if self.horas_improdutivas_dia >= self.horas_dia:
            raise ValueError(
                "horas_improdutivas_dia deve ser menor que horas_dia "
                f"(recebido {self.horas_improdutivas_dia} >= {self.horas_dia})"
            )
        return self
```

Por ser tempo fixo (não fração), a proporção produtiva varia com o regime: 8h/dia → 93,75% produtivo; 6h/dia → 91,7%; 10h/dia → 95%. Default `0.5` (30 min) reproduz o valor de referência adotado pelo usuário.

D2. **Novo fator determinístico `eta_jornada`, aplicado no mesmo ponto e com o mesmo tratamento que `η_clima` e `δ`:**

```
eta_jornada = (horas_dia - horas_improdutivas_dia) / horas_dia
```

Entra em `_build_dist_cell` (`_custos.py:303-350`) como terceiro fator multiplicativo de praticabilidade:

```python
praticabilidade = fator_clima * fator_calendario * eta_jornada
```

e é propagado para as três repetições de `producao_semanal_base` (`_scheduling.py:256,515`, `_validacao.py:182`) e para `_compute_productive_weeks` (`_calendario.py:356-389`, fórmula ADR-072), assim como para `WorkforcePolicySimulator.simulate()` (`mobilizacao_simulator.py`).

D2-bis. **`eta_jornada` entra em `_compute_productive_weeks` (ADR-072), diferente de `fator_clima`/`fator_calendario`.** A ADR-082-cons exclui deliberadamente clima e calendário do cálculo de duração produtiva (`prod_per_week = P × horas_dia × dias_semana × n_resources`, sem praticabilidade) — são fatores estocásticos/variáveis, e estender a janela por eles tornaria o RCPSP inviável sob prazo apertado; a sub-entrega resultante é sinalizada por `VAL-CRON-01`, não absorvida na duração. `eta_jornada` é categoricamente diferente: é um fato estrutural e determinístico da jornada, sempre verdadeiro, não um risco. Excluí-lo da duração faria todo item disparar `VAL-CRON-01` permanentemente (falso-alarme sistemático, não uma condição excepcional de clima ruim). Por isso `prod_per_week` passa a ser `P × horas_dia × dias_semana × eta_jornada × n_resources` — `eta_jornada` dimensiona o plano (como a própria jornada nominal já fazia); clima/calendário continuam fora, preservando o precedente ADR-082-cons.

D3. **Escopo por projeto (regime único), não por atividade/recurso.** Segue a granularidade já existente de `RegimeTrabalho` — um único valor por obra. Não se tenta modelar ineficiência diferenciada por tipo de atividade ou por recurso individual nesta ADR; a cardinalidade Producao:CPU (M:1) tornaria essa granularidade mais fina um problema de desenho à parte, sem necessidade demonstrada hoje.

D4. **Escopo explicitamente excluído: custo/PU do catálogo.** `eta_jornada` opera exclusivamente na camada operacional de cronograma/produção (mesma camada de `η_clima`/`δ`) e **não** altera `custo_hora_total_referencia`, `valor_horario_canonico` nem a calibração de `_apply_producao_canonico` (`_custos.py:187-234`). A equipe continua custando o regime cheio (hora paga); apenas a produção planejada é reduzida — decisão de negócio confirmada pelo usuário, replicando o tratamento já dado a clima e calendário, que também não recalibram o catálogo. Ficam fora de escopo: `pu_calculator._converter_rental_unit`, custo de equipamento/mão-de-obra em skill-05 (`_dimensionamento_custos.py`), e `custo_hora_total_referencia`.

D5. **Retrocompatibilidade via migração explícita, não via default silencioso — mesmo padrão da ADR-124 D5.** Specs de projeto já materializados recebem `horas_improdutivas_dia: 0.0` gravado explicitamente por um script de migração idempotente, executado **antes** do default do modelo mudar para `0.5`. Só depois da migração o default de `RegimeTrabalho.horas_improdutivas_dia` no código passa a ser `0.5`, valendo para specs novos. Efeito: nenhum projeto existente tem sua produção planejada recalculada silenciosamente por este ADR — a adoção da ineficiência de 30min é opt-in por novo projeto (ou por edição explícita de um projeto existente), nunca retroativa.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Absorver a perda dentro de `horas_dia` (reduzir o campo existente) | Contamina o significado de `horas_dia`, que outros consumidores (ex. conversão de `rental_unit`) tratam como jornada contratual/paga, não produtiva. Perde rastreabilidade — não seria possível reportar separadamente clima × calendário × ineficiência de jornada. |
| A2 | Modelar como percentual fixo da jornada (`eta_jornada` constante independente de `horas_dia`) | O usuário fixou a perda como tempo absoluto (30 min), não como fração — regimes com jornadas diferentes devem ter fatores diferentes, não o mesmo percentual. |
| A3 | Recalibrar `custo_hora_total_referencia`/`valor_horario_canonico` para absorver a perda e manter o PU de catálogo estável | Rejeitada explicitamente pelo usuário: a ineficiência horária deve afetar apenas o preço unitário operacional, seguindo o mesmo padrão já usado para clima e calendário — o catálogo permanece a fonte de verdade de custo/PU nominal. |
| A4 | Granularidade por atividade/recurso (campo na `Producao`/CPU em vez de `RegimeTrabalho`) | Sem caso de uso demonstrado hoje; a cardinalidade Producao:CPU M:1 tornaria a modelagem mais complexa sem benefício claro. Pode ser revisitada em ADR futura se surgir necessidade real. |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Rastreabilidade preservada | `eta_jornada` fica auditável separadamente de `η_clima`/`δ`, seguindo o padrão de decomposição causal explícita estabelecido pela ADR-124 |
| Sem risco de cascata no catálogo | Por não tocar a calibração de PU/custo, não há risco de disparar `VAL-PROD-INCONSISTENCIA` em cascata (risco identificado e descartado nesta decisão) |
| `horas_dia` mantém semântica única | Continua representando jornada contratual/paga; a perda produtiva é explícita, não embutida |
| Precedente reaproveitado | Mesma camada (`_build_dist_cell`), mesmo padrão de fator multiplicativo determinístico — sem reestruturação arquitetural |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Mudança de comportamento em projetos já materializados | Eliminado por design (D5): migração explícita grava `0.0` antes da troca de default; specs existentes só adotam a ineficiência se editados/recriados deliberadamente |
| Script de migração rodar fora de ordem (default `0.5` já em produção antes da migração gravar `0.0`) | Ordem de deploy explícita no plano: F0 (migração) antes de F1 (troca de default no modelo) |
| Divergência entre custo (hora paga) e produção (hora produtiva) já existe estruturalmente (D4) e fica mais visível | Aceita como modelo correto pelo usuário; não é uma regressão introduzida por esta ADR, apenas mais um fator que a expõe |
| `additionalProperties: false` em `config/schemas/projeto_spec.schema.json` rejeita o campo novo se o schema não for atualizado junto | Atualizar o schema no mesmo commit da mudança de modelo (Fase 1) |
| ~10 pontos de entrada em presentation (API/MCP/Streamlit/CLI) ficam sem o campo até serem propagados | Mapeados no Plano de Implementação; tratar como mecânico, não bloqueante para o motor de cálculo |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F0 | Script de migração idempotente (`scripts/dev/migrate_horas_improdutivas_dia.py`): grava `horas_improdutivas_dia: 0.0` em `escopos/*/meta.json` e `<versao>/canonical.json` — executa **antes** de F1. Escopo: backend `filesystem` apenas (backends remotos — Azure/SharePoint/S3, ADR-047 — precisam de migração equivalente via `BlobStoragePort`, não coberta por este script). Versões aprovadas (chmod 444) são listadas mas não editadas automaticamente — decisão de desbloqueio é manual/auditada | ✅ Implementado (script), execução contra dados reais pendente de decisão do operador |
| F1 | Campo `horas_improdutivas_dia` em `RegimeTrabalho` (default `0.5`) + `model_validator`; `config/schemas/projeto_spec.schema.json` atualizado | ✅ Implementado |
| F2 | `eta_jornada`/`fator_jornada` aplicado em `_build_dist_cell` (`_custos.py`, novo campo em `DistribuicaoSemanal`); propagado a `_scheduling.py`, `_validacao.py` e `_compute_productive_weeks` (`_calendario.py`, ADR-072) | ✅ Implementado |
| F3 | `WorkforcePolicySimulator.simulate()` (`mobilizacao_simulator.py`) e o helper de simulação stateless da API (`_cs_simulate_mobilizacao_policy`) atualizados para consumir `eta_jornada` | ✅ Implementado |
| F4 | Propagação: API (`schemas.py`, `routes/formulario.py`), MCP tools (`formulario.py`, `projeto.py`, `escopo.py`), Streamlit (`formulario_qqp_page.py`), `formulario_service.py`, `project_input_builder.py`, `ProjectStore`/`StorageProjectRepository`/`FileProjectRepository.create_escopo`. `replan.py` (lever de replanejamento) e CLI não têm entry point de criação de projeto com regime — fora de escopo (confirmado, não há gap) | ✅ Implementado |
| F5 | Testes novos: `test_adr148_horas_improdutivas_dia.py` (domain/RegimeTrabalho), `test_adr148_eta_jornada.py` (`_build_dist_cell`/`_compute_productive_weeks`), `TestSimulatorEtaJornada` em `test_mobilizacao_simulator.py`; fixtures pré-existentes ajustadas (`tests/conftest.py`, `test_skill_04_wmp_integration.py`, `test_adr068_calendario_operacional.py`, `test_skill04_cov2.py`) para isolar o novo fator quando não é o alvo do teste | ✅ Implementado |

---

## Definition of Done

### Fase 0
- [x] Script de migração roda contra todos os specs persistidos (backend filesystem) e grava `horas_improdutivas_dia: 0.0` explicitamente em escopo meta e canonical.json de versões draft
- [x] Script é idempotente (validado: rodar duas vezes não altera specs já migrados)
- [x] Versões aprovadas (imutáveis) são reportadas, não editadas silenciosamente
- [ ] Execução real do script contra `projects_root` de produção/dev — pendente de decisão do operador (fora do escopo desta implementação de código)
- [ ] Migração equivalente para backends remotos (Azure/SharePoint/S3) — não implementada nesta ADR

### Fase 1
- [x] `RegimeTrabalho.horas_improdutivas_dia` com default `0.5`, aceitando `0 ≤ horas_improdutivas_dia < horas_dia` (0.0 é o valor de migração de specs legados; `>0` é a recomendação para specs novos, reforçada na apresentação)
- [x] Schema `projeto_spec.schema.json` aceita o campo novo sem rejeitar specs existentes (default aplicado)

### Fase 2
- [x] `eta_jornada` calculado e multiplicado em `praticabilidade` dentro de `_build_dist_cell`, ao lado de `fator_clima`/`fator_calendario`; exposto como `DistribuicaoSemanal.fator_jornada`
- [x] `producao_semanal_base` (nominal) permanece inalterado; `_compute_productive_weeks` usa `eta_jornada` diretamente na fórmula de duração (D2-bis) — comportamento distinto e deliberado de clima/calendário, documentado
- [x] Nenhuma alteração em `custo_hora_total_referencia`, `valor_horario_canonico` ou `_apply_producao_canonico` — suíte completa (14.027 testes) passa sem regressão nesses pontos

### Fase 3
- [x] `WorkforcePolicySimulator.simulate()` produz `qtd(t)` reduzida pelo mesmo fator (`eta_jornada`, default 1.0 — sem regressão); testado em `TestSimulatorEtaJornada`

### Fase 4
- [x] Campo exposto e persistido nos pontos de entrada mapeados (API REST, MCP tools, Streamlit, serviços de aplicação, storage local); CLI e `replan.py` confirmados fora de escopo (sem entry point de criação de regime)

### Fase 5
- [x] Suíte de testes cobre: cálculo de `eta_jornada` para múltiplos regimes (6h/8h/10h), validação de limite (`horas_improdutivas_dia >= horas_dia` → erro), não-regressão de custo/PU (suíte completa verde, exceto 11 falhas pré-existentes não relacionadas em `test_adr115_procurement_rfx.py`, confirmadas na baseline sem esta ADR)

---

## Relacionados

- ADR-068 — Calendário Operacional (`fator_calendario` = δ, precedente direto de fator determinístico na mesma camada)
- ADR-072 — Duração Produtiva e Restrição de Janela de Corredor (consumidor de `producao_semanal_base`)
- ADR-124 — Reformulação do Modelo de Eficiência: Planejamento vs. Controle (framework `η_plan = η_clima · δ` que este ADR estende com `eta_jornada`)
