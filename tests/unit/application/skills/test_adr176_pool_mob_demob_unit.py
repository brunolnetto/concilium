"""ADR-176 F4 (pool) — custo_mob_unit/custo_demob_unit reais quando rcpsp_spec é
auto-derivado, sem desligar o fallback de idle (ADR-085).

Achado (ADR-137 P1): `_derive_rcpsp_from_canonical` omitia `resource_costs`
propositalmente, então `RecursoContrato.custo_mob_unit`/`custo_demob_unit`
ficavam sempre 0.0 no caminho automático — a decisão de perpetuação (ADR-073)
rodava sempre em modo heurístico de tempo, nunca econômico. Esta ADR popula
esses campos a partir do mesmo dado de catálogo `custo_mobilizacao`/
`custo_desmobilizacao` por função/equipamento já usado pelo custo direto e pelo
indireto de projeto — sem popular `custo_idle_semanal_unit`, para que o
fallback ADR-085 (`cus_mo + cus_locacao`) continue engajando.

Escrito antes da implementação (red phase).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[4]


def _load_helpers_a():
    path = (
        _ROOT
        / "src/concilium/application/skills/manifests"
        / "05-equipes-e-alocacao/_skill_helpers/__init__.py"
    )
    spec = importlib.util.spec_from_file_location(
        "adr176_helpers_a", path, submodule_search_locations=[str(path.parent)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["adr176_helpers_a"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestCustoMobDemobUnitComposicao:
    def _fn(self):
        return _load_helpers_a()._custo_mob_demob_unit_composicao

    def test_soma_funcoes_e_equipamentos(self):
        composicao = {
            "funcoes": [
                {"funcao_id": "F1", "num_pessoas": 2, "custo_mobilizacao": 800.0, "custo_desmobilizacao": 800.0},
            ],
            "equipamentos": [
                {"equip_id": "E1", "num_unidades": 1, "custo_mobilizacao": 6500.0, "custo_desmobilizacao": 6500.0},
                {"equip_id": "E2", "num_unidades": 2, "custo_mobilizacao": 1300.0, "custo_desmobilizacao": 1300.0},
            ],
        }
        c_mob, c_demob = self._fn()(composicao)
        # funcoes: 2*800=1600; equipamentos: 1*6500 + 2*1300 = 9100; total = 10700
        assert c_mob == pytest.approx(10700.0)
        assert c_demob == pytest.approx(10700.0)

    def test_composicao_sem_custo_mob_retorna_zero(self):
        composicao = {"funcoes": [{"funcao_id": "F1", "num_pessoas": 2}], "equipamentos": []}
        assert self._fn()(composicao) == (0.0, 0.0)

    def test_composicao_vazia_retorna_zero(self):
        assert self._fn()({}) == (0.0, 0.0)


class TestDeriveRcpspFromCanonicalResourceCosts:
    def _fn(self):
        return _load_helpers_a()._derive_rcpsp_from_canonical

    def _canonical(self, weeks, item_id="I1", cpu_id="CPU-1"):
        dist = {w: SimpleNamespace(num_equipes=1) for w in weeks}
        sched_act = SimpleNamespace(activity_id=item_id, distribuicao_semanal=dist)
        return SimpleNamespace(
            cronograma=SimpleNamespace(scheduled_activities=[sched_act]),
            eap=[SimpleNamespace(item_id=item_id, cpu_id=cpu_id)],
        )

    def test_composicao_sem_mob_demob_nao_popula_resource_costs(self):
        """Retrocompat: catálogo sem custo_mobilizacao/desmobilizacao não ganha
        a chave resource_costs — mesmo comportamento de sempre."""
        canonical_in = self._canonical(["S001"])
        catalogo = {
            "cpus": [{"codigo": "CPU-1", "producao_id_ref": "PROD-1"}],
            "producoes": [
                {
                    "id": "PROD-1",
                    "composicao_padrao_equipe": {"equipamentos": [{"equip_id": "EQ-1", "num_unidades": 1}]},
                }
            ],
        }
        result = self._fn()(canonical_in, catalogo)
        assert result is not None
        assert "resource_costs" not in result

    def test_composicao_com_mob_demob_popula_resource_costs_sem_idle(self):
        canonical_in = self._canonical(["S001"])
        catalogo = {
            "cpus": [{"codigo": "CPU-1", "producao_id_ref": "PROD-1"}],
            "producoes": [
                {
                    "id": "PROD-1",
                    "composicao_padrao_equipe": {
                        "equipamentos": [
                            {
                                "equip_id": "EQ-1",
                                "num_unidades": 1,
                                "custo_mobilizacao": 6500.0,
                                "custo_desmobilizacao": 6500.0,
                            }
                        ]
                    },
                }
            ],
        }
        result = self._fn()(canonical_in, catalogo)
        assert result is not None
        tipo = next(iter(result["activities"][0]["required_resources"]))
        assert result["resource_costs"][tipo]["custo_mob_unit"] == pytest.approx(6500.0)
        assert result["resource_costs"][tipo]["custo_demob_unit"] == pytest.approx(6500.0)
        assert "custo_idle_semanal_unit" not in result["resource_costs"][tipo]


class TestResourceCostsAbsentTresCases:
    """ADR-176 F4: resource_costs_absent distingue 3 casos, não 2."""

    def _fn(self):
        return _load_helpers_a()._setup_contratos_context

    def test_chave_ausente_absent_true(self):
        _pool, _act, _itm, _eqmap, _delta, _costs, absent = self._fn()([], {"activities": [], "resource_pool": {}})
        assert absent is True

    def test_chave_vazia_explicita_absent_false_adr071(self):
        """Sentinela ADR-071: resource_costs={} explícito força monolítico."""
        _pool, _act, _itm, _eqmap, _delta, _costs, absent = self._fn()(
            [], {"activities": [], "resource_pool": {}, "resource_costs": {}}
        )
        assert absent is False

    def test_mob_demob_sem_idle_absent_true(self):
        """ADR-176 F4: resource_costs não-vazio mas sem idle para nenhum tipo —
        fallback de idle continua engajando."""
        rcpsp_spec = {
            "activities": [],
            "resource_pool": {},
            "resource_costs": {"TIPO-X": {"custo_mob_unit": 6500.0, "custo_demob_unit": 6500.0}},
        }
        _pool, _act, _itm, _eqmap, _delta, _costs, absent = self._fn()([], rcpsp_spec)
        assert absent is True

    def test_com_idle_explicito_absent_false(self):
        rcpsp_spec = {
            "activities": [],
            "resource_pool": {},
            "resource_costs": {"TIPO-X": {"custo_idle_semanal_unit": 2000.0}},
        }
        _pool, _act, _itm, _eqmap, _delta, _costs, absent = self._fn()([], rcpsp_spec)
        assert absent is False
