from __future__ import annotations

import json
from pathlib import Path

from concilium.application.benchmarks.analysis.etapa_diffs import generate_diffs_for_benchmark


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def test_generate_diffs_supports_modern_agis_reference_layout(tmp_path: Path):
    root = tmp_path
    slug = "AGIS"

    # benchmark report (novo caminho organizado)
    _write_json(
        root / "benchmarks" / "data" / slug / "artifacts" / "outputs" / "benchmark_report.json",
        {"slug": slug, "projeto": "Projeto AGIS"},
    )

    # referência atual (artifacts/inputs/referencia.json)
    _write_json(
        root / "benchmarks" / "data" / slug / "artifacts" / "inputs" / "referencia.json",
        {
            "resultado": {
                "benchmark_confronto_referencia": {
                    "custo_direto": 100.0,
                    "custo_indireto": 20.0,
                    "custo_total": 120.0,
                    "preco_venda": 130.0,
                }
            },
            "equipes_detalhadas": [
                {
                    "item_id": "eap-1",
                    "funcoes": [{"funcao_id": "F1", "num_pessoas": 2}],
                    "equipamentos": [{"equip_id": "E1", "num_unidades": 1}],
                }
            ],
            "planejamento_detalhado": [
                {
                    "item_id": "eap-1",
                    "subtotal": {"sem_bdi": {"total": 100.0}},
                }
            ],
            "rcpsp_spec": {"deadline_weeks": 52},
            "ADM": {"custo_fixo_mensal_total": 1.0},
            "TOP": {"custo_fixo_mensal_total": 1.0},
            "LAB": {"custo_fixo_mensal_total": 1.0},
            "QSMS": {"custo_fixo_mensal_total": 1.0},
            "MOB": {"custo_fixo_total": 10.0},
        },
    )

    # canonical no novo root de benchmarks/projetos
    _write_json(
        root / "benchmarks" / "projetos" / "p1" / "meta.json",
        {"id": "p1", "nome": "Projeto AGIS", "current_version": "v1"},
    )
    _write_json(
        root / "benchmarks" / "projetos" / "p1" / "v1" / "canonical.json",
        {
            "equipes_diretas": [
                {
                    "item_id": "eap-1",
                    "funcoes": [{"funcao_id": "F1", "num_pessoas": 2}],
                    "equipamentos": [{"equip_id": "E1", "num_unidades": 1}],
                    "custo_total": 100.0,
                }
            ],
            "planejamento": [
                {
                    "item_id": "eap-1",
                    "subtotal": {"sem_bdi": {"total": 100.0}},
                }
            ],
            "indiretos": [
                {"categoria": "ADM", "custo_total": 12.0},
            ],
            "resultado": {
                "venda": {"total_com_bdi": 130.0},
                "custo": {"total": 120.0},
                "margem_pct": 0.0769,
            },
        },
    )

    out = generate_diffs_for_benchmark(slug, root=root)

    assert out is not None
    assert out["slug"] == slug
    assert "por_etapa" in out
    assert "05-equipes-e-alocacao" in out["por_etapa"]
    assert "04-planejamento-e-insumos" in out["por_etapa"]
    assert "indiretos-e-contingencia" in out["por_etapa"]  # NEP-041 F4
    assert "06-consolidacao-resultado" in out["por_etapa"]
