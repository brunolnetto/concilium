from __future__ import annotations

import json
from pathlib import Path

from concilium.application.benchmarks.analysis.stage_discrepancy_summary import (
    _bs_aggregate_gates,
    _bs_count_flag_rows,
    _ct_sum_equipes_costs,
    _find_praticabilidade_keys,
    _lgrs_sum_action_report,
    _load_gate_report_for_slug,
    _safe_float,
    _severity_score,
    build_summary,
)


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


# ---------------------------------------------------------------------------
# _find_praticabilidade_keys — list iteration branch
# ---------------------------------------------------------------------------


def test_find_praticabilidade_keys_in_list():
    """List elements are recursed into."""
    obj = [{"praticabilidade_valor": 12.5}, {"other": 1}]
    hits = _find_praticabilidade_keys(obj)
    assert len(hits) == 1
    assert hits[0]["value"] == 12.5


def test_find_praticabilidade_keys_nested_dict():
    """Nested dict keys are traversed recursively."""
    obj = {"nivel1": {"produtividade_media": 8}}
    hits = _find_praticabilidade_keys(obj)
    assert any("produtiv" in h["path"].lower() for h in hits)


def test_find_praticabilidade_keys_empty():
    assert _find_praticabilidade_keys({}) == []
    assert _find_praticabilidade_keys([]) == []
    assert _find_praticabilidade_keys("scalar") == []


# ---------------------------------------------------------------------------
# _safe_float
# ---------------------------------------------------------------------------


def test_safe_float_none_returns_none():
    assert _safe_float(None) is None


def test_safe_float_valid_string():
    assert _safe_float("3.14") == 3.14


def test_safe_float_invalid_returns_none():
    assert _safe_float("not_a_number") is None


# ---------------------------------------------------------------------------
# _lgrs_sum_action_report
# ---------------------------------------------------------------------------


def test_lgrs_sum_action_report_empty():
    by_sev, abertos = _lgrs_sum_action_report([])
    assert by_sev == {}
    assert abertos == 0


def test_lgrs_sum_action_report_counts_aberta():
    action_report = [
        {"severidade": "S1", "status_acao": "ABERTA"},
        {"severidade": "S1", "status_acao": "FECHADA"},
        {"severidade": None, "status_acao": "ABERTA"},
    ]
    by_sev, abertos = _lgrs_sum_action_report(action_report)
    assert abertos == 2
    assert by_sev["S1"] == 2
    assert by_sev["S0"] == 1  # None severidade defaults to S0


# ---------------------------------------------------------------------------
# _load_gate_report_for_slug — slug=None branch
# ---------------------------------------------------------------------------


def test_load_gate_report_slug_none_returns_empty(tmp_path):
    result = _load_gate_report_for_slug(None, tmp_path)
    assert result == {}


def test_load_gate_report_slug_not_found_returns_empty(tmp_path):
    result = _load_gate_report_for_slug("NONEXISTENT_SLUG", tmp_path)
    assert result == {}


def test_load_gate_report_slug_found_via_direct_path(tmp_path: Path):
    """Loads report from benchmarks/data/<SLUG>/artifacts/outputs/benchmark_report.json."""
    slug = "TEST_SLUG"
    report = {
        "slug": slug,
        "status_final": "APROVADO",
        "quality_gates": {"decision": "APROVADO", "worst_severity": "S0", "critical_metric_over_10pct": False},
        "action_report": [],
    }
    path = tmp_path / "benchmarks" / "data" / slug / "artifacts" / "outputs" / "benchmark_report.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(report), encoding="utf-8")
    result = _load_gate_report_for_slug(slug.lower(), tmp_path)
    assert result["status_final"] == "APROVADO"


# ---------------------------------------------------------------------------
# _ct_sum_equipes_costs
# ---------------------------------------------------------------------------


def test_ct_sum_equipes_costs_empty():
    total_mo, total_eq, total_diesel, total_mat = _ct_sum_equipes_costs([])
    assert total_mo == 0.0
    assert total_eq == 0.0


def test_ct_sum_equipes_costs_aggregates():
    equipes = [
        {
            "custo_mao_obra_mensal": 100,
            "custo_equipamentos_mensal": 200,
            "custo_combustivel_total_mensal": 50,
            "custo_material_mensal": 10,
        },
        {
            "custo_mao_obra_mensal": 200,
            "custo_equipamentos_mensal": 300,
            "custo_combustivel_total_mensal": None,
            "custo_material_mensal": None,
        },
    ]
    mo, eq, diesel, mat = _ct_sum_equipes_costs(equipes)
    assert mo == 300.0
    assert eq == 500.0
    assert diesel == 50.0
    assert mat == 10.0


# ---------------------------------------------------------------------------
# _bs_count_flag_rows
# ---------------------------------------------------------------------------


def test_bs_count_flag_rows_mixed():
    rows = [
        {
            "flags": {
                "sem_praticabilidade_planilha_fonte": True,
                "tem_zerados_em_equipes": True,
                "tem_zerados_em_planejamento": False,
            }
        },
        {
            "flags": {
                "sem_praticabilidade_planilha_fonte": False,
                "tem_zerados_em_equipes": False,
                "tem_zerados_em_planejamento": True,
            }
        },
        {"flags": {}},
    ]
    sem_prat, com_eq, com_pl = _bs_count_flag_rows(rows)
    assert sem_prat == 1
    assert com_eq == 1
    assert com_pl == 1


# ---------------------------------------------------------------------------
# _bs_aggregate_gates
# ---------------------------------------------------------------------------


def test_bs_aggregate_gates_nao_disponivel():
    rows = [{"quality_gates": {}}]
    status_counts, severity_counts, gates_missing, crit_over_10, abertos = _bs_aggregate_gates(rows)
    assert gates_missing == 1
    assert status_counts["NAO_DISPONIVEL"] == 1


def test_bs_aggregate_gates_critical_metric():
    rows = [
        {
            "quality_gates": {
                "status_final": "REPROVADO",
                "worst_severity": "S2",
                "critical_metric_over_10pct": True,
                "action_report_abertas": 3,
            }
        }
    ]
    _, _, _, crit_over_10, abertos = _bs_aggregate_gates(rows)
    assert crit_over_10 == 1
    assert abertos == 3


# ---------------------------------------------------------------------------
# _severity_score
# ---------------------------------------------------------------------------


def test_severity_score_with_gaps():
    item = {
        "discrepancias_etapas": {
            "gap_orcamento_vs_preco_plus_eq": 10000.0,
            "gap_orcamento_vs_preco_com_bdi_catalogo": -5000.0,
            "qtd_equipes_zeradas": 1,
            "qtd_itens_planejamento_zerados": 0,
        }
    }
    score = _severity_score(item)
    assert score == abs(10000.0) + abs(-5000.0) + 1 * 1_000_000.0


def test_severity_score_empty():
    assert _severity_score({}) == 0.0


# ---------------------------------------------------------------------------
# build_summary with empty benchmarks dir
# ---------------------------------------------------------------------------


def test_build_summary_empty_dir(tmp_path: Path):
    (tmp_path / "benchmarks" / "data").mkdir(parents=True)
    summary = build_summary(tmp_path)
    assert summary["meta"]["total_benchmarks_com_extracao"] == 0
    assert summary["top_discrepancias"] == []
    assert summary["benchmarks"] == []


def test_build_summary_skips_non_dirs(tmp_path: Path):
    data_dir = tmp_path / "benchmarks" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "some_file.txt").write_text("x")
    summary = build_summary(tmp_path)
    assert summary["meta"]["total_benchmarks_com_extracao"] == 0


import tempfile  # noqa: E402

# stage_discrepancy_summary.py line 208:
# bench_data subdir exists but no extracao_intermediarios.json → continue
# ---------------------------------------------------------------------------


class TestBuildSummarySkipsSubdirWithoutTrace:
    def test_dir_without_trace_file_is_skipped(self):
        """Line 208: continue when trace file doesn't exist."""
        from concilium.application.benchmarks.analysis.stage_discrepancy_summary import (
            build_summary,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bench_data = root / "benchmarks" / "data"
            bench_data.mkdir(parents=True)
            # Subdir without trace file
            (bench_data / "BENCH-NO-TRACE").mkdir()

            result = build_summary(root=root)

        # The subdir was skipped → no rows collected
        assert result["meta"]["total_benchmarks_com_extracao"] == 0
        assert result["top_discrepancias"] == []


# ---------------------------------------------------------------------------

