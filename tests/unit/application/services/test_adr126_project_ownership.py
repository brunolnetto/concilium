"""ADR-126 — Project Ownership: responsável por projeto e autorização por ownership.

Cobre (TDD, incluindo casos de NEGAÇÃO de acesso):
  - D1: owner_id/owner_assigned_at em ProjectMeta, inicializados por create_project
  - D3: project:delete/project:manage-config/project:manage-ownership em permission_guard
        + autorização combinada (role E (owner==actor OU admin))
  - D4: handover híbrido — admin transfere forçado; dono cria convite pendente
  - F3: accept/reject de convite pendente + expiração por TTL
  - D5: filtro mine=true por owner_id
  - D6: OwnershipTransferAction no audit trail (best-effort)
  - D7/F7: remove-user CLI propaga para find_projects_by_owner (--reassign-to/--force)
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from concilium.application.services.project._ownership_helpers import (
    OwnershipTransferPending,
    _email_for,
    _notify_ownership_event,
    accept_ownership_transfer,
    create_ownership_transfer_pending,
    find_projects_by_owner,
    get_project_owner,
    reject_ownership_transfer,
    transfer_ownership_forced,
)
from concilium.application.services.project.audit_service import AuditService, OwnershipTransferAction
from concilium.infrastructure.auth.permission_guard import (
    PROJECT_DELETE,
    PROJECT_MANAGE_CONFIG,
    PROJECT_MANAGE_OWNERSHIP,
    get_permissions,
    require_owner_or_admin,
)
from concilium.infrastructure.storage.file_project_repository import FileProjectRepository


@pytest.fixture
def repo(tmp_path):
    return FileProjectRepository(tmp_path)


@pytest.fixture
def audit():
    return AuditService()


def _make_project(repo, owner_id="joao.silva"):
    project = repo.create_project("Projeto Teste", "mendeslobo")
    project.update_meta(owner_id=owner_id, owner_assigned_at=datetime.now(UTC).isoformat())
    return project


# ---------------------------------------------------------------------------
# D1 — owner_id / owner_assigned_at em ProjectMeta
# ---------------------------------------------------------------------------


class TestD1OwnerIdField:
    def test_create_project_initializes_owner_id_from_actor(self, repo):
        from concilium.application.services.project._project_service_helpers import _ps_create_project
        from concilium.application.services.project.audit_service import AuditService
        from concilium.application.services.project.project_files import DEFAULT_PROJECT_FILES

        req = SimpleNamespace(
            nome="Projeto X",
            contexto_id="mendeslobo",
            tipo_obra="terraplenagem",
            localizacao="Brasil",
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
            coordenadas_lat=0.0,
            coordenadas_lng=0.0,
            dias_semana=6,
            horas_dia=8,
            catalogo_base=None,
            model_dump=lambda: {},
        )
        svc = SimpleNamespace(_repository=repo, _files=DEFAULT_PROJECT_FILES, _audit_service=AuditService())
        svc.list_contexto_versions = lambda contexto_id: []
        payload = _ps_create_project(svc, req, {}, {}, None, None, actor="maria.santos")
        project = repo.get_project(payload["project_id"])
        assert project.meta["owner_id"] == "maria.santos"
        assert project.meta.get("owner_assigned_at") is not None

    def test_owner_id_persisted_in_meta_json(self, repo):
        project = _make_project(repo, owner_id="joao.silva")
        # Reload via a fresh handle to prove it's read back from disk, not memory.
        reloaded = repo.get_project(project.meta["id"])
        assert reloaded.meta["owner_id"] == "joao.silva"

    def test_get_project_owner_returns_none_for_legacy_project(self, repo):
        project = repo.create_project("Legado", "mendeslobo")
        assert get_project_owner(project) is None


# ---------------------------------------------------------------------------
# D3 — permissões granulares e autorização combinada
# ---------------------------------------------------------------------------


class TestD3Permissions:
    def test_operator_has_project_delete(self):
        assert PROJECT_DELETE in get_permissions(["operator"])

    def test_operator_has_project_manage_config(self):
        assert PROJECT_MANAGE_CONFIG in get_permissions(["operator"])

    def test_operator_has_project_manage_ownership(self):
        assert PROJECT_MANAGE_OWNERSHIP in get_permissions(["operator"])

    def test_auditor_lacks_project_delete(self):
        assert PROJECT_DELETE not in get_permissions(["auditor"])

    def test_catalog_manager_lacks_project_manage_ownership(self):
        assert PROJECT_MANAGE_OWNERSHIP not in get_permissions(["catalog-manager"])

    def test_engineer_and_admin_inherit_new_permissions(self):
        for perm in (PROJECT_DELETE, PROJECT_MANAGE_CONFIG, PROJECT_MANAGE_OWNERSHIP):
            assert perm in get_permissions(["engineer"])
            assert perm in get_permissions(["admin"])


class TestRequireOwnerOrAdmin:
    """require_owner_or_admin: role já validada por @permission — isto é a 2ª camada (ownership)."""

    def test_noop_when_auth_disabled(self):
        clean = {k: v for k, v in os.environ.items() if k != "CONCILIUM__AUTH_ENABLED"}
        with patch.dict(os.environ, clean, clear=True):
            require_owner_or_admin(actor_id="joao.silva", owner_id="maria.santos", roles=["engineer"])

    def test_owner_matches_actor_allowed(self):
        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}):
            require_owner_or_admin(actor_id="joao.silva", owner_id="joao.silva", roles=["engineer"])

    def test_admin_allowed_regardless_of_owner(self):
        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}):
            require_owner_or_admin(actor_id="maria.santos", owner_id="joao.silva", roles=["admin"])

    def test_non_owner_non_admin_denied(self):
        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}), pytest.raises(PermissionError):
            require_owner_or_admin(actor_id="maria.santos", owner_id="joao.silva", roles=["engineer"])

    def test_legacy_project_without_owner_id_is_permissive(self):
        """Projeto legado (owner_id=None) — role gate via @permission já é a única barreira."""
        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}):
            require_owner_or_admin(actor_id="maria.santos", owner_id=None, roles=["engineer"])


# ---------------------------------------------------------------------------
# Routes: delete_project / patch_project_config — autorização combinada (D3, Fase 4 DoD)
# ---------------------------------------------------------------------------


def _fake_request(roles: list[str]) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(jwt_claims={"roles": roles}))


class _FakeOwnedService:
    """Fake ConciliumService cujo único projeto tem owner_id='joao.silva'."""

    def __init__(self, owner_id="joao.silva"):
        self._owner_id = owner_id
        self.deleted = None
        self.patched = None

    def get_project_owner(self, project_id: str) -> str | None:
        return self._owner_id

    def delete_project(self, project_id: str, actor: str = "system") -> dict:
        self.deleted = (project_id, actor)
        return {"project_id": project_id, "deleted": True}

    def patch_project_config(self, project_id: str, updates: dict, actor: str = "system") -> dict:
        self.patched = (project_id, updates, actor)
        return {"project_id": project_id, "updated": list(updates)}

    def transfer_ownership_forced(self, project_id: str, owner_novo: str, actor: str) -> dict:
        self._owner_id = owner_novo
        return {"project_id": project_id, "owner_id": owner_novo}

    def create_ownership_transfer_pending(self, project_id: str, owner_proposto: str, actor: str) -> dict:
        return {"project_id": project_id, "owner_proposto": owner_proposto, "token": "tok-123"}

    def accept_ownership_transfer(self, project_id: str, token: str, actor: str) -> dict:
        return {"project_id": project_id, "owner_id": actor, "token": token}

    def reject_ownership_transfer(self, project_id: str, token: str, actor: str) -> dict:
        return {"project_id": project_id, "owner_id": self._owner_id, "token": token}


class TestDeleteProjectRouteAuthorization:
    def _call(self, roles: list[str], x_user: str, svc):
        from concilium.presentation.api.routes.projects import delete_project

        return delete_project(request=_fake_request(roles), project_id="proj-1", x_user=x_user, service=svc)

    def test_owner_with_role_can_delete(self):
        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}):
            svc = _FakeOwnedService(owner_id="joao.silva")
            result = self._call(["engineer"], "joao.silva", svc)
            assert result["deleted"] is True
            assert svc.deleted == ("proj-1", "joao.silva")

    def test_admin_can_delete_others_project(self):
        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}):
            svc = _FakeOwnedService(owner_id="joao.silva")
            result = self._call(["admin"], "maria.santos", svc)
            assert result["deleted"] is True

    def test_non_owner_engineer_denied(self):
        # PermissionError propaga (não é convertido em HTTPException(400) pelo catch-all
        # da rota — só o app-level exception_handler(PermissionError)->403 faz essa conversão,
        # via `except PermissionError: raise` explícito antes do `except Exception` genérico).
        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}), pytest.raises(PermissionError):
            svc = _FakeOwnedService(owner_id="joao.silva")
            self._call(["engineer"], "maria.santos", svc)

    def test_role_without_permission_denied(self):
        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}), pytest.raises(PermissionError):
            svc = _FakeOwnedService(owner_id="joao.silva")
            self._call(["auditor"], "joao.silva", svc)


class TestPatchProjectConfigRouteAuthorization:
    def _call(self, roles: list[str], x_user: str, svc):
        from concilium.presentation.api.routes.projects import patch_project_config

        return patch_project_config(
            request=_fake_request(roles),
            project_id="proj-1",
            req={"nome": "Novo nome"},
            x_user=x_user,
            service=svc,
        )

    def test_owner_with_role_can_patch(self):
        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}):
            svc = _FakeOwnedService(owner_id="joao.silva")
            result = self._call(["engineer"], "joao.silva", svc)
            assert result["updated"] == ["nome"]

    def test_non_owner_denied(self):
        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}), pytest.raises(PermissionError):
            svc = _FakeOwnedService(owner_id="joao.silva")
            self._call(["engineer"], "maria.santos", svc)

    def test_role_without_permission_denied(self):
        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}), pytest.raises(PermissionError):
            svc = _FakeOwnedService(owner_id="joao.silva")
            self._call(["catalog-manager"], "joao.silva", svc)


class TestTransferOwnershipRoute:
    """Wiring da rota POST /transfer-ownership — branch admin (forçado) vs dono (convite)."""

    def _call(self, roles: list[str], x_user: str, svc, owner_novo: str = "maria.santos"):
        from concilium.presentation.api.routes.projects import transfer_ownership
        from concilium.presentation.api.schemas import TransferOwnershipRequest

        return transfer_ownership(
            request=_fake_request(roles),
            project_id="proj-1",
            req=TransferOwnershipRequest(owner_novo=owner_novo),
            x_user=x_user,
            service=svc,
        )

    def test_admin_forces_transfer(self):
        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}):
            svc = _FakeOwnedService(owner_id="joao.silva")
            result = self._call(["admin"], "bruno.admin", svc)
            assert result["owner_id"] == "maria.santos"

    def test_owner_creates_pending_invite(self):
        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}):
            svc = _FakeOwnedService(owner_id="joao.silva")
            result = self._call(["engineer"], "joao.silva", svc)
            assert result["owner_proposto"] == "maria.santos"

    def test_non_owner_non_admin_denied(self):
        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}), pytest.raises(PermissionError):
            svc = _FakeOwnedService(owner_id="joao.silva")
            self._call(["engineer"], "carlos.outro", svc)

    def test_role_without_permission_denied(self):
        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}), pytest.raises(PermissionError):
            svc = _FakeOwnedService(owner_id="joao.silva")
            self._call(["auditor"], "joao.silva", svc)


class TestAcceptRejectOwnershipTransferRoute:
    def test_accept_delegates_to_service(self):
        from concilium.presentation.api.routes.projects import accept_ownership_transfer_route

        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}):
            svc = _FakeOwnedService(owner_id="joao.silva")
            result = accept_ownership_transfer_route(
                request=_fake_request(["engineer"]),
                project_id="proj-1",
                token="tok-123",
                x_user="maria.santos",
                service=svc,
            )
            assert result["owner_id"] == "maria.santos"

    def test_reject_delegates_to_service(self):
        from concilium.presentation.api.routes.projects import reject_ownership_transfer_route

        with patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}):
            svc = _FakeOwnedService(owner_id="joao.silva")
            result = reject_ownership_transfer_route(
                request=_fake_request(["engineer"]),
                project_id="proj-1",
                token="tok-123",
                x_user="maria.santos",
                service=svc,
            )
            assert result["owner_id"] == "joao.silva"


# ---------------------------------------------------------------------------
# D4/F3 — Handover híbrido: forçado (admin) vs convite (dono) + accept/reject/expiração
# ---------------------------------------------------------------------------


class TestOwnershipTransferForced:
    def test_admin_forces_transfer_immediately(self, repo, audit):
        project = _make_project(repo, owner_id="joao.silva")
        result = transfer_ownership_forced(project, "maria.santos", actor="admin-bruno", audit=audit)
        assert result["owner_id"] == "maria.santos"
        reloaded = repo.get_project(project.meta["id"])
        assert reloaded.meta["owner_id"] == "maria.santos"
        assert reloaded.meta["owner_assigned_at"] is not None

    def test_forced_transfer_clears_any_pending_invite(self, repo, audit):
        project = _make_project(repo, owner_id="joao.silva")
        create_ownership_transfer_pending(project, "carlos.eng", actor="joao.silva", audit=audit)
        transfer_ownership_forced(project, "maria.santos", actor="admin-bruno", audit=audit)
        reloaded = repo.get_project(project.meta["id"])
        assert not reloaded.meta.get("ownership_transfer_pending")

    def test_forced_transfer_logs_audit_action(self, repo, audit):
        project = _make_project(repo, owner_id="joao.silva")
        transfer_ownership_forced(project, "maria.santos", actor="admin-bruno", audit=audit)
        entries = audit.list(project)
        actions = [e.get("ownership_action") for e in entries if e.get("ownership_action")]
        assert any(a["action"] == "transfer_forced" and a["owner_proposto_ou_novo"] == "maria.santos" for a in actions)


class TestOwnershipTransferPendingInvite:
    def test_owner_creates_pending_invite_without_changing_owner(self, repo, audit):
        project = _make_project(repo, owner_id="joao.silva")
        pending = create_ownership_transfer_pending(project, "maria.santos", actor="joao.silva", audit=audit)
        assert isinstance(pending, OwnershipTransferPending)
        reloaded = repo.get_project(project.meta["id"])
        assert reloaded.meta["owner_id"] == "joao.silva"
        assert reloaded.meta["ownership_transfer_pending"]["owner_proposto"] == "maria.santos"

    def test_invite_created_logs_audit_action(self, repo, audit):
        project = _make_project(repo, owner_id="joao.silva")
        create_ownership_transfer_pending(project, "maria.santos", actor="joao.silva", audit=audit)
        entries = audit.list(project)
        actions = [e.get("ownership_action") for e in entries if e.get("ownership_action")]
        assert any(a["action"] == "invite_created" for a in actions)

    def test_accept_transfers_ownership(self, repo, audit):
        project = _make_project(repo, owner_id="joao.silva")
        pending = create_ownership_transfer_pending(project, "maria.santos", actor="joao.silva", audit=audit)
        result = accept_ownership_transfer(project, pending.token, actor="maria.santos", audit=audit)
        assert result["owner_id"] == "maria.santos"
        reloaded = repo.get_project(project.meta["id"])
        assert reloaded.meta["owner_id"] == "maria.santos"
        assert not reloaded.meta.get("ownership_transfer_pending")

    def test_accept_wrong_actor_denied(self, repo, audit):
        project = _make_project(repo, owner_id="joao.silva")
        pending = create_ownership_transfer_pending(project, "maria.santos", actor="joao.silva", audit=audit)
        with pytest.raises(PermissionError):
            accept_ownership_transfer(project, pending.token, actor="carlos.eng", audit=audit)

    def test_reject_keeps_owner_unchanged(self, repo, audit):
        project = _make_project(repo, owner_id="joao.silva")
        pending = create_ownership_transfer_pending(project, "maria.santos", actor="joao.silva", audit=audit)
        result = reject_ownership_transfer(project, pending.token, actor="maria.santos", audit=audit)
        assert result["owner_id"] == "joao.silva"
        reloaded = repo.get_project(project.meta["id"])
        assert reloaded.meta["owner_id"] == "joao.silva"
        assert not reloaded.meta.get("ownership_transfer_pending")

    def test_accept_with_unknown_token_raises_not_found(self, repo, audit):
        project = _make_project(repo, owner_id="joao.silva")
        with pytest.raises(FileNotFoundError):
            accept_ownership_transfer(project, "token-invalido", actor="maria.santos", audit=audit)

    def test_accept_after_ttl_expiration_raises_value_error(self, repo, audit):
        project = _make_project(repo, owner_id="joao.silva")
        pending = create_ownership_transfer_pending(project, "maria.santos", actor="joao.silva", audit=audit)
        # Força expiração retroagindo expira_em.
        meta = dict(project.meta)
        expired = dict(meta["ownership_transfer_pending"])
        expired["expira_em"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        project.update_meta(ownership_transfer_pending=expired)
        with pytest.raises(ValueError):
            accept_ownership_transfer(project, pending.token, actor="maria.santos", audit=audit)
        # owner_id não muda quando expira.
        reloaded = repo.get_project(project.meta["id"])
        assert reloaded.meta["owner_id"] == "joao.silva"

    def test_expired_invite_logs_audit_action(self, repo, audit):
        project = _make_project(repo, owner_id="joao.silva")
        pending = create_ownership_transfer_pending(project, "maria.santos", actor="joao.silva", audit=audit)
        meta = dict(project.meta)
        expired = dict(meta["ownership_transfer_pending"])
        expired["expira_em"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        project.update_meta(ownership_transfer_pending=expired)
        with pytest.raises(ValueError):
            accept_ownership_transfer(project, pending.token, actor="maria.santos", audit=audit)
        entries = audit.list(project)
        actions = [e.get("ownership_action") for e in entries if e.get("ownership_action")]
        assert any(a["action"] == "invite_expired" for a in actions)

    def test_reject_with_unknown_token_raises_not_found(self, repo, audit):
        project = _make_project(repo, owner_id="joao.silva")
        create_ownership_transfer_pending(project, "maria.santos", actor="joao.silva", audit=audit)
        with pytest.raises(FileNotFoundError):
            reject_ownership_transfer(project, "token-invalido", actor="maria.santos", audit=audit)

    def test_reject_wrong_actor_denied(self, repo, audit):
        project = _make_project(repo, owner_id="joao.silva")
        pending = create_ownership_transfer_pending(project, "maria.santos", actor="joao.silva", audit=audit)
        with pytest.raises(PermissionError):
            reject_ownership_transfer(project, pending.token, actor="carlos.eng", audit=audit)


# ---------------------------------------------------------------------------
# D5 — mine=true filtra por owner_id
# ---------------------------------------------------------------------------


class TestMineFilter:
    def test_list_projects_filters_by_owner(self, repo):
        from concilium.application.services.project.audit_service import AuditService
        from concilium.application.services.project.project_service import ProjectService

        svc = ProjectService(repo, AuditService())
        _make_project(repo, owner_id="joao.silva")
        _make_project(repo, owner_id="maria.santos")
        _make_project(repo, owner_id="joao.silva")

        mine = svc.list_projects(owner_id="joao.silva")
        assert len(mine) == 2
        assert all(item["owner_id"] == "joao.silva" for item in mine)

    def test_list_projects_without_filter_returns_all(self, repo):
        from concilium.application.services.project.audit_service import AuditService
        from concilium.application.services.project.project_service import ProjectService

        svc = ProjectService(repo, AuditService())
        _make_project(repo, owner_id="joao.silva")
        _make_project(repo, owner_id="maria.santos")

        all_items = svc.list_projects()
        assert len(all_items) == 2


# ---------------------------------------------------------------------------
# D6 — OwnershipTransferAction é best-effort (nunca propaga exceção)
# ---------------------------------------------------------------------------


class TestOwnershipAuditBestEffort:
    def test_log_ownership_transfer_action_swallows_exceptions(self):
        audit = AuditService()
        broken_project = MagicMock()
        broken_project.append_jsonl.side_effect = RuntimeError("disco cheio")
        action = OwnershipTransferAction(
            action="transfer_forced",
            project_id="proj-x",
            actor_id="admin-bruno",
            owner_anterior="joao.silva",
            owner_proposto_ou_novo="maria.santos",
        )
        # Não deve levantar, mesmo com falha de I/O no append_jsonl.
        audit.log_ownership_transfer_action(broken_project, action)

    def test_ownership_transfer_action_to_dict_shape(self):
        action = OwnershipTransferAction(
            action="invite_accepted",
            project_id="proj-x",
            actor_id="maria.santos",
            owner_anterior="joao.silva",
            owner_proposto_ou_novo="maria.santos",
        )
        d = action.to_dict()
        assert d["action"] == "invite_accepted"
        assert d["owner_anterior"] == "joao.silva"
        assert d["owner_proposto_ou_novo"] == "maria.santos"
        assert "ts" in d


class TestOwnershipHelpersInternals:
    """_email_for / _notify_ownership_event / OwnershipTransferPending.from_dict."""

    def test_email_for_returns_none_when_client_id_is_falsy(self):
        assert _email_for(None) is None
        assert _email_for("") is None

    def test_notify_ownership_event_swallows_exception(self):
        def _boom(*args):
            raise RuntimeError("smtp indisponível")

        # Não deve levantar, mesmo com notify_fn quebrando.
        _notify_ownership_event(_boom, "arg1", "arg2")

    def test_notify_ownership_event_calls_notify_fn_with_args(self):
        notify_fn = MagicMock()
        _notify_ownership_event(notify_fn, "a", "b", "c")
        notify_fn.assert_called_once_with("a", "b", "c")

    def test_ownership_transfer_pending_from_dict_roundtrip(self):
        pending = OwnershipTransferPending(
            token="tok-abc",
            project_id="proj-x",
            owner_atual="joao.silva",
            owner_proposto="maria.santos",
            criado_em="2026-01-01T00:00:00+00:00",
            expira_em="2026-01-02T00:00:00+00:00",
        )
        rebuilt = OwnershipTransferPending.from_dict(pending.to_dict())
        assert rebuilt == pending


# ---------------------------------------------------------------------------
# D7/F7 — find_projects_by_owner + remove-user CLI propagation
# ---------------------------------------------------------------------------


class TestFindProjectsByOwner:
    def test_finds_all_projects_owned_by_client(self, repo):
        _make_project(repo, owner_id="joao.silva")
        _make_project(repo, owner_id="maria.santos")
        _make_project(repo, owner_id="joao.silva")
        found = find_projects_by_owner(repo, "joao.silva")
        assert len(found) == 2
        assert all(p.meta["owner_id"] == "joao.silva" for p in found)

    def test_returns_empty_list_when_no_projects_owned(self, repo):
        _make_project(repo, owner_id="maria.santos")
        assert find_projects_by_owner(repo, "joao.silva") == []


class TestRemoveUserCliOwnershipPropagation:
    def _run(self, **kwargs):
        from typer.testing import CliRunner

        from concilium.presentation.cli.commands_auth import app

        runner = CliRunner()
        args = ["remove-user", "--id", kwargs.pop("client_id", "joao.silva"), "--yes"]
        if kwargs.get("reassign_to"):
            args += ["--reassign-to", kwargs["reassign_to"]]
        if kwargs.get("force"):
            args += ["--force"]
            if kwargs.get("force_yes"):
                args += ["--force-yes"]
        return runner.invoke(app, args)

    def test_blocks_removal_when_owner_of_projects_without_flags(self, tmp_path, monkeypatch):
        from concilium.infrastructure.auth.auth_store import AuthStore

        store = AuthStore(data_dir=tmp_path / "auth")
        store.add_client("joao.silva", "secret123", ["engineer"])
        monkeypatch.setattr(
            "concilium.infrastructure.auth.auth_store.get_auth_store",
            lambda: store,
        )
        repo = FileProjectRepository(tmp_path / "projetos")
        _make_project(repo, owner_id="joao.silva")
        monkeypatch.setattr("concilium.presentation.cli.shared.project_repository", lambda **kw: repo)

        result = self._run(client_id="joao.silva")
        assert result.exit_code != 0
        assert store.remove_client("joao.silva") is True  # cliente NÃO deveria ter sido removido antes disso

    def test_reassign_to_transfers_then_removes(self, tmp_path, monkeypatch):
        from concilium.infrastructure.auth.auth_store import AuthStore

        store = AuthStore(data_dir=tmp_path / "auth")
        store.add_client("joao.silva", "secret123", ["engineer"])
        monkeypatch.setattr(
            "concilium.infrastructure.auth.auth_store.get_auth_store",
            lambda: store,
        )
        repo = FileProjectRepository(tmp_path / "projetos")
        project = _make_project(repo, owner_id="joao.silva")
        monkeypatch.setattr("concilium.presentation.cli.shared.project_repository", lambda **kw: repo)

        result = self._run(client_id="joao.silva", reassign_to="maria.santos")
        assert result.exit_code == 0
        reloaded = repo.get_project(project.meta["id"])
        assert reloaded.meta["owner_id"] == "maria.santos"
        assert store.remove_client("joao.silva") is False  # já foi removido pelo comando

    def test_force_removes_leaving_orphaned_owner_id(self, tmp_path, monkeypatch):
        from concilium.infrastructure.auth.auth_store import AuthStore

        store = AuthStore(data_dir=tmp_path / "auth")
        store.add_client("joao.silva", "secret123", ["engineer"])
        monkeypatch.setattr(
            "concilium.infrastructure.auth.auth_store.get_auth_store",
            lambda: store,
        )
        repo = FileProjectRepository(tmp_path / "projetos")
        project = _make_project(repo, owner_id="joao.silva")
        monkeypatch.setattr("concilium.presentation.cli.shared.project_repository", lambda **kw: repo)

        result = self._run(client_id="joao.silva", force=True, force_yes=True)
        assert result.exit_code == 0
        reloaded = repo.get_project(project.meta["id"])
        assert reloaded.meta["owner_id"] == "joao.silva"  # órfão: client não existe mais no auth store
        assert store.remove_client("joao.silva") is False  # já removido

    def test_no_projects_owned_behaves_like_before(self, tmp_path, monkeypatch):
        from concilium.infrastructure.auth.auth_store import AuthStore

        store = AuthStore(data_dir=tmp_path / "auth")
        store.add_client("joao.silva", "secret123", ["engineer"])
        monkeypatch.setattr(
            "concilium.infrastructure.auth.auth_store.get_auth_store",
            lambda: store,
        )
        repo = FileProjectRepository(tmp_path / "projetos")
        monkeypatch.setattr("concilium.presentation.cli.shared.project_repository", lambda **kw: repo)

        result = self._run(client_id="joao.silva")
        assert result.exit_code == 0
        assert store.remove_client("joao.silva") is False  # já removido, comportamento idêntico ao atual
