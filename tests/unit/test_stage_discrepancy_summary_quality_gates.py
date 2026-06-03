from __future__ import annotations

import json
from pathlib import Path

from concilium.application.benchmarks.analysis.stage_discrepancy_summary import build_summary


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_summary_includes_quality_gate_fields(tmp_path: Path):
    root = tmp_path
    bench_slug = "MATEC_GUARULHOS"

    referencia_path = root / "benchmarks" / "data" / bench_slug / "referencia.json"
    _write_json(
        referencia_path,
        {
            "equipes_detalhadas": [
                {
                    "custo_mao_obra_mensal": 10,
                    "custo_equipamentos_mensal": 20,
                    "custo_combustivel_total_mensal": 5,
                    "custo_material_mensal": 2,
                }
            ]
        },
    )

    _write_json(
        root / "benchmarks" / "data" / bench_slug / "extracao_intermediarios.json",
        {
            "slug": bench_slug,
            "projeto": "Projeto Teste",
            "paths": {"referencia": str(referencia_path)},
            "etapas": {
                "01_praticabilidade": {"fonte": "teste"},
                "06_consolidacao": {"benchmark_alignment": {"aplicada": True, "erro_vs_referencia": 1.2}},
            },
            "disparidades": {
                "itens_planejamento_zerados_com_quantidade": [],
                "equipes_zeradas": [],
                "gap_orcamento_itens_vs_tool_preco_plus_eq": 10.0,
                "gap_orcamento_itens_vs_tool_preco_com_bdi_catalogo": 5.0,
            },
        },
    )

    _write_json(
        root / "benchmark_matec_guarulhos.json",
        {
            "slug": bench_slug,
            "status_final": "APROVADO_COM_RESSALVAS",
            "quality_gates": {
                "decision": "APROVADO_COM_RESSALVAS",
                "worst_severity": "S1",
                "critical_metric_over_10pct": True,
            },
            "action_report": [
                {"severidade": "S1", "status_acao": "ABERTA"},
                {"severidade": "S0", "status_acao": "NAO_APLICAVEL"},
            ],
        },
    )

    summary = build_summary(root)

    assert summary["meta"]["total_benchmarks_com_extracao"] == 1
    assert summary["meta"]["quality_gate_status_counts"]["APROVADO_COM_RESSALVAS"] == 1
    assert summary["meta"]["quality_gate_severity_counts"]["S1"] == 1
    assert summary["meta"]["benchmarks_sem_quality_gate"] == 0
    assert summary["meta"]["benchmarks_critical_metric_over_10pct"] == 1
    assert summary["meta"]["acoes_granulares_abertas_total"] == 1

    row = summary["benchmarks"][0]
    gates = row["quality_gates"]
    assert gates["status_final"] == "APROVADO_COM_RESSALVAS"
    assert gates["worst_severity"] == "S1"
    assert gates["action_report_abertas"] == 1
