"""Tests for src/concilium/domain/services/project_rules.py"""

from unittest.mock import MagicMock

import pytest

from concilium.domain.services.project_rules import (
    calculate_deltas,
    resolve_compare_version,
    validate_delete_version,
)

# ---------------------------------------------------------------------------
# validate_delete_version
# ---------------------------------------------------------------------------


class TestValidateDeleteVersion:
    def test_raises_when_single_version_and_project_type(self):
        with pytest.raises(RuntimeError, match="última versão"):
            validate_delete_version("project", ["v1"], "v1")

    def test_no_raise_when_multiple_versions_and_project_type(self):
        # Should not raise — there are still other versions left
        validate_delete_version("project", ["v1", "v2"], "v1")

    def test_no_raise_when_single_version_but_not_project_type(self):
        # tipo_projeto != 'project', so deletion is allowed even with 1 version
        validate_delete_version("template", ["v1"], "v1")
        validate_delete_version("", ["v1"], "v1")

    def test_no_raise_when_empty_versions_list(self):
        # len([]) == 0, condition is False — no RuntimeError
        validate_delete_version("project", [], "v1")

    def test_no_raise_when_versions_has_two_items_and_project(self):
        validate_delete_version("project", ["v1", "v2"], "v2")

    def test_returns_none(self):
        result = validate_delete_version("project", ["v1", "v2"], "v1")
        assert result is None


# ---------------------------------------------------------------------------
# resolve_compare_version
# ---------------------------------------------------------------------------


def _make_project(canonical_map: dict, versions: list[str]) -> MagicMock:
    """Return a project stub where load_canonical returns values from canonical_map."""
    project = MagicMock()
    project.load_canonical.side_effect = lambda v: canonical_map.get(v)
    project.list_versions.return_value = versions
    return project


class TestResolveCompareVersion:
    def test_returns_version_immediately_when_canonical_exists(self):
        project = _make_project({"v3": {"some": "data"}}, ["v1", "v2", "v3"])
        result = resolve_compare_version(project, "v3")
        assert result == "v3"
        # list_versions should NOT have been called
        project.list_versions.assert_not_called()

    def test_falls_back_to_nearest_lower_version_with_canonical(self):
        # v2 has no canonical, v1 does; requesting v2 should return v1
        project = _make_project({"v1": {"ok": True}}, ["v1", "v2"])
        result = resolve_compare_version(project, "v2")
        assert result == "v1"

    def test_falls_back_skipping_versions_higher_than_target(self):
        # Versions: v1, v2, v3, v4. Only v1 and v3 have canonicals.
        # Requesting v3: v3 has no canonical → look for ≤v3 with canonical → v3 skipped
        # (first call returns None for v3), reversed([v1,v2,v3,v4]) → v4>3 skip,
        # v3≤3 check canonical → None, v2≤3 → None, v1≤3 → canonical found
        project = _make_project({"v1": {"ok": True}}, ["v1", "v2", "v3", "v4"])
        result = resolve_compare_version(project, "v3")
        assert result == "v1"

    def test_skips_candidates_higher_than_target(self):
        # v5 has canonical, target is v3 → v5 must be skipped; v2 has canonical
        project = _make_project({"v2": {"ok": True}, "v5": {"ok": True}}, ["v1", "v2", "v3", "v4", "v5"])
        result = resolve_compare_version(project, "v3")
        assert result == "v2"

    def test_raises_value_error_for_invalid_version_format(self):
        # No canonical for "main", format is invalid (not v<digits>)
        project = _make_project({}, ["v1", "v2"])
        with pytest.raises(ValueError, match="Versao invalida"):
            resolve_compare_version(project, "main")

    def test_raises_value_error_for_version_without_digits(self):
        project = _make_project({}, ["va", "vb"])
        with pytest.raises(ValueError, match="Versao invalida"):
            resolve_compare_version(project, "vabc")

    def test_raises_value_error_when_no_candidate_has_canonical(self):
        # v2 has no canonical; v1 also has no canonical → ValueError
        project = _make_project({}, ["v1", "v2"])
        with pytest.raises(ValueError, match="sem canônico"):
            resolve_compare_version(project, "v2")

    def test_skips_non_vN_format_candidates_in_list(self):
        # Candidates "main" and "dev" should be skipped; v1 has canonical
        project = _make_project({"v1": {"ok": True}}, ["v1", "main", "dev"])
        result = resolve_compare_version(project, "v2")
        assert result == "v1"

    def test_version_prefix_v_but_no_digits_raises(self):
        project = _make_project({}, ["v1"])
        with pytest.raises(ValueError, match="Versao invalida"):
            resolve_compare_version(project, "v")

    def test_exact_match_on_numeric_boundary(self):
        # Candidate v3 == target v3 → should be included (≤ check)
        _make_project({"v3": {"ok": True}}, ["v1", "v2", "v3"])
        # load_canonical("v3") returns None on first call (no direct canonical),
        # so we need a project where v3 has no direct canonical but IS found in loop
        # Let's set up: first call (direct) returns None, loop call returns data
        project2 = MagicMock()
        call_count = {"n": 0}

        def load_canonical(v):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First call (direct check) → None
                return None
            # Subsequent calls in the loop
            return {"ok": True} if v == "v3" else None

        project2.load_canonical.side_effect = load_canonical
        project2.list_versions.return_value = ["v1", "v2", "v3"]
        result = resolve_compare_version(project2, "v3")
        assert result == "v3"


# ---------------------------------------------------------------------------
# calculate_deltas
# ---------------------------------------------------------------------------


class TestCalculateDeltas:
    """#206: the domain delta covers only the break-even counter.

    The former float deltas of the legacy summary keys (preco_venda_total,
    custo_total, margem_pct, resultado_bruto) were removed with those keys;
    their exact replacements are tested with the exact financial view
    (tests/unit/application/scheduling/test_exact_financial_view.py).
    """

    LEGACY_KEYS = ["preco_venda_total", "custo_total", "margem_pct", "resultado_bruto"]

    def test_only_the_break_even_counter_is_compared(self):
        assert set(calculate_deltas({}, {}).keys()) == {"pe_deficit_items"}

    def test_legacy_financial_keys_produce_no_delta(self):
        left = {key: 100.0 for key in self.LEGACY_KEYS}
        right = {key: 150.0 for key in self.LEGACY_KEYS}
        result = calculate_deltas(left, right)
        assert not set(self.LEGACY_KEYS) & set(result)

    def test_missing_or_none_counter_defaults_to_zero(self):
        assert calculate_deltas({}, {"pe_deficit_items": 2})["pe_deficit_items"] == pytest.approx(2.0)
        assert calculate_deltas({"pe_deficit_items": None}, {})["pe_deficit_items"] == pytest.approx(0.0)

    def test_integer_values_are_cast_to_float(self):
        result = calculate_deltas({"pe_deficit_items": 1}, {"pe_deficit_items": 3})
        assert isinstance(result["pe_deficit_items"], float)

    def test_extra_keys_in_summaries_are_ignored(self):
        result = calculate_deltas({"extra_key": 999.0}, {"financeiro_exato": {"status": "AVALIADO"}})
        assert set(result) == {"pe_deficit_items"}

    def test_pe_deficit_items_delta(self):
        left = {"pe_deficit_items": 5.0}
        right = {"pe_deficit_items": 2.0}
        result = calculate_deltas(left, right)
        assert result["pe_deficit_items"] == pytest.approx(-3.0)
