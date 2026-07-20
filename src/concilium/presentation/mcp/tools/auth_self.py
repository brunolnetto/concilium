"""MCP tools para gestão de dispositivos próprios (ADR-123 F5)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.infrastructure.auth.permission_guard import AUTH_PUBLIC, AUTH_SELF, permission


def register(server: FastMCP) -> None:
    """Registra ferramentas de self-service de autenticação no servidor MCP."""

    @server.tool()
    @permission(AUTH_PUBLIC)
    def ativar_dispositivo(client_code: str, device_name: str) -> dict[str, Any]:
        """Ativa um dispositivo usando o código de cliente do usuário (bootstrap).

        O client_code é único por usuário e nunca é consumido: pode ser reutilizado
        em quantos dispositivos o usuário precisar, sem depender do admin/TI para
        cadastrar cada um. Cada ativação gera um refresh_token próprio, identificado
        por device_name.

        Args:
            client_code: Código de bootstrap do usuário (formato: RCODE-...)
            device_name: Nome descritivo para identificar este dispositivo

        Returns:
            refresh_token: Token de longa duração para renovar access_tokens
            expires_at: Data de expiração do refresh_token
            device_id: ID gerado para este dispositivo (a partir de device_name)

        Nota: Este tool é público (não requer autenticação) pois é usado no bootstrap.
        """
        from concilium.application.services.device_detection import list_devices_before, notify_if_unknown_device
        from concilium.infrastructure.auth.auth_store import get_auth_store

        store = get_auth_store()

        # ADR-123 F3: captura ANTES de ativar — ver nota em presentation/api/routes/auth.py.
        devices_before = list_devices_before(store)
        rt_record = store.activate_device_code(client_code, device_name=device_name)

        if rt_record is None:
            return {
                "status": "error",
                "message": "Código de cliente inválido ou usuário inativo.",
            }

        known_before = {d.device_id for d in devices_before if d.client_id == rt_record.client_id}
        notify_if_unknown_device(store, rt_record, known_before)

        return {
            "status": "ok",
            "refresh_token": rt_record.token_id,
            "device_id": rt_record.device_id,
            "device_name": rt_record.device_name,
            "client_id": rt_record.client_id,
            "expires_at": rt_record.expires_at,
        }

    @server.tool()
    @permission(AUTH_PUBLIC)
    def renovar_token(refresh_token: str) -> dict[str, Any]:
        """Renova um access_token usando um refresh_token válido.

        Use este tool para obter um novo access_token de curta duração (8h) a partir
        de um refresh_token de longa duração.

        Args:
            refresh_token: Token RT-* obtido via ativar_dispositivo()

        Returns:
            access_token: Novo JWT para usar em chamadas autenticadas
            expires_in: Tempo de vida do access_token em segundos
            token_type: Sempre "Bearer"

        Nota: Este tool é público (não requer autenticação) pois é usado para obter auth.
        """
        from concilium.application.services.device_detection import list_devices_before, notify_if_unknown_device
        from concilium.infrastructure.auth.auth_store import get_auth_store
        from concilium.infrastructure.auth.token_service import TTL_INTERACTIVE
        from concilium.infrastructure.auth.token_service import issue_token as _issue

        store = get_auth_store()
        devices_before = list_devices_before(store)
        record = store.use_refresh_token(refresh_token)
        if record is None:
            return {
                "status": "error",
                "message": "Refresh token inválido, expirado ou revogado.",
            }

        known_before = {d.device_id for d in devices_before if d.client_id == record.client_id}
        notify_if_unknown_device(store, record, known_before)

        jwt_token = _issue(subject=record.client_id, roles=record.roles, ttl=TTL_INTERACTIVE)
        return {
            "status": "ok",
            "access_token": jwt_token,
            "token_type": "Bearer",
            "expires_in": int(TTL_INTERACTIVE.total_seconds()),
        }

    @server.tool()
    @permission(AUTH_SELF)
    def listar_meus_dispositivos() -> dict[str, Any]:
        """Lista os dispositivos ativos do usuário autenticado atual.

        Retorna todos os refresh tokens ativos (não revogados, não expirados)
        associados ao client_id do JWT atual.

        Use para verificar quais dispositivos têm acesso à sua conta antes
        de iniciar uma revogação seletiva com revogar_meu_dispositivo().
        """
        from concilium.infrastructure.auth.auth_store import get_auth_store
        from concilium.infrastructure.auth.permission_guard import get_current_user_id

        client_id = get_current_user_id()
        if client_id is None:
            return {
                "status": "error",
                "message": "Identidade do usuário não disponível no contexto atual.",
                "dispositivos": [],
            }

        store = get_auth_store()
        devices = store.list_devices(client_id=client_id)

        return {
            "status": "ok",
            "client_id": client_id,
            "total": len(devices),
            "dispositivos": [
                {
                    "device_id": d.device_id,
                    "device_name": d.device_name,
                    "issued_at": d.issued_at,
                    "expires_at": d.expires_at,
                    "last_used_at": d.last_used_at or None,
                }
                for d in devices
            ],
        }

    @server.tool()
    @permission(AUTH_SELF)
    def revogar_meu_dispositivo(device_id: str) -> dict[str, Any]:
        """Solicita a revogação de um dispositivo próprio via self-service.

        Cria um pedido de revogação pendente e envia email de confirmação
        para o endereço cadastrado. O usuário deve clicar no link do email
        para confirmar e efetivar a revogação.

        Args:
            device_id: ID do dispositivo a revogar (use listar_meus_dispositivos()
                       para obter os IDs disponíveis).

        Retorna o revoke_token e instruções. A revogação só é efetivada após
        confirmação via email (link válido por 24h).
        """
        from concilium.application.services.notifications import notify_revoke_pending
        from concilium.infrastructure.auth.auth_store import get_auth_store
        from concilium.infrastructure.auth.permission_guard import get_current_user_id

        client_id = get_current_user_id()
        if client_id is None:
            return {
                "status": "error",
                "message": "Identidade do usuário não disponível no contexto atual.",
            }

        store = get_auth_store()

        # Verifica que o dispositivo pertence ao usuário atual
        devices = store.list_devices(client_id=client_id)
        device_ids = {d.device_id for d in devices}
        if device_id not in device_ids:
            return {
                "status": "error",
                "message": (
                    f"Dispositivo '{device_id}' não encontrado nos dispositivos ativos do usuário '{client_id}'. "
                    f"Dispositivos ativos: {sorted(device_ids) or ['(nenhum)']}"
                ),
            }

        # Cria pedido de revogação pendente
        pending = store.create_revoke_pending(client_id=client_id, device_id=device_id)

        # Tenta buscar email do cliente para enviar notificação
        clients = {c.client_id: c for c in store.list_clients()}
        client = clients.get(client_id)
        client_email = client.email if client else ""

        if client_email:
            notify_revoke_pending(
                client_id=client_id,
                device_id=device_id,
                email=client_email,
                revoke_token=pending.revoke_token,
            )

        return {
            "status": "pending",
            "revoke_token": pending.revoke_token,
            "device_id": device_id,
            "expires_at": pending.expires_at,
            "message": (
                f"Pedido de revogação do dispositivo '{device_id}' criado. "
                + (
                    f"Um email de confirmação foi enviado para {client_email}. "
                    "Clique no link do email para confirmar a revogação (válido por 24h)."
                    if client_email
                    else "Nenhum email cadastrado. Use o endpoint /auth/revoke-confirm/{revoke_token} para confirmar."
                )
            ),
        }

    @server.tool()
    @permission(AUTH_SELF)
    def obter_instrucoes_atualizadas() -> dict[str, Any]:
        """Retorna a versão mais atual das instruções de uso do Concilium (ADR-144 D6).

        Sempre lê o conteúdo do disco nesta chamada — nunca uma cópia
        congelada em memória — então reflete qualquer atualização publicada
        desde o anexo de onboarding original. Marca a versão retornada como
        "vista" pelo usuário atual (`last_skill_version_seen`), o que faz o
        aviso de `ping()` sobre skill desatualizado parar de aparecer até a
        próxima mudança de versão.
        """
        from concilium.application.services import skill_content
        from concilium.infrastructure.auth.auth_store import get_auth_store
        from concilium.infrastructure.auth.permission_guard import get_current_user_id

        client_id = get_current_user_id()
        if client_id is None:
            return {
                "status": "error",
                "message": "Identidade do usuário não disponível no contexto atual.",
            }

        content = skill_content.read_skill_content()
        versao = skill_content.get_skill_version(content)

        get_auth_store().mark_skill_version_seen(client_id, versao)

        return {
            "status": "ok",
            "versao": versao,
            "conteudo": content.decode("utf-8", errors="replace"),
        }
