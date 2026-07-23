"""Tests for application/services/visibility_digest_service.py (ADR-143 D7/D8)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from concilium.application.services.visibility_digest_service import enviar_digest_visibilidade


def _make_client(client_id: str, roles: list[str], email: str = "", active: bool = True):
    from concilium.infrastructure.auth.auth_store import ClientRecord

    return ClientRecord(
        client_id=client_id,
        secret_hash="sha256:x",
        roles=roles,
        created_at="2026-01-01T00:00:00",
        active=active,
        email=email,
    )


def _make_query(target_id: str, observer_id: str, roles: list[str]):
    from concilium.infrastructure.auth.auth_store import VisibilityQueryRecord

    return VisibilityQueryRecord(
        target_client_id=target_id,
        observer_client_id=observer_id,
        observer_roles=roles,
        queried_at="2026-07-20T00:00:00",
    )


class TestEnviarDigestVisibilidade:
    def test_sem_pendencias_nao_consulta_clientes_nem_envia(self):
        store = MagicMock()
        store.pop_pending_visibility_queries.return_value = []

        with patch(
            "concilium.application.services.visibility_digest_service.get_auth_store",
            return_value=store,
        ):
            enviados = enviar_digest_visibilidade()

        store.list_clients.assert_not_called()
        assert enviados == 0

    def test_envia_um_email_por_alvo_com_pendencias(self):
        store = MagicMock()
        store.pop_pending_visibility_queries.return_value = [
            _make_query("target1", "obs1", ["engineer"]),
            _make_query("target2", "obs1", ["engineer"]),
        ]
        store.list_clients.return_value = [
            _make_client("target1", ["admin"], email="t1@x.com"),
            _make_client("target2", ["engineer"], email="t2@x.com"),
        ]
        mock_notify = MagicMock(return_value=True)

        with (
            patch(
                "concilium.application.services.visibility_digest_service.get_auth_store",
                return_value=store,
            ),
            patch(
                "concilium.application.services.visibility_digest_service.notify_visibility_queried",
                mock_notify,
            ),
        ):
            enviados = enviar_digest_visibilidade()

        assert enviados == 2
        recipients = {call.args[0] for call in mock_notify.call_args_list}
        assert recipients == {"t1@x.com", "t2@x.com"}

    def test_agrupa_multiplas_consultas_ao_mesmo_alvo_em_um_so_email(self):
        store = MagicMock()
        store.pop_pending_visibility_queries.return_value = [
            _make_query("target1", "obs1", ["engineer"]),
            _make_query("target1", "obs1", ["engineer"]),
            _make_query("target1", "obs2", ["admin"]),
        ]
        store.list_clients.return_value = [_make_client("target1", ["admin"], email="t1@x.com")]
        mock_notify = MagicMock(return_value=True)

        with (
            patch(
                "concilium.application.services.visibility_digest_service.get_auth_store",
                return_value=store,
            ),
            patch(
                "concilium.application.services.visibility_digest_service.notify_visibility_queried",
                mock_notify,
            ),
        ):
            enviados = enviar_digest_visibilidade()

        assert enviados == 1
        mock_notify.assert_called_once()
        resumo = mock_notify.call_args.args[1]
        counts = {(observer_id, count) for observer_id, _roles, count in resumo}
        assert counts == {("obs1", 2), ("obs2", 1)}

    def test_pula_alvo_inativo(self):
        store = MagicMock()
        store.pop_pending_visibility_queries.return_value = [_make_query("target1", "obs1", ["engineer"])]
        store.list_clients.return_value = [_make_client("target1", ["admin"], email="t1@x.com", active=False)]
        mock_notify = MagicMock(return_value=True)

        with (
            patch(
                "concilium.application.services.visibility_digest_service.get_auth_store",
                return_value=store,
            ),
            patch(
                "concilium.application.services.visibility_digest_service.notify_visibility_queried",
                mock_notify,
            ),
        ):
            enviados = enviar_digest_visibilidade()

        assert enviados == 0
        mock_notify.assert_not_called()

    def test_pula_alvo_sem_email(self):
        store = MagicMock()
        store.pop_pending_visibility_queries.return_value = [_make_query("target1", "obs1", ["engineer"])]
        store.list_clients.return_value = [_make_client("target1", ["admin"], email="")]
        mock_notify = MagicMock(return_value=True)

        with (
            patch(
                "concilium.application.services.visibility_digest_service.get_auth_store",
                return_value=store,
            ),
            patch(
                "concilium.application.services.visibility_digest_service.notify_visibility_queried",
                mock_notify,
            ),
        ):
            enviados = enviar_digest_visibilidade()

        assert enviados == 0
        mock_notify.assert_not_called()

    def test_pula_alvo_que_nao_existe_mais_no_store(self):
        store = MagicMock()
        store.pop_pending_visibility_queries.return_value = [_make_query("ghost", "obs1", ["engineer"])]
        store.list_clients.return_value = []
        mock_notify = MagicMock(return_value=True)

        with (
            patch(
                "concilium.application.services.visibility_digest_service.get_auth_store",
                return_value=store,
            ),
            patch(
                "concilium.application.services.visibility_digest_service.notify_visibility_queried",
                mock_notify,
            ),
        ):
            enviados = enviar_digest_visibilidade()

        assert enviados == 0

    def test_conta_apenas_envios_bem_sucedidos(self):
        store = MagicMock()
        store.pop_pending_visibility_queries.return_value = [
            _make_query("target1", "obs1", ["engineer"]),
            _make_query("target2", "obs1", ["engineer"]),
        ]
        store.list_clients.return_value = [
            _make_client("target1", ["admin"], email="t1@x.com"),
            _make_client("target2", ["engineer"], email="t2@x.com"),
        ]
        mock_notify = MagicMock(side_effect=[True, False])

        with (
            patch(
                "concilium.application.services.visibility_digest_service.get_auth_store",
                return_value=store,
            ),
            patch(
                "concilium.application.services.visibility_digest_service.notify_visibility_queried",
                mock_notify,
            ),
        ):
            enviados = enviar_digest_visibilidade()

        assert enviados == 1
