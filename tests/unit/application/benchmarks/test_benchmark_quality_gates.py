from __future__ import annotations

from types import SimpleNamespace

from concilium.application.benchmarks.report.report_builder import BenchmarkReportBuilder
from concilium.application.benchmarks.spec.spec_loader import ProjectSpec


def _fake_projection(**kwargs):
    defaults = {
        "ferramenta": {},
        "preco_venda_fonte": None,
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

        # custo_direto is now PU×Q (comparable to reference); instancial is diagnostic only
        fake_projection = _fake_projection(
            ferramenta={
                "custo_direto": 120.0,  # PU×Q — gated against reference
                "custo_execucao_pool": 55.0,  # pool instancial — diagnostic
                "custo_indireto": 22.0,
                "custo_total": 142.0,
                "preco_venda": 150.0,
            }
        )

        monkeypatch.setattr(
            "concilium.application.benchmarks.report.report_builder.BenchmarkProjection.from_canonical",
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
        assert custo_direto_item["causa_categoria"] == "CATALOGO"

        preco_item = next(item for item in report["action_report"] if item["metric"] == "preco_venda")
        assert preco_item["causa_categoria"] == "PARAMETRIZACAO_BDI"
        assert preco_item["owner"] == "engenharia-bdi"

    def test_build_prefers_inference_pack_reference_projection(self, monkeypatch):
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
                "custo_direto": 100.0,  # PU×Q
                "custo_execucao_pool": 45.0,  # pool instancial (diagnostic)
                "custo_indireto": 20.0,
                "custo_total": 120.0,
                "preco_venda": 130.0,
            }
        )
        monkeypatch.setattr(
            "concilium.application.benchmarks.report.report_builder.BenchmarkProjection.from_canonical",
            lambda canonical: fake_projection,
        )

        def _unexpected_extract(_):
            raise AssertionError("_extract_referencia_confronto should not run when inference_pack is provided")

        monkeypatch.setattr(
            "concilium.application.benchmarks.report.report_builder.BenchmarkReportBuilder._extract_referencia_confronto",
            staticmethod(_unexpected_extract),
        )

        inference_pack = SimpleNamespace(
            reference_projection={
                "custo_direto": 100.0,
                "custo_indireto": 20.0,
                "custo_total": 120.0,
                "preco_venda": 130.0,
            }
        )

        report = builder.build(
            spec=spec,
            version="v1",
            results_log=[],
            ref=ref,
            canonical=object(),
            inference_pack=inference_pack,
        )

        assert report["confronto"]["referencia"] == inference_pack.reference_projection

def test_report_without_reference_is_not_evaluated(monkeypatch):
    builder = BenchmarkReportBuilder()
    spec = ProjectSpec(nome="Projeto Teste", slug="proj-teste", contexto_id="ctx")
    projection = _fake_projection(
        ferramenta={
            "custo_direto": 100.0,
            "custo_indireto": 20.0,
            "preco_venda": 130.0,
        }
    )
    monkeypatch.setattr(
        "concilium.application.benchmarks.report.report_builder.BenchmarkProjection.from_canonical",
        lambda canonical: projection,
    )

    report = builder.build(
        spec=spec, version="v1", results_log=[], ref=None, canonical=object()
    )

    assert report["referencia_disponivel"] is False
    assert report["quality_gates"]["decision"] == "NOT_EVALUATED"
    assert report["quality_gates"]["reason_code"] == "REFERENCE_PROJECTION_UNAVAILABLE"
    assert report["status_final"] == "NOT_EVALUATED"


def test_report_without_usable_reference_projection_is_not_evaluated(monkeypatch):
    builder = BenchmarkReportBuilder()
    spec = ProjectSpec(nome="Projeto Teste", slug="proj-teste", contexto_id="ctx")
    projection = _fake_projection(
        ferramenta={
            "custo_direto": 100.0,
            "custo_indireto": 20.0,
            "preco_venda": 130.0,
        }
    )
    monkeypatch.setattr(
        "concilium.application.benchmarks.report.report_builder.BenchmarkProjection.from_canonical",
        lambda canonical: projection,
    )
    monkeypatch.setattr(
        "concilium.application.benchmarks.report.report_builder.BenchmarkReportBuilder._extract_referencia_confronto",
        staticmethod(lambda _ref: None),
    )

    report = builder.build(
        spec=spec, version="v1", results_log=[], ref={"source": "reference"}, canonical=object()
    )

    assert report["quality_gates"]["decision"] == "NOT_EVALUATED"
    assert report["quality_gates"]["reason_code"] == "REFERENCE_PROJECTION_UNAVAILABLE"
    assert "not evaluated" in report["quality_gates"]["reason"].lower()


def test_report_missing_required_comparable_metric_is_not_evaluated(monkeypatch):
    builder = BenchmarkReportBuilder()
    spec = ProjectSpec(nome="Projeto Teste", slug="proj-teste", contexto_id="ctx")
    projection = _fake_projection(
        ferramenta={
            "custo_direto": 100.0,
            "custo_indireto": 20.0,
            "preco_venda": 130.0,
        }
    )
    monkeypatch.setattr(
        "concilium.application.benchmarks.report.report_builder.BenchmarkProjection.from_canonical",
        lambda canonical: projection,
    )
    monkeypatch.setattr(
        "concilium.application.benchmarks.report.report_builder.BenchmarkReportBuilder._extract_referencia_confronto",
        staticmethod(lambda _ref: {"custo_direto": 100.0, "custo_indireto": 20.0}),
    )

    report = builder.build(
        spec=spec, version="v1", results_log=[], ref={"source": "reference"}, canonical=object()
    )

    assert report["quality_gates"]["decision"] == "NOT_EVALUATED"
    assert report["quality_gates"]["reason_code"] == "INSUFFICIENT_COMPARABLE_METRICS"
    assert report["quality_gates"]["missing_metrics"] == ["preco_venda"]
    assert report["status_final"] == "NOT_EVALUATED"


def test_complete_comparable_metrics_preserve_approval_decision(monkeypatch):
    builder = BenchmarkReportBuilder()
    spec = ProjectSpec(nome="Projeto Teste", slug="proj-teste", contexto_id="ctx")
    reference = {
        "custo_direto": 100.0,
        "custo_indireto": 20.0,
        "preco_venda": 130.0,
    }
    projection = _fake_projection(ferramenta=dict(reference))
    monkeypatch.setattr(
        "concilium.application.benchmarks.report.report_builder.BenchmarkProjection.from_canonical",
        lambda canonical: projection,
    )
    monkeypatch.setattr(
        "concilium.application.benchmarks.report.report_builder.BenchmarkReportBuilder._extract_referencia_confronto",
        staticmethod(lambda _ref: reference),
    )

    report = builder.build(
        spec=spec, version="v1", results_log=[], ref={"source": "reference"}, canonical=object()
    )

    assert set(report["confronto"]["deltas"]) == {"custo_direto", "custo_indireto", "preco_venda"}
    assert report["quality_gates"]["decision"] == "APROVADO"
    assert report["status_final"] == "APROVADO"

def test_zero_reference_denominator_is_not_evaluated(monkeypatch):
    builder = BenchmarkReportBuilder()
    spec = ProjectSpec(nome="Projeto Teste", slug="proj-teste", contexto_id="ctx")
    reference = {
        "custo_direto": 0.0,
        "custo_indireto": 20.0,
        "preco_venda": 130.0,
    }
    projection = _fake_projection(
        ferramenta={
            "custo_direto": 15.0,
            "custo_indireto": 20.0,
            "preco_venda": 130.0,
        }
    )
    monkeypatch.setattr(
        "concilium.application.benchmarks.report.report_builder.BenchmarkProjection.from_canonical",
        lambda canonical: projection,
    )
    monkeypatch.setattr(
        "concilium.application.benchmarks.report.report_builder.BenchmarkReportBuilder._extract_referencia_confronto",
        staticmethod(lambda _ref: reference),
    )

    report = builder.build(
        spec=spec, version="v1", results_log=[], ref={"source": "reference"}, canonical=object()
    )

    assert report["quality_gates"]["decision"] == "NOT_EVALUATED"
    assert report["quality_gates"]["reason_code"] == "INSUFFICIENT_COMPARABLE_METRICS"
    assert report["quality_gates"]["missing_metrics"] == ["custo_direto"]


def test_non_finite_reference_metric_is_not_evaluated(monkeypatch):
    builder = BenchmarkReportBuilder()
    spec = ProjectSpec(nome="Projeto Teste", slug="proj-teste", contexto_id="ctx")
    reference = {
        "custo_direto": float("nan"),
        "custo_indireto": 20.0,
        "preco_venda": 130.0,
    }
    projection = _fake_projection(
        ferramenta={
            "custo_direto": 100.0,
            "custo_indireto": 20.0,
            "preco_venda": 130.0,
        }
    )
    monkeypatch.setattr(
        "concilium.application.benchmarks.report.report_builder.BenchmarkProjection.from_canonical",
        lambda canonical: projection,
    )
    monkeypatch.setattr(
        "concilium.application.benchmarks.report.report_builder.BenchmarkReportBuilder._extract_referencia_confronto",
        staticmethod(lambda _ref: reference),
    )

    report = builder.build(
        spec=spec, version="v1", results_log=[], ref={"source": "reference"}, canonical=object()
    )

    assert "custo_direto" not in report["confronto"]["deltas"]
    assert report["quality_gates"]["decision"] == "NOT_EVALUATED"
    assert report["quality_gates"]["missing_metrics"] == ["custo_direto"]
