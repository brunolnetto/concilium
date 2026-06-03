from __future__ import annotations

import json
import time
from datetime import date

from concilium.domain.services.bridge_analyzer import BridgeAnalyzer
from concilium.infrastructure.repositories.insumo import RepositorioInsumo


def _run_bridge_benchmark(iterations: int) -> dict:
    t0 = time.perf_counter()
    sample = None
    for _ in range(iterations):
        sample = BridgeAnalyzer.calcular(
            nivel_1=1500.0,
            necessidades_fracionadas=[0.7, 1.05, 1.9],
            praticabilidade=0.83,
            nivel_4=3200.0,
        )
    elapsed = time.perf_counter() - t0
    return {
        "iterations": iterations,
        "elapsed_seconds": elapsed,
        "ops_per_sec": iterations / elapsed if elapsed > 0 else 0.0,
        "sample": {
            "nivel_3": sample.nivel_3_catalogo_normalizado,
            "delta_real_abs": sample.delta_real_abs,
            "status_alerta": sample.status_alerta,
        },
    }


def _run_temporal_price_benchmark(iterations: int) -> dict:
    repo = RepositorioInsumo(
        {
            "insumos": [
                {
                    "codigo": "DIESEL-S10",
                    "preco_unitario": 6.2,
                    "historico_precos": [
                        {
                            "preco_unitario": 5.9,
                            "data_inicio_vigencia": "2026-03-01",
                            "data_fim_vigencia": "2026-03-31",
                        },
                        {
                            "preco_unitario": 6.2,
                            "data_inicio_vigencia": "2026-04-01",
                            "data_fim_vigencia": None,
                        },
                    ],
                }
            ]
        }
    )

    t0 = time.perf_counter()
    price = None
    source = None
    for _ in range(iterations):
        price, source = repo.resolver_preco("DIESEL-S10", data_referencia=date(2026, 4, 15))
    elapsed = time.perf_counter() - t0
    return {
        "iterations": iterations,
        "elapsed_seconds": elapsed,
        "ops_per_sec": iterations / elapsed if elapsed > 0 else 0.0,
        "sample": {"price": price, "source": source},
    }


def test_adr039_041_benchmark_evidence_is_reproducible(tmp_path) -> None:
    evidence = {
        "suite": "ADR039_041_REGRESSION_EVIDENCE",
        "bridge": _run_bridge_benchmark(iterations=2000),
        "temporal_price": _run_temporal_price_benchmark(iterations=4000),
    }

    out = tmp_path / "adr039_041_regression_evidence.json"
    out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    assert out.exists()

    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["suite"] == "ADR039_041_REGRESSION_EVIDENCE"
    assert loaded["bridge"]["sample"]["status_alerta"] in {"VERDE", "AMARELO", "VERMELHO"}
    assert loaded["bridge"]["ops_per_sec"] > 0
    assert loaded["temporal_price"]["sample"]["source"] == "HISTORICO_SCD2"
    assert loaded["temporal_price"]["sample"]["price"] == 6.2
    assert loaded["temporal_price"]["ops_per_sec"] > 0
