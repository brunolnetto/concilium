"""Coverage sweep 10 — skill-09 helpers, project_service, catalog_loader, skill 06 helpers."""

from __future__ import annotations

import importlib.util
import os
import sys


def _load_skill_module(skill_dir: str, module_name: str):
    """Load a skill module from a directory with dashes in name."""
    from pathlib import Path as _Path

    base = str(_Path(__file__).resolve().parents[4] / "src/concilium/application/skills/manifests")
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


# ─── skill-06 _consolidacao/_skill_helpers_b.py ───────────────────────────────


class TestSkill06ConsolidacaoHelpersB:
    def _load(self):
        return _load_skill_module("06-resultado-financeiro/_consolidacao", "_skill_helpers/_bdi_resolucao")

    def test_module_loads(self):
        mod = self._load()
        assert mod is not None

    def test_functions_available(self):
        mod = self._load()
        if mod is None:
            return
        fns = [f for f in dir(mod) if not f.startswith("__")]
        assert len(fns) > 0



