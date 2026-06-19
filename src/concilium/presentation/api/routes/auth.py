"""Auth endpoints — ADR-094.

POST /auth/token          — emissão de JWT via client_id/client_secret (Fase 2)
POST /auth/device/activate — troca device code por refresh token (Fase 1 proxy)
POST /auth/token/refresh   — troca refresh token por access token (Fase 1 proxy)
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from slowapi.util import get_remote_address

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
    device_code: str = Field(description="Código RCODE-* gerado pelo admin.")
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
    summary="Ativar dispositivo com device code (uso único)",
    status_code=status.HTTP_200_OK,
)
@limiter.limit("10/minute", key_func=get_remote_address)
def activate_device(request: Request, response: Response, body: DeviceActivateRequest) -> DeviceActivateResponse:
    """Troca um device code (RCODE-*) por um refresh token persistente.

    O device code é de uso único e expira em 1h.
    O refresh token retornado tem validade de 90 dias e deve ser armazenado
    localmente pelo proxy em `~/.concilium/tokens/` (chmod 600).
    """
    from concilium.infrastructure.auth.auth_store import get_auth_store

    rt = get_auth_store().activate_device_code(body.device_code)
    if rt is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Device code inválido, já utilizado ou expirado.",
        )
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
    """
    from concilium.infrastructure.auth.auth_store import get_auth_store
    from concilium.infrastructure.auth.token_service import issue_token as _issue

    store = get_auth_store()
    record = store.use_refresh_token(body.refresh_token)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido, expirado ou revogado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    ttl = timedelta(hours=8)
    token = _issue(subject=record.client_id, roles=record.roles, ttl=ttl)
    return TokenResponse(access_token=token, expires_in=int(ttl.total_seconds()))


# ── Emissão direta de token por usuário (sem device registration) ─────────────


class IssueTokenRequest(BaseModel):
    client_id: str = Field(description="ID do usuário (definido em CONCILIUM__AUTH_CLIENTS).")
    client_secret: str = Field(description="Senha do usuário.")
    ttl_days: int = Field(default=30, ge=1, le=90, description="Validade em dias. Padrão: 30 dias.")
    label: str = Field(default="", description="Rótulo opcional para identificar o uso do token (ex: 'claude-desktop-bruno').")


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
        body.client_id, body.label or "—", body.ttl_days, client_roles,
    )

    return TokenResponse(
        access_token=token,
        expires_in=int(ttl.total_seconds()),
    )
