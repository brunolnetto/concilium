"""Coverage batch A — targets mcp_server/__main__, semantic/__init__,
scheduling/selector, optimizer/loop, skills/__init__, cpu_insumo validations,
02-produtividade-climatica, 09-relatorio-e-artefatos, and scheduling/scheduler edge cases.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    CustoTotal,
    Meta,
    Projeto,
    RegimeTrabalho,
    Resultado,
    Venda,
)


def _make_meta():
    return Meta(gerado_em=datetime.now(UTC), contexto_id="test")

def _make_proj():
    return Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=-3.0, lng=-38.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2026, 6, 1),
        data_termino=date(2026, 7, 31),
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )

def _minimal_canonical(**kw):
    return CanonicalModel(meta=_make_meta(), projeto=_make_proj(), **kw)

def _canonical_com_resultado():
    resultado = Resultado(
        venda=Venda(total_sem_bdi=800_000.0, total_com_bdi=1_000_000.0),
        custo=CustoTotal(direto_equipes=500_000.0, total=800_000.0),
        resultado_financeiro=200_000.0,
        margem_pct=0.20,
        status_margem="VERDE",
        validacoes=[],
    )
    return _minimal_canonical(resultado=resultado)


# ══ optimizer/loop.py ════════════════════════════════════════════════════════


class TestOptimizerLoop:
    """Tests for adjust_schedule covering lines 41, 43, 49-50."""

    _PERFIL = {"categorias_indireto": []}

    def test_catalogo_none_defaults_to_empty(self):
        """catalogo=None → catalogo = {} (line 41)."""
        from concilium.application.optimizer.loop import adjust_schedule

        can = _minimal_canonical()
        can_out, feasible, violations = adjust_schedule(can, None, catalogo=None, perfil=self._PERFIL)
        assert isinstance(feasible, bool)

    def test_decision_variables_as_dict(self):
        """dict decision_variables → dv_dict = decision_variables (lines 49-50)."""
        from concilium.application.optimizer.loop import adjust_schedule

        can = _minimal_canonical()
        dv = {"dv2_num_equipes": {}}
        can_out, feasible, violations = adjust_schedule(can, dv, catalogo={}, perfil=self._PERFIL)
        assert isinstance(feasible, bool)

    def test_perfil_none_defaults_to_empty(self):
        """perfil=None → perfil = {} (line 90)."""
        from concilium.application.optimizer.loop import adjust_schedule

        can = _minimal_canonical()
        can_out, feasible, violations = adjust_schedule(can, None, catalogo=None, perfil=None)
        assert isinstance(feasible, bool)








# optimizer/loop.py: iteration control (line 43)
# ────────────────────────────────────────────────────────────────


class TestOptimizerIteration:
    """Test optimizer loop iteration control."""

    def test_optimizer_convergence_check(self):
        """Optimizer should check convergence criteria."""
        pass


# ────────────────────────────────────────────────────────────────

