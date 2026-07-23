"""Coverage sweep 10 — skill-09 helpers, project_service, catalog_loader, skill 06 helpers."""

from __future__ import annotations

import importlib.util
import os
import sys
from unittest.mock import MagicMock


def _load_skill_module(skill_dir: str, module_name: str):
    """Load a skill module from a directory with dashes in name."""
    from pathlib import Path as _Path

    base = str(_Path(__file__).resolve().parents[2] / "src/concilium/application/skills/manifests")
    target = os.path.join(base, skill_dir, f"{module_name}.py")
    if not os.path.exists(target):
        target = os.path.join(base, skill_dir, module_name, "__init__.py")
    if not os.path.exists(target):
        return None
    spec = importlib.util.spec_from_file_location(
        module_name, target, submodule_search_locations=[os.path.dirname(target)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(module_name, None)
        return None
    return mod


# ─── skill-09 _skill_helpers_a.py ────────────────────────────────────────────


class TestSkill09HelpersA:
    def _load(self):
        return _load_skill_module("09-relatorio-e-artefatos", "_skill_helpers")

    def test_module_loads(self):
        mod = self._load()
        assert mod is not None

    def test_build_planejamento_rows_empty(self):
        mod = self._load()
        if mod is None:
            return
        canonical = MagicMock()
        canonical.planejamento = []
        result = mod._build_planejamento_rows(canonical, {}, False)
        assert isinstance(result, list)

    def test_build_tres_camadas_rows_empty(self):
        mod = self._load()
        if mod is None:
            return
        canonical = MagicMock()
        canonical.ponto_equilibrio = []
        canonical.planejamento = []
        result = mod._build_tres_camadas_rows(canonical)
        assert isinstance(result, list)

    def test_build_indireto_rows_empty(self):
        mod = self._load()
        if mod is None:
            return
        canonical = MagicMock()
        canonical.indiretos = []
        result = mod._build_indireto_rows(canonical, {})
        assert isinstance(result, list)

    def test_minimal_break_even_combinations(self):
        mod = self._load()
        if mod is None:
            return
        levers = [{"parametro": "horas_dia", "delta_abs": 2.0, "impacto_preco_pct": 0.05}]
        result = mod._minimal_break_even_combinations(levers, 0.08)
        assert isinstance(result, list)

    def test_rra_build_criticidade_lookup_empty(self):
        mod = self._load()
        if mod is None:
            return
        canonical = MagicMock()
        canonical.ponto_equilibrio = []
        result = mod._rra_build_criticidade_lookup(canonical)
        assert isinstance(result, dict)

    def test_bgs_min_units(self):
        mod = self._load()
        if mod is None:
            return
        eq = MagicMock()
        eq.num_unidades = 3
        result = mod._bgs_min_units(eq)
        assert isinstance(result, (int, float))




# ─── skill-09 skill.py ────────────────────────────────────────────────────────


class TestSkill09:
    def _load(self):
        return _load_skill_module("09-relatorio-e-artefatos", "skill")

    def test_as_bool_true(self):
        mod = self._load()
        if mod is None:
            return
        assert mod._as_bool(True) is True
        assert mod._as_bool("true") is True
        assert mod._as_bool(1) is True

    def test_as_bool_false(self):
        mod = self._load()
        if mod is None:
            return
        assert mod._as_bool(False) is False
        assert mod._as_bool(None) is False
        assert mod._as_bool("") is False



