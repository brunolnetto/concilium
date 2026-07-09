"""ADR-126 — Project Ownership: helpers de handover (transferência de responsável).

Funções puras operando sobre `ProjectHandle` + `AuditService` — reaproveitadas tanto
pela camada de API (`ProjectService`/`ConciliumService`) quanto pela CLI
(`commands_auth.py remove-user`, D7/F7), sem depender do mixin `ProjectServiceHost`.

D4 — Handover híbrido:
  - `transfer_ownership_forced`: admin (ou CLI --reassign-to) troca `owner_id`
    imediatamente, sem aceite do destinatário.
  - `create_ownership_transfer_pending` + `accept_ownership_transfer` /
    `reject_ownership_transfer`: dono atual cria convite pendente (mesmo padrão de
    `revoke_pending`, ADR-094); `owner_id` só muda após aceite explícito.

O convite pendente vive dentro do próprio `meta.json` do projeto (chave
`ownership_transfer_pending`) — segue o mesmo padrão de dados "planos" já usado
para `version_history` (ADR-119), em vez de introduzir um store central novo.
"""

from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from .audit_service import AuditService, OwnershipTransferAction
from .project_repository import ProjectHandle, ProjectRepository

# ADR-126 D4.2: TTL do convite pendente — mesmo default de REVOKE_PENDING_TTL (ADR-094).
OWNERSHIP_TRANSFER_TTL = timedelta(hours=24)


def _email_for(client_id: str | None) -> str | None:
    """ADR-134 D6: resolve o email de um client_id via auth_store, best-effort.

    Nunca lança — se o lookup falhar (store indisponível, client não encontrado,
    sem email cadastrado), retorna None e o chamador simplesmente não notifica
    (mesmo padrão condicional das notificações ADR-123/ADR-131: "se há email").
    """
    if not client_id:
        return None
    try:
        from concilium.infrastructure.auth.auth_store import get_auth_store

        store = get_auth_store()
        record = next((r for r in store.list_clients() if r.client_id == client_id), None)
        return record.email if record and record.email else None
    except Exception:
        return None


def _notify_ownership_event(notify_fn: Any, *args: Any) -> None:
    """ADR-134 D6: dispara a notificação de ownership correspondente, best-effort.

    Nunca propaga exceção — a transferência de ownership em si já foi persistida
    em meta.json antes desta chamada; falhar só a notificação não deve reverter
    ou bloquear a operação de negócio (mesmo racional de `log_ownership_transfer_action`).
    """
    try:
        notify_fn(*args)
    except Exception:
        pass


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass
class OwnershipTransferPending:
    """ADR-126 D4.2 — convite pendente de transferência de ownership."""

    token: str
    project_id: str
    owner_atual: str
    owner_proposto: str
    criado_em: str
    expira_em: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OwnershipTransferPending:
        return cls(
            token=d["token"],
            project_id=d["project_id"],
            owner_atual=d["owner_atual"],
            owner_proposto=d["owner_proposto"],
            criado_em=d["criado_em"],
            expira_em=d["expira_em"],
        )


def get_project_owner(project: ProjectHandle) -> str | None:
    """D1: retorna owner_id do projeto (None para projetos legados sem migração)."""
    return project.meta.get("owner_id")


def find_projects_by_owner(repository: ProjectRepository, owner_id: str) -> list[ProjectHandle]:
    """D7/F7: retorna todos os projetos cujo owner_id é o informado.

    Usado por `remove-user` (CLI) para bloquear/realocar antes de remover um client.
    """
    return [p for p in repository.list_projects() if p.meta.get("owner_id") == owner_id]


def _active_pending(project: ProjectHandle) -> dict[str, Any] | None:
    """Retorna o convite pendente registrado no meta, ou None se não houver nenhum.

    Não verifica expiração — isso é responsabilidade do chamador (ex.:
    `accept_ownership_transfer`, que compara `expira_em` com `_now()` e trata
    o caso expirado explicitamente via `_log_expired`).
    """
    pending = project.meta.get("ownership_transfer_pending")
    if not pending:
        return None
    return pending


def transfer_ownership_forced(
    project: ProjectHandle,
    owner_novo: str,
    actor: str,
    audit: AuditService,
    actor_role: str | None = None,
) -> dict[str, Any]:
    """D4.1: admin (ou CLI --reassign-to) troca owner_id imediatamente, sem aceite."""
    meta = project.meta
    project_id = meta.get("id", "")
    owner_anterior = meta.get("owner_id")
    project.update_meta(
        owner_id=owner_novo,
        owner_assigned_at=_iso(_now()),
        ownership_transfer_pending=None,
    )
    action = OwnershipTransferAction(
        action="transfer_forced",
        project_id=project_id,
        actor_id=actor,
        actor_role=actor_role,
        owner_anterior=owner_anterior,
        owner_proposto_ou_novo=owner_novo,
    )
    audit.log_ownership_transfer_action(project, action)
    email_novo = _email_for(owner_novo)
    if email_novo:
        from concilium.application.services.notifications import notify_ownership_transfer_forced

        _notify_ownership_event(notify_ownership_transfer_forced, email_novo, project_id, owner_anterior, owner_novo)
    return {"project_id": project_id, "owner_id": owner_novo, "owner_anterior": owner_anterior}


def create_ownership_transfer_pending(
    project: ProjectHandle,
    owner_proposto: str,
    actor: str,
    audit: AuditService,
    actor_role: str | None = None,
) -> OwnershipTransferPending:
    """D4.2: dono atual cria convite pendente; owner_id só muda após /accept.

    Só existe um convite pendente por vez — criar um novo substitui o anterior
    (ainda não resolvido) sem alterar owner_id.
    """
    meta = project.meta
    project_id = meta.get("id", "")
    owner_atual = meta.get("owner_id")
    now = _now()
    pending = OwnershipTransferPending(
        token=secrets.token_urlsafe(32),
        project_id=project_id,
        owner_atual=owner_atual or "",
        owner_proposto=owner_proposto,
        criado_em=_iso(now),
        expira_em=_iso(now + OWNERSHIP_TRANSFER_TTL),
    )
    project.update_meta(ownership_transfer_pending=pending.to_dict())
    action = OwnershipTransferAction(
        action="invite_created",
        project_id=project_id,
        actor_id=actor,
        actor_role=actor_role,
        owner_anterior=owner_atual,
        owner_proposto_ou_novo=owner_proposto,
    )
    audit.log_ownership_transfer_action(project, action)
    email_proposto = _email_for(owner_proposto)
    if email_proposto:
        from concilium.application.services.notifications import notify_ownership_invite_created

        _notify_ownership_event(
            notify_ownership_invite_created,
            email_proposto,
            project_id,
            owner_atual or "",
            owner_proposto,
            pending.token,
        )
    return pending


def accept_ownership_transfer(
    project: ProjectHandle,
    token: str,
    actor: str,
    audit: AuditService,
    actor_role: str | None = None,
) -> dict[str, Any]:
    """F3: destinatário aceita — owner_id passa a ser owner_proposto.

    Raise:
        FileNotFoundError: convite não existe ou token não confere.
        PermissionError: actor não é o destinatário do convite.
        ValueError: convite expirou (TTL, ADR-126 D4.2).
    """
    project_id = project.meta.get("id", "")
    pending = _active_pending(project)
    if pending is None or pending.get("token") != token:
        raise FileNotFoundError(f"Convite de transferência de ownership não encontrado para o projeto '{project_id}'.")
    if actor != pending.get("owner_proposto"):
        raise PermissionError(
            f"Convite de transferência é destinado a '{pending.get('owner_proposto')}', não a '{actor}'."
        )
    if _parse_iso(pending["expira_em"]) < _now():
        project.update_meta(ownership_transfer_pending=None)
        _log_expired(project, pending, project_id, audit)
        raise ValueError(f"Convite de transferência de ownership do projeto '{project_id}' expirou.")

    owner_novo = pending["owner_proposto"]
    owner_anterior = pending["owner_atual"]
    project.update_meta(owner_id=owner_novo, owner_assigned_at=_iso(_now()), ownership_transfer_pending=None)
    action = OwnershipTransferAction(
        action="invite_accepted",
        project_id=project_id,
        actor_id=actor,
        actor_role=actor_role,
        owner_anterior=owner_anterior,
        owner_proposto_ou_novo=owner_novo,
    )
    audit.log_ownership_transfer_action(project, action)
    email_anterior = _email_for(owner_anterior)
    if email_anterior:
        from concilium.application.services.notifications import notify_ownership_invite_accepted

        _notify_ownership_event(notify_ownership_invite_accepted, email_anterior, project_id, owner_novo)
    return {"project_id": project_id, "owner_id": owner_novo}


def reject_ownership_transfer(
    project: ProjectHandle,
    token: str,
    actor: str,
    audit: AuditService,
    actor_role: str | None = None,
) -> dict[str, Any]:
    """F3: destinatário rejeita — owner_id permanece inalterado.

    Raise:
        FileNotFoundError: convite não existe ou token não confere.
        PermissionError: actor não é o destinatário do convite.
    """
    project_id = project.meta.get("id", "")
    pending = _active_pending(project)
    if pending is None or pending.get("token") != token:
        raise FileNotFoundError(f"Convite de transferência de ownership não encontrado para o projeto '{project_id}'.")
    if actor != pending.get("owner_proposto"):
        raise PermissionError(
            f"Convite de transferência é destinado a '{pending.get('owner_proposto')}', não a '{actor}'."
        )

    owner_atual = pending.get("owner_atual")
    project.update_meta(ownership_transfer_pending=None)
    action = OwnershipTransferAction(
        action="invite_rejected",
        project_id=project_id,
        actor_id=actor,
        actor_role=actor_role,
        owner_anterior=owner_atual,
        owner_proposto_ou_novo=pending.get("owner_proposto"),
    )
    audit.log_ownership_transfer_action(project, action)
    email_atual = _email_for(owner_atual)
    if email_atual:
        from concilium.application.services.notifications import notify_ownership_invite_rejected

        _notify_ownership_event(
            notify_ownership_invite_rejected, email_atual, project_id, pending["owner_proposto"]
        )
    return {"project_id": project_id, "owner_id": owner_atual}


def _log_expired(project: ProjectHandle, pending: dict[str, Any], project_id: str, audit: AuditService) -> None:
    action = OwnershipTransferAction(
        action="invite_expired",
        project_id=project_id,
        actor_id="system",
        actor_role=None,
        owner_anterior=pending.get("owner_atual"),
        owner_proposto_ou_novo=pending.get("owner_proposto"),
    )
    audit.log_ownership_transfer_action(project, action)
    email_atual = _email_for(pending.get("owner_atual"))
    if email_atual:
        from concilium.application.services.notifications import notify_ownership_invite_expired

        _notify_ownership_event(notify_ownership_invite_expired, email_atual, project_id, pending["owner_proposto"])
