"""Coverage batch 27 — runner_utils, stage_discrepancy_summary,
constraints, resolver small gaps."""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

# ---------------------------------------------------------------------------
# runner_utils.py line 68->67: funcao without 'salario_base' key → if False → skip
# ---------------------------------------------------------------------------


class TestApplyCustoDeltaFuncaoNoSalarioBase:
    def test_funcao_without_salario_base_is_skipped(self):
        """Line 68->67: funcao dict has no 'salario_base' → if False → back to loop."""
        from concilium.application.scenarios.runner_utils import apply_custo_delta

        inputs = {
            "composicao_customizada": {
                "CPU-01": {
                    "funcoes": [
                        {"funcao_id": "FNC-01"},  # no 'salario_base' key → skipped
                    ],
                    "equipamentos": [],
                }
            }
        }
        result = apply_custo_delta(inputs, delta=1.1)
        # funcao untouched — no salario_base to modify
        assert result["composicao_customizada"]["CPU-01"]["funcoes"][0] == {"funcao_id": "FNC-01"}


# ---------------------------------------------------------------------------
# stage_discrepancy_summary.py line 208:
# bench_data subdir exists but no extracao_intermediarios.json → continue
# ---------------------------------------------------------------------------


class TestBuildSummarySkipsSubdirWithoutTrace:
    def test_dir_without_trace_file_is_skipped(self):
        """Line 208: continue when trace file doesn't exist."""
        from concilium.application.benchmarks.analysis.stage_discrepancy_summary import (
            build_summary,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bench_data = root / "benchmarks" / "data"
            bench_data.mkdir(parents=True)
            # Subdir without trace file
            (bench_data / "BENCH-NO-TRACE").mkdir()

            result = build_summary(root=root)

        # The subdir was skipped → no rows collected
        assert result["meta"]["total_benchmarks_com_extracao"] == 0
        assert result["top_discrepancias"] == []


# ---------------------------------------------------------------------------
# constraints.py line 110->125:
# cpu has dmt in attributes but cpu_dmt is None → if condition False → skip to 125
# ---------------------------------------------------------------------------


class TestStructuralCompatibilityDmtNone:
    def _make_filter(self):
        from concilium.application.resolution.constraints import ConstraintFilter

        return ConstraintFilter()

    def test_returns_passed_when_cpu_dmt_is_none(self):
        """Line 110->125: intent_dmt is not None, but cpu_dmt is None → if False → passed=True."""
        cf = self._make_filter()
        # cpu: activity_type=cut_fill, dmt in attributes but value is None
        cpu = SimpleNamespace(activity_type="cut_fill", attributes={"dmt": None})
        # intent: dimension_value("dmt") returns 500.0 (not None)
        intent = SimpleNamespace(dimension_value=lambda name: 500.0 if name == "dmt" else None)

        result = cf.check_structural_compatibility(intent, cpu)
        assert result.passed is True

    def test_returns_passed_when_intent_dmt_is_none(self):
        """Line 110->125: intent_dmt is None → if condition False → passed=True."""
        cf = self._make_filter()
        cpu = SimpleNamespace(activity_type="cut_fill", attributes={"dmt": 2000.0})
        # intent: no dmt dimension → dimension_value returns None
        intent = SimpleNamespace(dimension_value=lambda name: None)

        result = cf.check_structural_compatibility(intent, cpu)
        assert result.passed is True

    def test_returns_failed_when_dmt_exceeds_cpu_limit(self):
        """Normal path: both dmt not None, intent_dmt > upper → passed=False."""
        cf = self._make_filter()
        cpu = SimpleNamespace(activity_type="cut_fill", attributes={"dmt": 1000.0})
        intent = SimpleNamespace(dimension_value=lambda name: 9999.0 if name == "dmt" else None)

        result = cf.check_structural_compatibility(intent, cpu)
        assert result.passed is False


# ---------------------------------------------------------------------------
# cpu_validator.py lines 25-26: check if these are coverable
# (they appear to be in a NameError-guarded block or similar)
# ---------------------------------------------------------------------------


class TestCpuValidatorSmallGaps:
    def test_import_validates_ok(self):
        """Smoke test — just importing should not raise."""
        from concilium.application.benchmarks.validation import cpu_validator

        assert cpu_validator is not None

    def test_constructor_builds_mapper_and_exposes_catalogo(self):
        """Lines 25-26: CpuValidator.__init__ constructs a CpuMapper for the given
        contexto_id and exposes its .catalogo attribute. CpuMapper's own catalog
        loading is patched out since we only care about CpuValidator's wiring."""
        from unittest.mock import patch

        from concilium.application.benchmarks.validation.cpu_mapper import CpuMapper
        from concilium.application.benchmarks.validation.cpu_validator import CpuValidator

        fake_catalogo = {"cpus": [], "producoes": []}

        def _fake_load_catalog(self):
            self.catalogo = fake_catalogo
            self.contexto = None

        with patch.object(CpuMapper, "_load_catalog", _fake_load_catalog):
            validator = CpuValidator(contexto_id="mendeslobo")

        assert isinstance(validator.mapper, CpuMapper)
        assert validator.mapper.contexto_id == "mendeslobo"
        assert validator.catalogo is validator.mapper.catalogo
