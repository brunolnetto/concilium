"""Tests to restore coverage from overwritten test_small_gaps_batch3.py:
flat_version_store, consolidation, engine_refs, memorial_bdi_markdown, mcp/server."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ─── infrastructure/storage/flat_version_store.py ─────────────────────────────

class TestFlatVersionStore:
    def _make_store(self, tmp_path):
        from concilium.infrastructure.storage.flat_version_store import FlatVersionStore
        proj_mock = MagicMock()
        proj_mock.meta = {
            "contexto_id": "ctx-1",
            "snapshot_catalogo_id": "cat-v2",
            "snapshot_perfil_id": "perf-1",
        }
        ver_path = tmp_path / "v1"
        ver_path.mkdir()
        proj_mock.version_path.return_value = ver_path
        proj_mock.load_canonical.return_value = None
        return FlatVersionStore(proj_mock, "v1")

    def test_plano_id(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.plano_id == "v1"

    def test_meta(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.meta["plano_id"] == "v1"

    def test_escopo_store_meta_with_snapshots(self, tmp_path):
        store = self._make_store(tmp_path)
        meta = store.escopo_store.meta
        assert meta["snapshot_catalogo_id"] == "cat-v2"
        assert meta["snapshot_perfil_id"] == "perf-1"

    def test_log_and_read_invocations(self, tmp_path):
        store = self._make_store(tmp_path)
        store.log_invocation({"skill": "01-escopo-e-eap", "status": "OK"})
        store.log_invocation({"skill": "02-prod", "status": "ERRO"})
        entries = store.read_invocations()
        assert len(entries) == 2
        assert entries[0]["skill"] == "01-escopo-e-eap"

    def test_read_invocations_empty(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.read_invocations() == []

    def test_read_invocations_skips_invalid_json(self, tmp_path):
        store = self._make_store(tmp_path)
        log_file = store.root / store.INVOCATIONS_LOG
        log_file.write_text('{"ok": true}\nBAD JSON\n{"second": true}\n')
        entries = store.read_invocations()
        assert len(entries) == 2


# ─── infrastructure/catalog/extraction/consolidation.py ───────────────────────

class TestConsolidation:
    def test_consolidate_reference_no_project_returns_ref(self, tmp_path):
        from concilium.infrastructure.catalog.extraction.consolidation import consolidate_reference
        bench_dir = tmp_path / "benchmarks" / "data" / "AGIS"
        bench_dir.mkdir(parents=True)
        (bench_dir / "referencia.json").write_text('{"slug": "AGIS", "projeto": "Proj Test"}')
        (tmp_path / "projetos").mkdir()
        result = consolidate_reference("AGIS", root=tmp_path)
        assert result["slug"] == "AGIS"

    def test_find_project_dir_not_found(self, tmp_path):
        from concilium.infrastructure.catalog.extraction.consolidation import _find_project_dir
        bench_dir = tmp_path / "benchmarks" / "data" / "AGIS"
        bench_dir.mkdir(parents=True)
        (bench_dir / "referencia.json").write_text('{"projeto": "Nonexistent"}')
        (tmp_path / "projetos").mkdir()
        result = _find_project_dir("AGIS", tmp_path)
        assert result is None

    def test_find_project_dir_no_project_name(self, tmp_path):
        from concilium.infrastructure.catalog.extraction.consolidation import _find_project_dir
        bench_dir = tmp_path / "benchmarks" / "data" / "AGIS"
        bench_dir.mkdir(parents=True)
        (bench_dir / "referencia.json").write_text('{}')
        result = _find_project_dir("AGIS", tmp_path)
        assert result is None


# ─── infrastructure/catalog/extraction/engine_refs.py ────────────────────────

class TestEngineRefs:
    def test_normalize_project_token(self):
        from concilium.infrastructure.catalog.extraction.engine_refs import _normalize_project_token
        assert _normalize_project_token("agis_calibrado") == "AGIS"

    def test_iter_benchmark_reports_empty(self, tmp_path):
        from concilium.infrastructure.catalog.extraction.engine_refs import iter_benchmark_reports
        result = iter_benchmark_reports(root=tmp_path)
        assert result == []

    def test_find_latest_project_not_found(self, tmp_path):
        from concilium.infrastructure.catalog.extraction.engine_refs import _find_latest_project_by_name
        (tmp_path / "projetos").mkdir()
        with pytest.raises(FileNotFoundError):
            _find_latest_project_by_name("Nonexistent", tmp_path / "projetos")

    def test_check_project_dir_non_dir(self, tmp_path):
        from concilium.infrastructure.catalog.extraction.engine_refs import _check_project_dir
        fake_file = tmp_path / "notadir.json"
        fake_file.write_text("{}")
        result = _check_project_dir(fake_file, "TARGET", None)
        assert result is None

    def test_check_project_dir_wrong_name(self, tmp_path):
        from concilium.infrastructure.catalog.extraction.engine_refs import _check_project_dir
        d = tmp_path / "proj"
        d.mkdir()
        (d / "meta.json").write_text('{"nome": "Other Project"}')
        result = _check_project_dir(d, "TARGET", None)
        assert result is None

    def test_check_project_dir_match(self, tmp_path):
        from concilium.infrastructure.catalog.extraction.engine_refs import _check_project_dir
        d = tmp_path / "proj"
        d.mkdir()
        (d / "meta.json").write_text('{"nome": "Target Project", "criado_em": "2026-01-01"}')
        result = _check_project_dir(d, "TARGET PROJECT", None)
        assert result is not None
        assert result[1] == d


# ─── application/runtime/deliverables/reports/memorial_bdi_markdown.py ────────

class TestMemorialBdiMarkdown:
    def test_render_with_decomposicao(self):
        from concilium.application.runtime.deliverables.reports.memorial_bdi_markdown import (
            render_memorial_bdi_markdown,
        )
        memorial = {
            "decomposicao_por_categoria": {
                "TERRA": {
                    "custo_direto_pct": 0.7, "overhead_ac_pct": 0.03, "overhead_df_pct": 0.01,
                    "overhead_r_pct": 0.01, "margem_l_pct": 0.10, "tributo_iss_pct": 0.02,
                    "tributo_cssl_pct": 0.01, "tributo_ir_pct": 0.01,
                }
            },
            "aplicacao_por_item": [],
        }
        result = render_memorial_bdi_markdown(memorial)
        assert "TERRA" in result or "Decomposicao" in result

    def test_render_without_decomposicao(self):
        from concilium.application.runtime.deliverables.reports.memorial_bdi_markdown import (
            render_memorial_bdi_markdown,
        )
        result = render_memorial_bdi_markdown({})
        assert isinstance(result, str)


# ─── presentation/mcp/server.py ───────────────────────────────────────────────

class TestMcpServer:
    def test_build_server_returns_fastmcp(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(tmp_path / "config"))
        (tmp_path / "config").mkdir()
        from concilium.presentation.mcp.server import build_server
        server = build_server()
        assert server is not None

    def test_patch_mcp_with_auth(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(tmp_path / "config"))
        (tmp_path / "config").mkdir()
        from concilium.presentation.mcp.server import _patch_mcp_with_auth
        from concilium.presentation.mcp.middleware import McpAuthMiddleware
        server = MagicMock()
        original_http = MagicMock(return_value=MagicMock())
        original_sse = MagicMock(return_value=MagicMock())
        server.streamable_http_app = original_http
        server.sse_app = original_sse
        _patch_mcp_with_auth(server)
        result = server.streamable_http_app()
        assert isinstance(result, McpAuthMiddleware)

    def test_main_config_not_found(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(tmp_path / "nonexistent"))
        from concilium.presentation.mcp.server import main
        with pytest.raises(RuntimeError, match="não encontrado"):
            main()

    def test_main_config_not_dir(self, monkeypatch, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")
        monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(config_file))
        from concilium.presentation.mcp.server import main
        with pytest.raises(RuntimeError, match="não é diretório"):
            main()


# ─── service_support.py (also covered in batch4, adding extra paths here) ─────

class TestServiceSupport:
    def test_deep_merge_nested(self):
        from concilium.application.services.service_support import deep_merge
        result = deep_merge({"a": {"x": 1, "y": 2}}, {"a": {"y": 99}})
        assert result["a"]["x"] == 1
        assert result["a"]["y"] == 99

    def test_build_summary_none_returns_empty(self):
        from concilium.application.services.service_support import build_summary
        assert build_summary(None) == {}


# ─── domain/validations/circular_deps.py ──────────────────────────────────────

class TestCircularDeps:
    def test_no_cycles_simple(self):
        from concilium.domain.validations.circular_deps import verificar_ciclos_cpu
        catalog = {"cpus": [{"codigo": "A", "composicao_itens": []}, {"codigo": "B", "composicao_itens": [], "cpu_referencia_id": "A"}]}
        assert verificar_ciclos_cpu(catalog) == []

    def test_cycle_detected(self):
        from concilium.domain.validations.circular_deps import verificar_ciclos_cpu
        catalog = {
            "cpus": [
                {"codigo": "A", "composicao_itens": [], "cpu_referencia_id": "B"},
                {"codigo": "B", "composicao_itens": [], "cpu_referencia_id": "A"},
            ]
        }
        errors = verificar_ciclos_cpu(catalog)
        assert len(errors) > 0

    def test_validar_sem_ciclos_raises(self):
        from concilium.domain.validations.circular_deps import validar_sem_ciclos
        catalog = {
            "cpus": [
                {"codigo": "A", "composicao_itens": [], "cpu_referencia_id": "B"},
                {"codigo": "B", "composicao_itens": [], "cpu_referencia_id": "A"},
            ]
        }
        with pytest.raises(ValueError):
            validar_sem_ciclos(catalog)
