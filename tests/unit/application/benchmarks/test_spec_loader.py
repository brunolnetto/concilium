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

    def test_load_spec_from_dict_repassa_logistica_consumiveis_para_cronograma(self, tmp_path):
        """ADR-151: `logistica_consumiveis` na referência (mesmo padrão já usado
        para `rcpsp_spec`) chega em `inputs_cronograma` — é assim que um benchmark
        declara o provisionamento externo conhecido de um material de projeto.
        Schema v1 (flat, sem 'spec') — não passa por `_unpack_v2_schema`."""
        from concilium.application.benchmarks.spec.spec_loader import load_spec_from_dict

        ref = self._make_ref()
        ref["logistica_consumiveis"] = {"MA-SOLO-ESCAVADO-3CAT": {"deficit_provisionado_externamente": 24721.17}}
        ref_file = tmp_path / "referencia.json"
        ref_file.write_text("{}", encoding="utf-8")
        spec = load_spec_from_dict(ref, ref_file)
        assert spec.inputs_cronograma["logistica_consumiveis"] == {
            "MA-SOLO-ESCAVADO-3CAT": {"deficit_provisionado_externamente": 24721.17}
        }

    def test_load_spec_from_dict_v2_schema_repassa_logistica_consumiveis(self, tmp_path):
        """ADR-151: mesmo repasse, mas para o schema v2 (meta+spec+resultado) — o
        formato real usado por AGIS. `_unpack_v2_schema` reconstrói o dict do zero
        e só propaga campos explicitamente mapeados (mesmo padrão de spec.rcpsp_spec
        → ref['rcpsp_spec']); spec.logistica_consumiveis precisa do mesmo tratamento."""
        from concilium.application.benchmarks.spec.spec_loader import load_spec_from_dict

        ref = {
            "id": "AGIS-TEST",
            "meta": {
                "projeto": "AGIS Test",
                "data_inicio": "2026-01-01",
                "data_termino": "2026-12-31",
                "contexto_id": "mendeslobo",
            },
            "spec": {
                "eap": [{"item_id": "eap-1", "cpu_id": "CPU-X", "quantitativo": 100.0}],
                "logistica_consumiveis": {
                    "MA-SOLO-ESCAVADO-3CAT": {"deficit_provisionado_externamente": 24721.17}
                },
            },
            "resultado": {},
        }
        ref_file = tmp_path / "referencia.json"
        ref_file.write_text("{}", encoding="utf-8")
        spec = load_spec_from_dict(ref, ref_file)
        assert spec.inputs_cronograma["logistica_consumiveis"] == {
            "MA-SOLO-ESCAVADO-3CAT": {"deficit_provisionado_externamente": 24721.17}
        }

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

