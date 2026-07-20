"""Visibilidade de usuários entre roles (ADR-143).

Um usuário autenticado pode ver outros usuários do sistema, escopado pela
matriz `ROLE_VISIBILITY` (`permission_guard.py`) — nunca dispositivos, nunca
`secret_hash`/`client_code_hash`/`notes` (D3). Cada consulta é registrada
via `AuthStore.record_visibility_queries` para alimentar o digest opcional
do consultado (D7/D8) — nunca notificação atômica por consulta.
"""

from __future__ import annotations

from typing import Any

from concilium.infrastructure.auth.auth_store import get_auth_store
from concilium.infrastructure.auth.permission_guard import visible_roles_for


def list_visible_users(caller_client_id: str | None, caller_roles: list[str]) -> list[dict[str, Any]]:
    """Retorna os usuários visíveis para os roles do chamador (ADR-143 D2/D3).

    Exclui: o próprio chamador (auto-consulta é redundante com o self-service
    existente), clients soft-deleted (`deleted_at`), e qualquer campo sensível
    (`secret_hash`, `client_code_hash`, `notes`, dispositivos). Registra a
    consulta para o digest do consultado (D7) — sem registrar self-queries,
    já excluídas do resultado antes de chegar lá.
    """
    visible_roles = visible_roles_for(caller_roles)
    store = get_auth_store()
    clients = [
        c
        for c in store.list_clients()
        if not c.deleted_at and c.client_id != caller_client_id and set(c.roles) & visible_roles
    ]

    if caller_client_id is not None:
        store.record_visibility_queries(
            observer_client_id=caller_client_id,
            observer_roles=caller_roles,
            target_client_ids=[c.client_id for c in clients],
        )

    return [
        {
            "client_id": c.client_id,
            "email": c.email,
            "roles": c.roles,
            "active": c.active,
        }
        for c in clients
    ]
