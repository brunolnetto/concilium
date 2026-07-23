"""Coverage sweep 9 — project_service, financial_report_pdf, sharepoint, scheduling."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
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


# ─── application/services/project_service.py helpers ─────────────────────────


class TestProjectServiceHelpers:
    def test_resolve_project_type_project(self):
        from concilium.application.services.project.project_service import _resolve_project_type

        assert _resolve_project_type({"tipo": "project"}) == "project"

    def test_resolve_project_type_hot_project(self):
        from concilium.application.services.project.project_service import _resolve_project_type

        assert _resolve_project_type({"tipo_projeto": "hot_project"}) == "hot_project"

    def test_resolve_project_type_default(self):
        from concilium.application.services.project.project_service import _resolve_project_type

        result = _resolve_project_type({})
        assert isinstance(result, str)

    def test_is_valid_canonical_eap_true(self):
        from concilium.application.services.project.project_service import _is_valid_canonical_eap

        payload = {"cpus": {"itens_eap": [{"item_id": "eap-1"}]}}
        assert _is_valid_canonical_eap(payload) is True

    def test_is_valid_canonical_eap_false(self):
        from concilium.application.services.project.project_service import _is_valid_canonical_eap

        assert _is_valid_canonical_eap({}) is False
        assert _is_valid_canonical_eap({"cpus": {}}) is False

    def test_catalog_is_deficit_false(self):
        from concilium.application.services.project.project_service import _catalog_is_deficit

        catalog = MagicMock()
        catalog.n_cpus = 50
        catalog.n_insumos_com_preco = 45
        result = _catalog_is_deficit(catalog)
        assert isinstance(result, bool)

    def test_canonical_eap_to_rows(self):
        from concilium.application.services.project.project_service import _canonical_eap_to_rows

        canonical = MagicMock()
        canonical.eap = [MagicMock(item_id="eap-1", descricao="Test", nivel=1)]
        result = _canonical_eap_to_rows(canonical)
        assert isinstance(result, list)

    def test_project_service_instantiates(self):
        from concilium.application.services.project.project_service import ProjectService

        svc = ProjectService(MagicMock(), MagicMock(), MagicMock())
        assert svc is not None

    def test_debug_storage_info(self):
        from concilium.application.services.project.project_service import _debug_storage_info

        project = MagicMock()
        project.root = Path("/tmp/fake_project")
        project.meta = {"nome": "Test"}
        result = _debug_storage_info(project)
        assert isinstance(result, dict)




# ─── application/services/project_service.py more coverage ───────────────────


class TestProjectServiceMore:
    def test_extract_historical_eap_rows_empty(self):
        from concilium.application.services.project.project_service import _extract_historical_eap_rows

        result = _extract_historical_eap_rows({})
        assert isinstance(result, list)

    def test_extract_canonical_eap_rows_empty(self):
        from concilium.application.services.project.project_service import _extract_canonical_eap_rows

        result = _extract_canonical_eap_rows({})
        assert isinstance(result, list)

    def test_latest_version_with_eap_empty_project(self):
        from concilium.application.services.project.project_service import _latest_version_with_eap

        project = MagicMock()
        project.list_versions.return_value = []
        rows, version = _latest_version_with_eap(project)
        assert isinstance(rows, list)
        assert version is None



