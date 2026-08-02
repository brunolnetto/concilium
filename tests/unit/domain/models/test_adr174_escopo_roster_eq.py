"""Testes para Escopo.roster_eq (ADR-174 F1).

Espelha test_adr173_escopo_roster_mo.py — fecha a assimetria MO/EQ: roster real
de equipamento nunca tinha ganho persistência (ADR-155/157 permaneciam
transientes mesmo depois da ADR-173, que só cobriu MO).
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from concilium.domain.models.canonical import AtivoEquipamentoReal
from concilium.domain.models.project.escopo import Escopo


def _escopo_kwargs(**overrides) -> dict:
    base = dict(
        escopo_id="lote-a",
        projeto_id="proj-1",
        nome="Lote A",
        tipo_obra="terraplenagem",
        localizacao="Fortaleza-CE",
        coordenadas_lat=-3.7172,
        coordenadas_lng=-38.5433,
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
    )
    base.update(overrides)
    return base


class TestRosterEq:
    def test_default_e_lista_vazia(self):
        escopo = Escopo(**_escopo_kwargs())
        assert escopo.roster_eq == []

    def test_aceita_ativos_reais(self):
        escopo = Escopo(
            **_escopo_kwargs(
                roster_eq=[
                    AtivoEquipamentoReal(
                        ativo_id="eq-001",
                        equip_id="EQ-ESCAVADEIRA",
                        custo_locacao_mensal_real=12000.0,
                        data_contrato_inicio=date(2026, 1, 5),
                    )
                ]
            )
        )
        assert len(escopo.roster_eq) == 1
        assert escopo.roster_eq[0].ativo_id == "eq-001"

    def test_aceita_dict_cru_via_model_validate(self):
        escopo = Escopo.model_validate(
            {
                **_escopo_kwargs(),
                "roster_eq": [
                    {
                        "ativo_id": "eq-002",
                        "equip_id": "EQ-CAMINHAO",
                        "custo_locacao_mensal_real": 8000.0,
                        "data_contrato_inicio": "2026-02-01",
                    }
                ],
            }
        )
        assert isinstance(escopo.roster_eq[0], AtivoEquipamentoReal)
        assert escopo.roster_eq[0].equip_id == "EQ-CAMINHAO"

    def test_rejeita_custo_locacao_negativo(self):
        with pytest.raises(ValidationError):
            AtivoEquipamentoReal(
                ativo_id="eq-003",
                equip_id="EQ-X",
                custo_locacao_mensal_real=-1.0,
                data_contrato_inicio=date(2026, 1, 1),
            )
