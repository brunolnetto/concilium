"""Cobertura da segunda metade de cure_schema.py: cure_contextual, I/O e CLI.

Escopo: cure_contextual (linhas ~497-742), _context_base, _load_entity_files,
_persist_entity_files, run() e main() (linhas ~742-885).

A primeira metade do módulo (helpers + cure_producao/cure_cpu/cure_insumo) é
coberta por outro arquivo de teste concorrente — não duplicar aqui.
"""

from __future__ import annotations

import json
import sys

import pytest

from concilium.application.catalog import cure_schema
from concilium.application.catalog.cure_schema import (
    CurationReport,
    _context_base,
    _load_entity_files,
    _persist_entity_files,
    cure_contextual,
    main,
    run,
)


def _report() -> CurationReport:
    return CurationReport()


# ── cure_contextual: bloco 0) equipe herdada de template CAP ─────────────────


class TestCureContextualTemplateEquipe:
    def _prods(self, target_team, source_team):
        return [
            {"id": "CPU-DREN-BOCA-BDCAP-100-PROD-001", "composicao_padrao_equipe": target_team},
            {"id": "CPU-DREN-BOCA-BDTC-100-PROD-001", "composicao_padrao_equipe": source_team},
        ]

    def test_inherits_when_target_empty_and_source_filled_apply(self):
        source_team = {"funcoes": [{"funcao_id": "MO-1", "num_pessoas": 2}], "equipamentos": []}
        prods = self._prods({"funcoes": [], "equipamentos": []}, source_team)
        report = _report()
        cure_contextual([], prods, [], report, apply=True)
        assert prods[0]["composicao_padrao_equipe"] == source_team
        # deep copy, not same object
        assert prods[0]["composicao_padrao_equipe"] is not source_team
        assert any("equipe herdada de template" in m for m in report.fixed)

    def test_inherits_dry_run_does_not_mutate(self):
        source_team = {"funcoes": [{"funcao_id": "MO-1", "num_pessoas": 2}], "equipamentos": []}
        target_team = {"funcoes": [], "equipamentos": []}
        prods = self._prods(target_team, source_team)
        report = _report()
        cure_contextual([], prods, [], report, apply=False)
        assert prods[0]["composicao_padrao_equipe"] == target_team
        assert any("equipe herdada de template" in m for m in report.fixed)

    def test_skips_when_target_missing(self):
        prods = [{"id": "CPU-DREN-BOCA-BDTC-100-PROD-001", "composicao_padrao_equipe": {}}]
        report = _report()
        cure_contextual([], prods, [], report, apply=True)
        assert report.fixed == []

    def test_skips_when_target_not_empty(self):
        target_team = {"funcoes": [{"funcao_id": "MO-X", "num_pessoas": 1}], "equipamentos": []}
        source_team = {"funcoes": [{"funcao_id": "MO-1", "num_pessoas": 2}], "equipamentos": []}
        prods = self._prods(target_team, source_team)
        report = _report()
        cure_contextual([], prods, [], report, apply=True)
        assert report.fixed == []
        assert prods[0]["composicao_padrao_equipe"] == target_team

    def test_skips_when_source_also_empty(self):
        prods = self._prods({"funcoes": [], "equipamentos": []}, {"funcoes": [], "equipamentos": []})
        report = _report()
        cure_contextual([], prods, [], report, apply=True)
        assert report.fixed == []


# ── cure_contextual: bloco 1) valor_horario herdado de PROD-* equivalente ────


class TestCureContextualValorHorarioHerdado:
    def test_inherits_from_equivalent_prod_apply(self):
        prods = [
            {"id": "CPU-ABC-XYZ-PROD-001", "valor_horario": None},
            {"id": "PROD-XYZ-001", "valor_horario": 42.5},
        ]
        report = _report()
        cure_contextual([], prods, [], report, apply=True)
        assert prods[0]["valor_horario"] == 42.5
        assert any("valor_horario herdado de PROD-XYZ-001" in m for m in report.fixed)

    def test_inherits_dry_run(self):
        prods = [
            {"id": "CPU-ABC-XYZ-PROD-001", "valor_horario": None},
            {"id": "PROD-XYZ-001", "valor_horario": 42.5},
        ]
        report = _report()
        cure_contextual([], prods, [], report, apply=False)
        assert prods[0]["valor_horario"] is None
        assert report.fixed

    def test_no_match_when_valor_horario_present(self):
        prods = [{"id": "CPU-ABC-XYZ-PROD-001", "valor_horario": 10.0}]
        report = _report()
        cure_contextual([], prods, [], report, apply=True)
        assert report.fixed == []

    def test_no_match_when_id_does_not_match_pattern(self):
        prods = [{"id": "PROD-SOMETHING", "valor_horario": None}]
        report = _report()
        cure_contextual([], prods, [], report, apply=True)
        assert report.fixed == []

    def test_no_match_when_candidate_missing(self):
        prods = [{"id": "CPU-ABC-XYZ-PROD-001", "valor_horario": None}]
        report = _report()
        cure_contextual([], prods, [], report, apply=True)
        assert report.fixed == []

    def test_skips_non_dict_and_missing_id(self):
        prods = ["not-a-dict", {"valor_horario": None}]
        report = _report()
        cure_contextual([], prods, [], report, apply=True)
        assert report.fixed == []

    def test_skips_when_candidate_val_none(self):
        prods = [
            {"id": "CPU-ABC-XYZ-PROD-001", "valor_horario": None},
            {"id": "PROD-XYZ-001", "valor_horario": None},
        ]
        report = _report()
        cure_contextual([], prods, [], report, apply=True)
        assert report.fixed == []


# ── cure_contextual: bloco 2) normalização de código de insumo + remap ──────


class TestCureContextualNormalizaCodigoInsumo:
    def test_normalizes_invalid_code_and_remaps_refs(self):
        insumos = [{"codigo": "insumo inválido!!", "tipo": "MATERIAL"}]
        cpus = [{"codigo": "CPU-1", "composicao_itens": [{"insumo_id": "insumo inválido!!"}]}]
        prods = [
            {
                "id": "P1",
                "composicao_padrao_equipe": {
                    "funcoes": [{"funcao_id": "insumo inválido!!"}],
                    "equipamentos": [{"equip_id": "insumo inválido!!"}],
                },
                "variantes": [
                    {
                        "equipe": {
                            "funcoes": [{"funcao_id": "insumo inválido!!"}],
                            "equipamentos": [{"equip_id": "insumo inválido!!"}],
                        }
                    }
                ],
            }
        ]
        report = _report()
        cure_contextual(cpus, prods, insumos, report, apply=True)
        new_code = insumos[0]["codigo"]
        assert new_code != "insumo inválido!!"
        assert cure_schema._is_valid_insumo_code(new_code)
        assert cpus[0]["composicao_itens"][0]["insumo_id"] == new_code
        assert prods[0]["composicao_padrao_equipe"]["funcoes"][0]["funcao_id"] == new_code
        assert prods[0]["composicao_padrao_equipe"]["equipamentos"][0]["equip_id"] == new_code
        assert prods[0]["variantes"][0]["equipe"]["funcoes"][0]["funcao_id"] == new_code
        assert prods[0]["variantes"][0]["equipe"]["equipamentos"][0]["equip_id"] == new_code
        assert any("codigo normalizado" in m for m in report.fixed)

    def test_normalizes_dry_run_does_not_mutate(self):
        insumos = [{"codigo": "insumo inválido!!", "tipo": "MATERIAL"}]
        report = _report()
        cure_contextual([], [], insumos, report, apply=False)
        assert insumos[0]["codigo"] == "insumo inválido!!"
        assert report.fixed

    def test_valid_code_untouched(self):
        insumos = [{"codigo": "MA-VALID-1", "tipo": "MATERIAL"}]
        report = _report()
        cure_contextual([], [], insumos, report, apply=True)
        assert insumos[0]["codigo"] == "MA-VALID-1"
        assert report.fixed == []

    def test_collision_triggers_salt_suffix(self):
        # Dois códigos inválidos que normalizam para o mesmo valor colidem
        # com um código já em uso -> aplica sufixo -1, -2, ...
        insumos = [
            {"codigo": "MA VALID 1", "tipo": "MATERIAL"},
            {"codigo": "ma valid 1", "tipo": "MATERIAL"},
            {"codigo": "MA-VALID-1", "tipo": "MATERIAL"},
        ]
        report = _report()
        cure_contextual([], [], insumos, report, apply=True)
        codes = [i["codigo"] for i in insumos]
        assert len(set(codes)) == 3
        for c in codes:
            assert cure_schema._is_valid_insumo_code(c)

    def test_non_dict_and_non_str_codigo_skipped(self):
        insumos = ["not-a-dict", {"codigo": 123, "tipo": "MATERIAL"}]
        report = _report()
        cure_contextual([], [], insumos, report, apply=True)
        assert report.fixed == []


# ── cure_contextual: bloco 3) composicao_itens vazia -> preencher/sintetizar ─


class TestCureContextualComposicaoItensVazia:
    def test_fills_with_unique_candidate_apply(self):
        cpus = [{"codigo": "X1", "composicao_itens": []}]
        insumos = [{"codigo": "MA-AGIS-X1", "tipo": "MATERIAL"}]
        report = _report()
        cure_contextual(cpus, [], insumos, report, apply=True)
        assert cpus[0]["composicao_itens"] == [
            {"insumo_id": "MA-AGIS-X1", "coeficiente": 1.0, "categoria_custo": "MATERIAL"}
        ]
        assert any("preenchida automaticamente" in m for m in report.fixed)

    def test_fills_with_unique_candidate_dry_run(self):
        cpus = [{"codigo": "X1", "composicao_itens": []}]
        insumos = [{"codigo": "MA-AGIS-X1", "tipo": "MATERIAL"}]
        report = _report()
        cure_contextual(cpus, [], insumos, report, apply=False)
        assert cpus[0]["composicao_itens"] == []
        assert report.fixed

    def test_synthesizes_from_producao_equipe_apply(self):
        cpus = [{"codigo": "X2", "composicao_itens": [], "producao_id_ref": "P2"}]
        prods = [
            {
                "id": "P2",
                "composicao_padrao_equipe": {
                    "funcoes": [{"funcao_id": "MO-1", "num_pessoas": 2}],
                    "equipamentos": [{"equip_id": "EQ-1", "num_unidades": 1}],
                },
            }
        ]
        insumos = [
            {"codigo": "MO-1", "tipo": "MAO_OBRA"},
            {"codigo": "EQ-1", "tipo": "EQUIPAMENTO"},
        ]
        report = _report()
        cure_contextual(cpus, prods, insumos, report, apply=True)
        itens = cpus[0]["composicao_itens"]
        assert {"insumo_id": "MO-1", "coeficiente": 2.0, "categoria_custo": "MAO_OBRA"} in itens
        assert {"insumo_id": "EQ-1", "coeficiente": 1.0, "categoria_custo": "EQUIPAMENTO"} in itens
        assert any("sintetizada a partir da equipe" in m for m in report.fixed)

    def test_synthesizes_skips_non_positive_and_unknown(self):
        cpus = [{"codigo": "X3", "composicao_itens": [], "producao_id_ref": "P3"}]
        prods = [
            {
                "id": "P3",
                "composicao_padrao_equipe": {
                    "funcoes": [
                        {"funcao_id": "MO-UNKNOWN", "num_pessoas": 2},
                        {"funcao_id": "MO-1", "num_pessoas": 0},
                        {"funcao_id": "MO-2", "num_pessoas": "not-a-number"},
                        "not-a-dict",
                    ],
                    "equipamentos": [
                        {"equip_id": "EQ-UNKNOWN", "num_unidades": 1},
                        {"equip_id": "EQ-1", "num_unidades": 0},
                        {"equip_id": "EQ-2", "num_unidades": "not-a-number"},
                        "not-a-dict",
                    ],
                },
            }
        ]
        insumos = [
            {"codigo": "MO-1", "tipo": "MAO_OBRA"},
            {"codigo": "MO-2", "tipo": "MAO_OBRA"},
            {"codigo": "EQ-1", "tipo": "EQUIPAMENTO"},
            {"codigo": "EQ-2", "tipo": "EQUIPAMENTO"},
        ]
        report = _report()
        cure_contextual(cpus, prods, insumos, report, apply=True)
        # nenhum item sobrevive aos filtros -> nada sintetizado -> manual+skipped
        assert "composicao_itens" not in cpus[0] or cpus[0].get("composicao_itens") == []
        assert any("sem candidato único de insumo" in m for m in report.manual)
        assert any("permitido no schema" in m for m in report.skipped)

    def test_synthesizes_dry_run_does_not_mutate(self):
        cpus = [{"codigo": "X2B", "composicao_itens": [], "producao_id_ref": "P2B"}]
        prods = [
            {
                "id": "P2B",
                "composicao_padrao_equipe": {
                    "funcoes": [{"funcao_id": "MO-1", "num_pessoas": 2}],
                    "equipamentos": [],
                },
            }
        ]
        insumos = [{"codigo": "MO-1", "tipo": "MAO_OBRA"}]
        report = _report()
        cure_contextual(cpus, prods, insumos, report, apply=False)
        assert cpus[0]["composicao_itens"] == []
        assert any("sintetizada a partir da equipe" in m for m in report.fixed)

    def test_no_candidate_and_no_producao_ref(self):
        cpus = [{"codigo": "X4", "composicao_itens": []}]
        report = _report()
        cure_contextual(cpus, [], [], report, apply=True)
        assert any("sem candidato único" in m for m in report.manual)

    def test_two_ambiguous_candidates_falls_back(self):
        cpus = [{"codigo": "X5", "composicao_itens": []}]
        insumos = [
            {"codigo": "MA-AGIS-X5", "tipo": "MATERIAL"},
            {"codigo": "MA-X5", "tipo": "MATERIAL"},
        ]
        report = _report()
        cure_contextual(cpus, [], insumos, report, apply=True)
        assert any("sem candidato único" in m for m in report.manual)

    def test_non_dict_cpu_and_missing_fields_skipped(self):
        cpus = ["not-a-dict", {"codigo": 123, "composicao_itens": []}, {"codigo": "X6", "composicao_itens": None}]
        report = _report()
        cure_contextual(cpus, [], [], report, apply=True)
        assert report.manual == []
        assert report.fixed == []

    def test_non_empty_composicao_itens_untouched(self):
        cpus = [{"codigo": "X7", "composicao_itens": [{"insumo_id": "A", "coeficiente": 1, "categoria_custo": "M"}]}]
        report = _report()
        cure_contextual(cpus, [], [], report, apply=True)
        assert report.fixed == []
        assert report.manual == []


# ── cure_contextual: bloco 4) outliers de produtividade -> mediana do grupo ──


def _outlier_group(prefix: str, categoria: str, unidade: str, valores: list[float]) -> tuple[list[dict], list[dict]]:
    cpus = []
    prods = []
    for i, v in enumerate(valores):
        pid = f"PROD-{prefix}-{i}"
        prods.append({"id": pid, "valor_horario": v})
        cpus.append(
            {
                "codigo": f"CPU-{prefix}-{i}",
                "categoria": categoria,
                "unidade": unidade,
                "producao_id_ref": pid,
            }
        )
    return cpus, prods


class TestCureContextualOutliers:
    def test_high_extreme_corrected_to_median_apply(self):
        cpus, prods = _outlier_group("HI", "CAT1", "UN1", [10.0] * 7 + [100.0])
        report = _report()
        cure_contextual(cpus, prods, [], report, apply=True)
        outlier_prod = next(p for p in prods if p["id"] == "PROD-HI-7")
        assert outlier_prod["valor_horario"] == 10.0
        assert any("valor_horario 100.000000 -> 10.000000" in m for m in report.fixed)

    def test_high_extreme_dry_run_not_mutated(self):
        cpus, prods = _outlier_group("HID", "CAT1D", "UN1", [10.0] * 7 + [100.0])
        report = _report()
        cure_contextual(cpus, prods, [], report, apply=False)
        outlier_prod = next(p for p in prods if p["id"] == "PROD-HID-7")
        assert outlier_prod["valor_horario"] == 100.0
        assert report.fixed

    def test_high_moderate_not_extreme_enough_skipped(self):
        cpus, prods = _outlier_group("HM", "CAT2", "UN1", [10.0] * 7 + [30.0])
        report = _report()
        cure_contextual(cpus, prods, [], report, apply=True)
        assert report.fixed == []

    def test_low_extreme_corrected_to_median_apply(self):
        cpus, prods = _outlier_group("LO", "CAT3", "UN1", [10.0] * 7 + [3.0])
        report = _report()
        cure_contextual(cpus, prods, [], report, apply=True)
        outlier_prod = next(p for p in prods if p["id"] == "PROD-LO-7")
        assert outlier_prod["valor_horario"] == 10.0
        assert report.fixed

    def test_low_moderate_not_extreme_enough_skipped(self):
        cpus, prods = _outlier_group("LM", "CAT4", "UN1", [10.0] * 7 + [6.0])
        report = _report()
        cure_contextual(cpus, prods, [], report, apply=True)
        assert report.fixed == []

    def test_group_with_fewer_than_8_rows_no_bounds_no_op(self):
        cpus, prods = _outlier_group("SM", "CAT5", "UN1", [10.0, 20.0, 1000.0])
        report = _report()
        cure_contextual(cpus, prods, [], report, apply=True)
        assert report.fixed == []

    def test_all_values_equal_no_iqr_no_op(self):
        cpus, prods = _outlier_group("EQ", "CAT6", "UN1", [10.0] * 8)
        report = _report()
        cure_contextual(cpus, prods, [], report, apply=True)
        assert report.fixed == []

    def test_skips_non_dict_and_missing_codigo(self):
        cpus = ["not-a-dict", {"codigo": 123}]
        report = _report()
        cure_contextual(cpus, [], [], report, apply=True)
        assert report.fixed == []

    def test_skips_missing_or_invalid_producao_ref(self):
        cpus = [
            {"codigo": "C1", "producao_id_ref": None},
            {"codigo": "C2", "producao_id_ref": ""},
            {"codigo": "C3", "producao_id_ref": "NOPE"},
        ]
        report = _report()
        cure_contextual(cpus, [], [], report, apply=True)
        assert report.fixed == []

    def test_skips_when_valor_horario_none_or_invalid_or_non_positive(self):
        prods = [
            {"id": "P1", "valor_horario": None},
            {"id": "P2", "valor_horario": "not-a-number"},
            {"id": "P3", "valor_horario": -5.0},
        ]
        cpus = [
            {"codigo": "C1", "producao_id_ref": "P1"},
            {"codigo": "C2", "producao_id_ref": "P2"},
            {"codigo": "C3", "producao_id_ref": "P3"},
        ]
        report = _report()
        cure_contextual(cpus, prods, [], report, apply=True)
        assert report.fixed == []


# ── nothing-to-fix pass-through ──────────────────────────────────────────────


class TestCureContextualNoOp:
    def test_empty_inputs_no_op(self):
        report = _report()
        cure_contextual([], [], [], report, apply=True)
        assert report.fixed == report.manual == report.skipped == []

    def test_clean_inputs_no_op_apply_false(self):
        cpus = [
            {
                "codigo": "CPU-1",
                "categoria": "DIVERSOS",
                "unidade": "un",
                "producao_id_ref": "PROD-1",
                "composicao_itens": [{"insumo_id": "MA-1", "coeficiente": 1, "categoria_custo": "MATERIAL"}],
            }
        ]
        prods = [{"id": "PROD-1", "valor_horario": 10.0}]
        insumos = [{"codigo": "MA-1", "tipo": "MATERIAL"}]
        report = _report()
        cure_contextual(cpus, prods, insumos, report, apply=False)
        assert report.fixed == []
        assert report.manual == []


# ── _context_base ────────────────────────────────────────────────────────────


class TestContextBase:
    def test_raises_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cure_schema._io, "ROOT", tmp_path)
        with pytest.raises(FileNotFoundError, match="Contexto não encontrado"):
            _context_base("nope")

    def test_returns_path_when_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cure_schema._io, "ROOT", tmp_path)
        (tmp_path / "config" / "catalogos" / "ctx1").mkdir(parents=True)
        result = _context_base("ctx1")
        assert result == tmp_path / "config" / "catalogos" / "ctx1"


# ── _load_entity_files ───────────────────────────────────────────────────────


class TestLoadEntityFiles:
    def test_loads_json_files_from_subdirs(self, tmp_path):
        (tmp_path / "cpus").mkdir()
        (tmp_path / "cpus" / "a.json").write_text(json.dumps({"codigo": "A"}), encoding="utf-8")
        (tmp_path / "cpus" / "b.json").write_text(json.dumps({"codigo": "B"}), encoding="utf-8")
        rows = _load_entity_files(tmp_path, ("cpus",))
        assert len(rows) == 2
        codes = sorted(payload["codigo"] for _, payload in rows)
        assert codes == ["A", "B"]

    def test_missing_subdir_is_skipped(self, tmp_path):
        rows = _load_entity_files(tmp_path, ("nao_existe",))
        assert rows == []

    def test_hidden_files_are_skipped(self, tmp_path):
        (tmp_path / "insumos").mkdir()
        (tmp_path / "insumos" / ".hidden.json").write_text("{}", encoding="utf-8")
        rows = _load_entity_files(tmp_path, ("insumos",))
        assert rows == []

    def test_malformed_json_is_skipped(self, tmp_path):
        (tmp_path / "producoes").mkdir()
        (tmp_path / "producoes" / "bad.json").write_text("{not valid json", encoding="utf-8")
        rows = _load_entity_files(tmp_path, ("producoes",))
        assert rows == []

    def test_non_dict_payload_is_skipped(self, tmp_path):
        (tmp_path / "producoes").mkdir()
        (tmp_path / "producoes" / "list.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        rows = _load_entity_files(tmp_path, ("producoes",))
        assert rows == []

    def test_multiple_subdirs_combined(self, tmp_path):
        (tmp_path / "producoes").mkdir()
        (tmp_path / "produtividades").mkdir()
        (tmp_path / "producoes" / "p1.json").write_text(json.dumps({"id": "P1"}), encoding="utf-8")
        (tmp_path / "produtividades" / "p2.json").write_text(json.dumps({"id": "P2"}), encoding="utf-8")
        rows = _load_entity_files(tmp_path, ("producoes", "produtividades"))
        assert len(rows) == 2


# ── _persist_entity_files ────────────────────────────────────────────────────


class TestPersistEntityFiles:
    def test_apply_false_is_noop(self, tmp_path):
        f = tmp_path / "x.json"
        f.write_text(json.dumps({"a": 1}), encoding="utf-8")
        written = _persist_entity_files([(f, {"a": 2})], apply=False)
        assert written == 0
        assert json.loads(f.read_text(encoding="utf-8")) == {"a": 1}

    def test_apply_true_writes_when_changed(self, tmp_path):
        f = tmp_path / "x.json"
        f.write_text(json.dumps({"a": 1}), encoding="utf-8")
        written = _persist_entity_files([(f, {"a": 2})], apply=True)
        assert written == 1
        assert json.loads(f.read_text(encoding="utf-8")) == {"a": 2}

    def test_apply_true_skips_when_unchanged(self, tmp_path):
        f = tmp_path / "x.json"
        f.write_text(json.dumps({"a": 1}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written = _persist_entity_files([(f, {"a": 1})], apply=True)
        assert written == 0

    def test_apply_true_writes_when_file_missing_or_unreadable(self, tmp_path):
        f = tmp_path / "new.json"
        written = _persist_entity_files([(f, {"a": 1})], apply=True)
        assert written == 1
        assert f.exists()

    def test_empty_entries_returns_zero(self):
        assert _persist_entity_files([], apply=True) == 0


# ── run() ─────────────────────────────────────────────────────────────────────


def _write_entity(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestRun:
    def test_dry_run_happy_path_no_entities(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(cure_schema._run, "_context_base", lambda cid: tmp_path)
        run("ctx", apply=False)
        out = capsys.readouterr().out
        assert "DRY-RUN" in out
        assert "Nenhum erro residual" in out

    def test_apply_happy_path_persists_valid_entities(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(cure_schema._run, "_context_base", lambda cid: tmp_path)
        _write_entity(
            tmp_path / "insumos" / "ins1.json",
            {
                "codigo": "MA-TEST",
                "tipo": "MATERIAL",
                "descricao": "Teste",
                "unidade": "un",
                "preco_unitario": 10.0,
                "fonte_preco": "catalogo_proprio",
            },
        )
        _write_entity(
            tmp_path / "producoes" / "prod1.json",
            {"id": "PROD-TEST-001", "codigo": "PROD-TEST-001", "descricao": "Teste", "valor_horario": 50.0},
        )
        _write_entity(
            tmp_path / "cpus" / "cpu1.json",
            {
                "codigo": "CPU-TEST-001",
                "descricao": "Teste",
                "unidade": "un",
                "origem": "PROPRIA",
                "producao_id_ref": "PROD-TEST-001",
                "categoria": "DIVERSOS",
                "composicao_itens": [{"insumo_id": "MA-TEST", "coeficiente": 1.0, "categoria_custo": "MATERIAL"}],
            },
        )
        (tmp_path / ".catalog_bundle.json").write_text("{}", encoding="utf-8")

        run("ctx", apply=True)

        out = capsys.readouterr().out
        assert "APPLY" in out
        assert "Arquivos atualizados" in out
        assert "Bundle invalidado" in out
        assert not (tmp_path / ".catalog_bundle.json").exists()
        assert "Nenhum erro residual" in out

    def test_raises_runtime_error_on_residual_schema_errors(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(cure_schema._run, "_context_base", lambda cid: tmp_path)
        # Insumo inválido: falta campo obrigatório 'fonte_preco'
        _write_entity(
            tmp_path / "insumos" / "bad.json",
            {"codigo": "MA-BAD", "tipo": "MATERIAL", "descricao": "X", "unidade": "un", "preco_unitario": 1.0},
        )
        with pytest.raises(RuntimeError, match="erro"):
            run("ctx", apply=False)
        out = capsys.readouterr().out
        assert "erro(s) residual(is)" in out
        assert "DRY-RUN" in out  # mensagem de dica de --apply

    def test_raises_runtime_error_on_residual_schema_errors_apply_true_no_dry_run_hint(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(cure_schema._run, "_context_base", lambda cid: tmp_path)
        # Falta 'codigo' — nenhuma regra de cura_insumo inventa um código ausente,
        # então o erro residual persiste mesmo com apply=True.
        _write_entity(
            tmp_path / "insumos" / "bad.json",
            {"tipo": "MATERIAL", "descricao": "X", "unidade": "un", "preco_unitario": 1.0},
        )
        with pytest.raises(RuntimeError, match="erro"):
            run("ctx", apply=True)
        out = capsys.readouterr().out
        assert "erro(s) residual(is)" in out
        assert "DRY-RUN" not in out

    def test_reports_auto_fixes_and_manual_and_skipped(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(cure_schema._run, "_context_base", lambda cid: tmp_path)
        # Producao com campo legado 'equipe' -> gera correção automática (fixed)
        _write_entity(
            tmp_path / "producoes" / "p1.json",
            {
                "id": "PROD-1",
                "codigo": "PROD-1",
                "descricao": "Teste",
                "valor_horario": 10.0,
                "equipe": {"funcoes": [], "equipamentos": []},
            },
        )
        # CPU com composicao_itens vazia sem candidato -> manual + skipped
        _write_entity(
            tmp_path / "cpus" / "c1.json",
            {
                "codigo": "CPU-1",
                "descricao": "Teste",
                "unidade": "un",
                "origem": "PROPRIA",
                "producao_id_ref": "PROD-1",
                "categoria": "DIVERSOS",
                "composicao_itens": [],
            },
        )
        run("ctx", apply=True)
        out = capsys.readouterr().out
        assert "[AUTO]" in out
        assert "[MANUAL]" in out
        assert "[INFO]" in out

    def test_erros_truncated_after_50(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(cure_schema._run, "_context_base", lambda cid: tmp_path)
        for i in range(60):
            _write_entity(
                tmp_path / "insumos" / f"bad{i}.json",
                {"codigo": f"MA-BAD-{i}", "tipo": "MATERIAL", "descricao": "X", "unidade": "un"},
            )
        with pytest.raises(RuntimeError):
            run("ctx", apply=False)
        out = capsys.readouterr().out
        assert "mais " in out


# ── main() ────────────────────────────────────────────────────────────────────


class TestMain:
    def test_main_calls_run_with_parsed_args(self, monkeypatch):
        calls = {}

        def fake_run(contexto_id, apply):
            calls["contexto_id"] = contexto_id
            calls["apply"] = apply

        monkeypatch.setattr(cure_schema._run, "run", fake_run)
        monkeypatch.setattr(sys, "argv", ["prog", "--contexto", "mendeslobo", "--apply"])
        main()
        assert calls == {"contexto_id": "mendeslobo", "apply": True}

    def test_main_default_apply_false(self, monkeypatch):
        calls = {}

        def fake_run(contexto_id, apply):
            calls["contexto_id"] = contexto_id
            calls["apply"] = apply

        monkeypatch.setattr(cure_schema._run, "run", fake_run)
        monkeypatch.setattr(sys, "argv", ["prog", "--contexto", "ctx"])
        main()
        assert calls == {"contexto_id": "ctx", "apply": False}

    def test_main_exits_1_on_file_not_found(self, monkeypatch, capsys):
        def fake_run(contexto_id, apply):
            raise FileNotFoundError("Contexto não encontrado: ctx")

        monkeypatch.setattr(cure_schema._run, "run", fake_run)
        monkeypatch.setattr(sys, "argv", ["prog", "--contexto", "ctx"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "[ERRO]" in err

    def test_main_exits_1_on_runtime_error(self, monkeypatch, capsys):
        def fake_run(contexto_id, apply):
            raise RuntimeError("erros residuais")

        monkeypatch.setattr(cure_schema._run, "run", fake_run)
        monkeypatch.setattr(sys, "argv", ["prog", "--contexto", "ctx", "--apply"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "[ERRO]" in err

    def test_dunder_main_invokes_main(self, monkeypatch):
        """Running cure_schema.py as __main__ calls main() (last line of module)."""
        import runpy

        monkeypatch.setattr(sys, "argv", ["cure_schema.py", "--contexto", "does-not-exist-ctx"])
        _mod = "concilium.application.catalog.cure_schema"
        saved = sys.modules.pop(_mod, None)
        try:
            with pytest.raises(SystemExit) as exc_info:
                runpy.run_module(_mod, run_name="__main__", alter_sys=False)
            assert exc_info.value.code == 1
        finally:
            if saved is not None:
                sys.modules[_mod] = saved
