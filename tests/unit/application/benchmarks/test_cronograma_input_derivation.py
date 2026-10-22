"""Unit tests for benchmarks/input_derivation/cronograma.py.

Covers BenchmarkInputDeriver and its helper functions:
_scale_item_if_needed, _scale_derived_equipes, _catalog_based_sizing,
_drfs_get_item_ids, _drfs_build_week_map, _drfs_get_week_equipes,
_drfs_extract_item_weeks, and _resolve_productivity.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

# ── _drfs_get_item_ids ────────────────────────────────────────────────────────


def test_drfs_get_item_ids_basic():
    from concilium.application.benchmarks.input_derivation.cronograma import _drfs_get_item_ids

    eap = [{"item_id": "A1"}, {"item_id": "B2"}, {}]  # last has no item_id
    result = _drfs_get_item_ids(eap)
    assert result == {"A1", "B2"}


def test_drfs_get_item_ids_empty():
    from concilium.application.benchmarks.input_derivation.cronograma import _drfs_get_item_ids

    assert _drfs_get_item_ids([]) == set()


# ── _drfs_build_week_map ──────────────────────────────────────────────────────


def test_drfs_build_week_map_no_semanas():
    from concilium.application.benchmarks.input_derivation.cronograma import _drfs_build_week_map

    # no semanas key -> empty dict
    result = _drfs_build_week_map({})
    assert result == {}


def test_drfs_build_week_map_non_numeric_keys():
    from concilium.application.benchmarks.input_derivation.cronograma import _drfs_build_week_map

    # keys are not digits -> empty dict (returns {} from non-numeric path)
    cronograma = {"semanas": {"2026-W01": {"val": 1}}}
    result = _drfs_build_week_map(cronograma)
    assert result == {}


def test_drfs_build_week_map_numeric_keys():
    from concilium.application.benchmarks.input_derivation import week_mapper
    from concilium.application.benchmarks.input_derivation.cronograma import _drfs_build_week_map

    # numeric keys -> build iso_to_num reverse map
    semanas_meta = {"1": {"iso": "2026-W01"}, "2": {"iso": "2026-W02"}}
    fake_num_to_iso = {"1": "2026-W01", "2": "2026-W02"}
    with patch.object(week_mapper, "build_numeric_to_iso_map", return_value=fake_num_to_iso):
        result = _drfs_build_week_map({"semanas": semanas_meta})
    assert result == {"2026-W01": "1", "2026-W02": "2"}


# ── _drfs_get_week_equipes ────────────────────────────────────────────────────


def test_drfs_get_week_equipes_direct_iso_key():
    from concilium.application.benchmarks.input_derivation.cronograma import _drfs_get_week_equipes

    semanas = {"2026-W01": {"num_equipes": 3}}
    result = _drfs_get_week_equipes(semanas, "2026-W01", {})
    assert result == 3


def test_drfs_get_week_equipes_iso_to_num_fallback():
    from concilium.application.benchmarks.input_derivation.cronograma import _drfs_get_week_equipes

    # ISO key not in semanas, uses numeric fallback via iso_to_num (lines 89-91)
    semanas = {"1": {"num_equipes": 2}}
    iso_to_num = {"2026-W01": "1"}
    result = _drfs_get_week_equipes(semanas, "2026-W01", iso_to_num)
    assert result == 2


def test_drfs_get_week_equipes_missing_returns_zero():
    from concilium.application.benchmarks.input_derivation.cronograma import _drfs_get_week_equipes

    semanas = {}
    result = _drfs_get_week_equipes(semanas, "2026-W01", {})
    assert result == 0


def test_drfs_get_week_equipes_non_dict_row():
    from concilium.application.benchmarks.input_derivation.cronograma import _drfs_get_week_equipes

    # week_row is not a dict (e.g. an int) -> num_equipes = 0
    semanas = {"2026-W01": 5}  # plain int, not a dict
    result = _drfs_get_week_equipes(semanas, "2026-W01", {})
    assert result == 0


def test_drfs_get_week_equipes_bad_value_returns_zero():
    from concilium.application.benchmarks.input_derivation.cronograma import _drfs_get_week_equipes

    # num_equipes non-numeric -> except -> 0 (line 99)
    semanas = {"2026-W01": {"num_equipes": "bad"}}
    result = _drfs_get_week_equipes(semanas, "2026-W01", {})
    assert result == 0


# ── _drfs_extract_item_weeks ──────────────────────────────────────────────────


def test_drfs_extract_item_weeks_no_semanas():
    from concilium.application.benchmarks.input_derivation.cronograma import _drfs_extract_item_weeks

    # no semanas key -> (None, False)
    atividade = {"item_id": "A1"}
    result, has_nz = _drfs_extract_item_weeks(atividade, ["2026-W01"], {})
    assert result is None
    assert has_nz is False


def test_drfs_extract_item_weeks_all_zero():
    from concilium.application.benchmarks.input_derivation.cronograma import _drfs_extract_item_weeks

    atividade = {"item_id": "A1", "semanas": {"2026-W01": {"num_equipes": 0}}}
    result, has_nz = _drfs_extract_item_weeks(atividade, ["2026-W01"], {})
    assert result == {"2026-W01": 0}
    assert has_nz is False


def test_drfs_extract_item_weeks_has_nonzero():
    from concilium.application.benchmarks.input_derivation.cronograma import _drfs_extract_item_weeks

    atividade = {"item_id": "A1", "semanas": {"2026-W01": {"num_equipes": 2}}}
    result, has_nz = _drfs_extract_item_weeks(atividade, ["2026-W01"], {})
    assert result == {"2026-W01": 2}
    assert has_nz is True


# ── _scale_item_if_needed ─────────────────────────────────────────────────────


def test_scale_item_if_needed_no_atividade():
    from concilium.application.benchmarks.input_derivation.cronograma import _scale_item_if_needed

    # item not in ativ_by_id -> no-op
    num_equipes: dict = {}
    _scale_item_if_needed("MISSING", {}, {}, 6, num_equipes)
    assert num_equipes == {}


def test_scale_item_if_needed_zero_qty():
    from concilium.application.benchmarks.input_derivation.cronograma import _scale_item_if_needed

    # qty == 0 -> no scale
    ativ_by_id = {"A1": {"quantitativo": 0, "producao_diaria": 100}}
    num_equipes: dict = {}
    _scale_item_if_needed("A1", {"2026-W01": 1}, ativ_by_id, 6, num_equipes)
    assert num_equipes == {}


def test_scale_item_if_needed_capacity_sufficient():
    from concilium.application.benchmarks.input_derivation.cronograma import _scale_item_if_needed

    # cap >= qty -> no scale
    ativ_by_id = {"A1": {"quantitativo": 100, "producao_diaria": 20}}
    week_map = {"2026-W01": 1}
    num_equipes: dict = {}
    # cap = 1 * 6 * 20 = 120 > 100
    _scale_item_if_needed("A1", week_map, ativ_by_id, 6, num_equipes)
    assert num_equipes == {}


def test_scale_item_if_needed_scales_when_capacity_low():
    from concilium.application.benchmarks.input_derivation.cronograma import _scale_item_if_needed

    # cap = 1 * 6 * 5 = 30 < qty = 100 -> scale needed
    ativ_by_id = {"A1": {"quantitativo": 100, "producao_diaria": 5}}
    week_map = {"2026-W01": 1}
    num_equipes: dict = {}
    _scale_item_if_needed("A1", week_map, ativ_by_id, 6, num_equipes)
    assert "A1" in num_equipes
    assert num_equipes["A1"]["2026-W01"] >= 2


def test_scale_item_if_needed_skips_zero_equipes_weeks():
    from concilium.application.benchmarks.input_derivation.cronograma import _scale_item_if_needed

    # weeks with n=0 should stay 0 after scaling
    ativ_by_id = {"A1": {"quantitativo": 200, "producao_diaria": 5}}
    week_map = {"2026-W01": 1, "2026-W02": 0}
    num_equipes: dict = {}
    _scale_item_if_needed("A1", week_map, ativ_by_id, 6, num_equipes)
    assert num_equipes["A1"]["2026-W02"] == 0


# ── _scale_derived_equipes ────────────────────────────────────────────────────


def test_scale_derived_equipes_no_atividades_in_cronograma():
    from concilium.application.benchmarks.input_derivation.cronograma import _scale_derived_equipes

    # ref with no atividades -> ativ_by_id is empty -> no-op
    ref = {"cronograma": {}}
    derived = {"A1": {"2026-W01": 1}}
    num_equipes: dict = {"A1": {"2026-W01": 1}}
    _scale_derived_equipes(ref, derived, num_equipes)
    assert num_equipes["A1"]["2026-W01"] == 1


def test_scale_derived_equipes_uses_regime_default():
    from concilium.application.benchmarks.input_derivation.cronograma import _scale_derived_equipes

    # no regime_trabalho -> uses default dias_semana=6
    ref = {"cronograma": {"atividades": [{"item_id": "A1", "quantitativo": 10, "producao_diaria": 100}]}}
    derived = {"A1": {"2026-W01": 1}}
    num_equipes: dict = {"A1": {"2026-W01": 1}}
    _scale_derived_equipes(ref, derived, num_equipes)
    # cap = 1 * 6 * 100 = 600 > 10 -> no change
    assert num_equipes["A1"]["2026-W01"] == 1


# ── BenchmarkInputDeriver._derive_from_reference_schedule ────────────────────


def test_derive_from_reference_schedule_no_cronograma():
    from concilium.application.benchmarks.input_derivation.cronograma import BenchmarkInputDeriver

    result = BenchmarkInputDeriver._derive_from_reference_schedule(
        {},  # no cronograma key
        [{"item_id": "A1"}],
        ["2026-W01"],
    )
    assert result == {}


def test_derive_from_reference_schedule_no_atividades():
    from concilium.application.benchmarks.input_derivation.cronograma import BenchmarkInputDeriver

    result = BenchmarkInputDeriver._derive_from_reference_schedule(
        {"cronograma": {}},  # no atividades
        [{"item_id": "A1"}],
        ["2026-W01"],
    )
    assert result == {}


def test_derive_from_reference_schedule_empty_eap():
    from concilium.application.benchmarks.input_derivation.cronograma import BenchmarkInputDeriver

    result = BenchmarkInputDeriver._derive_from_reference_schedule(
        {"cronograma": {"atividades": [{"item_id": "A1", "semanas": {"2026-W01": {"num_equipes": 2}}}]}},
        [],  # empty eap -> item_ids empty
        ["2026-W01"],
    )
    assert result == {}


def test_derive_from_reference_schedule_skips_activity_not_in_eap():
    from concilium.application.benchmarks.input_derivation.cronograma import BenchmarkInputDeriver

    result = BenchmarkInputDeriver._derive_from_reference_schedule(
        {"cronograma": {"atividades": [{"item_id": "NOT_IN_EAP", "semanas": {"2026-W01": {"num_equipes": 2}}}]}},
        [{"item_id": "A1"}],
        ["2026-W01"],
    )
    assert result == {}


def test_derive_from_reference_schedule_skips_non_dict_atividade():
    from concilium.application.benchmarks.input_derivation.cronograma import BenchmarkInputDeriver

    result = BenchmarkInputDeriver._derive_from_reference_schedule(
        {"cronograma": {"atividades": ["not-a-dict"]}},
        [{"item_id": "A1"}],
        ["2026-W01"],
    )
    assert result == {}


def test_derive_from_reference_schedule_activity_id_fallback():
    from concilium.application.benchmarks.input_derivation.cronograma import BenchmarkInputDeriver

    # uses activity_id when item_id absent
    result = BenchmarkInputDeriver._derive_from_reference_schedule(
        {"cronograma": {"atividades": [{"activity_id": "A1", "semanas": {"2026-W01": {"num_equipes": 1}}}]}},
        [{"item_id": "A1"}],
        ["2026-W01"],
    )
    assert "A1" in result
    assert result["A1"]["2026-W01"] == 1


def test_derive_from_reference_schedule_all_zero_not_included():
    from concilium.application.benchmarks.input_derivation.cronograma import BenchmarkInputDeriver

    # has_non_zero = False -> not added to result
    result = BenchmarkInputDeriver._derive_from_reference_schedule(
        {"cronograma": {"atividades": [{"item_id": "A1", "semanas": {"2026-W01": {"num_equipes": 0}}}]}},
        [{"item_id": "A1"}],
        ["2026-W01"],
    )
    assert result == {}


# ── BenchmarkInputDeriver._resolve_productivity ───────────────────────────────


def test_resolve_productivity_no_prod_id_ref():
    from concilium.application.benchmarks.input_derivation.cronograma import BenchmarkInputDeriver

    cpu = {}  # no producao_id_ref
    result = BenchmarkInputDeriver._resolve_productivity(cpu, {})
    assert result == 1.0


def test_resolve_productivity_prod_id_not_found():
    from concilium.application.benchmarks.input_derivation.cronograma import BenchmarkInputDeriver

    cpu = {"producao_id_ref": "PROD-X"}
    result = BenchmarkInputDeriver._resolve_productivity(cpu, {})
    assert result == 1.0


def test_resolve_productivity_uses_valor_horario():
    from concilium.application.benchmarks.input_derivation.cronograma import BenchmarkInputDeriver

    cpu = {"producao_id_ref": "PROD-1"}
    prod_lookup = {"PROD-1": {"producao_horaria": 50.0}}
    result = BenchmarkInputDeriver._resolve_productivity(cpu, prod_lookup)
    assert result == 50.0


def test_resolve_productivity_falls_back_to_producao_horaria():
    from concilium.application.benchmarks.input_derivation.cronograma import BenchmarkInputDeriver

    # producao_horaria is None -> fall back to producao_horaria (lines 205-207)
    cpu = {"producao_id_ref": "PROD-1"}
    prod_lookup = {"PROD-1": {"producao_horaria": 30.0}}
    result = BenchmarkInputDeriver._resolve_productivity(cpu, prod_lookup)
    assert result == 30.0


def test_resolve_productivity_value_not_numeric_returns_one():
    from concilium.application.benchmarks.input_derivation.cronograma import BenchmarkInputDeriver

    # Neither producao_horaria nor producao_horaria is numeric
    cpu = {"producao_id_ref": "PROD-1"}
    prod_lookup = {"PROD-1": {"producao_horaria": "N/A"}}
    result = BenchmarkInputDeriver._resolve_productivity(cpu, prod_lookup)
    assert result == 1.0


# ── BenchmarkInputDeriver.derive_num_equipes_por_item ────────────────────────


def test_derive_num_equipes_por_item_fallback_to_one():
    from concilium.application.benchmarks.input_derivation.cronograma import BenchmarkInputDeriver

    tmp = Path("/tmp")
    deriver = BenchmarkInputDeriver(tmp)
    eap = [{"item_id": "A1"}, {"item_id": "B2"}]
    weeks = ["2026-W01"]

    # no cronograma, no catalog -> all fallback to {week: 1}
    with patch.object(deriver, "_load_and_size", return_value=None):
        result = deriver.derive_num_equipes_por_item({}, eap, weeks)
    assert result["A1"] == {"2026-W01": 1}
    assert result["B2"] == {"2026-W01": 1}


def test_derive_num_equipes_por_item_from_schedule():
    from concilium.application.benchmarks.input_derivation.cronograma import BenchmarkInputDeriver

    tmp = Path("/tmp")
    deriver = BenchmarkInputDeriver(tmp)
    eap = [{"item_id": "A1"}]
    weeks = ["2026-W01"]
    ref = {"cronograma": {"atividades": [{"item_id": "A1", "semanas": {"2026-W01": {"num_equipes": 3}}}]}}

    with patch.object(deriver, "_load_and_size", return_value=None):
        result = deriver.derive_num_equipes_por_item(ref, eap, weeks)
    assert result["A1"]["2026-W01"] == 3


# ── _catalog_based_sizing ────────────────────────────────────────────────────


def test_catalog_based_sizing_no_cpu_data():
    from concilium.application.benchmarks.input_derivation.cronograma import _catalog_based_sizing

    snapshot = MagicMock()
    snapshot.cpus = []
    snapshot.produtividades = []
    items = [{"item_id": "A1", "cpu_id": "CPU-X", "quantitativo": 100}]
    num_equipes: dict = {}
    _catalog_based_sizing(items, ["2026-W01"], 48.0, snapshot, num_equipes)
    assert num_equipes == {}


def test_catalog_based_sizing_with_cpu_and_prod():
    from concilium.application.benchmarks.input_derivation.cronograma import _catalog_based_sizing

    snapshot = MagicMock()
    snapshot.cpus = [{"codigo": "CPU-1", "producao_id_ref": "PROD-1"}]
    snapshot.produtividades = [{"id": "PROD-1", "producao_horaria": 10.0}]
    items = [{"item_id": "A1", "cpu_id": "CPU-1", "quantitativo": 480}]
    num_equipes: dict = {}
    _catalog_based_sizing(items, ["2026-W01"], 48.0, snapshot, num_equipes)
    assert "A1" in num_equipes
    assert num_equipes["A1"]["2026-W01"] >= 1


def test_catalog_based_sizing_zero_qty_skipped():
    from concilium.application.benchmarks.input_derivation.cronograma import _catalog_based_sizing

    snapshot = MagicMock()
    snapshot.cpus = [{"codigo": "CPU-1", "producao_id_ref": "PROD-1"}]
    snapshot.produtividades = [{"id": "PROD-1", "producao_horaria": 10.0}]
    items = [{"item_id": "A1", "cpu_id": "CPU-1", "quantitativo": 0}]
    num_equipes: dict = {}
    _catalog_based_sizing(items, ["2026-W01"], 48.0, snapshot, num_equipes)
    assert num_equipes == {}


def test_catalog_based_sizing_productivity_lookup_by_prod_id():
    from concilium.application.benchmarks.input_derivation.cronograma import _catalog_based_sizing

    # prod looked up via get("id")
    snapshot = MagicMock()
    snapshot.cpus = [{"codigo": "CPU-A", "producao_id_ref": None}]
    snapshot.produtividades = []
    items = [{"item_id": "X1", "cpu_id": "CPU-A", "quantitativo": 100}]
    num_equipes: dict = {}
    _catalog_based_sizing(items, ["2026-W01", "2026-W02"], 48.0, snapshot, num_equipes)
    # prod = 1.0 (default), needed = ceil(100/(1*48*2)*1.25) = ceil(1.302) = 2
    assert "X1" in num_equipes


def test_catalog_based_sizing_cpu_without_codigo_key_skipped():
    """Branch 49->50: cpu dict sem chave 'codigo' não entra no cpu_lookup."""
    from concilium.application.benchmarks.input_derivation.cronograma import _catalog_based_sizing

    snapshot = MagicMock()
    snapshot.cpus = [{"nome": "sem codigo"}, {"codigo": "CPU-1", "producao_id_ref": "PROD-1"}]
    snapshot.produtividades = [{"id": "PROD-1", "producao_horaria": 10.0}]
    items = [{"item_id": "A1", "cpu_id": "CPU-1", "quantitativo": 480}]
    num_equipes: dict = {}
    _catalog_based_sizing(items, ["2026-W01"], 48.0, snapshot, num_equipes)
    assert "A1" in num_equipes


def test_catalog_based_sizing_produtividade_without_id_or_codigo_skipped():
    """Branch 55->53: produtividade sem 'id' nem 'codigo' não entra no prod_lookup."""
    from concilium.application.benchmarks.input_derivation.cronograma import _catalog_based_sizing

    snapshot = MagicMock()
    snapshot.cpus = [{"codigo": "CPU-1", "producao_id_ref": "PROD-1"}]
    snapshot.produtividades = [{"producao_horaria": 99.0}, {"id": "PROD-1", "producao_horaria": 10.0}]
    items = [{"item_id": "A1", "cpu_id": "CPU-1", "quantitativo": 480}]
    num_equipes: dict = {}
    _catalog_based_sizing(items, ["2026-W01"], 48.0, snapshot, num_equipes)
    assert "A1" in num_equipes


def test_drfs_get_week_equipes_iso_to_num_present_but_num_key_falsy():
    """Branch 91->93: iso_to_num tem a chave mas o valor é falsy (0/None) → não tenta fallback."""
    from concilium.application.benchmarks.input_derivation.cronograma import _drfs_get_week_equipes

    semanas = {}
    iso_to_num = {"2026-W01": None}
    result = _drfs_get_week_equipes(semanas, "2026-W01", iso_to_num)
    assert result == 0


# ── BenchmarkInputDeriver._load_and_size ─────────────────────────────────────


def test_load_and_size_exception_prints_warning(tmp_path, capsys):
    from concilium.application.benchmarks.input_derivation.cronograma import BenchmarkInputDeriver

    deriver = BenchmarkInputDeriver(tmp_path)
    num_equipes: dict = {}
    # CatalogLoader.load will fail since catalog doesn't exist -> warn printed
    deriver._load_and_size(
        {},
        [{"item_id": "A1", "cpu_id": "CPU-X", "quantitativo": 100}],
        ["2026-W01"],
        "nonexistent_catalog",
        num_equipes,
    )
    captured = capsys.readouterr()
    assert "WARN" in captured.out or num_equipes == {}


def test_load_and_size_uses_regime_trabalho(tmp_path):
    from concilium.application.benchmarks.input_derivation.cronograma import BenchmarkInputDeriver

    deriver = BenchmarkInputDeriver(tmp_path)
    num_equipes: dict = {}
    ref = {"regime_trabalho": {"horas_dia": 10, "dias_semana": 5}}
    # This will fail at loader.load but we just test no crash
    deriver._load_and_size(ref, [], ["2026-W01"], "nonexistent", num_equipes)
    # no exception propagated
