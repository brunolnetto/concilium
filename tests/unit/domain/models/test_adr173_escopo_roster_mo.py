"""Testes para Escopo.roster_mo (ADR-173 F1).

Campo persistido que dá ao pipeline de custo real individualizado (ADR-154→160)
uma fonte real de indivíduos por projeto/escopo — ausente (lista vazia, default)
preserva o comportamento atual (custo calibrado/agregado, sem substituição por
roster). Mesmo padrão de `Escopo.logistica_consumiveis` (ADR-128 F5).
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from concilium.domain.models.canonical import MembroEquipeReal
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


class TestRosterMo:
    def test_default_e_lista_vazia(self):
        escopo = Escopo(**_escopo_kwargs())
        assert escopo.roster_mo == []

    def test_aceita_membros_reais(self):
        escopo = Escopo(
            **_escopo_kwargs(
                roster_mo=[
                    MembroEquipeReal(
                        individuo_id="mo-001",
                        funcao_id="MO-ARMADOR",
                        salario_base_mensal=3200.0,
                        data_admissao=date(2026, 1, 5),
                    )
                ]
            )
        )
        assert len(escopo.roster_mo) == 1
        assert escopo.roster_mo[0].individuo_id == "mo-001"

    def test_aceita_dict_cru_via_model_validate(self):
        """MCP/persistência entregam dict cru (JSON), não MembroEquipeReal já
        instanciado — Escopo deve validar/converter automaticamente."""
        escopo = Escopo.model_validate(
            {
                **_escopo_kwargs(),
                "roster_mo": [
                    {
                        "individuo_id": "mo-002",
                        "funcao_id": "MO-CARPINTEIRO",
                        "salario_base_mensal": 2800.0,
                        "data_admissao": "2026-02-01",
                    }
                ],
            }
        )
        assert isinstance(escopo.roster_mo[0], MembroEquipeReal)
        assert escopo.roster_mo[0].funcao_id == "MO-CARPINTEIRO"

    def test_aceita_multiplos_individuos(self):
        escopo = Escopo(
            **_escopo_kwargs(
                roster_mo=[
                    MembroEquipeReal(
                        individuo_id="mo-001",
                        funcao_id="MO-ARMADOR",
                        salario_base_mensal=3200.0,
                        data_admissao=date(2026, 1, 5),
                    ),
                    MembroEquipeReal(
                        individuo_id="mo-002",
                        funcao_id="MO-ARMADOR",
                        salario_base_mensal=3100.0,
                        data_admissao=date(2026, 1, 5),
                    ),
                ]
            )
        )
        assert {m.individuo_id for m in escopo.roster_mo} == {"mo-001", "mo-002"}

    def test_membro_desligado_preserva_data_desligamento(self):
        escopo = Escopo(
            **_escopo_kwargs(
                roster_mo=[
                    MembroEquipeReal(
                        individuo_id="mo-003",
                        funcao_id="MO-ARMADOR",
                        salario_base_mensal=3200.0,
                        data_admissao=date(2026, 1, 5),
                        data_desligamento=date(2026, 6, 30),
                    )
                ]
            )
        )
        assert escopo.roster_mo[0].data_desligamento == date(2026, 6, 30)

    def test_rejeita_salario_negativo(self):
        with pytest.raises(ValidationError):
            MembroEquipeReal(
                individuo_id="mo-004",
                funcao_id="MO-ARMADOR",
                salario_base_mensal=-1.0,
                data_admissao=date(2026, 1, 5),
            )
