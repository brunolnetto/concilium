# ADR-123 — Serviço de Notificação por Email e Gestão de Dispositivos

**Status:** ✅ Implementado _(F1-F5 completas; F3 — detecção de dispositivo desconhecido — implementada em `application/services/device_detection.py`, ligada a `activate_device_code()`/`use_refresh_token()` em `presentation/api/routes/auth.py` e `presentation/mcp/tools/auth_self.py`)_  
**Data:** 2026-06-23  
**Contexto:** MendesLobo Construtora — Concilium  
**Dependências:** ADR-094 (JWT/auth), ADR-099 (RBAC), ADR-116 (MCP surface)  
**Evolução:** ADR-134 substitui os métodos `notify_*` de `NotificationService` (contrato original desta ADR) por
`send(template, context)` genérico com templates Jinja2 — os casos de uso de negócio migraram para
`application/services/notifications.py`.

---

## Contexto

O CRUD de usuários é feito pelo admin via CLI (`concilium ops auth user create/edit/remove`). Após criar um usuário, o admin precisa:

1. Gerar manualmente um `claude_desktop_config.json` com as credenciais corretas.
2. Enviar esse arquivo ao usuário por algum canal externo (email, Slack, etc.).
3. Orientar o usuário a reinicializar o Claude Desktop para ativar o servidor MCP.

Esse processo é completamente manual, frágil e sem rastreabilidade. Além disso:

- Quando um usuário acessa de um dispositivo desconhecido, ninguém é notificado.
- O usuário não tem como revogar o acesso de um dispositivo sem acionar o admin.
- A estrutura multi-dispositivo já existe em `auth_store.py` (`DeviceCodeRecord`, `list_devices()`, `revoke_device()`), mas não está exposta ao usuário.

## Decisão

### F1 — Serviço de notificação por email

Criar `infrastructure/services/notification_service.py` com envio de email transacional.

**Interface mínima:**

```python
class NotificationService:
    async def notify_user_created(self, user: UserRecord, device_code: str) -> None: ...
    async def notify_user_edited(self, user: UserRecord, changes: dict) -> None: ...
    async def notify_user_removed(self, user: UserRecord) -> None: ...
    async def notify_new_device(self, user: UserRecord, device: DeviceRecord) -> None: ...
    async def notify_revoke_pending(self, user: UserRecord, device: DeviceRecord, token: str) -> None: ...
```

**Backend:** SMTP (configurável via `CONCILIUM__SMTP_HOST/PORT/USER/PASSWORD`) com fallback para log estruturado quando SMTP não configurado (dev/CI).

**Variáveis de configuração:**

```bash
CONCILIUM__SMTP_HOST=smtp.sendgrid.net        # [cond] obrigatório se notificações ativas
CONCILIUM__SMTP_PORT=587
CONCILIUM__SMTP_USER=apikey
CONCILIUM__SMTP_PASSWORD=<sendgrid-api-key>   # → Key Vault: smtp-password
CONCILIUM__SMTP_FROM=concilium@mendesloboconstrucao.com.br
CONCILIUM__NOTIFICATIONS_ENABLED=1            # default: 0 em dev
```

### F2 — Email de criação: claude_desktop_config.json gerado automaticamente

> **Nota de implementação (2026-07-13):** o bloco original abaixo era a especificação
> inicial desta ADR e nunca foi atualizado após a implementação real divergir dele —
> ver a versão corrigida logo depois, que reflete `commands_auth.py::_build_mcp_config_block`
> e `application/services/notifications.py` tal como existem hoje.

Ao criar um usuário, o sistema gera dois arquivos `claude_desktop_config.json` (um por SO — o admin não escolhe a plataforma do usuário final na hora do cadastro) pré-preenchidos. Não há pacote `concilium` publicado no PyPI para instalação via `npx`/`pip` na máquina do usuário final — em vez disso, o usuário baixa um executável standalone (PyInstaller, publicado pela workflow `build-proxy.yml`, um build nativo por SO) e salva num caminho fixo local:

```json
// macOS/Linux — salvar o executável em $HOME/.concilium/bin/concilium-mcp-proxy (chmod +x)
{
  "mcpServers": {
    "concilium": {
      "command": "sh",
      "args": ["-c", "$HOME/.concilium/bin/concilium-mcp-proxy"],
      "env": {
        "CONCILIUM_CLIENT_CODE": "<client_code>",
        "CONCILIUM_SERVER_URL": "https://mcp.mendesloboconstrucao.com.br"
      }
    }
  }
}
```

```json
// Windows — salvar o executável em C:\Concilium\concilium-mcp-proxy.exe
{
  "mcpServers": {
    "concilium": {
      "command": "C:\\Concilium\\concilium-mcp-proxy.exe",
      "env": {
        "CONCILIUM_CLIENT_CODE": "<client_code>",
        "CONCILIUM_SERVER_URL": "https://mcp.mendesloboconstrucao.com.br"
      }
    }
  }
}
```

`CONCILIUM_DEVICE_CODE` é o nome legado dessa mesma variável (pré-#17) — o proxy ainda a aceita como fallback (`_mcp.py::McpProxySettings.from_env`), porque configs já distribuídos antes do rename continuam em uso em máquinas de usuários reais e não estão sob nosso controle para migrar retroativamente.

O email de boas-vindas anexa: os dois JSONs crus (fallback), o executável do proxy zipado junto com o JSON já preenchido para aquele SO (quando os zips cabem no limite de 18MB da mensagem — `notifications.py::_zips_fit_in_email`), e o tutorial de uso. Instruções para o usuário:
1. Baixar o executável do proxy do link enviado (válido por 7 dias, `scope="organization"` — abre só com login M365 da empresa) e salvar no caminho indicado acima.
2. Colar o JSON do seu SO em `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) ou `%APPDATA%\Claude\claude_desktop_config.json` (Windows).
3. Reinicializar o Claude Desktop.

O `client_code` (`ClientRecord.client_code_hash`) **não tem TTL** e é reutilizável em quantos dispositivos o usuário precisar — não é um código de uso único por dispositivo. Se vazar ou o usuário perder o código original, o admin invalida o anterior e gera um novo via `concilium ops auth regenerate-code --user <client_id>`.

### F3 — Notificação de novo dispositivo

Ao detectar um device_id desconhecido em `activate_device_code()` ou `use_refresh_token()`, enviar email ao usuário com:

- Nome/IP do dispositivo detectado.
- Timestamp do acesso.
- Link de revoke com token de 24h.

**Lógica de detecção:** se `device_id` não está em `list_devices(client_id)` do usuário no momento do acesso.

> **Nota de implementação (2026-07-10):** implementado em
> `application/services/device_detection.py` (`notify_if_unknown_device`), chamado a partir de
> `presentation/api/routes/auth.py` (`activate_device` e `refresh_token`) e
> `presentation/mcp/tools/auth_self.py` (`activate_device`/`refresh_token` MCP). Dois refinamentos
> em relação à spec original: (1) a lista de dispositivos conhecidos é capturada via
> `store.list_devices()` **antes** da chamada a `activate_device_code()`/`use_refresh_token()` —
> capturá-la depois faria o dispositivo recém-ativado já aparecer na lista e nunca ser detectado
> como desconhecido; (2) o primeiro dispositivo de um usuário novo nunca gera notificação (onboarding,
> não anomalia) — notificação só a partir do 2º dispositivo em diante. A função é best-effort: nunca
> propaga exceção (falha de storage/SMTP não pode derrubar login/ativação), e é condicionada a
> `email` cadastrado no `ClientRecord`.

### F4 — Revoke self-service com timeout de 24h

Novo estado no modelo de revogação:

```python
class RevokePendingRecord(BaseModel):
    revoke_token: str          # token opaco enviado por email
    client_id: str
    device_id: str
    requested_at: datetime
    expires_at: datetime       # requested_at + 24h
    confirmed: bool = False
```

**Fluxo:**

1. Usuário clica no link de revoke no email → `POST /auth/revoke-pending/{revoke_token}`.
2. Sistema cria `RevokePendingRecord` (TTL 24h) e envia email de confirmação com segundo link.
3. Usuário confirma → `POST /auth/revoke-confirm/{revoke_token}` → `revoke_device(device_id)` executado.
4. Se não confirmado em 24h, `RevokePendingRecord` expira sem revogar nada.

O duplo-clique (pending → confirm) previne revogações acidentais por phishing.

**Endpoint exposto:** `POST /auth/revoke-pending/{token}` e `POST /auth/revoke-confirm/{token}` — sem autenticação JWT (o revoke_token é o único fator). Protegido por rate limit (5 req/min por IP).

### F5 — Exposição self-service de dispositivos ao usuário

Adicionar tool MCP (acessível a qualquer role autenticado, não só admin):

```python
@mcp.tool()
@permission("auth:self")   # nova permissão: usuário vê/revoga apenas os próprios devices
async def listar_meus_dispositivos() -> list[DeviceInfo]: ...

@mcp.tool()
@permission("auth:self")
async def revogar_dispositivo(device_id: str) -> RevokeResult: ...
```

A permissão `auth:self` é adicionada a todos os roles (viewer, operator, engineer, admin). Diferente de `auth:manage` (admin apenas, que lista dispositivos de qualquer usuário).

## Arquivos a criar/modificar

| Arquivo | Ação |
|---|---|
| `infrastructure/services/notification_service.py` | Criar — serviço de email |
| `infrastructure/services/__init__.py` | Atualizar exports |
| `infrastructure/auth/auth_store.py` | Adicionar `RevokePendingRecord`, `create_revoke_pending()`, `confirm_revoke()` |
| `infrastructure/auth/permission_guard.py` | Adicionar permissão `auth:self` a todos os roles |
| `presentation/api/routes/auth.py` | Adicionar endpoints `revoke-pending` e `revoke-confirm` |
| `presentation/mcp/tools/` | Criar tool `listar_meus_dispositivos` e `revogar_dispositivo` |
| `presentation/cli/commands_ops.py` | Acionar `NotificationService` em create/edit/remove |
| `infrastructure/settings.py` | Adicionar `SMTP_*` e `NOTIFICATIONS_ENABLED` |

> **Nota retroativa (ADR-131, 2026-07-08):** a implementação real divergiu desta tabela —
> `notify_user_edited` não foi implementado junto com este ADR e `notify_user_removed`
> ficou implementado mas sem call site (`remove-user` nunca o chamava). O comando que
> acionou `NotificationService` foi `commands_auth.py` (não `commands_ops.py`, que não
> existe). O ADR-131 fecha essas lacunas: liga `notify_user_removed` a `remove-user`,
> implementa `notify_user_edited` e o liga a `regenerate-code`, e adiciona
> `notify_device_revoked_admin` para a revogação administrativa direta em `revoke-device`.

## Consequências

**Positivas:**
- Onboarding de usuário torna-se self-service: admin cria, usuário recebe tudo por email.
- Rastreabilidade de novos dispositivos sem depender do admin como intermediário.
- Revoke self-service com duplo-fator previne tanto phishing quanto revogações acidentais.

**Negativas / trade-offs:**
- SMTP em produção requer configuração adicional no Key Vault (`smtp-password`).
- O device code no email é um segredo — o email deve ser tratado como canal seguro. Documentar que endereços de email corporativos são requisito.
- TTL de 1h para device code pode ser curto se o usuário demorar a configurar; admin pode regenerar via CLI.
