from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from concilium.application.services.project.project_service import (
    ProjectService,
    _canonical_eap_to_rows,
    _catalog_is_deficit,
    _debug_storage_info,
    _extract_historical_eap_rows,
    _is_valid_canonical_eap,
    _latest_version_with_eap,
    _resolve_project_type,
)

# ---------------------------------------------------------------------------
# _debug_storage_info
# ---------------------------------------------------------------------------


def test_debug_storage_info_normal():
    project = MagicMock()
    project.root = MagicMock()
    project.root.__str__ = MagicMock(return_value="/some/root")
    project.root.parent.__str__ = MagicMock(return_value="/some")
    info = _debug_storage_info(project)
    assert info["storage_root"] == "/some/root"
    assert info["projects_root"] == "/some"


def test_debug_storage_info_root_raises():
    project = MagicMock()
    type(project).root = property(lambda self: (_ for _ in ()).throw(RuntimeError("no root")))
    info = _debug_storage_info(project)
    assert info["storage_root"] == ""
    assert info["projects_root"] == ""


# ---------------------------------------------------------------------------
# _resolve_project_type
# ---------------------------------------------------------------------------


def test_resolve_project_type_hot_project():
    assert _resolve_project_type({"tipo_projeto": "hot_project"}) == "hot_project"


def test_resolve_project_type_project():
    assert _resolve_project_type({"tipo_projeto": "project"}) == "project"


def test_resolve_project_type_unknown_with_benchmark_slug():
    assert _resolve_project_type({"tipo_projeto": "other", "benchmark_slug": "abc"}) == "hot_project"


def test_resolve_project_type_unknown_without_benchmark_slug():
    assert _resolve_project_type({"tipo_projeto": "other"}) == "project"


def test_resolve_project_type_missing_tipo():
    assert _resolve_project_type({}) == "project"


# ---------------------------------------------------------------------------
# _canonical_eap_to_rows
# ---------------------------------------------------------------------------


def test_canonical_eap_to_rows_dict_items():
    canonical = MagicMock()
    canonical.eap = [{"a": 1}, {"b": 2}]
    rows = _canonical_eap_to_rows(canonical)
    assert rows == [{"a": 1}, {"b": 2}]


def test_canonical_eap_to_rows_model_dump():
    item = MagicMock(spec=[])
    item.model_dump = MagicMock(return_value={"x": 10})
    canonical = MagicMock()
    canonical.eap = [item]
    rows = _canonical_eap_to_rows(canonical)
    assert rows == [{"x": 10}]


def test_canonical_eap_to_rows_dict_method():
    item = MagicMock(spec=[])
    item.dict = MagicMock(return_value={"y": 20})
    canonical = MagicMock()
    canonical.eap = [item]
    rows = _canonical_eap_to_rows(canonical)
    assert rows == [{"y": 20}]


def test_canonical_eap_to_rows_to_dict():
    item = MagicMock(spec=[])
    item.to_dict = MagicMock(return_value={"z": 30})
    canonical = MagicMock()
    canonical.eap = [item]
    rows = _canonical_eap_to_rows(canonical)
    assert rows == [{"z": 30}]


def test_canonical_eap_to_rows_empty():
    canonical = MagicMock()
    canonical.eap = []
    assert _canonical_eap_to_rows(canonical) == []


def test_canonical_eap_to_rows_no_eap_attr():
    canonical = MagicMock(spec=[])
    assert _canonical_eap_to_rows(canonical) == []


# ---------------------------------------------------------------------------
# _is_valid_canonical_eap
# ---------------------------------------------------------------------------


def test_is_valid_canonical_eap_no_cpus():
    assert _is_valid_canonical_eap({}) is False


def test_is_valid_canonical_eap_cpus_not_dict():
    assert _is_valid_canonical_eap({"cpus": [1, 2]}) is False


def test_is_valid_canonical_eap_empty_itens_eap():
    assert _is_valid_canonical_eap({"cpus": {"itens_eap": []}}) is False


def test_is_valid_canonical_eap_non_empty():
    assert _is_valid_canonical_eap({"cpus": {"itens_eap": [{"item_id": "1"}]}}) is True


# ---------------------------------------------------------------------------
# _extract_historical_eap_rows
# ---------------------------------------------------------------------------


def test_extract_historical_eap_rows_eap_key():
    payload = {"eap": [{"a": 1}, {"b": 2}]}
    rows = _extract_historical_eap_rows(payload)
    assert rows == [{"a": 1}, {"b": 2}]


def test_extract_historical_eap_rows_skill_inputs_path():
    payload = {"skill_inputs": {"01-escopo-e-eap": {"eap": [{"c": 3}]}}}
    rows = _extract_historical_eap_rows(payload)
    assert rows == [{"c": 3}]


def test_extract_historical_eap_rows_nested_inputs_escopo():
    payload = {"skill_inputs": {"01-escopo-e-eap": {"inputs_escopo": {"eap": [{"d": 4}]}}}}
    rows = _extract_historical_eap_rows(payload)
    assert rows == [{"d": 4}]


def test_extract_historical_eap_rows_none():
    rows = _extract_historical_eap_rows({})
    assert rows == []


# ---------------------------------------------------------------------------
# _catalog_is_deficit
# ---------------------------------------------------------------------------


def test_catalog_is_deficit_none():
    assert _catalog_is_deficit(None) is True


def test_catalog_is_deficit_no_cpus():
    assert _catalog_is_deficit({"cpus": []}) is True


def test_catalog_is_deficit_cpu_with_funcoes():
    catalog = {"cpus": [{"equipe": {"funcoes": [{"nome": "engenheiro"}], "equipamentos": []}}]}
    assert _catalog_is_deficit(catalog) is False


def test_catalog_is_deficit_cpus_not_list():
    assert _catalog_is_deficit({"cpus": "invalid"}) is True


# ---------------------------------------------------------------------------
# _latest_version_with_eap
# ---------------------------------------------------------------------------


def test_latest_version_with_eap_version_with_eap():
    project = MagicMock()
    project.list_versions.return_value = ["v1", "v2"]
    canonical = MagicMock()
    canonical.eap = [{"item_id": "x"}]
    project.load_canonical.return_value = canonical
    rows, version = _latest_version_with_eap(project)
    assert len(rows) > 0
    assert version is not None


def test_latest_version_with_eap_load_raises_skips():
    project = MagicMock()
    project.list_versions.return_value = ["v1", "v2"]
    project.load_canonical.side_effect = RuntimeError("fail")
    rows, version = _latest_version_with_eap(project)
    assert rows == []
    assert version is None


def test_latest_version_with_eap_no_eap_skips():
    project = MagicMock()
    project.list_versions.return_value = ["v1"]
    canonical = MagicMock()
    canonical.eap = []
    project.load_canonical.return_value = canonical
    rows, version = _latest_version_with_eap(project)
    assert rows == []
    assert version is None


def test_latest_version_with_eap_no_versions():
    project = MagicMock()
    project.list_versions.return_value = []
    rows, version = _latest_version_with_eap(project)
    assert rows == []
    assert version is None


# ---------------------------------------------------------------------------
# ProjectService helpers
# ---------------------------------------------------------------------------


def _make_service():
    repo = MagicMock()
    audit = MagicMock()
    svc = ProjectService(repository=repo, audit_service=audit)
    return svc, repo, audit


# ---------------------------------------------------------------------------
# list_projects
# ---------------------------------------------------------------------------


def test_list_projects_delegates_to_repo():
    svc, repo, _ = _make_service()
    p = MagicMock()
    p.meta = {"id": "proj-1", "nome": "Test", "contexto_id": "ctx", "tipo_projeto": "project"}
    p.list_versions.return_value = ["v1"]
    repo.list_projects.return_value = [p]
    result = svc.list_projects()
    assert len(result) == 1
    assert result[0]["project_id"] == "proj-1"


# ---------------------------------------------------------------------------
# get_project
# ---------------------------------------------------------------------------


def test_get_project_benchmark_reference_exists():
    svc, repo, _ = _make_service()
    project = MagicMock()
    project.meta = {"id": "p1", "nome": "N", "contexto_id": "c", "tipo_projeto": "project"}
    project.list_versions.return_value = ["v1"]
    project.current_version.return_value = "v1"
    project.exists.return_value = True
    repo.get_project.return_value = project
    result = svc.get_project("p1")
    assert result["benchmark_reference_file"] is not None


def test_get_project_benchmark_reference_missing():
    svc, repo, _ = _make_service()
    project = MagicMock()
    project.meta = {"id": "p1", "nome": "N", "contexto_id": "c", "tipo_projeto": "project"}
    project.list_versions.return_value = []
    project.current_version.return_value = None
    project.exists.return_value = False
    repo.get_project.return_value = project
    result = svc.get_project("p1")
    assert result["benchmark_reference_file"] is None


# ---------------------------------------------------------------------------
# compare_versions
# ---------------------------------------------------------------------------


def test_compare_versions_left_none_raises():
    svc, repo, _ = _make_service()
    project = MagicMock()

    project.load_canonical.return_value = None
    repo.get_project.return_value = project
    project.meta = {"version_history": {}}
    with patch(
        "concilium.application.services.project.project_service.resolve_compare_version",
        side_effect=lambda p, v: v,
    ):
        with pytest.raises(ValueError):
            svc.compare_versions("p1", "v1", "v2")


def test_compare_versions_both_present():
    svc, repo, _ = _make_service()
    project = MagicMock()
    project.meta = {"version_history": {}}
    canonical = MagicMock()
    canonical.custo_total = 100.0
    project.load_canonical.return_value = canonical
    repo.get_project.return_value = project
    with (
        patch(
            "concilium.application.services.project.project_service.resolve_compare_version",
            side_effect=lambda p, v: v,
        ),
        patch(
            "concilium.application.services.project.project_service.build_summary",
            return_value={"custo_total": 100.0},
        ),
        patch(
            "concilium.application.services.project.project_service.calculate_deltas",
            return_value={"custo_total": 0.0},
        ),
    ):
        result = svc.compare_versions("p1", "v1", "v2")
    assert "left" in result
    assert "right" in result
    assert "deltas" in result


# ---------------------------------------------------------------------------
# list_artifacts
# ---------------------------------------------------------------------------


def test_list_artifacts_current_version_none():
    svc, repo, _ = _make_service()
    project = MagicMock()
    project.current_version.return_value = None
    repo.get_project.return_value = project
    result = svc.list_artifacts("p1", None)
    assert result["version"] is None
    assert result["outputs"] == []


def test_list_artifacts_version_given():
    svc, repo, _ = _make_service()
    project = MagicMock()
    project.list_output_files.return_value = ["file.json"]
    project.list_file_names.return_value = []
    repo.get_project.return_value = project
    result = svc.list_artifacts("p1", "v1")
    assert result["version"] == "v1"
    assert "outputs" in result


# ---------------------------------------------------------------------------
# get_artifact_bytes
# ---------------------------------------------------------------------------


def test_get_artifact_bytes_intermediate():
    svc, repo, _ = _make_service()
    project = MagicMock()
    project.current_version.return_value = "v1"
    project.read_bytes.return_value = b"data"
    repo.get_project.return_value = project
    data, mime = svc.get_artifact_bytes("p1", "v1", "intermediate", "report.json")
    assert data == b"data"
    project.read_bytes.assert_called_once_with("v1/intermediate/report.json")


def test_get_artifact_bytes_artifacts():
    svc, repo, _ = _make_service()
    project = MagicMock()
    project.current_version.return_value = "v1"
    project.read_bytes.return_value = b"pdf"
    repo.get_project.return_value = project
    data, mime = svc.get_artifact_bytes("p1", "v1", "artifacts", "out.pdf")
    assert data == b"pdf"
    project.read_bytes.assert_called_once_with("v1/artifacts/out.pdf")


def test_get_artifact_bytes_invalid_kind():
    svc, repo, _ = _make_service()
    project = MagicMock()
    project.current_version.return_value = "v1"
    repo.get_project.return_value = project
    with pytest.raises(ValueError):
        svc.get_artifact_bytes("p1", "v1", "invalid", "x.json")


def test_get_artifact_bytes_payload_none():
    svc, repo, _ = _make_service()
    project = MagicMock()
    project.current_version.return_value = "v1"
    project.read_bytes.return_value = None
    repo.get_project.return_value = project
    with pytest.raises(FileNotFoundError):
        svc.get_artifact_bytes("p1", "v1", "intermediate", "missing.json")


# ---------------------------------------------------------------------------
# patch_project_config
# ---------------------------------------------------------------------------


def test_patch_project_config_updates_allowed_keys():
    svc, repo, _ = _make_service()
    project = MagicMock()
    project.meta = {"id": "p1", "nome": "Old", "contexto_id": "c"}
    repo.get_project.return_value = project
    result = svc.patch_project_config("p1", {"nome": "New", "illegal": "x"})
    assert "nome" in result["updated"]
    assert "illegal" not in result["updated"]


def test_patch_project_config_noop_when_same():
    svc, repo, _ = _make_service()
    project = MagicMock()
    project.meta = {"id": "p1", "nome": "Same"}
    repo.get_project.return_value = project
    result = svc.patch_project_config("p1", {"nome": "Same"})
    assert result["updated"] == []
    project.write_json.assert_not_called()


# ---------------------------------------------------------------------------
# list_contextos
# ---------------------------------------------------------------------------


def test_list_contextos_svc_present():
    svc, repo, _ = _make_service()
    mock_svc = MagicMock()
    mock_svc.list_contexts.return_value = [{"id": "ctx1"}]
    with patch.object(svc, "_get_contexto_svc", return_value=mock_svc):
        result = svc.list_contextos()
    assert result == [{"id": "ctx1"}]


def test_list_contextos_svc_none():
    svc, repo, _ = _make_service()
    with patch.object(svc, "_get_contexto_svc", return_value=None):
        result = svc.list_contextos()
    assert result == []


# ---------------------------------------------------------------------------
# list_perfis
# ---------------------------------------------------------------------------


def test_list_perfis_svc_present():
    svc, repo, _ = _make_service()
    mock_svc = MagicMock()
    mock_svc.list_entities.return_value = [{"id": "p1"}]
    with patch.object(svc, "_get_perfil_svc", return_value=mock_svc):
        result = svc.list_perfis()
    assert result == [{"id": "p1"}]


def test_list_perfis_svc_none():
    svc, repo, _ = _make_service()
    with patch.object(svc, "_get_perfil_svc", return_value=None):
        result = svc.list_perfis()
    assert result == []


# ---------------------------------------------------------------------------
# _validate_range_field
# ---------------------------------------------------------------------------


def test_validate_range_field_not_dict_skips():
    svc, _, _ = _make_service()
    # Should not raise — non-dict values are silently skipped
    svc._validate_range_field({"key": "not-a-dict"}, "key", lower=0.0, upper=1.0)


def test_validate_range_field_missing_min_raises():
    svc, _, _ = _make_service()
    with pytest.raises(ValueError, match="min"):
        svc._validate_range_field({"key": {"max": 0.5}}, "key", lower=0.0, upper=1.0)


def test_validate_range_field_missing_max_raises():
    svc, _, _ = _make_service()
    with pytest.raises(ValueError, match="max"):
        svc._validate_range_field({"key": {"min": 0.1}}, "key", lower=0.0, upper=1.0)


def test_validate_range_field_min_greater_than_max_raises():
    svc, _, _ = _make_service()
    with pytest.raises(ValueError, match="min deve ser"):
        svc._validate_range_field({"key": {"min": 0.8, "max": 0.2}}, "key", lower=0.0, upper=1.0)


def test_validate_range_field_out_of_range_raises():
    svc, _, _ = _make_service()
    with pytest.raises(ValueError, match="fora do intervalo"):
        svc._validate_range_field({"key": {"min": 0.0, "max": 2.0}}, "key", lower=0.0, upper=1.0)


def test_validate_range_field_valid():
    svc, _, _ = _make_service()
    # Should not raise
    svc._validate_range_field({"key": {"min": 0.1, "max": 0.9}}, "key", lower=0.0, upper=1.0)


# ---------------------------------------------------------------------------
# _normalize_eap_item
# ---------------------------------------------------------------------------


def test_normalize_eap_item_valid():
    item = {"item_id": "I1", "cpu_id": "CPU1", "descricao": "Desc", "quantitativo": 5.0}
    result = ProjectService._normalize_eap_item(item, ordem_padrao=1)
    assert result is not None
    assert result["item_id"] == "I1"
    assert result["cpu_id"] == "CPU1"
    assert result["quantitativo"] == 5.0


def test_normalize_eap_item_missing_item_id():
    item = {"cpu_id": "CPU1"}
    result = ProjectService._normalize_eap_item(item, ordem_padrao=1)
    assert result is None


def test_normalize_eap_item_missing_cpu_id():
    item = {"item_id": "I1"}
    result = ProjectService._normalize_eap_item(item, ordem_padrao=1)
    assert result is None


def test_normalize_eap_item_invalid_quantitativo():
    item = {"item_id": "I1", "cpu_id": "CPU1", "quantitativo": "not-a-number"}
    result = ProjectService._normalize_eap_item(item, ordem_padrao=1)
    assert result is not None
    assert result["quantitativo"] == 0.0
