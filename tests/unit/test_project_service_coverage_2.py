from __future__ import annotations

"""Coverage tests for ProjectService – missing lines batch 2."""

from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from concilium.application.services.project.project_service import ProjectService  # noqa: E402

_normalize_eap_item = ProjectService._normalize_eap_item


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_svc():
    repo = MagicMock()
    audit = MagicMock()
    return ProjectService(repo, audit)


def _make_project(*, exists_file: bool = False):
    proj = MagicMock()
    proj.exists.return_value = exists_file
    proj.meta = {}
    proj.list_versions.return_value = []
    proj.current_version.return_value = None
    return proj


# ---------------------------------------------------------------------------
# 1. get_project – benchmark_reference_file (lines 218-220, 231, 240, 246, 249)
# ---------------------------------------------------------------------------


class TestGetProject:
    def test_benchmark_reference_file_present_when_exists(self):
        svc = _make_svc()
        proj = _make_project(exists_file=True)
        svc._repository.get_project.return_value = proj

        result = svc.get_project("proj-1")
        assert result["benchmark_reference_file"] == svc._files.benchmark_reference

    def test_benchmark_reference_file_none_when_not_exists(self):
        svc = _make_svc()
        proj = _make_project(exists_file=False)
        svc._repository.get_project.return_value = proj

        result = svc.get_project("proj-1")
        assert result["benchmark_reference_file"] is None

    def test_get_eap_non_list_becomes_empty(self):
        """Line 231: eap = [] when read_json returns non-list."""
        svc = _make_svc()
        proj = MagicMock()
        proj.meta = {"id": "p1"}
        proj.read_json.side_effect = lambda path, default: "bad_data" if "eap_items" in str(path) else {}
        proj.load_canonical.return_value = None
        proj.list_versions.return_value = []
        svc._repository.get_project.return_value = proj

        result = svc.get_eap("p1")
        assert result["items"] == []

    def test_get_eap_normalize_skips_none(self):
        """Lines 245-246: _normalize_eap_item returning None → continue."""
        svc = _make_svc()
        proj = MagicMock()
        proj.meta = {"id": "p1"}

        # eap_items empty → falls through to benchmark_reference
        # benchmark_reference has historical source with bad row (no item_id/cpu_id)
        def _read_json(path, default):
            if "eap_items" in str(path):
                return []
            if "benchmark_reference" in str(path):
                return {"eap": [{"no_item_id": True}]}
            return default

        proj.read_json.side_effect = _read_json
        proj.load_canonical.return_value = None
        proj.list_versions.return_value = []
        svc._repository.get_project.return_value = proj

        result = svc.get_eap("p1")
        assert result["items"] == []

    def test_get_eap_dedup_same_item_id(self):
        """Line 249: duplicate item_id → continue."""
        svc = _make_svc()
        proj = MagicMock()
        proj.meta = {"id": "p1"}
        dup_row = {"item_id": "A1", "cpu_id": "CPU-1", "descricao": "X", "unidade": "un", "quantitativo": 1.0}

        def _read_json(path, default):
            if "eap_items" in str(path):
                return []
            if "benchmark_reference" in str(path):
                return {"eap": [dup_row, dup_row]}
            return default

        proj.read_json.side_effect = _read_json
        proj.load_canonical.return_value = None
        proj.list_versions.return_value = []
        svc._repository.get_project.return_value = proj

        result = svc.get_eap("p1")
        # should deduplicate → only 1 item
        assert result["count"] == 1


# ---------------------------------------------------------------------------
# 2. compare_versions – lines 356-357, 364-388
# ---------------------------------------------------------------------------


class TestCompareVersions:
    def _make_version_project(self):
        proj = MagicMock()
        proj.meta = {}
        proj.list_versions.return_value = ["v1", "v2"]
        return proj

    def test_left_none_raises(self):
        svc = _make_svc()
        proj = self._make_version_project()
        proj.load_canonical.side_effect = [None, MagicMock()]
        proj.meta = {"version_history": {}}
        svc._repository.get_project.return_value = proj

        with patch(
            "concilium.application.services.project.project_service.resolve_compare_version",
            side_effect=lambda p, v: v,
        ):
            with pytest.raises(ValueError, match="sem canônico"):
                svc.compare_versions("p1", "v1", "v2")

    def test_right_none_raises(self):
        svc = _make_svc()
        proj = self._make_version_project()
        canonical_left = MagicMock()
        proj.load_canonical.side_effect = [canonical_left, None]
        proj.meta = {"version_history": {}}
        svc._repository.get_project.return_value = proj

        with patch(
            "concilium.application.services.project.project_service.resolve_compare_version",
            side_effect=lambda p, v: v,
        ):
            with pytest.raises(ValueError, match="sem canônico"):
                svc.compare_versions("p1", "v1", "v2")

    def test_both_present_returns_autoria_metadata(self):
        svc = _make_svc()
        proj = self._make_version_project()
        canonical_left = MagicMock()
        canonical_right = MagicMock()
        proj.load_canonical.side_effect = [canonical_left, canonical_right]
        proj.meta = {
            "version_history": {
                "v1": {
                    "criado_por": "alice",
                    "role_criador": "gestor",
                    "procurement_intent": "RFP",
                    "criado_em": "2026-01-01",
                },
                "v2": {
                    "criado_por": "bob",
                    "role_criador": "admin",
                    "procurement_intent": "RFI",
                    "criado_em": "2026-01-02",
                },
            }
        }
        svc._repository.get_project.return_value = proj

        with (
            patch(
                "concilium.application.services.project.project_service.resolve_compare_version",
                side_effect=lambda p, v: v,
            ),
            patch(
                "concilium.application.services.project.project_service.build_summary",
                side_effect=lambda c: {"summary": str(c)},
            ),
            patch(
                "concilium.application.services.project.project_service.calculate_deltas",
                return_value={"delta": 0},
            ),
        ):
            result = svc.compare_versions("p1", "v1", "v2")

        assert result["left_autoria"]["criado_por"] == "alice"
        assert result["right_autoria"]["criado_por"] == "bob"
        assert result["left_autoria"]["procurement_intent"] == "RFP"
        assert "deltas" in result


# ---------------------------------------------------------------------------
# 3. get_artifact_bytes – lines 418-423 (kind intermediate / artifacts / invalid)
# ---------------------------------------------------------------------------


class TestGetArtifactBytes:
    def _setup(self, svc, *, version="v1", read_bytes_return=b"data"):
        proj = MagicMock()
        proj.current_version.return_value = version
        proj.read_bytes.return_value = read_bytes_return
        proj.load_output_file.return_value = read_bytes_return
        svc._repository.get_project.return_value = proj
        return proj

    def test_kind_intermediate_reads_intermediate_path(self):
        svc = _make_svc()
        proj = self._setup(svc)

        data, mt = svc.get_artifact_bytes("p1", "v1", kind="intermediate", filename="foo.bin")

        proj.read_bytes.assert_called_once_with("v1/intermediate/foo.bin")
        assert data == b"data"

    def test_kind_artifacts_reads_artifacts_path(self):
        svc = _make_svc()
        proj = self._setup(svc)

        data, mt = svc.get_artifact_bytes("p1", "v1", kind="artifacts", filename="report.pdf")

        proj.read_bytes.assert_called_once_with("v1/artifacts/report.pdf")

    def test_kind_invalid_raises_value_error(self):
        svc = _make_svc()
        self._setup(svc)

        with pytest.raises(ValueError, match="kind deve ser"):
            svc.get_artifact_bytes("p1", "v1", kind="bogus", filename="file.txt")


# ---------------------------------------------------------------------------
# 4. list_contextos, list_perfis + create/compare (lines 452-517)
# ---------------------------------------------------------------------------


class TestContextoAndPerfilMethods:
    def test_list_contextos_svc_present(self):
        svc = _make_svc()
        mock_svc = MagicMock()
        mock_svc.list_contexts.return_value = [{"id": "ctx-1"}]
        with patch.object(svc, "_get_contexto_svc", return_value=mock_svc):
            result = svc.list_contextos()
        assert result == [{"id": "ctx-1"}]

    def test_list_contextos_svc_none(self):
        svc = _make_svc()
        with patch.object(svc, "_get_contexto_svc", return_value=None):
            result = svc.list_contextos()
        assert result == []

    def test_list_perfis_svc_present(self):
        svc = _make_svc()
        mock_svc = MagicMock()
        mock_svc.list_entities.return_value = [{"id": "perf-1"}]
        with patch.object(svc, "_get_perfil_svc", return_value=mock_svc):
            result = svc.list_perfis()
        assert result == [{"id": "perf-1"}]

    def test_list_perfis_svc_none(self):
        svc = _make_svc()
        with patch.object(svc, "_get_perfil_svc", return_value=None):
            result = svc.list_perfis()
        assert result == []

    def test_create_perfil_version_svc_none_raises(self):
        svc = _make_svc()
        with patch.object(svc, "_get_perfil_svc", return_value=None):
            with pytest.raises(RuntimeError, match="perfis"):
                svc.create_perfil_version("p1", {}, "motivo")

    def test_create_perfil_version_svc_present_calls_validate_and_create(self):
        svc = _make_svc()
        mock_svc = MagicMock()
        mock_svc.create_version.return_value = {"version": "v2"}
        with (
            patch.object(svc, "_get_perfil_svc", return_value=mock_svc),
            patch.object(svc, "_validate_perfil_fields") as mock_val,
        ):
            result = svc.create_perfil_version("p1", {"x": 1}, "motivo", "alice")
        mock_val.assert_called_once()
        mock_svc.create_version.assert_called_once()
        assert result == {"version": "v2"}

    def test_compare_perfil_versions_svc_none_returns_error(self):
        svc = _make_svc()
        with patch.object(svc, "_get_perfil_svc", return_value=None):
            result = svc.compare_perfil_versions("p1", "v1", "v2")
        assert "error" in result

    def test_compare_perfil_versions_svc_present_calls_compare(self):
        svc = _make_svc()
        mock_svc = MagicMock()
        mock_svc.compare.return_value = {"diff": []}
        with patch.object(svc, "_get_perfil_svc", return_value=mock_svc):
            result = svc.compare_perfil_versions("p1", "v1", "v2")
        assert result == {"diff": []}


# ---------------------------------------------------------------------------
# 5. list_temas, create_tema_version, compare_tema_versions (lines 537-563)
# ---------------------------------------------------------------------------


class TestTemaMethods:
    def test_list_temas_svc_present(self):
        svc = _make_svc()
        mock_svc = MagicMock()
        mock_svc.list_temas.return_value = [{"id": "t1"}]
        with patch.object(svc, "_get_tema_svc", return_value=mock_svc):
            result = svc.list_temas()
        assert result == [{"id": "t1"}]

    def test_list_temas_svc_none(self):
        svc = _make_svc()
        with patch.object(svc, "_get_tema_svc", return_value=None):
            result = svc.list_temas()
        assert result == []

    def test_create_tema_version_svc_none_raises(self):
        svc = _make_svc()
        with patch.object(svc, "_get_tema_svc", return_value=None):
            with pytest.raises(RuntimeError, match="temas"):
                svc.create_tema_version("t1", {}, "motivo")

    def test_create_tema_version_svc_present(self):
        svc = _make_svc()
        mock_svc = MagicMock()
        mock_svc.create_version.return_value = {"version": "v2"}
        with patch.object(svc, "_get_tema_svc", return_value=mock_svc), patch.object(svc, "_validate_tema_fields"):
            result = svc.create_tema_version("t1", {}, "motivo", "actor")
        mock_svc.create_version.assert_called_once()
        assert result == {"version": "v2"}

    def test_compare_tema_versions_svc_none_returns_error(self):
        svc = _make_svc()
        with patch.object(svc, "_get_tema_svc", return_value=None):
            result = svc.compare_tema_versions("t1", "v1", "v2")
        assert "error" in result

    def test_compare_tema_versions_svc_present(self):
        svc = _make_svc()
        mock_svc = MagicMock()
        mock_svc.compare.return_value = {"diff": []}
        with patch.object(svc, "_get_tema_svc", return_value=mock_svc):
            result = svc.compare_tema_versions("t1", "v1", "v2")
        assert result == {"diff": []}


# ---------------------------------------------------------------------------
# 6. list_jurisdicoes, create_jurisdicao_version, compare_jurisdicao_versions
# ---------------------------------------------------------------------------


class TestJurisdicaoMethods:
    def test_list_jurisdicoes_svc_present(self):
        svc = _make_svc()
        mock_svc = MagicMock()
        mock_svc.list_jurisdicoes.return_value = [{"id": "j1"}]
        with patch.object(svc, "_get_jurisdiction_svc", return_value=mock_svc):
            result = svc.list_jurisdicoes()
        assert result == [{"id": "j1"}]

    def test_list_jurisdicoes_svc_none(self):
        svc = _make_svc()
        with patch.object(svc, "_get_jurisdiction_svc", return_value=None):
            result = svc.list_jurisdicoes()
        assert result == []

    def test_create_jurisdicao_version_svc_none_raises(self):
        svc = _make_svc()
        with patch.object(svc, "_get_jurisdiction_svc", return_value=None):
            with pytest.raises(RuntimeError, match="jurisdições"):
                svc.create_jurisdicao_version("j1", {}, "motivo")

    def test_create_jurisdicao_version_svc_present(self):
        svc = _make_svc()
        mock_svc = MagicMock()
        mock_svc.create_version.return_value = {"version": "v2"}
        with (
            patch.object(svc, "_get_jurisdiction_svc", return_value=mock_svc),
            patch.object(svc, "_validate_jurisdicao_fields"),
        ):
            svc.create_jurisdicao_version("j1", {}, "motivo", "actor")
        mock_svc.create_version.assert_called_once()

    def test_compare_jurisdicao_versions_svc_none_returns_error(self):
        svc = _make_svc()
        with patch.object(svc, "_get_jurisdiction_svc", return_value=None):
            result = svc.compare_jurisdicao_versions("j1", "v1", "v2")
        assert "error" in result

    def test_compare_jurisdicao_versions_svc_present(self):
        svc = _make_svc()
        mock_svc = MagicMock()
        mock_svc.compare.return_value = {"diff": []}
        with patch.object(svc, "_get_jurisdiction_svc", return_value=mock_svc):
            result = svc.compare_jurisdicao_versions("j1", "v1", "v2")
        assert result == {"diff": []}


# ---------------------------------------------------------------------------
# 7. _validate_contexto_fields – catalogo_id branch (lines 694-698, 701, 703-710)
# ---------------------------------------------------------------------------


class TestValidateContextoFields:
    def test_catalogo_id_config_root_none_raises(self):
        svc = _make_svc()
        with (
            patch.object(svc, "_resolve_config_root", return_value=None),
            patch.object(svc, "list_perfis", return_value=[]),
            patch.object(svc, "list_jurisdicoes", return_value=[]),
            patch.object(svc, "list_temas", return_value=[]),
        ):
            with pytest.raises(ValueError, match="catalogo_id inválido"):
                svc._validate_contexto_fields({"catalogo_id": "cat-99"})

    def test_catalogo_id_path_not_exists_raises(self):
        from pathlib import Path

        svc = _make_svc()
        fake_cfg = MagicMock(spec=Path)
        # (cfg / "catalogos" / "cat-99").exists() → False
        fake_catalogos = MagicMock()
        fake_catalog_dir = MagicMock()
        fake_catalog_dir.exists.return_value = False
        fake_catalogos.__truediv__ = MagicMock(return_value=fake_catalog_dir)
        fake_cfg.__truediv__ = MagicMock(return_value=fake_catalogos)

        with (
            patch.object(svc, "_resolve_config_root", return_value=fake_cfg),
            patch.object(svc, "list_perfis", return_value=[]),
            patch.object(svc, "list_jurisdicoes", return_value=[]),
            patch.object(svc, "list_temas", return_value=[]),
        ):
            with pytest.raises(ValueError, match="catalogo_id inválido"):
                svc._validate_contexto_fields({"catalogo_id": "cat-99"})

    def test_catalogo_id_valid_does_not_raise(self):
        from pathlib import Path

        svc = _make_svc()
        fake_cfg = MagicMock(spec=Path)
        fake_catalog_dir = MagicMock()
        fake_catalog_dir.exists.return_value = True
        fake_catalogos = MagicMock()
        fake_catalogos.__truediv__ = MagicMock(return_value=fake_catalog_dir)
        fake_cfg.__truediv__ = MagicMock(return_value=fake_catalogos)

        with (
            patch.object(svc, "_resolve_config_root", return_value=fake_cfg),
            patch.object(svc, "list_perfis", return_value=[]),
            patch.object(svc, "list_jurisdicoes", return_value=[]),
            patch.object(svc, "list_temas", return_value=[]),
        ):
            # Should not raise
            svc._validate_contexto_fields({"catalogo_id": "cat-1"})


# ---------------------------------------------------------------------------
# 8. _normalize_eap_item static method (lines 724-764)
# ---------------------------------------------------------------------------


class TestNormalizeEapItem:
    def test_valid_item_returns_normalized(self):
        item = {"item_id": "A1", "cpu_id": "CPU-1", "descricao": "Atividade X", "unidade": "m²", "quantitativo": 5.0}
        result = _normalize_eap_item(item, ordem_padrao=1)
        assert result is not None
        assert result["item_id"] == "A1"
        assert result["cpu_id"] == "CPU-1"
        assert result["quantitativo"] == 5.0
        assert result["ordem"] == 1

    def test_missing_item_id_returns_none(self):
        item = {"cpu_id": "CPU-1", "descricao": "X"}
        result = _normalize_eap_item(item, ordem_padrao=1)
        assert result is None

    def test_missing_cpu_id_returns_none(self):
        item = {"item_id": "A1", "descricao": "X"}
        result = _normalize_eap_item(item, ordem_padrao=1)
        assert result is None

    def test_invalid_quantitativo_becomes_zero(self):
        item = {"item_id": "A1", "cpu_id": "CPU-1", "quantitativo": "bad_float"}
        result = _normalize_eap_item(item, ordem_padrao=1)
        assert result is not None
        assert result["quantitativo"] == 0.0

    def test_custom_ordem_used_when_provided(self):
        item = {"item_id": "A1", "cpu_id": "CPU-1", "ordem": 42}
        result = _normalize_eap_item(item, ordem_padrao=1)
        assert result is not None
        assert result["ordem"] == 42

    def test_ordem_padrao_used_when_ordem_absent(self):
        item = {"item_id": "A1", "cpu_id": "CPU-1"}
        result = _normalize_eap_item(item, ordem_padrao=7)
        assert result is not None
        assert result["ordem"] == 7

    def test_alternative_keys_item_id(self):
        """Fallback keys: activity_id, eap_item_id, id, codigo."""
        item = {"activity_id": "ACT-1", "cpu_codigo": "CPU-2"}
        result = _normalize_eap_item(item, ordem_padrao=1)
        assert result is not None
        assert result["item_id"] == "ACT-1"
        assert result["cpu_id"] == "CPU-2"

    def test_empty_string_item_id_returns_none(self):
        """Empty string should be treated as missing."""
        item = {"item_id": "   ", "cpu_id": "CPU-1"}
        result = _normalize_eap_item(item, ordem_padrao=1)
        assert result is None


# ---------------------------------------------------------------------------
# 9. get_benchmark_reference – various payload states (lines 821-905)
# ---------------------------------------------------------------------------


class TestGetBenchmarkReference:
    def _setup_proj(self, svc, *, payload=None, skill_inputs=None, eap_items=None):
        proj = MagicMock()
        proj.meta = {}

        def _read_json(path, default):
            p = str(path)
            if "benchmark_reference" in p:
                return payload if payload is not None else {}
            if "skill_inputs" in p:
                return skill_inputs if skill_inputs is not None else {}
            if "eap_items" in p:
                return eap_items if eap_items is not None else []
            return default

        proj.read_json.side_effect = _read_json
        proj.load_canonical.return_value = None
        proj.list_versions.return_value = []
        svc._repository.get_project.return_value = proj
        return proj

    def _patch_enrichers(self):
        """Patch the three enricher functions so they don't fail."""
        from unittest.mock import patch as _patch

        return (
            _patch("concilium.application.services.project.project_service._catalog_is_deficit", return_value=False),
            _patch("concilium.application.services.project.project_service._enrich_payload_encargos"),
            _patch("concilium.application.services.project.project_service._enrich_payload_bdi"),
        )

    def test_missing_skill_inputs_reads_from_project(self):
        svc = _make_svc()
        # payload with no skill_inputs key → should hydrate from project
        payload = {"cpus": {"itens_eap": [{"item_id": "A1", "cpu_id": "CPU-1"}]}}
        skill_inputs_data = {"01-escopo-e-eap": {"some_key": "val"}}

        self._setup_proj(svc, payload=payload, skill_inputs=skill_inputs_data)

        p1, p2, p3 = self._patch_enrichers()
        with p1, p2, p3:
            result = svc.get_benchmark_reference("proj-1")

        assert result["skill_inputs"] == skill_inputs_data

    def test_historical_eap_source_migrates_to_cpus_itens_eap(self):
        """Lines 857-875: source != canonical → migrates historical rows."""
        svc = _make_svc()
        # payload with historical eap root → triggers migration
        payload = {
            "eap": [{"item_id": "A1", "cpu_id": "CPU-1", "descricao": "Atividade A"}],
            "skill_inputs": {"key": "val"},
        }
        self._setup_proj(svc, payload=payload)

        p1, p2, p3 = self._patch_enrichers()
        with p1, p2, p3:
            result = svc.get_benchmark_reference("proj-1")

        # After migration, cpus.itens_eap should be populated
        assert isinstance(result.get("cpus", {}).get("itens_eap"), list)

    def test_no_valid_eap_falls_back_to_latest_version(self):
        """Lines 887-893: _latest_version_with_eap used when canonical is None."""
        svc = _make_svc()
        # payload with no EAP anywhere
        payload = {"skill_inputs": {"k": "v"}}
        proj = self._setup_proj(svc, payload=payload)
        proj.load_canonical.return_value = None

        historical_rows = [{"item_id": "H1", "cpu_id": "CPU-H1"}]
        with patch(
            "concilium.application.services.project.project_service._latest_version_with_eap",
            return_value=(historical_rows, "v3"),
        ):
            p1, p2, p3 = self._patch_enrichers()
            with p1, p2, p3:
                result = svc.get_benchmark_reference("proj-1")

        assert result["_debug"]["benchmark_reference_source"].startswith("historical_canonical.eap")

    def test_eap_items_hydrates_cpus_block(self):
        """Lines 835-855: eap_items → cpus.itens_eap."""
        svc = _make_svc()
        payload = {"skill_inputs": {"k": "v"}}
        eap_items = [
            {"item_id": "E1", "cpu_id": "CPU-E1", "descricao": "EAP item", "unidade": "un", "quantitativo": 2.0}
        ]
        self._setup_proj(svc, payload=payload, eap_items=eap_items)

        p1, p2, p3 = self._patch_enrichers()
        with p1, p2, p3:
            result = svc.get_benchmark_reference("proj-1")

        assert result["_debug"]["benchmark_reference_source"] == "eap_items->cpus.itens_eap"

    def test_invalid_payload_raises(self):
        svc = _make_svc()
        proj = MagicMock()
        proj.read_json.return_value = "not a dict"
        svc._repository.get_project.return_value = proj

        with pytest.raises(ValueError, match="invalida"):
            svc.get_benchmark_reference("proj-1")

    def test_debug_block_present(self):
        """Line 900: _debug block is returned."""
        svc = _make_svc()
        payload = {"cpus": {"itens_eap": [{"item_id": "A1", "cpu_id": "CPU-1"}]}, "skill_inputs": {}}
        self._setup_proj(svc, payload=payload)

        p1, p2, p3 = self._patch_enrichers()
        with p1, p2, p3:
            result = svc.get_benchmark_reference("proj-1")

        assert "_debug" in result
        assert "benchmark_reference_source" in result["_debug"]


# ---------------------------------------------------------------------------
# 10. get_version_history (lines 290-291)
# ---------------------------------------------------------------------------


class TestGetVersionHistory:
    def test_returns_version_history_from_meta(self):
        svc = _make_svc()
        proj = MagicMock()
        proj.meta = {"version_history": {"v1": {"criado_por": "alice"}}}
        svc._repository.get_project.return_value = proj

        result = svc.get_version_history("proj-1")
        assert result == {"v1": {"criado_por": "alice"}}

    def test_returns_empty_dict_when_missing(self):
        svc = _make_svc()
        proj = MagicMock()
        proj.meta = {}
        svc._repository.get_project.return_value = proj

        result = svc.get_version_history("proj-1")
        assert result == {}

    def test_delete_project_delegates(self):
        """Line 297: delete_project calls _ps_delete_project."""
        svc = _make_svc()
        with patch(
            "concilium.application.services.project.project_service._ps_delete_project",
            return_value={"deleted": True},
        ) as mock_del:
            result = svc.delete_project("proj-1", actor="admin")
        mock_del.assert_called_once_with(svc, "proj-1", "admin")
        assert result == {"deleted": True}
