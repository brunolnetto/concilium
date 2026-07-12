"""ADR-137 item 1 — Split real de mob/demob no breakdown semanal de indiretos.

TDD: testes escritos antes da implementação.

Contexto: _breakdown_mob() (skill 06, categoria MOB) sempre dividia o custo
50/50 entre a semana 0 e a última semana, independente de quanto do custo real
vem de itens de mobilização vs. desmobilização (quando `_custo_mob_composicional`
constrói `mobilizacoes: list[Mobilizacao]` com `descricao`/`custo_total` por
item — ver `_mob.py`). Este teste cobre a nova proporção real, com fallback
retrocompatível para 50/50 quando não há itens distinguíveis (ex.: custo
pré-agregado via `categorias_config`, caminho usado por todos os benchmarks
reais atuais).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent

_HELPERS = (
    _ROOT
    / "src/concilium/application/skills/manifests/06-resultado-financeiro/_indiretos/_skill_helpers/_breakdown.py"
)

sys.path.insert(0, str(_ROOT / "src"))


def _load_breakdown() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_indiretos_breakdown", _HELPERS)
    assert spec and spec.loader, f"Não encontrou {_HELPERS}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_indiretos_breakdown"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _make_categoria(custo_total: float):
    from concilium.domain.models.canonical import IndirectoCategoria

    return IndirectoCategoria(categoria="MOB", driver="one_time", custo_fixo_total=custo_total)


def _make_mob(descricao: str, custo_total: float):
    from concilium.domain.models.canonical import Mobilizacao

    return Mobilizacao(
        descricao=descricao,
        num_unidades=1,
        origem="A",
        destino="B",
        distancia_km=100.0,
        custo_km=custo_total / 100.0,
        custo_total=custo_total,
    )


class TestBreakdownMobSplitReal:
    def test_sem_mobs_fallback_50_50(self):
        """Retrocompat: sem itens de mobilizacoes distinguíveis, mantém 50/50."""
        mod = _load_breakdown()
        result = mod._breakdown_mob(_make_categoria(100_000.0), n_semanas=12)
        assert result[0].custo_semanal == pytest.approx(50_000.0)
        assert result[-1].custo_semanal == pytest.approx(50_000.0)

    def test_mobs_vazia_fallback_50_50(self):
        """mobs=[] (lista vazia) também cai no fallback 50/50."""
        mod = _load_breakdown()
        result = mod._breakdown_mob(_make_categoria(100_000.0), n_semanas=12, mobs=[])
        assert result[0].custo_semanal == pytest.approx(50_000.0)
        assert result[-1].custo_semanal == pytest.approx(50_000.0)

    def test_proporcao_real_assimetrica(self):
        """Itens reais 70% mob / 30% demob → semana 0 e última refletem essa proporção."""
        mod = _load_breakdown()
        mobs = [
            _make_mob("Mobilização de equipamento pesado", 70_000.0),
            _make_mob("Desmobilização de equipamento pesado", 30_000.0),
        ]
        result = mod._breakdown_mob(_make_categoria(100_000.0), n_semanas=12, mobs=mobs)
        assert result[0].custo_semanal == pytest.approx(70_000.0)
        assert result[-1].custo_semanal == pytest.approx(30_000.0)

    def test_soma_fecha_com_custo_total(self):
        """Semana 0 + última semana == categoria.custo_fixo_total (invariante de fechamento)."""
        mod = _load_breakdown()
        mobs = [
            _make_mob("Mobilização", 12_345.67),
            _make_mob("Desmobilização", 3_210.98),
        ]
        categoria = _make_categoria(15_556.65)
        result = mod._breakdown_mob(categoria, n_semanas=8, mobs=mobs)
        soma = result[0].custo_semanal + result[-1].custo_semanal
        assert soma == pytest.approx(categoria.custo_fixo_total, abs=0.01)

    def test_semanas_intermediarias_zero(self):
        """Semanas que não são a primeira nem a última têm custo zero e ativa=False."""
        mod = _load_breakdown()
        mobs = [_make_mob("Mobilização", 60_000.0), _make_mob("Desmobilização", 40_000.0)]
        result = mod._breakdown_mob(_make_categoria(100_000.0), n_semanas=6, mobs=mobs)
        for semana in result[1:-1]:
            assert semana.custo_semanal == pytest.approx(0.0)
            assert semana.ativa is False

    def test_somente_mob_sem_demob_identificavel(self):
        """Todos os itens classificados como mob (sem 'desmob' na descrição) → fallback 50/50,
        pois não há dado real de proporção de desmobilização."""
        mod = _load_breakdown()
        mobs = [_make_mob("Transporte de equipamento", 100_000.0)]
        result = mod._breakdown_mob(_make_categoria(100_000.0), n_semanas=10, mobs=mobs)
        # bruto_total > 0 mas custo_demob_raw == 0 → ainda assim usamos a proporção real
        # (100% mob, 0% demob) — é o dado real disponível, não ausência de dado.
        assert result[0].custo_semanal == pytest.approx(100_000.0)
        assert result[-1].custo_semanal == pytest.approx(0.0)

    def test_build_semanal_breakdown_propaga_mobs(self):
        """_build_semanal_breakdown (entry point usado por _process_mob_categoria) aceita
        e propaga mobs para _breakdown_mob."""
        mod = _load_breakdown()
        mobs = [_make_mob("Mobilização", 80_000.0), _make_mob("Desmobilização", 20_000.0)]
        result = mod._build_semanal_breakdown(_make_categoria(100_000.0), n_semanas=10, mobs=mobs)
        assert result[0].custo_semanal == pytest.approx(80_000.0)
        assert result[-1].custo_semanal == pytest.approx(20_000.0)

    def test_build_semanal_breakdown_sem_mobs_retrocompat(self):
        """_build_semanal_breakdown sem o parâmetro mobs continua funcionando (retrocompat)."""
        mod = _load_breakdown()
        result = mod._build_semanal_breakdown(_make_categoria(100_000.0), n_semanas=10)
        assert result[0].custo_semanal == pytest.approx(50_000.0)
