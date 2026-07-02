"""Tests for _audit_utils.py — coverage boost toward 80%+."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from concilium.application.benchmarks.analysis._audit_utils import (
    _aq_lp_check_dir,
    _aq_lp_load_meta,
    _aq_lp_matches_name,
    _as_float,
    _build_c_fixo_candidates,
    _extract_pe_from_list_block,
    _extract_ref_ponto_equilibrio,
    _get_ref_confronto,
    _is_close,
    _latest_project_by_name,
    _load_json,
    _norm_float,
    _normalize_project_token,
    _resolve_canonical_path,
    _row_to_pe_entry,
    _sum_dict_counter,
)

# ---------------------------------------------------------------------------
# _load_json
# ---------------------------------------------------------------------------


class TestLoadJson:
    def test_reads_valid_json(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        f.write_text(json.dumps({"a": 1}), encoding="utf-8")
        result = _load_json(f)
        assert result == {"a": 1}

    def test_raises_on_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(Exception):  # noqa: B017
            _load_json(tmp_path / "nonexistent.json")

    def test_raises_on_invalid_json(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.json"
        f.write_text("not json", encoding="utf-8")
        with pytest.raises(Exception):  # noqa: B017
            _load_json(f)


# ---------------------------------------------------------------------------
# _norm_float
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, 0.0),
        (1.5, 1.5),
        ("3.14", 3.14),
        (None, 0.0),
        ("", 0.0),
        (False, 0.0),
        ("abc", 0.0),
        (42, 42.0),
    ],
)
def test_norm_float(value, expected):
    assert _norm_float(value) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# _normalize_project_token
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("hello_world", "HELLO WORLD"),
        ("calibrado_test", "TEST"),
        ("CALIBRADO", ""),
        ("abc--123", "ABC 123"),
        ("  spaces  ", "SPACES"),
        (None, ""),
        ("", ""),
        ("PROJETO CALIBRADO FINAL", "PROJETO FINAL"),
        ("projeto_CALIBRADO_final", "PROJETO FINAL"),
        ("abc_def_ghi", "ABC DEF GHI"),
    ],
)
def test_normalize_project_token(value, expected):
    assert _normalize_project_token(value) == expected


# ---------------------------------------------------------------------------
# _get_ref_confronto
# ---------------------------------------------------------------------------


class TestGetRefConfronto:
    def test_returns_benchmark_confronto_when_present(self):
        ref = {"resultado": {"benchmark_confronto_referencia": {"x": 1}}}
        assert _get_ref_confronto(ref) == {"x": 1}

    def test_returns_empty_when_resultado_missing(self):
        assert _get_ref_confronto({}) == {}

    def test_returns_empty_when_resultado_not_dict(self):
        ref = {"resultado": "string"}
        assert _get_ref_confronto(ref) == {}

    def test_returns_empty_when_confronto_missing(self):
        ref = {"resultado": {"other_key": 42}}
        assert _get_ref_confronto(ref) == {}

    def test_returns_empty_when_confronto_none(self):
        ref = {"resultado": {"benchmark_confronto_referencia": None}}
        assert _get_ref_confronto(ref) == {}

    def test_returns_empty_when_resultado_none(self):
        ref = {"resultado": None}
        assert _get_ref_confronto(ref) == {}


# ---------------------------------------------------------------------------
# _is_close
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ref_val,cur_val,expected",
    [
        (100.0, 100.0, True),
        (100.0, 100.04, True),  # within default abs_tol=0.05
        (100.0, 100.06, True),  # within rel_tol=0.001 * 100=0.1
        (100.0, 100.2, False),  # outside both tolerances
        (0.0, 0.0, True),
        (0.0, 0.04, True),  # within abs_tol=0.05
        (0.0, 0.06, False),  # outside rel_tol * max(0,0,1)=0.001, but abs_tol=0.05 → 0.06>0.05 so False
        (1000.0, 1001.0, True),  # rel_tol=0.001 * 1000 = 1.0, delta=1.0 ≤ 1.0
        (1000.0, 1001.1, False),  # delta=1.1 > max(0.05, 1.0)
    ],
)
def test_is_close(ref_val, cur_val, expected):
    assert _is_close(ref_val, cur_val) is expected


def test_is_close_custom_tol():
    assert _is_close(10.0, 11.0, abs_tol=2.0) is True
    assert _is_close(10.0, 13.0, abs_tol=2.0) is False


# ---------------------------------------------------------------------------
# _sum_dict_counter
# ---------------------------------------------------------------------------


class TestSumDictCounter:
    def test_basic_sum(self):
        entries = [
            {"id": "A", "qty": 3},
            {"id": "B", "qty": 2},
            {"id": "A", "qty": 4},
        ]
        result = _sum_dict_counter(entries, "id", "qty")
        assert result == Counter({"A": 7, "B": 2})

    def test_empty_list(self):
        assert _sum_dict_counter([], "id", "qty") == Counter()

    def test_none_list(self):
        assert _sum_dict_counter(None, "id", "qty") == Counter()  # type: ignore[arg-type]

    def test_skips_rows_without_key_id(self):
        entries = [{"qty": 5}, {"id": "A", "qty": 2}]
        result = _sum_dict_counter(entries, "id", "qty")
        assert result == Counter({"A": 2})

    def test_missing_qty_treated_as_zero(self):
        entries = [{"id": "A"}]
        result = _sum_dict_counter(entries, "id", "qty")
        assert result["A"] == 0

    def test_falsy_key_id_skipped(self):
        entries = [{"id": "", "qty": 5}, {"id": None, "qty": 3}]
        result = _sum_dict_counter(entries, "id", "qty")
        assert len(result) == 0


# ---------------------------------------------------------------------------
# _as_float
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        (1, 1.0),
        ("2.5", 2.5),
        (None, 0.0),
        ("", 0.0),
        (False, 0.0),
        ("not_a_number", 0.0),
        (0, 0.0),
    ],
)
def test_as_float(value, expected):
    assert _as_float(value) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# _row_to_pe_entry
# ---------------------------------------------------------------------------


class TestRowToPeEntry:
    def test_returns_none_when_no_item_id(self):
        assert _row_to_pe_entry({}) is None
        assert _row_to_pe_entry({"other": "x"}) is None

    def test_uses_item_id_field(self):
        row = {"item_id": "X1", "custo_fixo_equipe": 100.0, "custo_venda_cpu": 150.0}
        result = _row_to_pe_entry(row)
        assert result is not None
        assert result["item_id"] == "X1"
        assert result["custo_fixo_equipe"] == pytest.approx(100.0)
        assert result["custo_venda_cpu"] == pytest.approx(150.0)
        assert result["delta"] == pytest.approx(50.0)

    def test_uses_item_field_as_fallback(self):
        row = {"item": "Y2", "custo_fixo_total": 50.0, "custo_venda": 80.0}
        result = _row_to_pe_entry(row)
        assert result is not None
        assert result["item_id"] == "Y2"
        assert result["custo_fixo_equipe"] == pytest.approx(50.0)
        assert result["custo_venda_cpu"] == pytest.approx(80.0)
        assert result["delta"] == pytest.approx(30.0)

    def test_uses_eap_item_as_fallback(self):
        row = {"eap_item": "Z3"}
        result = _row_to_pe_entry(row)
        assert result is not None
        assert result["item_id"] == "Z3"

    def test_uses_existing_delta_when_provided(self):
        row = {"item_id": "A1", "custo_fixo_equipe": 100.0, "custo_venda_cpu": 200.0, "delta": 999.0}
        result = _row_to_pe_entry(row)
        assert result is not None
        assert result["delta"] == pytest.approx(999.0)

    def test_custo_fixo_equipe_takes_priority_over_total(self):
        row = {"item_id": "B1", "custo_fixo_equipe": 10.0, "custo_fixo_total": 99.0, "custo_venda_cpu": 20.0}
        result = _row_to_pe_entry(row)
        assert result is not None
        assert result["custo_fixo_equipe"] == pytest.approx(10.0)

    def test_custo_venda_cpu_takes_priority_over_custo_venda(self):
        row = {"item_id": "C1", "custo_venda_cpu": 50.0, "custo_venda": 999.0}
        result = _row_to_pe_entry(row)
        assert result is not None
        assert result["custo_venda_cpu"] == pytest.approx(50.0)

    def test_delta_none_when_both_costs_none(self):
        row = {"item_id": "D1"}
        result = _row_to_pe_entry(row)
        assert result is not None
        assert result["delta"] == pytest.approx(0.0)

    def test_custo_fixo_equipe_zero_is_used(self):
        # custo_fixo_equipe=0 is not None, so should be used (not fall back to custo_fixo_total)
        row = {"item_id": "E1", "custo_fixo_equipe": 0, "custo_fixo_total": 99.0, "custo_venda_cpu": 10.0}
        result = _row_to_pe_entry(row)
        assert result is not None
        assert result["custo_fixo_equipe"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _extract_pe_from_list_block
# ---------------------------------------------------------------------------


class TestExtractPeFromListBlock:
    def test_returns_none_for_non_list(self):
        assert _extract_pe_from_list_block("string") is None
        assert _extract_pe_from_list_block({}) is None
        assert _extract_pe_from_list_block(None) is None

    def test_returns_none_for_empty_list(self):
        assert _extract_pe_from_list_block([]) is None

    def test_returns_none_for_list_of_non_dicts(self):
        assert _extract_pe_from_list_block([1, 2, "three"]) is None

    def test_returns_none_when_all_rows_invalid(self):
        # dicts but missing item_id/item/eap_item
        assert _extract_pe_from_list_block([{"x": 1}, {"y": 2}]) is None

    def test_returns_valid_entries(self):
        rows = [
            {"item_id": "A", "custo_fixo_equipe": 10.0, "custo_venda_cpu": 20.0},
            {"not_item": "ignored"},
        ]
        result = _extract_pe_from_list_block(rows)
        assert result is not None
        assert len(result) == 1
        assert result[0]["item_id"] == "A"

    def test_skips_non_dict_entries_but_includes_valid(self):
        rows = [
            "not_a_dict",
            {"item_id": "B", "custo_fixo_equipe": 5.0, "custo_venda_cpu": 15.0},
        ]
        result = _extract_pe_from_list_block(rows)
        assert result is not None
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _build_c_fixo_candidates
# ---------------------------------------------------------------------------


class TestBuildCFixoCandidates:
    def test_pe_block_dict_with_all_keys(self):
        pe_block = {"c_fixo": [1], "benchmark_referencia": [2], "benchmark_referencia_itemizado": [3]}
        ref = {"c_fixo": [4]}
        result = _build_c_fixo_candidates(pe_block, ref)
        assert result == [[1], [2], [3], [4]]

    def test_pe_block_dict_missing_keys(self):
        pe_block = {}
        ref = {"c_fixo": [99]}
        result = _build_c_fixo_candidates(pe_block, ref)
        assert result == [None, None, None, [99]]

    def test_pe_block_not_dict(self):
        ref = {"c_fixo": [42]}
        result = _build_c_fixo_candidates(None, ref)
        assert result == [[42]]

    def test_pe_block_list_not_dict(self):
        ref = {}
        result = _build_c_fixo_candidates([1, 2], ref)
        assert result == [None]

    def test_ref_missing_c_fixo(self):
        pe_block = {}
        ref = {}
        result = _build_c_fixo_candidates(pe_block, ref)
        assert result == [None, None, None, None]


# ---------------------------------------------------------------------------
# _extract_ref_ponto_equilibrio
# ---------------------------------------------------------------------------


class TestExtractRefPontoEquilibrio:
    def test_returns_empty_when_no_pe_block(self):
        assert _extract_ref_ponto_equilibrio({}) == []

    def test_pe_block_as_list_with_valid_rows(self):
        ref = {"ponto_equilibrio": [{"item_id": "A1", "custo_fixo_equipe": 10.0, "custo_venda_cpu": 20.0}]}
        result = _extract_ref_ponto_equilibrio(ref)
        assert len(result) == 1
        assert result[0]["item_id"] == "A1"

    def test_pe_block_list_invalid_rows_falls_through(self):
        # list exists but has no valid rows => falls through to dict/candidate paths
        ref = {
            "ponto_equilibrio": [{"no_item_id": True}],
        }
        result = _extract_ref_ponto_equilibrio(ref)
        assert result == []

    def test_pe_block_dict_with_canonical(self):
        canonical_list = [{"item_id": "X"}]
        ref = {"ponto_equilibrio": {"canonical": canonical_list}}
        result = _extract_ref_ponto_equilibrio(ref)
        assert result == canonical_list

    def test_pe_block_dict_with_canonical_empty_ignored(self):
        # canonical is present but empty — should fall through to candidates
        ref = {
            "ponto_equilibrio": {
                "canonical": [],
                "c_fixo": [{"item_id": "B1", "custo_fixo_equipe": 5.0, "custo_venda_cpu": 10.0}],
            }
        }
        result = _extract_ref_ponto_equilibrio(ref)
        assert len(result) == 1
        assert result[0]["item_id"] == "B1"

    def test_pe_block_dict_with_c_fixo_candidate(self):
        ref = {"ponto_equilibrio": {"c_fixo": [{"item_id": "C1", "custo_fixo_equipe": 1.0, "custo_venda_cpu": 2.0}]}}
        result = _extract_ref_ponto_equilibrio(ref)
        assert len(result) == 1
        assert result[0]["item_id"] == "C1"

    def test_pe_block_dict_c_fixo_from_ref_level(self):
        ref = {
            "ponto_equilibrio": {},
            "c_fixo": [{"item_id": "D1", "custo_fixo_equipe": 3.0, "custo_venda_cpu": 6.0}],
        }
        result = _extract_ref_ponto_equilibrio(ref)
        assert len(result) == 1
        assert result[0]["item_id"] == "D1"

    def test_returns_empty_when_nothing_matches(self):
        ref = {"ponto_equilibrio": {"canonical": None}}
        result = _extract_ref_ponto_equilibrio(ref)
        assert result == []


# ---------------------------------------------------------------------------
# _aq_lp_load_meta
# ---------------------------------------------------------------------------


class TestAqLpLoadMeta:
    def test_loads_valid_meta(self, tmp_path: Path) -> None:
        meta_file = tmp_path / "meta.json"
        meta_file.write_text(json.dumps({"nome": "Projeto X"}), encoding="utf-8")
        result = _aq_lp_load_meta(meta_file)
        assert result == {"nome": "Projeto X"}

    def test_returns_none_on_missing_file(self, tmp_path: Path) -> None:
        result = _aq_lp_load_meta(tmp_path / "nonexistent.json")
        assert result is None

    def test_returns_none_on_invalid_json(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("not-json", encoding="utf-8")
        result = _aq_lp_load_meta(bad)
        assert result is None


# ---------------------------------------------------------------------------
# _aq_lp_matches_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nome_meta,nome_norm,project_name,target_norm,expected",
    [
        ("Projeto A", "PROJETO A", "Projeto A", "PROJETO A", True),  # exact nome_meta match
        ("Outro", "PROJETO A", "Outro2", "PROJETO A", True),  # nome_norm == target_norm
        ("Outro", "PROJETO A B", "Outro2", "PROJETO A", True),  # target_norm in nome_norm
        ("Outro", "PROJETO", "Outro2", "PROJETO A B", True),  # nome_norm in target_norm
        ("X", "X NORM", "Y", "Y NORM", False),  # no match
        ("", "", "", "", True),  # empty strings match
    ],
)
def test_aq_lp_matches_name(nome_meta, nome_norm, project_name, target_norm, expected):
    assert _aq_lp_matches_name(nome_meta, nome_norm, project_name, target_norm) is expected


# ---------------------------------------------------------------------------
# _aq_lp_check_dir
# ---------------------------------------------------------------------------


class TestAqLpCheckDir:
    def test_returns_none_for_non_directory(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("hi")
        assert _aq_lp_check_dir(f, "X", "X") is None

    def test_returns_none_when_meta_missing(self, tmp_path: Path) -> None:
        d = tmp_path / "proj"
        d.mkdir()
        assert _aq_lp_check_dir(d, "Proj X", "PROJ X") is None

    def test_returns_none_when_name_does_not_match(self, tmp_path: Path) -> None:
        d = tmp_path / "proj"
        d.mkdir()
        (d / "meta.json").write_text(json.dumps({"nome": "Outro Projeto", "criado_em": "2024-01"}), encoding="utf-8")
        assert _aq_lp_check_dir(d, "Proj X", "PROJ X") is None

    def test_returns_tuple_when_name_matches(self, tmp_path: Path) -> None:
        d = tmp_path / "proj"
        d.mkdir()
        (d / "meta.json").write_text(json.dumps({"nome": "Proj X", "criado_em": "2024-06"}), encoding="utf-8")
        result = _aq_lp_check_dir(d, "Proj X", "PROJ X")
        assert result is not None
        created, path = result
        assert created == "2024-06"
        assert path == d

    def test_returns_empty_criado_em_when_missing(self, tmp_path: Path) -> None:
        d = tmp_path / "proj"
        d.mkdir()
        (d / "meta.json").write_text(json.dumps({"nome": "Proj X"}), encoding="utf-8")
        result = _aq_lp_check_dir(d, "Proj X", "PROJ X")
        assert result is not None
        created, _ = result
        assert created == ""


# ---------------------------------------------------------------------------
# _latest_project_by_name
# ---------------------------------------------------------------------------


class TestLatestProjectByName:
    def _make_project_dir(self, root: Path, name: str, criado_em: str) -> Path:
        d = root / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(
            json.dumps({"nome": name, "criado_em": criado_em}),
            encoding="utf-8",
        )
        return d

    def test_returns_none_when_no_matching_projects(self, tmp_path: Path) -> None:
        projects_root = tmp_path / "projetos"
        projects_root.mkdir()
        self._make_project_dir(projects_root, "Outro Projeto", "2024-01")
        result = _latest_project_by_name("Proj X", projects_root)
        assert result is None

    def test_returns_matching_project(self, tmp_path: Path) -> None:
        projects_root = tmp_path / "projetos"
        projects_root.mkdir()
        d = self._make_project_dir(projects_root, "Proj X", "2024-01")
        result = _latest_project_by_name("Proj X", projects_root)
        assert result == d

    def test_returns_latest_when_multiple_match(self, tmp_path: Path) -> None:
        projects_root = tmp_path / "projetos"
        projects_root.mkdir()
        self._make_project_dir(projects_root, "Proj X", "2024-01")
        d2 = projects_root / "Proj X v2"
        d2.mkdir()
        (d2 / "meta.json").write_text(
            json.dumps({"nome": "Proj X", "criado_em": "2025-06"}),
            encoding="utf-8",
        )
        result = _latest_project_by_name("Proj X", projects_root)
        assert result == d2

    def test_skips_files_not_directories(self, tmp_path: Path) -> None:
        projects_root = tmp_path / "projetos"
        projects_root.mkdir()
        # Create a file that would fail is_dir check
        (projects_root / "not_a_dir.txt").write_text("hi")
        d = self._make_project_dir(projects_root, "Proj X", "2024-06")
        result = _latest_project_by_name("Proj X", projects_root)
        assert result == d


# ---------------------------------------------------------------------------
# _resolve_canonical_path
# ---------------------------------------------------------------------------


class TestResolveCanonicalPath:
    def test_returns_valid_candidate_raw_path(self, tmp_path: Path) -> None:
        canonical = tmp_path / "canonical.json"
        canonical.write_text(json.dumps({}), encoding="utf-8")
        extr = {"paths": {"canonical": str(canonical)}}
        ref = {}
        result = _resolve_canonical_path(extr, ref, tmp_path)
        assert result == canonical

    def test_finds_canonical_in_benchmarks_projetos(self, tmp_path: Path) -> None:
        # Build: tmp_path/benchmarks/projetos/proj_dir/v1/canonical.json
        proj_dir = tmp_path / "benchmarks" / "projetos" / "AGIS"
        proj_dir.mkdir(parents=True)
        (proj_dir / "meta.json").write_text(
            json.dumps({"nome": "AGIS", "criado_em": "2024-01"}),
            encoding="utf-8",
        )
        v1_dir = proj_dir / "v1"
        v1_dir.mkdir()
        canonical = v1_dir / "canonical.json"
        canonical.write_text(json.dumps({}), encoding="utf-8")

        extr = {}
        ref = {"projeto": "AGIS"}
        result = _resolve_canonical_path(extr, ref, tmp_path)
        assert result == canonical

    def test_finds_canonical_using_meta_current_version(self, tmp_path: Path) -> None:
        proj_dir = tmp_path / "benchmarks" / "projetos" / "MYPROJ"
        proj_dir.mkdir(parents=True)
        (proj_dir / "meta.json").write_text(
            json.dumps({"nome": "MYPROJ", "criado_em": "2024-05", "current_version": "v2"}),
            encoding="utf-8",
        )
        v2_dir = proj_dir / "v2"
        v2_dir.mkdir()
        canonical = v2_dir / "canonical.json"
        canonical.write_text(json.dumps({}), encoding="utf-8")

        extr = {}
        ref = {"projeto": "MYPROJ"}
        result = _resolve_canonical_path(extr, ref, tmp_path)
        assert result == canonical

    def test_raises_file_not_found_when_nothing_matches(self, tmp_path: Path) -> None:
        extr = {}
        ref = {"projeto": "NonExistent"}
        with pytest.raises(FileNotFoundError):
            _resolve_canonical_path(extr, ref, tmp_path)

    def test_raises_when_candidate_raw_path_missing_and_no_project(self, tmp_path: Path) -> None:
        extr = {"paths": {"canonical": "/tmp/does_not_exist_ever_xyz.json"}}
        ref = {}
        with pytest.raises(FileNotFoundError):
            _resolve_canonical_path(extr, ref, tmp_path)

    def test_uses_meta_projeto_when_ref_projeto_missing(self, tmp_path: Path) -> None:
        proj_dir = tmp_path / "benchmarks" / "projetos" / "META_PROJ"
        proj_dir.mkdir(parents=True)
        (proj_dir / "meta.json").write_text(
            json.dumps({"nome": "META PROJ", "criado_em": "2024-03"}),
            encoding="utf-8",
        )
        v1_dir = proj_dir / "v1"
        v1_dir.mkdir()
        canonical = v1_dir / "canonical.json"
        canonical.write_text(json.dumps({}), encoding="utf-8")

        extr = {}
        ref = {"meta": {"projeto": "META PROJ"}}
        result = _resolve_canonical_path(extr, ref, tmp_path)
        assert result == canonical
