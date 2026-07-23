"""Tests for _project_service_helpers.py and spec_loader.py helpers."""

from __future__ import annotations

# ─── application/benchmarks/spec/spec_loader.py ───────────────────────────────


class TestSpecLoader:
    def _make_ref(self):
        return {
            "slug": "AGIS",
            "nome": "AGIS Test",
            "contexto_id": "mendeslobo",
            "projeto": "Test Project",
            "data_inicio": "2026-W01",
            "data_termino": "2026-W20",
        }

    def test_load_spec_from_json_minimal(self, tmp_path):
        from concilium.application.benchmarks.spec.spec_loader import load_spec_from_json

        ref_file = tmp_path / "referencia.json"
        import json

        ref = self._make_ref()
        ref_file.write_text(json.dumps(ref), encoding="utf-8")
        spec = load_spec_from_json(ref_file)
        assert spec is not None
        assert isinstance(spec.slug, str)

    def test_load_spec_from_dict(self, tmp_path):
        from concilium.application.benchmarks.spec.spec_loader import load_spec_from_dict

        ref = self._make_ref()
        ref_file = tmp_path / "referencia.json"
        ref_file.write_text("{}", encoding="utf-8")
        spec = load_spec_from_dict(ref, ref_file)
        assert spec is not None

    def test_benchmark_spec_loader_from_root(self, tmp_path):
        from concilium.application.benchmarks.spec.spec_loader import BenchmarkSpecLoader

        (tmp_path / "catalogos").mkdir()
        loader = BenchmarkSpecLoader(config_root=tmp_path)
        assert loader is not None

    def test_discover_benchmark_slugs(self, tmp_path):
        from concilium.application.benchmarks.execution.batch import discover_benchmark_slugs

        (tmp_path / "BENCH1").mkdir()
        (tmp_path / "BENCH1" / "referencia.json").write_text('{"slug": "bench1"}', encoding="utf-8")
        result = discover_benchmark_slugs(tmp_path)
        assert "BENCH1" in result

