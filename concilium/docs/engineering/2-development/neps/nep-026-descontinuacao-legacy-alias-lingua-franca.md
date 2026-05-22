# NEP-026: Descontinuação de legacy/alias e consolidação da língua franca de contratos

**Status:** Concluído  
**Prioridade:** 🔴 Crítico  
**Área:** Arquitetura e Skills  
**Tipo:** Governança + Refactor  
**Esforço:** XL  
**Identificado em:** 2026-05-22

---

## Contexto

O código-fonte acumulou múltiplos caminhos de leitura para os mesmos conceitos de domínio
(ex.: aliases e formatos legados para EAP, CPU, cronograma, artefatos e comandos).

Esse padrão gera:

1. ambiguidade semântica entre camadas (API, domínio, UI, scripts),
2. dificuldade de auditoria e rastreabilidade,
3. risco de regressão silenciosa por fallback implícito,
4. aumento de custo de manutenção e de onboarding.

Foi feito inventário técnico de ocorrências de legacy/alias em `src/`, `tests/` e `scripts/`,
com hotspots em modelos de domínio, rotas de alias, comandos CLI e helpers de UI.

## Objetivo

Estabelecer contrato canônico único por entidade e remover fallback distribuído,
preservando compatibilidade apenas em fronteiras controladas e temporárias.

## Decisão

1. Definir uma língua franca de contratos por entidade, com schema único e versionado.
2. Concentrar compatibilidade legada somente no backend de entrada (normalização explícita).
3. Eliminar aliases em camadas consumidoras (UI, domínio interno e fluxos de execução).
4. Tratar campos legados como erro de contrato após janela de transição.
5. Remover rotas/comandos alias públicos após depreciação anunciada.

## Contratos canônicos iniciais

### EAP (benchmark reference)

- caminho oficial: `cpus.itens_eap`
- item oficial: `item_id`, `ordem`, `cpu_id`, `descricao`, `unidade`, `quantitativo`

### CPU (catálogo)

- identificador oficial: `codigo`
- produção oficial: `producao_id_ref` (e vínculo em `producoes`)
- composição oficial: `composicao_itens`

### Tema visual

- objeto oficial de tema em contrato próprio
- serialização para exportadores apenas enquanto ponte temporária de compatibilidade

## Plano de implementação

### Fase 1 - Congelamento de contrato (sem quebra externa)

1. Publicar matriz canônica por entidade (campos obrigatórios, opcionais e removidos).
2. Marcar leituras legadas com warning estruturado e código de validação.
3. Garantir que consumidores internos usem apenas contrato canônico.

### Progresso da Sprint 1 (2026-05-22)

- [x] Matriz canônica publicada por entidade (documento de sprint)
- [x] Leitura legada de EAP marcada com warning estruturado e código
- [x] Consumo interno de EAP/CPU na UI consolidado no contrato canônico

### Fase 2 - Depreciação controlada

1. Expor sinalização de depreciação em rotas/comandos alias.
2. Ativar flag de ambiente para bloquear legacy em ambientes internos.
3. Atualizar testes para refletir canônico como comportamento default.

### Progresso da Sprint 2 (2026-05-22)

- [x] Bloqueio de payload legado em benchmark reference com código explícito
- [x] Testes ajustados para default canônico
- [x] Validação intermediária registrada

### Fase 3 - Remoção definitiva

1. Remover normalizações legadas fora das fronteiras aprovadas.
2. Remover endpoints/comandos alias descontinuados.
3. Converter testes de backward compat em testes de erro explícito de contrato inválido.

### Progresso da Sprint 3 (2026-05-22)

- [x] Endpoints alias de artefatos removidos
- [x] Comando CLI alias removido
- [x] Conversão de testes para falha explícita em payload legado
- [x] Validação intermediária registrada

## Critério de aceite

1. Cada entidade alvo possui contrato canônico documentado e validável.
2. UI e domínio não dependem de aliases de campo para funcionamento normal.
3. Fallbacks legados ficam restritos a um ponto de entrada por entidade (ou nenhum).
4. Rotas e comandos alias possuem data de retirada e plano de comunicação.
5. Suite de testes cobre sucesso no canônico e falha explícita para payload inválido.

## Riscos

1. Quebra de integrações que ainda dependem de aliases não mapeados.
2. Dados históricos com formato parcial exigindo migração adicional.
3. Mudanças transversais em domínio + UI + CLI no mesmo ciclo.

## Mitigações

1. Janela de depreciação com telemetria de uso de caminhos legados.
2. Scripts de migração idempotentes para payloads históricos.
3. Rollout por entidade, com feature flags e checkpoints por sprint.

## Evidências iniciais

- `src/concilium/domain/models/canonical.py` (retrocompat e legacy fields)
- `src/concilium/presentation/api/routes/analysis.py` (rotas alias)
- `src/concilium/presentation/cli/commands_validate.py` (aliases PT-BR)
- `src/concilium/presentation/ui/helpers/helpers.py` (mapeamento de aliases)
- `scripts/migrate_overlays.py` e `scripts/sicro_inject.py` (migração/ingestão legada)

## Evidências da Sprint 1

- `docs/engineering/2-development/implementation_plan/sprint-1-matriz-contratos-canonicos.md`
- `src/concilium/application/services/project_service.py`
- `src/concilium/presentation/ui/helpers/helpers.py`
- `src/concilium/presentation/ui/organisms/layout.py`
- `tests/unit/test_benchmark_reference_contract.py`

## Evidências da Sprint 2 e 3

- `docs/engineering/2-development/implementation_plan/sprint-2-3-validacoes-intermediarias.md`
- `src/concilium/application/services/project_service.py`
- `src/concilium/presentation/api/routes/analysis.py`
- `src/concilium/presentation/cli/commands_validate.py`
- `src/concilium/presentation/main.py`
- `tests/unit/test_benchmark_reference_contract.py`
