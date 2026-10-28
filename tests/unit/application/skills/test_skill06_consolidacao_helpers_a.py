"""Coverage sweep 12 — two files below 90%:

- _consolidacao/_skill_helpers_a.py (88%) — missing: 74->73, 164-165, 209, 212-214, 238, 273, 275, 293->295, etc.
- financial_report_pdf.py (89%) — missing: 273, 459->486, 464, 469, 472-477, 480-483, 516-517, etc.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

_ROOT = Path(__file__).resolve().parents[4]

_MANIFESTS = _ROOT / "src/concilium/application/skills/manifests"

def _load(mod_name: str, rel_path: str):
    path = _MANIFESTS / rel_path
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod

_cons = _load("_cons_helpers_sw12", "06-resultado-financeiro/_consolidacao/_skill_helpers/__init__.py")
CONSOL = _cons


# ── _consolidacao/_skill_helpers_a.py ─────────────────────────────────────────


class TestCpuFamilia:
    def test_empty_string_returns_empty(self):
        """Line 209: cpu_id is empty → return ''."""
        assert _cons._cpu_familia("") == ""

    def test_dash_separator_returns_prefix(self):
        """Line 211: '-' in cpu_id → split on '-'."""
        assert _cons._cpu_familia("CPU-001") == "CPU"

    def test_underscore_separator_returns_prefix(self):
        """Lines 212-213: '_' in cpu_id → split on '_'."""
        assert _cons._cpu_familia("ESC_HIDRA") == "ESC"

    def test_no_separator_returns_whole(self):
        """Line 214: no '-' or '_' → return cpu_id unchanged."""
        assert _cons._cpu_familia("CPUX") == "CPUX"


class TestCalcVendaComBdiMissingRate:
    def _make_empty_canonical(self):
        return SimpleNamespace(
            contratos_recurso=[],
            equipes_diretas=[],
            indiretos=[],
        )

    def test_missing_bdi_rate_logs_warning_returns_zero(self):
        """Lines 163-165: _bdi called with missing key → warning + return 0.0."""
        canonical = self._make_empty_canonical()
        bdi_rates = {}  # no keys → every lookup triggers the warning branch
        vd, vi, ct = _cons._calc_venda_com_bdi(canonical, bdi_rates)
        assert vd == 0.0
        assert vi == 0.0
        assert ct == 0.0

    def test_uses_prebuilt_activity_artifacts_without_rebuilding(self):
        from concilium.domain.models.canonical import AtividadeCustoCompleto

        canonical = self._make_empty_canonical()
        artifacts = [
            AtividadeCustoCompleto(
                atividade_id="EAP-01",
                semana_inicio=0,
                semana_fim=0,
                custo_operacional_direto=100.0,
                custo_direto_com_bdi=120.0,
            )
        ]
        with patch.object(_cons, "_build_custos_atividades", side_effect=AssertionError("must not rebuild")):
            venda_direta, _venda_indireta, _custo_indireto = _cons._calc_venda_com_bdi(
                canonical,
                {"mao_obra": 0.0, "equipamentos": 0.0, "material": 0.0, "indireto": 0.0},
                custos_atividades=artifacts,
            )

        assert venda_direta == 120.0

    def test_prices_activity_mobilization_as_indirect_cost(self):
        from concilium.domain.models.canonical import (
            AtividadeCustoCompleto,
            InsumoComponenteAtividade,
            MobilizacaoAtividade,
        )

        canonical = self._make_empty_canonical()
        artifacts = [
            AtividadeCustoCompleto(
                atividade_id="EAP-01",
                semana_inicio=0,
                semana_fim=0,
                mobilizacao=MobilizacaoAtividade(
                    atividade_id="EAP-01",
                    fase="both",
                    equipamentos=InsumoComponenteAtividade(nome="MOB_DEMOB", custo_total=100.0),
                ),
            )
        ]

        venda_direta, venda_indireta, custo_indireto = _cons._calc_venda_com_bdi(
            canonical,
            {"mao_obra": 0.0, "equipamentos": 0.0, "material": 0.0, "indireto": 0.25},
            custos_atividades=artifacts,
        )

        assert venda_direta == 0.0
        assert venda_indireta == 125.0
        assert custo_indireto == 0.0


class TestValidateAcAdmSobreposicao:
    """Issue #126: VAL-BDI-AC-ADM-POSSIVEL-SOBREPOSICAO — validação puramente
    informativa (AVISO, nunca ERRO, nunca bloqueia) de possível sobreposição entre
    o componente `ac` do BDI e o custo real de indireto categoria ADM.
    """

    _CUSTO_OPERACIONAL = 1_000_000.0

    def test_ambos_significativos_dispara_aviso(self):
        """AC embutido (5% × 1MM = 50k = 5%) e ADM real (50k = 5%) acima do limiar de 2%."""
        validacoes: list = []
        _cons._validate_ac_adm_sobreposicao(
            0.05, 1_000_000.0, 50_000.0, self._CUSTO_OPERACIONAL, validacoes
        )
        assert any(
            v.codigo == "VAL-BDI-AC-ADM-POSSIVEL-SOBREPOSICAO" and v.status == "AVISO" for v in validacoes
        )

    def test_somente_ac_significativo_nao_dispara(self):
        """AC embutido = 5% (> limiar) mas ADM real = 0,5% (< limiar) — não dispara."""
        validacoes: list = []
        _cons._validate_ac_adm_sobreposicao(
            0.05, 1_000_000.0, 5_000.0, self._CUSTO_OPERACIONAL, validacoes
        )
        assert all(v.codigo != "VAL-BDI-AC-ADM-POSSIVEL-SOBREPOSICAO" for v in validacoes)

    def test_somente_adm_significativo_nao_dispara(self):
        """ADM real = 5% (> limiar) mas AC embutido = 0,1% (< limiar) — não dispara."""
        validacoes: list = []
        _cons._validate_ac_adm_sobreposicao(
            0.001, 1_000_000.0, 50_000.0, self._CUSTO_OPERACIONAL, validacoes
        )
        assert all(v.codigo != "VAL-BDI-AC-ADM-POSSIVEL-SOBREPOSICAO" for v in validacoes)

    def test_nenhum_significativo_nao_dispara(self):
        """Ambos abaixo do limiar de 2% — não dispara."""
        validacoes: list = []
        _cons._validate_ac_adm_sobreposicao(
            0.001, 1_000_000.0, 5_000.0, self._CUSTO_OPERACIONAL, validacoes
        )
        assert all(v.codigo != "VAL-BDI-AC-ADM-POSSIVEL-SOBREPOSICAO" for v in validacoes)

    def test_custo_operacional_zero_nao_dispara(self):
        """Guard: custo_operacional_real <= 0 → retorna sem calcular (evita ZeroDivisionError)."""
        validacoes: list = []
        _cons._validate_ac_adm_sobreposicao(0.05, 1_000_000.0, 50_000.0, 0.0, validacoes)
        assert validacoes == []

    def test_mensagem_menciona_ambos_valores(self):
        """A mensagem deve ser educativa e citar os dois valores/percentuais envolvidos."""
        validacoes: list = []
        _cons._validate_ac_adm_sobreposicao(
            0.05, 1_000_000.0, 50_000.0, self._CUSTO_OPERACIONAL, validacoes
        )
        msg = next(v.mensagem for v in validacoes if v.codigo == "VAL-BDI-AC-ADM-POSSIVEL-SOBREPOSICAO")
        assert "AC" in msg and "ADM" in msg
        assert "conceitos distintos" in msg


class TestBrBuildVendaCustoFallback:
    def _make_canonical_no_planejamento(self, custo_total=10_000.0):
        eq = SimpleNamespace(
            item_id="EAP-01",
            custo_total=custo_total,
        )
        SimpleNamespace(
            subtotal=SimpleNamespace(
                sem_bdi=SimpleNamespace(total=0.0, material=0.0),
                com_bdi=SimpleNamespace(total=0.0),
            )
        )
        return SimpleNamespace(
            planejamento=[],
            equipes_diretas=[eq],
        )

    def test_empty_planejamento_nonzero_equipes_triggers_fallback(self):
        """Lines 273, 275: venda_sem_bdi and venda_com_bdi both fall back to custo_direto_equipe."""
        canonical = self._make_canonical_no_planejamento(custo_total=5000.0)
        vsb, vcb, cde, cm, cdp = _cons._br_build_venda_custo(canonical)
        assert vsb == 5000.0
        assert vcb == 5000.0


class TestBuildCustoAtvFallback:
    def test_no_cronograma_no_equipes_returns_empty(self):
        """Lines 235-251: when cronograma is None and equipes_diretas has items with item_id."""
        canonical = SimpleNamespace(
            cronograma=None,
            equipes_diretas=[
                SimpleNamespace(item_id="EAP-01"),
                SimpleNamespace(item_id="EAP-02"),
            ],
            eap=[],
        )
        result = _cons._build_custos_atividades(canonical)
        assert len(result) == 2
        assert result[0].atividade_id == "EAP-01"

    def test_equipe_with_empty_item_id_skipped(self):
        """Line 238: equipe with empty item_id → continue."""
        canonical = SimpleNamespace(
            cronograma=None,
            equipes_diretas=[
                SimpleNamespace(item_id=""),
                SimpleNamespace(item_id="EAP-03"),
            ],
            eap=[],
        )
        result = _cons._build_custos_atividades(canonical)
        assert len(result) == 1
        assert result[0].atividade_id == "EAP-03"


class TestBuildActivityDirectCost:
    def test_weekly_costs_follow_formal_catalog_rates(self):
        activity = SimpleNamespace(
            distribuicao_semanal={
                "2026-W01": SimpleNamespace(num_equipes=1.0, qtd_executada=10.0),
                "2026-W02": SimpleNamespace(num_equipes=2.0, qtd_executada=30.0),
            }
        )
        equipe = SimpleNamespace(
            produtividade_horaria=10.0,
            horas_dia=8.0,
            dias_semana=5.0,
            gamma_mao_obra_catalogo=2.0,
            gamma_equipamentos_catalogo=3.0,
            gamma_material_catalogo=1.0,
            gamma_combustivel_catalogo=0.5,
        )

        components, weekly, operational, _direct_bdi, _equivalent_bdi = _cons._build_activity_direct_cost(
            activity, equipe, {}
        )

        assert weekly[0].custo_contratual == pytest.approx(200.0)
        assert weekly[1].custo_contratual == pytest.approx(400.0)
        assert weekly[0].custo_variavel == pytest.approx(1.5)
        assert weekly[1].custo_variavel == pytest.approx(4.5)
        assert operational == pytest.approx(606.0)
        assert components[0].custo_total_direto == pytest.approx(606.0)

    def test_operational_pricing_uses_instancial_costs_not_catalog_gamma(self):
        """Catalogue gamma must not inflate actual sale with real Skill05 costs."""
        act = SimpleNamespace(
            distribuicao_semanal={
                "2026-W01": SimpleNamespace(num_equipes=1.0, qtd_executada=10.0),
                "2026-W02": SimpleNamespace(num_equipes=2.0, qtd_executada=30.0),
            }
        )
        equipe = SimpleNamespace(
            custo_inst_mo=100.0,
            custo_inst_eq=50.0,
            custo_inst_mat=30.0,
            custo_inst_comb=20.0,
            contrato_tipo_id="POOL-RESOURCES",  # aggregate measured pool postings
            produtividade_horaria=10.0,
            horas_dia=8.0,
            dias_semana=5.0,
            # Materially different catalog rates; they are only a reference
            # and cannot be charged as the *operational* sale base.
            gamma_mao_obra_catalogo=10000.0,
            gamma_equipamentos_catalogo=25000.0,
            gamma_material_catalogo=1000.0,
            gamma_combustivel_catalogo=1000.0,
        )
        rates = {
            "mao_obra": 0.10,
            "equipamentos": 0.20,
            "material": 0.05,
            "diesel": 0.04,
        }
        _components, weeks, cost, price, _bdi = _cons._build_activity_direct_cost(
            act, equipe, rates
        )
        expected_price = 100 * 1.10 + 50 * 1.20 + 30 * 1.05 + 20 * 1.04
        assert cost == pytest.approx(200.0)
        assert price == pytest.approx(expected_price)
        assert sum(w.custo_operacional for w in weeks) == pytest.approx(cost)
        assert sum(w.custo_operacional_com_bdi for w in weeks) == pytest.approx(price)
        assert sum(w.custo_variavel for w in weeks) == pytest.approx(50.0)
        assert weeks[0].custo_contratual == pytest.approx(50.0)
        assert weeks[1].custo_contratual == pytest.approx(100.0)

    def test_completed_f3_without_pool_multifront_uses_aggregate_schedule(self):
        """F3 components are one-front, even when all four fields are populated."""
        activity = SimpleNamespace(
            distribuicao_semanal={
                "2026-W01": SimpleNamespace(num_equipes=2.0, qtd_executada=20.0),
            }
        )
        team = SimpleNamespace(
            contrato_tipo_id="",
            num_equipes_base=2,
            custo_total=200.0,  # one-front F3 reference
            custo_operacional_agregado=400.0,  # two actual fronts
            custo_inst_mo=100.0,
            custo_inst_eq=100.0,
            custo_inst_mat=0.0,
            custo_inst_comb=0.0,
            produtividade_horaria=10.0,
            horas_dia=8.0,
            dias_semana=5.0,
            gamma_mao_obra_catalogo=2.5,  # 100 per front per 40h week
            gamma_equipamentos_catalogo=2.5,
            gamma_material_catalogo=0.0,
            gamma_combustivel_catalogo=0.0,
        )
        components, weekly, total, sale, _ = _cons._build_activity_direct_cost(
            activity, team, {
                "mao_obra": 0.0, "equipamentos": 0.0,
                "material": 0.0, "diesel": 0.0,
            }
        )
        assert total == pytest.approx(team.custo_operacional_agregado)
        assert sale == pytest.approx(400.0)
        assert weekly[0].custo_mao_obra == pytest.approx(200.0)
        assert weekly[0].custo_equipamentos == pytest.approx(200.0)
        assert components[0].custo_total_direto == pytest.approx(400.0)

    def test_completed_f3_nonpool_multifront_without_gamma_scales_active_week_reference(self):
        """Fallback without catalog rates must not silently sell one front."""
        activity = SimpleNamespace(
            distribuicao_semanal={
                "2026-W01": SimpleNamespace(num_equipes=1.0, qtd_executada=10.0),
                "2026-W02": SimpleNamespace(num_equipes=3.0, qtd_executada=30.0),
            }
        )
        team = SimpleNamespace(
            contrato_tipo_id="",
            custo_inst_mo=80.0,
            custo_inst_eq=40.0,
            custo_inst_mat=0.0,
            custo_inst_comb=0.0,
            produtividade_horaria=0.0,
            horas_dia=8.0,
            dias_semana=5.0,
        )
        _components, weekly, total, sale, _ = _cons._build_activity_direct_cost(
            activity, team, {
                "mao_obra": 0.0, "equipamentos": 0.0,
                "material": 0.0, "diesel": 0.0,
            }
        )
        # One-front F3 sum=120 across two active weeks; four team-weeks
        # require twice the amount across the same two calendar weeks.
        assert total == pytest.approx(240.0)
        assert sale == pytest.approx(240.0)
        assert sum(w.custo_operacional for w in weekly) == pytest.approx(total)
        assert weekly[0].custo_contratual == pytest.approx(60.0)
        assert weekly[1].custo_contratual == pytest.approx(180.0)

    def test_nonpool_f3_fractional_front_uses_fractional_schedule(self):
        """F3 one-front postings cannot charge a full front for 0.5 effective fronts."""
        activity = SimpleNamespace(
            distribuicao_semanal={
                "2026-W01": SimpleNamespace(num_equipes=0.5, qtd_executada=5.0),
            }
        )
        team = SimpleNamespace(
            contrato_tipo_id="",
            custo_inst_mo=100.0,
            custo_inst_eq=100.0,
            custo_inst_mat=0.0,
            custo_inst_comb=0.0,
            produtividade_horaria=10.0,
            horas_dia=8.0,
            dias_semana=5.0,
            gamma_mao_obra_catalogo=2.5,
            gamma_equipamentos_catalogo=2.5,
            gamma_material_catalogo=0.0,
            gamma_combustivel_catalogo=0.0,
        )
        _components, weekly, cost, sale, _ = _cons._build_activity_direct_cost(
            activity, team, {
                "mao_obra": 0.0, "equipamentos": 0.0,
                "material": 0.0, "diesel": 0.0,
            }
        )
        assert cost == pytest.approx(100.0)
        assert sale == pytest.approx(100.0)
        assert weekly[0].frentes == pytest.approx(0.5)

    @pytest.mark.parametrize("has_catalog_rates", [False, True])
    def test_planning_reconciled_f3_is_aggregate_even_with_two_fronts(
        self, has_catalog_rates
    ):
        """P2: F3 after Skill05 planning override must never multiply costs twice."""
        activity = SimpleNamespace(
            distribuicao_semanal={
                "2026-W01": SimpleNamespace(num_equipes=2.0, qtd_executada=20.0),
            }
        )
        team = SimpleNamespace(
            contrato_tipo_id="",
            custo_reconciliado_planejamento=True,
            num_equipes_base=2,
            custo_total=400.0,
            custo_operacional_agregado=400.0,
            # Skill05 F3 allocated an already reconciled, aggregate P&L
            # subtotal, not the default one-front cost.
            custo_inst_mo=200.0,
            custo_inst_eq=200.0,
            custo_inst_mat=0.0,
            custo_inst_comb=0.0,
            produtividade_horaria=10.0,
            horas_dia=8.0,
            dias_semana=5.0,
            gamma_mao_obra_catalogo=30.0 if has_catalog_rates else 0.0,
            gamma_equipamentos_catalogo=30.0 if has_catalog_rates else 0.0,
            gamma_material_catalogo=0.0,
            gamma_combustivel_catalogo=0.0,
        )
        _components, weeks, direct_cost, sale, _ = _cons._build_activity_direct_cost(
            activity, team, {
                "mao_obra": 0.0, "equipamentos": 0.0,
                "material": 0.0, "diesel": 0.0,
            }
        )
        assert direct_cost == pytest.approx(400.0)
        assert sale == pytest.approx(400.0)
        assert weeks[0].custo_operacional == pytest.approx(400.0)
        assert weeks[0].frentes == pytest.approx(2.0)

    def test_pool_backed_reconciled_flag_does_not_rescale_measured_components(self):
        """Pool postings remain authoritative if a prior planning flag survives allocation."""
        activity = SimpleNamespace(
            distribuicao_semanal={
                "2026-W01": SimpleNamespace(num_equipes=2.0, qtd_executada=20.0),
            }
        )
        team = SimpleNamespace(
            contrato_tipo_id="POOL-RESOURCES",
            custo_reconciliado_planejamento=True,
            num_equipes_base=2,
            custo_total=200.0,
            # The planning subtotal is stale after pool allocation. The four
            # instancial fields are now measured pool postings and sum to 200.
            custo_operacional_agregado=400.0,
            custo_inst_mo=100.0,
            custo_inst_eq=100.0,
            custo_inst_mat=0.0,
            custo_inst_comb=0.0,
            produtividade_horaria=10.0,
            horas_dia=8.0,
            dias_semana=5.0,
            gamma_mao_obra_catalogo=30.0,
            gamma_equipamentos_catalogo=30.0,
            gamma_material_catalogo=0.0,
            gamma_combustivel_catalogo=0.0,
        )
        _components, weeks, direct_cost, sale, _ = _cons._build_activity_direct_cost(
            activity, team, {
                "mao_obra": 0.0, "equipamentos": 0.0,
                "material": 0.0, "diesel": 0.0,
            }
        )
        assert direct_cost == pytest.approx(200.0)
        assert sale == pytest.approx(200.0)
        assert weeks[0].custo_operacional == pytest.approx(200.0)

    def test_heuristic_nonpool_cost_does_not_suppress_material_gamma(self):
        """Incomplete non-pool aggregate is not complete physical K/V evidence."""
        activity = SimpleNamespace(
            distribuicao_semanal={
                "2026-W01": SimpleNamespace(num_equipes=1.0, qtd_executada=1.0),
            }
        )
        equipe = SimpleNamespace(
            custo_inst_mo=None,
            custo_total=200.0,
            custo_operacional_agregado=200.0,
            custo_mao_obra_mensal=100.0,
            custo_encargos_mensal=0.0,
            custo_equipamentos_mensal=100.0,
            custo_material_mensal=100.0,
            custo_combustivel_total_mensal=0.0,
            produtividade_horaria=1.0,
            horas_dia=2.0,
            dias_semana=5.0,
            gamma_mao_obra_catalogo=10.0,
            gamma_equipamentos_catalogo=10.0,
            gamma_material_catalogo=100.0,
            gamma_combustivel_catalogo=0.0,
        )
        # Heuristic proportions would incorrectly scale 100/100/100 into
        # 66.67/66.67/66.67 to fit the aggregate 200, dropping material.
        # Explicit gamma computes K=200 + V=100 until a complete
        # instancial breakdown becomes available.
        components, weeks, operational, price, _ = _cons._build_activity_direct_cost(
            activity, equipe, {
                "mao_obra": 0.0, "equipamentos": 0.0,
                "material": 0.0, "diesel": 0.0,
            }
        )
        assert operational == pytest.approx(300.0)
        assert price == pytest.approx(300.0)
        assert weeks[0].custo_material == pytest.approx(100.0)
        assert components[0].custo_total_direto == pytest.approx(300.0)

    def test_variable_cost_is_invariant_under_extra_unproductive_team_week(self):
        equipe = SimpleNamespace(
            produtividade_horaria=10.0,
            horas_dia=8.0,
            dias_semana=5.0,
            gamma_mao_obra_catalogo=2.0,
            gamma_equipamentos_catalogo=3.0,
            gamma_material_catalogo=1.0,
            gamma_combustivel_catalogo=0.5,
        )
        sem_espera = SimpleNamespace(
            distribuicao_semanal={"2026-W01": SimpleNamespace(num_equipes=1.0, qtd_executada=10.0)}
        )
        com_espera = SimpleNamespace(
            distribuicao_semanal={
                "2026-W01": SimpleNamespace(num_equipes=1.0, qtd_executada=0.0),
                "2026-W02": SimpleNamespace(num_equipes=1.0, qtd_executada=10.0),
            }
        )

        _components_base, weekly_base, _operational_base, _bdi_base, _eq_base = _cons._build_activity_direct_cost(
            sem_espera, equipe, {}
        )
        _components_wait, weekly_wait, _operational_wait, _bdi_wait, _eq_wait = _cons._build_activity_direct_cost(
            com_espera, equipe, {}
        )

        assert sum(cost.custo_variavel for cost in weekly_wait) == pytest.approx(
            sum(cost.custo_variavel for cost in weekly_base)
        )
        assert sum(cost.custo_contratual for cost in weekly_wait) == pytest.approx(
            2 * sum(cost.custo_contratual for cost in weekly_base)
        )

    def test_weekly_costs_conserve_components_and_activity_bdi(self):
        """K rateia por frente-semana, V por quantidade, sem perda por arredondamento."""
        activity = SimpleNamespace(
            distribuicao_semanal={
                "2026-W01": SimpleNamespace(num_equipes=1.0, qtd_executada=1.0),
                "2026-W02": SimpleNamespace(num_equipes=1.0, qtd_executada=1.0),
                "2026-W03": SimpleNamespace(num_equipes=1.0, qtd_executada=1.0),
            }
        )
        equipe = SimpleNamespace(
            custo_inst_mo=100.0,
            custo_inst_eq=50.0,
            custo_inst_mat=30.0,
            custo_inst_comb=20.0,
            custo_inst_mob_demob=0.0,
        )
        rates = {"mao_obra": 0.10, "equipamentos": 0.20, "material": 0.05, "diesel": 0.05}

        _components, weekly, operational, direct_bdi, equivalent_bdi = _cons._build_activity_direct_cost(
            activity, equipe, rates
        )

        assert sum(cost.custo_mao_obra for cost in weekly) == pytest.approx(100.0)
        assert sum(cost.custo_equipamentos for cost in weekly) == pytest.approx(50.0)
        assert sum(cost.custo_material for cost in weekly) == pytest.approx(30.0)
        assert sum(cost.custo_combustivel for cost in weekly) == pytest.approx(20.0)
        assert sum(cost.custo_operacional for cost in weekly) == pytest.approx(operational)
        assert sum(cost.custo_operacional_com_bdi for cost in weekly) == pytest.approx(direct_bdi)
        assert equivalent_bdi == pytest.approx(direct_bdi / operational - 1)

    def test_mobilization_is_excluded_from_direct_components(self):
        activity = SimpleNamespace(
            distribuicao_semanal={"2026-W01": SimpleNamespace(num_equipes=1.0, qtd_executada=1.0)}
        )
        equipe = SimpleNamespace(
            custo_inst_mo=100.0,
            custo_inst_eq=50.0,
            custo_inst_mat=0.0,
            custo_inst_comb=0.0,
            custo_inst_mob_demob=25.0,
            custo_mob_desmob=25.0,
        )

        components, weekly, operational, _direct_bdi, _equivalent_bdi = _cons._build_activity_direct_cost(
            activity, equipe, {}
        )

        assert components[0].equipamentos.custo_total == 50.0
        assert operational == 150.0
        assert weekly[0].custo_operacional == 150.0


class TestBuildCustoCategoriaBottomUp:
    def test_part_with_zero_inst_not_added_to_part_by_item(self):
        """Line 74->73: part with all-zero custo_inst_* → if-condition False → skip."""
        from types import SimpleNamespace

        part = SimpleNamespace(
            item_id="EAP-01",
            custo_inst_mo=0.0,
            custo_inst_eq=0.0,
            custo_inst_comb=0.0,
            custo_inst_mat=0.0,
        )
        contrato = SimpleNamespace(particao_por_item=[part])
        eq = SimpleNamespace(
            item_id="EAP-01",
            custo_total=1000.0,
            custo_inst_mo=None,
            custo_mao_obra_mensal=500.0,
            custo_equipamentos_mensal=200.0,
            custo_combustivel_total_mensal=100.0,
            custo_material_mensal=50.0,
        )
        # getattr needed for custo_encargos_mensal
        eq.custo_encargos_mensal = 0.0
        canonical = SimpleNamespace(
            contratos_recurso=[contrato],
            equipes_diretas=[eq],
        )
        result = _cons._build_custo_categorial_bottom_up(canonical)
        # EAP-01 should appear in the heuristic path, not the pool path
        assert result["mao_obra"] > 0.0





# _consolidacao/_skill_helpers_a.py
# ===========================================================================


class TestAsBool:
    """Lines 967-978: _as_bool conversion."""

    def test_bool_true(self):
        assert CONSOL._as_bool(True) is True

    def test_bool_false(self):
        assert CONSOL._as_bool(False) is False

    def test_int_nonzero(self):
        assert CONSOL._as_bool(1) is True

    def test_int_zero(self):
        assert CONSOL._as_bool(0) is False

    def test_str_true_values(self):
        """Lines 973-975: truthy strings → True."""
        for v in ("1", "true", "t", "yes", "y", "on", "True", " YES "):
            assert CONSOL._as_bool(v) is True, f"Expected True for {v!r}"

    def test_str_false_values(self):
        """Lines 976-977: falsy strings → False."""
        for v in ("0", "false", "f", "no", "n", "off", "", " "):
            assert CONSOL._as_bool(v) is False, f"Expected False for {v!r}"

    def test_unrecognized_string_returns_false(self):
        """Line 978 fallthrough: unrecognized string → False."""
        assert CONSOL._as_bool("maybe") is False

    def test_none_returns_false(self):
        assert CONSOL._as_bool(None) is False


class TestValidatePeDuploRisco:
    """Lines 728-741: _validate_pe_duplo_risco."""

    def _make_pe(self, confianca: str, status: str = "ERRO") -> object:
        from concilium.domain.models.canonical import PontoEquilibrio

        return PontoEquilibrio(
            item_id="ITEM-01",
            custo_fixo_equipe=100_000.0,
            custo_venda_cpu=80_000.0,
            delta=-20_000.0,
            delta_pct=-0.2,
            status_validacao=status,
            confianca_pe=confianca,
        )

    def test_media_confianca_emits_aviso(self):
        """Line 730: confianca_pe == 'MEDIA' → severidade = 'AVISO'."""
        pe = self._make_pe("MEDIA", "ERRO")
        validacoes = []
        CONSOL._validate_pe_duplo_risco(pe, validacoes)
        assert len(validacoes) == 1
        assert validacoes[0].codigo == "VAL-PE-PU-DUPLO-RISCO"
        assert validacoes[0].status == "AVISO"

    def test_baixa_confianca_emits_erro(self):
        """Line 731: confianca_pe == 'BAIXA' → severidade = 'ERRO'."""
        pe = self._make_pe("BAIXA", "ERRO")
        validacoes = []
        CONSOL._validate_pe_duplo_risco(pe, validacoes)
        assert validacoes[0].status == "ERRO"

    def test_alta_confianca_no_emission(self):
        """Guard: 'ALTA' not in ('MEDIA', 'BAIXA') → no validacao emitted."""
        pe = self._make_pe("ALTA", "ERRO")
        validacoes = []
        CONSOL._validate_pe_duplo_risco(pe, validacoes)
        assert len(validacoes) == 0

    def test_status_ok_no_emission(self):
        """Guard: status_validacao != 'ERRO' → no emission."""
        pe = self._make_pe("MEDIA", "OK")
        validacoes = []
        CONSOL._validate_pe_duplo_risco(pe, validacoes)
        assert len(validacoes) == 0


class TestApmProcessFamilia:
    """Lines 839-860: _apm_process_familia downgrade ERRO → AVISO."""

    def _make_pe(self, delta: float, status: str = "ERRO") -> object:
        from concilium.domain.models.canonical import PontoEquilibrio

        return PontoEquilibrio(
            item_id="X",
            custo_fixo_equipe=100.0,
            custo_venda_cpu=120.0,
            delta=delta,
            delta_pct=delta / 100.0,
            status_validacao=status,
        )

    def test_single_row_returns_early(self):
        """Line 841-842: len(rows) < 2 → return immediately."""
        pe = self._make_pe(-10.0)
        validacoes = []
        CONSOL._apm_process_familia("FAM-A", [("X", pe)], validacoes)
        assert len(validacoes) == 0
        assert pe.status_validacao == "ERRO"  # unchanged

    def test_family_with_positive_aggregate_downgrades(self):
        """Lines 843-850: 2 rows, ERRO + OK, delta_fam >= 0 → ERRO downgraded to AVISO."""
        pe_err = self._make_pe(-10.0, "ERRO")
        pe_ok = self._make_pe(50.0, "OK")
        validacoes = []
        CONSOL._apm_process_familia("FAM-B", [("A", pe_err), ("B", pe_ok)], validacoes)
        assert pe_err.status_validacao == "AVISO"
        assert len(validacoes) == 1
        assert validacoes[0].codigo == "VAL-PONTO-EQUILIBRIO-MITIGACAO"

    def test_all_negative_aggregate_no_downgrade(self):
        """Guard: erros_fam exists but delta_fam < 0 → no downgrade."""
        pe1 = self._make_pe(-100.0, "ERRO")
        pe2 = self._make_pe(-50.0, "ERRO")
        validacoes = []
        CONSOL._apm_process_familia("FAM-C", [("A", pe1), ("B", pe2)], validacoes)
        assert pe1.status_validacao == "ERRO"
        assert len(validacoes) == 0


class TestBpeProcessEquipe:
    """Line 882: _bpe_process_equipe returns None when equipe.item_id is falsy."""

    def test_empty_item_id_returns_none(self):
        """Line 882: not equipe.item_id → return None."""
        equipe = SimpleNamespace(item_id="", custo_total=0.0, funcoes=[])
        result = CONSOL._bpe_process_equipe(equipe, venda_por_item={}, validacoes=[])
        assert result is None

    def test_none_item_id_returns_none(self):
        equipe = SimpleNamespace(item_id=None, custo_total=0.0, funcoes=[])
        result = CONSOL._bpe_process_equipe(equipe, venda_por_item={}, validacoes=[])
        assert result is None


class TestApmBuildFamiliaRows:
    """Line 862: `if fam:` — item sem cpu_id resolvível não entra em nenhuma família."""

    def _make_pe(self) -> object:
        from concilium.domain.models.canonical import PontoEquilibrio

        return PontoEquilibrio(
            item_id="X",
            custo_fixo_equipe=100.0,
            custo_venda_cpu=120.0,
            delta=10.0,
            delta_pct=0.1,
            status_validacao="OK",
        )

    def test_equipe_ausente_gera_familia_vazia(self):
        """eq is None → fam = _cpu_familia("") = "" → branch `if fam` é False."""
        pe = self._make_pe()
        rows = CONSOL._apm_build_familia_rows({"X": pe}, equipe_by_item={})
        assert rows == {}

    def test_equipe_sem_cpu_id_gera_familia_vazia(self):
        """eq.cpu_id vazio → fam == "" → item não é agrupado."""
        pe = self._make_pe()
        equipe = SimpleNamespace(item_id="X", cpu_id="")
        rows = CONSOL._apm_build_familia_rows({"X": pe}, equipe_by_item={"X": equipe})
        assert rows == {}

    def test_equipe_com_cpu_id_agrupa_por_familia(self):
        pe = self._make_pe()
        equipe = SimpleNamespace(item_id="X", cpu_id="CPU-DREN-01")
        rows = CONSOL._apm_build_familia_rows({"X": pe}, equipe_by_item={"X": equipe})
        assert "CPU" in rows
        assert rows["CPU"] == [("X", pe)]


# ===========================================================================
# _indiretos/_skill_helpers_b.py
# ===========================================================================



