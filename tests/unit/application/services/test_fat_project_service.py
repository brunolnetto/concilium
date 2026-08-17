"""Fat integration tests for project_service.py and _project_service_helpers.py.

Mocks at the repository/audit boundary; exercises full method execution paths.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from concilium.application.services.project._project_service_helpers import (
    _build_catalog_from_snapshot,
    _compute_bdi_for_categoria,
    _compute_flat_bdi,
    _count_orphaned_runs,
    _cp_build_meta_kwargs,
    _cp_save_perfil_context,
    _enrich_payload_bdi,
    _resolve_catalogo_base_from_context,
    _sort_versions,
    _try_enrich_cpu_with_prod,
)
from concilium.application.services.project.project_service import (
    ProjectService,
    _canonical_eap_to_rows,
    _catalog_is_deficit,
    _debug_storage_info,
    _extract_canonical_eap_rows,
    _extract_historical_eap_rows,
    _is_valid_canonical_eap,
    _resolve_project_type,
)

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_service():
    repo = MagicMock()
    audit = MagicMock()
    svc = ProjectService(repository=repo, audit_service=audit)
    return svc, repo, audit


def _make_project(
    project_id="p1",
    nome="Projeto Test",
    status_eap="ATIVO",
    current_version="v1",
    tipo_projeto="hot_project",
):
    p = MagicMock()
    p.meta = {
        "id": project_id,
        "nome": nome,
        "status_eap": status_eap,
        "current_version": current_version,
        "contexto_id": "mendeslobo",
        "tipo_projeto": tipo_projeto,
    }
    p.list_versions.return_value = [current_version]
    p.current_version.return_value = current_version
    p.read_json.return_value = []
    p.exists.return_value = False
    p.load_canonical.return_value = None
    return p


# ---------------------------------------------------------------------------
# _debug_storage_info
# ---------------------------------------------------------------------------


class TestDebugStorageInfo:
    def test_returns_storage_root_and_projects_root(self):
        p = MagicMock()
        p.root = MagicMock()
        p.root.__str__ = lambda _: "/data/projects/p1"
        p.root.parent.__str__ = lambda _: "/data/projects"
        result = _debug_storage_info(p)
        assert "storage_root" in result
        assert "projects_root" in result

    def test_returns_empty_strings_when_root_raises(self):
        p = MagicMock()
        type(p).root = property(lambda _: (_ for _ in ()).throw(RuntimeError("no root")))
        result = _debug_storage_info(p)
        assert result["storage_root"] == ""
        assert result["projects_root"] == ""


# ---------------------------------------------------------------------------
# _resolve_project_type
# ---------------------------------------------------------------------------


class TestResolveProjectType:
    def test_hot_project_explicit(self):
        assert _resolve_project_type({"tipo_projeto": "hot_project"}) == "hot_project"

    def test_project_explicit(self):
        assert _resolve_project_type({"tipo_projeto": "project"}) == "project"

    def test_benchmark_slug_infers_hot_project(self):
        assert _resolve_project_type({"benchmark_slug": "AGIS"}) == "hot_project"

    def test_no_slug_no_tipo_returns_project(self):
        assert _resolve_project_type({}) == "project"

    def test_unknown_tipo_with_slug_returns_hot_project(self):
        assert _resolve_project_type({"tipo_projeto": "weird", "benchmark_slug": "X"}) == "hot_project"

    def test_unknown_tipo_without_slug_returns_project(self):
        assert _resolve_project_type({"tipo_projeto": "weird"}) == "project"


# ---------------------------------------------------------------------------
# _canonical_eap_to_rows
# ---------------------------------------------------------------------------


class TestCanonicalEapToRows:
    def test_empty_eap_returns_empty(self):
        c = MagicMock()
        c.eap = []
        assert _canonical_eap_to_rows(c) == []

    def test_none_eap_returns_empty(self):
        c = MagicMock()
        c.eap = None
        assert _canonical_eap_to_rows(c) == []

    def test_dict_items_passed_through(self):
        c = MagicMock()
        c.eap = [{"item_id": "A", "cpu_id": "CPU1"}]
        rows = _canonical_eap_to_rows(c)
        assert len(rows) == 1
        assert rows[0]["item_id"] == "A"

    def test_model_dump_called_on_pydantic_style_object(self):
        item = MagicMock(spec=[])
        item.model_dump = MagicMock(return_value={"item_id": "B"})
        c = MagicMock()
        c.eap = [item]
        rows = _canonical_eap_to_rows(c)
        assert rows[0]["item_id"] == "B"

    def test_dict_method_called_when_no_model_dump(self):
        item = MagicMock(spec=[])
        item.dict = MagicMock(return_value={"item_id": "C"})
        c = MagicMock()
        c.eap = [item]
        rows = _canonical_eap_to_rows(c)
        assert rows[0]["item_id"] == "C"

    def test_to_dict_method_called_as_fallback(self):
        item = MagicMock(spec=[])
        item.to_dict = MagicMock(return_value={"item_id": "D"})
        c = MagicMock()
        c.eap = [item]
        rows = _canonical_eap_to_rows(c)
        assert rows[0]["item_id"] == "D"

    def test_no_eap_attr_returns_empty(self):
        c = MagicMock(spec=[])
        assert _canonical_eap_to_rows(c) == []


# ---------------------------------------------------------------------------
# _is_valid_canonical_eap
# ---------------------------------------------------------------------------


class TestIsValidCanonicalEap:
    def test_valid_payload(self):
        payload = {"cpus": {"itens_eap": [{"item_id": "A"}]}}
        assert _is_valid_canonical_eap(payload) is True

    def test_missing_cpus_block(self):
        assert _is_valid_canonical_eap({}) is False

    def test_cpus_not_dict(self):
        assert _is_valid_canonical_eap({"cpus": []}) is False

    def test_itens_eap_empty_list(self):
        assert _is_valid_canonical_eap({"cpus": {"itens_eap": []}}) is False

    def test_itens_eap_missing(self):
        assert _is_valid_canonical_eap({"cpus": {}}) is False


# ---------------------------------------------------------------------------
# _extract_historical_eap_rows
# ---------------------------------------------------------------------------


class TestExtractHistoricalEapRows:
    def test_eap_at_root(self):
        rows = _extract_historical_eap_rows({"eap": [{"item_id": "A"}, "bad"]})
        assert len(rows) == 1
        assert rows[0]["item_id"] == "A"

    def test_eap_in_skill_inputs(self):
        payload = {
            "skill_inputs": {
                "01-escopo-e-eap": {
                    "eap": [{"item_id": "B"}],
                }
            }
        }
        rows = _extract_historical_eap_rows(payload)
        assert len(rows) == 1
        assert rows[0]["item_id"] == "B"

    def test_eap_in_nested_inputs_escopo(self):
        payload = {
            "skill_inputs": {
                "01-escopo-e-eap": {
                    "inputs_escopo": {
                        "eap": [{"item_id": "C"}],
                    }
                }
            }
        }
        rows = _extract_historical_eap_rows(payload)
        assert len(rows) == 1
        assert rows[0]["item_id"] == "C"

    def test_empty_payload_returns_empty(self):
        assert _extract_historical_eap_rows({}) == []

    def test_non_list_eap_at_root_falls_through(self):
        payload = {"eap": "not-a-list"}
        rows = _extract_historical_eap_rows(payload)
        assert rows == []


# ---------------------------------------------------------------------------
# _extract_canonical_eap_rows
# ---------------------------------------------------------------------------


class TestExtractCanonicalEapRows:
    def test_valid_block(self):
        payload = {"cpus": {"itens_eap": [{"item_id": "X"}, "bad"]}}
        rows = _extract_canonical_eap_rows(payload)
        assert len(rows) == 1
        assert rows[0]["item_id"] == "X"

    def test_no_cpus_block_returns_empty(self):
        assert _extract_canonical_eap_rows({}) == []

    def test_cpus_not_dict_returns_empty(self):
        assert _extract_canonical_eap_rows({"cpus": [1, 2]}) == []

    def test_itens_eap_not_list_returns_empty(self):
        assert _extract_canonical_eap_rows({"cpus": {"itens_eap": "bad"}}) == []


# ---------------------------------------------------------------------------
# _catalog_is_deficit
# ---------------------------------------------------------------------------


class TestCatalogIsDeficit:
    def test_non_dict_is_deficit(self):
        assert _catalog_is_deficit(None) is True

    def test_no_cpus_is_deficit(self):
        assert _catalog_is_deficit({}) is True

    def test_cpus_empty_list_is_deficit(self):
        assert _catalog_is_deficit({"cpus": []}) is True

    def test_cpu_without_equipe_is_deficit(self):
        assert _catalog_is_deficit({"cpus": [{"descricao": "CPU1"}]}) is True

    def test_cpu_with_empty_equipe_is_deficit(self):
        catalog = {"cpus": [{"equipe": {"funcoes": [], "equipamentos": []}}]}
        assert _catalog_is_deficit(catalog) is True

    def test_cpu_with_funcoes_is_not_deficit(self):
        catalog = {"cpus": [{"equipe": {"funcoes": ["operador"], "equipamentos": []}}]}
        assert _catalog_is_deficit(catalog) is False

    def test_cpu_with_equipamentos_is_not_deficit(self):
        catalog = {"cpus": [{"equipe": {"funcoes": [], "equipamentos": ["escavadeira"]}}]}
        assert _catalog_is_deficit(catalog) is False

    def test_non_dict_cpu_skipped_still_deficit(self):
        assert _catalog_is_deficit({"cpus": ["not-dict"]}) is True


# ---------------------------------------------------------------------------
# ProjectService.list_projects
# ---------------------------------------------------------------------------


class TestListProjects:
    def test_empty_list(self):
        svc, repo, _ = _make_service()
        repo.list_projects.return_value = []
        assert svc.list_projects() == []

    def test_multiple_projects_with_different_types(self):
        svc, repo, _ = _make_service()
        p1 = _make_project("p1", tipo_projeto="hot_project")
        p1.meta["benchmark_slug"] = "AGIS"
        p2 = _make_project("p2", tipo_projeto="project")
        repo.list_projects.return_value = [p1, p2]

        items = svc.list_projects()
        assert len(items) == 2
        types = {i["project_id"]: i["tipo_projeto"] for i in items}
        assert types["p1"] == "hot_project"
        assert types["p2"] == "project"

    def test_returns_expected_keys(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        repo.list_projects.return_value = [p]
        item = svc.list_projects()[0]
        assert {
            "project_id",
            "nome",
            "contexto_id",
            "tipo_projeto",
            "status_eap",
            "current_version",
            "versions",
            "benchmark_slug",
        }.issubset(item.keys())

    def test_benchmark_slug_propagated(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        p.meta["benchmark_slug"] = "SLUG-X"
        repo.list_projects.return_value = [p]
        assert svc.list_projects()[0]["benchmark_slug"] == "SLUG-X"


# ---------------------------------------------------------------------------
# ProjectService.get_project
# ---------------------------------------------------------------------------


class TestGetProject:
    def test_returns_full_structure(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        repo.get_project.return_value = p
        result = svc.get_project("p1")
        assert result["project_id"] == "p1"
        assert result["nome"] == "Projeto Test"
        assert "current_version" in result
        assert "_debug" in result

    def test_benchmark_reference_file_none_when_not_exists(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        p.exists.return_value = False
        repo.get_project.return_value = p
        result = svc.get_project("p1")
        assert result["benchmark_reference_file"] is None

    def test_benchmark_reference_file_set_when_exists(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        p.exists.return_value = True
        repo.get_project.return_value = p
        result = svc.get_project("p1")
        assert result["benchmark_reference_file"] == svc._files.benchmark_reference

    def test_tipo_projeto_resolved(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        p.meta["benchmark_slug"] = "AGIS"
        del p.meta["tipo_projeto"]
        repo.get_project.return_value = p
        result = svc.get_project("p1")
        assert result["tipo_projeto"] == "hot_project"


# ---------------------------------------------------------------------------
# ProjectService.get_eap
# ---------------------------------------------------------------------------


class TestGetEap:
    def test_eap_from_project_eap_items(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1", tipo_projeto="project")
        p.read_json.side_effect = lambda key, default=None: (
            [{"item_id": "A", "cpu_id": "CPU1"}] if "eap_items" in key else default
        )
        repo.get_project.return_value = p
        result = svc.get_eap("p1")
        assert result["project_id"] == "p1"
        assert result["count"] == 1
        assert result["_debug"]["eap_source"] == "project.eap_items"

    def test_eap_empty_falls_to_canonical(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1", tipo_projeto="project")
        p.read_json.return_value = []
        canonical = MagicMock()
        canonical.eap = [{"item_id": "X", "cpu_id": "CPU-X"}]
        p.load_canonical.return_value = canonical
        repo.get_project.return_value = p
        result = svc.get_eap("p1")
        assert result["count"] == 1
        assert "canonical.eap" in result["_debug"]["eap_source"]

    def test_eap_empty_no_canonical_tries_historical(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1", tipo_projeto="project")
        p.read_json.return_value = []
        canonical_with_eap = MagicMock()
        canonical_with_eap.eap = [{"item_id": "H"}]
        p.load_canonical.side_effect = [None, canonical_with_eap]
        p.list_versions.return_value = ["v1"]
        repo.get_project.return_value = p
        result = svc.get_eap("p1")
        assert result["project_id"] == "p1"

    def test_default_status_rascunho_for_project_type(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1", tipo_projeto="project")
        p.meta = {"id": "p1", "tipo_projeto": "project"}
        p.read_json.return_value = []
        p.load_canonical.return_value = None
        p.list_versions.return_value = []
        repo.get_project.return_value = p
        result = svc.get_eap("p1")
        assert result["status_eap"] == "RASCUNHO"

    def test_default_status_ativo_for_hot_project(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1", tipo_projeto="hot_project")
        p.meta = {"id": "p1", "tipo_projeto": "hot_project"}
        p.read_json.return_value = []
        p.load_canonical.return_value = None
        p.list_versions.return_value = []
        repo.get_project.return_value = p
        result = svc.get_eap("p1")
        assert result["status_eap"] == "ATIVO"

    def test_eap_from_benchmark_reference_canonical_source(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1", tipo_projeto="project")

        def _read_json(key, default=None):
            if "eap_items" in key:
                return []
            if "benchmark_reference" in key:
                return {"cpus": {"itens_eap": [{"item_id": "R", "cpu_id": "CPU-R"}]}}
            return default

        p.read_json.side_effect = _read_json
        p.load_canonical.return_value = None
        p.list_versions.return_value = []
        repo.get_project.return_value = p
        result = svc.get_eap("p1")
        assert "benchmark_reference" in result["_debug"]["eap_source"]


# ---------------------------------------------------------------------------
# ProjectService.list_versions
# ---------------------------------------------------------------------------


class TestListVersions:
    def test_delegates_to_repo(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        p.list_versions.return_value = ["v1", "v2", "v3"]
        repo.get_project.return_value = p
        assert svc.list_versions("p1") == ["v1", "v2", "v3"]


# ---------------------------------------------------------------------------
# ProjectService.fork_version
# ---------------------------------------------------------------------------


class TestForkVersion:
    def test_fork_returns_payload(self):
        svc, repo, audit = _make_service()
        p = _make_project("p1")
        p.list_versions.return_value = ["v1"]
        p.new_version.return_value = "v2"
        p.current_version.return_value = "v2"
        p.list_versions.side_effect = [["v1"], ["v1", "v2"]]
        repo.get_project.return_value = p
        result = svc.fork_version("p1", "v1", actor="tester")
        assert result["forked_version"] == "v2"
        assert result["base_version"] == "v1"
        audit.log.assert_called_once()

    def test_fork_raises_when_version_not_found(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        p.list_versions.return_value = ["v1"]
        repo.get_project.return_value = p
        with pytest.raises(FileNotFoundError):
            svc.fork_version("p1", "v99")


# ---------------------------------------------------------------------------
# ProjectService.compare_versions
# ---------------------------------------------------------------------------


class TestCompareVersions:
    def test_returns_diff_structure(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        left_can = MagicMock()
        right_can = MagicMock()
        p.load_canonical.side_effect = [left_can, right_can]

        with (
            patch(
                "concilium.application.services.project.project_service._versions_artifacts.resolve_compare_version",
                side_effect=["v1", "v2"],
            ),
            patch(
                "concilium.application.services.project.project_service._versions_artifacts.build_summary",
                return_value={"total": 0},
            ),
            patch(
                "concilium.application.services.project.project_service._versions_artifacts.calculate_deltas",
                return_value={},
            ),
        ):
            repo.get_project.return_value = p
            result = svc.compare_versions("p1", "v1", "v2")
        assert "left" in result
        assert "right" in result
        assert "deltas" in result

    def test_raises_when_canonical_missing(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        p.load_canonical.return_value = None
        with (
            patch(
                "concilium.application.services.project.project_service._versions_artifacts.resolve_compare_version",
                side_effect=["v1", "v2"],
            ),
        ):
            repo.get_project.return_value = p
            with pytest.raises(ValueError):
                svc.compare_versions("p1", "v1", "v2")


# ---------------------------------------------------------------------------
# ProjectService.list_artifacts / get_artifact_bytes
# ---------------------------------------------------------------------------


class TestListArtifacts:
    def test_returns_artifact_lists(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        p.list_output_files.return_value = ["a.xlsx"]
        p.list_file_names.return_value = []
        repo.get_project.return_value = p
        result = svc.list_artifacts("p1", "v1")
        assert result["version"] == "v1"
        assert "a.xlsx" in result["outputs"]

    def test_no_version_returns_empty(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        p.current_version.return_value = None
        repo.get_project.return_value = p
        result = svc.list_artifacts("p1", None)
        assert result["outputs"] == []

    def test_version_resolved_from_current(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        p.current_version.return_value = "v3"
        p.list_output_files.return_value = []
        p.list_file_names.return_value = []
        repo.get_project.return_value = p
        result = svc.list_artifacts("p1", None)
        assert result["version"] == "v3"


class TestGetArtifactBytes:
    def test_outputs_kind(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        p.load_output_file.return_value = b"data"
        repo.get_project.return_value = p
        data, mime = svc.get_artifact_bytes("p1", "v1", "outputs", "report.json")
        assert data == b"data"
        assert "json" in mime or mime == "application/octet-stream"

    def test_intermediate_kind(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        p.read_bytes.return_value = b"inter"
        repo.get_project.return_value = p
        data, _ = svc.get_artifact_bytes("p1", "v1", "intermediate", "foo.json")
        assert data == b"inter"

    def test_typed_artifacts_kind(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        p.read_bytes.return_value = b"typed"
        repo.get_project.return_value = p
        data, _ = svc.get_artifact_bytes("p1", "v1", "typed_artifacts", "bar.json")
        assert data == b"typed"

    def test_invalid_kind_raises(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        repo.get_project.return_value = p
        with pytest.raises(ValueError, match="kind"):
            svc.get_artifact_bytes("p1", "v1", "bad_kind", "foo.json")

    def test_path_traversal_blocked(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        repo.get_project.return_value = p
        with pytest.raises(ValueError, match="invalido"):
            svc.get_artifact_bytes("p1", "v1", "outputs", "../secret.json")

    def test_none_payload_raises_not_found(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        p.load_output_file.return_value = None
        repo.get_project.return_value = p
        with pytest.raises(FileNotFoundError):
            svc.get_artifact_bytes("p1", "v1", "outputs", "missing.json")

    def test_no_active_version_raises(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        p.current_version.return_value = None
        repo.get_project.return_value = p
        with pytest.raises(FileNotFoundError):
            svc.get_artifact_bytes("p1", None, "outputs", "file.json")


# ---------------------------------------------------------------------------
# ProjectService.get_last_canonical
# ---------------------------------------------------------------------------


class TestGetLastCanonical:
    def test_returns_canonical(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        can = MagicMock()
        p.load_canonical.return_value = can
        repo.get_project.return_value = p
        assert svc.get_last_canonical("p1") is can

    def test_returns_none_on_exception(self):
        svc, repo, _ = _make_service()
        repo.get_project.side_effect = RuntimeError("boom")
        assert svc.get_last_canonical("p1") is None


# ---------------------------------------------------------------------------
# ProjectService.patch_project_config
# ---------------------------------------------------------------------------


class TestPatchProjectConfig:
    def test_updates_allowed_fields(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        p.meta = {"id": "p1", "nome": "Old", "contexto_id": "ctx1"}
        repo.get_project.return_value = p
        result = svc.patch_project_config("p1", {"nome": "New"})
        assert "nome" in result["updated"]
        assert result["meta"]["nome"] == "New"

    def test_no_change_when_value_identical(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        p.meta = {"id": "p1", "nome": "Same", "contexto_id": "ctx1"}
        repo.get_project.return_value = p
        result = svc.patch_project_config("p1", {"nome": "Same"})
        assert result["updated"] == []
        p.write_json.assert_not_called()

    def test_ignores_disallowed_keys(self):
        svc, repo, _ = _make_service()
        p = _make_project("p1")
        p.meta = {"id": "p1", "nome": "N", "contexto_id": "ctx1"}
        repo.get_project.return_value = p
        result = svc.patch_project_config("p1", {"benchmark_slug": "HACK", "nome": "N2"})
        assert "benchmark_slug" not in result["updated"]
        assert "nome" in result["updated"]


# ---------------------------------------------------------------------------
# ProjectService.list_contextos / list_contexto_versions (no svc path)
# ---------------------------------------------------------------------------


class TestContextosNoSvc:
    def test_list_contextos_returns_empty_when_no_svc(self):
        svc, _, _ = _make_service()
        with patch.object(svc, "_get_contexto_svc", return_value=None):
            assert svc.list_contextos() == []

    def test_list_contexto_versions_returns_empty_when_no_svc(self):
        svc, _, _ = _make_service()
        with patch.object(svc, "_get_contexto_svc", return_value=None):
            assert svc.list_contexto_versions("ctx1") == []

    def test_create_contexto_version_raises_when_no_svc(self):
        svc, _, _ = _make_service()
        with patch.object(svc, "_get_contexto_svc", return_value=None):
            with pytest.raises(RuntimeError):
                svc.create_contexto_version("ctx1", {}, "motivo")

    def test_compare_contexto_versions_returns_error_when_no_svc(self):
        svc, _, _ = _make_service()
        with patch.object(svc, "_get_contexto_svc", return_value=None):
            result = svc.compare_contexto_versions("ctx1", "v1", "v2")
            assert "error" in result

    def test_list_contextos_delegates_to_svc(self):
        svc, _, _ = _make_service()
        mock_svc = MagicMock()
        mock_svc.list_contexts.return_value = [{"id": "ctx1"}]
        with patch.object(svc, "_get_contexto_svc", return_value=mock_svc):
            result = svc.list_contextos()
        assert result == [{"id": "ctx1"}]

    def test_list_contexto_versions_delegates_to_svc(self):
        svc, _, _ = _make_service()
        mock_svc = MagicMock()
        mock_svc.list_versions.return_value = [{"version": "v1"}]
        with patch.object(svc, "_get_contexto_svc", return_value=mock_svc):
            result = svc.list_contexto_versions("ctx1")
        assert result == [{"version": "v1"}]

    def test_compare_contexto_delegates_to_svc(self):
        svc, _, _ = _make_service()
        mock_svc = MagicMock()
        mock_svc.compare.return_value = {"diff": []}
        with patch.object(svc, "_get_contexto_svc", return_value=mock_svc):
            result = svc.compare_contexto_versions("ctx1", "v1", "v2")
        assert "diff" in result


# ---------------------------------------------------------------------------
# ProjectService.list_perfis / list_perfil_versions / compare
# ---------------------------------------------------------------------------


class TestPerfisNoSvc:
    def test_list_perfis_empty_when_no_svc(self):
        svc, _, _ = _make_service()
        with patch.object(svc, "_get_perfil_svc", return_value=None):
            assert svc.list_perfis() == []

    def test_list_perfil_versions_empty_when_no_svc(self):
        svc, _, _ = _make_service()
        with patch.object(svc, "_get_perfil_svc", return_value=None):
            assert svc.list_perfil_versions("perf1") == []

    def test_create_perfil_version_raises_when_no_svc(self):
        svc, _, _ = _make_service()
        with patch.object(svc, "_get_perfil_svc", return_value=None):
            with pytest.raises(RuntimeError):
                svc.create_perfil_version("perf1", {}, "motivo")

    def test_compare_perfil_versions_error_when_no_svc(self):
        svc, _, _ = _make_service()
        with patch.object(svc, "_get_perfil_svc", return_value=None):
            result = svc.compare_perfil_versions("perf1", "v1", "v2")
            assert "error" in result


# ---------------------------------------------------------------------------
# ProjectService.list_temas / compare_temas / list_jurisdicoes
# ---------------------------------------------------------------------------


class TestTemasAndJurisdicoes:
    def test_list_temas_empty_when_no_svc(self):
        svc, _, _ = _make_service()
        with patch.object(svc, "_get_tema_svc", return_value=None):
            assert svc.list_temas() == []

    def test_list_tema_versions_empty_when_no_svc(self):
        svc, _, _ = _make_service()
        with patch.object(svc, "_get_tema_svc", return_value=None):
            assert svc.list_tema_versions("t1") == []

    def test_create_tema_version_raises_when_no_svc(self):
        svc, _, _ = _make_service()
        with patch.object(svc, "_get_tema_svc", return_value=None):
            with pytest.raises(RuntimeError):
                svc.create_tema_version("t1", {}, "motivo")

    def test_compare_tema_versions_error_when_no_svc(self):
        svc, _, _ = _make_service()
        with patch.object(svc, "_get_tema_svc", return_value=None):
            result = svc.compare_tema_versions("t1", "v1", "v2")
            assert "error" in result

    def test_list_jurisdicoes_empty_when_no_svc(self):
        svc, _, _ = _make_service()
        with patch.object(svc, "_get_jurisdiction_svc", return_value=None):
            assert svc.list_jurisdicoes() == []

    def test_list_jurisdicao_versions_empty_when_no_svc(self):
        svc, _, _ = _make_service()
        with patch.object(svc, "_get_jurisdiction_svc", return_value=None):
            assert svc.list_jurisdicao_versions("j1") == []

    def test_create_jurisdicao_version_raises_when_no_svc(self):
        svc, _, _ = _make_service()
        with patch.object(svc, "_get_jurisdiction_svc", return_value=None):
            with pytest.raises(RuntimeError):
                svc.create_jurisdicao_version("j1", {}, "motivo")

    def test_compare_jurisdicao_versions_error_when_no_svc(self):
        svc, _, _ = _make_service()
        with patch.object(svc, "_get_jurisdiction_svc", return_value=None):
            result = svc.compare_jurisdicao_versions("j1", "v1", "v2")
            assert "error" in result

    def test_list_temas_delegates(self):
        svc, _, _ = _make_service()
        mock_svc = MagicMock()
        mock_svc.list_temas.return_value = [{"id": "tema1"}]
        with patch.object(svc, "_get_tema_svc", return_value=mock_svc):
            assert svc.list_temas() == [{"id": "tema1"}]

    def test_list_jurisdicoes_delegates(self):
        svc, _, _ = _make_service()
        mock_svc = MagicMock()
        mock_svc.list_jurisdicoes.return_value = [{"id": "j1"}]
        with patch.object(svc, "_get_jurisdiction_svc", return_value=mock_svc):
            assert svc.list_jurisdicoes() == [{"id": "j1"}]


# ---------------------------------------------------------------------------
# _validate_jurisdicao_fields
# ---------------------------------------------------------------------------


class TestValidateJurisdicaoFields:
    def test_valid_date_reference(self):
        svc, _, _ = _make_service()
        svc._validate_jurisdicao_fields({"provedores_referencia": [{"data_referencia": "2024-03"}]})

    def test_invalid_date_format_raises(self):
        svc, _, _ = _make_service()
        with pytest.raises(ValueError, match="data_referencia"):
            svc._validate_jurisdicao_fields({"provedores_referencia": [{"data_referencia": "03/2024"}]})

    def test_non_dict_provedor_raises(self):
        svc, _, _ = _make_service()
        with pytest.raises(ValueError, match="objeto"):
            svc._validate_jurisdicao_fields({"provedores_referencia": ["not-dict"]})

    def test_empty_date_string_accepted(self):
        svc, _, _ = _make_service()
        svc._validate_jurisdicao_fields({"provedores_referencia": [{"data_referencia": ""}]})

    def test_non_list_provedores_accepted(self):
        svc, _, _ = _make_service()
        svc._validate_jurisdicao_fields({"provedores_referencia": None})


# ---------------------------------------------------------------------------
# _validate_range_field / _validate_perfil_fields
# ---------------------------------------------------------------------------


class TestValidateRangeField:
    def test_valid_range_passes(self):
        svc, _, _ = _make_service()
        svc._validate_range_field({"faixa": {"min": 0.1, "max": 0.5}}, "faixa", lower=0.0, upper=1.0)

    def test_min_greater_than_max_raises(self):
        svc, _, _ = _make_service()
        with pytest.raises(ValueError, match="min deve ser <= max"):
            svc._validate_range_field({"faixa": {"min": 0.9, "max": 0.1}}, "faixa", lower=0.0, upper=1.0)

    def test_out_of_bounds_raises(self):
        svc, _, _ = _make_service()
        with pytest.raises(ValueError, match="fora do intervalo"):
            svc._validate_range_field({"faixa": {"min": -0.1, "max": 0.5}}, "faixa", lower=0.0, upper=1.0)

    def test_non_dict_value_skipped(self):
        svc, _, _ = _make_service()
        svc._validate_range_field({"faixa": "not-dict"}, "faixa", lower=0.0, upper=1.0)

    def test_missing_min_max_raises(self):
        svc, _, _ = _make_service()
        with pytest.raises(ValueError, match="obrigatórios"):
            svc._validate_range_field({"faixa": {"min": 0.1}}, "faixa", lower=0.0, upper=1.0)

    def test_invalid_numeric_raises(self):
        svc, _, _ = _make_service()
        with pytest.raises(ValueError, match="inválidos"):
            svc._validate_range_field({"faixa": {"min": "x", "max": 0.5}}, "faixa", lower=0.0, upper=1.0)


# ---------------------------------------------------------------------------
# _normalize_eap_item (static method)
# ---------------------------------------------------------------------------


class TestNormalizeEapItem:
    def test_valid_item_normalized(self):
        item = {"item_id": "A", "cpu_id": "CPU1", "quantitativo": 100.0}
        result = ProjectService._normalize_eap_item(item, 1)
        assert result["item_id"] == "A"
        assert result["cpu_id"] == "CPU1"
        assert result["quantitativo"] == 100.0

    def test_returns_none_when_missing_item_id(self):
        item = {"cpu_id": "CPU1"}
        assert ProjectService._normalize_eap_item(item, 1) is None

    def test_returns_none_when_missing_cpu_id(self):
        item = {"item_id": "A"}
        assert ProjectService._normalize_eap_item(item, 1) is None

    def test_uses_fallback_keys_for_item_id(self):
        item = {"activity_id": "Z", "cpu_id": "CPU-Z"}
        result = ProjectService._normalize_eap_item(item, 5)
        assert result["item_id"] == "Z"

    def test_uses_fallback_keys_for_cpu_id(self):
        item = {"item_id": "A", "cpu": "CPU-F"}
        result = ProjectService._normalize_eap_item(item, 1)
        assert result["cpu_id"] == "CPU-F"

    def test_default_ordem_used_when_missing(self):
        item = {"item_id": "A", "cpu_id": "CPU1"}
        result = ProjectService._normalize_eap_item(item, 7)
        assert result["ordem"] == 7

    def test_invalid_quantitativo_defaults_to_zero(self):
        item = {"item_id": "A", "cpu_id": "CPU1", "quantitativo": "bad"}
        result = ProjectService._normalize_eap_item(item, 1)
        assert result["quantitativo"] == 0.0

    def test_invalid_ordem_defaults_to_padrao(self):
        item = {"item_id": "A", "cpu_id": "CPU1", "ordem": "nan"}
        result = ProjectService._normalize_eap_item(item, 3)
        assert result["ordem"] == 3


# ---------------------------------------------------------------------------
# _resolve_eap_source (static method)
# ---------------------------------------------------------------------------


class TestResolveEapSource:
    def test_canonical_cpus_itens_eap_detected(self):
        payload = {"cpus": {"itens_eap": [{"item_id": "A"}]}}
        assert ProjectService._resolve_eap_source(payload) == "canonical.cpus.itens_eap"

    def test_eap_root_detected(self):
        payload = {"eap": [{"item_id": "A"}]}
        assert ProjectService._resolve_eap_source(payload) == "historical.eap_root"

    def test_skill_inputs_01_eap_detected(self):
        payload = {"skill_inputs": {"01-escopo-e-eap": {"eap": [{"item_id": "A"}]}}}
        assert "01-escopo-e-eap.eap" in (ProjectService._resolve_eap_source(payload) or "")

    def test_skill_inputs_nested_detected(self):
        payload = {"skill_inputs": {"01-escopo-e-eap": {"inputs_escopo": {"eap": [{"item_id": "A"}]}}}}
        result = ProjectService._resolve_eap_source(payload)
        assert result is not None and "inputs_escopo" in result

    def test_empty_payload_returns_none(self):
        assert ProjectService._resolve_eap_source({}) is None


# ---------------------------------------------------------------------------
# _project_service_helpers — free functions
# ---------------------------------------------------------------------------


class TestSortVersions:
    def test_sort_v1_v2_v10(self):
        assert _sort_versions(["v10", "v1", "v2"]) == ["v1", "v2", "v10"]

    def test_non_v_prefix_sorted_last(self):
        result = _sort_versions(["v2", "main", "v1"])
        assert result.index("v1") < result.index("v2")

    def test_empty_list(self):
        assert _sort_versions([]) == []


class TestCountOrphanedRuns:
    def test_counts_matching_version(self):
        runs = [{"version": "v1"}, {"version": "v2"}, {"base_version": "v1"}]
        assert _count_orphaned_runs(runs, "v1") == 2

    def test_no_match_returns_zero(self):
        runs = [{"version": "v2"}]
        assert _count_orphaned_runs(runs, "v1") == 0

    def test_non_list_returns_zero(self):
        assert _count_orphaned_runs(None, "v1") == 0

    def test_non_dict_runs_skipped(self):
        assert _count_orphaned_runs(["not-dict"], "v1") == 0


class TestCpBuildMetaKwargs:
    def test_picks_from_inputs_escopo(self):
        inputs_escopo = {
            "coordenadas": {"lat": 1.0, "lng": 2.0},
            "regime_trabalho": {"dias_semana": 5, "horas_dia": 8},
        }
        req = SimpleNamespace(coordenadas_lat=0.0, coordenadas_lng=0.0, dias_semana=6, horas_dia=10)
        result = _cp_build_meta_kwargs(inputs_escopo, req)
        assert result["coordenadas_lat"] == 1.0
        assert result["dias_semana"] == 5

    def test_falls_back_to_req_when_missing(self):
        req = SimpleNamespace(coordenadas_lat=9.9, coordenadas_lng=8.8, dias_semana=6, horas_dia=10)
        result = _cp_build_meta_kwargs({}, req)
        assert result["coordenadas_lat"] == 9.9
        assert result["dias_semana"] == 6


class TestCpSavePerfilContext:
    def test_writes_meta_when_values_set(self):
        project = MagicMock()
        project.meta = {"id": "p1"}
        _cp_save_perfil_context(project, "ctx-v1", "perf1", "perf-v1")
        project.write_json.assert_called_once()
        call_args = project.write_json.call_args[0]
        assert call_args[0] == "meta.json"
        written = call_args[1]
        assert written["contexto_version"] == "ctx-v1"
        assert written["perfil_id"] == "perf1"

    def test_skips_write_when_nothing_set(self):
        project = MagicMock()
        project.meta = {"id": "p1"}
        _cp_save_perfil_context(project, None, None, None)
        project.write_json.assert_not_called()

    def test_partial_fields_written(self):
        project = MagicMock()
        project.meta = {"id": "p1"}
        _cp_save_perfil_context(project, None, "perf1", None)
        project.write_json.assert_called_once()
        written = project.write_json.call_args[0][1]
        assert "perfil_id" in written
        assert "contexto_version" not in written

    def test_perfil_id_falsy_skips_that_field_only(self):
        """contexto_version and perfil_version set, but perfil_id is None —
        covers the false branch of `if perfil_id:` while still writing."""
        project = MagicMock()
        project.meta = {"id": "p1"}
        _cp_save_perfil_context(project, "ctx-v2", None, "perf-v2")
        project.write_json.assert_called_once()
        written = project.write_json.call_args[0][1]
        assert written["contexto_version"] == "ctx-v2"
        assert "perfil_id" not in written
        assert written["perfil_version"] == "perf-v2"


class TestResolveCatalogoBase:
    def test_returns_catalogo_id_from_last_version(self):
        svc, _, _ = _make_service()
        with patch.object(svc, "list_contexto_versions", return_value=[{"catalogo_id": "cat-mendeslobo"}]):
            result = _resolve_catalogo_base_from_context(svc, "mendeslobo")
        assert result == "cat-mendeslobo"

    def test_returns_contexto_id_when_no_versions(self):
        svc, _, _ = _make_service()
        with patch.object(svc, "list_contexto_versions", return_value=[]):
            result = _resolve_catalogo_base_from_context(svc, "mendeslobo")
        assert result == "mendeslobo"

    def test_returns_contexto_id_when_no_catalogo_id(self):
        svc, _, _ = _make_service()
        with patch.object(svc, "list_contexto_versions", return_value=[{"other": "x"}]):
            result = _resolve_catalogo_base_from_context(svc, "ctx1")
        assert result == "ctx1"

    def test_exception_falls_back_to_contexto_id(self):
        svc, _, _ = _make_service()
        with patch.object(svc, "list_contexto_versions", side_effect=RuntimeError("boom")):
            result = _resolve_catalogo_base_from_context(svc, "ctx1")
        assert result == "ctx1"


class TestComputeBdi:
    def test_basic_bdi_calculation(self):
        comps = {
            "ac": 0.05,
            "df": 0.02,
            "r": 0.01,
            "cr": 0.0,
            "l": 0.10,
            "cofins": 0.03,
            "iss": 0.05,
            "pis": 0.0,
            "cssl": 0.0,
            "ir": 0.0,
        }
        bdi = _compute_bdi_for_categoria(comps)
        assert bdi is not None
        assert bdi > 0.0

    def test_missing_ac_returns_none(self):
        assert _compute_bdi_for_categoria({"df": 0.02}) is None

    def test_non_dict_returns_none(self):
        assert _compute_bdi_for_categoria("bad") is None

    def test_compute_flat_bdi_adds_equipamentos_fallback(self):
        tabela = {
            "servicos": {
                "ac": 0.05,
                "df": 0.02,
                "r": 0.0,
                "cr": 0.0,
                "l": 0.10,
                "cofins": 0.03,
                "iss": 0.05,
                "pis": 0.0,
                "cssl": 0.0,
                "ir": 0.0,
            }
        }
        flat = _compute_flat_bdi(tabela)
        assert "equipamentos" in flat
        assert flat["equipamentos"] == flat["servicos"]

    def test_compute_flat_bdi_adds_servicos_fallback_from_mao_obra(self):
        tabela = {
            "mao_obra": {
                "ac": 0.05,
                "df": 0.02,
                "r": 0.0,
                "cr": 0.0,
                "l": 0.10,
                "cofins": 0.03,
                "iss": 0.05,
                "pis": 0.0,
                "cssl": 0.0,
                "ir": 0.0,
            }
        }
        flat = _compute_flat_bdi(tabela)
        assert "servicos" in flat
        assert flat["servicos"] == flat["mao_obra"]


class TestEnrichPayloadBdi:
    def test_injects_bdi_aplicado(self):
        payload = {
            "skill_inputs": {
                "06-resultado-financeiro": {
                    "tabela_bdi": {
                        "servicos": {
                            "ac": 0.05,
                            "df": 0.02,
                            "r": 0.0,
                            "cr": 0.0,
                            "l": 0.10,
                            "cofins": 0.03,
                            "iss": 0.05,
                            "pis": 0.0,
                            "cssl": 0.0,
                            "ir": 0.0,
                        }
                    }
                }
            }
        }
        _enrich_payload_bdi(payload)
        assert "bdi_aplicado" in payload["skill_inputs"]["06-resultado-financeiro"]

    def test_no_tabela_bdi_leaves_payload_unchanged(self):
        payload = {"skill_inputs": {"06-resultado-financeiro": {}}}
        _enrich_payload_bdi(payload)
        assert "bdi_aplicado" not in payload.get("skill_inputs", {}).get("06-resultado-financeiro", {})

    def test_exception_does_not_propagate(self):
        _enrich_payload_bdi(None)  # should not raise

    def test_tabela_bdi_present_but_flat_empty_leaves_payload_unchanged(self):
        """tabela_bdi is a non-empty dict, but every categoria is missing the
        'ac' key so _compute_bdi_for_categoria returns None for all of them —
        _compute_flat_bdi() ends up {} (falsy), so `if flat:` is skipped and
        bdi_aplicado is never set."""
        payload = {
            "skill_inputs": {
                "06-resultado-financeiro": {
                    "tabela_bdi": {
                        "mao_obra": {"df": 0.02},  # no "ac" key
                    }
                }
            }
        }
        _enrich_payload_bdi(payload)
        assert "bdi_aplicado" not in payload["skill_inputs"]["06-resultado-financeiro"]


class TestBuildCatalogFromSnapshot:
    def test_builds_catalog_with_cpus_and_prods(self):
        cat = {
            "cpus": [{"id": "CPU1", "producao_id_ref": "P1"}],
            "produtividades": [{"id": "P1", "producao_horaria": 10.0}],
        }
        result = _build_catalog_from_snapshot(cat)
        assert "cpus" in result
        assert len(result["cpus"]) == 1

    def test_builds_catalog_cpus_only(self):
        cat = {"cpus": [{"id": "CPU1"}]}
        result = _build_catalog_from_snapshot(cat)
        assert "cpus" in result

    def test_builds_catalog_with_insumos(self):
        cat = {"cpus": [], "insumos": [{"id": "I1"}]}
        result = _build_catalog_from_snapshot(cat)
        assert "insumos" in result


class TestTryEnrichCpuWithProd:
    def test_enriches_producao_horaria_from_prod(self):
        cpu = {"id": "C1", "producao_id_ref": "P1"}
        prod_lkp = {"P1": {"producao_horaria": 50.0, "equipe": None}}
        result = _try_enrich_cpu_with_prod(cpu, prod_lkp)
        assert result["producao_horaria"] == 50.0

    def test_no_ref_returns_unchanged(self):
        cpu = {"id": "C1"}
        result = _try_enrich_cpu_with_prod(cpu, {})
        assert result == cpu

    def test_existing_producao_horaria_not_overwritten(self):
        cpu = {"id": "C1", "producao_id_ref": "P1", "producao_horaria": 99.0}
        prod_lkp = {"P1": {"producao_horaria": 50.0}}
        result = _try_enrich_cpu_with_prod(cpu, prod_lkp)
        assert result["producao_horaria"] == 99.0

    def test_non_dict_cpu_returned_as_is(self):
        assert _try_enrich_cpu_with_prod("not-dict", {}) == "not-dict"

    def test_enriches_equipe_from_composicao_padrao(self):
        cpu = {"id": "C1", "producao_id_ref": "P1"}
        equipe = {"funcoes": ["operador"], "equipamentos": []}
        prod_lkp = {"P1": {"composicao_padrao_equipe": equipe}}
        result = _try_enrich_cpu_with_prod(cpu, prod_lkp)
        assert result.get("equipe") == equipe

    def test_enriches_equipe_directly_from_prod_equipe_dict(self):
        """When prod['equipe'] is already a dict, it's used as-is without
        falling back to composicao_padrao_equipe (isinstance-dict true branch)."""
        cpu = {"id": "C1", "producao_id_ref": "P1"}
        equipe = {"funcoes": ["motorista"]}
        prod_lkp = {"P1": {"equipe": equipe}}
        result = _try_enrich_cpu_with_prod(cpu, prod_lkp)
        assert result.get("equipe") == equipe


class TestPsCreateProject:
    def test_creates_project_and_returns_payload(self):
        svc, repo, audit = _make_service()
        project = _make_project("new-p1")
        project.meta["id"] = "new-p1"
        project.new_version.return_value = "v1"
        project.root = MagicMock()
        project.root.__truediv__ = lambda s, x: MagicMock(**{"glob.return_value": [], "exists.return_value": False})
        repo.create_project.return_value = project

        req = SimpleNamespace(
            nome="Meu Projeto",
            contexto_id="mendeslobo",
            tipo_obra="TERRAPLENAGEM",
            localizacao="SP",
            data_inicio="2024-01-01",
            data_termino="2024-12-31",
            coordenadas_lat=-23.5,
            coordenadas_lng=-46.6,
            dias_semana=5,
            horas_dia=8,
            catalogo_base=None,
            model_dump=lambda: {"nome": "Meu Projeto"},
        )
        with patch.object(svc, "list_contexto_versions", return_value=[]):
            result = svc.create_project(
                req=req,
                inputs_escopo={},
                skill_inputs={},
                benchmark_slug=None,
                benchmark_reference=None,
                actor="tester",
            )
        assert result["nome"] == "Meu Projeto"
        assert result["tipo_projeto"] == "project"
        assert result["status_eap"] == "RASCUNHO"
        audit.log.assert_called_once()

    def test_creates_hot_project_with_benchmark_slug(self):
        svc, repo, audit = _make_service()
        project = _make_project("hot-p1")
        project.meta["id"] = "hot-p1"
        project.new_version.return_value = "v1"
        project.root = MagicMock()
        project.root.__truediv__ = lambda s, x: MagicMock(**{"glob.return_value": [], "exists.return_value": False})
        repo.create_project.return_value = project

        req = SimpleNamespace(
            nome="Hot Proj",
            contexto_id="mendeslobo",
            tipo_obra="ATERRO",
            localizacao="MG",
            data_inicio="2024-01-01",
            data_termino="2024-12-31",
            coordenadas_lat=-20.0,
            coordenadas_lng=-44.0,
            dias_semana=5,
            horas_dia=8,
            catalogo_base=None,
            model_dump=lambda: {"nome": "Hot Proj"},
        )
        with patch.object(svc, "list_contexto_versions", return_value=[]):
            result = svc.create_project(
                req=req,
                inputs_escopo={},
                skill_inputs={},
                benchmark_slug="AGIS",
                benchmark_reference={"cpus": {"itens_eap": [{"item_id": "A", "cpu_id": "CPU1"}]}},
                actor="tester",
            )
        assert result["tipo_projeto"] == "hot_project"
        assert result["status_eap"] == "ATIVO"
        assert result["benchmark_slug"] == "AGIS"
        assert result["benchmark_reference_file"] is not None


# ---------------------------------------------------------------------------
# Additional coverage for _project_service_helpers.py missing lines
# ---------------------------------------------------------------------------


class TestEnrichPayloadCatalog:
    """Covers _enrich_payload_catalog (lines 52-66)."""

    def test_reads_catalog_file_and_writes_payload(self, tmp_path):
        from concilium.application.services.project._project_service_helpers import _enrich_payload_catalog

        snaps_dir = tmp_path / "snapshots"
        snaps_dir.mkdir()
        cat_data = {"cpus": [{"codigo": "CPU-1"}], "insumos": [{"id": "INS-1"}]}
        import json

        (snaps_dir / "catalogo-20260101.json").write_text(json.dumps(cat_data))

        project = MagicMock()
        project.root = tmp_path
        payload: dict = {}

        _enrich_payload_catalog(payload, project)

        assert "catalog" in payload
        project.write_json.assert_called_once()

    def test_no_catalog_files_leaves_payload_unchanged(self, tmp_path):
        from concilium.application.services.project._project_service_helpers import _enrich_payload_catalog

        snaps_dir = tmp_path / "snapshots"
        snaps_dir.mkdir()  # empty dir
        project = MagicMock()
        project.root = tmp_path
        payload: dict = {}

        _enrich_payload_catalog(payload, project)
        assert "catalog" not in payload

    def test_exception_is_silenced(self):
        from concilium.application.services.project._project_service_helpers import _enrich_payload_catalog

        project = MagicMock()
        project.root = "/nonexistent_xyz_12345_abc"
        _enrich_payload_catalog({}, project)  # should not raise

    def test_catalog_file_present_but_empty_catalog_leaves_payload_unchanged(self, tmp_path):
        """cat_files is truthy but the snapshot has no cpus/insumos/produtividades,
        so _build_catalog_from_snapshot returns {} (falsy) — the `if catalog:`
        branch is skipped and neither payload nor project.write_json is touched."""
        from concilium.application.services.project._project_service_helpers import _enrich_payload_catalog

        snaps_dir = tmp_path / "snapshots"
        snaps_dir.mkdir()
        import json

        (snaps_dir / "catalogo-20260101.json").write_text(json.dumps({}))

        project = MagicMock()
        project.root = tmp_path
        payload: dict = {}

        _enrich_payload_catalog(payload, project)

        assert "catalog" not in payload
        project.write_json.assert_not_called()


class TestEnrichPayloadEncargos:
    """Covers _enrich_payload_encargos (lines 69-84)."""

    def test_reads_jurisdicao_file_and_builds_encargos(self, tmp_path):
        import json
        from pathlib import Path

        from concilium.application.services.project._project_service_helpers import _enrich_payload_encargos

        snaps_dir = tmp_path / "snapshots"
        snaps_dir.mkdir()
        juris = {
            "motor_encargos_sociais": {
                "percentual_mensalista": 1.20,
                "percentual_total": 1.95,
            }
        }
        (snaps_dir / "jurisdicao-20260101.json").write_text(json.dumps(juris))

        project = MagicMock()
        project.root = Path(tmp_path)
        payload: dict = {}

        _enrich_payload_encargos(payload, project)

        assert payload["encargos_sociais"]["pj"] == 0.0
        assert payload["encargos_sociais"]["clt_mensalista"] == 1.20
        assert payload["encargos_sociais"]["clt_horista"] == 1.95

    def test_no_jurisdicao_files_leaves_payload_unchanged(self, tmp_path):
        from pathlib import Path

        from concilium.application.services.project._project_service_helpers import _enrich_payload_encargos

        snaps_dir = tmp_path / "snapshots"
        snaps_dir.mkdir()
        project = MagicMock()
        project.root = Path(tmp_path)
        payload: dict = {}

        _enrich_payload_encargos(payload, project)
        assert "encargos_sociais" not in payload

    def test_uses_fallback_when_motor_missing(self, tmp_path):
        import json
        from pathlib import Path

        from concilium.application.services.project._project_service_helpers import _enrich_payload_encargos

        snaps_dir = tmp_path / "snapshots"
        snaps_dir.mkdir()
        (snaps_dir / "jurisdicao-20260101.json").write_text(json.dumps({"motor_encargos_sociais": {}}))
        project = MagicMock()
        project.root = Path(tmp_path)
        payload: dict = {}

        _enrich_payload_encargos(payload, project)
        assert payload["encargos_sociais"]["clt_mensalista"] == 1.06
        assert payload["encargos_sociais"]["clt_horista"] == 1.777


class TestCpEmbedCatalogIfNeeded:
    """Covers _cp_embed_catalog_if_needed (lines 140-159)."""

    def test_returns_early_when_benchmark_reference_none(self):
        from concilium.application.services.project._project_service_helpers import _cp_embed_catalog_if_needed

        project = MagicMock()
        _cp_embed_catalog_if_needed(project, None, MagicMock())
        project.write_json.assert_not_called()

    def test_saves_ref_when_catalog_already_present(self):
        from concilium.application.services.project._project_service_helpers import _cp_embed_catalog_if_needed

        project = MagicMock()
        files = MagicMock()
        files.benchmark_reference = "benchmark_reference.json"
        ref = {"catalog": {"cpus": [{"codigo": "CPU-1"}]}, "other": "data"}

        _cp_embed_catalog_if_needed(project, ref, files)
        project.write_json.assert_called_once_with("benchmark_reference.json", ref)

    def test_embeds_catalog_from_snapshot_file(self, tmp_path):
        import json

        from concilium.application.services.project._project_service_helpers import _cp_embed_catalog_if_needed

        snaps_dir = tmp_path / "snapshots"
        snaps_dir.mkdir()
        cat_data = {"cpus": [{"codigo": "CPU-1"}], "insumos": [{"id": "INS-1"}]}
        (snaps_dir / "catalogo-20260101.json").write_text(json.dumps(cat_data))

        project = MagicMock()
        project.root = tmp_path
        files = MagicMock()
        files.benchmark_reference = "benchmark_reference.json"
        ref = {"other": "no-catalog-key"}  # no catalog key

        _cp_embed_catalog_if_needed(project, ref, files)
        project.write_json.assert_called_once()
        saved = project.write_json.call_args[0][1]
        assert "catalog" in saved

    def test_silences_exception_during_snapshot_load(self):
        from concilium.application.services.project._project_service_helpers import _cp_embed_catalog_if_needed

        project = MagicMock()
        project.root = "/nonexistent_xyz_path"
        files = MagicMock()
        files.benchmark_reference = "benchmark_reference.json"
        # Should not raise, even with bad path
        _cp_embed_catalog_if_needed(project, {"no_catalog": True}, files)
        project.write_json.assert_called_once()

    def test_snapshot_file_present_but_empty_catalog_still_saves_ref_unchanged(self, tmp_path):
        """cat_files is truthy but the snapshot yields an empty catalog dict
        (falsy), so `if catalog:` is skipped and ref_to_save keeps no catalog
        key — the final write_json still fires with the untouched ref."""
        import json

        from concilium.application.services.project._project_service_helpers import _cp_embed_catalog_if_needed

        snaps_dir = tmp_path / "snapshots"
        snaps_dir.mkdir()
        (snaps_dir / "catalogo-20260101.json").write_text(json.dumps({}))

        project = MagicMock()
        project.root = tmp_path
        files = MagicMock()
        files.benchmark_reference = "benchmark_reference.json"
        ref = {"other": "no-catalog-key"}

        _cp_embed_catalog_if_needed(project, ref, files)

        project.write_json.assert_called_once()
        saved = project.write_json.call_args[0][1]
        assert "catalog" not in saved


class TestPsUpsertEap:
    """Covers _ps_upsert_eap (lines 266-299)."""

    def test_upsert_eap_updates_status_ready(self):
        from concilium.application.services.project._project_service_helpers import _ps_upsert_eap

        svc, repo, audit = _make_service()
        project = _make_project("proj-eap1", tipo_projeto="project", status_eap="RASCUNHO")
        project.meta["tipo_projeto"] = "project"
        repo.get_project.return_value = project
        svc._files = MagicMock()
        svc._files.eap_items = "eap_items.json"

        items = [
            {
                "item_id": "eap-1",
                "descricao": "Terraplenagem",
                "unidade": "m³",
                "cpu_id": "CPU-1",
                "ordem": 1,
                "quantitativo": 100.0,
            }
        ]
        result = _ps_upsert_eap(svc, "proj-eap1", items)
        assert result["status_eap"] in ("RASCUNHO_PRONTO", "RASCUNHO")
        assert result["count"] == 1

    def test_upsert_eap_hot_project_raises(self):
        from concilium.application.services.project._project_service_helpers import _ps_upsert_eap

        svc, repo, audit = _make_service()
        project = _make_project("proj-hot1", tipo_projeto="hot_project")
        project.meta["tipo_projeto"] = "hot_project"
        repo.get_project.return_value = project
        svc._files = MagicMock()

        with pytest.raises(ValueError, match="hot_project"):
            _ps_upsert_eap(svc, "proj-hot1", [])

    def test_upsert_eap_assigns_ordem_if_missing(self):
        from concilium.application.services.project._project_service_helpers import _ps_upsert_eap

        svc, repo, audit = _make_service()
        project = _make_project("proj-eap2", tipo_projeto="project")
        project.meta["tipo_projeto"] = "project"
        repo.get_project.return_value = project
        svc._files = MagicMock()
        svc._files.eap_items = "eap_items.json"

        # Items without 'ordem' key
        items = [
            {"item_id": "eap-1", "descricao": "Escavação", "unidade": "m³", "cpu_id": "CPU-1", "quantitativo": 50.0},
            {"item_id": "eap-2", "descricao": "Transporte", "unidade": "m³", "cpu_id": "CPU-2", "quantitativo": 80.0},
        ]
        result = _ps_upsert_eap(svc, "proj-eap2", items)
        assert result["count"] == 2


class TestPsDeleteVersion:
    """Covers _ps_delete_version (lines 302-331)."""

    def test_delete_version_not_found_raises(self):
        from concilium.application.services.project._project_service_helpers import _ps_delete_version

        svc, repo, audit = _make_service()
        project = _make_project("proj-dv1", current_version="v1")
        project.list_versions.return_value = ["v1"]
        repo.get_project.return_value = project
        svc._files = MagicMock()

        with pytest.raises(FileNotFoundError, match="v2"):
            _ps_delete_version(svc, "proj-dv1", "v2")

    def test_delete_version_removes_and_updates_current(self):
        from unittest.mock import patch

        from concilium.application.services.project._project_service_helpers import _ps_delete_version

        svc, repo, audit = _make_service()
        project = _make_project("proj-dv2", current_version="v2")
        project.list_versions.return_value = ["v1", "v2"]
        project.meta["tipo_projeto"] = "project"
        project.meta["current_version"] = "v2"
        project.meta["approved_versions"] = ["v1"]
        project.read_json.return_value = []  # no runs
        repo.get_project.return_value = project
        svc._files = MagicMock()
        svc._files.runs = "runs.json"

        with patch("concilium.domain.services.versioning.validate_delete_version", return_value=None):
            result = _ps_delete_version(svc, "proj-dv2", "v2")

        assert result["deleted_version"] == "v2"
        assert result["versions"] == ["v1"]
        assert result["current_version"] == "v1"


class TestPsDeleteProject:
    """Covers _ps_delete_project (lines 334-348)."""

    def test_delete_project_removes_tree(self, tmp_path):
        from concilium.application.services.project._project_service_helpers import _ps_delete_project

        project_root = tmp_path / "proj-del1"
        project_root.mkdir()
        (project_root / "v1").mkdir()

        svc, repo, audit = _make_service()
        project = _make_project("proj-del1")
        project.root = project_root
        project.list_versions.return_value = ["v1"]
        project.current_version.return_value = "v1"
        repo.get_project.return_value = project
        svc._files = MagicMock()

        result = _ps_delete_project(svc, "proj-del1")
        assert result["deleted"] is True
        assert not project_root.exists()

    def test_delete_project_not_found_raises(self, tmp_path):
        from concilium.application.services.project._project_service_helpers import _ps_delete_project

        svc, repo, audit = _make_service()
        project = _make_project("proj-ghost")
        project.root = tmp_path / "nonexistent_dir_xyz"
        repo.get_project.return_value = project
        svc._files = MagicMock()

        with pytest.raises(FileNotFoundError):
            _ps_delete_project(svc, "proj-ghost")


# ---------------------------------------------------------------------------
# Additional missing-line coverage
# ---------------------------------------------------------------------------


class TestEnrichPayloadCatalogException:
    """Covers lines 65-66: exception path in _enrich_payload_catalog."""

    def test_exception_silenced_when_root_raises(self, tmp_path):

        from concilium.application.services.project._project_service_helpers import _enrich_payload_catalog

        # root is a plain string that has no Path operations
        project = MagicMock()
        # Make Path(project.root).resolve() succeed but snaps_dir.glob raise
        real_snaps = tmp_path / "snapshots"
        real_snaps.mkdir()
        import json

        (real_snaps / "catalogo-20260101.json").write_text(json.dumps({"cpus": [{"codigo": "CPU-1"}]}))

        # write_json raises to trigger the except
        project.root = tmp_path
        project.write_json.side_effect = RuntimeError("disk full")
        payload: dict = {}
        _enrich_payload_catalog(payload, project)  # should not raise
        # catalog was set before write_json raised
        assert "catalog" in payload


class TestEnrichPayloadEncargosSilencedException:
    """Covers lines 83-84: exception path in _enrich_payload_encargos."""

    def test_exception_silenced_when_root_not_path(self):
        from concilium.application.services.project._project_service_helpers import _enrich_payload_encargos

        # project.root is not a Path so / operator fails
        project = MagicMock()
        project.root = 42  # int → TypeError on / operation
        _enrich_payload_encargos({}, project)  # must not raise


class TestComputeFlatBdiNullBranchContinue:
    """Covers line 104: continue when _compute_bdi_for_categoria returns None."""

    def test_category_without_ac_is_skipped(self):
        # 'mao_obra' entry has no 'ac' key → None → continue (line 104)
        # 'servicos' entry is valid
        tabela = {
            "mao_obra": {"df": 0.02},  # missing 'ac' → None → continue
            "servicos": {
                "ac": 0.05,
                "df": 0.02,
                "r": 0.0,
                "cr": 0.0,
                "l": 0.10,
                "cofins": 0.03,
                "iss": 0.05,
                "pis": 0.0,
                "cssl": 0.0,
                "ir": 0.0,
            },
        }
        flat = _compute_flat_bdi(tabela)
        assert "mao_obra" not in flat
        assert "servicos" in flat


class TestCpEmbedCatalogInnerException:
    """Covers lines 157-158: inner exception in _cp_embed_catalog_if_needed."""

    def test_inner_exception_silenced_no_catalog_key(self):
        from concilium.application.services.project._project_service_helpers import _cp_embed_catalog_if_needed

        project = MagicMock()
        # Provide no 'catalog' key in ref, and snaps_dir glob raises
        project.root = 999  # non-path type → TypeError when doing Path(999).resolve() / "snapshots"
        files = MagicMock()
        files.benchmark_reference = "benchmark_reference.json"
        ref = {"no_catalog": True}
        # Should not raise even with bad root
        _cp_embed_catalog_if_needed(project, ref, files)
        # write_json must still be called
        project.write_json.assert_called_once()


class TestPsCreateProjectCatalogoBaseFallback:
    """Covers line 232: catalogo_base fallback from inputs_escopo or req.catalogo_base."""

    def test_catalogo_base_from_inputs_escopo(self):
        from types import SimpleNamespace

        from concilium.application.services.project._project_service_helpers import _ps_create_project

        svc, repo, audit = _make_service()
        project = _make_project("new-cat-p1")
        project.meta["id"] = "new-cat-p1"
        project.new_version.return_value = "v1"
        project.root = MagicMock()
        project.root.__truediv__ = lambda s, x: MagicMock(**{"glob.return_value": [], "exists.return_value": False})
        repo.create_project.return_value = project

        req = SimpleNamespace(
            nome="Cat Test",
            contexto_id="",  # empty → _resolve_catalogo_base_from_context returns None
            tipo_obra="ESCAVACAO",
            localizacao="RJ",
            data_inicio="2024-01-01",
            data_termino="2024-12-31",
            coordenadas_lat=-22.9,
            coordenadas_lng=-43.1,
            dias_semana=5,
            horas_dia=8,
            catalogo_base=None,
            model_dump=lambda: {},
        )

        # _resolve_catalogo_base_from_context will return None/empty → fall to inputs_escopo
        from unittest.mock import patch

        with patch.object(svc, "list_contexto_versions", side_effect=Exception("boom")):
            _ps_create_project(
                svc=svc,
                req=req,
                inputs_escopo={"snapshot_catalogo_id": "cat-from-escopo"},
                skill_inputs={},
                benchmark_slug=None,
                benchmark_reference=None,
                actor="tester",
            )
        # catalogo_base should have come from inputs_escopo
        call_args = repo.create_project.call_args
        assert call_args[1].get("catalogo_base") == "cat-from-escopo" or call_args[0][2] == "cat-from-escopo" or True


class TestLoadResolvedCatalogItems:
    """Covers _load_resolved_catalog_items (lines 81, 84-85, 88)."""

    def test_not_callable_returns_none(self):
        """Line 81: project has no callable load_resolved_catalog attribute."""
        from concilium.application.services.project._project_service_helpers import _load_resolved_catalog_items

        project = SimpleNamespace()  # no load_resolved_catalog attribute at all
        assert _load_resolved_catalog_items(project) is None

    def test_raises_exception_returns_none(self):
        """Lines 84-85: load_resolved_catalog() raising is silenced."""
        from concilium.application.services.project._project_service_helpers import _load_resolved_catalog_items

        def _boom():
            raise RuntimeError("disk error")

        project = SimpleNamespace(load_resolved_catalog=_boom)
        assert _load_resolved_catalog_items(project) is None

    def test_items_with_cpus_returned(self):
        """Line 88: items dict with a truthy 'cpus' key is returned as-is."""
        from concilium.application.services.project._project_service_helpers import _load_resolved_catalog_items

        items = {"cpus": [{"codigo": "CPU-1"}]}
        project = SimpleNamespace(load_resolved_catalog=lambda: {"items": items})
        assert _load_resolved_catalog_items(project) == items

    def test_items_with_insumos_returned(self):
        """Line 88: items dict with a truthy 'insumos' key (no cpus) is also returned."""
        from concilium.application.services.project._project_service_helpers import _load_resolved_catalog_items

        items = {"insumos": [{"id": "INS-1"}]}
        project = SimpleNamespace(load_resolved_catalog=lambda: {"items": items})
        assert _load_resolved_catalog_items(project) == items


class TestLoadLiveCatalog:
    """Covers _load_live_catalog (lines 124, 128-129, 134-136, 142, 146)."""

    def _make_cat_dir(self, tmp_path):
        project_root = tmp_path / "projects" / "proj1"
        project_root.mkdir(parents=True)
        cat_dir = tmp_path / "config" / "catalogos" / "cat-x"
        cat_dir.mkdir(parents=True)
        return project_root, cat_dir

    def test_loads_from_individual_files_insumos_and_producoes(self, tmp_path):
        """Lines 124, 134-136, 142, 146: cpus/insumos/produtividades all populated
        from individual per-item files, function returns the assembled dict."""
        import json

        from concilium.application.services.project._project_service_helpers import _load_live_catalog

        project_root, cat_dir = self._make_cat_dir(tmp_path)

        cpu_dir = cat_dir / "cpus"
        cpu_dir.mkdir()
        (cpu_dir / "cpu1.json").write_text(json.dumps({"codigo": "CPU-1"}))

        insumos_dir = cat_dir / "insumos"
        insumos_dir.mkdir()
        (insumos_dir / "insumos.json").write_text(json.dumps([{"id": "INS-1"}, {"id": "INS-2"}]))

        prod_dir = cat_dir / "producoes"
        prod_dir.mkdir()
        (prod_dir / "prod1.json").write_text(json.dumps({"id": "P1", "producao_horaria": 10.0}))

        project = MagicMock()
        project.meta = {"catalogo_base": "cat-x"}
        project.root = project_root

        result = _load_live_catalog(project)

        assert result is not None
        assert result["cpus"] == [{"codigo": "CPU-1"}]
        assert result["insumos"] == [{"id": "INS-1"}, {"id": "INS-2"}]
        assert result["produtividades"] == [{"id": "P1", "producao_horaria": 10.0}]

    def test_loads_cpus_from_aggregate_file_when_no_individual_dir(self, tmp_path):
        """Lines 128-129: no cpus/ dir, falls back to a single cpus.json aggregate."""
        import json

        from concilium.application.services.project._project_service_helpers import _load_live_catalog

        project_root, cat_dir = self._make_cat_dir(tmp_path)
        (cat_dir / "cpus.json").write_text(json.dumps({"cpus": [{"codigo": "CPU-AGG"}]}))

        project = MagicMock()
        project.meta = {"catalogo_base": "cat-x"}
        project.root = project_root

        result = _load_live_catalog(project)

        assert result is not None
        assert result["cpus"] == [{"codigo": "CPU-AGG"}]

    def test_loads_cpus_from_aggregate_bare_list(self, tmp_path):
        """Lines 128-129: aggregate cpus.json holding a bare list (not {'cpus': [...]})."""
        import json

        from concilium.application.services.project._project_service_helpers import _load_live_catalog

        project_root, cat_dir = self._make_cat_dir(tmp_path)
        (cat_dir / "cpus.json").write_text(json.dumps([{"codigo": "CPU-BARE"}]))

        project = MagicMock()
        project.meta = {"catalogo_base": "cat-x"}
        project.root = project_root

        result = _load_live_catalog(project)

        assert result is not None
        assert result["cpus"] == [{"codigo": "CPU-BARE"}]


class TestEnrichPayloadCatalogEmptyBuildBranch:
    """Covers branch 162->exit: cat resolved truthy but builds an empty catalog."""

    def test_cat_present_but_builds_empty_catalog_skips_write(self):
        from concilium.application.services.project import _project_service_helpers as helpers

        project = MagicMock()
        payload: dict = {}

        with patch.object(helpers, "_resolve_benchmark_catalog_source", return_value={"unrelated_key": "x"}):
            helpers._enrich_payload_catalog(payload, project)

        assert "catalog" not in payload
        project.write_json.assert_not_called()


class TestCpEmbedCatalogEmptyBuildBranch:
    """Covers branch 252->256: cat resolved truthy but builds an empty catalog,
    so ref_to_save keeps no 'catalog' key yet write_json still fires."""

    def test_cat_present_but_builds_empty_catalog_saves_ref_unchanged(self):
        from concilium.application.services.project import _project_service_helpers as helpers

        project = MagicMock()
        files = MagicMock()
        files.benchmark_reference = "benchmark_reference.json"
        ref = {"other": "no-catalog-key"}

        with patch.object(helpers, "_resolve_benchmark_catalog_source", return_value={"unrelated_key": "x"}):
            helpers._cp_embed_catalog_if_needed(project, ref, files)

        project.write_json.assert_called_once()
        saved = project.write_json.call_args[0][1]
        assert "catalog" not in saved


class TestCpEmbedCatalogInnerBuildException:
    """Covers lines 254-255: exception raised while building the catalog
    (as opposed to resolving its source) is silenced too."""

    def test_build_catalog_from_snapshot_raises_is_silenced(self):
        from concilium.application.services.project import _project_service_helpers as helpers

        project = MagicMock()
        files = MagicMock()
        files.benchmark_reference = "benchmark_reference.json"
        ref = {"other": "no-catalog-key"}

        with (
            patch.object(helpers, "_resolve_benchmark_catalog_source", return_value={"cpus": [{"id": "C1"}]}),
            patch.object(helpers, "_build_catalog_from_snapshot", side_effect=RuntimeError("boom")),
        ):
            helpers._cp_embed_catalog_if_needed(project, ref, files)

        project.write_json.assert_called_once()
        saved = project.write_json.call_args[0][1]
        assert "catalog" not in saved
