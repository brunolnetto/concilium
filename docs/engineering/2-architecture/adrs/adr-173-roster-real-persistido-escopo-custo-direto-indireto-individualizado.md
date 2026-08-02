# ADR-173 — Roster Real de MO Persistido por Escopo + Custo Direto/Indireto Individualizado por Instância

**Status:** Proposta
**Data:** 2026-08-02
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-032 (Entidades Versionadas), ADR-047 (Blob Storage Multi-Backend), ADR-097 (Encargos Sociais), ADR-128 (Logística de Consumíveis — `Escopo.logistica_consumiveis`), ADR-136 (Custo MOB Composicional), ADR-145 (Unificação do Caminho de Escrita de Preço no Catálogo Mestre), ADR-153 (Identidade Física F1), ADR-154/155 (Roster Real — Custo Individualizado MO/EQ), ADR-156/157 (Composição de Funções — Substituição de Roster MO/EQ), ADR-158 (Custo Real por Instância — Timeline), ADR-159 (Wiring Composição Pipeline Real), ADR-160 (Cubo Pool Real Transiente — **D4 revogada aqui**), ADR-165 (Catálogo de Treinamentos/Exames/EPIs/Benefícios de MO), ADR-166 (Wiring de RH no Pipeline de Indiretos)

---

## Contexto

### Problema

P1. ADR-154→160 construíram uma cadeia completa de custo real individualizado de mão de obra — `MembroEquipeReal` (`domain/models/canonical/_roster_mo.py:8`) → `custo_real_mo_semanal`/`_total` (`domain/services/financial/roster_custo_mo.py`, salário-base + encargos via `resolver_encargo`) → `aplicar_roster_custo_real_mo` (`roster_custo_mo_substituicao.py`, substituição integral nunca parcial) → `custo_real_instancia_semanal` (`application/scheduling/custo_real_instancia.py`). Mas a ADR-160 D4 decidiu **explicitamente nunca persistir o roster em lugar nenhum** ("nem catálogo, nem Escopo, nem tabela própria") — `roster_mo`/`roster_eq` são sempre parâmetro transiente de função pura, fornecido por quem chama.

P2. Consequência confirmada por investigação: essa cadeia **nunca foi wireada a nenhum orquestrador real**. Nem `05-equipes-e-alocacao/skill.py` nem `06-resultado-financeiro/_indiretos/skill.py` recebem ou usam roster hoje — só testes unitários (`tests/unit/application/scheduling/test_adr160_cubo_pool_real.py`) exercitam `aplicar_roster_custo_real_mo`/`gerar_timeline_real_instancias`. É código funcional, testado, e dormente.

P3. Em paralelo, ADR-165/166 criaram e wireram custo de RH (EPI, TREINAMENTO, EXAME, BENEFICIO — catálogo mestre, D1-D5 da ADR-165) no pipeline de indiretos (`_composicao_qsms_bottom_up`, `_dimensionamento.py:266`; `_composicao_mob_beneficio_bottom_up`, `_mob.py:78`) — mas **sempre por headcount agregado** de `canonical.equipes_diretas` (número de pessoas por função, não indivíduos), nunca por pessoa real.

P4. O usuário quer duas mudanças, confirmadas nesta conversa via pergunta direta:

- (a) Reabrir a decisão da ADR-160 D4 — quer um roster real de MO **persistido** por projeto, editável ao longo do tempo (admissão/desligamento de pessoas reais), não mais um parâmetro transiente que nenhum caminho de produção fornece.
- (b) Que o custo de **equipe** (direto e indireto) seja uma **agregação** do custo de **instância** (indivíduo, direto e indireto) — não duas fontes de verdade paralelas. Quando o roster cobre uma função por completo, tanto o custo direto (salário+encargos, já existe via ADR-156/157) quanto o indireto (EPI+treinamento+exame+benefício por indivíduo, **não existe hoje**) devem vir da soma dos indivíduos reais daquela função — substituindo a estimativa calibrada/headcount-agregada só para aquela função, nunca uma soma adicional por cima dela (duplicaria custo do mesmo headcount).

P5. Achado de população: `canonical.equipes_diretas.funcoes` (usado pelo bottom-up de QSMS/MOB, skill-06) e `RecursoContrato.composicao_funcoes_mo` (usado pela substituição de custo direto, skill-05) **compartilham a mesma fonte catalográfica** — ambos derivam de `ComposicaoPadraoEquipe` da CPU via `cpu.producao_id_ref` (`_dimensionamento_itens.py:145-160` e `_composicao_por_tipo.py:24-79`, respectivamente). Ou seja: é a mesma população de pessoas vista por dois pipelines diferentes. Qualquer substituição por roster que aconteça só de um lado (ex.: skill-05 substitui custo direto, skill-06 continua estimando indireto por headcount cheio, ou vice-versa) não duplica nem zera custo por si só — mas se o critério de cobertura usado nos dois lados divergir, um lado pode considerar a função "coberta pelo roster" e o outro não, produzindo inconsistência entre o que a equipe custa de fato e o que os dois relatórios (direto/indireto) somam. A substituição precisa usar o mesmo critério de cobertura (`roster_cobre_composicao_mo`) nos dois lados, para a mesma função, na mesma execução.

P6. **Correção pós-investigação de implementação**: a hipótese original desta seção (gap de produção em `StorageProjectHandle`, backend blob) estava errada. Investigação confirmou que **nenhuma tool MCP usa `StorageProjectHandle`** — `presentation/mcp/_context.py:_project()` (usado por toda `presentation/mcp/tools/`, incluindo `gerir_escopo`) sempre instancia `ProjectStore` (`infrastructure/storage/project.py`), puramente filesystem, independente de `CONCILIUM__STORE_BACKEND`. `StorageProjectHandle` (blob/SharePoint) existe no código mas não é o caminho real de escrita/leitura de projeto hoje — é infraestrutura não conectada, ortogonal a esta ADR. Corrigir isso (se um dia for necessário) é trabalho de uma ADR própria de migração de backend, não pré-requisito para o roster funcionar em produção.

P7. **Achado positivo da mesma investigação**: já existe um mecanismo genérico de propagação Escopo→inputs, então grande parte do "wiring" temido não precisa ser construído. `Runtime.run_skill_on_plano` (`application/runtime/mixins/execution.py:120-127`) monta `base_inputs = dict(escopo_meta)` — um spread bruto de **todas** as chaves de `escopo.json` — e sobrepõe com os `inputs` explícitos da chamada, antes de rodar qualquer skill. É assim que `logistica_consumiveis` (ADR-128) chega em `inputs["logistica_consumiveis"]` na skill-04 hoje, sem nenhum código dedicado de "ponte". `roster_mo`, uma vez persistido em `escopo.json` (D2/D3), chega automaticamente em `inputs["roster_mo"]` de qualquer skill executada pelo caminho real (`disparar_pipeline` → `avancar_plano` → `run_skill_on_plano`) — sem precisar de nenhuma mudança em `execution.py`. Ressalva conhecida (mesma limitação que `logistica_consumiveis` já tem, não nova): o caminho legado "flat vN" (`Runtime.run_skill()` direto, via `FlatVersionStore`) usa um proxy de Escopo que só encaminha 4 chaves fixas (`_EscopoStoreProxy`, `flat_version_store.py:21-36`) — `roster_mo` não chega por esse caminho. Aceito como limitação pré-existente, não uma regressão introduzida aqui.

## Decisão

D1. **Supera a ADR-160 D4.** O roster de MO passa a ser dado persistido — a decisão original de mantê-lo transiente partia da premissa de que não haveria necessidade de um registro de pessoas reais entre execuções; essa premissa não se sustenta mais: sem persistência, a cadeia ADR-154→160 nunca teria um caminho de produção que a alimentasse.

D2. Roster é persistido **por `Escopo`**, não por `CanonicalModel`/plano (congelaria ao aprovar um plano — RH real muda independente de replanejamento) e não por `Projeto` inteiro (sem precedente de dado compartilhado entre escopos do mesmo projeto; `logistica_consumiveis`, o precedente mais próximo, também é por Escopo). Novo campo:

```python
roster_mo: list[MembroEquipeReal] = Field(default_factory=list)
```

em `domain/models/project/escopo.py`, mesmo padrão de `logistica_consumiveis` (D-ADR-128 F5, linha 88).

D3. Persistência: `EscopoStore.update_meta()` (filesystem, `escopo_store.py:375-378`) já serve `roster_mo` sem mudança — é um campo Pydantic novo do mesmo model.

D4. **(Revisado — ver P6/P7)** `ProjectStore.create_escopo()` (`infrastructure/storage/project.py:545-593`) ganha parâmetro `roster_mo: list[dict] | None = None`, gravando a chave em `escopo.json` — mesmo padrão de `logistica_consumiveis` (linha 561/588). Não há trabalho de storage blob nesta ADR (P6) — o mecanismo genérico de propagação (P7) já cobre o resto; esta fase inclui um teste de integração ponta a ponta (`create_escopo(roster_mo=...)` → `run_skill_on_plano` → `inputs["roster_mo"]` chega intacto), fechando a lacuna de teste que `logistica_consumiveis` também tinha (nunca provado ponta a ponta pelo `Runtime`, só por chamada direta da função da skill).

D5. Nova ação em `gerir_escopo` (`presentation/mcp/tools/escopo.py:71`) para editar o roster incrementalmente — merge por `individuo_id`, nunca substituição da lista inteira: adicionar um membro novo, ou "desligar" um existente (`data_desligamento` setada), nunca remover um registro já existente da lista (preserva histórico para recomputar custo de semanas já fechadas no passado).

D6. Extrai a lógica de amortização/elegibilidade de RH — hoje duplicada implicitamente entre `_custo_mensal_rh_por_funcao` (EPI/TREINAMENTO/EXAME, `_dimensionamento.py:248`) e `_custo_mensal_beneficio_por_funcao` (BENEFICIO, `_mob.py:55`), ambas privadas dentro de `_skill_helpers` de skill-06 — para um módulo de domínio compartilhado (`domain/services/financial/rh_custo_catalogo.py`), preservando assinatura/comportamento exato (`_rh_insumos_por_tipo`, `_custo_mensal_rh_por_funcao`, `_beneficios_ativos`, `_tipo_contrato_por_funcao`, `_custo_mensal_beneficio_por_funcao`). Skill-06 importa de lá em vez de definir localmente; a nova função por indivíduo (D7) reusa o mesmo módulo — nenhuma lógica de amortização é escrita uma terceira vez.

D7. Novas funções em `domain/services/financial/roster_custo_mo.py`, paralelas a `custo_real_mo_semanal`/`_total`:

```python
def custo_real_mo_indireto_semanal(
    roster: list[MembroEquipeReal], funcao_id: str, semana_inicio: str, semana_fim: str, catalogo: dict | None,
) -> dict[str, float]: ...

def custo_real_mo_indireto_total(...) -> float: ...
```

Para cada membro ativo na semana (mesmo critério de `_membro_ativo_na_semana`), soma o custo mensal amortizado de EPI/TREINAMENTO/EXAME (via `_custo_mensal_rh_por_funcao`, D6) + BENEFICIO (via `_custo_mensal_beneficio_por_funcao`, D6, resolvendo `tipo_contrato` do indivíduo pelo mesmo `_tipo_contrato_por_funcao(catalogo)[membro.funcao_id]` já usado em skill-06), convertido de mensal para semanal (`/ SEMANAS_POR_MES`, mesma constante de `_custo_semanal_membro`). Retorna `0.0` por semana se `catalogo` for `None` ou não tiver itens RH — degradação segura, mesmo padrão de toda a cadeia ADR-165/166.

D8. **Wiring real em skill-05 (custo direto)**: `05-equipes-e-alocacao/skill.py` lê `inputs.get("roster_mo")` (lista de dicts, chega automaticamente via P7 quando `Escopo.roster_mo` está populado — sem novo código de propagação), converte para `list[MembroEquipeReal]` via `model_validate`, e chama `aplicar_roster_custo_real_mo` de fato — hoje nunca invocada em produção. Lógica interna inalterada (substituição integral por função, `roster_cobre_composicao_mo`).

D9. **Wiring real em skill-06 (custo indireto)**: `_composicao_qsms_bottom_up`/`_composicao_mob_beneficio_bottom_up` ganham acesso ao mesmo `roster` (mesmo canal — `inputs.get("roster_mo")`, não um parâmetro novo desconectado). Para cada função em `equipes_diretas`: se `roster_cobre_composicao_mo`-equivalente for verdadeiro para aquela função (headcount do roster ≥ headcount de `equipes_diretas` para a mesma função), o termo daquela função passa a ser `custo_real_mo_indireto_total` (D7) somado sobre os indivíduos reais, em vez de `headcount × _custo_mensal_rh_por_funcao`; senão, mantém o cálculo agregado atual — nunca substituição parcial.

D10. **Disciplina anti-duplicação (resolve P5)**: D8 e D9 usam o mesmo critério de cobertura (`roster_cobre_composicao_mo`) para a mesma função, na mesma execução — se o roster cobre a função, os dois lados (direto em skill-05, indireto em skill-06) usam roster; se não cobre, os dois lados usam o cálculo agregado/calibrado de hoje. Nunca um lado substitui e o outro não para a mesma função — testado explicitamente (ver DoD F7).

D11. **Explicitamente fora de escopo desta ADR**: propagação de `FuncaoEquipe.papel` (`domain/models/catalog/catalogo.py:66-70,306`, valores `"direto"`/`"indireto"`/`"gestao"`) em `_dimensionamento_itens.py:196-206` — hoje toda função de uma CPU é contada como direta independente do `papel` cadastrado no catálogo. Gap pré-existente, não relacionado a este wiring; fica para ADR futura se priorizado.

D12. **`individuo_id` é um identificador opaco de recurso, não um dado de identidade real** (resolve o risco de PII levantado na revisão desta ADR) — decisão do usuário: esta etapa do pipeline é simulação de planejamento, não um sistema de registro de RH; `MembroEquipeReal.individuo_id` não precisa (e não deve) carregar CPF/nome/matrícula real. É exatamente o mesmo tratamento que `InstanciaRecurso`/`AtivoEquipamentoReal` já dão a equipamento (ADR-153/157): um identificador único e estável dentro do Escopo, arbitrário na sua forma (ex.: `"mo-001"`), suficiente para diferenciar instâncias e resolver cobertura/substituição (D8-D10), sem exigir nem armazenar vínculo com uma pessoa do mundo real. `gerir_escopo` (D5) não valida nem exige formato de matrícula/CPF — só unicidade de `individuo_id` dentro do `roster_mo` do Escopo.

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Manter roster transiente (ADR-160 D4 inalterada) — exigir que quem chama a skill forneça roster via `inputs` a cada execução, sem persistência | Rejeitada por decisão explícita do usuário — sem persistência, ninguém em produção jamais fornece esse input; a cadeia ADR-154→160 continuaria dormente. |
| A2 | Persistir roster no `CanonicalModel` (mesmo padrão de `progresso`, ADR-003) | Rejeitada — amarraria o roster ao ciclo de vida do plano (congela ao aprovar); RH real (admissão/desligamento) muda independente de replanejamento. |
| A3 | Persistir roster por `Projeto` inteiro, compartilhado entre Escopos | Rejeitada — sem precedente no repo (todo dado operacional real hoje é por Escopo, ex. `logistica_consumiveis`) e sem necessidade demonstrada; se um projeto tiver múltiplos escopos com equipes de fato compartilhadas, isso é decisão futura, não assumida aqui. |
| A4 | Somar custo de RH tanto no agregado (skill-06) quanto no roster (nova função), de forma aditiva | Rejeitada — duplicaria custo do mesmo headcount coberto por roster; mesmo padrão de risco já identificado e rejeitado na ADR-166 A1 ("dupla contagem do mesmo conceito de benefício para o mesmo grupo de pessoas"). |
| A5 | Corrigir `FuncaoEquipe.papel` (direto/indireto/gestão) nesta mesma ADR | Rejeitada — gap pré-existente e ortogonal a este wiring; expandir o raio de impacto sem necessidade. |
| A6 | ~~Adiar fix do stub de `StorageProjectHandle` para uma ADR separada~~ — **obsoleta**: investigação confirmou que `StorageProjectHandle` não é usado por nenhuma tool MCP hoje (produção real roda via `ProjectStore`/filesystem, P6); não há gap a fechar nesta ADR. | N/A — premissa original (P6 na versão inicial desta ADR) estava incorreta. |
| A7 | Construir um mecanismo novo e dedicado de propagação `Escopo → inputs` para `roster_mo` | Rejeitada após investigação (P7) — `Runtime.run_skill_on_plano` já faz spread de `escopo.json` inteiro em `inputs` para qualquer skill executada pelo caminho real; construir um mecanismo paralelo duplicaria plumbing já existente e testado (mesmo caminho de `logistica_consumiveis`). |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Cadeia ADR-154→160 deixa de ser dormente | Primeira vez que `MembroEquipeReal`/`aplicar_roster_custo_real_mo` são exercitados por um caminho de produção real, não só testes. |
| Custo de equipe = agregação real de instância | Direto e indireto passam a vir da mesma fonte (indivíduos reais) quando disponível, com fallback seguro para o calibrado/agregado — sem duas fontes de verdade paralelas. |
| Zero plumbing novo de propagação | Reusa o mecanismo genérico já existente (`execution.py:120-127`) que já serve `logistica_consumiveis` — `roster_mo` chega a qualquer skill via `inputs` sem nenhum código de "ponte" dedicado. |
| Fecha lacuna de teste pré-existente | Nenhum teste hoje prova `Escopo → Runtime → inputs` ponta a ponta para `logistica_consumiveis`; esta ADR adiciona esse teste também, usando `roster_mo` como caso concreto (F2). |
| Zero duplicação de lógica de amortização RH | `_custo_mensal_rh_por_funcao`/`_custo_mensal_beneficio_por_funcao` passam a ter uma única implementação compartilhada entre skill-06 e o novo cálculo por indivíduo. |
| Histórico de RH preservado | Desligamento nunca remove o registro (D5) — cálculo de custo de semanas passadas permanece reproduzível mesmo após alguém ser desligado. |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Reversão de uma decisão arquitetural anterior (ADR-160 D4) | Documentada explicitamente aqui (D1) com a justificativa de mudança de requisito — não é descoberta de erro, é mudança de necessidade do usuário. |
| ~~Dado de RH real (indivíduo, datas de admissão/desligamento) é potencialmente sensível (PII)~~ — **resolvido (D12)** | Decisão do usuário na revisão desta ADR: `individuo_id` é identificador opaco de recurso de simulação, não dado de identidade real — mesmo tratamento já dado a equipamento (ADR-153/157). Nenhum CPF/nome/matrícula real é exigido ou armazenado. |
| Cobertura divergente entre skill-05 e skill-06 para a mesma função (mesmo com D10) se as duas skills rodarem em momentos diferentes com rosters diferentes | Ambas leem o mesmo `Escopo.roster_mo` na mesma execução de pipeline (mesmo canonical_in/inputs) — risco só existe de fato se o roster for editado no meio de uma execução em andamento, cenário já fora de escopo de qualquer consistência transacional deste sistema. |
| Caminho legado "flat vN" (`Runtime.run_skill()` direto) não propaga `roster_mo` (mesma limitação de `logistica_consumiveis`) | Aceito como limitação pré-existente e não nova — quem precisa de roster real usa o caminho `disparar_pipeline`/`avancar_plano` (Escopo/Plano), que é o caminho de produção real hoje. |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | D2 — `Escopo.roster_mo`, persistência via `EscopoStore` (filesystem) | Pendente |
| F2 | D4 — `ProjectStore.create_escopo(roster_mo=...)` + teste ponta a ponta `Escopo → Runtime → inputs["roster_mo"]` | Pendente |
| F3 | D5 — nova ação em `gerir_escopo` (adicionar/editar/desligar membro do roster) | Pendente |
| F4 | D6 — extração de `_custo_mensal_rh_por_funcao`/`_custo_mensal_beneficio_por_funcao` para `domain/services/financial/rh_custo_catalogo.py`, skill-06 importando de lá (regressão: comportamento idêntico) | Pendente |
| F5 | D7 — `custo_real_mo_indireto_semanal`/`_total` em `roster_custo_mo.py` | Pendente |
| F6 | D8 — wiring real em skill-05 (`aplicar_roster_custo_real_mo` lendo `Escopo.roster_mo`) | Pendente |
| F7 | D9/D10 — wiring real em skill-06 (`_composicao_qsms_bottom_up`/`_composicao_mob_beneficio_bottom_up` aceitam roster, substituem por função coberta, mesmo critério dos dois lados) + teste de não-duplicação | Pendente |

## Definition of Done

### Fase 1
- [ ] `Escopo.roster_mo: list[MembroEquipeReal] = Field(default_factory=list)` — retrocompatível (default vazio, escopos existentes carregam sem alteração)
- [ ] Teste cobrindo: `EscopoStore.update_meta()` persiste e relê `roster_mo` corretamente (filesystem)

### Fase 2
- [ ] `ProjectStore.create_escopo()` aceita `roster_mo: list[dict] | None`, grava `escopo.json["roster_mo"]` (default `[]`, mesmo padrão de `logistica_consumiveis`)
- [ ] Teste cobrindo: `create_escopo(roster_mo=[...])` → `Runtime.run_skill_on_plano` (caminho real, não chamada direta da função da skill) → `inputs["roster_mo"]` chega intacto — prova ponta a ponta do mecanismo de propagação (P7), fechando também a lacuna equivalente que `logistica_consumiveis` tinha

### Fase 3
- [ ] `gerir_escopo` aceita nova ação para roster; merge por `individuo_id` (não substitui lista inteira)
- [ ] Teste cobrindo: adicionar membro novo, editar membro existente, "desligar" (seta `data_desligamento`, não remove), tentativa de remover registro já existente é rejeitada ou ignorada

### Fase 4
- [ ] `_custo_mensal_rh_por_funcao`/`_beneficios_ativos`/`_tipo_contrato_por_funcao`/`_custo_mensal_beneficio_por_funcao` movidas para `domain/services/financial/rh_custo_catalogo.py`, skill-06 importa de lá
- [ ] Teste de regressão: suíte de skill-06 (QSMS/MOB) produz exatamente os mesmos valores antes/depois da extração

### Fase 5
- [ ] `custo_real_mo_indireto_semanal`/`_total` cobrem: comum (EXAME sempre), específico via `funcoes_aplicaveis`, benefício excluído por `aplicavel_tipo_contrato`, catálogo `None`/sem itens RH → `0.0`
- [ ] Teste cobrindo: soma por indivíduo bate exatamente com a soma que `_custo_mensal_rh_por_funcao`/`_custo_mensal_beneficio_por_funcao` produziriam para o mesmo headcount agregado (paridade de fórmula, não só de assinatura)

### Fase 6
- [ ] `05-equipes-e-alocacao/skill.py` lê `Escopo.roster_mo` (via `inputs`) e chama `aplicar_roster_custo_real_mo` de fato
- [ ] Teste cobrindo: sem roster no Escopo, comportamento idêntico ao atual (custo calibrado); com roster cobrindo integralmente, custo direto = soma real dos indivíduos

### Fase 7
- [ ] `_composicao_qsms_bottom_up`/`_composicao_mob_beneficio_bottom_up` aceitam roster e substituem por função coberta
- [ ] Teste cobrindo: mesma função coberta pelo roster produz o MESMO resultado se calculado via skill-05 (direto) ou via `custo_real_mo_indireto_total` (indireto) somando os indivíduos — nenhum indivíduo contado zero ou duas vezes
- [ ] Teste cobrindo: função parcialmente coberta (roster insuficiente) mantém os DOIS lados (direto e indireto) no cálculo agregado/calibrado atual, nunca um substitui e o outro não

## Nota de Implementação

_(preenchida ao final da implementação)_

---

## Relacionados

- ADR-128 — Logística de Consumíveis (`Escopo.logistica_consumiveis`, precedente direto de D2/D3)
- ADR-153 — Identidade Física F1 (fungibilidade do pool RCPSP preservada — este ADR não reabre isso)
- ADR-154/155/156/157/158/159 — Roster Real (cadeia de custo individualizado que esta ADR finalmente conecta a produção)
- ADR-160 — Cubo Pool Real Transiente (D4 revogada por D1 desta ADR)
- ADR-165/166 — Catálogo e Wiring de RH (lógica de amortização/elegibilidade reusada por D6/D7)
