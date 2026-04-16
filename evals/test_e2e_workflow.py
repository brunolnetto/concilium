#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evals — E2E: Workflow Completo (4 Gates)

Simula o fluxo obrigatório Layer 1 → Layer 2 → Layer 3 → Layer 4,
reproduzindo os 4 gates de validação do framework sem dependência de LLM.

Gate 1: Base data valid
Gate 2: Cost converged (delta < 5%)
Gate 3: Schedule 100% complete
Gate 4: Profitability 8–10%
"""

import pytest

from conftest import ENCARGOS_RATE


# ---------------------------------------------------------------------------
# Helpers de cenário E2E
# ---------------------------------------------------------------------------

def build_base_data_mock():
    """Base data com ENCARGOS já aplicados (como skill carregaria)."""
    return {
        "labor_costs": {
            "Operador de Escavadeira": 6_300.00 * ENCARGOS_RATE,
            "Motorista de Basculante": 4_800.00 * ENCARGOS_RATE,
            "Encarregado": 5_500.00 * ENCARGOS_RATE,
        },
        "equipment_costs": {
            "Escavadeira Hidráulica": 15_000.00,
            "Caminhão Basculante": 8_500.00,
        },
    }


# ---------------------------------------------------------------------------
# Gate 1 — Base Data
# ---------------------------------------------------------------------------

class TestGate1BaseData:
    """Gate 1: dados base existem e têm qualidade suficiente."""

    def test_encargos_table_defined(self, base_skill):
        """ENCARGOS deve estar no cache para cálculos corretos."""
        assert "ENCARGOS" in base_skill._cache

    def test_mao_de_obra_has_records(self, base_skill):
        """MÃO DE OBRA não pode estar vazia."""
        df = base_skill._cache.get("MÃO DE OBRA")
        assert df is not None
        assert len(df) > 0

    def test_equipamentos_has_records(self, base_skill):
        """EQUIPAMENTOS não pode estar vazia."""
        df = base_skill._cache.get("EQUIPAMENTOS")
        assert df is not None
        assert len(df) > 0

    def test_encargos_multiplier_is_critical(self, base_skill):
        """Multiplicador 1.66 deve estar correto — gate crítico."""
        df = base_skill._cache["ENCARGOS"]
        rate = df["% Encargo"].sum() / 100
        assert abs((1 + rate) - 1.66) < 0.01, (
            "GATE 1 FAIL: Multiplicador de encargos incorreto"
        )


# ---------------------------------------------------------------------------
# Gate 2 — Cost Convergence
# ---------------------------------------------------------------------------

class TestGate2CostConvergence:
    """Gate 2: custo fixo calculado deve convergir com custo de venda (< 5%)."""

    def test_gate2_pass_delta_within_5pct(self, operational_skill):
        """Delta de 3% → gate passa."""
        result = operational_skill.validate_cost_delta(
            service="ESCAVAÇÃO",
            fixed_cost=500_000,
            sales_cost=515_000,  # 3% acima
        )
        assert result.status == "OK", (
            f"GATE 2 FAIL: delta 3% deveria ser OK, recebeu {result.status}"
        )

    def test_gate2_fail_delta_above_5pct(self, operational_skill):
        """Delta de 12% → gate falha."""
        result = operational_skill.validate_cost_delta(
            service="ESCAVAÇÃO",
            fixed_cost=500_000,
            sales_cost=560_000,  # 12%
        )
        assert result.status in ("WARNING", "ERROR"), (
            "GATE 2 FAIL: delta 12% deveria sinalizar erro"
        )

    def test_gate2_indirect_costs_included(self, operational_skill):
        """Custos indiretos devem ser incluídos antes de comparar com venda."""
        indirect = operational_skill.aggregate_indirect(
            adm_cost=50_000,
            topografia_cost=20_000,
            laboratorio_cost=15_000,
            qsms_cost=10_000,
            mob_cost=30_000,
        )
        assert indirect > 0, "Custos indiretos não podem ser zero"


# ---------------------------------------------------------------------------
# Gate 3 — Schedule Completion
# ---------------------------------------------------------------------------

class TestGate3ScheduleCompletion:
    """Gate 3: cronograma deve atingir 100% de cada atividade."""

    def test_gate3_pass_all_activities_complete(self, planning_skill):
        """Todas as atividades em 100% → gate passa."""
        activities = [
            ("ESCAVAÇÃO", 10_000, 10_000),
            ("ATERRO", 8_000, 8_000),
            ("PAVIMENTAÇÃO", 5_000, 5_000),
        ]
        for name, total, planned in activities:
            result = planning_skill.validate_schedule(name, total, planned)
            assert result.status == "OK", (
                f"GATE 3 FAIL: atividade '{name}' incompleta ({result.completion_pct:.1%})"
            )

    def test_gate3_fail_one_activity_incomplete(self, planning_skill):
        """Uma atividade abaixo de 100% → gate falha."""
        result = planning_skill.validate_schedule(
            activity="ATERRO", total_qty=8_000, planned_accumulated=6_000
        )
        assert result.status == "INCOMPLETE", (
            "GATE 3 FAIL: atividade incompleta deveria ser INCOMPLETE"
        )


# ---------------------------------------------------------------------------
# Gate 4 — Profitability
# ---------------------------------------------------------------------------

class TestGate4Profitability:
    """Gate 4: margem deve estar entre 8% e 10%."""

    def test_gate4_pass_margin_9pct(self, financial_skill):
        """9% → gate passa."""
        result = financial_skill.validate_profitability(0.09)
        assert result["status"] == "VIABLE", (
            f"GATE 4 FAIL: margem 9% deveria ser VIABLE, recebeu {result['status']}"
        )

    def test_gate4_fail_margin_6pct(self, financial_skill):
        """6% → gate falha."""
        result = financial_skill.validate_profitability(0.06)
        assert result["status"] != "VIABLE", (
            "GATE 4 FAIL: margem 6% não deveria ser VIABLE"
        )

    def test_gate4_fail_margin_13pct(self, financial_skill):
        """13% → gate falha (não competitivo)."""
        result = financial_skill.validate_profitability(0.13)
        assert result["status"] != "VIABLE"


# ---------------------------------------------------------------------------
# Fluxo E2E Completo
# ---------------------------------------------------------------------------

class TestFullWorkflow:
    """Simula pipeline completo: Layer 1 → 2 → 3 → 4 com cenário GO."""

    def test_full_pipeline_go_scenario(
        self, base_skill, operational_skill, planning_skill, financial_skill
    ):
        """
        Cenário completo GO:
        - Base data: carregada e encargos corretos
        - Crew cost: calculado com ENCARGOS × 1.66
        - Delta: dentro de 5%
        - Cronograma: 100%
        - Margem: 9% → VIABLE

        Todos os 4 gates devem passar.
        """

        # ── Gate 1: Base Data ────────────────────────────────────────────
        mao_de_obra = base_skill._cache["MÃO DE OBRA"]
        encargos_df = base_skill._cache["ENCARGOS"]
        multiplier = 1 + encargos_df["% Encargo"].sum() / 100

        assert len(mao_de_obra) > 0, "Gate 1 FAIL: MÃO DE OBRA vazia"
        assert abs(multiplier - 1.66) < 0.01, "Gate 1 FAIL: ENCARGOS incorretos"

        # ── Gate 2: Crew Cost + Delta ────────────────────────────────────
        base_data = build_base_data_mock()
        crew = operational_skill.calculate_crew_cost(
            activity="ESCAVAÇÃO",
            labor=[{"function": "Operador de Escavadeira", "qty": 2}],
            equipment=[{"name": "Escavadeira Hidráulica", "qty": 2}],
            duration_months=3,
            base_data=base_data,
        )
        assert crew.total_cost > 0, "Gate 2 FAIL: custo de equipe zero"

        # Simula custo de venda = crew + BDI ~3% (dentro da tolerância de 5%)
        sales_cost = crew.total_cost * 1.03
        delta = operational_skill.validate_cost_delta(
            "ESCAVAÇÃO", crew.total_cost, sales_cost
        )
        assert delta.status == "OK", f"Gate 2 FAIL: delta={delta.delta_pct:.2%}"

        # ── Gate 3: Schedule ─────────────────────────────────────────────
        schedule = planning_skill.validate_schedule(
            activity="ESCAVAÇÃO",
            total_qty=30_000,
            planned_accumulated=30_000,
        )
        assert schedule.status == "OK", "Gate 3 FAIL: cronograma incompleto"

        # ── Gate 4: Profitability ─────────────────────────────────────────
        revenue = 1_000_000
        total_cost = 910_000  # margem 9%
        margin = (revenue - total_cost) / revenue

        fin = financial_skill.validate_profitability(margin)
        assert fin["status"] == "VIABLE", (
            f"Gate 4 FAIL: margem {margin:.1%} não é VIABLE"
        )

    def test_full_pipeline_nogo_scenario(
        self, operational_skill, financial_skill
    ):
        """
        Cenário NOGO:
        - Delta 15% → gate 2 falha
        - Margem 5% → gate 4 falha
        Ambos os gates devem retornar falha.
        """

        # Gate 2 FAIL
        delta = operational_skill.validate_cost_delta(
            "PAVIMENTAÇÃO", 500_000, 575_000  # 15%
        )
        assert delta.status == "ERROR", "Gate 2 deveria falhar com delta 15%"

        # Gate 4 FAIL
        fin = financial_skill.validate_profitability(0.05)
        assert fin["status"] != "VIABLE", "Gate 4 deveria falhar com margem 5%"
