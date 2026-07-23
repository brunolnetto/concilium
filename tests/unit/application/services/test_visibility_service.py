"""Tests for application/services/visibility_service.py (ADR-143)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from concilium.application.services.visibility_service import list_visible_users


def _make_client(client_id: str, roles: list[str], email: str = "", active: bool = True, deleted_at: str = ""):
    from concilium.infrastructure.auth.auth_store import ClientRecord

    return ClientRecord(
        client_id=client_id,
        secret_hash="sha256:x",
        roles=roles,
        created_at="2026-01-01T00:00:00",
        active=active,
        email=email,
        deleted_at=deleted_at,
    )


class TestListVisibleUsers:
    def test_filters_by_role_visibility_matrix(self):
        """engineer só vê engineer/admin (ROLE_VISIBILITY) — não operator nem catalog-manager."""
        clients = [
            _make_client("eng2", ["engineer"], email="eng2@x.com"),
            _make_client("adm1", ["admin"], email="adm1@x.com"),
            _make_client("op1", ["operator"], email="op1@x.com"),
            _make_client("cat1", ["catalog-manager"], email="cat1@x.com"),
        ]
        store = MagicMock()
        store.list_clients.return_value = clients
        with patch("concilium.application.services.visibility_service.get_auth_store", return_value=store):
            result = list_visible_users("eng1", ["engineer"])

        ids = {u["client_id"] for u in result}
        assert ids == {"eng2", "adm1"}

    def test_excludes_caller_itself(self):
        clients = [_make_client("adm1", ["admin"], email="adm1@x.com")]
        store = MagicMock()
        store.list_clients.return_value = clients
        with patch("concilium.application.services.visibility_service.get_auth_store", return_value=store):
            result = list_visible_users("adm1", ["admin"])

        assert result == []

    def test_excludes_soft_deleted_clients(self):
        clients = [_make_client("adm1", ["admin"], email="adm1@x.com", deleted_at="2026-01-01T00:00:00")]
        store = MagicMock()
        store.list_clients.return_value = clients
        with patch("concilium.application.services.visibility_service.get_auth_store", return_value=store):
            result = list_visible_users("someone", ["admin"])

        assert result == []

    def test_response_fields_never_include_secrets_or_devices(self):
        clients = [_make_client("adm1", ["admin"], email="adm1@x.com")]
        store = MagicMock()
        store.list_clients.return_value = clients
        with patch("concilium.application.services.visibility_service.get_auth_store", return_value=store):
            result = list_visible_users("someone", ["admin"])

        assert result == [{"client_id": "adm1", "email": "adm1@x.com", "roles": ["admin"], "active": True}]

    def test_records_visibility_query_for_each_visible_target(self):
        clients = [
            _make_client("adm1", ["admin"], email="adm1@x.com"),
            _make_client("eng2", ["engineer"], email="eng2@x.com"),
        ]
        store = MagicMock()
        store.list_clients.return_value = clients
        with patch("concilium.application.services.visibility_service.get_auth_store", return_value=store):
            list_visible_users("eng1", ["engineer"])

        store.record_visibility_queries.assert_called_once_with(
            observer_client_id="eng1",
            observer_roles=["engineer"],
            target_client_ids=["adm1", "eng2"],
        )

    def test_no_recording_when_caller_id_is_none(self):
        """Fora de request MCP/API real (ex.: stdio sem contexto), não há observador a registrar."""
        clients = [_make_client("adm1", ["admin"], email="adm1@x.com")]
        store = MagicMock()
        store.list_clients.return_value = clients
        with patch("concilium.application.services.visibility_service.get_auth_store", return_value=store):
            result = list_visible_users(None, ["admin"])

        store.record_visibility_queries.assert_not_called()
        assert len(result) == 1

    def test_unknown_role_sees_nothing(self):
        clients = [_make_client("adm1", ["admin"], email="adm1@x.com")]
        store = MagicMock()
        store.list_clients.return_value = clients
        with patch("concilium.application.services.visibility_service.get_auth_store", return_value=store):
            result = list_visible_users("someone", ["not-a-role"])

        assert result == []
