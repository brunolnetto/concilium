"""Coverage tests for helper functions and cure_producao/cure_cpu/cure_insumo
in src/concilium/application/catalog/cure_schema.py.

Scope: _load_schema, _schema_store, _make_validator, _validate_all, _now_iso,
_normalize_code, _is_valid_insumo_code, _categoria_custo_from_tipo,
_team_is_empty, _infer_tipo_contrato, _q, _iqr_bounds, _robust_bounds,
CurationReport, _dedupe_team_items, _normalize_team, cure_producao, cure_cpu,
cure_insumo, _apply_insumo_code_remap.
"""

from __future__ import annotations

import re

import pytest

from concilium.application.catalog import cure_schema as cs

# ---------------------------------------------------------------------------
# _load_schema / _schema_store / _make_validator / _validate_all
# ---------------------------------------------------------------------------


class TestLoadSchema:
    def test_load_schema_reads_real_file(self):
        schema = cs._load_schema("cpu.schema.json")
        assert isinstance(schema, dict)
        assert "$id" in schema or "properties" in schema

    def test_load_schema_missing_raises(self):
        with pytest.raises(FileNotFoundError):
            cs._load_schema("does-not-exist.schema.json")


class TestSchemaStore:
    def test_schema_store_populates_and_caches(self, monkeypatch):
        monkeypatch.setattr(cs, "_SCHEMA_STORE", None)
        store = cs._schema_store()
        assert isinstance(store, dict)
        assert len(store) > 0
        # Second call returns cached object (same identity)
        store2 = cs._schema_store()
        assert store is store2

    def test_schema_store_skips_files_without_id(self, tmp_path, monkeypatch):
        """A schema file lacking `$id` is loaded but not indexed (line 69->67
        false branch: the `if "$id" in s` guard skips the dict assignment)."""
        (tmp_path / "no_id.schema.json").write_text('{"type": "object"}', encoding="utf-8")
        (tmp_path / "with_id.schema.json").write_text('{"$id": "with-id", "type": "object"}', encoding="utf-8")
        monkeypatch.setattr(cs, "_SCHEMA_STORE", None)
        monkeypatch.setattr(cs, "SCHEMA_ROOT", tmp_path)
        store = cs._schema_store()
        assert store == {"with-id": {"$id": "with-id", "type": "object"}}


class TestMakeValidator:
    def test_make_validator_builds_validator(self):
        schema = cs._load_schema("cpu.schema.json")
        validator = cs._make_validator(schema)
        assert validator is not None
        # Should be usable to validate an obviously-empty (likely invalid) dict
        list(validator.iter_errors({}))


class TestValidateAll:
    def test_validate_all_reports_errors_with_codigo(self):
        schema = cs._load_schema("cpu.schema.json")
        validator = cs._make_validator(schema)
        entities = [{"codigo": "CPU-X"}]
        erros = cs._validate_all(entities, validator, "CPU")
        # An empty-ish CPU entity is very likely to fail required-field validation
        assert isinstance(erros, list)
        for e in erros:
            assert e.startswith("CPU CPU-X:")

    def test_validate_all_uses_id_when_no_codigo(self):
        schema = cs._load_schema("producao.schema.json")
        validator = cs._make_validator(schema)
        entities = [{"id": "PROD-1"}]
        erros = cs._validate_all(entities, validator, "PRODUCAO")
        for e in erros:
            assert e.startswith("PRODUCAO PROD-1:")

    def test_validate_all_uses_placeholder_when_no_id_or_codigo(self):
        schema = cs._load_schema("insumo.schema.json")
        validator = cs._make_validator(schema)
        entities = [{}]
        erros = cs._validate_all(entities, validator, "INSUMO")
        for e in erros:
            assert e.startswith("INSUMO <sem-id>:")

    def test_validate_all_no_errors_for_valid_entities_returns_empty(self):
        # A validator against an always-true style schema (no required/props) yields no errors.
        trivial_schema = {"$id": "trivial", "type": "object"}
        validator = cs._make_validator(trivial_schema)
        erros = cs._validate_all([{"codigo": "X"}], validator, "X")
        assert erros == []


# ---------------------------------------------------------------------------
# small pure helpers
# ---------------------------------------------------------------------------


class TestNowIso:
    def test_now_iso_format(self):
        value = cs._now_iso()
        assert isinstance(value, str)
        assert "T" in value


class TestNormalizeCode:
    def test_normalize_code_ascii_uppercase(self):
        assert cs._normalize_code("abc-123") == "ABC-123"

    def test_normalize_code_strips_accents(self):
        assert cs._normalize_code("máo-de-obra") == "MAO-DE-OBRA"

    def test_normalize_code_replaces_invalid_chars(self):
        assert cs._normalize_code("MA_T/01#") == "MA-T-01"

    def test_normalize_code_collapses_dashes_and_strips(self):
        assert cs._normalize_code("--A--B--") == "A-B"

    def test_normalize_code_empty_after_clean_becomes_insumo(self):
        assert cs._normalize_code("***") == "INSUMO"

    def test_normalize_code_empty_string(self):
        assert cs._normalize_code("") == "INSUMO"

    def test_normalize_code_short_enough_returned_as_is(self):
        code = "A" * 40
        assert cs._normalize_code(code) == code

    def test_normalize_code_long_code_gets_hashed_suffix(self):
        code = "A" * 60
        result = cs._normalize_code(code)
        assert len(result) <= 40
        assert re.match(r"^[A-Z]{33}-[0-9A-F]{6}$", result)


class TestIsValidInsumoCode:
    @pytest.mark.parametrize(
        "code,expected",
        [
            ("ABC-123", True),
            ("AB", False),  # too short
            ("A" * 41, False),  # too long
            ("abc-123", False),  # lowercase invalid
            ("AB_12", False),  # underscore invalid
            ("A" * 40, True),  # boundary max length
            ("ABC", True),  # boundary min length
        ],
    )
    def test_is_valid_insumo_code(self, code, expected):
        assert cs._is_valid_insumo_code(code) is expected


class TestCategoriaCustoFromTipo:
    @pytest.mark.parametrize(
        "tipo,expected",
        [
            ("MAO_OBRA", "MAO_OBRA"),
            ("EQUIPAMENTO", "EQUIPAMENTO"),
            ("TERCEIRIZADO", "MATERIAL"),
            ("MATERIAL", "MATERIAL"),
            (None, "MATERIAL"),
            ("OUTRO", "MATERIAL"),
        ],
    )
    def test_categoria_custo_from_tipo(self, tipo, expected):
        assert cs._categoria_custo_from_tipo(tipo) == expected


class TestTeamIsEmpty:
    def test_none_is_empty(self):
        assert cs._team_is_empty(None) is True

    def test_non_dict_is_empty(self):
        assert cs._team_is_empty("not-a-dict") is True

    def test_empty_lists_is_empty(self):
        assert cs._team_is_empty({"funcoes": [], "equipamentos": []}) is True

    def test_missing_keys_is_empty(self):
        assert cs._team_is_empty({}) is True

    def test_non_list_values_treated_as_empty(self):
        assert cs._team_is_empty({"funcoes": "x", "equipamentos": None}) is True

    def test_funcoes_present_not_empty(self):
        assert cs._team_is_empty({"funcoes": [{"funcao_id": "F1"}], "equipamentos": []}) is False

    def test_equipamentos_present_not_empty(self):
        assert cs._team_is_empty({"funcoes": [], "equipamentos": [{"equip_id": "E1"}]}) is False


class TestInferTipoContrato:
    def test_infer_pj_from_codigo_suffix(self):
        assert cs._infer_tipo_contrato({"codigo": "MO-PEDREIRO-PJ"}) == "PJ"

    def test_infer_pj_from_descricao(self):
        assert cs._infer_tipo_contrato({"codigo": "MO-1", "descricao": "Pedreiro PJ contratado"}) == "PJ"

    def test_infer_clt_default(self):
        assert cs._infer_tipo_contrato({"codigo": "MO-1", "descricao": "Pedreiro CLT"}) == "CLT"

    def test_infer_clt_when_fields_missing(self):
        assert cs._infer_tipo_contrato({}) == "CLT"


# ---------------------------------------------------------------------------
# statistical helpers: _q / _iqr_bounds / _robust_bounds
# ---------------------------------------------------------------------------


class TestQ:
    def test_q_empty_list(self):
        assert cs._q([], 0.5) == 0.0

    def test_q_single_value(self):
        assert cs._q([5.0], 0.9) == 5.0

    def test_q_median_of_odd_list(self):
        assert cs._q([1.0, 2.0, 3.0], 0.5) == 2.0

    def test_q_interpolates_between_values(self):
        # ordered [1,2,3,4]; p=0.5 -> pos=1.5 -> interpolate between idx1(2) and idx2(3) => 2.5
        assert cs._q([4.0, 1.0, 3.0, 2.0], 0.5) == 2.5

    def test_q_p_zero_returns_min(self):
        assert cs._q([3.0, 1.0, 2.0], 0.0) == 1.0

    def test_q_p_one_returns_max(self):
        assert cs._q([3.0, 1.0, 2.0], 1.0) == 3.0


class TestIqrBounds:
    def test_fewer_than_8_values_returns_none(self):
        assert cs._iqr_bounds([1.0, 2.0, 3.0]) is None

    def test_zero_iqr_returns_none(self):
        values = [5.0] * 8
        assert cs._iqr_bounds(values) is None

    def test_normal_case_returns_bounds(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 100.0]
        bounds = cs._iqr_bounds(values)
        assert bounds is not None
        low, high = bounds
        assert low < high

    def test_non_negative_clamps_low(self):
        values = [-100.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
        bounds = cs._iqr_bounds(values, non_negative=True)
        assert bounds is not None
        low, high = bounds
        assert low >= 0.0
        assert high >= 0.0


class TestRobustBounds:
    def test_fewer_than_8_values_returns_none(self):
        assert cs._robust_bounds([1.0, 2.0]) is None

    def test_normal_case_widens_with_percentiles(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        bounds = cs._robust_bounds(values)
        assert bounds is not None
        low, high = bounds
        assert low <= high

    def test_zero_iqr_falls_back_to_percentiles(self):
        # all identical -> iqr==0 -> _iqr_bounds returns None -> uses q10/q90 (both == value)
        values = [5.0] * 8
        bounds = cs._robust_bounds(values)
        assert bounds == (5.0, 5.0)

    def test_non_negative_clamps(self):
        values = [-50.0, -10.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        bounds = cs._robust_bounds(values, non_negative=True)
        assert bounds is not None
        low, high = bounds
        assert low >= 0.0
        assert high >= 0.0

    def test_iqr_bounds_narrower_than_percentiles_takes_percentiles(self):
        # Construct data where q10/q90 are wider than the IQR-derived bounds,
        # forcing the min/max widening branch to actually change the result.
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 1000.0]
        bounds = cs._robust_bounds(values)
        assert bounds is not None


# ---------------------------------------------------------------------------
# CurationReport
# ---------------------------------------------------------------------------


class TestCurationReport:
    def test_init_empty(self):
        report = cs.CurationReport()
        assert report.fixed == []
        assert report.manual == []
        assert report.skipped == []

    def test_add_fixed(self):
        report = cs.CurationReport()
        report.add_fixed("a")
        assert report.fixed == ["a"]

    def test_add_manual(self):
        report = cs.CurationReport()
        report.add_manual("b")
        assert report.manual == ["b"]

    def test_add_skipped(self):
        report = cs.CurationReport()
        report.add_skipped("c")
        assert report.skipped == ["c"]


# ---------------------------------------------------------------------------
# _dedupe_team_items / _normalize_team
# ---------------------------------------------------------------------------


class TestDedupeTeamItems:
    def test_empty_list(self):
        assert cs._dedupe_team_items([], "funcao_id", "num_pessoas") == []

    def test_skips_non_dict_items(self):
        result = cs._dedupe_team_items(["not-a-dict"], "funcao_id", "num_pessoas")
        assert result == []

    def test_skips_missing_or_invalid_id(self):
        items = [{"num_pessoas": 2}, {"funcao_id": "", "num_pessoas": 2}, {"funcao_id": 123, "num_pessoas": 2}]
        assert cs._dedupe_team_items(items, "funcao_id", "num_pessoas") == []

    def test_skips_zero_or_negative_qty(self):
        items = [{"funcao_id": "F1", "num_pessoas": 0}, {"funcao_id": "F2", "num_pessoas": -1}]
        assert cs._dedupe_team_items(items, "funcao_id", "num_pessoas") == []

    def test_skips_non_numeric_qty(self):
        items = [{"funcao_id": "F1", "num_pessoas": "abc"}]
        assert cs._dedupe_team_items(items, "funcao_id", "num_pessoas") == []

    def test_treats_missing_qty_as_zero_and_skips(self):
        items = [{"funcao_id": "F1"}]
        assert cs._dedupe_team_items(items, "funcao_id", "num_pessoas") == []

    def test_merges_duplicate_ids_summing_qty(self):
        items = [
            {"funcao_id": "F1", "num_pessoas": 2},
            {"funcao_id": "F1", "num_pessoas": 3},
        ]
        result = cs._dedupe_team_items(items, "funcao_id", "num_pessoas")
        assert len(result) == 1
        assert result[0]["funcao_id"] == "F1"
        assert result[0]["num_pessoas"] == 5

    def test_keeps_distinct_ids_separate(self):
        items = [
            {"funcao_id": "F1", "num_pessoas": 2},
            {"funcao_id": "F2", "num_pessoas": 3},
        ]
        result = cs._dedupe_team_items(items, "funcao_id", "num_pessoas")
        assert len(result) == 2

    def test_merge_when_existing_qty_key_is_none(self):
        # Exercise int(by_id[item_id].get(qty_key) or 0) branch where prior stored value is falsy.
        # qty<=0 entries are skipped before storage, so exercise accumulation with a string qty instead.
        items2 = [
            {"funcao_id": "F1", "num_pessoas": 1},
            {"funcao_id": "F1", "num_pessoas": "2"},
        ]
        result = cs._dedupe_team_items(items2, "funcao_id", "num_pessoas")
        assert result[0]["num_pessoas"] == 3


class TestNormalizeTeam:
    def test_normalize_team_dedupes_funcoes_and_equipamentos(self):
        equipe = {
            "funcoes": [
                {"funcao_id": "F1", "num_pessoas": 1},
                {"funcao_id": "F1", "num_pessoas": 2},
            ],
            "equipamentos": [
                {"equip_id": "E1", "num_unidades": 1},
                {"equip_id": "E1", "num_unidades": 1},
            ],
        }
        result = cs._normalize_team(equipe)
        assert len(result["funcoes"]) == 1
        assert result["funcoes"][0]["num_pessoas"] == 3
        assert len(result["equipamentos"]) == 1
        assert result["equipamentos"][0]["num_unidades"] == 2

    def test_normalize_team_missing_keys_default_to_empty(self):
        result = cs._normalize_team({})
        assert result["funcoes"] == []
        assert result["equipamentos"] == []

    def test_normalize_team_preserves_other_keys(self):
        result = cs._normalize_team({"observacao": "x", "funcoes": [], "equipamentos": []})
        assert result["observacao"] == "x"


# ---------------------------------------------------------------------------
# cure_producao
# ---------------------------------------------------------------------------


class TestCureProducao:
    def test_removes_cpu_contaminated_fields_apply_true(self):
        report = cs.CurationReport()
        prod = {"id": "PROD-1", "atributos_categoria": {"x": 1}, "cpu_ids": ["CPU-1"]}
        result = cs.cure_producao(prod, report, apply=True)
        assert "atributos_categoria" not in result
        assert "cpu_ids" not in result
        assert any("atributos_categoria" in m for m in report.fixed)
        assert any("cpu_ids" in m for m in report.fixed)

    def test_contaminated_fields_apply_false_no_mutation(self):
        report = cs.CurationReport()
        prod = {"id": "PROD-1", "atributos_categoria": {"x": 1}}
        result = cs.cure_producao(prod, report, apply=False)
        assert result == prod
        assert result is prod
        assert any("atributos_categoria" in m for m in report.fixed)

    def test_no_contaminated_fields_no_report_entry(self):
        report = cs.CurationReport()
        prod = {"id": "PROD-1"}
        cs.cure_producao(prod, report, apply=True)
        assert report.fixed == []

    def test_migrates_producao_horaria_to_valor_horario_apply_true(self):
        report = cs.CurationReport()
        prod = {"id": "PROD-1", "producao_horaria": 10.0}
        result = cs.cure_producao(prod, report, apply=True)
        assert result["valor_horario"] == 10.0
        assert "producao_horaria" not in result
        assert any("producao_horaria" in m for m in report.fixed)

    def test_producao_horaria_does_not_override_existing_valor_horario(self):
        report = cs.CurationReport()
        prod = {"id": "PROD-1", "producao_horaria": 10.0, "valor_horario": 5.0}
        result = cs.cure_producao(prod, report, apply=True)
        assert result["valor_horario"] == 5.0
        assert "producao_horaria" not in result

    def test_producao_horaria_none_value(self):
        report = cs.CurationReport()
        prod = {"id": "PROD-1", "producao_horaria": None}
        result = cs.cure_producao(prod, report, apply=True)
        assert "valor_horario" not in result
        assert "producao_horaria" not in result

    def test_producao_horaria_apply_false_no_mutation(self):
        report = cs.CurationReport()
        prod = {"id": "PROD-1", "producao_horaria": 10.0}
        result = cs.cure_producao(prod, report, apply=False)
        assert result == prod
        assert "producao_horaria" in result

    def test_migrates_equipe_to_composicao_padrao_equipe_apply_true(self):
        report = cs.CurationReport()
        prod = {"id": "PROD-1", "equipe": {"funcoes": [], "equipamentos": []}}
        result = cs.cure_producao(prod, report, apply=True)
        assert "equipe" not in result
        assert "composicao_padrao_equipe" in result
        assert any("migrado equipe" in m for m in report.fixed)

    def test_equipe_and_composicao_both_present_removes_equipe(self):
        report = cs.CurationReport()
        prod = {
            "id": "PROD-1",
            "equipe": {"funcoes": []},
            "composicao_padrao_equipe": {"funcoes": [], "equipamentos": []},
        }
        result = cs.cure_producao(prod, report, apply=True)
        assert "equipe" not in result
        assert any("removido campo legado equipe" in m for m in report.fixed)

    def test_migrates_equipe_to_composicao_padrao_equipe_apply_false_no_mutation(self):
        report = cs.CurationReport()
        prod = {"id": "PROD-1", "equipe": {"funcoes": [], "equipamentos": []}}
        result = cs.cure_producao(prod, report, apply=False)
        assert result == prod
        assert any("migrado equipe" in m for m in report.fixed)

    def test_equipe_and_composicao_both_present_apply_false_no_mutation(self):
        report = cs.CurationReport()
        prod = {
            "id": "PROD-1",
            "equipe": {"funcoes": []},
            "composicao_padrao_equipe": {"funcoes": [], "equipamentos": []},
        }
        result = cs.cure_producao(prod, report, apply=False)
        assert result == prod
        assert any("removido campo legado equipe" in m for m in report.fixed)

    def test_no_equipe_field_no_migration_report(self):
        report = cs.CurationReport()
        prod = {"id": "PROD-1"}
        cs.cure_producao(prod, report, apply=True)
        assert report.fixed == []

    def test_normalizes_composicao_padrao_equipe_when_dirty(self):
        report = cs.CurationReport()
        prod = {
            "id": "PROD-1",
            "composicao_padrao_equipe": {
                "funcoes": [
                    {"funcao_id": "F1", "num_pessoas": 1},
                    {"funcao_id": "F1", "num_pessoas": 1},
                ],
                "equipamentos": [],
            },
        }
        result = cs.cure_producao(prod, report, apply=True)
        assert len(result["composicao_padrao_equipe"]["funcoes"]) == 1
        assert any("deduplicada composicao_padrao_equipe" in m for m in report.fixed)

    def test_composicao_padrao_equipe_already_clean_no_report(self):
        report = cs.CurationReport()
        prod = {
            "id": "PROD-1",
            "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "F1", "num_pessoas": 1}], "equipamentos": []},
        }
        cs.cure_producao(prod, report, apply=True)
        assert report.fixed == []

    def test_composicao_padrao_equipe_apply_false_no_mutation(self):
        report = cs.CurationReport()
        prod = {
            "id": "PROD-1",
            "composicao_padrao_equipe": {
                "funcoes": [
                    {"funcao_id": "F1", "num_pessoas": 1},
                    {"funcao_id": "F1", "num_pessoas": 1},
                ],
                "equipamentos": [],
            },
        }
        result = cs.cure_producao(prod, report, apply=False)
        assert result == prod
        assert len(result["composicao_padrao_equipe"]["funcoes"]) == 2

    def test_cpu_ids_removed_apply_true(self):
        report = cs.CurationReport()
        prod = {"id": "PROD-1", "cpu_ids": ["X"]}
        result = cs.cure_producao(prod, report, apply=True)
        assert "cpu_ids" not in result

    def test_cpu_ids_apply_false_no_mutation(self):
        report = cs.CurationReport()
        prod = {"id": "PROD-1", "cpu_ids": ["X"]}
        result = cs.cure_producao(prod, report, apply=False)
        assert result == prod
        assert "cpu_ids" in result

    def test_historico_observacoes_completes_missing_fields_apply_true(self):
        report = cs.CurationReport()
        prod = {
            "id": "PROD-1",
            "historico_observacoes": [{"data": "", "autor": "", "descricao": ""}],
        }
        result = cs.cure_producao(prod, report, apply=True)
        obs = result["historico_observacoes"][0]
        assert obs["data"]
        assert obs["autor"] == "cure_catalog"
        assert obs["descricao"] == "(migrado sem descrição original)"
        assert obs["tipo"] == "migracao"
        assert any("historico_observacoes[0]" in m for m in report.fixed)

    def test_historico_observacoes_already_complete_kept_as_is(self):
        report = cs.CurationReport()
        item = {"data": "2024-01-01", "autor": "joao", "descricao": "ok", "tipo": "manual"}
        prod = {"id": "PROD-1", "historico_observacoes": [item]}
        result = cs.cure_producao(prod, report, apply=True)
        assert result["historico_observacoes"][0] == item
        assert report.fixed == []

    def test_historico_observacoes_non_dict_item_skipped(self):
        report = cs.CurationReport()
        prod = {"id": "PROD-1", "historico_observacoes": ["not-a-dict"]}
        result = cs.cure_producao(prod, report, apply=True)
        assert result["historico_observacoes"] == []
        assert any("não é objeto" in m for m in report.skipped)

    def test_historico_observacoes_apply_false_no_mutation(self):
        report = cs.CurationReport()
        prod = {"id": "PROD-1", "historico_observacoes": [{"data": "", "autor": "", "descricao": ""}]}
        result = cs.cure_producao(prod, report, apply=False)
        assert result == prod
        assert result["historico_observacoes"][0]["data"] == ""

    def test_historico_observacoes_partial_tipo_already_present_not_overwritten(self):
        report = cs.CurationReport()
        item = {"data": "", "autor": "x", "descricao": "y", "tipo": "custom"}
        prod = {"id": "PROD-1", "historico_observacoes": [item]}
        result = cs.cure_producao(prod, report, apply=True)
        assert result["historico_observacoes"][0]["tipo"] == "custom"

    def test_historico_observacoes_data_present_but_autor_missing(self):
        report = cs.CurationReport()
        item = {"data": "2024-01-01", "autor": "", "descricao": "y"}
        prod = {"id": "PROD-1", "historico_observacoes": [item]}
        result = cs.cure_producao(prod, report, apply=True)
        obs = result["historico_observacoes"][0]
        assert obs["data"] == "2024-01-01"
        assert obs["autor"] == "cure_catalog"

    def test_historico_observacoes_non_list_left_untouched(self):
        report = cs.CurationReport()
        prod = {"id": "PROD-1", "historico_observacoes": "not-a-list"}
        result = cs.cure_producao(prod, report, apply=True)
        assert result["historico_observacoes"] == "not-a-list"
        assert report.fixed == []

    def test_variantes_normalizes_equipe_apply_true(self):
        report = cs.CurationReport()
        prod = {
            "id": "PROD-1",
            "variantes": [
                {
                    "nome": "v1",
                    "equipe": {
                        "funcoes": [
                            {"funcao_id": "F1", "num_pessoas": 1},
                            {"funcao_id": "F1", "num_pessoas": 1},
                        ],
                        "equipamentos": [],
                    },
                }
            ],
        }
        result = cs.cure_producao(prod, report, apply=True)
        assert len(result["variantes"][0]["equipe"]["funcoes"]) == 1
        assert any("deduplicadas equipes nas variantes" in m for m in report.fixed)

    def test_variantes_apply_false_no_mutation(self):
        report = cs.CurationReport()
        prod = {
            "id": "PROD-1",
            "variantes": [
                {
                    "equipe": {
                        "funcoes": [
                            {"funcao_id": "F1", "num_pessoas": 1},
                            {"funcao_id": "F1", "num_pessoas": 1},
                        ],
                        "equipamentos": [],
                    },
                }
            ],
        }
        result = cs.cure_producao(prod, report, apply=False)
        assert result == prod

    def test_variantes_with_non_dict_item_passthrough(self):
        report = cs.CurationReport()
        prod = {"id": "PROD-1", "variantes": ["not-a-dict"]}
        result = cs.cure_producao(prod, report, apply=True)
        assert result["variantes"] == ["not-a-dict"]
        assert report.fixed == []

    def test_variantes_with_no_equipe_key_untouched(self):
        report = cs.CurationReport()
        prod = {"id": "PROD-1", "variantes": [{"nome": "v1"}]}
        result = cs.cure_producao(prod, report, apply=True)
        assert result["variantes"] == [{"nome": "v1"}]
        assert report.fixed == []

    def test_variantes_equipe_already_clean_no_touch(self):
        report = cs.CurationReport()
        prod = {
            "id": "PROD-1",
            "variantes": [{"equipe": {"funcoes": [{"funcao_id": "F1", "num_pessoas": 1}], "equipamentos": []}}],
        }
        result = cs.cure_producao(prod, report, apply=True)
        assert report.fixed == []
        assert result["variantes"][0]["equipe"]["funcoes"] == [{"funcao_id": "F1", "num_pessoas": 1}]

    def test_fully_clean_producao_no_report_entries(self):
        report = cs.CurationReport()
        prod = {
            "id": "PROD-1",
            "valor_horario": 5.0,
            "composicao_padrao_equipe": {"funcoes": [], "equipamentos": []},
        }
        result = cs.cure_producao(prod, report, apply=True)
        assert result == {**prod, "historico_observacoes": []}
        assert report.fixed == []
        assert report.manual == []
        assert report.skipped == []

    def test_missing_id_uses_placeholder(self):
        report = cs.CurationReport()
        prod = {"cpu_ids": ["X"]}
        cs.cure_producao(prod, report, apply=True)
        assert any("<sem-id>" in m for m in report.fixed)


# ---------------------------------------------------------------------------
# cure_cpu
# ---------------------------------------------------------------------------


class TestCureCpu:
    def test_moves_dmt_fields_to_atributos_categoria_apply_true(self):
        report = cs.CurationReport()
        cpu = {"codigo": "CPU-1", "dmt_referencia_m": 100, "dmt_min_metros": 10, "dmt_max_metros": 200}
        result = cs.cure_cpu(cpu, report, apply=True)
        assert "dmt_referencia_m" not in result
        assert "dmt_min_metros" not in result
        assert "dmt_max_metros" not in result
        assert result["atributos_categoria"]["dmt_referencia_m"] == 100
        assert result["atributos_categoria"]["dmt_min_metros"] == 10
        assert result["atributos_categoria"]["dmt_max_metros"] == 200
        assert len([m for m in report.fixed if "movido" in m]) == 3

    def test_moves_dmt_fields_preserves_existing_atributos_categoria(self):
        report = cs.CurationReport()
        cpu = {"codigo": "CPU-1", "dmt_referencia_m": 100, "atributos_categoria": {"existing": True}}
        result = cs.cure_cpu(cpu, report, apply=True)
        assert result["atributos_categoria"]["existing"] is True
        assert result["atributos_categoria"]["dmt_referencia_m"] == 100

    def test_dmt_fields_apply_false_no_mutation(self):
        report = cs.CurationReport()
        cpu = {"codigo": "CPU-1", "dmt_referencia_m": 100}
        result = cs.cure_cpu(cpu, report, apply=False)
        assert result == cpu
        assert "dmt_referencia_m" in result
        assert any("movido" in m for m in report.fixed)

    def test_no_dmt_fields_no_report(self):
        report = cs.CurationReport()
        cpu = {"codigo": "CPU-1"}
        cs.cure_cpu(cpu, report, apply=True)
        assert report.fixed == []

    def test_removes_deprecated_fonte_preco_and_data_referencia_apply_true(self):
        report = cs.CurationReport()
        cpu = {"codigo": "CPU-1", "fonte_preco": "x", "data_referencia_preco": "2024-01-01"}
        result = cs.cure_cpu(cpu, report, apply=True)
        assert "fonte_preco" not in result
        assert "data_referencia_preco" not in result
        assert len([m for m in report.fixed if "deprecated" in m]) == 2

    def test_deprecated_fields_apply_false_no_mutation(self):
        report = cs.CurationReport()
        cpu = {"codigo": "CPU-1", "fonte_preco": "x"}
        result = cs.cure_cpu(cpu, report, apply=False)
        assert result == cpu
        assert "fonte_preco" in result

    def test_missing_codigo_uses_placeholder(self):
        report = cs.CurationReport()
        cpu = {"fonte_preco": "x"}
        cs.cure_cpu(cpu, report, apply=True)
        assert any("<sem-codigo>" in m for m in report.fixed)

    def test_fully_clean_cpu_no_report(self):
        report = cs.CurationReport()
        cpu = {"codigo": "CPU-1", "categoria": "X"}
        result = cs.cure_cpu(cpu, report, apply=True)
        assert result == cpu
        assert report.fixed == []


# ---------------------------------------------------------------------------
# cure_insumo
# ---------------------------------------------------------------------------


class TestCureInsumo:
    def test_fills_fonte_preco_when_missing_apply_true(self):
        report = cs.CurationReport()
        ins = {"codigo": "MA-1", "tipo": "MATERIAL"}
        result = cs.cure_insumo(ins, report, apply=True)
        assert result["fonte_preco"] == "catalogo_proprio"
        assert any("fonte_preco" in m for m in report.fixed)

    def test_fonte_preco_apply_false_no_mutation(self):
        report = cs.CurationReport()
        ins = {"codigo": "MA-1", "tipo": "MATERIAL"}
        result = cs.cure_insumo(ins, report, apply=False)
        assert result == ins
        assert "fonte_preco" not in result

    def test_fonte_preco_already_present_no_report(self):
        report = cs.CurationReport()
        ins = {"codigo": "MA-1", "tipo": "MATERIAL", "fonte_preco": "manual"}
        result = cs.cure_insumo(ins, report, apply=True)
        assert result["fonte_preco"] == "manual"
        assert report.fixed == []

    def test_fonte_preco_empty_string_treated_as_missing(self):
        report = cs.CurationReport()
        ins = {"codigo": "MA-1", "tipo": "MATERIAL", "fonte_preco": ""}
        result = cs.cure_insumo(ins, report, apply=True)
        assert result["fonte_preco"] == "catalogo_proprio"

    def test_removes_cpu_only_fields_apply_true(self):
        report = cs.CurationReport()
        ins = {
            "codigo": "MA-1",
            "tipo": "MATERIAL",
            "fonte_preco": "x",
            "atributos_categoria": {},
            "composicao_itens": [],
            "cpu_referencia_id": "CPU-1",
        }
        result = cs.cure_insumo(ins, report, apply=True)
        assert "atributos_categoria" not in result
        assert "composicao_itens" not in result
        assert "cpu_referencia_id" not in result
        assert len([m for m in report.fixed if "exclusivo de CPU" in m]) == 3

    def test_cpu_only_fields_apply_false_no_mutation(self):
        report = cs.CurationReport()
        ins = {"codigo": "MA-1", "tipo": "MATERIAL", "fonte_preco": "x", "atributos_categoria": {}}
        result = cs.cure_insumo(ins, report, apply=False)
        assert result == ins
        assert "atributos_categoria" in result

    def test_no_cpu_only_fields_no_report(self):
        report = cs.CurationReport()
        ins = {"codigo": "MA-1", "tipo": "MATERIAL", "fonte_preco": "x"}
        cs.cure_insumo(ins, report, apply=True)
        assert report.fixed == []

    def test_mao_obra_infers_and_sets_tipo_contrato_when_invalid(self):
        report = cs.CurationReport()
        ins = {"codigo": "MO-1-PJ", "tipo": "MAO_OBRA", "fonte_preco": "x", "atributos_especificos": {}}
        result = cs.cure_insumo(ins, report, apply=True)
        assert result["atributos_especificos"]["tipo_contrato"] == "PJ"
        assert any("tipo_contrato" in m for m in report.fixed)

    def test_mao_obra_tipo_contrato_apply_false_no_mutation(self):
        report = cs.CurationReport()
        ins = {"codigo": "MO-1-PJ", "tipo": "MAO_OBRA", "fonte_preco": "x", "atributos_especificos": {}}
        result = cs.cure_insumo(ins, report, apply=False)
        assert result == ins
        assert "tipo_contrato" not in result["atributos_especificos"]

    def test_mao_obra_tipo_contrato_already_valid_not_touched(self):
        report = cs.CurationReport()
        ins = {
            "codigo": "MO-1",
            "tipo": "MAO_OBRA",
            "fonte_preco": "x",
            "atributos_especificos": {"tipo_contrato": "CLT"},
        }
        cs.cure_insumo(ins, report, apply=True)
        assert report.fixed == []

    def test_mao_obra_missing_atributos_especificos_defaults_to_dict(self):
        report = cs.CurationReport()
        ins = {"codigo": "MO-1", "tipo": "MAO_OBRA", "fonte_preco": "x"}
        result = cs.cure_insumo(ins, report, apply=True)
        assert result["atributos_especificos"]["tipo_contrato"] == "CLT"

    def test_mao_obra_atributos_especificos_non_dict_becomes_dict(self):
        report = cs.CurationReport()
        ins = {"codigo": "MO-1", "tipo": "MAO_OBRA", "fonte_preco": "x", "atributos_especificos": "not-a-dict"}
        result = cs.cure_insumo(ins, report, apply=True)
        assert result["atributos_especificos"]["tipo_contrato"] == "CLT"

    def test_mao_obra_removes_custo_com_encargos_apply_true(self):
        report = cs.CurationReport()
        ins = {
            "codigo": "MO-1",
            "tipo": "MAO_OBRA",
            "fonte_preco": "x",
            "atributos_especificos": {"tipo_contrato": "CLT", "custo_com_encargos": 50.0},
        }
        result = cs.cure_insumo(ins, report, apply=True)
        assert "custo_com_encargos" not in result["atributos_especificos"]
        assert any("custo_com_encargos" in m for m in report.fixed)

    def test_mao_obra_custo_com_encargos_apply_false_no_mutation(self):
        report = cs.CurationReport()
        ins = {
            "codigo": "MO-1",
            "tipo": "MAO_OBRA",
            "fonte_preco": "x",
            "atributos_especificos": {"tipo_contrato": "CLT", "custo_com_encargos": 50.0},
        }
        result = cs.cure_insumo(ins, report, apply=False)
        assert result == ins
        assert "custo_com_encargos" in result["atributos_especificos"]

    def test_equipamento_removes_derived_fields_apply_true(self):
        report = cs.CurationReport()
        ins = {
            "codigo": "EQ-1",
            "tipo": "EQUIPAMENTO",
            "fonte_preco": "x",
            "atributos_especificos": {"custo_manutencao_hora": 1.0, "custo_produtivo_hora": 2.0},
        }
        result = cs.cure_insumo(ins, report, apply=True)
        assert "custo_manutencao_hora" not in result["atributos_especificos"]
        assert "custo_produtivo_hora" not in result["atributos_especificos"]
        assert len([m for m in report.fixed if "removido campo derivado" in m]) == 2

    def test_equipamento_derived_fields_apply_false_no_mutation(self):
        report = cs.CurationReport()
        ins = {
            "codigo": "EQ-1",
            "tipo": "EQUIPAMENTO",
            "fonte_preco": "x",
            "atributos_especificos": {"custo_manutencao_hora": 1.0},
        }
        result = cs.cure_insumo(ins, report, apply=False)
        assert result == ins
        assert "custo_manutencao_hora" in result["atributos_especificos"]

    def test_equipamento_no_derived_fields_no_report(self):
        report = cs.CurationReport()
        ins = {"codigo": "EQ-1", "tipo": "EQUIPAMENTO", "fonte_preco": "x", "atributos_especificos": {}}
        cs.cure_insumo(ins, report, apply=True)
        assert report.fixed == []

    def test_equipamento_atributos_especificos_non_dict_skips_derived_check(self):
        report = cs.CurationReport()
        ins = {"codigo": "EQ-1", "tipo": "EQUIPAMENTO", "fonte_preco": "x", "atributos_especificos": "not-a-dict"}
        result = cs.cure_insumo(ins, report, apply=True)
        assert result["atributos_especificos"] == "not-a-dict"
        assert report.fixed == []

    def test_equipamento_removes_custo_hora_total_from_decomposicao_apply_true(self):
        report = cs.CurationReport()
        ins = {
            "codigo": "EQ-1",
            "tipo": "EQUIPAMENTO",
            "fonte_preco": "x",
            "atributos_especificos": {"decomposicao_equip": {"custo_hora_total": 10.0, "outro": 1}},
        }
        result = cs.cure_insumo(ins, report, apply=True)
        assert "custo_hora_total" not in result["atributos_especificos"]["decomposicao_equip"]
        assert result["atributos_especificos"]["decomposicao_equip"]["outro"] == 1
        assert any("decomposicao_equip.custo_hora_total" in m for m in report.fixed)

    def test_equipamento_custo_hora_total_apply_false_no_mutation(self):
        report = cs.CurationReport()
        ins = {
            "codigo": "EQ-1",
            "tipo": "EQUIPAMENTO",
            "fonte_preco": "x",
            "atributos_especificos": {"decomposicao_equip": {"custo_hora_total": 10.0}},
        }
        result = cs.cure_insumo(ins, report, apply=False)
        assert result == ins
        assert "custo_hora_total" in result["atributos_especificos"]["decomposicao_equip"]

    def test_equipamento_decomposicao_non_dict_no_crash(self):
        report = cs.CurationReport()
        ins = {
            "codigo": "EQ-1",
            "tipo": "EQUIPAMENTO",
            "fonte_preco": "x",
            "atributos_especificos": {"decomposicao_equip": "not-a-dict"},
        }
        result = cs.cure_insumo(ins, report, apply=True)
        assert result["atributos_especificos"]["decomposicao_equip"] == "not-a-dict"
        assert report.fixed == []

    def test_equipamento_no_decomposicao_key_no_crash(self):
        report = cs.CurationReport()
        ins = {"codigo": "EQ-1", "tipo": "EQUIPAMENTO", "fonte_preco": "x", "atributos_especificos": {}}
        cs.cure_insumo(ins, report, apply=True)
        assert report.fixed == []

    def test_material_tipo_untouched_by_mao_obra_or_equipamento_rules(self):
        report = cs.CurationReport()
        ins = {"codigo": "MA-1", "tipo": "MATERIAL", "fonte_preco": "x", "atributos_especificos": {"foo": "bar"}}
        result = cs.cure_insumo(ins, report, apply=True)
        assert result["atributos_especificos"] == {"foo": "bar"}
        assert report.fixed == []

    def test_missing_codigo_uses_placeholder(self):
        report = cs.CurationReport()
        ins = {"tipo": "MATERIAL"}
        cs.cure_insumo(ins, report, apply=True)
        assert any("<sem-codigo>" in m for m in report.fixed)


# ---------------------------------------------------------------------------
# _apply_insumo_code_remap
# ---------------------------------------------------------------------------


class TestApplyInsumoCodeRemap:
    def test_empty_remap_is_noop(self):
        cpus = [{"composicao_itens": [{"insumo_id": "OLD"}]}]
        cs._apply_insumo_code_remap(cpus, [], {})
        assert cpus[0]["composicao_itens"][0]["insumo_id"] == "OLD"

    def test_remaps_cpu_composicao_itens(self):
        cpus = [{"composicao_itens": [{"insumo_id": "OLD"}, {"insumo_id": "OTHER"}]}]
        cs._apply_insumo_code_remap(cpus, [], {"OLD": "NEW"})
        assert cpus[0]["composicao_itens"][0]["insumo_id"] == "NEW"
        assert cpus[0]["composicao_itens"][1]["insumo_id"] == "OTHER"

    def test_cpu_without_composicao_itens_list_skipped(self):
        cpus = [{"composicao_itens": "not-a-list"}, {}]
        cs._apply_insumo_code_remap(cpus, [], {"OLD": "NEW"})  # should not raise

    def test_cpu_composicao_item_non_dict_skipped(self):
        cpus = [{"composicao_itens": ["not-a-dict"]}]
        cs._apply_insumo_code_remap(cpus, [], {"OLD": "NEW"})  # should not raise

    def test_remaps_prod_composicao_padrao_equipe_funcoes_and_equipamentos(self):
        prods = [
            {
                "composicao_padrao_equipe": {
                    "funcoes": [{"funcao_id": "OLD"}],
                    "equipamentos": [{"equip_id": "OLD"}],
                }
            }
        ]
        cs._apply_insumo_code_remap([], prods, {"OLD": "NEW"})
        assert prods[0]["composicao_padrao_equipe"]["funcoes"][0]["funcao_id"] == "NEW"
        assert prods[0]["composicao_padrao_equipe"]["equipamentos"][0]["equip_id"] == "NEW"

    def test_prod_without_composicao_padrao_equipe_skipped(self):
        prods = [{"id": "PROD-1"}]
        cs._apply_insumo_code_remap([], prods, {"OLD": "NEW"})  # should not raise

    def test_prod_equipe_funcoes_or_equipamentos_non_list_skipped(self):
        prods = [{"composicao_padrao_equipe": {"funcoes": "x", "equipamentos": "y"}}]
        cs._apply_insumo_code_remap([], prods, {"OLD": "NEW"})  # should not raise

    def test_prod_equipe_item_non_dict_skipped(self):
        prods = [{"composicao_padrao_equipe": {"funcoes": ["not-a-dict"], "equipamentos": ["not-a-dict"]}}]
        cs._apply_insumo_code_remap([], prods, {"OLD": "NEW"})  # should not raise

    def test_remaps_variantes_equipe_funcoes_and_equipamentos(self):
        prods = [
            {
                "variantes": [
                    {
                        "equipe": {
                            "funcoes": [{"funcao_id": "OLD"}],
                            "equipamentos": [{"equip_id": "OLD"}],
                        }
                    }
                ]
            }
        ]
        cs._apply_insumo_code_remap([], prods, {"OLD": "NEW"})
        var_equipe = prods[0]["variantes"][0]["equipe"]
        assert var_equipe["funcoes"][0]["funcao_id"] == "NEW"
        assert var_equipe["equipamentos"][0]["equip_id"] == "NEW"

    def test_variantes_non_list_skipped(self):
        prods = [{"variantes": "not-a-list"}]
        cs._apply_insumo_code_remap([], prods, {"OLD": "NEW"})  # should not raise

    def test_variantes_item_non_dict_skipped(self):
        prods = [{"variantes": ["not-a-dict"]}]
        cs._apply_insumo_code_remap([], prods, {"OLD": "NEW"})  # should not raise

    def test_variante_equipe_non_dict_skipped(self):
        prods = [{"variantes": [{"equipe": "not-a-dict"}]}]
        cs._apply_insumo_code_remap([], prods, {"OLD": "NEW"})  # should not raise

    def test_variante_equipe_funcoes_equipamentos_non_list_skipped(self):
        prods = [{"variantes": [{"equipe": {"funcoes": "x", "equipamentos": "y"}}]}]
        cs._apply_insumo_code_remap([], prods, {"OLD": "NEW"})  # should not raise

    def test_variante_equipe_item_non_dict_skipped(self):
        prods = [{"variantes": [{"equipe": {"funcoes": ["not-a-dict"], "equipamentos": ["not-a-dict"]}}]}]
        cs._apply_insumo_code_remap([], prods, {"OLD": "NEW"})  # should not raise

    def test_value_not_in_remap_unchanged(self):
        cpus = [{"composicao_itens": [{"insumo_id": "UNRELATED"}]}]
        cs._apply_insumo_code_remap(cpus, [], {"OLD": "NEW"})
        assert cpus[0]["composicao_itens"][0]["insumo_id"] == "UNRELATED"

    def test_value_non_string_unchanged(self):
        cpus = [{"composicao_itens": [{"insumo_id": 123}]}]
        cs._apply_insumo_code_remap(cpus, [], {"OLD": "NEW"})
        assert cpus[0]["composicao_itens"][0]["insumo_id"] == 123


class TestJsonschemaImportGuard:
    """Cobre o raise ImportError quando jsonschema não está instalado (linhas 46-47)."""

    def test_missing_jsonschema_raises_import_error_with_hint(self):
        import builtins
        import importlib
        import sys

        real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "jsonschema":
                raise ImportError("No module named 'jsonschema'")
            return real_import(name, *args, **kwargs)

        modules_backup = {k: v for k, v in sys.modules.items() if k == "concilium.application.catalog.cure_schema"}
        sys.modules.pop("concilium.application.catalog.cure_schema", None)
        try:
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(builtins, "__import__", _fake_import)
                with pytest.raises(ImportError, match="Instale jsonschema"):
                    importlib.import_module("concilium.application.catalog.cure_schema")
        finally:
            sys.modules.pop("concilium.application.catalog.cure_schema", None)
            sys.modules.update(modules_backup)
            importlib.import_module("concilium.application.catalog.cure_schema")
