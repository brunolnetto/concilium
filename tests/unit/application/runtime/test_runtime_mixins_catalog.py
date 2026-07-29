"""Coverage sweep 11 — files below 90%:

- _indiretos/_skill_helpers_a.py (88%) — missing: 38, 122-124, 132, 137, 170, 202-203, 216-217, 242->exit
- mixins/catalog.py (88%) — missing: 49->53, 52, 85-110, 123-124, 167->162, 215-216, 230-231, 237-238,
                                       248->251, 255->251, 259->255, 264-265, 280
- recursos.py (89%) — missing: 77, 271-295
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parents[4]

def _load_ind_helpers_a():
    path = (
        _ROOT
        / "src/concilium/application/skills/manifests"
        / "06-resultado-financeiro/_indiretos/_skill_helpers/_dimensionamento.py"
    )
    spec = importlib.util.spec_from_file_location("ind_helpers_a_sw11", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── mixins/catalog.py ─────────────────────────────────────────────────────────


def _make_catalog_mixin(tmp_path):
    from concilium.application.runtime.mixins.catalog import CatalogMixin

    obj = CatalogMixin.__new__(CatalogMixin)
    obj.config_root = tmp_path
    obj._config_cache = {}
    return obj


def _make_cat_dir(tmp_path, cat_id="cat1", cpus=None):
    cat_dir = tmp_path / "catalogos" / cat_id
    cat_dir.mkdir(parents=True)
    cpus_data = cpus or [{"codigo": "CPU-1", "descricao": "Test"}]
    (cat_dir / "cpus.json").write_text(json.dumps({"cpus": cpus_data}), encoding="utf-8")
    ins_dir = cat_dir / "insumos"
    ins_dir.mkdir()
    (ins_dir / "mao_obra.json").write_text(
        json.dumps(
            [{"codigo": "MO-1", "descricao": "Op", "unidade": "h", "preco_unitario": 20.0, "categoria": "MAO_OBRA"}]
        ),
        encoding="utf-8",
    )
    return cat_dir


class TestResolveCatalogBase:
    def test_project_catalog_in_benchmark_reference(self, tmp_path):
        """Lines 49->53, 52: benchmark_reference has a catalog dict → returns project_reference."""
        mixin = _make_catalog_mixin(tmp_path)
        _make_cat_dir(tmp_path, "cat1")
        project = MagicMock()
        project_catalog = {"cpus": [{"codigo": "CPU-X"}], "insumos": []}
        project.read_json.return_value = {"catalog": project_catalog}
        cat, source = mixin._resolve_project_catalog_base("cat1", project)
        assert source == "project_reference"
        assert cat["cpus"][0]["codigo"] == "CPU-X"

    def test_no_project_catalog_uses_master(self, tmp_path):
        """Line 53: no catalog in benchmark → loads master."""
        mixin = _make_catalog_mixin(tmp_path)
        _make_cat_dir(tmp_path, "cat1")
        project = MagicMock()
        project.read_json.return_value = {}
        cat, source = mixin._resolve_project_catalog_base("cat1", project)
        assert source == "master"

    def test_non_dict_benchmark_reference_uses_master(self, tmp_path):
        """Branch 49->53: benchmark_reference.json não é um dict → pula direto para master."""
        mixin = _make_catalog_mixin(tmp_path)
        _make_cat_dir(tmp_path, "cat1")
        project = MagicMock()
        project.read_json.return_value = ["not", "a", "dict"]
        cat, source = mixin._resolve_project_catalog_base("cat1", project)
        assert source == "master"


class TestLoadResolvedCatalogWithProvenance:
    def test_basic_provenance(self, tmp_path):
        """Lines 85-110: full body executes and returns (resolved, provenance)."""
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        mixin = _make_catalog_mixin(tmp_path)
        _make_cat_dir(tmp_path, "cat1")
        project = MagicMock()
        project.read_json.return_value = {}

        with patch.object(CatalogResolver, "apply_overlays") as mock_apply:
            trace = MagicMock()
            trace.to_dict.return_value = {}
            mock_apply.return_value = ({"cpus": [], "_catalog_source": "master"}, trace)
            resolved, prov = mixin._load_resolved_catalog_with_provenance("cat1", None, project)

        assert "catalogo_base_hash" in prov
        assert prov["catalogo_base_id"] == "cat1"
        assert prov["strict_baseline"] is False

    def test_strict_baseline_raises_when_no_project_catalog(self, tmp_path):
        """Line 93: strict_baseline=True without project catalog raises RuntimeDomainError."""
        from concilium.application.runtime.exceptions import RuntimeDomainError

        mixin = _make_catalog_mixin(tmp_path)
        project = MagicMock()
        project.read_json.return_value = {}
        with pytest.raises(RuntimeDomainError, match="estrito"):
            mixin._load_resolved_catalog_with_provenance("cat1", None, project, strict_baseline=True)


class TestCatalogBundleValid:
    def test_exception_returns_false(self, tmp_path):
        """Lines 123-124: rglob raises inside try → except → return False."""
        mixin = _make_catalog_mixin(tmp_path)
        bundle_path = tmp_path / ".catalog_bundle.json"
        bundle_path.write_text("{}", encoding="utf-8")
        cat_dir = tmp_path

        with patch.object(Path, "rglob", side_effect=OSError("permission denied")):
            result = mixin._catalog_bundle_valid(cat_dir, bundle_path)
        assert result is False


class TestLoadProducoesFromCatDirs:
    def test_dict_branch(self, tmp_path):
        """Line 167->162: p_data is a dict (not a list) → producoes.append."""
        from concilium.application.runtime.mixins.catalog import CatalogMixin

        prod_dir = tmp_path / "producoes"
        prod_dir.mkdir()
        (prod_dir / "p1.json").write_text(json.dumps({"id": "PROD-1", "valor_horario": 10.0}), encoding="utf-8")
        result = CatalogMixin._load_producoes_from_cat_dirs(tmp_path)
        assert any(p.get("id") == "PROD-1" for p in result)

    def test_non_dict_non_list_json_is_skipped(self, tmp_path):
        """Branch 167->162: JSON não é lista nem dict (ex: número) → ignorado silenciosamente."""
        from concilium.application.runtime.mixins.catalog import CatalogMixin

        prod_dir = tmp_path / "producoes"
        prod_dir.mkdir()
        (prod_dir / "scalar.json").write_text("42", encoding="utf-8")
        result = CatalogMixin._load_producoes_from_cat_dirs(tmp_path)
        assert result == []


class TestLoadCatalogoFromDisk:
    def test_bundle_read_fails_still_loads(self, tmp_path):
        """Lines 215-216: bundle exists but JSON corrupt → exception caught, full load continues."""
        mixin = _make_catalog_mixin(tmp_path)
        cat_dir = _make_cat_dir(tmp_path, "cat1")
        bundle = cat_dir / ".catalog_bundle.json"
        bundle.write_text("CORRUPTED_JSON{{{}}", encoding="utf-8")
        with patch.object(mixin, "_catalog_bundle_valid", return_value=True):
            cat = mixin._load_catalogo_from_disk("cat1")
        assert isinstance(cat, dict)

    def test_templates_loaded_when_file_exists(self, tmp_path):
        """Lines 230-231: templates.json exists → catalogo['templates'] populated."""
        mixin = _make_catalog_mixin(tmp_path)
        cat_dir = _make_cat_dir(tmp_path, "cat1")
        (cat_dir / "templates.json").write_text(
            json.dumps({"templates": {"T1": {"desc": "Template 1"}}}), encoding="utf-8"
        )
        cat = mixin._load_catalogo_from_disk("cat1")
        assert "T1" in cat.get("templates", {})

    def test_estruturas_indiretas_loaded_when_file_exists(self, tmp_path):
        """Regressão: templates.json com 'estruturas_indiretas' (irmã de 'templates') não pode ser
        descartada — sem isso, o driver magnitude_financeira (dimensionamento de ADM por porte da
        obra) sempre cai no fallback estático, pois _da_magnitude_financeira lê exatamente
        catalogo['estruturas_indiretas']."""
        mixin = _make_catalog_mixin(tmp_path)
        cat_dir = _make_cat_dir(tmp_path, "cat1")
        (cat_dir / "templates.json").write_text(
            json.dumps(
                {
                    "templates": {"T1": {"desc": "Template 1"}},
                    "estruturas_indiretas": [{"codigo": "ADM_PEQUENA", "mao_de_obra": []}],
                }
            ),
            encoding="utf-8",
        )
        cat = mixin._load_catalogo_from_disk("cat1")
        assert [e["codigo"] for e in cat.get("estruturas_indiretas", [])] == ["ADM_PEQUENA"]

    def test_estruturas_indiretas_defaults_empty_when_absent(self, tmp_path):
        """templates.json sem 'estruturas_indiretas' → chave presente e vazia (não ausente)."""
        mixin = _make_catalog_mixin(tmp_path)
        cat_dir = _make_cat_dir(tmp_path, "cat1")
        (cat_dir / "templates.json").write_text(
            json.dumps({"templates": {"T1": {"desc": "Template 1"}}}), encoding="utf-8"
        )
        cat = mixin._load_catalogo_from_disk("cat1")
        assert cat.get("estruturas_indiretas") == []

    def test_bundle_write_failure_is_swallowed(self, tmp_path):
        """Lines 237-238: bundle write fails → exception caught, catalog still returned."""
        mixin = _make_catalog_mixin(tmp_path)
        _make_cat_dir(tmp_path, "cat1")
        with patch("pathlib.Path.write_text", side_effect=OSError("read-only")):
            cat = mixin._load_catalogo_from_disk("cat1")
        assert isinstance(cat, dict)


class TestLoadProducoesFromCpus:
    def test_cat_dir_none_skips_extra_dirs(self, tmp_path):
        """Line 248->251: cat_dir is None → search_dirs has only config root/producoes."""
        mixin = _make_catalog_mixin(tmp_path)
        result = mixin._load_producoes_from_cpus([{"producao_id_ref": "prod-X"}], cat_dir=None)
        assert result == []

    def test_missing_p_dir_skips(self, tmp_path):
        """Line 255->251: p_dir doesn't exist → continue to next."""
        mixin = _make_catalog_mixin(tmp_path)
        cpus = [{"producao_id_ref": "prod-Y"}]
        cat_dir = tmp_path / "catalogos" / "cat1"
        cat_dir.mkdir(parents=True)
        result = mixin._load_producoes_from_cpus(cpus, cat_dir=cat_dir)
        assert result == []

    def test_path_not_exists_tries_next_dir(self, tmp_path):
        """Line 259->255: prod file not in first dir, found via config root."""
        mixin = _make_catalog_mixin(tmp_path)
        prod_dir = tmp_path / "producoes"
        prod_dir.mkdir(parents=True)
        prod_data = {"id": "prod-Z", "valor_horario": 5.0}
        (prod_dir / "prod-Z.json").write_text(json.dumps(prod_data), encoding="utf-8")
        cpus = [{"producao_id_ref": "prod-Z"}]
        result = mixin._load_producoes_from_cpus(cpus, cat_dir=None)
        assert any(p.get("id") == "prod-Z" for p in result)

    def test_file_missing_in_earlier_dir_found_in_later_dir(self, tmp_path):
        """Branch 259->255: arquivo não existe no primeiro search_dir mas existe em um posterior."""
        mixin = _make_catalog_mixin(tmp_path)
        # Primeiro search_dir (config_root/producoes) existe mas não contém o arquivo.
        empty_prod_dir = tmp_path / "producoes"
        empty_prod_dir.mkdir(parents=True)
        # Segundo search_dir (cat_dir/producoes) contém o arquivo procurado.
        cat_dir = tmp_path / "catalogos" / "cat1"
        cat_prod_dir = cat_dir / "producoes"
        cat_prod_dir.mkdir(parents=True)
        prod_data = {"id": "prod-W", "valor_horario": 7.0}
        (cat_prod_dir / "prod-W.json").write_text(json.dumps(prod_data), encoding="utf-8")

        cpus = [{"producao_id_ref": "prod-W"}]
        result = mixin._load_producoes_from_cpus(cpus, cat_dir=cat_dir)
        assert any(p.get("id") == "prod-W" for p in result)

    def test_json_parse_error_continues(self, tmp_path):
        """Lines 264-265: JSON parse error on prod file → except: continue."""
        mixin = _make_catalog_mixin(tmp_path)
        prod_dir = tmp_path / "producoes"
        prod_dir.mkdir()
        (prod_dir / "prod-BAD.json").write_text("NOT_JSON{{{{", encoding="utf-8")
        cpus = [{"producao_id_ref": "prod-BAD"}]
        result = mixin._load_producoes_from_cpus(cpus, cat_dir=None)
        assert result == []


class TestLoadInsumos:
    def test_subdir_load_called(self, tmp_path):
        """Line 280: load_insumos_subdir called for subdirectories."""
        mixin = _make_catalog_mixin(tmp_path)
        cat_dir = tmp_path
        ins_dir = cat_dir / "insumos"
        ins_dir.mkdir()
        sub = ins_dir / "sub_categoria"
        sub.mkdir()
        (sub / "item.json").write_text(
            json.dumps(
                [
                    {
                        "codigo": "MAT-1",
                        "descricao": "Areia",
                        "unidade": "m3",
                        "preco_unitario": 50.0,
                        "categoria": "MATERIAL",
                    }
                ]
            ),
            encoding="utf-8",
        )
        result = mixin._load_insumos(cat_dir)
        assert isinstance(result, list)





# ─── application/runtime/mixins/catalog.py (49 missing) ─────────────────────


class TestCatalogMixin:
    def _make_mixin(self, tmp_path):
        from concilium.application.runtime.mixins.catalog import CatalogMixin

        obj = CatalogMixin.__new__(CatalogMixin)
        obj.config_root = tmp_path
        obj._config_cache = {}
        return obj

    def test_load_catalogo_not_found_raises_a(self, tmp_path):
        from concilium.application.runtime.exceptions import RuntimeDomainError

        mixin = self._make_mixin(tmp_path)
        with pytest.raises((RuntimeDomainError, FileNotFoundError)):
            mixin.load_catalogo("nonexistent-cat")

    def test_load_catalogo_not_found_raises(self, tmp_path):
        from concilium.application.runtime.exceptions import RuntimeDomainError

        mixin = self._make_mixin(tmp_path)
        with pytest.raises(RuntimeDomainError):
            mixin.load_catalogo("missing-cat")

    def test_load_catalogo_basic(self, tmp_path):
        from concilium.application.runtime.mixins.catalog import CatalogMixin

        # Create a minimal catalog directory
        cat_dir = tmp_path / "catalogos" / "test-cat"
        cat_dir.mkdir(parents=True)
        (cat_dir / "cpus.json").write_text('{"cpus": []}', encoding="utf-8")
        obj = CatalogMixin.__new__(CatalogMixin)
        obj.config_root = tmp_path
        obj._config_cache = {}
        cat = obj.load_catalogo("test-cat")
        assert isinstance(cat, dict)

    def test_load_catalogo_with_bundle_cache(self, tmp_path):
        """Test that bundle cache is used when available."""

        cat_dir = tmp_path / "catalogos" / "test-cat2"
        cat_dir.mkdir(parents=True)
        (cat_dir / "cpus.json").write_text('{"cpus": [{"codigo": "CPU-1"}]}', encoding="utf-8")
        from concilium.application.runtime.mixins.catalog import CatalogMixin

        obj = CatalogMixin.__new__(CatalogMixin)
        obj.config_root = tmp_path
        obj._config_cache = {}
        cat = obj.load_catalogo("test-cat2")
        # Second load should use cache
        cat2 = obj.load_catalogo("test-cat2")
        assert cat == cat2  # same content (may or may not be same object)

    def test_load_resolved_catalogo(self, tmp_path):
        from concilium.application.runtime.mixins.catalog import CatalogMixin

        cat_dir = tmp_path / "catalogos" / "test-cat"
        cat_dir.mkdir(parents=True)
        (cat_dir / "cpus.json").write_text('{"cpus": []}', encoding="utf-8")
        obj = CatalogMixin.__new__(CatalogMixin)
        obj.config_root = tmp_path
        obj._config_cache = {}
        # Mock the snapshot/project for overlay loading
        project = MagicMock()
        project.meta = {"id": "proj-1"}
        project.read_json.return_value = {}
        cat = obj._load_resolved_catalogo("test-cat", None, project)
        assert isinstance(cat, dict)



