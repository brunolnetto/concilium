"""Testes ADR-162 Fase 1 (D1) — causa_dominante: decomposição causal Cronograma × Precificação.

Cobre `_pe_causa_dominante` (_ponto_equilibrio.py) e sua integração em
`_build_pe_for_equipe`/`_build_ponto_equilibrio` (_balanco_pe.py):
  - causa_dominante = "CRONOGRAMA" | "PRECIFICACAO" pela magnitude de T_cronograma/T_precificacao
  - "INDETERMINADO" quando H_i/ρ_i/custo_operacional_real não são resolvíveis
  - identidade T_cronograma + T_precificacao == delta (dentro de tolerância de arredondamento)
  - P5: nunca um diagnóstico antes do cronograma real (schedule ausente)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_helpers_path = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "src"
    / "concilium"
    / "application"
    / "skills"
    / "manifests"
    / "06-resultado-financeiro"
    / "_consolidacao"
    / "_skill_helpers"
    / "__init__.py"
)
_spec = importlib.util.spec_from_file_location("skill_adr162_helpers", _helpers_path)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
sys.modules["skill_adr162_helpers"] = _mod
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_pe_causa_dominante = _mod._pe_causa_dominante
_build_pe_for_equipe = _mod._build_pe_for_equipe
_build_ponto_equilibrio = _mod._build_ponto_equilibrio


REGIME = SimpleNamespace(horas_dia=8.0, dias_semana=6.0)


def _plan(qty: float, produtividade_catalogo: float, venda_sem_bdi: float | None = None) -> SimpleNamespace:
    """`venda_sem_bdi` só é necessário quando o plan passa por `_pe_plan_calibracao`
    (integração via `_build_pe_for_equipe`) — os testes unitários de `_pe_causa_dominante`
    chamam a função direto e não tocam `plan.subtotal`."""
    return SimpleNamespace(
        quantitativo=qty,
        produtividade_catalogo=produtividade_catalogo,
        subtotal=SimpleNamespace(sem_bdi=SimpleNamespace(total=venda_sem_bdi or 0.0)),
    )


class TestPeCausaDominanteIndeterminado:
    """DoD: INDETERMINADO quando H_i não resolvível — nunca um valor inventado."""

    def test_sem_produtividade_catalogo_retorna_indeterminado(self):
        """ρ_i=0 (Fonte 2/fallback de composição, issue #132) — sem base p/ γ_i^v."""
        plan = _plan(qty=1000.0, produtividade_catalogo=0.0)
        causa, t_cron, t_prec = _pe_causa_dominante(
            plan, custo_venda_total=500_000.0, custo_fixo_total=600_000.0,
            custo_operacional_real=700_000.0, machine_weeks_brutas=50.0,
            horas_dia=8.0, dias_semana=6.0,
        )
        assert causa == "INDETERMINADO"
        assert t_cron == 0.0
        assert t_prec == 0.0

    def test_custo_operacional_real_zero_retorna_indeterminado(self):
        plan = _plan(qty=1000.0, produtividade_catalogo=25.0)
        causa, t_cron, t_prec = _pe_causa_dominante(
            plan, custo_venda_total=500_000.0, custo_fixo_total=600_000.0,
            custo_operacional_real=0.0, machine_weeks_brutas=50.0,
            horas_dia=8.0, dias_semana=6.0,
        )
        assert causa == "INDETERMINADO"

    def test_sem_schedule_machine_weeks_zero_retorna_indeterminado(self):
        """P5: H_i real só existe pós-cronograma — machine_weeks_brutas=0 (sem schedule) -> INDETERMINADO."""
        plan = _plan(qty=1000.0, produtividade_catalogo=25.0)
        causa, t_cron, t_prec = _pe_causa_dominante(
            plan, custo_venda_total=500_000.0, custo_fixo_total=600_000.0,
            custo_operacional_real=700_000.0, machine_weeks_brutas=0.0,
            horas_dia=8.0, dias_semana=6.0,
        )
        assert causa == "INDETERMINADO"

    def test_sem_regime_horas_dia_zero_retorna_indeterminado(self):
        """Sem RegimeTrabalho (ex.: fixture antiga sem canonical_in.projeto) -> h·d=0 -> H_i=0."""
        plan = _plan(qty=1000.0, produtividade_catalogo=25.0)
        causa, t_cron, t_prec = _pe_causa_dominante(
            plan, custo_venda_total=500_000.0, custo_fixo_total=600_000.0,
            custo_operacional_real=700_000.0, machine_weeks_brutas=50.0,
            horas_dia=0.0, dias_semana=0.0,
        )
        assert causa == "INDETERMINADO"

    def test_plan_none_retorna_indeterminado(self):
        causa, t_cron, t_prec = _pe_causa_dominante(
            None, custo_venda_total=500_000.0, custo_fixo_total=600_000.0,
            custo_operacional_real=700_000.0, machine_weeks_brutas=50.0,
            horas_dia=8.0, dias_semana=6.0,
        )
        assert causa == "INDETERMINADO"


class TestPeCausaDominanteClassificacao:
    """DoD: CRONOGRAMA quando |T_cronograma| > |T_precificacao|, PRECIFICACAO no caso contrário."""

    def test_gap_puro_de_horas_e_cronograma(self):
        """ρ_i e taxas iguais nos dois lados (γ_v==γ_o), mas H_i real >> H_i catálogo
        (mais horas do que o catálogo previa) -> T_precificacao=0, T_cronograma domina."""
        # Q/ρ = 1000/25 = 40h catálogo. H_i real = 8*6*10 = 480h (bem mais que 40h).
        plan = _plan(qty=1000.0, produtividade_catalogo=25.0)
        # custo_fixo_total escolhido para que γ_o = custo_fixo_total/H_i == γ_v = custo_venda/H_i_cat
        custo_venda_total = 4_000.0  # γ_v = 4000/40 = 100 R$/h
        custo_fixo_total = 48_000.0  # γ_o = 48000/480 = 100 R$/h (mesma taxa)
        causa, t_cron, t_prec = _pe_causa_dominante(
            plan, custo_venda_total, custo_fixo_total,
            custo_operacional_real=48_000.0, machine_weeks_brutas=10.0,
            horas_dia=8.0, dias_semana=6.0,
        )
        assert t_prec == 0.0
        assert t_cron != 0.0
        assert causa == "CRONOGRAMA"

    def test_gap_puro_de_taxa_e_precificacao(self):
        """H_i real == H_i catálogo (mesmas horas), mas taxa real >> taxa de venda
        -> T_cronograma=0, T_precificacao domina."""
        # Q/ρ = 1000/25 = 40h catálogo. H_i real = 8*6*(40/48) semanas-equivalentes... para
        # simplificar, escolhe machine_weeks_brutas tal que H_i == 40h exatamente: 40/(8*6)=0.8333.
        plan = _plan(qty=1000.0, produtividade_catalogo=25.0)
        mwb = 40.0 / (8.0 * 6.0)
        custo_venda_total = 4_000.0  # γ_v = 4000/40 = 100 R$/h
        custo_fixo_total = 8_000.0  # γ_o = 8000/40 = 200 R$/h (taxa real 2x a de venda)
        causa, t_cron, t_prec = _pe_causa_dominante(
            plan, custo_venda_total, custo_fixo_total,
            custo_operacional_real=8_000.0, machine_weeks_brutas=mwb,
            horas_dia=8.0, dias_semana=6.0,
        )
        assert t_cron == 0.0
        assert t_prec != 0.0
        assert causa == "PRECIFICACAO"


class TestPeCausaDominanteIdentidade:
    """DoD: T_cronograma + T_precificacao == delta (custo_venda_total - custo_fixo_total),
    dentro de tolerância de arredondamento — mesmo padrão de ε_tol do roundtrip do ADR-061."""

    @pytest.mark.parametrize(
        ("qty", "rho", "venda", "fixo", "op_real", "mwb"),
        [
            (1000.0, 25.0, 500_000.0, 600_000.0, 700_000.0, 50.0),
            (2500.0, 12.5, 120_000.0, 95_000.0, 110_000.0, 22.0),
            (10.0, 0.5, 900.0, 850.0, 820.0, 3.0),
            (1000.0, 25.0, 600_000.0, 600_000.0, 600_000.0, 41.6667),  # ~delta=0
        ],
    )
    def test_identidade_sempre_vale(self, qty, rho, venda, fixo, op_real, mwb):
        plan = _plan(qty=qty, produtividade_catalogo=rho)
        causa, t_cron, t_prec = _pe_causa_dominante(
            plan, venda, fixo, op_real, mwb, horas_dia=8.0, dias_semana=6.0
        )
        assert causa != "INDETERMINADO"
        delta = round(venda - fixo, 2)
        assert round(t_cron + t_prec, 2) == pytest.approx(delta, abs=0.02)


class TestBuildPeForEquipeWiringAdr162:
    """Integração: causa_dominante chega no PontoEquilibrio final via _build_pe_for_equipe,
    alimentado por Planejamento.produtividade_catalogo e RegimeTrabalho — sem nenhum dos
    dois, cai em INDETERMINADO (nunca bloqueia o resto do PE)."""

    def _equipe(self):
        return SimpleNamespace(
            item_id="eap-01",
            cpu_id="CPU-01",
            custo_fixo_mensal=100_000.0,
            permanencia_meses=5.0,
            permanencia_efetiva_meses=6.0,
            custo_total=700_000.0,
            custo_total_autonomo=600_000.0,
            num_equipes_base=1,
        )

    def _sched_com_producao(self, num_equipes=2.0, semanas=10) -> SimpleNamespace:
        dist = {
            f"2026-W{i:02d}": SimpleNamespace(num_equipes=num_equipes, fator_clima=1.0, fator_calendario=1.0)
            for i in range(semanas)
        }
        return SimpleNamespace(distribuicao_semanal=dist)

    def test_sem_regime_fica_indeterminado_mas_pe_e_construido(self):
        plan = _plan(qty=1000.0, produtividade_catalogo=25.0)
        pe = _build_pe_for_equipe(
            self._equipe(),
            venda_por_item={"eap-01": 500_000.0},
            planejamento_por_item={"eap-01": plan},
            sched_por_item={"eap-01": self._sched_com_producao()},
            regime=None,
        )
        assert pe is not None
        assert pe.causa_dominante == "INDETERMINADO"
        assert pe.delta == 500_000.0 - 600_000.0  # PE em si não é afetado por causa_dominante

    def test_com_regime_e_produtividade_causa_dominante_resolvida(self):
        plan = _plan(qty=1000.0, produtividade_catalogo=25.0)
        pe = _build_pe_for_equipe(
            self._equipe(),
            venda_por_item={"eap-01": 500_000.0},
            planejamento_por_item={"eap-01": plan},
            sched_por_item={"eap-01": self._sched_com_producao()},
            regime=REGIME,
        )
        assert pe is not None
        assert pe.causa_dominante in ("CRONOGRAMA", "PRECIFICACAO")
        assert round(pe.t_cronograma + pe.t_precificacao, 2) == pytest.approx(pe.delta, abs=0.02)

    def test_sem_schedule_real_fica_indeterminado(self):
        """P5: sem sched_por_item (cronograma real ainda não montado) -> INDETERMINADO,
        nunca uma validação prospectiva de mobilização."""
        plan = _plan(qty=1000.0, produtividade_catalogo=25.0)
        pe = _build_pe_for_equipe(
            self._equipe(),
            venda_por_item={"eap-01": 500_000.0},
            planejamento_por_item={"eap-01": plan},
            sched_por_item=None,
            regime=REGIME,
        )
        assert pe is not None
        assert pe.causa_dominante == "INDETERMINADO"

    def test_build_ponto_equilibrio_thread_regime_do_canonical(self):
        """_build_ponto_equilibrio deriva regime de canonical_in.projeto.regime_trabalho
        automaticamente — nenhum caller externo precisa passá-lo manualmente."""
        equipe = self._equipe()
        plan = SimpleNamespace(
            item_id="eap-01",
            quantitativo=1000.0,
            produtividade_catalogo=25.0,
            subtotal=SimpleNamespace(sem_bdi=SimpleNamespace(total=500_000.0)),
        )
        sa = SimpleNamespace(
            activity_id="eap-01",
            distribuicao_semanal=self._sched_com_producao().distribuicao_semanal,
        )
        canonical_in = SimpleNamespace(
            projeto=SimpleNamespace(regime_trabalho=REGIME),
            planejamento=[plan],
            equipes_diretas=[equipe],
            cronograma=SimpleNamespace(scheduled_activities=[sa]),
            contratos_recurso=[],
            instancias_recurso=[],
        )
        validacoes: list = []
        result = _build_ponto_equilibrio(canonical_in, validacoes)
        assert len(result) == 1
        assert result[0].causa_dominante in ("CRONOGRAMA", "PRECIFICACAO")
