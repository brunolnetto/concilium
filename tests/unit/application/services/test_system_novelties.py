"""Tests for application/services/system_novelties.py (ADR-144 D2/D3).

TDD: escritos antes da implementação. `check_and_report_novidades(client_id)`
é chamada por `ping()` — compara o estado atual (deploy log + versão do
skill) contra os cursores do `client_id` e retorna o que há de novo, já
marcando o cursor de deploy como visto (D3: o de skill só avança quando
`obter_instrucoes_atualizadas()` é chamada, não aqui).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_client(client_id: str, last_deploy_seen: str = "", last_skill_version_seen: int = 0):
    from concilium.infrastructure.auth.auth_store import ClientRecord

    return ClientRecord(
        client_id=client_id,
        secret_hash="sha256:x",
        roles=["operator"],
        created_at="2026-01-01T00:00:00",
        last_deploy_seen=last_deploy_seen,
        last_skill_version_seen=last_skill_version_seen,
    )


def _make_deploy_entry(promoted_at="2026-07-20T14:32:00+00:00", resumo="ADR-144 ao vivo"):
    from concilium.infrastructure.deploy.deploy_log_store import DeployLogEntry

    return DeployLogEntry(
        image_tag="90caf8ae",
        api_revision="concilium-api--0000091",
        mcp_revision="concilium-mcp--0000097",
        promoted_at=promoted_at,
        resumo=resumo,
    )


_MOD = "concilium.application.services.system_novelties"


class TestNoIdentity:
    def test_returns_none_when_client_id_is_none(self):
        from concilium.application.services.system_novelties import check_and_report_novidades

        assert check_and_report_novidades(None) is None

    def test_returns_none_when_client_not_found(self):
        from concilium.application.services.system_novelties import check_and_report_novidades

        store = MagicMock()
        store.get_client.return_value = None
        with patch(f"{_MOD}.get_auth_store", return_value=store):
            assert check_and_report_novidades("ghost") is None


class TestNothingNew:
    def test_returns_none_when_deploy_already_seen_and_skill_up_to_date(self):
        from concilium.application.services.system_novelties import check_and_report_novidades

        entry = _make_deploy_entry(promoted_at="2026-07-20T14:32:00+00:00")
        client = _make_client("c1", last_deploy_seen="2026-07-20T14:32:00+00:00", last_skill_version_seen=1)
        store = MagicMock()
        store.get_client.return_value = client
        deploy_store = MagicMock()
        deploy_store.load_latest.return_value = entry

        with (
            patch(f"{_MOD}.get_auth_store", return_value=store),
            patch(f"{_MOD}._get_deploy_log_store", return_value=deploy_store),
            patch(f"{_MOD}.get_skill_version", return_value=1),
        ):
            result = check_and_report_novidades("c1")

        assert result is None
        store.mark_deploy_seen.assert_not_called()

    def test_returns_none_when_no_deploy_ever_recorded(self):
        from concilium.application.services.system_novelties import check_and_report_novidades

        client = _make_client("c1")
        store = MagicMock()
        store.get_client.return_value = client
        deploy_store = MagicMock()
        deploy_store.load_latest.return_value = None

        with (
            patch(f"{_MOD}.get_auth_store", return_value=store),
            patch(f"{_MOD}._get_deploy_log_store", return_value=deploy_store),
            patch(f"{_MOD}.get_skill_version", return_value=0),
        ):
            result = check_and_report_novidades("c1")

        assert result is None


class TestDeployNotice:
    def test_reports_new_deploy_and_marks_it_seen(self):
        from concilium.application.services.system_novelties import check_and_report_novidades

        entry = _make_deploy_entry(promoted_at="2026-07-20T14:32:00+00:00", resumo="ADR-144 ao vivo")
        client = _make_client("c1", last_deploy_seen="2026-07-19T00:00:00+00:00", last_skill_version_seen=1)
        store = MagicMock()
        store.get_client.return_value = client
        deploy_store = MagicMock()
        deploy_store.load_latest.return_value = entry

        with (
            patch(f"{_MOD}.get_auth_store", return_value=store),
            patch(f"{_MOD}._get_deploy_log_store", return_value=deploy_store),
            patch(f"{_MOD}.get_skill_version", return_value=1),
        ):
            result = check_and_report_novidades("c1")

        assert result is not None
        assert result["deploy"] == {"resumo": "ADR-144 ao vivo", "promoted_at": "2026-07-20T14:32:00+00:00"}
        store.mark_deploy_seen.assert_called_once_with("c1", "2026-07-20T14:32:00+00:00")

    def test_first_ever_ping_with_a_deploy_on_record_reports_it(self):
        """client novo (last_deploy_seen="") vê a última promoção como novidade."""
        from concilium.application.services.system_novelties import check_and_report_novidades

        entry = _make_deploy_entry()
        client = _make_client("c1", last_deploy_seen="", last_skill_version_seen=1)
        store = MagicMock()
        store.get_client.return_value = client
        deploy_store = MagicMock()
        deploy_store.load_latest.return_value = entry

        with (
            patch(f"{_MOD}.get_auth_store", return_value=store),
            patch(f"{_MOD}._get_deploy_log_store", return_value=deploy_store),
            patch(f"{_MOD}.get_skill_version", return_value=1),
        ):
            result = check_and_report_novidades("c1")

        assert result is not None
        assert result["deploy"]["promoted_at"] == entry.promoted_at


class TestSkillNotice:
    def test_reports_outdated_skill_without_marking_it_seen(self):
        """D3/A7: ping() só aponta que há versão nova — não marca como visto.
        Só obter_instrucoes_atualizadas() avança last_skill_version_seen."""
        from concilium.application.services.system_novelties import check_and_report_novidades

        entry = _make_deploy_entry()
        client = _make_client("c1", last_deploy_seen=entry.promoted_at, last_skill_version_seen=1)
        store = MagicMock()
        store.get_client.return_value = client
        deploy_store = MagicMock()
        deploy_store.load_latest.return_value = entry

        with (
            patch(f"{_MOD}.get_auth_store", return_value=store),
            patch(f"{_MOD}._get_deploy_log_store", return_value=deploy_store),
            patch(f"{_MOD}.get_skill_version", return_value=2),
        ):
            result = check_and_report_novidades("c1")

        assert result is not None
        assert result["skill_desatualizado"] is True
        store.mark_skill_version_seen.assert_not_called()

    def test_up_to_date_skill_reports_false(self):
        from concilium.application.services.system_novelties import check_and_report_novidades

        entry = _make_deploy_entry()
        client = _make_client("c1", last_deploy_seen="2026-07-19T00:00:00+00:00", last_skill_version_seen=2)
        store = MagicMock()
        store.get_client.return_value = client
        deploy_store = MagicMock()
        deploy_store.load_latest.return_value = entry

        with (
            patch(f"{_MOD}.get_auth_store", return_value=store),
            patch(f"{_MOD}._get_deploy_log_store", return_value=deploy_store),
            patch(f"{_MOD}.get_skill_version", return_value=2),
        ):
            result = check_and_report_novidades("c1")

        # Há deploy novo (força o dict a existir), mas skill_desatualizado deve ser False.
        assert result is not None
        assert result["skill_desatualizado"] is False
