"""Tests for application/services/catalog/draft_digest_service.py (ADR-141)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from concilium.application.services.catalog.draft_digest_service import (
    enviar_digest_rascunhos_pendentes,
    rascunhos_pendentes,
)


def _write_version(root: Path, contexto_id: str, version: str, data: dict) -> None:
    versions_dir = root / "contextos" / contexto_id / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    payload = {"version": version, "created_at": "2026-07-16T00:00:00", "created_by": "engineer1", **data}
    (versions_dir / f"{version}.json").write_text(json.dumps(payload), encoding="utf-8")
    current_file = root / "contextos" / contexto_id / "current"
    if not current_file.exists():
        current_file.write_text("v1", encoding="utf-8")


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


class TestRascunhosPendentes:
    def test_rascunho_nao_decidido_incluido(self, tmp_path: Path):
        _write_version(tmp_path, "mendeslobo", "v1", {"motivo": "base"})
        _write_version(tmp_path, "mendeslobo", "v2", {"_rascunho": True, "motivo": "rascunho: reajuste"})

        result = rascunhos_pendentes(tmp_path)

        assert "mendeslobo" in result
        assert [v["version"] for v in result["mendeslobo"]] == ["v2"]

    def test_rascunho_rejeitado_excluido(self, tmp_path: Path):
        _write_version(tmp_path, "mendeslobo", "v1", {"motivo": "base"})
        _write_version(tmp_path, "mendeslobo", "v2", {"_rascunho": True, "_rejeitado": True})

        result = rascunhos_pendentes(tmp_path)

        assert result == {}

    def test_rascunho_ja_promovido_excluido(self, tmp_path: Path):
        _write_version(tmp_path, "mendeslobo", "v1", {"motivo": "base"})
        _write_version(tmp_path, "mendeslobo", "v2", {"_rascunho": True})
        (tmp_path / "contextos" / "mendeslobo" / "current").write_text("v2", encoding="utf-8")

        result = rascunhos_pendentes(tmp_path)

        assert result == {}

    def test_versao_sem_flag_rascunho_excluida(self, tmp_path: Path):
        _write_version(tmp_path, "mendeslobo", "v1", {"motivo": "base"})
        _write_version(tmp_path, "mendeslobo", "v2", {"motivo": "correção pontual, não é campanha"})

        result = rascunhos_pendentes(tmp_path)

        assert result == {}

    def test_multiplos_contextos_agregados(self, tmp_path: Path):
        _write_version(tmp_path, "mendeslobo", "v1", {"motivo": "base"})
        _write_version(tmp_path, "mendeslobo", "v2", {"_rascunho": True})
        _write_version(tmp_path, "rfi-r02", "v1", {"motivo": "base"})
        _write_version(tmp_path, "rfi-r02", "v2", {"_rascunho": True})

        result = rascunhos_pendentes(tmp_path)

        assert set(result.keys()) == {"mendeslobo", "rfi-r02"}

    def test_nenhum_contexto_retorna_dict_vazio(self, tmp_path: Path):
        (tmp_path / "contextos").mkdir()
        assert rascunhos_pendentes(tmp_path) == {}


class TestEnviarDigestRascunhosPendentes:
    def test_sem_pendencias_nao_consulta_destinatarios_nem_envia(self, tmp_path: Path):
        (tmp_path / "contextos").mkdir()

        with patch("concilium.application.services.catalog.draft_digest_service.get_auth_store") as mock_store:
            enviados = enviar_digest_rascunhos_pendentes(tmp_path)

        mock_store.assert_not_called()
        assert enviados == 0

    def test_envia_um_email_por_catalog_manager_ativo_com_email(self, tmp_path: Path):
        _write_version(tmp_path, "mendeslobo", "v1", {"motivo": "base"})
        _write_version(tmp_path, "mendeslobo", "v2", {"_rascunho": True})

        clients = [
            _make_client("mgr1", ["catalog-manager"], email="mgr1@x.com"),
            _make_client("mgr2", ["catalog-manager"], email="mgr2@x.com"),
            _make_client("mgr3-no-email", ["catalog-manager"], email=""),
            _make_client("eng1", ["engineer"], email="eng1@x.com"),
            _make_client("mgr4-inativo", ["catalog-manager"], email="mgr4@x.com", active=False),
        ]
        mock_store = MagicMock()
        mock_store.list_clients.return_value = clients
        mock_notify = MagicMock(return_value=True)

        with (
            patch(
                "concilium.application.services.catalog.draft_digest_service.get_auth_store",
                return_value=mock_store,
            ),
            patch(
                "concilium.application.services.catalog.draft_digest_service.notify_catalog_drafts_pending",
                mock_notify,
            ),
        ):
            enviados = enviar_digest_rascunhos_pendentes(tmp_path)

        assert enviados == 2
        assert mock_notify.call_count == 2
        recipients = {call.args[0] for call in mock_notify.call_args_list}
        assert recipients == {"mgr1@x.com", "mgr2@x.com"}

    def test_conta_apenas_envios_bem_sucedidos(self, tmp_path: Path):
        _write_version(tmp_path, "mendeslobo", "v1", {"motivo": "base"})
        _write_version(tmp_path, "mendeslobo", "v2", {"_rascunho": True})

        clients = [
            _make_client("mgr1", ["catalog-manager"], email="mgr1@x.com"),
            _make_client("mgr2", ["catalog-manager"], email="mgr2@x.com"),
        ]
        mock_store = MagicMock()
        mock_store.list_clients.return_value = clients
        mock_notify = MagicMock(side_effect=[True, False])

        with (
            patch(
                "concilium.application.services.catalog.draft_digest_service.get_auth_store",
                return_value=mock_store,
            ),
            patch(
                "concilium.application.services.catalog.draft_digest_service.notify_catalog_drafts_pending",
                mock_notify,
            ),
        ):
            enviados = enviar_digest_rascunhos_pendentes(tmp_path)

        assert enviados == 1

    def test_usa_config_root_do_storage_settings_quando_omitido(self, tmp_path: Path):
        (tmp_path / "contextos").mkdir()
        mock_storage = MagicMock(config_root=tmp_path)

        with (
            patch(
                "concilium.infrastructure.settings.get_storage",
                return_value=mock_storage,
            ),
            patch("concilium.application.services.catalog.draft_digest_service.get_auth_store") as mock_store,
        ):
            enviados = enviar_digest_rascunhos_pendentes()

        mock_store.assert_not_called()
        assert enviados == 0
