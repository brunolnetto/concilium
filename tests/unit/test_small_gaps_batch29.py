"""Coverage batch 29 — insumo, extractor, scheduler, runtime small gaps."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# insumo.py lines 68-69:
# _rp_historico_scd2 with missing data_inicio_vigencia key → KeyError → pass
# ---------------------------------------------------------------------------


class TestRpHistoricoScd2KeyError:
    def test_record_missing_data_inicio_raises_and_is_caught(self):
        """Lines 68-69: historico entry without data_inicio_vigencia → KeyError → pass → None."""
        from concilium.infrastructure.repositories.insumo import _rp_historico_scd2

        insumo = {
            "historico_precos": [
                # Missing 'data_inicio_vigencia' → KeyError when accessing registro["data_inicio_vigencia"]
                {"preco_unitario": 100.0},
            ]
        }
        result = _rp_historico_scd2(insumo, data_referencia="2026-01-15")
        assert result is None

    def test_invalid_date_string_raises_value_error_and_is_caught(self):
        """Lines 68-69: invalid date string → ValueError → pass → None."""
        from concilium.infrastructure.repositories.insumo import _rp_historico_scd2

        insumo = {
            "historico_precos": [
                {"data_inicio_vigencia": "not-a-date", "preco_unitario": 100.0},
            ]
        }
        result = _rp_historico_scd2(insumo, data_referencia="2026-01-15")
        assert result is None


# ---------------------------------------------------------------------------
# semantic/extractor.py line 102:
# _strip_soil_qualifiers: qualifier not starting with "solo_class:" → appended
# ---------------------------------------------------------------------------


class TestStripSoilQualifiers:
    def test_non_soil_qualifier_is_kept(self):
        """Line 102: qualifier without 'solo_class:' prefix → result.append(q)."""
        from concilium.application.semantic.extractor import _strip_soil_qualifiers

        result = _strip_soil_qualifiers(["texture:loose", "solo_class:argila", "method:ripping"])
        assert "texture:loose" in result
        assert "method:ripping" in result
        assert "solo_class:argila" not in result

    def test_only_soil_qualifiers_gives_empty(self):
        """All qualifiers are solo_class → result is empty."""
        from concilium.application.semantic.extractor import _strip_soil_qualifiers

        result = _strip_soil_qualifiers(["solo_class:1A", "solo_class:2"])
        assert result == []


# ---------------------------------------------------------------------------
# scheduler.py line 79:
# _demand_at_offset with ramp_profile set → scaled demand
# ---------------------------------------------------------------------------


class TestDemandAtOffsetRampProfile:
    def _make_activity(self, ramp_profile):
        from concilium.application.scheduling.models import Activity

        return Activity(
            activity_id="ACT-TEST",
            description="Test activity with ramp",
            duration_weeks=len(ramp_profile),
            required_resources={"worker": 4},
            ramp_profile=ramp_profile,
        )

    def test_ramp_profile_scales_demand(self):
        """Line 79: ramp_profile[0]=0.5, qty=4 → max(0, round(4*0.5))=2."""
        from concilium.application.scheduling.scheduler import _demand_at_offset

        activity = self._make_activity([0.5, 1.0, 0.75])
        result = _demand_at_offset(activity, 0, "worker", 4)
        assert result == 2  # round(4 * 0.5) = 2

    def test_ramp_profile_offset_out_of_range_returns_qty(self):
        """Line 78 (no branch): offset >= len(ramp_profile) → return qty unchanged."""
        from concilium.application.scheduling.scheduler import _demand_at_offset

        activity = self._make_activity([0.5, 1.0])
        # offset=5 >= len([0.5, 1.0])=2 → return qty=4
        result = _demand_at_offset(activity, 5, "worker", 4)
        assert result == 4


# ---------------------------------------------------------------------------
# scheduler.py line 243:
# SerialScheduler._find_start with activity.window_weeks set → uses min constraint
# ---------------------------------------------------------------------------


class TestFindStartWithWindowWeeks:
    def test_window_weeks_constrains_max_start(self):
        """Line 243: window_weeks not None → max_start = min(deadline, window) - duration."""
        from concilium.application.scheduling.models import Activity, ResourcePool
        from concilium.application.scheduling.scheduler import SerialScheduler

        activity = Activity(
            activity_id="ACT-W",
            description="Windowed activity",
            duration_weeks=2,
            required_resources={},
            window_weeks=8,  # must finish within 8 weeks of project start
        )
        pool = ResourcePool(resources={})
        scheduler = SerialScheduler()

        # deadline=20, window_weeks=8 → max_start = min(20, 8) - 2 = 6
        start = scheduler._find_start(activity, 0, {}, pool, deadline_weeks=20)
        assert start == 0  # no resource conflicts, starts at earliest=0

    def test_without_window_weeks_uses_deadline(self):
        """Line 245 (else branch): window_weeks None → max_start = deadline - duration."""
        from concilium.application.scheduling.models import Activity, ResourcePool
        from concilium.application.scheduling.scheduler import SerialScheduler

        activity = Activity(
            activity_id="ACT-NW",
            description="No-window activity",
            duration_weeks=2,
            required_resources={},
        )
        pool = ResourcePool(resources={})
        scheduler = SerialScheduler()

        start = scheduler._find_start(activity, 0, {}, pool, deadline_weeks=20)
        assert start == 0


# ---------------------------------------------------------------------------
# runtime/__init__.py line 178:
# Runtime._meta_is_gate returns gate flag from MANIFEST_META
# ---------------------------------------------------------------------------


class TestRuntimeMetaIsGate:
    def _make_runtime(self, tmp_path):
        from concilium.application.runtime import Runtime

        return Runtime(config_root=tmp_path)

    def test_meta_is_gate_returns_false_for_unknown_skill(self, tmp_path):
        """Line 178: MANIFEST_META.get unknown → {} → .get("gate", False) → False."""
        rt = self._make_runtime(tmp_path)
        result = rt._meta_is_gate("99-nonexistent-skill")
        assert result is False

    def test_meta_is_gate_returns_false_for_non_gate_skill(self, tmp_path):
        """Line 178: known skill with gate=False → False."""
        rt = self._make_runtime(tmp_path)
        # "05-equipes-e-alocacao" has gate=False in MANIFEST_META
        result = rt._meta_is_gate("05-equipes-e-alocacao")
        assert result is False

    def test_meta_is_gate_returns_true_for_gate_skill(self, tmp_path):
        """Line 178: known skill with gate=True → True."""
        rt = self._make_runtime(tmp_path)
        result = rt._meta_is_gate("01-escopo-e-eap")
        assert result is True
