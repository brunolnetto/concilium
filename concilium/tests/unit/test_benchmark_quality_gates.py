from __future__ import annotations

from types import SimpleNamespace

from concilium.application.benchmarks.report_builder import BenchmarkReportBuilder
from concilium.application.benchmarks.spec_loader import ProjectSpec


def _fake_projection(**kwargs):
    defaults = {
        "ferramenta": {},
        "ponto_equilibrio_ferramenta": None,
        "ferramenta_breakdown_direto": None,
        "ferramenta_breakdown_indireto": None,
        "actionable_insights": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestBenchmarkQualityGates:
    def test_classify_delta_uses_expected_thresholds(self):
        builder = BenchmarkReportBuilder()

        assert builder._classify_delta(2.5) == ("IDEAL", "S0")
        assert builder._classify_delta(10.0) == ("ATENCAO", "S1")
        assert builder._classify_delta(20.0) == ("PREOCUPANTE", "S2")
        assert builder._classify_delta(35.0) == ("CRITICO", "S3")

    def test_build_emits_quality_gates_and_action_report(self, monkeypatch):
        builder = BenchmarkReportBuilder()
        spec = ProjectSpec(nome="Projeto Teste", slug="proj-teste", contexto_id="ctx")
        ref = {
            "resultado": {
                "benchmark_confronto_referencia": {
                    "custo_direto": 100.0,
                    "custo_indireto": 20.0,
                    "custo_total": 120.0,
                    "preco_venda": 130.0,
                }
            }
        }

        fake_projection = _fake_projection(
            ferramenta={
                "custo_direto": 120.0,
                "custo_direto_catalogo": 95.0,
                "custo_indireto": 22.0,
                "custo_total": 142.0,
                "preco_venda": 150.0,
            }
        )

        monkeypatch.setattr(
            "concilium.application.benchmarks.report_builder.BenchmarkProjection.from_canonical",
            lambda canonical: fake_projection,
        )

        report = builder.build(spec=spec, version="v1", results_log=[], ref=ref, canonical=object())

        assert report["status_final"] == "BLOQUEADO_COM_INVESTIGACAO"
        assert report["quality_gates"]["worst_severity"] == "S2"
        assert report["quality_gates"]["critical_metric_over_10pct"] is True
        assert len(report["action_report"]) >= 3

        metrics = {item["metric"] for item in report["action_report"]}
        assert {"custo_direto", "custo_indireto", "preco_venda"}.issubset(metrics)

        custo_direto_item = next(item for item in report["action_report"] if item["metric"] == "custo_direto")
        assert custo_direto_item["classe"] in ("ATENCAO", "PREOCUPANTE")
        assert custo_direto_item["severidade"] in ("S1", "S2")
        assert "consolidacao" in custo_direto_item["fase"]
        assert custo_direto_item["causa_categoria"] == "DERIVACAO_PIPELINE"

        preco_item = next(item for item in report["action_report"] if item["metric"] == "preco_venda")
        assert preco_item["causa_categoria"] == "PARAMETRIZACAO_BDI"
        assert preco_item["owner"] == "engenharia-bdi"
