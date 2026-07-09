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

_ROOT = Path(__file__).resolve().parents[2]


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


# ── _indiretos/_skill_helpers_a.py ────────────────────────────────────────────


class TestMesesEntre:
    def test_meses_entre_basic(self):
        """Line 38: return value of _meses_entre."""
        from datetime import date

        mod = _load_ind_helpers_a()
        result = mod._meses_entre(date(2026, 1, 1), date(2026, 6, 30))
        assert result == 6


class TestDmfFindTemplateId:
    def test_acima_de_branch_returns_template(self):
        """Lines 122-123: 'acima_de' step matches."""
        mod = _load_ind_helpers_a()
        regra = {
            "steps": [
                {"acima_de": 500_000, "equipe_base": "TPL-GRANDE"},
                {"ate_valor": 500_000, "equipe_base": "TPL-PEQUENO"},
            ]
        }
        result = mod._dmf_find_template_id(regra, 1_000_000.0)
        assert result == "TPL-GRANDE"

    def test_no_matching_step_returns_none(self):
        """Line 124: return None when no step matches."""
        mod = _load_ind_helpers_a()
        regra = {"steps": []}
        result = mod._dmf_find_template_id(regra, 100.0)
        assert result is None

    def test_first_step_no_match_continues_to_next(self):
        """Branch 122->119: primeiro step não casa nenhuma condição -> continua para o próximo."""
        mod = _load_ind_helpers_a()
        regra = {
            "steps": [
                {"acima_de": 999_999.0, "equipe_base": "TPL-NUNCA"},
                {"ate_valor": 100.0, "equipe_base": "TPL-PEQUENO"},
            ]
        }
        result = mod._dmf_find_template_id(regra, 50.0)
        assert result == "TPL-PEQUENO"


class TestDaMagnitudeFinanceira:
    def _mk_canonical(self, total_venda):
        from types import SimpleNamespace

        plan_item = SimpleNamespace(subtotal=SimpleNamespace(sem_bdi=SimpleNamespace(total=total_venda)))
        return SimpleNamespace(planejamento=[plan_item])

    def test_no_tpl_id_returns_none(self):
        """Line 132: tpl_id is None → return None."""
        mod = _load_ind_helpers_a()
        canonical = self._mk_canonical(100.0)
        regra = {"steps": []}  # no matching step
        result = mod._da_magnitude_financeira("ADM", regra, canonical, {})
        assert result is None

    def test_template_not_found_returns_none(self):
        """Line 137: tpl_id found but template not in estruturas → return None."""
        mod = _load_ind_helpers_a()
        canonical = self._mk_canonical(1_500_000.0)
        regra = {"steps": [{"acima_de": 1_000_000, "equipe_base": "TPL-X"}]}
        catalogo = {"estruturas_indiretas": [{"codigo": "OTHER", "mao_de_obra": []}]}
        result = mod._da_magnitude_financeira("ADM", regra, canonical, catalogo)
        assert result is None

    def test_template_found_returns_dict(self):
        """Line 170: magnitude_financeira returns valid result."""
        mod = _load_ind_helpers_a()
        canonical = self._mk_canonical(1_500_000.0)
        regra = {
            "driver": "magnitude_financeira",
            "steps": [{"acima_de": 1_000_000, "equipe_base": "TPL-X"}],
        }
        catalogo = {
            "estruturas_indiretas": [
                {
                    "codigo": "TPL-X",
                    "mao_de_obra": [{"funcao_id": "ENG", "quantidade": 1}],
                    "equipamentos": [],
                    "verbas": [],
                }
            ]
        }
        result = mod._dimensionar_automatico("ADM", regra, canonical, catalogo)
        assert "mao_de_obra" in result


class TestBcfdResolveSalarioBase:
    def test_exception_returns_preco(self):
        """Lines 202-203: ConversorUnidades.converter_preco raises → returns preco."""
        mod = _load_ind_helpers_a()
        with patch(
            "concilium.domain.services.conversor_unidades.ConversorUnidades.converter_preco",
            side_effect=ValueError("unknown unit"),
        ):
            result = mod._bcfd_resolve_salario_base(5000.0, "semana_invalida")
        assert result == 5000.0


class TestBcfdApplyEncargos:
    def test_override_val_returns_override(self):
        """Line 216: custo_com_encargos override > 0 → return float(override_val)."""
        mod = _load_ind_helpers_a()
        atrib = {"custo_com_encargos": 9999.0}
        result = mod._bcfd_apply_encargos(5000.0, atrib)
        assert result == 9999.0

    def test_resolver_encargo_path(self):
        """Line 217: resolver_encargo called when no override."""
        mod = _load_ind_helpers_a()
        with patch(
            "concilium.domain.services.financial.encargo_resolver.resolver_encargo",
            return_value=0.5,
        ):
            result = mod._bcfd_apply_encargos(1000.0, {})
        assert result == pytest.approx(1500.0)


class TestBcfdEnrichMoItem:
    def test_descricao_already_present_skips_assignment(self):
        """Line 242->exit: 'descricao' already in f → if-body not executed."""
        mod = _load_ind_helpers_a()
        repo = MagicMock()
        repo.obter_insumo.return_value = {
            "preco_unitario": 1000.0,
            "unidade": "mes",
            "atributos_especificos": {},
        }
        repo.resolver_preco.return_value = (1000.0, "catalog")

        f = {"funcao_id": "ENG-001", "descricao": "Engenheiro já definido"}
        mod._bcfd_enrich_mo_item(f, repo, None, None, None)
        assert f["descricao"] == "Engenheiro já definido"
        assert "custo_mensal" in f

    def test_descricao_missing_gets_assigned(self):
        """Lines 242-243: 'descricao' not in f → assigned from insumo."""
        mod = _load_ind_helpers_a()
        repo = MagicMock()
        repo.obter_insumo.return_value = {
            "preco_unitario": 800.0,
            "unidade": "mes",
            "descricao": "Técnico de Campo",
            "atributos_especificos": {},
        }
        repo.resolver_preco.return_value = (800.0, "catalog")

        f = {"funcao_id": "TEC-001"}
        mod._bcfd_enrich_mo_item(f, repo, None, None, None)
        assert f.get("descricao") == "Técnico de Campo"

    def test_no_insumo_returns_early(self):
        """Lines 229-230: insumo not found → return early, f unchanged."""
        mod = _load_ind_helpers_a()
        repo = MagicMock()
        repo.obter_insumo.return_value = None
        f = {"funcao_id": "MISSING-001"}
        mod._bcfd_enrich_mo_item(f, repo, None, None, None)
        assert "custo_mensal" not in f


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


# ── recursos.py (excel sheets) ────────────────────────────────────────────────


class TestRenderCalendarioOperacional:
    def test_item_not_dict_nor_model_uses_empty_row_data(self):
        """Line 77: item is neither model_dump-able nor dict → row_data = {}."""
        from openpyxl import Workbook

        from concilium.infrastructure.adapters.excel.sheets.recursos import render_calendario_operacional

        wb = Workbook()
        canonical = MagicMock()
        # a plain string is neither a model nor a dict
        canonical.calendario_operacional = ["plain_string"]
        canonical.cronograma = None

        render_calendario_operacional(wb, canonical)
        ws = wb["CALENDARIO.OP"]
        # semana = str({}.get("semana_iso", "")) == ""
        assert ws.cell(row=5, column=1).value == ""


class TestRenderEquipeIndireto:
    def _make_entry(self, with_equipamentos=True):
        from types import SimpleNamespace

        funcoes = [{"funcao_id": "ENG", "num_pessoas": 2, "custo_mensal_unitario": 5000.0, "custo_total": 10000.0}]
        equipamentos = (
            [{"equip_id": "EQ-1", "num_unidades": 1, "custo_mensal": 2000.0, "custo_total": 2000.0}]
            if with_equipamentos
            else []
        )
        return SimpleNamespace(
            categoria="ADM",
            custo_total=12000.0,
            custo_mao_obra=10000.0,
            custo_equipamentos=2000.0,
            custo_combustivel=0.0,
            funcoes=funcoes,
            equipamentos=equipamentos,
        )

    def _make_canonical(self, entry):
        canonical = MagicMock()
        canonical.indiretos = [entry]
        return canonical

    def test_equipamentos_loop_renders_rows(self):
        """Lines 271-295: equipamentos loop in render_equipe_indireto."""
        from openpyxl import Workbook

        from concilium.infrastructure.adapters.excel.sheets.recursos import render_equipe_indireto

        wb = Workbook()
        canonical = self._make_canonical(self._make_entry(with_equipamentos=True))
        render_equipe_indireto(wb, canonical, "ADM")
        ws = wb["EQUIPE.INDIRETO.ADM"]
        all_vals = [ws.cell(row=r, column=1).value for r in range(1, 20)]
        assert "EQUIPAMENTO" in all_vals

    def test_no_equipamentos_renders_only_funcoes(self):
        """Equipamentos loop skipped when empty; has_rows=True from funcoes."""
        from openpyxl import Workbook

        from concilium.infrastructure.adapters.excel.sheets.recursos import render_equipe_indireto

        wb = Workbook()
        canonical = self._make_canonical(self._make_entry(with_equipamentos=False))
        render_equipe_indireto(wb, canonical, "ADM")
        ws = wb["EQUIPE.INDIRETO.ADM"]
        all_vals = [ws.cell(row=r, column=1).value for r in range(1, 20)]
        assert "MÃO DE OBRA" in all_vals
        assert "EQUIPAMENTO" not in all_vals

    def test_entry_not_found_shows_message(self):
        """Lines 218-223: categoria not found → message displayed."""
        from openpyxl import Workbook

        from concilium.infrastructure.adapters.excel.sheets.recursos import render_equipe_indireto

        wb = Workbook()
        canonical = MagicMock()
        canonical.indiretos = []
        render_equipe_indireto(wb, canonical, "LAB")
        ws = wb["EQUIPE.INDIRETO.LAB"]
        assert any("não encontrada" in str(ws.cell(row=r, column=1).value or "") for r in range(1, 5))

    def test_no_funcoes_no_equipamentos_shows_fallback(self):
        """Lines 297-303: has_rows=False → fallback cell shown."""
        from types import SimpleNamespace

        from openpyxl import Workbook

        from concilium.infrastructure.adapters.excel.sheets.recursos import render_equipe_indireto

        wb = Workbook()
        entry = SimpleNamespace(
            categoria="TOP",
            custo_total=5000.0,
            custo_mao_obra=0.0,
            custo_equipamentos=0.0,
            custo_combustivel=0.0,
            funcoes=[],
            equipamentos=[],
        )
        canonical = MagicMock()
        canonical.indiretos = [entry]
        render_equipe_indireto(wb, canonical, "TOP")
        ws = wb["EQUIPE.INDIRETO.TOP"]
        all_vals = [str(ws.cell(row=r, column=1).value or "") for r in range(1, 20)]
        assert any("Sem equipes" in v for v in all_vals)
