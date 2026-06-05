from __future__ import annotations

from types import SimpleNamespace

from concilium.application.benchmarks.inference import BenchmarkInferenceService
from concilium.application.benchmarks.report_builder import BenchmarkReportBuilder
from concilium.application.benchmarks.spec_loader import ProjectSpec


def _fake_projection() -> SimpleNamespace:
    return SimpleNamespace(
        ferramenta={
            "custo_direto": 100.0,
            "custo_direto_catalogo": 100.0,
            "custo_indireto": 20.0,
            "custo_total": 120.0,
            "preco_venda": 130.0,
        },
        ponto_equilibrio_ferramenta=None,
        ferramenta_breakdown_direto=None,
        ferramenta_breakdown_indireto=None,
        actionable_insights=None,
    )


def test_report_reference_projection_parity_legacy_vs_v2(monkeypatch) -> None:
    builder = BenchmarkReportBuilder()
    spec = ProjectSpec(nome="Projeto Teste", slug="proj-teste", contexto_id="ctx")
    ref = {
        "planejamento_detalhado": [
            {"subtotal": {"sem_bdi": {"total": 60.0}, "com_bdi": {"total": 80.0}}},
            {"subtotal": {"sem_bdi": {"total": 40.0}, "com_bdi": {"total": 50.0}}},
        ],
        "resultado": {
            "benchmark_confronto_referencia": {
                "custo_direto": 95.0,
                "custo_indireto": 20.0,
                "custo_total": 115.0,
                "preco_venda": 130.0,
            }
        },
    }

    monkeypatch.setattr(
        "concilium.application.benchmarks.report_builder.BenchmarkProjection.from_canonical",
        lambda canonical: _fake_projection(),
    )

    inferred = builder.build(spec=spec, version="v1", results_log=[], ref=ref, canonical=object())

    pack = BenchmarkInferenceService.derive(ref)
    injected = builder.build(spec=spec, version="v1", results_log=[], ref=ref, canonical=object(), inference_pack=pack)

    assert inferred["confronto"]["referencia"] == injected["confronto"]["referencia"]
    assert inferred["confronto"]["deltas"] == injected["confronto"]["deltas"]
    assert inferred["status_final"] == injected["status_final"]
