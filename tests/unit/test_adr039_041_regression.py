from __future__ import annotations

from datetime import date

import pytest

from concilium.domain.services.bridge_analyzer import BridgeAnalyzer
from concilium.infrastructure.repositories.insumo import RepositorioInsumo


def test_adr039_bridge_decomposition_is_deterministic() -> None:
    bridge = BridgeAnalyzer.calcular(
        nivel_1=1000.0,
        necessidades_fracionadas=[0.5, 1.2],
        praticabilidade=0.8,
        nivel_4=2600.0,
    )

    assert bridge.fator_quantizacao == pytest.approx(1.8333, abs=1e-4)
    assert bridge.nivel_2_catalogo_escalado == pytest.approx(1833.33, abs=1e-2)
    assert bridge.nivel_3_catalogo_normalizado == pytest.approx(2291.66, abs=1e-2)
    assert bridge.desvio_escala_abs == pytest.approx(833.33, abs=1e-2)
    assert bridge.desvio_clima_abs == pytest.approx(458.33, abs=1e-2)
    assert bridge.delta_real_abs == pytest.approx(308.34, abs=1e-2)
    assert bridge.delta_estrutural_abs == pytest.approx(1291.66, abs=1e-2)
    assert bridge.status_alerta == "AMARELO"


def test_adr041_resolver_preco_cascade_priority() -> None:
    catalogo = {
        "insumos": [
            {
                "codigo": "INS-001",
                "preco_unitario": 10.0,
                "regionalizacao": {"GO": {"preco": 13.0}},
                "historico_precos": [
                    {
                        "preco_unitario": 9.0,
                        "data_inicio_vigencia": "2025-01-01",
                        "data_fim_vigencia": "2025-12-31",
                    },
                    {
                        "preco_unitario": 11.0,
                        "data_inicio_vigencia": "2026-01-01",
                        "data_fim_vigencia": None,
                    },
                ],
            }
        ]
    }
    repo = RepositorioInsumo(catalogo)

    preco_ovr, fonte_ovr = repo.resolver_preco(
        "INS-001",
        jurisdicao_id="GO",
        overrides={"INS-001": {"preco_calibrado": 19.5}},
        data_referencia=date(2026, 2, 1),
    )
    assert preco_ovr == pytest.approx(19.5)
    assert fonte_ovr == "PROJECT_OVERRIDE"

    preco_reg, fonte_reg = repo.resolver_preco(
        "INS-001",
        jurisdicao_id="GO",
        overrides=None,
        data_referencia=date(2026, 2, 1),
    )
    assert preco_reg == pytest.approx(13.0)
    assert fonte_reg == "SICRO_REGIONAL"

    preco_hist, fonte_hist = repo.resolver_preco(
        "INS-001",
        jurisdicao_id=None,
        overrides=None,
        data_referencia=date(2026, 2, 1),
    )
    assert preco_hist == pytest.approx(11.0)
    assert fonte_hist == "HISTORICO_SCD2"


def test_adr041_scd2_update_closes_previous_period() -> None:
    catalogo = {
        "insumos": [
            {
                "codigo": "INS-002",
                "preco_unitario": 20.0,
                "historico_precos": [
                    {
                        "preco_unitario": 20.0,
                        "data_inicio_vigencia": "2026-01-01",
                        "data_fim_vigencia": None,
                    }
                ],
            }
        ]
    }
    repo = RepositorioInsumo(catalogo)

    ok = repo.atualizar_preco("INS-002", 25.0, date(2026, 5, 1), fonte="PROMOTION")
    assert ok is True

    insumo = repo.obter_insumo("INS-002")
    assert insumo is not None
    historico = insumo["historico_precos"]
    assert historico[0]["data_fim_vigencia"] == "2026-05-01"
    assert historico[-1]["preco_unitario"] == pytest.approx(25.0)
    assert historico[-1]["data_inicio_vigencia"] == "2026-05-01"
    assert historico[-1]["data_fim_vigencia"] is None
    assert insumo["preco_unitario"] == pytest.approx(25.0)
