"""Unit tests for MOB (Mobilização/Desmobilização) scheduling — ADR-105."""

from datetime import date

from concilium.application.scheduling.mob_scheduling import (
    _topological_sort_eap,
    calcular_custo_indireto_mob,
    get_mob_summary,
    infer_mob_windows,
)


class TestInferMobWindows:
    """Tests for infer_mob_windows() function."""

    def test_infer_windows_basic(self):
        """Basic window inference with simple project dates."""
        meta = {
            "data_inicio": "2025-01-15",
            "data_termino": "2027-03-30",
        }
        spec_eap = [
            {"item_id": "1.1", "predecessores": []},
            {"item_id": "1.2", "predecessores": [{"item_id": "1.1"}]},
        ]

        windows = infer_mob_windows(meta, spec_eap)

        assert "mobilizacao" in windows
        assert "operacao" in windows
        assert "desmobilizacao" in windows

        # mobilizacao should be before operacao
        assert windows["mobilizacao"]["fim"] <= windows["operacao"]["inicio"]
        # operacao should be before desmobilizacao
        assert windows["operacao"]["fim"] <= windows["desmobilizacao"]["inicio"]

    def test_infer_windows_no_eap(self):
        """Window inference with empty EAP."""
        meta = {
            "data_inicio": "2025-01-01",
            "data_termino": "2025-12-31",
        }
        spec_eap = []

        windows = infer_mob_windows(meta, spec_eap)

        # Should still return valid windows
        assert windows["mobilizacao"]["inicio"] == date(2025, 1, 1)
        assert windows["desmobilizacao"]["fim"] == date(2025, 12, 31)

    def test_infer_windows_safety_margin(self):
        """Window inference respects safety margin."""
        meta = {
            "data_inicio": "2025-01-01",
            "data_termino": "2025-12-31",
        }
        spec_eap = [
            {"item_id": "1.1", "predecessores": []},
        ]

        windows = infer_mob_windows(meta, spec_eap, safety_margin_days=7)

        # mobilizacao fim should be before operacao by at least safety margin days
        # (if possible)
        assert windows["mobilizacao"]["fim"] <= windows["operacao"]["inicio"]

    def test_infer_windows_no_gap(self):
        """Verify windows cover full project timeline without gaps."""
        meta = {
            "data_inicio": "2025-06-01",
            "data_termino": "2026-06-01",
        }
        spec_eap = [
            {"item_id": "A", "predecessores": []},
            {"item_id": "B", "predecessores": [{"item_id": "A"}]},
        ]

        windows = infer_mob_windows(meta, spec_eap)

        # Project start should be in mobilizacao
        assert windows["mobilizacao"]["inicio"] == date(2025, 6, 1)
        # Project end should be in desmobilizacao
        assert windows["desmobilizacao"]["fim"] == date(2026, 6, 1)

    def test_infer_windows_zero_margin_skips_adjustment(self):
        """With safety_margin_days=0, mob_end==mob_start and op_end==project_end,
        so neither the `mob_end < mob_start` nor `op_end > project_end` adjustment
        branches fire (both conditions are exactly equal, not strictly True)."""
        meta = {
            "data_inicio": "2025-01-01",
            "data_termino": "2025-12-31",
        }
        spec_eap = [{"item_id": "1.1", "predecessores": []}]

        windows = infer_mob_windows(meta, spec_eap, safety_margin_days=0)

        assert windows["mobilizacao"]["fim"] == date(2025, 1, 1)
        assert windows["operacao"]["fim"] == date(2025, 12, 31)


class TestTopologicalSortEap:
    def test_predecessor_not_in_graph_is_skipped(self):
        """A predecessor referencing an item_id absent from the EAP list must
        simply be skipped (dangling reference), not raise."""
        spec_eap = [
            {"item_id": "1.1", "predecessores": [{"item_id": "does-not-exist"}]},
        ]
        order = _topological_sort_eap(spec_eap)
        assert [i["item_id"] for i in order] == ["1.1"]


class TestCalcularCustoIndiretoMob:
    """Tests for calcular_custo_indireto_mob() function."""

    def test_calcular_mob_projeto(self):
        """MOB with driver='projeto' incurs cost once."""
        indiretos = [
            {
                "tipo": "MOB",
                "categoria": "MOB",
                "fase": "mobilizacao",
                "driver": "projeto",
                "custo_fixo_total": 100000.0,
            }
        ]
        mob_windows = {
            "mobilizacao": {
                "inicio": date(2025, 1, 1),
                "fim": date(2025, 1, 15),
            },
            "operacao": {
                "inicio": date(2025, 1, 16),
                "fim": date(2026, 12, 31),
            },
            "desmobilizacao": {
                "inicio": date(2027, 1, 1),
                "fim": date(2027, 1, 15),
            },
        }

        result = calcular_custo_indireto_mob(indiretos, mob_windows)

        assert result["custo_mob_total"] == 100000.0
        assert result["mob"]["mobilizacao"]["custo_total"] == 100000.0
        assert "semana_inicio" in result["mob"]["mobilizacao"]

    def test_calcular_mob_mensal(self):
        """MOB with driver='mensal' distributes cost over window duration."""
        indiretos = [
            {
                "tipo": "MOB",
                "categoria": "MOB",
                "fase": "operacao",
                "driver": "mensal",
                "custo_fixo_mensal": 50000.0,
            }
        ]
        mob_windows = {
            "mobilizacao": {
                "inicio": date(2025, 1, 1),
                "fim": date(2025, 1, 15),
            },
            "operacao": {
                "inicio": date(2025, 1, 16),
                "fim": date(2025, 4, 30),  # ~3.5 months
            },
            "desmobilizacao": {
                "inicio": date(2025, 5, 1),
                "fim": date(2025, 5, 15),
            },
        }

        result = calcular_custo_indireto_mob(indiretos, mob_windows)

        # Check operacao is distributed
        op_data = result["mob"]["operacao"]
        assert "custo_mensal" in op_data
        assert op_data["custo_mensal"] == 50000.0
        assert op_data["duracao_meses"] > 3.0
        assert op_data["total"] > 50000.0

    def test_calcular_mob_mixed(self):
        """MOB with multiple phases and mixed drivers."""
        indiretos = [
            {
                "tipo": "MOB",
                "categoria": "MOB",
                "fase": "mobilizacao",
                "driver": "projeto",
                "custo_fixo_total": 50000.0,
            },
            {
                "tipo": "MOB",
                "categoria": "MOB",
                "fase": "operacao",
                "driver": "mensal",
                "custo_fixo_mensal": 30000.0,
            },
            {
                "tipo": "MOB",
                "categoria": "MOB",
                "fase": "desmobilizacao",
                "driver": "projeto",
                "custo_fixo_total": 30000.0,
            },
        ]
        mob_windows = {
            "mobilizacao": {
                "inicio": date(2025, 1, 1),
                "fim": date(2025, 1, 31),
            },
            "operacao": {
                "inicio": date(2025, 2, 1),
                "fim": date(2026, 1, 31),  # 12 months
            },
            "desmobilizacao": {
                "inicio": date(2026, 2, 1),
                "fim": date(2026, 2, 28),
            },
        }

        result = calcular_custo_indireto_mob(indiretos, mob_windows)

        # Check all phases present
        assert "mobilizacao" in result["mob"]
        assert "operacao" in result["mob"]
        assert "desmobilizacao" in result["mob"]

        # Check totals
        mob_total = result["custo_mob_total"]
        assert mob_total > 50000.0 + 30000.0  # at least mobilizacao + 1 month

    def test_calcular_mob_ignores_non_mob(self):
        """calcular_custo_indireto_mob should ignore non-MOB categories."""
        indiretos = [
            {
                "tipo": "ADM",
                "categoria": "ADM",
                "driver": "mensal",
                "custo_fixo_mensal": 100000.0,
            },
            {
                "tipo": "MOB",
                "categoria": "MOB",
                "fase": "mobilizacao",
                "driver": "projeto",
                "custo_fixo_total": 50000.0,
            },
        ]
        mob_windows = {
            "mobilizacao": {
                "inicio": date(2025, 1, 1),
                "fim": date(2025, 1, 31),
            },
            "operacao": {
                "inicio": date(2025, 2, 1),
                "fim": date(2026, 1, 31),
            },
            "desmobilizacao": {
                "inicio": date(2026, 2, 1),
                "fim": date(2026, 2, 28),
            },
        }

        result = calcular_custo_indireto_mob(indiretos, mob_windows)

        # Should only include MOB cost, not ADM
        assert result["custo_mob_total"] == 50000.0

    def test_calcular_mob_unrecognized_driver_contributes_nothing(self):
        """A MOB indireto with a driver that is neither 'projeto' nor 'mensal'
        should be silently skipped (no phase entry, no cost added)."""
        indiretos = [
            {
                "tipo": "MOB",
                "categoria": "MOB",
                "fase": "mobilizacao",
                "driver": "desconhecido",
                "custo_fixo_total": 50000.0,
            },
        ]
        mob_windows = {
            "mobilizacao": {"inicio": date(2025, 1, 1), "fim": date(2025, 1, 31)},
            "operacao": {"inicio": date(2025, 2, 1), "fim": date(2026, 1, 31)},
            "desmobilizacao": {"inicio": date(2026, 2, 1), "fim": date(2026, 2, 28)},
        }

        result = calcular_custo_indireto_mob(indiretos, mob_windows)

        assert result["custo_mob_total"] == 0.0
        assert "mobilizacao" not in result["mob"]


class TestGetMobSummary:
    """Tests for get_mob_summary() function."""

    def test_get_mob_summary_all_phases(self):
        """Extract summary from complete mob_costs."""
        mob_costs = {
            "mob": {
                "mobilizacao": {
                    "custo_total": 50000.0,
                    "semana_inicio": "2025-W01",
                },
                "operacao": {
                    "custo_mensal": 30000.0,
                    "duracao_meses": 12.0,
                    "total": 360000.0,
                },
                "desmobilizacao": {
                    "custo_total": 30000.0,
                    "semana_inicio": "2026-W09",
                },
            },
            "custo_mob_total": 440000.0,
        }

        summary = get_mob_summary(mob_costs)

        assert summary["mobilizacao"] == 50000.0
        assert summary["operacao"] == 360000.0
        assert summary["desmobilizacao"] == 30000.0

    def test_get_mob_summary_partial(self):
        """Extract summary from partial mob_costs."""
        mob_costs = {
            "mob": {
                "mobilizacao": {
                    "custo_total": 50000.0,
                    "semana_inicio": "2025-W01",
                },
            },
            "custo_mob_total": 50000.0,
        }

        summary = get_mob_summary(mob_costs)

        assert len(summary) == 1
        assert summary["mobilizacao"] == 50000.0

    def test_get_mob_summary_empty(self):
        """Extract summary from empty mob_costs."""
        mob_costs = {
            "mob": {},
            "custo_mob_total": 0.0,
        }

        summary = get_mob_summary(mob_costs)

        assert summary == {}

    def test_get_mob_summary_phase_without_recognized_keys(self):
        """A phase dict lacking both 'custo_total' and 'total' keys must be
        skipped entirely (neither branch of the if/elif matches)."""
        mob_costs = {
            "mob": {
                "mobilizacao": {"semana_inicio": "2025-W01"},
            },
            "custo_mob_total": 0.0,
        }

        summary = get_mob_summary(mob_costs)

        assert summary == {}


class TestIntegration:
    """Integration tests for full MOB scheduling flow."""

    def test_full_flow_odfjell_like(self):
        """Full flow similar to ODFJELL structure."""
        meta = {
            "data_inicio": "2024-01-15",
            "data_termino": "2028-01-15",
        }
        spec_eap = [
            {"item_id": "1.1", "predecessores": []},
            {"item_id": "1.2", "predecessores": [{"item_id": "1.1"}]},
            {"item_id": "2.1", "predecessores": [{"item_id": "1.2"}]},
        ]

        # Step 1: Infer windows
        windows = infer_mob_windows(meta, spec_eap)

        # Step 2: Calculate costs
        indiretos = [
            {
                "tipo": "MOB",
                "categoria": "MOB",
                "fase": "mobilizacao",
                "driver": "projeto",
                "custo_fixo_total": 246900.0,
            },
            {
                "tipo": "MOB",
                "categoria": "MOB",
                "fase": "operacao",
                "driver": "mensal",
                "custo_fixo_mensal": 35654.0,  # 855706/24 months typical
            },
            {
                "tipo": "MOB",
                "categoria": "MOB",
                "fase": "desmobilizacao",
                "driver": "projeto",
                "custo_fixo_total": 123450.0,
            },
        ]

        mob_costs = calcular_custo_indireto_mob(indiretos, windows)
        summary = get_mob_summary(mob_costs)

        # Verify structure
        assert len(summary) == 3
        assert mob_costs["custo_mob_total"] > 0
