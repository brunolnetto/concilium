"""ADR-137 D1 — Aviso quando o pool decide perpetuação com custo mob/demob zerado.

TDD: testes escritos antes da implementação.

Contexto: _build_perpetuation_chains cai (propositalmente) para o heurístico
baseado em tempo (gap <= delta_max) quando custo_mob_unit + custo_demob_unit == 0
(ex: rcpsp_spec derivado automaticamente do canônico nunca popula esses campos —
ver ADR-137 P1). Esse fallback é intencional, mas até agora não deixava rastro
algum na lista de validações — o usuário não tinha como saber que a decisão de
perpetuação estava sendo tomada sem qualquer base de custo real.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent

_HELPERS_A = _ROOT / "src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers/__init__.py"

sys.path.insert(0, str(_ROOT / "src"))


def _load_helpers_a() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_skill_helpers_a", _HELPERS_A)
    assert spec and spec.loader, f"Não encontrou {_HELPERS_A}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_skill_helpers_a"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _weeks(start: int, end: int) -> list[str]:
    return [f"2026-W{w:02d}" for w in range(start, end + 1)]


def _items(starts_ends: list[tuple[int, int]], required: int = 1) -> list[dict]:
    result = []
    for i, (s, e) in enumerate(starts_ends):
        result.append(
            {
                "item_id": f"act-{i + 1}",
                "required": required,
                "active_weeks": _weeks(s, e),
                "machine_weeks": (e - s + 1) * required,
                "start_idx": s,
                "end_idx": e + 1,
                "semana_inicio": f"2026-W{s:02d}",
                "semana_fim": f"2026-W{e:02d}",
            }
        )
    return result


class TestValPoolMobZero:
    def test_custo_zerado_emite_aviso(self):
        """custo_mob_unit=custo_demob_unit=0 e >1 item → emite VAL-POOL-MOB-ZERO."""
        mod = _load_helpers_a()
        validacoes: list = []
        mod._build_perpetuation_chains(
            tipo_id="ESC",
            items=_items([(1, 4), (8, 11)]),
            custo_mob_unit=0.0,
            custo_demob_unit=0.0,
            validacoes=validacoes,
        )
        codigos = [v.codigo for v in validacoes]
        assert "VAL-POOL-MOB-ZERO" in codigos
        aviso = next(v for v in validacoes if v.codigo == "VAL-POOL-MOB-ZERO")
        assert aviso.status == "AVISO"
        assert "ESC" in aviso.mensagem

    def test_custo_presente_nao_emite_aviso(self):
        """Com custo_mob_unit/custo_demob_unit > 0, não há fallback → sem aviso."""
        mod = _load_helpers_a()
        validacoes: list = []
        mod._build_perpetuation_chains(
            tipo_id="ESC",
            items=_items([(1, 4), (8, 11)]),
            custo_mob_unit=80_000.0,
            custo_demob_unit=40_000.0,
            validacoes=validacoes,
        )
        assert validacoes == []

    def test_sem_validacoes_nao_quebra(self):
        """validacoes=None (default) não deve levantar exceção — retrocompat."""
        mod = _load_helpers_a()
        chains = mod._build_perpetuation_chains(
            tipo_id="ESC",
            items=_items([(1, 4), (8, 11)]),
            custo_mob_unit=0.0,
            custo_demob_unit=0.0,
        )
        assert len(chains) >= 1

    def test_um_unico_item_nao_emite_aviso(self):
        """Sem decisão de gap real (1 único item), não há fallback ativo → sem aviso."""
        mod = _load_helpers_a()
        validacoes: list = []
        mod._build_perpetuation_chains(
            tipo_id="ESC",
            items=_items([(1, 4)]),
            custo_mob_unit=0.0,
            custo_demob_unit=0.0,
            validacoes=validacoes,
        )
        assert validacoes == []

    def test_build_contratos_recurso_propaga_aviso(self):
        """_build_contratos_recurso (chamador de produção) deve propagar o aviso
        até a lista de validações do skill quando o rcpsp_spec não traz custos."""
        mod = _load_helpers_a()

        class _Eq:
            def __init__(self, iid, c):
                self.item_id = iid
                self.custo_total = c

        equipes = [_Eq("act-1", 100_000.0), _Eq("act-2", 100_000.0)]

        class _Dist:
            def __init__(self, ne):
                self.num_equipes = ne

        class _Sched:
            def __init__(self, aid, weeks, ne):
                self.activity_id = aid
                self.distribuicao_semanal = {w: _Dist(ne) for w in weeks}

        rcpsp_spec = {
            "resource_pool": {"T4": 2},
            "activities": [
                {"item_id": "act-1", "required_resources": {"T4": 2}},
                {"item_id": "act-2", "required_resources": {"T4": 2}},
            ],
        }
        sched_lookup = {
            "act-1": _Sched("act-1", _weeks(1, 4), 2),
            "act-2": _Sched("act-2", _weeks(8, 11), 2),
        }
        validacoes: list = []
        mod._build_contratos_recurso(equipes, rcpsp_spec, sched_lookup, validacoes)
        codigos = [v.codigo for v in validacoes]
        assert "VAL-POOL-MOB-ZERO" in codigos
