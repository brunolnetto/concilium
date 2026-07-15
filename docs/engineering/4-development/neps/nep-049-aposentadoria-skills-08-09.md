# NEP-049 — Aposentadoria das Skills Dormentes 08 (Avaliação de Intervenções) e 09 (Registro de Decisões)

**Data:** 2026-07-14
**Status:** ✅ Implementado _(2026-07-14)_
**Contexto:** Skills dormentes desde NEP-041 F3 (2026-06-09); auditoria de viabilidade de 2026-07-14
**Relacionado:** NEP-041 (consolidação 15→11 skills), ADR-070 (exploração determinística — dependência declarada e já implementada), ADR-082 (levers), skill 11 (cenários), `simular_cenario_replan`

---

## Decisão

Aposentar (remover) as skills `08-avaliacao-intervencoes` e `09-registro-decisoes`. O pipeline
passa de 11 manifests (9 ativos + 2 dormentes) para **9 manifests, todos ativos**. Nenhuma
funcionalidade em uso é perdida — ver "Caminhos de preservação".

## Motivação (dossiê da auditoria de 2026-07-14)

As duas skills estavam dormentes desde a NEP-041 F3 com o motivo "aguarda loop de feedback de
agente (ADR-070)". A ADR-070 foi implementada em 2026-06-27 e **ninguém revisitou a dormência**
— sinal de que a demanda não existia. A auditoria confirmou que o problema não é regressão
técnica (nenhuma foi quebrada por ADR-124/136/137/138/139 ou NEP-043), e sim **desconexão
estrutural do resto do sistema**:

### Skill 08 — obsoleta

1. **Input obrigatório sem produtor real**: `intervencoes_propostas` não é produzido por
   nenhuma skill, tool MCP ou agente. O único "produtor" era um stub de benchmark
   (`benchmarks/spec/spec_loader/_inputs.py`) com **shape divergente** do que a skill lê
   (`nome/custo_estimado` vs `intervencao_id/variavel/tipo_perturbacao`) — geraria
   assessments degenerados.
2. **ROI hardcoded**: a matriz ROI×Effort×Risk usava dicionários fixos por string de
   perturbação (`"+10%" → (1.5, −15)`), desconectados de qualquer motor de simulação.
3. **Output sem consumidor**: `intervention_assessments` não era lido por skill 10,
   relatórios, MCP nem UI.
4. **Superada por**: skill 11 (`ReplanSugestao` com `delta_margem_estimado`/`confianca`) +
   tool MCP `simular_cenario_replan` + ADR-070 — avaliação de intervenção com simulação
   real em vez de heurística fixa.

### Skill 09 — viável porém órfã

1. Dependências declaradas no `skill.toml` eram **stale**: o código não lia
   `resultado_reconciliado` (o modelo `ResultadoReconciliado` é LEGADO/zerado), `resultado`
   nem `conflitos_pico`.
2. **Output terminal**: `decision_log.json` era persistido pelo runtime mas nunca lido por
   nenhum consumidor.
3. **Superada por**: `aprovar_versao` + `AuditService.log_version_action` + versionamento
   append-only — registro de decisão humana **integrado ao ciclo de vida da versão**, com
   trilha de auditoria, em vez de um JSON solto.

## Caminhos de preservação (se a demanda surgir)

- **Matriz de decisão ROI×Effort×Risk (UX da 08)**: renasce como camada fina sobre os deltas
  reais da skill 11 / `simular_cenario_replan` — nunca reativar a heurística hardcoded.
- **Registro de decisão (09)**: dobrar no fluxo `aprovar_versao`/`AuditService`; se for
  necessário registro desacoplado de aprovação de versão, redesenhar com consumidor
  explícito (ex.: seção no relatório da skill 10).

## Mudanças

1. Remoção dos diretórios `src/concilium/application/skills/manifests/08-avaliacao-intervencoes/`
   e `09-registro-decisoes/` (auto-descoberta remove das `SKILLS`; `phase_classifier` deixa
   de ter dormentes).
2. Remoção do plumbing exclusivo: campos canônicos `intervention_assessments`/`decision_log`,
   persistência de `decision_log.json` no runtime, stubs de benchmark
   (`intervencoes_propostas`, inputs de decisão).
3. Remoção dos testes exclusivos das duas skills; adaptação dos testes de pipeline/registry
   que assumiam 11 manifests ou 2 dormentes.
4. Docs: INDEX de skills/apresentação atualizados (pipeline = 9 skills ativas).

## Riscos e mitigação

- **Snapshots antigos** de canonical com `intervention_assessments`/`decision_log` gravados:
  os modelos canônicos toleram campos extras na leitura (`extra="ignore"`), então snapshots
  históricos continuam carregáveis; os campos simplesmente deixam de ser interpretados.
- **Artefatos `decision_log.json` já persistidos** em projetos: permanecem nos storages como
  arquivos históricos inertes — nada os remove nem os reinterpreta.
- ~~**IDs 08/09 ficam vagos**: numeração de skills não é reutilizada~~ — **superado pelo
  Addendum abaixo (decisão do usuário, 2026-07-14)**.

## Addendum (2026-07-14) — Renumeração para ordem contígua

Decisão do usuário: renumerar para refletir a ordem real de execução, fechando 01–09
contíguo:

| ID antigo | ID novo |
|---|---|
| `11-replanejamento-e-cenarios` | `08-replanejamento-e-cenarios` |
| `10-relatorio-e-artefatos` | `09-relatorio-e-artefatos` |

- `SKILL_ID_ALIASES` (phase_classifier) carrega os mapeamentos legado→novo, então
  callers e dados persistidos com IDs antigos continuam resolvendo via
  `resolve_skill_id`.
- Corrigido de carona o quirk da fase **"Inicialização"** (não constava em
  `_PHASE_ORDER`, jogando a skill 01 para o fim de `CANONICAL_SKILL_ORDER` — inócuo
  apenas porque o runtime filtra 01 do auto-avanço). Ordem canônica agora: 01→…→09.
- Curiosidade de arqueologia: o helper `_handle_skill_09_side_effects` do runtime,
  que servia a `10-relatorio-e-artefatos` com nome defasado, volta a bater com o ID.
