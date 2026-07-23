"""ADR-134 F3 — 5 notificações de ownership (ADR-126) + wiring em _ownership_helpers.py.

Mapeamento 1:1 com OwnershipTransferAction.action:
  transfer_forced  -> notify_ownership_transfer_forced
  invite_created   -> notify_ownership_invite_created
  invite_accepted  -> notify_ownership_invite_accepted
  invite_rejected  -> notify_ownership_invite_rejected
  invite_expired   -> notify_ownership_invite_expired

Não há uma 6ª notificação para D7 (remove-user --reassign-to): reaproveita o
mesmo `transfer_ownership_forced()` de D4.1 -> mesma notificação.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from concilium.application.services.project._ownership_helpers import (
    accept_ownership_transfer,
    create_ownership_transfer_pending,
    reject_ownership_transfer,
    transfer_ownership_forced,
)
from concilium.application.services.project.audit_service import AuditService
from concilium.infrastructure.storage.file_project_repository import FileProjectRepository

PATCH_AUTH_STORE = "concilium.infrastructure.auth.auth_store.get_auth_store"


def _make_project(repo, owner_id="joao.silva"):
    project = repo.create_project("Projeto Teste", "mendeslobo")
    project.update_meta(owner_id=owner_id, owner_assigned_at=datetime.now(UTC).isoformat())
    return project


def _client(client_id, email=""):
    return MagicMock(client_id=client_id, email=email)


def _store_with(*clients):
    store = MagicMock()
    store.list_clients.return_value = list(clients)
    return store


@pytest.fixture
def repo(tmp_path):
    return FileProjectRepository(tmp_path)


@pytest.fixture
def audit():
    return AuditService()


# ---------------------------------------------------------------------------
# application/services/notifications.py — as 5 funções novas (D6)
# ---------------------------------------------------------------------------


class TestOwnershipNotificationFunctions:
    def _patched_service(self):
        mock_service = MagicMock()
        return patch(
            "concilium.application.services.notifications.get_notification_service",
            return_value=mock_service,
        ), mock_service

    def test_notify_ownership_transfer_forced(self):
        from concilium.application.services.notifications import notify_ownership_transfer_forced

        patcher, mock_service = self._patched_service()
        with patcher:
            notify_ownership_transfer_forced("novo@x.com", "proj1", "joao", "maria")
        kwargs = mock_service.send.call_args.kwargs
        assert kwargs["to"] == "novo@x.com"
        assert ("Novo dono", "maria") in kwargs["context"]["details"]

    def test_notify_ownership_invite_created(self):
        from concilium.application.services.notifications import notify_ownership_invite_created

        patcher, mock_service = self._patched_service()
        with patcher:
            notify_ownership_invite_created("proposto@x.com", "proj1", "joao", "maria", "tok-123")
        kwargs = mock_service.send.call_args.kwargs
        assert "tok-123" in kwargs["context"]["cta"]["url"]
        assert "accept" in kwargs["context"]["cta"]["url"]
        assert "reject" in kwargs["context"]["footer_note"]
        # Copilot (PR #71): links devem apontar para o prefixo real das rotas
        # (presentation/api/routes/projects.py: router = APIRouter(prefix="/api/projects")).
        assert "/api/projects/proj1/transfer-ownership/tok-123/accept" in kwargs["context"]["cta"]["url"]
        assert "/api/projects/proj1/transfer-ownership/tok-123/reject" in kwargs["context"]["footer_note"]

    def test_notify_ownership_invite_accepted(self):
        from concilium.application.services.notifications import notify_ownership_invite_accepted

        patcher, mock_service = self._patched_service()
        with patcher:
            notify_ownership_invite_accepted("anterior@x.com", "proj1", "maria")
        kwargs = mock_service.send.call_args.kwargs
        assert kwargs["to"] == "anterior@x.com"
        assert "maria" in kwargs["context"]["heading"] or ("Novo dono", "maria") in kwargs["context"]["details"]

    def test_notify_ownership_invite_rejected(self):
        from concilium.application.services.notifications import notify_ownership_invite_rejected

        patcher, mock_service = self._patched_service()
        with patcher:
            notify_ownership_invite_rejected("anterior@x.com", "proj1", "maria")
        kwargs = mock_service.send.call_args.kwargs
        assert kwargs["to"] == "anterior@x.com"

    def test_notify_ownership_invite_expired(self):
        from concilium.application.services.notifications import notify_ownership_invite_expired

        patcher, mock_service = self._patched_service()
        with patcher:
            notify_ownership_invite_expired("anterior@x.com", "proj1", "maria")
        kwargs = mock_service.send.call_args.kwargs
        assert kwargs["to"] == "anterior@x.com"


# ---------------------------------------------------------------------------
# Wiring em _ownership_helpers.py
# ---------------------------------------------------------------------------


class TestTransferOwnershipForcedWiring:
    def test_notifies_new_owner_when_email_registered(self, repo, audit):
        project = _make_project(repo, owner_id="joao")
        store = _store_with(_client("maria", email="maria@x.com"))
        with (
            patch(PATCH_AUTH_STORE, return_value=store),
            patch("concilium.application.services.notifications.notify_ownership_transfer_forced") as notify_mock,
        ):
            transfer_ownership_forced(project, "maria", actor="admin1", audit=audit)
        notify_mock.assert_called_once_with("maria@x.com", project.meta["id"], "joao", "maria")

    def test_does_not_notify_when_no_email_registered(self, repo, audit):
        project = _make_project(repo, owner_id="joao")
        store = _store_with(_client("maria", email=""))
        with (
            patch(PATCH_AUTH_STORE, return_value=store),
            patch("concilium.application.services.notifications.notify_ownership_transfer_forced") as notify_mock,
        ):
            transfer_ownership_forced(project, "maria", actor="admin1", audit=audit)
        notify_mock.assert_not_called()

    def test_lookup_failure_never_raises(self, repo, audit):
        """auth_store indisponível não deve bloquear a transferência de ownership."""
        project = _make_project(repo, owner_id="joao")
        with patch(PATCH_AUTH_STORE, side_effect=RuntimeError("store down")):
            result = transfer_ownership_forced(project, "maria", actor="admin1", audit=audit)
        assert result["owner_id"] == "maria"


class TestCreateOwnershipTransferPendingWiring:
    def test_notifies_proposed_owner_when_email_registered(self, repo, audit):
        project = _make_project(repo, owner_id="joao")
        store = _store_with(_client("maria", email="maria@x.com"))
        with (
            patch(PATCH_AUTH_STORE, return_value=store),
            patch("concilium.application.services.notifications.notify_ownership_invite_created") as notify_mock,
        ):
            pending = create_ownership_transfer_pending(project, "maria", actor="joao", audit=audit)
        notify_mock.assert_called_once_with("maria@x.com", project.meta["id"], "joao", "maria", pending.token)


class TestAcceptOwnershipTransferWiring:
    def test_notifies_previous_owner_on_accept(self, repo, audit):
        project = _make_project(repo, owner_id="joao")
        store = _store_with(_client("joao", email="joao@x.com"))
        with patch(PATCH_AUTH_STORE, return_value=store):
            pending = create_ownership_transfer_pending(project, "maria", actor="joao", audit=audit)

        with (
            patch(PATCH_AUTH_STORE, return_value=store),
            patch("concilium.application.services.notifications.notify_ownership_invite_accepted") as notify_mock,
        ):
            accept_ownership_transfer(project, pending.token, actor="maria", audit=audit)
        notify_mock.assert_called_once_with("joao@x.com", project.meta["id"], "maria")

    def test_expired_invite_notifies_expiration_not_acceptance(self, repo, audit):
        project = _make_project(repo, owner_id="joao")
        store = _store_with(_client("joao", email="joao@x.com"))
        with patch(PATCH_AUTH_STORE, return_value=store):
            pending = create_ownership_transfer_pending(project, "maria", actor="joao", audit=audit)

        # Força expiração retroativa do convite.
        expired = dict(project.meta["ownership_transfer_pending"])
        expired["expira_em"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        project.update_meta(ownership_transfer_pending=expired)

        with (
            patch(PATCH_AUTH_STORE, return_value=store),
            patch("concilium.application.services.notifications.notify_ownership_invite_accepted") as accepted_mock,
            patch("concilium.application.services.notifications.notify_ownership_invite_expired") as expired_mock,
            pytest.raises(ValueError),
        ):
            accept_ownership_transfer(project, pending.token, actor="maria", audit=audit)

        accepted_mock.assert_not_called()
        expired_mock.assert_called_once_with("joao@x.com", project.meta["id"], "maria")


class TestRejectOwnershipTransferWiring:
    def test_notifies_previous_owner_on_reject(self, repo, audit):
        project = _make_project(repo, owner_id="joao")
        store = _store_with(_client("joao", email="joao@x.com"))
        with patch(PATCH_AUTH_STORE, return_value=store):
            pending = create_ownership_transfer_pending(project, "maria", actor="joao", audit=audit)

        with (
            patch(PATCH_AUTH_STORE, return_value=store),
            patch("concilium.application.services.notifications.notify_ownership_invite_rejected") as notify_mock,
        ):
            reject_ownership_transfer(project, pending.token, actor="maria", audit=audit)
        notify_mock.assert_called_once_with("joao@x.com", project.meta["id"], "maria")


# ---------------------------------------------------------------------------
# Regressão D7: remove-user --reassign-to dispara notify_ownership_transfer_forced
# (mesma função de D4.1, sem uma 6ª notificação nova).
# ---------------------------------------------------------------------------


class TestRemoveUserReassignToRegressionNotification:
    def test_reassign_to_uses_same_transfer_forced_notification(self, tmp_path):
        from typer.testing import CliRunner

        from concilium.infrastructure.auth.auth_store import AuthStore
        from concilium.presentation.cli.commands_auth import app

        store = AuthStore(data_dir=tmp_path / "auth")
        store.add_client("joao.silva", "secret123", ["engineer"])
        store.add_client("maria.santos", "secret456", ["engineer"], email="maria.santos@x.com")

        repo = FileProjectRepository(tmp_path / "projetos")
        project = _make_project(repo, owner_id="joao.silva")

        runner = CliRunner()
        with (
            patch("concilium.infrastructure.auth.auth_store.get_auth_store", return_value=store),
            patch("concilium.presentation.cli.shared.project_repository", return_value=repo),
            patch("concilium.application.services.notifications.notify_ownership_transfer_forced") as notify_mock,
        ):
            result = runner.invoke(
                app,
                ["remove-user", "--id", "joao.silva", "--reassign-to", "maria.santos", "--yes"],
            )

        assert result.exit_code == 0, result.output
        notify_mock.assert_called_once_with("maria.santos@x.com", project.meta["id"], "joao.silva", "maria.santos")
