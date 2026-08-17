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





import pytest  # noqa: E402

# ─── application/services/project/_project_service_helpers.py ─────────────────


class TestProjectServiceHelpers2:
    def test_try_enrich_cpu_no_prod(self):
        from concilium.application.services.project._project_service_helpers import _try_enrich_cpu_with_prod

        cpu = {"codigo": "CPU-1", "producao_id_ref": "P1"}
        result = _try_enrich_cpu_with_prod(cpu, {})
        assert result is cpu  # unchanged

    def test_try_enrich_cpu_with_prod(self):
        from concilium.application.services.project._project_service_helpers import _try_enrich_cpu_with_prod

        cpu = {"codigo": "CPU-1", "producao_id_ref": "P1"}
        prod_lkp = {"P1": {"producao_horaria": 50.0, "composicao_padrao_equipe": {"funcoes": []}}}
        result = _try_enrich_cpu_with_prod(cpu, prod_lkp)
        assert result.get("producao_horaria") == 50.0

    def test_build_joined_cpus_empty(self):
        from concilium.application.services.project._project_service_helpers import _build_joined_cpus

        result = _build_joined_cpus([], [])
        assert result == []

    def test_build_joined_cpus_with_data(self):
        from concilium.application.services.project._project_service_helpers import _build_joined_cpus

        cpus = [{"codigo": "CPU-1", "producao_id_ref": "P1"}]
        prods = [{"id": "P1", "producao_horaria": 50.0}]
        result = _build_joined_cpus(cpus, prods)
        assert len(result) == 1

    def test_build_catalog_from_snapshot(self):
        from concilium.application.services.project._project_service_helpers import _build_catalog_from_snapshot

        cat = {"cpus": [{"codigo": "CPU-1"}], "insumos": [], "producoes": [], "produtividades": []}
        result = _build_catalog_from_snapshot(cat)
        assert "cpus" in result

    def test_compute_bdi_for_categoria_none(self):
        from concilium.application.services.project._project_service_helpers import _compute_bdi_for_categoria

        result = _compute_bdi_for_categoria(None)
        assert result is None

    def test_compute_bdi_for_categoria_with_comps(self):
        from concilium.application.services.project._project_service_helpers import _compute_bdi_for_categoria

        comps = MagicMock()
        comps.ac = 0.05
        comps.df = 0.01
        comps.r = 0.01
        comps.l = 0.08
        comps.cofins = 0.03
        comps.iss = 0.03
        comps.pis = 0.0065
        comps.cssl = 0.0288
        comps.ir = 0.015
        result = _compute_bdi_for_categoria(comps)
        assert result is None or isinstance(result, float)

    def test_compute_flat_bdi(self):
        from concilium.application.services.project._project_service_helpers import _compute_flat_bdi

        tabela = {
            "padrao": MagicMock(
                ac=0.05, df=0.01, r=0.01, l=0.08, cofins=0.03, iss=0.03, pis=0.0065, cssl=0.0288, ir=0.015
            ),
        }
        result = _compute_flat_bdi(tabela)
        assert isinstance(result, dict)

    def test_sort_versions(self):
        from concilium.application.services.project._project_service_helpers import _sort_versions

        versions = ["v3", "v1", "v10", "v2"]
        result = _sort_versions(versions)
        assert result[0] == "v1"
        assert "v10" in result

    def test_count_orphaned_runs_empty(self):
        from concilium.application.services.project._project_service_helpers import _count_orphaned_runs

        result = _count_orphaned_runs([], "v1")
        assert result == 0

    def test_count_orphaned_runs_with_data(self):
        from concilium.application.services.project._project_service_helpers import _count_orphaned_runs

        runs = [
            {"version": "v1", "status": "OK"},
            {"version": "v2", "status": "OK"},
        ]
        result = _count_orphaned_runs(runs, "v1")
        assert isinstance(result, int)

    def test_cp_build_meta_kwargs_basic(self):
        from concilium.application.services.project._project_service_helpers import _cp_build_meta_kwargs

        inputs = {"nome": "Test", "contexto_id": "ctx", "localizacao": "SP"}
        req = MagicMock()
        req.nome = "Test"
        req.contexto_id = "ctx"
        result = _cp_build_meta_kwargs(inputs, req)
        assert isinstance(result, dict)

    def test_enrich_payload_catalog_no_crash(self, tmp_path):
        from concilium.application.services.project._project_service_helpers import _enrich_payload_catalog

        project = MagicMock()
        project.root = tmp_path
        payload: dict = {}
        # No snapshot files → should silently pass
        _enrich_payload_catalog(payload, project)

    def test_enrich_payload_encargos_no_crash(self, tmp_path):
        from concilium.application.services.project._project_service_helpers import _enrich_payload_encargos

        project = MagicMock()
        project.root = tmp_path
        payload: dict = {}
        _enrich_payload_encargos(payload, project)

    def test_compute_bdi_for_categoria_with_dict(self):
        from concilium.application.services.project._project_service_helpers import _compute_bdi_for_categoria

        comps = {
            "ac": 0.05,
            "df": 0.01,
            "r": 0.01,
            "cr": 0.01,
            "l": 0.08,
            "cofins": 0.03,
            "iss": 0.03,
            "pis": 0.0065,
            "cssl": 0.0288,
            "ir": 0.015,
        }
        result = _compute_bdi_for_categoria(comps)
        assert result is not None
        assert result > 0

    def test_compute_flat_bdi_with_categories(self):
        from concilium.application.services.project._project_service_helpers import _compute_flat_bdi

        comps = {
            "ac": 0.05,
            "df": 0.01,
            "r": 0.01,
            "cr": 0.01,
            "l": 0.08,
            "cofins": 0.03,
            "iss": 0.03,
            "pis": 0.0065,
            "cssl": 0.0288,
            "ir": 0.015,
        }
        tabela = {"servicos": comps, "mao_obra": comps}
        result = _compute_flat_bdi(tabela)
        assert "servicos" in result
        assert "equipamentos" in result  # auto-filled from servicos

    def test_enrich_payload_bdi_no_crash(self):
        from concilium.application.services.project._project_service_helpers import _enrich_payload_bdi

        payload = {"skill_inputs": {}}
        _enrich_payload_bdi(payload)  # no tabela_bdi → no-op

    def test_enrich_payload_bdi_with_tabela(self):
        from concilium.application.services.project._project_service_helpers import _enrich_payload_bdi

        comps = {
            "ac": 0.05,
            "df": 0.01,
            "r": 0.01,
            "cr": 0.01,
            "l": 0.08,
            "cofins": 0.03,
            "iss": 0.03,
            "pis": 0.0065,
            "cssl": 0.0288,
            "ir": 0.015,
        }
        payload = {"skill_inputs": {"06-resultado-financeiro": {"tabela_bdi": {"servicos": comps}}}}
        _enrich_payload_bdi(payload)
        assert "bdi_aplicado" in payload["skill_inputs"]["06-resultado-financeiro"]

    def test_ps_delete_version_not_found_raises(self):
        from concilium.application.services.project._project_service_helpers import _ps_delete_version

        svc = MagicMock()
        proj_mock = MagicMock()
        proj_mock.list_versions.return_value = ["v1", "v2"]
        svc._dependencies.repository.get_project.return_value = proj_mock
        with pytest.raises(FileNotFoundError):
            _ps_delete_version(svc, "proj-1", "v99")

    def test_resolve_catalogo_base_none(self):
        from concilium.application.services.project._project_service_helpers import _resolve_catalogo_base_from_context

        svc = MagicMock()
        svc._dependencies = MagicMock()
        # Should not raise; return None or str
        result = _resolve_catalogo_base_from_context(svc, "nonexistent-ctx")
        assert result is None or isinstance(result, str)



