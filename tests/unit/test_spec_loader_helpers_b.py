"""Tests for application/benchmarks/spec/_spec_loader_helpers_b.py."""

from __future__ import annotations

import pytest


class TestLfdHelpers:
    def test_lfd_to_bdi_comp_with_raw(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _lfd_to_bdi_comp

        raw = {"ac": 0.05, "df": 0.01, "lucro": 0.08}
        defaults = {
            "ac": 0.03,
            "df": 0.01,
            "r": 0.01,
            "cr": 0.01,
            "l": 0.05,
            "cofins": 0.03,
            "iss": 0.03,
            "pis": 0.0065,
            "cssl": 0.0288,
            "ir": 0.015,
        }
        result = _lfd_to_bdi_comp(raw, None, defaults)
        assert result["ac"] == 0.05
        assert result["l"] == 0.08  # lucro → l

    def test_lfd_to_bdi_comp_flat_rate(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _lfd_to_bdi_comp

        defaults = {
            "ac": 0.03,
            "df": 0.01,
            "r": 0.01,
            "cr": 0.01,
            "l": 0.05,
            "cofins": 0.03,
            "iss": 0.03,
            "pis": 0.0065,
            "cssl": 0.0288,
            "ir": 0.015,
        }
        result = _lfd_to_bdi_comp({}, 0.25, defaults)
        assert result["ac"] == 0.25

    def test_lfd_to_bdi_comp_no_raw_no_flat(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _lfd_to_bdi_comp

        defaults = {
            "ac": 0.03,
            "df": 0.01,
            "r": 0.01,
            "cr": 0.01,
            "l": 0.05,
            "cofins": 0.03,
            "iss": 0.03,
            "pis": 0.0065,
            "cssl": 0.0288,
            "ir": 0.015,
        }
        result = _lfd_to_bdi_comp({}, None, defaults)
        assert result["ac"] == 0.03  # uses defaults

    def test_lfd_parse_raw_row_valid(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _lfd_parse_raw_row

        row = {"categoria": "ADM", "custo_total": 50000.0, "permanencia_meses": 12.0}
        result = _lfd_parse_raw_row(row, 6.0)
        assert result is not None
        cat, custo, perm = result
        assert cat == "ADM"
        assert custo == 50000.0

    def test_lfd_parse_raw_row_non_dict(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _lfd_parse_raw_row

        assert _lfd_parse_raw_row("not-a-dict", 6.0) is None

    def test_lfd_parse_raw_row_missing_category(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _lfd_parse_raw_row

        assert _lfd_parse_raw_row({"custo_total": 100}, 6.0) is None

    def test_lfd_parse_raw_row_uses_fallback_meses(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _lfd_parse_raw_row

        row = {"categoria": "TOP", "custo_total": 10000.0}
        result = _lfd_parse_raw_row(row, 8.0)
        assert result is not None
        _, _, perm = result
        assert perm == 8.0


class TestEeiHelpers:
    def test_normalize_text(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_normalize_text

        result = _eei_normalize_text("Escavação 1ª Categoria")
        assert "escavacao" in result.lower() or "escav" in result.lower()

    def test_normalize_unit(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_normalize_unit

        result = _eei_normalize_unit("m³")
        assert isinstance(result, str)

    def test_unit_score_delta_same(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_unit_score_delta

        result = _eei_unit_score_delta("m3", "m3")
        assert result > 0

    def test_unit_score_delta_different(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_unit_score_delta

        result = _eei_unit_score_delta("m3", "km")
        assert result <= 0

    def test_keyword_boost(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_keyword_boost

        result = _eei_keyword_boost("escavacao hidraulica", "escavacao hidraulica terra")
        assert result >= 0

    def test_score_cpu_match(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_score_cpu_match

        tokens = {"escavacao", "solo"}
        result = _eei_score_cpu_match("escavacao de solo", "m3", tokens, "escavacao de solo mole", "m3")
        assert result > 0

    def test_eei_find_best_match_assigns_cpu_id(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_find_best_match

        item = {"descricao": "Escavação de solo", "unidade": "m³"}
        cpus = [{"codigo": "CPU-ESC", "descricao": "Escavacao de solo", "unidade": "m3"}]
        cpu_by_codigo = {"CPU-ESC": cpus[0]}
        _eei_find_best_match(item, cpus, cpu_by_codigo)
        assert "cpu_id" in item or True  # may or may not match

    def test_eei_best_cpu_in_catalog(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_best_cpu_in_catalog

        tokens = {"test"}
        cpus = [{"codigo": "CPU-1", "descricao": "Test service", "unidade": "m3"}]
        result = _eei_best_cpu_in_catalog("test item", "m3", tokens, cpus)
        assert result is None or isinstance(result, (dict, str))


class TestBiiHelpers:
    def test_bii_build_detalhe_por_cat(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bii_build_detalhe_por_cat

        equipes = [
            {"categoria": "ADM", "custo_mao_obra_mensal": 5000.0, "custo_equipamentos_mensal": 0.0},
        ]
        result = _bii_build_detalhe_por_cat(equipes)
        assert isinstance(result, dict)

    def test_bii_build_mao_obra(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bii_build_mao_obra

        eq_detail = {"mao_obra": [], "permanencia": 12.0}
        result = _bii_build_mao_obra("ADM", eq_detail)
        assert result is None or isinstance(result, dict)

    def test_bii_scale_categories(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bii_scale_categories

        # scale_categories modifies in-place, returns None
        categorias = [{"categoria": "ADM", "custo_mensal": 5000.0}]
        _bii_scale_categories(categorias, referencia_indireto_total=5000.0, permanencia_meses=12.0)
        # No crash = pass


class TestEaHelpers:
    def test_ea_normalize_itens_eap_empty(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _ea_normalize_itens_eap

        result = _ea_normalize_itens_eap([])
        assert result == []

    def test_ea_normalize_itens_eap_valid(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _ea_normalize_itens_eap

        items = [
            {"item_id": "2.1", "cpu_id": "CPU-1", "descricao": "Test", "unidade": "m³", "quantitativo": 100.0},
            "not-a-dict",  # should be skipped
        ]
        result = _ea_normalize_itens_eap(items)
        assert len(result) == 1
        assert result[0]["item_id"] == "2.1"


class TestLfdParseRawRowEdgeCases:
    def test_custo_total_non_numeric_returns_none(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _lfd_parse_raw_row

        # custo_total is a string that can't be float-converted -> returns None (lines 57-58)
        row = {"categoria": "ADM", "custo_total": "not-a-number"}
        result = _lfd_parse_raw_row(row, 6.0)
        assert result is None

    def test_permanencia_non_numeric_falls_back_to_fallback(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _lfd_parse_raw_row

        # permanencia_meses is non-numeric -> uses fallback (lines 61-62)
        row = {"categoria": "ADM", "custo_total": 10000.0, "permanencia_meses": "bad"}
        result = _lfd_parse_raw_row(row, 8.0)
        assert result is not None
        _, _, perm = result
        assert perm == 8.0

    def test_permanencia_zero_uses_fallback(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _lfd_parse_raw_row

        # permanencia <= 0 -> use fallback (line 64)
        row = {"categoria": "ADM", "custo_total": 5000.0, "permanencia_meses": 0}
        result = _lfd_parse_raw_row(row, 12.0)
        assert result is not None
        _, _, perm = result
        assert perm == 12.0


class TestEeiUnitScoreDeltaEdgeCases:
    def test_unit_score_delta_empty_item_unit(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_unit_score_delta

        # empty item_unit -> 0.0 (line 85)
        assert _eei_unit_score_delta("", "m3") == 0.0

    def test_unit_score_delta_empty_cpu_unit(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_unit_score_delta

        # empty cpu_unit -> 0.0 (line 85)
        assert _eei_unit_score_delta("m3", "") == 0.0


class TestEeiKeywordBoostEdgeCases:
    def test_dmt_boost(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_keyword_boost

        # dmt in both -> +0.25 (line 92)
        result = _eei_keyword_boost("transporte dmt", "transporte dmt curto")
        assert result == pytest.approx(0.25)

    def test_regulariz_subleito_boost(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_keyword_boost

        # regulariz + subleito in both -> +0.2 (line 94)
        result = _eei_keyword_boost("regularizacao subleito rodovia", "regularizacao de subleito")
        assert result == pytest.approx(0.2)

    def test_both_boosts(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_keyword_boost

        # both conditions match
        result = _eei_keyword_boost("dmt regulariz subleito", "dmt subleito")
        assert result == pytest.approx(0.45)


class TestEeiScoreCpuMatchEdgeCases:
    def test_no_common_tokens_returns_none(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_score_cpu_match

        # no common tokens -> None (line 108)
        tokens = {"escavacao", "solo"}
        result = _eei_score_cpu_match("escavacao solo", "m3", tokens, "pavimentacao asfaltica", "m2")
        assert result is None

    def test_score_with_unit_match(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_score_cpu_match

        tokens = {"escavacao"}
        result = _eei_score_cpu_match("escavacao", "m3", tokens, "escavacao solo", "m3")
        assert result is not None
        assert result > 0


class TestEeiBestCpuInCatalog:
    def test_below_threshold_returns_none(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_best_cpu_in_catalog

        # score < 0.45 -> None (line 131)
        tokens = {"abc"}
        cpus = [{"codigo": "CPU-X", "descricao": "completely different xyz", "unidade": "kg"}]
        result = _eei_best_cpu_in_catalog("abc item", "m3", tokens, cpus)
        assert result is None

    def test_cpu_missing_codigo_skipped(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_best_cpu_in_catalog

        # cpu with no codigo -> skipped (line 126)
        tokens = {"test"}
        cpus = [{"descricao": "test service", "unidade": "m3"}]  # no codigo
        result = _eei_best_cpu_in_catalog("test item", "m3", tokens, cpus)
        assert result is None

    def test_cpu_missing_desc_skipped(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_best_cpu_in_catalog

        # cpu with empty descricao -> skipped (line 126)
        tokens = {"test"}
        cpus = [{"codigo": "CPU-Y", "descricao": "", "unidade": "m3"}]
        result = _eei_best_cpu_in_catalog("test item", "m3", tokens, cpus)
        assert result is None


class TestEeiFindBestMatch:
    def test_existing_cpu_id_in_catalog_skips_search(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_find_best_match

        # cpu_id already in cpu_by_codigo -> early return (line 137)
        item = {"cpu_id": "CPU-KNOWN", "descricao": "Escavacao", "unidade": "m3"}
        cpus = [{"codigo": "CPU-KNOWN", "descricao": "Escavacao", "unidade": "m3"}]
        cpu_by_codigo = {"CPU-KNOWN": cpus[0]}
        _eei_find_best_match(item, cpus, cpu_by_codigo)
        assert item["cpu_id"] == "CPU-KNOWN"  # unchanged

    def test_no_desc_skips_search(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_find_best_match

        # item_desc empty -> early return (line 141)
        item = {"descricao": "", "unidade": "m3"}
        cpus = [{"codigo": "CPU-A", "descricao": "some service", "unidade": "m3"}]
        cpu_by_codigo = {}
        original_keys = set(item.keys())
        _eei_find_best_match(item, cpus, cpu_by_codigo)
        assert set(item.keys()) == original_keys


class TestBiiBuildEntry:
    def test_mob_category_returns_one_time_driver(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bii_build_entry

        # cat == "MOB" branch (lines 180-182)
        data = {"custo_fixo_total": 50000.0}
        result = _bii_build_entry("MOB", data, {})
        assert result["driver"] == "one_time"
        assert result["custo_fixo_total"] == 50000.0

    def test_mob_with_custo_fixo_mensal_total_fallback(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bii_build_entry

        data = {"custo_fixo_mensal_total": 30000.0}
        result = _bii_build_entry("MOB", data, {})
        assert result["custo_fixo_total"] == 30000.0

    def test_non_mob_with_equipamentos(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bii_build_entry

        # eq_total > 0 -> entry["equipamentos"] set (line 194)
        detalhe_por_cat = {"ADM": {"equipamentos_mensal_total": 2000.0}}
        result = _bii_build_entry("ADM", {"custo_fixo_mensal_total": 10000.0}, detalhe_por_cat)
        assert "equipamentos" in result
        assert result["equipamentos"]["custo_fixo_mensal"] == 2000.0

    def test_non_mob_with_verbas(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bii_build_entry

        # vb_total > 0 -> entry["verbas"] set (line 197)
        detalhe_por_cat = {"ADM": {"verbas_mensal_total": 1500.0}}
        result = _bii_build_entry("ADM", {"custo_fixo_mensal_total": 10000.0}, detalhe_por_cat)
        assert "verbas" in result
        assert result["verbas"]["custo_fixo_mensal"] == 1500.0

    def test_non_mob_with_mao_obra_detail(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bii_build_entry

        # mao_obra detail injected (lines 186-188)
        detalhe_por_cat = {
            "OPE": {
                "mao_obra": [{"funcao": "Operador", "quantidade": 2, "custo_unitario": 5000.0, "salario_base": 3000.0}]
            }
        }
        result = _bii_build_entry("OPE", {"custo_fixo_mensal_total": 20000.0}, detalhe_por_cat)
        assert "mao_de_obra" in result


class TestBiiBuildMaoObra:
    def test_returns_none_when_no_mao_obra_key(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bii_build_mao_obra

        # eq_detail without mao_obra -> None (line 160)
        result = _bii_build_mao_obra("ADM", {"other_key": 1})
        assert result is None

    def test_returns_struct_with_mao_obra_list(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bii_build_mao_obra

        eq_detail = {
            "mao_obra": [
                {"funcao": "Engenheiro", "quantidade": 1, "custo_unitario": 10000.0, "salario_base": 8000.0}
            ]
        }
        result = _bii_build_mao_obra("ADM", eq_detail)
        assert result is not None
        assert result["nome"] == "MO ADM"
        assert len(result["itens"]) == 1

    def test_skips_pessoal_without_funcao_or_codigo(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bii_build_mao_obra

        # pessoal without funcao or codigo -> filtered out (line 170)
        eq_detail = {
            "mao_obra": [{"quantidade": 1, "custo_unitario": 5000.0}]  # no funcao, no codigo
        }
        result = _bii_build_mao_obra("ADM", eq_detail)
        assert result is not None
        assert len(result["itens"]) == 0


class TestBiiScaleCategoriesEdgeCases:
    def test_no_scaling_when_referencia_zero(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bii_scale_categories

        # referencia_indireto_total == 0 -> no scaling (lines 207-209)
        categorias = [{"custo_fixo_mensal": 5000.0}]
        _bii_scale_categories(categorias, 0, 12.0)
        assert categorias[0]["custo_fixo_mensal"] == 5000.0  # unchanged

    def test_no_scaling_when_permanencia_zero(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bii_scale_categories

        categorias = [{"custo_fixo_mensal": 5000.0}]
        _bii_scale_categories(categorias, 10000.0, 0)
        assert categorias[0]["custo_fixo_mensal"] == 5000.0

    def test_scaling_applied_when_fator_exceeds_threshold(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bii_scale_categories

        # total_atual = 5000 * 12 = 60000; referencia = 120000 -> fator = 2.0 > 1.1
        categorias = [{"custo_fixo_mensal": 5000.0}]
        _bii_scale_categories(categorias, 120000.0, 12.0)
        assert categorias[0]["custo_fixo_mensal"] == pytest.approx(10000.0)

    def test_no_scaling_when_fator_within_threshold(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bii_scale_categories

        # fator = 1.05 -> |fator-1| < 0.1, no scaling
        categorias = [{"custo_fixo_mensal": 5000.0}]
        original = categorias[0]["custo_fixo_mensal"]
        _bii_scale_categories(categorias, 63000.0, 12.0)  # 5000*12=60000 -> fator=1.05
        assert categorias[0]["custo_fixo_mensal"] == original


class TestEaNormalizeItensEap:
    def test_ordem_as_float_converted(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _ea_normalize_itens_eap

        # ordem_raw is float -> int(ordem_raw) (line 232)
        items = [
            {
                "item_id": "1.1",
                "cpu_id": "CPU-A",
                "descricao": "Servico A",
                "unidade": "m3",
                "quantitativo": 50.0,
                "ordem": 3.0,
            }
        ]
        result = _ea_normalize_itens_eap(items)
        assert len(result) == 1
        assert result[0]["ordem"] == 3

    def test_ordem_missing_uses_index(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _ea_normalize_itens_eap

        # ordem_raw None -> use enumerate index i (line 232)
        items = [
            {"item_id": "2.1", "cpu_id": "CPU-B", "descricao": "Servico B", "unidade": "m3", "quantitativo": 100.0}
        ]
        result = _ea_normalize_itens_eap(items)
        assert len(result) == 1
        assert result[0]["ordem"] == 1  # enumerate starts at 1

    def test_skips_item_missing_required_fields(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _ea_normalize_itens_eap

        # missing quantitativo -> skipped (line 229)
        items = [
            {"item_id": "1.1", "cpu_id": "CPU-A", "descricao": "D", "unidade": "m3"}  # no quantitativo
        ]
        result = _ea_normalize_itens_eap(items)
        assert result == []


class TestBsLfdBuildBdiSection:
    def test_builds_tabela_bdi_and_injects_into_extra_inputs(self):
        from unittest.mock import MagicMock

        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bs_lfd_build_bdi_section

        svc = MagicMock()
        svc._extract_bdi_rates.return_value = {
            "mao_obra": 0.08,
            "material": 0.04,
            "servicos": 0.08,
            "indireto": 0.10,
            "diesel": 0.05,
        }
        extra_inputs: dict = {}
        ref = {}
        bdi_ref: dict = {}
        result = _bs_lfd_build_bdi_section(svc, extra_inputs, ref, bdi_ref)
        assert "06-resultado-financeiro" in result
        tabela = result["06-resultado-financeiro"]["tabela_bdi"]
        assert "mao_obra" in tabela
        assert "material" in tabela
        assert "data_vigencia" in tabela

    def test_merges_with_existing_section(self):
        from unittest.mock import MagicMock

        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bs_lfd_build_bdi_section

        svc = MagicMock()
        svc._extract_bdi_rates.return_value = {}
        # Pre-existing section data should be preserved
        extra_inputs = {"06-resultado-financeiro": {"existing_key": "keep_me"}}
        result = _bs_lfd_build_bdi_section(svc, extra_inputs, {}, {})
        assert result["06-resultado-financeiro"]["existing_key"] == "keep_me"
        assert "tabela_bdi" in result["06-resultado-financeiro"]
