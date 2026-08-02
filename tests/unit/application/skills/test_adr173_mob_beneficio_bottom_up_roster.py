"""ADR-173 F7 — _composicao_mob_beneficio_bottom_up com roster_mo.

Quando o roster cobre integralmente o headcount agregado de uma função
(across todas as equipes), a contagem real substitui `num_pessoas` —
proporcionalmente por equipe quando a mesma função aparece em mais de uma,
preservando a ponderação por `permanencia_efetiva_meses` (ADR-136 F4).
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from concilium.domain.constants import SEMANAS_POR_MES
from concilium.domain.models.canonical import MembroEquipeReal

_DIAS_MES = SEMANAS_POR_MES * 7
_BASE = Path("src/concilium/application/skills/manifests/06-resultado-financeiro")


def _load_mob():
    p = (_BASE / "_indiretos/_skill_helpers/__init__.py").resolve()
    spec = importlib.util.spec_from_file_location("adr173_indir_mob", p, submodule_search_locations=[str(p.parent)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["adr173_indir_mob"] = mod
    spec.loader.exec_module(mod)
    return mod


def _mk_equipe(funcoes: list[tuple[str, int]], permanencia_efetiva_meses: float):
    return SimpleNamespace(
        funcoes=[SimpleNamespace(funcao_id=fid, num_pessoas=n) for fid, n in funcoes],
        permanencia_efetiva_meses=permanencia_efetiva_meses,
    )


def _beneficio(codigo, preco, periodicidade, aplicavel_tipo_contrato=None, status="ativo"):
    return {
        "codigo": codigo,
        "tipo": "BENEFICIO",
        "preco_unitario": preco,
        "status": status,
        "atributos_especificos": {
            "periodicidade_beneficio": periodicidade,
            "aplicavel_tipo_contrato": aplicavel_tipo_contrato,
        },
    }


def _membro(**overrides) -> MembroEquipeReal:
    defaults = dict(
        individuo_id="mo-001",
        funcao_id="MO-ARMADOR",
        salario_base_mensal=3000.0,
        data_admissao=date(2026, 1, 1),
    )
    defaults.update(overrides)
    return MembroEquipeReal(**defaults)


class TestComposicaoMobBeneficioComRoster:
    def _fn(self):
        return _load_mob()._composicao_mob_beneficio_bottom_up

    def test_sem_roster_comportamento_identico_ao_adr166(self):
        fn = self._fn()
        equipes = [_mk_equipe([("MO-ARMADOR", 2)], 3.0)]
        catalogo = {"insumos": [_beneficio("BEN-SEGURO-VIDA", 35.0, "mensal")]}
        total = fn(equipes, catalogo, None)
        assert total == pytest.approx(2 * 35.0 * 3.0)

    def test_roster_cobre_funcao_unica_equipe_usa_contagem_real(self):
        fn = self._fn()
        equipes = [_mk_equipe([("MO-ARMADOR", 1)], 3.0)]  # cadastro diz 1, real são 2
        catalogo = {"insumos": [_beneficio("BEN-SEGURO-VIDA", 35.0, "mensal")]}
        roster = [
            _membro(individuo_id="mo-001", funcao_id="MO-ARMADOR"),
            _membro(individuo_id="mo-002", funcao_id="MO-ARMADOR"),
        ]
        total = fn(equipes, catalogo, roster)
        assert total == pytest.approx(2 * 35.0 * 3.0)

    def test_roster_nao_cobre_mantem_num_pessoas_cadastrado(self):
        fn = self._fn()
        equipes = [_mk_equipe([("MO-ARMADOR", 3)], 3.0)]
        catalogo = {"insumos": [_beneficio("BEN-SEGURO-VIDA", 35.0, "mensal")]}
        roster = [_membro(individuo_id="mo-001", funcao_id="MO-ARMADOR")]  # só 1, precisa de 3
        total = fn(equipes, catalogo, roster)
        assert total == pytest.approx(3 * 35.0 * 3.0)

    def test_mesma_funcao_em_duas_equipes_distribui_proporcionalmente(self):
        fn = self._fn()
        # MO-ARMADOR: 2 pessoas na equipe A (permanencia 3.0), 2 na equipe B (permanencia 6.0)
        # agregado = 4; roster real = 4 (cobre) -> proporção 1:1, resultado idêntico ao cadastrado
        equipes = [
            _mk_equipe([("MO-ARMADOR", 2)], 3.0),
            _mk_equipe([("MO-ARMADOR", 2)], 6.0),
        ]
        catalogo = {"insumos": [_beneficio("BEN-SEGURO-VIDA", 35.0, "mensal")]}
        roster = [_membro(individuo_id=f"mo-{i:03d}", funcao_id="MO-ARMADOR") for i in range(4)]
        total = fn(equipes, catalogo, roster)
        esperado = 2 * 35.0 * 3.0 + 2 * 35.0 * 6.0
        assert total == pytest.approx(esperado)

    def test_mesma_funcao_duas_equipes_roster_reduzido_distribui_proporcao(self):
        fn = self._fn()
        # agregado cadastrado = 4 (2+2), roster real = 2 -> não cobre (2 < 4), mantém cadastrado
        equipes = [
            _mk_equipe([("MO-ARMADOR", 2)], 3.0),
            _mk_equipe([("MO-ARMADOR", 2)], 6.0),
        ]
        catalogo = {"insumos": [_beneficio("BEN-SEGURO-VIDA", 35.0, "mensal")]}
        roster = [
            _membro(individuo_id="mo-001", funcao_id="MO-ARMADOR"),
            _membro(individuo_id="mo-002", funcao_id="MO-ARMADOR"),
        ]
        total = fn(equipes, catalogo, roster)
        esperado = 2 * 35.0 * 3.0 + 2 * 35.0 * 6.0
        assert total == pytest.approx(esperado)

    def test_roster_de_outra_funcao_nao_afeta(self):
        fn = self._fn()
        equipes = [_mk_equipe([("MO-ARMADOR", 1)], 1.0)]
        catalogo = {"insumos": [_beneficio("BEN-SEGURO-VIDA", 35.0, "mensal")]}
        roster = [_membro(individuo_id="mo-001", funcao_id="MO-CARPINTEIRO")]
        total = fn(equipes, catalogo, roster)
        assert total == pytest.approx(1 * 35.0 * 1.0)
