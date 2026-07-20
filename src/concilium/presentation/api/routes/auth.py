"""Auth endpoints — ADR-094 / ADR-123.

POST /auth/token          — emissão de JWT via client_id/client_secret (Fase 2)
POST /auth/device/activate — troca device code por refresh token (Fase 1 proxy)
POST /auth/token/refresh   — troca refresh token por access token (Fase 1 proxy)
POST /auth/revoke-pending/{revoke_token}  — inicia revogação self-service (ADR-123 F4)
POST /auth/revoke-confirm/{revoke_token}  — confirma revogação self-service (ADR-123 F4)
GET  /auth/users/visible   — visibilidade de usuários entre roles (ADR-143)
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from slowapi.util import get_remote_address

from concilium.infrastructure.auth.permission_guard import permission
from concilium.presentation.api.rate_limit import limiter

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenRequest(BaseModel):
    client_id: str
    client_secret: str
    ttl_days: int | None = Field(default=None, ge=1, le=90, description="TTL em dias (máx 90). Default: 8 horas.")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Validade em segundos.")


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Emitir JWT de acesso (RS256)",
    status_code=status.HTTP_200_OK,
)
@limiter.limit("5/minute", key_func=get_remote_address)
def issue_token(request: Request, response: Response, body: TokenRequest) -> TokenResponse:
    """Valida `client_id`/`client_secret` e retorna um JWT RS256.

    **Scopes por consumidor** são definidos em `CONCILIUM__AUTH_CLIENTS` (env JSON).
    Perfis de TTL:
    - Padrão (agentes, engenheiros): 8 horas
    - Service account CI (`ttl_days`): até 90 dias

    Retorna `401` para credenciais inválidas.
    """
    from concilium.infrastructure.auth.auth_store import get_auth_store
    from concilium.infrastructure.auth.token_service import issue_token as _issue

    # Valida credenciais: file store (ADR-099) com fallback env var (ADR-094)
    store = get_auth_store()
    client_roles = store.get_client_roles(body.client_id, body.client_secret)
    if client_roles is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    ttl = timedelta(days=body.ttl_days) if body.ttl_days else timedelta(hours=8)
    token = _issue(subject=body.client_id, roles=client_roles, ttl=ttl)

    return TokenResponse(
        access_token=token,
        expires_in=int(ttl.total_seconds()),
    )


# ── Device activation (ADR-094 Fase 1 — proxy flow) ──────────────────────────


class DeviceActivateRequest(BaseModel):
    device_code: str = Field(description="client_code do usuário (formato RCODE-*).")
    device_name: str = Field(default="", description="Nome legível do dispositivo (opcional).")


class DeviceActivateResponse(BaseModel):
    refresh_token: str
    device_id: str
    client_id: str
    scopes: list[str]
    expires_at: str


@router.post(
    "/device/activate",
    response_model=DeviceActivateResponse,
    summary="Ativar dispositivo com client_code do usuário",
    status_code=status.HTTP_200_OK,
)
@limiter.limit("10/minute", key_func=get_remote_address)
def activate_device(request: Request, response: Response, body: DeviceActivateRequest) -> DeviceActivateResponse:
    """Troca o client_code do usuário (RCODE-*) por um refresh token do dispositivo.

    O client_code é reutilizável — não é consumido nem expira — e pode ativar
    quantos dispositivos o usuário precisar, cada um identificado por device_name.
    O refresh token retornado tem validade de 90 dias e deve ser armazenado
    localmente pelo proxy em `~/.concilium/tokens/` (chmod 600).
    """
    from concilium.application.services.device_detection import list_devices_before, notify_if_unknown_device
    from concilium.infrastructure.auth.auth_store import get_auth_store

    store = get_auth_store()
    # ADR-123 F3: captura a lista de dispositivos ANTES da ativação — depois disso
    # o dispositivo recém-criado já estaria na lista e nunca seria "desconhecido".
    # client_id só é conhecido DEPOIS de activate_device_code() ter sucesso, por
    # isso a captura é irrestrita (sem filtro) e o filtro por client_id acontece
    # depois, com o rt.client_id retornado.
    devices_before = list_devices_before(store)
    rt = store.activate_device_code(body.device_code, device_name=body.device_name)
    if rt is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="client_code inválido ou usuário inativo.",
        )
    known_before = {d.device_id for d in devices_before if d.client_id == rt.client_id}
    notify_if_unknown_device(store, rt, known_before)
    return DeviceActivateResponse(
        refresh_token=rt.token_id,
        device_id=rt.device_id,
        client_id=rt.client_id,
        scopes=rt.roles,  # campo legado mantido na resposta por compatibilidade
        expires_at=rt.expires_at,
    )


# ── Token refresh ─────────────────────────────────────────────────────────────


class TokenRefreshRequest(BaseModel):
    refresh_token: str = Field(description="Token RT-* obtido via /auth/device/activate.")


@router.post(
    "/token/refresh",
    response_model=TokenResponse,
    summary="Obter access token a partir de refresh token",
    status_code=status.HTTP_200_OK,
)
@limiter.limit("30/minute", key_func=get_remote_address)
def refresh_token(request: Request, response: Response, body: TokenRefreshRequest) -> TokenResponse:
    """Troca um refresh token por um access token JWT de 8 horas.

    O proxy chama este endpoint automaticamente antes de cada expiração.

    As roles são resolvidas a partir do ClientRecord *atual* (não do snapshot
    congelado no refresh token na ativação do dispositivo) — assim uma mudança
    de role (ou desativação) do usuário se propaga no próximo refresh, sem
    exigir revogar e reativar o dispositivo manualmente.
    """
    from concilium.application.services.device_detection import list_devices_before, notify_if_unknown_device
    from concilium.infrastructure.auth.auth_store import get_auth_store
    from concilium.infrastructure.auth.token_service import issue_token as _issue

    store = get_auth_store()
    devices_before = list_devices_before(store)
    record = store.use_refresh_token(body.refresh_token)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido, expirado ou revogado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    client = store.get_client(record.client_id)
    if client is None or not client.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário do dispositivo não existe mais ou foi desativado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    known_before = {d.device_id for d in devices_before if d.client_id == record.client_id}
    notify_if_unknown_device(store, record, known_before)

    ttl = timedelta(hours=8)
    token = _issue(subject=record.client_id, roles=client.roles, ttl=ttl, device_id=record.device_id)
    return TokenResponse(access_token=token, expires_in=int(ttl.total_seconds()))


# ── Emissão direta de token por usuário (sem device registration) ─────────────


class IssueTokenRequest(BaseModel):
    client_id: str = Field(description="ID do usuário (definido em CONCILIUM__AUTH_CLIENTS).")
    client_secret: str = Field(description="Senha do usuário.")
    ttl_days: int = Field(default=30, ge=1, le=90, description="Validade em dias. Padrão: 30 dias.")
    label: str = Field(
        default="", description="Rótulo opcional para identificar o uso do token (ex: 'claude-desktop-bruno')."
    )


@router.post(
    "/token/issue",
    response_model=TokenResponse,
    summary="Emitir token de longa duração por usuário — sem device registration",
    status_code=status.HTTP_200_OK,
)
@limiter.limit("10/minute", key_func=get_remote_address)
def issue_user_token(request: Request, response: Response, body: IssueTokenRequest) -> TokenResponse:
    """Emite JWT de longa duração diretamente para um usuário existente.

    Alternativa ao fluxo de registro de dispositivo (device code + refresh token):
    - Sem necessidade de ativar dispositivo manualmente
    - Token válido por até 90 dias
    - Ideal para configuração de Claude Desktop, CI/CD, agentes automatizados

    O `label` é registrado nos logs para rastreabilidade de origem.
    Retorna `401` para credenciais inválidas.
    """
    import logging

    from concilium.infrastructure.auth.auth_store import get_auth_store
    from concilium.infrastructure.auth.token_service import issue_token as _issue

    logger = logging.getLogger(__name__)

    store = get_auth_store()
    client_roles = store.get_client_roles(body.client_id, body.client_secret)
    if client_roles is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    ttl = timedelta(days=body.ttl_days)
    token = _issue(subject=body.client_id, roles=client_roles, ttl=ttl)

    logger.info(
        "Token emitido para usuário '%s' (label='%s', ttl=%dd, roles=%s)",
        body.client_id,
        body.label or "—",
        body.ttl_days,
        client_roles,
    )

    return TokenResponse(
        access_token=token,
        expires_in=int(ttl.total_seconds()),
    )


# ── Self-service revoke (ADR-123 F4) ─────────────────────────────────────────


class RevokePendingResponse(BaseModel):
    status: str
    message: str


class RevokeConfirmResponse(BaseModel):
    status: str
    device_id: str


@router.post(
    "/revoke-pending/{revoke_token}",
    response_model=RevokePendingResponse,
    summary="Iniciar revogação self-service de dispositivo (ADR-123 F4)",
    status_code=status.HTTP_200_OK,
)
@limiter.limit("5/minute", key_func=get_remote_address)
def revoke_pending(request: Request, response: Response, revoke_token: str) -> RevokePendingResponse:
    """Usuário clica no link do email de novo dispositivo para iniciar a revogação.

    Busca o RevokePendingRecord pelo token e envia email de confirmação com link
    para o passo final. Retorna 404 se token não encontrado ou expirado.

    Não requer autenticação JWT — o token do link é a prova de posse do email.
    """
    import logging as _logging

    from concilium.application.services.notifications import notify_revoke_pending
    from concilium.infrastructure.auth.auth_store import get_auth_store

    _log = _logging.getLogger(__name__)

    store = get_auth_store()
    record = store.get_revoke_pending(revoke_token)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token de revogação não encontrado, expirado ou já utilizado.",
        )

    # Tenta buscar email do cliente para enviar confirmação
    clients = {c.client_id: c for c in store.list_clients()}
    client = clients.get(record.client_id)
    client_email = client.email if client else ""

    if client_email:
        notify_revoke_pending(
            client_id=record.client_id,
            device_id=record.device_id,
            email=client_email,
            revoke_token=revoke_token,
        )
        _log.info(
            "revoke-pending: enviado email de confirmação para '%s' (device='%s')",
            record.client_id,
            record.device_id,
        )

    return RevokePendingResponse(
        status="confirmation_sent",
        message=(
            f"Confirmação de revogação do dispositivo '{record.device_id}' enviada. "
            "Verifique seu email e clique no link de confirmação para concluir."
            if client_email
            else "Solicitação recebida. Nenhum email de confirmação configurado para este usuário."
        ),
    )


@router.post(
    "/revoke-confirm/{revoke_token}",
    response_model=RevokeConfirmResponse,
    summary="Confirmar revogação self-service de dispositivo (ADR-123 F4)",
    status_code=status.HTTP_200_OK,
)
@limiter.limit("5/minute", key_func=get_remote_address)
def revoke_confirm(request: Request, response: Response, revoke_token: str) -> RevokeConfirmResponse:
    """Usuário clica no link de confirmação do email para efetivar a revogação.

    Chama confirm_revoke() que marca como confirmado e revoga o dispositivo.
    Retorna 404 se token não encontrado, expirado ou já confirmado.

    Não requer autenticação JWT — o token do link é a prova de posse do email.
    """
    from concilium.infrastructure.auth.auth_store import get_auth_store

    store = get_auth_store()
    record = store.get_revoke_pending(revoke_token)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token de revogação não encontrado, expirado ou já confirmado.",
        )

    device_id = record.device_id
    ok = store.confirm_revoke(revoke_token)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token de revogação não encontrado, expirado ou já confirmado.",
        )

    return RevokeConfirmResponse(status="revoked", device_id=device_id)


# ── Visibilidade de usuários entre roles (ADR-143) ───────────────────────────


class VisibleUsersResponse(BaseModel):
    status: str = "ok"
    total: int
    usuarios: list[dict[str, Any]]


@router.get(
    "/users/visible",
    response_model=VisibleUsersResponse,
    summary="Listar usuários visíveis para os roles do chamador (ADR-143)",
    status_code=status.HTTP_200_OK,
)
@permission("auth:list-visible")
def list_visible_users_route(request: Request) -> VisibleUsersResponse:
    """Lista outros usuários visíveis, escopado pela matriz `ROLE_VISIBILITY` (D2).

    Nunca inclui dispositivos, senha/hash ou notas administrativas (D3) — apenas
    client_id, email, roles e active. Nunca inclui o próprio chamador. Cada
    consulta é registrada para o digest opcional do usuário consultado (D7/D8).
    """
    from concilium.application.services.visibility_service import list_visible_users
    from concilium.infrastructure.auth.permission_guard import roles_from_token
    from concilium.presentation.api.deps import get_current_subject

    claims = getattr(request.state, "jwt_claims", {})
    caller_roles = roles_from_token(claims)
    caller_id = get_current_subject(request)

    usuarios = list_visible_users(caller_id, caller_roles)
    return VisibleUsersResponse(total=len(usuarios), usuarios=usuarios)
