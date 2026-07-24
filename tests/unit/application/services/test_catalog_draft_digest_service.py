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


# ---------------------------------------------------------------------------
# ADR-150 D5: rascunhos de override de projeto no mesmo digest
# ---------------------------------------------------------------------------


def _write_projeto_estado(projects_root: Path, projeto_id: str, **fields) -> None:
    overrides_dir = projects_root / projeto_id / "overrides"
    overrides_dir.mkdir(parents=True, exist_ok=True)
    data = {"_rascunho": True, "created_by": "eng1", "projeto_id": projeto_id, **fields}
    (overrides_dir / "_rascunho_estado.json").write_text(json.dumps(data), encoding="utf-8")


def _write_projeto_overrides(projects_root: Path, projeto_id: str, overrides: dict) -> None:
    overrides_dir = projects_root / projeto_id / "overrides"
    overrides_dir.mkdir(parents=True, exist_ok=True)
    (overrides_dir / "insumos_override.json").write_text(json.dumps(overrides), encoding="utf-8")


def _write_projeto_cpu_overrides(projects_root: Path, projeto_id: str, overrides: dict) -> None:
    overrides_dir = projects_root / projeto_id / "overrides"
    overrides_dir.mkdir(parents=True, exist_ok=True)
    (overrides_dir / "cpus_override.json").write_text(json.dumps(overrides), encoding="utf-8")


def _write_projeto_meta(projects_root: Path, projeto_id: str, owner_id: str | None) -> None:
    (projects_root / projeto_id).mkdir(parents=True, exist_ok=True)
    (projects_root / projeto_id / "meta.json").write_text(json.dumps({"owner_id": owner_id}), encoding="utf-8")


class TestRascunhosPendentesProjeto:
    def test_override_pendente_com_estado_rascunho_incluido(self, tmp_path: Path):
        (tmp_path / "contextos").mkdir()
        projects_root = tmp_path / "projetos"
        _write_projeto_estado(projects_root, "PROJ-001")
        _write_projeto_overrides(projects_root, "PROJ-001", {"INS-001::BASE": {"preco": 10.0}})

        result = rascunhos_pendentes(tmp_path, projects_root)

        assert "projeto:PROJ-001" in result
        assert result["projeto:PROJ-001"][0]["projeto_id"] == "PROJ-001"
        assert result["projeto:PROJ-001"][0]["created_by"] == "eng1"

    def test_estado_aprovado_excluido(self, tmp_path: Path):
        (tmp_path / "contextos").mkdir()
        projects_root = tmp_path / "projetos"
        _write_projeto_estado(projects_root, "PROJ-001", _aprovado=True)
        _write_projeto_overrides(projects_root, "PROJ-001", {"INS-001::BASE": {"preco": 10.0}})

        assert rascunhos_pendentes(tmp_path, projects_root) == {}

    def test_sem_overrides_pendentes_excluido(self, tmp_path: Path):
        (tmp_path / "contextos").mkdir()
        projects_root = tmp_path / "projetos"
        _write_projeto_estado(projects_root, "PROJ-001")
        _write_projeto_overrides(projects_root, "PROJ-001", {})

        assert rascunhos_pendentes(tmp_path, projects_root) == {}

    def test_projeto_sem_estado_de_rascunho_excluido(self, tmp_path: Path):
        (tmp_path / "contextos").mkdir()
        projects_root = tmp_path / "projetos"
        (projects_root / "PROJ-001").mkdir(parents=True)

        assert rascunhos_pendentes(tmp_path, projects_root) == {}

    def test_projects_root_omitido_nao_afeta_contextos_globais(self, tmp_path: Path):
        _write_version(tmp_path, "mendeslobo", "v1", {"motivo": "base"})
        _write_version(tmp_path, "mendeslobo", "v2", {"_rascunho": True})

        result = rascunhos_pendentes(tmp_path)

        assert set(result.keys()) == {"mendeslobo"}

    def test_override_de_cpu_sem_insumo_tambem_e_pendente(self, tmp_path: Path):
        """ADR-150, extensão CPU: projeto com só CPU pendente também deve aparecer no digest."""
        (tmp_path / "contextos").mkdir()
        projects_root = tmp_path / "projetos"
        _write_projeto_estado(projects_root, "PROJ-001")
        _write_projeto_cpu_overrides(projects_root, "PROJ-001", {"CPU-001": {"producao_horaria": 4.0}})

        result = rascunhos_pendentes(tmp_path, projects_root)

        assert "projeto:PROJ-001" in result
        assert "CPU" in result["projeto:PROJ-001"][0]["motivo"]

    def test_override_de_insumo_e_cpu_combinados_no_mesmo_motivo(self, tmp_path: Path):
        (tmp_path / "contextos").mkdir()
        projects_root = tmp_path / "projetos"
        _write_projeto_estado(projects_root, "PROJ-001")
        _write_projeto_overrides(projects_root, "PROJ-001", {"INS-001::BASE": {"preco": 10.0}})
        _write_projeto_cpu_overrides(projects_root, "PROJ-001", {"CPU-001": {"producao_horaria": 4.0}})

        result = rascunhos_pendentes(tmp_path, projects_root)

        motivo = result["projeto:PROJ-001"][0]["motivo"]
        assert "insumo" in motivo
        assert "CPU" in motivo

    def test_sem_overrides_de_insumo_nem_cpu_excluido(self, tmp_path: Path):
        (tmp_path / "contextos").mkdir()
        projects_root = tmp_path / "projetos"
        _write_projeto_estado(projects_root, "PROJ-001")
        _write_projeto_overrides(projects_root, "PROJ-001", {})
        _write_projeto_cpu_overrides(projects_root, "PROJ-001", {})

        assert rascunhos_pendentes(tmp_path, projects_root) == {}


class TestEnviarDigestNotificaDonoDoProjeto:
    def test_dono_do_projeto_recebe_mesmo_sem_role_catalog_manager(self, tmp_path: Path):
        (tmp_path / "contextos").mkdir()
        projects_root = tmp_path / "projetos"
        _write_projeto_estado(projects_root, "PROJ-001")
        _write_projeto_overrides(projects_root, "PROJ-001", {"INS-001::BASE": {"preco": 10.0}})
        _write_projeto_meta(projects_root, "PROJ-001", owner_id="owner1")

        clients = [_make_client("owner1", ["engineer"], email="owner1@x.com")]
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
            enviados = enviar_digest_rascunhos_pendentes(tmp_path, projects_root)

        assert enviados == 1
        mock_notify.assert_called_once()
        assert mock_notify.call_args.args[0] == "owner1@x.com"
        assert "projeto:PROJ-001" in mock_notify.call_args.args[1]

    def test_catalog_manager_e_dono_nao_duplicam_envio_se_mesmo_email(self, tmp_path: Path):
        (tmp_path / "contextos").mkdir()
        projects_root = tmp_path / "projetos"
        _write_projeto_estado(projects_root, "PROJ-001")
        _write_projeto_overrides(projects_root, "PROJ-001", {"INS-001::BASE": {"preco": 10.0}})
        _write_projeto_meta(projects_root, "PROJ-001", owner_id="mgr1")

        clients = [_make_client("mgr1", ["catalog-manager"], email="mgr1@x.com")]
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
            enviados = enviar_digest_rascunhos_pendentes(tmp_path, projects_root)

        assert enviados == 1
        assert mock_notify.call_count == 1

    def test_sem_owner_id_nao_quebra_e_nao_notifica_ninguem_extra(self, tmp_path: Path):
        (tmp_path / "contextos").mkdir()
        projects_root = tmp_path / "projetos"
        _write_projeto_estado(projects_root, "PROJ-001")
        _write_projeto_overrides(projects_root, "PROJ-001", {"INS-001::BASE": {"preco": 10.0}})
        # sem meta.json / owner_id

        mock_store = MagicMock()
        mock_store.list_clients.return_value = []
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
            enviados = enviar_digest_rascunhos_pendentes(tmp_path, projects_root)

        assert enviados == 0
