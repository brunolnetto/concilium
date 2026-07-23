from __future__ import annotations

from datetime import date

import pytest

from concilium.infrastructure.repositories.insumo import RepositorioInsumo


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


def test_adr145_atualizar_preco_records_nota_append_only() -> None:
    """ADR-145 D4: `nota` fica no próprio registro histórico (append-only por
    construção), sem sobrescrever um campo único a cada chamada."""
    catalogo = {
        "insumos": [
            {
                "codigo": "INS-003",
                "preco_unitario": 10.0,
                "historico_precos": [
                    {"preco_unitario": 10.0, "data_inicio_vigencia": "2026-01-01", "data_fim_vigencia": None}
                ],
            }
        ]
    }
    repo = RepositorioInsumo(catalogo)

    repo.atualizar_preco("INS-003", 12.0, date(2026, 3, 1), fonte="eng@co.com", nota="reajuste INCC")
    repo.atualizar_preco("INS-003", 14.0, date(2026, 6, 1), fonte="eng@co.com", nota="reajuste cambial")

    historico = repo.obter_insumo("INS-003")["historico_precos"]
    assert historico[0].get("nota") is None  # registro original, anterior à mudança
    assert historico[1]["nota"] == "reajuste INCC"
    assert historico[2]["nota"] == "reajuste cambial"
