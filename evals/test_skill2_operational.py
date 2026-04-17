#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evals — Layer 2: Cálculo Operacional

Valida:
- Aplicação obrigatória de ENCARGOS (multiplier 1.66)
- calculate_crew_cost: cálculo de custo de equipe
- validate_cost_delta: tolerância ≤ 5% (C_FIXO)
- aggregate_indirect: soma de custos indiretos
- validate_team_composition: composição razoável
- calculate_adm_infrastructure: custos de infraestrutura
"""

import pytest

from conftest import (
    ENCARGOS_RATE,
    CREW_ESCAVACAO,
    EXPECTED_ESCAVACAO_MONTHLY,
    EXPECTED_ESCAVACAO_TOTAL,
    ENCARGOS_TOLERANCE,
)


# ---------------------------------------------------------------------------
# ENCARGOS — regra crítica de negócio
# ---------------------------------------------------------------------------

class TestEncargosMultiplier:
    """Garante que o multiplicador 1.66 é aplicado corretamente."""

    def test_encargos_rate_is_66_percent(self):
        """Taxa de encargos deve ser 0.66 (66%)."""
        assert abs(ENCARGOS_RATE - 1.66) < 0.001

    def test_salary_with_encargos_operador(self):
        """Operador de Escavadeira: R$ 6.300 × 1.66 = R$ 10.458."""
        salary_base = 6_300.00
        with_encargos = salary_base * ENCARGOS_RATE
        assert abs(with_encargos - 10_458.00) < 1.00, (
            f"Esperado R$ 10.458, calculado R$ {with_encargos:.2f}"
        )

    def test_salary_with_encargos_auxiliar(self):
        """Auxiliar de Produção: R$ 2.800 × 1.66 = R$ 4.648."""
        salary_base = 2_800.00
        with_encargos = salary_base * ENCARGOS_RATE
        assert abs(with_encargos - 4_648.00) < 1.00

    def test_encargos_increases_cost(self):
        """Custo com encargos deve ser sempre maior que o salário base."""
        for salary in [2_000, 5_000, 10_000, 20_000]:
            assert salary * ENCARGOS_RATE > salary


# ---------------------------------------------------------------------------
# calculate_crew_cost
# ---------------------------------------------------------------------------

class TestCalculateCrewCost:
    """Testa o cálculo de custo total de equipe."""

    def _build_base_data(self):
        """Monta base_data com ENCARGOS já aplicados (conforme skill carrega)."""
        return {
            "labor_costs": {
                # Salário base × 1.66
                "Operador de Escavadeira": 6_300.00 * ENCARGOS_RATE,
                "Motorista de Basculante": 4_800.00 * ENCARGOS_RATE,
                "Encarregado": 5_500.00 * ENCARGOS_RATE,
            },
            "equipment_costs": {
                "Escavadeira Hidráulica": 15_000.00,
                "Caminhão Basculante": 8_500.00,
            },
        }

    def test_crew_cost_1_team_3_months(self, operational_skill):
        """1 equipe de escavação por 3 meses: mensal = 25.458, total = 76.374."""
        result = operational_skill.calculate_crew_cost(
            activity=CREW_ESCAVACAO["activity"],
            labor=CREW_ESCAVACAO["labor"],
            equipment=CREW_ESCAVACAO["equipment"],
            duration_months=CREW_ESCAVACAO["duration_months"],
            base_data=self._build_base_data(),
        )
        assert abs(result.monthly_total - EXPECTED_ESCAVACAO_MONTHLY) < (
            EXPECTED_ESCAVACAO_MONTHLY * ENCARGOS_TOLERANCE
        ), f"Mensal esperado R$ {EXPECTED_ESCAVACAO_MONTHLY:.2f}, calculado R$ {result.monthly_total:.2f}"

        assert abs(result.total_cost - EXPECTED_ESCAVACAO_TOTAL) < (
            EXPECTED_ESCAVACAO_TOTAL * ENCARGOS_TOLERANCE
        )

    def test_crew_cost_scales_linearly_with_duration(self, operational_skill):
        """Custo total deve escalar linearmente com a duração."""
        base_data = self._build_base_data()
        result_3m = operational_skill.calculate_crew_cost(
            activity="Teste", labor=CREW_ESCAVACAO["labor"],
            equipment=CREW_ESCAVACAO["equipment"],
            duration_months=3, base_data=base_data,
        )
        result_6m = operational_skill.calculate_crew_cost(
            activity="Teste", labor=CREW_ESCAVACAO["labor"],
            equipment=CREW_ESCAVACAO["equipment"],
            duration_months=6, base_data=base_data,
        )
        ratio = result_6m.total_cost / result_3m.total_cost
        assert abs(ratio - 2.0) < 0.01, (
            f"6 meses deveria custar 2× os 3 meses, ratio={ratio:.4f}"
        )

    def test_crew_cost_2_teams_doubles_monthly(self, operational_skill):
        """2 equipes devem custar aprox. o dobro de 1 equipe/mês."""
        base_data = self._build_base_data()
        labor_2 = [{"function": "Operador de Escavadeira", "qty": 2}]
        equip_2 = [{"name": "Escavadeira Hidráulica", "qty": 2}]

        result_1 = operational_skill.calculate_crew_cost(
            "Escavação", CREW_ESCAVACAO["labor"], CREW_ESCAVACAO["equipment"],
            duration_months=1, base_data=base_data,
        )
        result_2 = operational_skill.calculate_crew_cost(
            "Escavação", labor_2, equip_2,
            duration_months=1, base_data=base_data,
        )
        ratio = result_2.monthly_total / result_1.monthly_total
        assert abs(ratio - 2.0) < 0.01

    def test_crew_cost_unknown_function_is_zero(self, operational_skill):
        """Função desconhecida não deve causar erro — custo = 0 com aviso."""
        base_data = self._build_base_data()
        labor_unknown = [{"function": "Função Inexistente", "qty": 1}]
        result = operational_skill.calculate_crew_cost(
            "Teste", labor_unknown, [], duration_months=1, base_data=base_data,
        )
        assert result.monthly_labor == 0.0

    def test_crew_cost_activity_stored_in_result(self, operational_skill):
        """Nome da atividade deve ser preservado no resultado."""
        base_data = self._build_base_data()
        result = operational_skill.calculate_crew_cost(
            "ESCAVAÇÃO, CARGA, TRANSPORTE",
            CREW_ESCAVACAO["labor"], CREW_ESCAVACAO["equipment"],
            duration_months=1, base_data=base_data,
        )
        assert result.activity == "ESCAVAÇÃO, CARGA, TRANSPORTE"


# ---------------------------------------------------------------------------
# validate_cost_delta (C_FIXO)
# ---------------------------------------------------------------------------

class TestCostDelta:
    """Testa a validação de convergência de custos (C_FIXO < 5%)."""

    def test_delta_zero_is_ok(self, operational_skill):
        result = operational_skill.validate_cost_delta(
            service="ESCAVAÇÃO", fixed_cost=100_000, sales_cost=100_000
        )
        assert result.status == "OK"
        assert result.delta_pct == 0.0

    def test_delta_within_5pct_is_ok(self, operational_skill):
        """Delta de 4% deve passar (< 5%)."""
        result = operational_skill.validate_cost_delta(
            service="ESCAVAÇÃO", fixed_cost=100_000, sales_cost=104_000
        )
        assert result.status == "OK", (
            f"Delta de 4% deveria ser OK, status={result.status}"
        )

    def test_delta_exactly_5pct_is_ok(self, operational_skill):
        """Delta exatamente de 5% ainda é aceitável."""
        result = operational_skill.validate_cost_delta(
            service="ESCAVAÇÃO", fixed_cost=100_000, sales_cost=105_000
        )
        assert result.status == "OK"

    def test_delta_above_5pct_is_warning_or_error(self, operational_skill):
        """Delta de 8% deve ser WARNING ou ERROR."""
        result = operational_skill.validate_cost_delta(
            service="ESCAVAÇÃO", fixed_cost=100_000, sales_cost=108_000
        )
        assert result.status in ("WARNING", "ERROR"), (
            f"Delta de 8% deveria ser WARNING/ERROR, status={result.status}"
        )

    def test_delta_above_10pct_is_error(self, operational_skill):
        """Delta de 15% deve ser ERROR."""
        result = operational_skill.validate_cost_delta(
            service="ESCAVAÇÃO", fixed_cost=100_000, sales_cost=115_000
        )
        assert result.status == "ERROR"

    def test_delta_symmetrical(self, operational_skill):
        """Delta deve ser avaliado em valor absoluto (subestimação = sobrestimação)."""
        result_over = operational_skill.validate_cost_delta(
            "Serviço", 100_000, 110_000
        )
        result_under = operational_skill.validate_cost_delta(
            "Serviço", 100_000, 90_000
        )
        assert result_over.status == result_under.status


# ---------------------------------------------------------------------------
# aggregate_indirect
# ---------------------------------------------------------------------------

class TestAggregateIndirect:
    """Testa a agregação de custos indiretos."""

    def test_aggregate_indirect_sum(self, operational_skill):
        """Soma dos indiretos deve ser a soma aritmética dos componentes."""
        total = operational_skill.aggregate_indirect(
            adm_cost=50_000,
            topografia_cost=20_000,
            laboratorio_cost=15_000,
            qsms_cost=10_000,
            mob_cost=30_000,
        )
        assert abs(total - 125_000) < 0.01

    def test_aggregate_indirect_zero(self, operational_skill):
        """Com todos os custos zerados, total deve ser 0."""
        total = operational_skill.aggregate_indirect(0, 0, 0, 0, 0)
        assert total == 0.0


# ---------------------------------------------------------------------------
# validate_team_composition
# ---------------------------------------------------------------------------

class TestTeamComposition:
    """Valida a composição razoável de equipe."""

    def test_balanced_team_no_issues(self, operational_skill):
        """1 operador + 1 escavadeira = composição equilibrada."""
        result = operational_skill.validate_team_composition(
            activity="ESCAVAÇÃO",
            teams=1,
            labor_per_team=[{"function": "Operador", "qty": 1}],
            equipment_per_team=[{"name": "Escavadeira", "qty": 1}],
        )
        assert result["status"] == "OK"

    def test_too_many_people_per_equipment_flags_review(self, operational_skill):
        """10 operadores para 1 máquina deve sinalizar revisão."""
        result = operational_skill.validate_team_composition(
            activity="Teste",
            teams=1,
            labor_per_team=[{"function": "Operador", "qty": 10}],
            equipment_per_team=[{"name": "Máquina", "qty": 1}],
        )
        assert result["status"] == "REVIEW"
