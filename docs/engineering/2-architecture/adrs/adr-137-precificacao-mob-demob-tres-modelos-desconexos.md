# ADR-137 — Precificação de Mobilização/Desmobilização: Três Modelos Desconexos, Sem Base de Custo Real

**Status:** ⚠️ Parcialmente Implementado _(F1/D1 ✅ 2026-07-10; F2/D2 e F3/D3 pendentes — decisão de dado/produto e de demanda real, respectivamente, não de código)_
**Data:** 2026-07-10
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-106 (EquipeCustoEngine — Lifecycle Unificado), ADR-105 (Mobilização e Desmobilização — Política Integrada), ADR-129 (Cotação por Proximidade Geográfica), ADR-073 (Cadeias de Perpetuação), ADR-136 (Custo de Mob/Demob no Pool — F1-F3/F6)

---

## Contexto

### Problema

Este ADR nasce de uma pergunta direta do produto: *"qual é o meu receio sobre a precificação da (des)mobilização?"* — feita depois de mapearmos (ADR-136, ADR-106 F2-bis) **onde** e **quando** o custo de mob/demob é lançado no cronograma financeiro. A pergunta certa, que ainda não tínhamos respondido, é: **de onde vem o número em si — é um custo real, calculado, ou um valor de cadastro genérico?**

O sistema modela mob/demob de três formas distintas e **nenhuma delas deriva o preço de uma lógica de custo real** (peso do equipamento, tipo de transporte, distância efetiva). Todas dependem de um valor digitado em algum ponto anterior do pipeline — só o modelo 3 foi desenhado para calcular por distância, e mesmo esse não é usado na prática pelos projetos reais.

### P1 — Pool de recursos compartilhados: o caminho automático zera o preço silenciosamente

`RecursoContrato.custo_mob_unit`/`custo_demob_unit` (`domain/models/canonical/_pool_recursos.py:145-146`) só recebem valor quando `rcpsp_spec` é fornecido explicitamente com `resource_costs` (input manual/programático, sem validação contra catálogo). Quando o `rcpsp_spec` é **derivado automaticamente** do catálogo — o caminho padrão de produção —, `_derive_rcpsp_from_canonical` (`_pool_contrato_construcao.py:271-314`) **omite `resource_costs` propositalmente** (comentário no código: "custo_unit_semanal derivado de custo_hora_total_referencia do catálogo"), deixando `custo_mob_unit`/`custo_demob_unit` no default `0.0` do modelo Pydantic.

Confirmado em produção: **todo** `RecursoContrato` do projeto AGIS real (`benchmarks/projetos/AGIS/v1/canonical.json`) tem `custo_mob_unit`/`custo_demob_unit` = `0.0`.

Isso não é cosmético — esses dois valores são o **threshold** que a lógica de cadeias de perpetuação (ADR-073, `_perpetuation_chains.py:46,90`) usa para decidir se compensa manter um equipamento parado entre atividades ou desmobilizar e remobilizar depois. Com o threshold sempre zero, essa decisão degenera silenciosamente — sem nenhuma `ValidacaoItem` alertando que a decisão de perpetuação está sendo tomada sem dado de custo de mob/demob real.

### P2 — Equipes diretas sem pool: catálogo com valores uniformes suspeitos de placeholder

`EquipamentoEquipeDireta.custo_mobilizacao`/`custo_desmobilizacao` (`_equipes_diretas.py:46-47`) vêm da composição-padrão de equipe no catálogo (`_build_comp_para_item`, `_dimensionamento_itens.py:48-59`). Inspecionando o catálogo real do AGIS (`benchmarks/projetos/AGIS/snapshots/catalogo-*.json`): **todo** equipamento (escavadeira, caminhão, gerador — qualquer tipo) tem `custo_mobilizacao = R$ 6.500,00`, e **toda** função tem `R$ 800,00`. Não há diferenciação por peso, tipo de transporte ou distância — são dois valores únicos aplicados a qualquer coisa, sem fórmula nenhuma por trás.

### P3 — Indiretos: a fórmula de distância existe no código, mas nenhum projeto real a usa

`_custo_mob_composicional` (`.../06-resultado-financeiro/_indiretos/_skill_helpers/_mob.py:26-47`) calcula `num_unidades × distancia_km × custo_km` por item de `dados_mobilizacao.mobilizacoes` — a única das três fórmulas genuinamente desenhada para precificar por distância real. Mas ao inspecionar **todos** os projetos de benchmark disponíveis (AGIS, SERRA_VERDE, RUMO, ODFJELL, LUNDIN, GOLDEN, VALE), **nenhum** tem essa lista populada (`"mobilizacoes": []` em todos). Na prática, o custo de MOB desses projetos vem de um valor agregado fixo pré-configurado (`categorias_config`/`cat_cfg_raw`, `_mob.py:88-91`), tipicamente herdado da planilha de orçamento original importada — fora do alcance de qualquer cálculo do pipeline.

### P4 — Sem verificação cruzada entre os três modelos

Não existe reconciliação alguma entre os três caminhos. Se o mesmo tipo de equipamento aparece simultaneamente no pool (modelo 1, tipicamente zerado no caminho automático) e como composição de equipe direta (modelo 2, valor uniforme de catálogo), não há nenhuma validação detectando dupla contagem (se ambos os caminhos precificarem o mesmo evento físico) ou subcontagem (mais comum na prática observada — o pool fica em zero e só o catálogo de equipe direta contribui, silenciosamente incompleto).

### P5 — Existe infraestrutura de precificação geográfica pronta, mas desconectada

`MunicipioReferenceClient` (`infrastructure/clients/municipios.py:64`, com `haversine_km`/`municipio_mais_proximo`) já resolve distância entre municípios e é usado para achar o preço de diesel mais próximo por proximidade geográfica (ADR-129, via `geo_diesel_resolver.py`). Esse mesmo mecanismo poderia alimentar `distancia_km` automaticamente a partir de origem/destino em qualquer um dos três modelos — mas não está conectado a nenhum deles.

## Decisão

> Este ADR documenta o achado e propõe direções. D1 foi implementada (F1, 2026-07-10); D2 e D3 seguem como decisões independentes de dado/produto, não de código.

### D1 — Emitir validação explícita quando o pool decide perpetuação com custo de mob/demob zerado ✅

Quando `_perpetuation_chains.py` toma uma decisão de perpetuar (ou não) uma cadeia usando `custo_mob_unit + custo_demob_unit == 0`, emitir uma `ValidacaoItem` de aviso explícito (ex.: `VAL-POOL-MOB-ZERO`) informando que a decisão foi tomada sem dado de custo real — hoje o comportamento é silencioso. Isso não corrige o dado ausente, mas transforma um risco invisível em um risco visível e auditável.

**Implementado (2026-07-10):** `_build_perpetuation_chains` aceita um parâmetro opcional `validacoes` e emite `VAL-POOL-MOB-ZERO` (status `AVISO`) por tipo de recurso quando `custo_mob_unit + custo_demob_unit == 0` e há mais de um item na cadeia (ou seja, uma decisão de gap real está em jogo). O parâmetro é threaded por toda a cadeia de chamadas (`_build_contrato_entry` → `_build_tipo_contrato` → `_build_contratos_por_tipo` → `_build_contratos_recurso`, que já recebia `validacoes`). A decisão de perpetuação em si não muda — só passa a ser auditável. Testes em `tests/unit/test_adr137_val_pool_mob_zero.py`.

### D2 — Revisar os valores uniformes do catálogo (R$ 6.500/R$ 800) com quem mantém os dados de composição

Não é uma decisão de código — é uma tarefa de dado. Alguém com acesso ao processo de cadastro de composições-padrão precisa confirmar se esses valores são um placeholder temporário (nunca revisitado) ou uma escolha consciente de simplificação. Se for placeholder, differenciar por tipo/peso de equipamento é trabalho de dado (preencher o catálogo), não de engenharia.

### D3 — Avaliar conectar `MunicipioReferenceClient` para derivar `distancia_km` automaticamente

Restrito à categoria indiretos (P3), onde a fórmula de distância já existe e é o único caso em que reaproveitar o cliente geográfico (ADR-129) resolveria um gap real de precisão sem inventar um modelo novo — mas só vale a pena se algum projeto real vier a popular `dados_mobilizacao.mobilizacoes` de fato (hoje nenhum popula, então o benefício imediato é zero; a decisão é sobre facilitar a adoção futura, não sobre um problema ativo).

### D4 — Documentar explicitamente que os três modelos não são reconciliados (sem propor unificação agora)

Dado o histórico desta sessão (duas vezes descobrimos tarde que dois "modelos duplicados" eram, na verdade, ou já idênticos ou estruturalmente incompatíveis — ver ADR-136 F5 e A4 deste mesmo ADR), **não propor unificação dos três modelos de precificação neste ADR**. Registrar a ausência de reconciliação como risco conhecido e aceito, não como um TODO de unificação — decisão de escopo, não de omissão.

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Unificar os três modelos de precificação num só, imediatamente | Prematuro — cada modelo resolve um cenário físico genuinamente diferente (recurso compartilhado vs. dedicado vs. overhead de projeto); unificar sem entender se as fontes de preço deveriam mesmo ser as mesmas arrisca introduzir a mesma armadilha de "achar que são iguais quando não são" (ou vice-versa) já cometida duas vezes nesta sessão |
| A2 | Aplicar automaticamente `DEFAULT` constants (ex.: uma tarifa padrão de mob/demob) quando `custo_mob_unit`/`custo_demob_unit` estão zerados no pool | Rejeitado pelo mesmo racional do ADR-106 F5: aplicar um default genérico sem calibração quebraria o baseline calibrado do AGIS e poderia duplicar custo já contabilizado em outro lugar (indiretos) |
| A3 | Bloquear o pipeline (erro, não aviso) quando custo de mob/demob está zerado no pool | Rejeitado — a maioria dos projetos reais hoje roda com esses valores zerados; bloquear quebraria todo benchmark existente sem uma transição planejada. D1 (aviso) é o passo correto antes de considerar um gate bloqueante |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Risco documentado, não mais invisível | Quem olhar este ADR entende que os números de mob/demob no resultado financeiro de hoje não são precificação de engenharia real na maioria dos casos |
| Escopo claro para decisões futuras | D1-D4 podem ser tratadas independentemente, sem exigir um projeto grande de unificação |
| Evita repetir a armadilha desta sessão | A4 registra explicitamente por que não se deve pular direto para "unificar tudo" sem entender as diferenças reais entre os modelos |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Nenhuma decisão deste ADR corrige o número em si — apenas documenta e (se D1 for implementada) alerta | Aceito conscientemente: corrigir o preço real é decisão de produto/dado (D2), fora do escopo de uma correção de código isolada |
| D3 (geografia) só vale a pena se `dados_mobilizacao.mobilizacoes` passar a ser populado por algum projeto real | Não implementar D3 até haver esse sinal de demanda real |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| **F1 — Validação de risco no pool (D1)** | `ValidacaoItem` de aviso quando decisão de perpetuação usa custo de mob/demob zerado | ✅ 2026-07-10 |
| **F2 — Revisão de dado de catálogo (D2)** | Confirmação (fora do código) se R$ 6.500/R$ 800 são placeholder ou escolha consciente | ⬜ |
| **F3 — Geografia para indiretos (D3)** | Avaliar conectar `MunicipioReferenceClient` a `distancia_km`, condicionado a demanda real | ⬜ |

## Definition of Done

### Fase 1
- [x] `_perpetuation_chains.py` emite `VAL-POOL-MOB-ZERO` (ou código equivalente) quando decide perpetuação com `custo_mob_unit + custo_demob_unit == 0`
- [x] Teste cobrindo a emissão do aviso e confirmando que a decisão de perpetuação em si não muda de comportamento (só passa a ser auditável)

### Fase 2
- [ ] Resposta documentada (nesta ADR ou em nota de acompanhamento) sobre a origem dos valores R$ 6.500/R$ 800 no catálogo

### Fase 3
- [ ] Decisão registrada: conectar `MunicipioReferenceClient` aos indiretos, ou explicitamente descartar por falta de demanda real

---

## Relacionados

- ADR-106 — EquipeCustoEngine (F2-bis fecha o gap de *timing* de mob/demob para equipes diretas sem pool; este ADR trata do gap de *preço*, não de timing)
- ADR-105 — Mobilização e Desmobilização (política integrada; §6.6 já documentava lacunas de granularidade, agora complementadas pela lacuna de precificação)
- ADR-136 — Custo de Mob/Demob no Pool (F1-F3/F6 corrigiu os campos mortos de *cálculo*; este ADR mostra que, mesmo calculando corretamente, o insumo de preço em si pode ser zero ou genérico)
- ADR-129 — Cotação por Proximidade Geográfica (`MunicipioReferenceClient`, hoje só usado para diesel — candidato a reaproveitamento em D3)
- ADR-073 — Cadeias de Perpetuação (consumidor direto de `custo_mob_unit`/`custo_demob_unit` como threshold de decisão — o principal afetado por P1)
