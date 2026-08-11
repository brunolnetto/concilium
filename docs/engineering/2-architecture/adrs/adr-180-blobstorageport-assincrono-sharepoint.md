# ADR-180 — BlobStoragePort Assíncrono — Fase 1: SharePoint

**Status:** Parcialmente Implementado _(F1-F4 ✅; F5 ✅ em forma reduzida — ver Nota de Implementação)_
**Data:** 2026-08-10
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-047 (Unificação BlobStoragePort), issue #147, issue #148, issue #149

---

## Contexto

### Problema

P1. **Três mitigações no mesmo dia (2026-08-10) sobre o mesmo sintoma raiz, sem resolvê-lo.** Issue #147 adicionou `timeout=` explícito em todas as chamadas `httpx` de `SharePointBlobStorage` (antes, algumas dependiam do default do httpx). Issue #148 tornou `ping()`/`listar_projetos()` `async def`, delegando o corpo síncrono a `asyncio.to_thread` — o worker único do `concilium-mcp` parou de travar por inteiro quando uma chamada de storage trava. Issue #149 envolveu esse `to_thread` com `asyncio.wait_for(timeout=45s)` — o tool passa a falhar rápido e claro em vez de ficar pendurado. Mesmo com as três em produção, uma `CallToolRequest` ficou presa por 12+ minutos no mesmo dia, sem nenhuma linha de log intermediária (sem retry, sem exceção). Causa: o `timeout=` do httpx é **por-operação** (connect/read/write/pool individualmente), não um deadline total da requisição — uma resposta que "goteja" bytes lentamente (rede degradada, proxy corporativo) evita esse timeout indefinidamente. `asyncio.wait_for` sobre um `to_thread` não resolve isso: ele abandona a *espera* pelo resultado, mas não mata a thread — ela continua rodando, presa no mesmo I/O bloqueante, consumindo um slot do thread pool até eventualmente resolver sozinha (ou nunca).

P2. **`BlobStoragePort` tem 6 implementações e ~40+ call sites fora do MCP** (CLI síncrona via Click/Typer, `infrastructure/observability/` — checkpoint_store, gold_aggregator, pipeline —, `catalog/excel_ingestion.py`, `deploy_log_store.py`, `storage/campaign_store.py`). Tornar o port inteiro assíncrono cascateia `async`/`await` por toda essa árvore, incluindo entry points hoje síncronos, e provavelmente exige retocar uma fração grande da suíte de ~14.700 testes — desproporcional ao incidente real e já descartado como fix pontual na issue #149.

P3. **SharePoint é o único backend relevante aos três incidentes de hoje.** Produção roda com `CONCILIUM__STORE_BACKEND=sharepoint`; os outros 5 backends (local, S3, Azure, GDrive, cloud) têm perfis de latência/uso completamente diferentes e não são exercitados pelo caminho de rede que causou os hangs.

P4. **Cancelamento real exige I/O nativamente assíncrono.** `asyncio.wait_for` só interrompe de verdade uma coroutine que está em um `await` — quando o trabalho protegido é uma thread (`to_thread`), não há como o eventloop "matar" essa thread; o máximo que se consegue é parar de *esperar* por ela. Um cliente HTTP async (`httpx.AsyncClient`) dentro de uma coroutine, ao ser cancelado, de fato fecha o socket subjacente.

## Decisão

D1. Introduzir um novo port `AsyncBlobStoragePort` (ABC, `src/concilium/domain/repositories/async_blob_storage_port.py`), espelhando 1:1 os métodos de `BlobStoragePort` (`ler_blob`, `gravar_blob`, `listar_blobs`, `blob_existe`, `deletar_blob`, `aprovar_versao`, `gerar_url_temporaria`, `ensure_root_path`, `health_check`) como `async def`. **Coexiste** com o port síncrono legado — não o substitui, não remove nenhuma implementação existente. Este é o modelo de migração incremental referenciado na issue #149 (dois ports convivendo, consumidores migram um de cada vez).

D2. Implementar `AsyncSharePointBlobStorage` (`blob_storage/sharepoint_async.py`) usando `httpx.AsyncClient` ponta a ponta:
   - Retry com backoff via `asyncio.sleep` (não `time.sleep`) — mesma política de status transitório (429/502/503/504) e mesmos delays de `sharepoint.py`.
   - Cache local ETag+TTL (`_BlobCache`) permanece **síncrono** — é I/O de disco local, não de rede; não é a origem dos hangs observados e não justifica a complexidade de um cache assíncrono (ver A4).
   - Mesma lógica de upload em chunks (`_gravar_upload_session`) e mesmos limiares (`_LARGE_FILE_THRESHOLD`).

D3. `SharePointCredential.acquire_token()` (MSAL `ConfidentialClientApplication`) **permanece síncrono internamente** — a biblioteca MSAL não é async-native e reescrevê-la está fora de escopo. Chamado via `asyncio.to_thread` a partir do código async — aceitável porque o MSAL já cacheia o token internamente e só bate na rede quando expira (janela de exposição pequena, já com timeout de 15s explícito desde antes desta ADR).

D4. `store_factory.py` ganha `build_async_blob_storage()`: retorna `AsyncSharePointBlobStorage` quando `CONCILIUM__STORE_BACKEND=sharepoint`; para qualquer outro backend, levanta `NotImplementedError` explícito. **Sem fallback silencioso** para sync-via-`to_thread` dentro dessa função — isso reintroduziria exatamente o problema que esta ADR resolve (thread presa sem cancelamento real). O fallback é responsabilidade do chamador (D5).

D5. `ping()`/`listar_projetos()` tentam `build_async_blob_storage()` primeiro; se o backend não for SharePoint (`NotImplementedError`), caem para o caminho síncrono existente (`to_thread` + `wait_for` de #148/#149, inalterado). Quando o caminho async é usado, o deadline (`TOOL_IO_TIMEOUT_S`, já existente em `_context.py`) passa a envolver uma coroutine nativa — cancelamento de verdade, não abandono de thread.

D6. **Escopo desta fase: só as duas tools que motivaram #148/#149.** Os ~40 call sites restantes (D2/P2) não fazem parte desta ADR. Critério de expansão para fases futuras: repetir o padrão D1-D5 por consumidor, um de cada vez — nunca big-bang no port inteiro.

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Migrar `BlobStoragePort` inteiro (6 implementações, ~40+ call sites) de uma vez | Rejeitada — já descartada na issue #149 por desproporção de risco/escopo (P2). |
| A2 | Manter `BlobStoragePort` síncrono e usar um bridge `asyncio.run()` interno dentro de `SharePointBlobStorage` | Rejeitada — explicitamente descartada na issue #149 ("Não fazer"): adiciona complexidade (dois runtimes de I/O coexistindo) sem entregar cancelamento real, que é o objetivo desta ADR. |
| A3 | Timeout "duro" via `signal.alarm`/thread killing para matar a thread presa do caminho síncrono atual | Rejeitada — não portável (Windows), frágil em processos multi-thread, e não ataca a causa raiz (I/O ainda bloqueante). |
| A4 | Cache local (`_BlobCache`) também assíncrono via `aiofiles` | Rejeitada — I/O de disco local é rápido e não é a origem dos hangs observados; nova dependência para benefício marginal. |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Cancelamento real | `asyncio.wait_for` sobre uma coroutine `httpx.AsyncClient` fecha o socket de verdade — não deixa uma thread presa consumindo recursos indefinidamente. |
| Escopo contido | Só SharePoint, só duas tools — sem cascata de `async`/`await` pela CLI/observability/catalog. |
| Caminho de fallback preservado | Backends não-SharePoint continuam funcionando exatamente como hoje (`to_thread`+`wait_for`), sem regressão. |
| Base para expansão futura | D1 (port novo coexistindo) estabelece o padrão de migração incremental para quando outros consumidores/backends forem priorizados. |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Dois códigos-cliente SharePoint coexistindo (`sharepoint.py` síncrono + `sharepoint_async.py` novo) — risco de drift (bug corrigido em um, não no outro) | Suíte de testes parametrizada rodando os mesmos cenários (mock de respostas do Graph) contra as duas implementações (F5 do plano). |
| MSAL (D3) ainda roda em thread — janela residual de hang na aquisição de token | Timeout de 15s já existente (`_MSAL_HTTP_TIMEOUT_S`) limita o pior caso; risco muito menor que o do I/O de dados (token é cacheado, raramente bate rede). |
| `NotImplementedError` em `build_async_blob_storage()` para outros backends pode ser esquecido por um chamador futuro que não trate a exceção | Documentar claramente no docstring; D5 é o único caller hoje e trata explicitamente — revisão de code review para novos callers. |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `AsyncBlobStoragePort` (ABC) — mesmos métodos de `BlobStoragePort`, `async def` | ✅ |
| F2 | `AsyncSharePointBlobStorage` — `httpx.AsyncClient`, retry via `asyncio.sleep`, cache local síncrono reaproveitado | ✅ |
| F3 | `store_factory.build_async_blob_storage()`/`build_async_system_blob_storage()` — só SharePoint, `NotImplementedError` para os demais | ✅ |
| F4 | `ping()`/`listar_projetos()` tentam o caminho async primeiro, fallback para `to_thread` existente | ✅ _(ver Nota de Implementação — `listar_projetos` precisou de um mirror dedicado, não reaproveitou `StorageProjectRepository`)_ |
| F5 | Suíte de testes cobrindo os comportamentos-chave de `AsyncSharePointBlobStorage` + a fiação nas 2 tools | ✅ _(forma reduzida — ver Nota de Implementação)_ |

## Definition of Done

### Fase 1-3
- [x] `AsyncBlobStoragePort` declara os 9 métodos de `BlobStoragePort` como `async def`, mesma assinatura de parâmetros
- [x] `AsyncSharePointBlobStorage` implementa todos os métodos do port novo
- [x] Teste: retry transitório (429/503) usa `asyncio.sleep` (não bloqueia o event loop durante o backoff — verificado com uma tarefa concorrente progredindo durante o retry)
- [x] `build_async_blob_storage()`/`build_async_system_blob_storage()` levantam `NotImplementedError` com mensagem clara para backend != sharepoint

### Fase 4-5
- [x] `ping()`/`listar_projetos()` usam o caminho async quando o backend é SharePoint (`build_async_blob_storage()` não levanta `NotImplementedError`)
- [x] Teste: cancelamento via `asyncio.wait_for` de uma chamada `AsyncSharePointBlobStorage` em andamento efetivamente propaga `CancelledError` para dentro da coroutine (não deixa tarefa/thread órfã) — `TestCancelamentoReal` em `test_adr180_sharepoint_async.py`
- [x] Backends não-SharePoint continuam passando pelo caminho `to_thread`+`wait_for` existente, sem regressão de comportamento (testado explicitamente para as duas tools)
- [x] Suíte cobrindo os comportamentos-chave (não uma parametrização literal das duas implementações — ver Nota de Implementação)
- [x] Nenhuma regressão na suíte completa (14.751 testes, fast profile — 14.714 anteriores + 37 novos)

---

## Nota de Implementação

Implementado na mesma sessão da redação desta ADR. Dois ajustes de escopo descobertos durante a implementação (nenhum deles muda D1-D6, só a forma de entrega):

1. **`listar_projetos()` não toca `BlobStoragePort` diretamente** — passa por `StorageProjectRepository`/`StorageProjectHandle` (índice de projetos, `meta.json`, `list_versions()` via `listar_blobs`), uma camada de abstração síncrona compartilhada com outros consumidores (CLI, `iniciar_orcamento`, `consultar_status` etc.) que está fora do escopo D6 desta ADR. Em vez de expandir escopo para uma `StorageProjectRepository` assíncrona genérica (o que reabriria exatamente a discussão de raio de impacto que motivou D6), foi implementado um mirror assíncrono **mínimo e deliberadamente não-genérico** (`_listar_projetos_async` em `projeto.py`) que replica só a leitura read-only necessária (índice + meta + versões) usando `AsyncBlobStoragePort` diretamente. Documentado inline no código como não sendo uma abstração reutilizável.

2. **F5 entregue em forma reduzida.** Em vez de parametrizar a suíte síncrona existente (`test_adr047_sharepoint.py`, ~1560 linhas) para rodar contra as duas implementações, foi escrita uma suíte nova e independente (`test_adr180_sharepoint_async.py`, 20 testes) cobrindo os mesmos comportamentos-chave (leitura com cache/304, retry transitório sem bloquear o event loop, escrita pequena/conflito de ETag, listagem paginada/recursiva, delete, aprovação com checkout/checkin, health_check) mais o teste que justifica a ADR inteira: cancelamento real via `asyncio.wait_for` propaga `CancelledError` para dentro da chamada em andamento. Risco aceito (ver "Negativas/Riscos": drift entre as duas implementações) — mitigação real (parametrização de fato) fica para quando o padrão for expandido a um segundo backend.

3. **`ping()` só migrou o sub-`health_check()`** para o caminho async — as outras duas leituras de storage dentro de `ping()` (carregamento de catálogo via `Runtime.load_catalogo`, e `check_and_report_novidades` via `DeployLogStore`) passam por abstrações mais altas (`Runtime`, `DeployLogStore`) não tocadas por esta ADR, e continuam no caminho síncrono `to_thread` existente. O deadline de `asyncio.wait_for` em `ping()` envolve as duas partes juntas (health async + resto em thread) sob um único timeout, preservando o comportamento de latência total já em produção desde #149.

Verificação: suíte completa (`pytest tests -q -m "not slow and not flaky"`) — 14.751 passed (14.714 anteriores + 37 novos), 0 regressão. `ty check src` e `ruff check` limpos. `lint-imports` confirmado sem violação nova introduzida (as 3 quebras de contrato existentes no repositório são pré-existentes, não tocam nenhum arquivo desta ADR).

## Relacionados

- ADR-047 — Unificação BlobStoragePort (port original que esta ADR estende, não substitui)
- issue #147 — timeout explícito no httpx (mitigação parcial, pré-requisito lógico)
- issue #148 — `ping()`/`listar_projetos()` async + `asyncio.to_thread` (evita outage total; permanece como fallback para backends não-SharePoint)
- issue #149 — deadline de parede via `asyncio.wait_for` (mitigação sem cancelamento real; esta ADR implementa o plano faseado ali proposto)
