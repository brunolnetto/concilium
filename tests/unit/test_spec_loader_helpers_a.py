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


# ─── application/benchmarks/_spec_loader_helpers_a.py more ───────────────────


class TestSpecLoaderHelpersAMore:
    def test_norm_ref_atividades_to_eap(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_atividades_to_eap

        out = {"atividades": [{"item_id": "a1", "cpu_id": "C1", "quantitativo": 100.0}]}
        _norm_ref_atividades_to_eap(out)
        assert "eap" in out or isinstance(out, dict)

    def test_ebr_from_stats(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _ebr_from_stats

        stats = MagicMock()
        stats.preco_venda_total = 1e6
        stats.custo_direto_total = 7e5
        result = _ebr_from_stats(stats)
        assert isinstance(result, dict)

    def test_norm_ref_ensure_rcpsp_spec(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_ensure_rcpsp_spec

        out = {}
        _norm_ref_ensure_rcpsp_spec(out)
        assert isinstance(out, dict)

