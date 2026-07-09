# ADR-135 — Isolamento de Drive: dados de sistema (auth/distribuição) vs. projetos

**Status:** Parcialmente implementado (código pronto; provisionamento do site/drive dedicado é passo manual pendente)
**Data:** 2026-07-09
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-047 (SharePoint Blob Storage Adapter), ADR-099 (Auth), ADR-123 (Notificação e gestão de dispositivos)

---

## Contexto

Hoje, `auth/` (credenciais de usuários e devices), `distribuicao/` (executáveis do proxy publicados por `build-proxy.yml`) e `projetos/` (dados de todos os projetos) vivem no **mesmo Drive** do SharePoint, sob o mesmo `CONCILIUM__SP_DRIVE_ID`/`CONCILIUM__SP_ROOT_PATH`, com a mesma credencial de Service Principal (ADR-047 §D2).

Isso significa que qualquer credencial ou acesso capaz de ler/escrever em `projetos/` também alcança `auth/` e `distribuicao/` — não há isolamento por permissão, apenas por convenção de prefixo de caminho (`auth_store.py` já documentava isso como intenção, nunca como garantia).

### Ameaça

Não há hoje acesso humano direto ao SharePoint de produção — apenas a aplicação acessa, via API/MCP, com a credencial de Service Principal. Não é uma vulnerabilidade ativa. É um endurecimento preventivo: se acesso humano direto (ex.: um gestor de projeto navegando a biblioteca de documentos no SharePoint) for concedido no futuro para operar em `projetos/`, essa mesma pessoa/permissão alcançaria `auth/` (podendo forjar tokens/roles) e `distribuicao/` (podendo substituir o executável distribuído aos usuários finais) sem que isso fosse intencional.

## Decisão

Separar os dados de **sistema** (`auth/`, `distribuicao/`) dos dados de **projeto** (`projetos/`) em dois sites/Drives distintos do SharePoint, cada um com seu próprio escopo de permissão — em vez de apenas restringir o escopo do App Registration atual (`Sites.Selected`), que mitigaria acesso de terceiros mas não separaria fisicamente os dois tipos de dado nem permitiria conceder acesso humano a `projetos/` sem também expor `auth/`/`distribuicao/`.

### D1 — Duas configurações de Drive, uma credencial

`SharePointSettings` (`src/concilium/infrastructure/settings/_storage.py`) ganha `system_drive_id`/`system_root_path`, lidos de `CONCILIUM__SP_SYSTEM_DRIVE_ID`/`CONCILIUM__SP_SYSTEM_ROOT_PATH`. Ambos **caem para `drive_id`/`root_path`** (as vars existentes) quando não configurados — até o site dedicado ser provisionado, o comportamento é idêntico ao atual, sem risco de regressão.

A credencial (tenant/client id/secret ou certificado) continua única — a app registration precisa apenas ter o novo site concedido (via `Sites.Selected`, ver D3).

### D2 — Novo ponto de construção: `build_system_blob_storage()`

`store_factory.py` ganha `build_system_blob_storage()`, espelhando `build_blob_storage()` mas usando `SharePointBlobStorage.from_env(system=True)` no backend sharepoint. Rewired para usar o Drive de sistema:

- `auth_store.py::get_auth_store()` — auth de usuários/devices.
- `commands_auth.py::_get_proxy_exe_download_urls()` — links assinados dos executáveis do proxy.
- `commands_blob.py::blob put --system` — usado por `build-proxy.yml` para publicar `distribuicao/`.

`projetos/` (via `build_project_repository`/`_build_sharepoint_repository`) e dados por-projeto (`campaign_store`, `tool_invocation_store`, via `build_blob_storage()` genérico) **não mudam** — continuam no Drive de projetos.

Catálogos (`config/catalogos/`) hoje são carregados via `CatalogBackend.LOCAL_JSON` (arquivos versionados em git, copiados para a imagem Docker) — não há wiring de produção usando `CatalogBackend.SHAREPOINT`. Se esse backend for ativado no futuro, deve injetar `SharePointBlobStorage.from_env(system=True)`.

### D3 — Provisionamento (passo manual, fora do código)

Pendente de execução por um administrador do Microsoft 365/SharePoint da MendesLobo:

1. Criar um novo site do SharePoint dedicado a dados de sistema do Concilium (ex.: `Concilium-Sistema`), com seu próprio Drive.
2. Conceder ao App Registration existente (mesmo `CONCILIUM__SP_CLIENT_ID`) acesso `Sites.Selected` a esse novo site — **não** `Sites.Read/ReadWrite.All` tenant-wide, para não recriar o mesmo problema (ver ADR-047 R4, mitigação nunca implementada; esta ADR complementa aquela).
3. Migrar `auth/` e `distribuicao/` do Drive atual para o novo Drive (`concilium ops blob migrate --source-backend sharepoint --target-backend sharepoint --prefix auth/`, análogo para `distribuicao/` — origem lê do Drive atual via `CONCILIUM__SP_*`, destino escreve no novo via `CONCILIUM__SP_SYSTEM_*` setados no ambiente do comando).
4. Configurar `CONCILIUM__SP_SYSTEM_DRIVE_ID`/`CONCILIUM__SP_SYSTEM_ROOT_PATH` (App Settings do Container App em produção; `secrets.CONCILIUM__SP_SYSTEM_DRIVE_ID`/`vars.CONCILIUM__SP_SYSTEM_ROOT_PATH` no GitHub Actions para `build-proxy.yml`).
5. Opcional (defesa em profundidade complementar): revisar se o App Registration pode ser restrito a `Sites.Selected` também no Drive de projetos existente, eliminando o escopo tenant-wide de `Files.ReadWrite.All` documentado como risco aceito em ADR-047 R4.

Até o passo 4 ser feito, o sistema continua funcionando exatamente como hoje (fallback para o Drive único) — este ADR não bloqueia nem exige uma janela de manutenção para o código já mergeado.

## Consequências

### Positivas

- Acesso humano futuro a `projetos/` (caso concedido) não alcança `auth/`/`distribuicao/` automaticamente.
- Comprometimento do Drive de projetos não permite forjar tokens de auth nem substituir o executável distribuído a usuários finais.
- Mudança é aditiva e faseada — código e provisionamento são passos independentes.

### Negativas / Riscos

- Duas credenciais/Drives para operar aumenta a superfície de configuração (mais variáveis de ambiente a manter corretas em produção e CI).
- A separação de fato só existe após o provisionamento manual (D3) ser executado — até lá, é apenas a capacidade de isolar, não isolamento real.

## Referências

- ADR-047 — SharePoint Blob Storage Adapter (R4: risco de permissão tenant-wide, mitigação `Sites.Selected` nunca implementada).
- ADR-099 — Auth store.
- ADR-123 — Notificação e gestão de dispositivos (fluxo de `claude_desktop_config.json` por e-mail, usa `distribuicao/` para links de download).
