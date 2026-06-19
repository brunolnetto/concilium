"""Tests for side_effects.py — targeting coverage boost from 62% toward 80%+."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from concilium.application.runtime.deliverables.side_effects import (
    _append_png_gallery,
    _dedup_insumos,
    _handle_skill_04_side_effects,
    _handle_skill_09_side_effects,
    _ingest_insumos,
    _json_default,
    _load_insumos_subdir,
    _load_output_image_bytes,
    _persist_typed_artifacts,
    _save_memorial_bdi_files,
    _save_relatorio_files,
    _save_relatorio_graficos_files,
)

# ---------------------------------------------------------------------------
# _json_default
# ---------------------------------------------------------------------------


class TestJsonDefault:
    def test_uuid_converts_to_string(self):
        import uuid

        u = uuid.UUID("12345678-1234-5678-1234-567812345678")
        result = _json_default(u)
        assert result == "12345678-1234-5678-1234-567812345678"

    def test_non_serializable_raises(self):
        with pytest.raises(TypeError):
            _json_default(object())

    def test_used_in_json_dumps_with_uuid(self):
        import uuid

        u = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        out = json.dumps({"id": u}, default=_json_default)
        assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in out


# ---------------------------------------------------------------------------
# _ingest_insumos
# ---------------------------------------------------------------------------


class TestIngestInsumos:
    def test_list_extends(self):
        insumos: list = []
        _ingest_insumos([{"id": "a"}, {"id": "b"}], insumos)
        assert len(insumos) == 2

    def test_dict_with_insumos_key_extends(self):
        insumos: list = []
        _ingest_insumos({"insumos": [{"id": "x"}]}, insumos)
        assert insumos == [{"id": "x"}]

    def test_plain_dict_appends(self):
        insumos: list = []
        _ingest_insumos({"id": "z", "valor": 1}, insumos)
        assert insumos == [{"id": "z", "valor": 1}]

    def test_non_list_non_dict_does_nothing(self):
        insumos: list = []
        _ingest_insumos("string_data", insumos)
        assert insumos == []


# ---------------------------------------------------------------------------
# _load_insumos_subdir
# ---------------------------------------------------------------------------


class TestLoadInsumosSubdir:
    def test_loads_json_files(self, tmp_path):
        f = tmp_path / "item.json"
        f.write_text(json.dumps([{"id": "abc"}]), encoding="utf-8")
        insumos: list = []
        _load_insumos_subdir(tmp_path, insumos)
        assert insumos == [{"id": "abc"}]

    def test_ignores_invalid_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not-json", encoding="utf-8")
        insumos: list = []
        _load_insumos_subdir(tmp_path, insumos)  # should not raise
        assert insumos == []

    def test_empty_dir(self, tmp_path):
        insumos: list = []
        _load_insumos_subdir(tmp_path, insumos)
        assert insumos == []


# ---------------------------------------------------------------------------
# _dedup_insumos
# ---------------------------------------------------------------------------


class TestDedupInsumos:
    def test_deduplicates_by_id(self):
        items = [{"id": "x", "v": 1}, {"id": "x", "v": 2}, {"id": "y", "v": 3}]
        result = _dedup_insumos(items)
        assert len(result) == 2
        assert result[0]["v"] == 1

    def test_deduplicates_by_codigo(self):
        items = [{"codigo": "a"}, {"codigo": "a"}, {"codigo": "b"}]
        result = _dedup_insumos(items)
        assert len(result) == 2

    def test_items_without_id_or_codigo_are_dropped(self):
        items = [{"nome": "foo"}, {"nome": "bar"}]
        result = _dedup_insumos(items)
        assert result == []


# ---------------------------------------------------------------------------
# _append_png_gallery
# ---------------------------------------------------------------------------


class TestAppendPngGallery:
    def test_empty_list_returns_unchanged(self):
        md = "# Título\n\nConteúdo."
        result = _append_png_gallery(md, [])
        assert result == md

    def test_non_empty_adds_gallery_section(self):
        md = "# Relatório"
        result = _append_png_gallery(md, ["chart_b.png", "chart_a.png"])
        assert "## Graficos Gerados" in result
        # Files are sorted
        assert result.index("chart_a.png") < result.index("chart_b.png")
        assert "![chart_a.png](chart_a.png)" in result
        assert "![chart_b.png](chart_b.png)" in result

    def test_result_ends_with_newline(self):
        result = _append_png_gallery("text", ["x.png"])
        assert result.endswith("\n")

    def test_single_file(self):
        result = _append_png_gallery("content", ["only.png"])
        assert "### only.png" in result
        assert "![only.png](only.png)" in result


# ---------------------------------------------------------------------------
# _load_output_image_bytes
# ---------------------------------------------------------------------------


class TestLoadOutputImageBytes:
    def test_returns_bytes_on_success(self):
        project = MagicMock()
        project.load_output_file.return_value = b"PNG"
        result = _load_output_image_bytes(project, "v1", "chart.png")
        assert result == b"PNG"
        project.load_output_file.assert_called_once_with("v1", "chart.png")

    def test_returns_none_on_exception(self):
        project = MagicMock()
        project.load_output_file.side_effect = FileNotFoundError("missing")
        result = _load_output_image_bytes(project, "v1", "missing.png")
        assert result is None

    def test_returns_none_on_generic_exception(self):
        project = MagicMock()
        project.load_output_file.side_effect = RuntimeError("boom")
        result = _load_output_image_bytes(project, "v1", "file.png")
        assert result is None


# ---------------------------------------------------------------------------
# _save_memorial_bdi_files
# ---------------------------------------------------------------------------


class TestSaveMemorialBdiFiles:
    def test_no_memorial_returns_early(self):
        result = SimpleNamespace(memorial_bdi_json=None)
        project = MagicMock()
        _save_memorial_bdi_files(result, project, "v1", True, True)
        project.save_intermediate_file.assert_not_called()
        project.save_output_file.assert_not_called()

    def test_saves_intermediate_json(self):
        memorial_dict = {
            "meta": {"projeto": "Test"},
            "itens": [],
        }
        memorial_bytes = json.dumps(memorial_dict).encode("utf-8")
        result = SimpleNamespace(memorial_bdi_json=memorial_bytes)
        project = MagicMock()
        with patch(
            "concilium.application.runtime.deliverables.side_effects.render_memorial_bdi_markdown",
            return_value="# Markdown",
        ):
            _save_memorial_bdi_files(result, project, "v1", gerar_md=False, gerar_pdf=False)
        project.save_intermediate_file.assert_called_once_with("memorial_bdi.json", memorial_bytes, "v1")

    def test_saves_md_when_gerar_md_true(self):
        memorial_dict = {"meta": {"projeto": "Proj"}, "itens": []}
        memorial_bytes = json.dumps(memorial_dict).encode("utf-8")
        result = SimpleNamespace(memorial_bdi_json=memorial_bytes)
        project = MagicMock()
        with patch(
            "concilium.application.runtime.deliverables.side_effects.render_memorial_bdi_markdown",
            return_value="# MD content",
        ):
            _save_memorial_bdi_files(result, project, "v1", gerar_md=True, gerar_pdf=False)
        calls = [c[0] for c in project.save_output_file.call_args_list]
        # Should call save_output_file once with the md content
        assert any(b"# MD content" in c[0] for c in calls)

    def test_saves_pdf_when_gerar_pdf_true(self):
        memorial_dict = {"meta": {"projeto": "Proj"}, "itens": []}
        memorial_bytes = json.dumps(memorial_dict).encode("utf-8")
        result = SimpleNamespace(memorial_bdi_json=memorial_bytes)
        project = MagicMock()
        project.load_output_file.return_value = b"PNG"
        with (
            patch(
                "concilium.application.runtime.deliverables.side_effects.render_memorial_bdi_markdown",
                return_value="# MD",
            ),
            patch(
                "concilium.application.runtime.deliverables.side_effects.render_markdown_pdf",
                return_value=b"%PDF",
            ),
        ):
            _save_memorial_bdi_files(result, project, "v1", gerar_md=False, gerar_pdf=True)
        # pdf save_output_file should have been called with the pdf bytes
        calls = [c[0] for c in project.save_output_file.call_args_list]
        assert any(c[0] == b"%PDF" for c in calls)

    def test_pdf_not_saved_when_render_returns_none(self):
        memorial_dict = {"meta": {"projeto": "Proj"}, "itens": []}
        memorial_bytes = json.dumps(memorial_dict).encode("utf-8")
        result = SimpleNamespace(memorial_bdi_json=memorial_bytes)
        project = MagicMock()
        with (
            patch(
                "concilium.application.runtime.deliverables.side_effects.render_memorial_bdi_markdown",
                return_value="# MD",
            ),
            patch(
                "concilium.application.runtime.deliverables.side_effects.render_markdown_pdf",
                return_value=None,
            ),
        ):
            _save_memorial_bdi_files(result, project, "v1", gerar_md=False, gerar_pdf=True)
        # save_output_file should not be called (no pdf bytes)
        project.save_output_file.assert_not_called()

    def test_exception_swallowed(self):
        result = SimpleNamespace(memorial_bdi_json=b"not valid json")
        project = MagicMock()
        # Should not raise even with invalid json
        _save_memorial_bdi_files(result, project, "v1", gerar_md=True, gerar_pdf=False)


# ---------------------------------------------------------------------------
# _save_relatorio_graficos_files
# ---------------------------------------------------------------------------


class TestSaveRelatorioGraficosFiles:
    def test_returns_empty_when_gerar_md_and_gerar_pdf_both_false(self):
        result = _save_relatorio_graficos_files({}, None, MagicMock(), "v1", gerar_md=False, gerar_pdf=False)
        assert result == []

    def test_returns_empty_when_gerar_pngs_false(self):
        result = _save_relatorio_graficos_files(
            {}, None, MagicMock(), "v1", gerar_md=True, gerar_pdf=False, gerar_pngs=False
        )
        assert result == []

    def test_returns_empty_when_no_graficos_and_no_canonical(self):
        result = _save_relatorio_graficos_files({}, None, MagicMock(), "v1", gerar_md=True, gerar_pdf=False)
        assert result == []

    def test_saves_pngs_and_returns_sorted_filenames(self):
        project = MagicMock()
        rel_dict = {"GRAFICOS": {"chart": {}}}
        with patch(
            "concilium.application.runtime.deliverables.side_effects.build_visualization_png_files",
            return_value={"b.png": b"PNG_B", "a.png": b"PNG_A"},
        ):
            result = _save_relatorio_graficos_files(rel_dict, None, project, "v1", gerar_md=True, gerar_pdf=False)
        assert result == ["a.png", "b.png"]
        # Both files saved
        assert project.save_output_file.call_count == 2

    def test_returns_empty_when_build_raises(self):
        rel_dict = {"GRAFICOS": {"chart": {}}}
        with patch(
            "concilium.application.runtime.deliverables.side_effects.build_visualization_png_files",
            side_effect=RuntimeError("render failed"),
        ):
            result = _save_relatorio_graficos_files(rel_dict, None, MagicMock(), "v1", gerar_md=True, gerar_pdf=False)
        assert result == []

    def test_returns_empty_when_build_returns_empty(self):
        rel_dict = {"GRAFICOS": {"chart": {}}}
        with patch(
            "concilium.application.runtime.deliverables.side_effects.build_visualization_png_files",
            return_value={},
        ):
            result = _save_relatorio_graficos_files(rel_dict, None, MagicMock(), "v1", gerar_md=True, gerar_pdf=False)
        assert result == []

    def test_uses_canonical_when_provided(self):
        canonical = MagicMock()
        project = MagicMock()
        with patch(
            "concilium.application.runtime.deliverables.side_effects.build_visualization_png_files",
            return_value={"c.png": b"data"},
        ) as mock_build:
            _save_relatorio_graficos_files({}, canonical, project, "v1", gerar_md=True, gerar_pdf=False)
            mock_build.assert_called_once_with({}, canonical=canonical)


# ---------------------------------------------------------------------------
# _handle_skill_09_side_effects
# ---------------------------------------------------------------------------


class TestHandleSkill09SideEffects:
    def _make_result(self, **kwargs):
        defaults = {
            "relatorio": None,
            "excel_bytes": None,
            "memorial_bdi_json": None,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_saves_xlsx_when_flag_true(self):
        result = self._make_result(excel_bytes=b"XLSX")
        project = MagicMock()
        outputs_cfg = {"resultado_xlsx": True}
        with (
            patch("concilium.application.runtime.deliverables.side_effects._save_memorial_bdi_files"),
            patch("concilium.application.runtime.deliverables.side_effects._save_relatorio_files"),
        ):
            _handle_skill_09_side_effects(result, project, "v1", outputs_cfg)
        project.save_output_file.assert_called_once_with(b"XLSX", "v1", "resultado_planejamento.xlsx")

    def test_does_not_save_xlsx_when_flag_false(self):
        result = self._make_result(excel_bytes=b"XLSX")
        project = MagicMock()
        outputs_cfg = {"resultado_xlsx": False}
        with (
            patch("concilium.application.runtime.deliverables.side_effects._save_memorial_bdi_files"),
            patch("concilium.application.runtime.deliverables.side_effects._save_relatorio_files"),
        ):
            _handle_skill_09_side_effects(result, project, "v1", outputs_cfg)
        project.save_output_file.assert_not_called()

    def test_does_not_save_xlsx_when_bytes_none(self):
        result = self._make_result(excel_bytes=None)
        project = MagicMock()
        outputs_cfg = {"resultado_xlsx": True}
        with (
            patch("concilium.application.runtime.deliverables.side_effects._save_memorial_bdi_files"),
            patch("concilium.application.runtime.deliverables.side_effects._save_relatorio_files"),
        ):
            _handle_skill_09_side_effects(result, project, "v1", outputs_cfg)
        project.save_output_file.assert_not_called()

    def test_saves_relatorio_json_when_relatorio_present(self):
        relatorio = {"meta": {"projeto": "Test"}, "custos": {}}
        result = self._make_result(relatorio=relatorio)
        project = MagicMock()
        with (
            patch("concilium.application.runtime.deliverables.side_effects._save_memorial_bdi_files"),
            patch("concilium.application.runtime.deliverables.side_effects._save_relatorio_files"),
        ):
            _handle_skill_09_side_effects(result, project, "v1", {})
        project.save_intermediate_file.assert_called_once()
        args = project.save_intermediate_file.call_args[0]
        assert args[0] == "relatorio.json"

    def test_no_relatorio_json_saved_when_none(self):
        result = self._make_result(relatorio=None)
        project = MagicMock()
        with (
            patch("concilium.application.runtime.deliverables.side_effects._save_memorial_bdi_files"),
            patch("concilium.application.runtime.deliverables.side_effects._save_relatorio_files"),
        ):
            _handle_skill_09_side_effects(result, project, "v1", {})
        project.save_intermediate_file.assert_not_called()

    def test_uses_cronograma_xlsx_fallback_key(self):
        result = self._make_result(excel_bytes=b"XLSX")
        project = MagicMock()
        # Should use cronograma_xlsx if resultado_xlsx not present
        outputs_cfg = {"cronograma_xlsx": True}
        with (
            patch("concilium.application.runtime.deliverables.side_effects._save_memorial_bdi_files"),
            patch("concilium.application.runtime.deliverables.side_effects._save_relatorio_files"),
        ):
            _handle_skill_09_side_effects(result, project, "v1", outputs_cfg)
        project.save_output_file.assert_called_once()

    def test_defaults_xlsx_to_true_when_key_absent(self):
        result = self._make_result(excel_bytes=b"XLSX")
        project = MagicMock()
        with (
            patch("concilium.application.runtime.deliverables.side_effects._save_memorial_bdi_files"),
            patch("concilium.application.runtime.deliverables.side_effects._save_relatorio_files"),
        ):
            _handle_skill_09_side_effects(result, project, "v1", {})
        project.save_output_file.assert_called_once()


# ---------------------------------------------------------------------------
# _handle_skill_04_side_effects
# ---------------------------------------------------------------------------


class TestHandleSkill04SideEffects:
    def test_no_op_when_cronograma_none(self):
        canonical = SimpleNamespace(cronograma=None)
        result = SimpleNamespace(canonical=canonical)
        project = MagicMock()
        _handle_skill_04_side_effects(result, project, "v1")
        project.save_intermediate_file.assert_not_called()

    def test_no_op_when_algorithm_is_manual_allocation(self):
        cronograma = SimpleNamespace(algorithm="manual_allocation")
        canonical = SimpleNamespace(cronograma=cronograma)
        result = SimpleNamespace(canonical=canonical)
        project = MagicMock()
        _handle_skill_04_side_effects(result, project, "v1")
        project.save_intermediate_file.assert_not_called()

    def test_saves_schedules_json_for_real_algorithm(self):
        sa = SimpleNamespace(
            activity_id="act-01",
            start_week=1,
            end_week=3,
            duration_weeks=3,
            data_inicio=None,
            data_fim=None,
        )
        cronograma = SimpleNamespace(
            algorithm="cpsat",
            quality_score=0.95,
            makespan_weeks=10,
            is_feasible=True,
            was_relaxed=False,
            scheduled_activities=[sa],
        )
        canonical = SimpleNamespace(cronograma=cronograma)
        result = SimpleNamespace(canonical=canonical)
        project = MagicMock()
        _handle_skill_04_side_effects(result, project, "v1")
        project.save_intermediate_file.assert_called_once()
        fname, json_str, v = project.save_intermediate_file.call_args[0]
        assert fname == "schedules_weekly.json"
        assert v == "v1"
        data = json.loads(json_str)
        assert data["algorithm"] == "cpsat"
        assert len(data["activities"]) == 1
        assert data["activities"][0]["activity_id"] == "act-01"

    def test_saves_schedules_with_dates(self):
        from datetime import date

        sa = SimpleNamespace(
            activity_id="act-02",
            start_week=5,
            end_week=8,
            duration_weeks=4,
            data_inicio=date(2026, 6, 1),
            data_fim=date(2026, 6, 28),
        )
        cronograma = SimpleNamespace(
            algorithm="milp",
            quality_score=0.80,
            makespan_weeks=8,
            is_feasible=True,
            was_relaxed=True,
            scheduled_activities=[sa],
        )
        canonical = SimpleNamespace(cronograma=cronograma)
        result = SimpleNamespace(canonical=canonical)
        project = MagicMock()
        _handle_skill_04_side_effects(result, project, "v1")
        _, json_str, _ = project.save_intermediate_file.call_args[0]
        data = json.loads(json_str)
        assert data["activities"][0]["data_inicio"] == "2026-06-01"
        assert data["activities"][0]["data_fim"] == "2026-06-28"


# ---------------------------------------------------------------------------
# _persist_typed_artifacts
# ---------------------------------------------------------------------------


class TestPersistTypedArtifacts:
    def test_no_op_when_artifacts_none(self):
        result = SimpleNamespace(artifacts=None)
        project = MagicMock()
        _persist_typed_artifacts(result, project, "v1")
        project.version_path.assert_not_called()

    def test_no_op_when_artifacts_empty_list(self):
        result = SimpleNamespace(artifacts=[])
        project = MagicMock()
        _persist_typed_artifacts(result, project, "v1")
        project.version_path.assert_not_called()

    def test_saves_artifact_with_model_dump_json(self, tmp_path):
        payload = MagicMock()
        payload.model_dump_json.return_value = '{"key": "value"}'
        meta = SimpleNamespace(artifact_id="art-001")
        artifact = SimpleNamespace(payload=payload, meta=meta)
        result = SimpleNamespace(artifacts=[artifact])

        project = MagicMock()
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()
        project.version_path.return_value = tmp_path

        mock_store = MagicMock()
        mock_store.root = artifacts_dir
        mock_store_cls = MagicMock(return_value=mock_store)

        with patch.dict(
            "sys.modules",
            {"concilium.infrastructure.storage.artifact_store": MagicMock(FileSystemArtifactStore=mock_store_cls)},
        ):
            # We need the actual write_text to work, so set up real path
            mock_store.root = artifacts_dir
            _persist_typed_artifacts(result, project, "v1")

        project.version_path.assert_called_once_with("v1")

    def test_saves_artifact_with_plain_payload(self, tmp_path):
        payload = {"plain": "dict"}
        meta = SimpleNamespace(artifact_id="art-002")
        artifact = SimpleNamespace(payload=payload, meta=meta)
        result = SimpleNamespace(artifacts=[artifact])

        project = MagicMock()
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()
        project.version_path.return_value = tmp_path

        mock_store = MagicMock()
        mock_store.root = artifacts_dir

        mock_store_cls = MagicMock(return_value=mock_store)

        with patch.dict(
            "sys.modules",
            {"concilium.infrastructure.storage.artifact_store": MagicMock(FileSystemArtifactStore=mock_store_cls)},
        ):
            mock_store.root = artifacts_dir
            _persist_typed_artifacts(result, project, "v1")

        project.version_path.assert_called_once_with("v1")

    def test_exception_swallowed(self):
        """Even if FileSystemArtifactStore raises, no exception propagates."""
        meta = SimpleNamespace(artifact_id="art-003")
        artifact = SimpleNamespace(payload=None, meta=meta)
        result = SimpleNamespace(artifacts=[artifact])
        project = MagicMock()
        project.version_path.side_effect = RuntimeError("storage unavailable")
        # Should not raise
        _persist_typed_artifacts(result, project, "v1")


# ---------------------------------------------------------------------------
# _save_relatorio_files
# ---------------------------------------------------------------------------


class TestSaveRelatorioFiles:
    def test_no_op_when_no_relatorio(self):
        result = SimpleNamespace(relatorio=None)
        project = MagicMock()
        _save_relatorio_files(result, project, "v1", gerar_md=True, gerar_pdf=False)
        project.save_output_file.assert_not_called()

    def test_no_op_when_both_flags_false(self):
        result = SimpleNamespace(relatorio={"meta": {}}, canonical=None)
        project = MagicMock()
        _save_relatorio_files(result, project, "v1", gerar_md=False, gerar_pdf=False)
        project.save_output_file.assert_not_called()

    def test_saves_md_when_flag_true(self):
        result = SimpleNamespace(relatorio={"meta": {"projeto": "Test"}}, canonical=None)
        project = MagicMock()
        project.load_canonical.side_effect = FileNotFoundError

        with (
            patch(
                "concilium.application.runtime.deliverables.side_effects.render_financial_report_markdown",
                return_value="# Relatorio",
            ),
            patch(
                "concilium.application.runtime.deliverables.side_effects._save_relatorio_graficos_files",
                return_value=[],
            ),
            patch(
                "concilium.application.runtime.deliverables.side_effects.render_resumo_executivo",
                return_value="# Resumo",
            ),
        ):
            _save_relatorio_files(result, project, "v1", gerar_md=True, gerar_pdf=False)

        calls_args = [c[0] for c in project.save_output_file.call_args_list]
        fnames = [c[2] for c in calls_args]
        assert "relatorio.md" in fnames

    def test_saves_pdf_when_flag_true(self):
        result = SimpleNamespace(relatorio={"meta": {"projeto": "Proj"}}, canonical=None)
        project = MagicMock()
        project.load_canonical.side_effect = FileNotFoundError

        with (
            patch(
                "concilium.application.runtime.deliverables.side_effects.render_financial_report_markdown",
                return_value="# Relatorio",
            ),
            patch(
                "concilium.application.runtime.deliverables.side_effects._save_relatorio_graficos_files",
                return_value=[],
            ),
            patch(
                "concilium.application.runtime.deliverables.side_effects.render_financial_report_pdf",
                return_value=b"%PDF",
            ),
        ):
            _save_relatorio_files(result, project, "v1", gerar_md=False, gerar_pdf=True)

        calls_args = [c[0] for c in project.save_output_file.call_args_list]
        fnames = [c[2] for c in calls_args]
        assert "relatorio.pdf" in fnames

    def test_uses_canonical_from_result_when_present(self):
        canonical = MagicMock()
        result = SimpleNamespace(relatorio={"meta": {}}, canonical=canonical)
        project = MagicMock()

        with (
            patch(
                "concilium.application.runtime.deliverables.side_effects.render_financial_report_markdown",
                return_value="# MD",
            ) as mock_render,
            patch(
                "concilium.application.runtime.deliverables.side_effects._save_relatorio_graficos_files",
                return_value=[],
            ),
            patch(
                "concilium.application.runtime.deliverables.side_effects.render_resumo_executivo",
                return_value="# Resumo",
            ),
        ):
            _save_relatorio_files(result, project, "v1", gerar_md=True, gerar_pdf=False)

        # load_canonical should NOT be called if canonical is already on result
        project.load_canonical.assert_not_called()

    def test_loads_canonical_from_project_when_not_on_result(self):
        canonical = MagicMock()
        result = SimpleNamespace(relatorio={"meta": {}}, canonical=None)
        project = MagicMock()
        project.load_canonical.return_value = canonical

        with (
            patch(
                "concilium.application.runtime.deliverables.side_effects.render_financial_report_markdown",
                return_value="# MD",
            ),
            patch(
                "concilium.application.runtime.deliverables.side_effects._save_relatorio_graficos_files",
                return_value=[],
            ),
            patch(
                "concilium.application.runtime.deliverables.side_effects.render_resumo_executivo",
                return_value="# Resumo",
            ),
        ):
            _save_relatorio_files(result, project, "v1", gerar_md=True, gerar_pdf=False)

        project.load_canonical.assert_called_once_with("v1")
