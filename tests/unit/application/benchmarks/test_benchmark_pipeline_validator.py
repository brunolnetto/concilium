"""Tests for pipeline_validator.py — targets 80%+ coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.concilium.application.benchmarks.analysis.pipeline_validator import (
    _bet_build_indiretos,
    _bet_extract_resultado,
    _bet_sum_equipes_custo,
    _build_etapas_from_canonical,
    _latest_project_by_name,
    _lp_check_dir,
    _lp_matches_name,
    _sum_subtotal,
    _vpi_build_checkpoints,
    _vpi_build_output,
    _vpi_load_etapas,
    _vpi_partition_ref,
    validate_pipeline_integrity,
)

# ---------------------------------------------------------------------------
# _lp_matches_name
# ---------------------------------------------------------------------------


class TestLpMatchesName:
    def test_exact_match(self):
        assert _lp_matches_name("AGIS", "AGIS") is True

    def test_project_name_subset_of_meta(self):
        # "AGIS" is in "PROJETO AGIS 2024"
        assert _lp_matches_name("PROJETO AGIS 2024", "AGIS") is True

    def test_meta_subset_of_project_name(self):
        # "AGIS" is in "AGIS FULL"
        assert _lp_matches_name("AGIS", "AGIS FULL") is True

    def test_no_match(self):
        assert _lp_matches_name("OUTRO", "AGIS") is False

    def test_case_insensitive_match(self):
        assert _lp_matches_name("agis", "AGIS") is True

    def test_empty_strings(self):
        # empty meta name subset of any project name
        assert _lp_matches_name("", "AGIS") is True

    def test_completely_different(self):
        assert _lp_matches_name("XPTO", "ZULU") is False


# ---------------------------------------------------------------------------
# _lp_check_dir
# ---------------------------------------------------------------------------


class TestLpCheckDir:
    def test_non_directory_returns_none(self, tmp_path):
        file_path = tmp_path / "file.txt"
        file_path.write_text("hello")
        assert _lp_check_dir(file_path, "AGIS") is None

    def test_missing_meta_json_returns_none(self, tmp_path):
        d = tmp_path / "proj"
        d.mkdir()
        # no meta.json
        assert _lp_check_dir(d, "AGIS") is None

    def test_invalid_meta_json_returns_none(self, tmp_path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / "meta.json").write_text("not json")
        assert _lp_check_dir(d, "AGIS") is None

    def test_name_mismatch_returns_none(self, tmp_path):
        d = tmp_path / "proj"
        d.mkdir()
        meta = {"nome": "OUTRO", "criado_em": "2024-01-01T00:00:00"}
        (d / "meta.json").write_text(json.dumps(meta))
        assert _lp_check_dir(d, "AGIS") is None

    def test_happy_path_returns_tuple(self, tmp_path):
        d = tmp_path / "proj_agis"
        d.mkdir()
        meta = {"nome": "AGIS", "criado_em": "2024-06-01T00:00:00"}
        (d / "meta.json").write_text(json.dumps(meta))
        result = _lp_check_dir(d, "AGIS")
        assert result is not None
        criado_em, path = result
        assert criado_em == "2024-06-01T00:00:00"
        assert path == d

    def test_missing_criado_em_returns_empty_string(self, tmp_path):
        d = tmp_path / "proj_agis"
        d.mkdir()
        meta = {"nome": "AGIS"}
        (d / "meta.json").write_text(json.dumps(meta))
        result = _lp_check_dir(d, "AGIS")
        assert result is not None
        criado_em, _ = result
        assert criado_em == ""

    def test_none_nome_treated_as_empty(self, tmp_path):
        d = tmp_path / "proj_agis"
        d.mkdir()
        meta = {"nome": None, "criado_em": "2024-01-01"}
        (d / "meta.json").write_text(json.dumps(meta))
        # empty string matches "AGIS FULL" (empty is subset), but not when project_name
        # only contains AGIS and nome is empty: "".upper() in "AGIS".upper() → True
        result = _lp_check_dir(d, "AGIS")
        assert result is not None


# ---------------------------------------------------------------------------
# _latest_project_by_name
# ---------------------------------------------------------------------------


class TestLatestProjectByName:
    def test_no_matching_dirs_returns_none(self, tmp_path):
        projects = tmp_path / "projects"
        projects.mkdir()
        d = projects / "other"
        d.mkdir()
        (d / "meta.json").write_text(json.dumps({"nome": "OUTRO"}))
        assert _latest_project_by_name("AGIS", projects) is None

    def test_single_match(self, tmp_path):
        projects = tmp_path / "projects"
        projects.mkdir()
        d = projects / "agis_001"
        d.mkdir()
        (d / "meta.json").write_text(json.dumps({"nome": "AGIS", "criado_em": "2024-01-01"}))
        result = _latest_project_by_name("AGIS", projects)
        assert result == d

    def test_multiple_matches_picks_highest_criado_em(self, tmp_path):
        projects = tmp_path / "projects"
        projects.mkdir()
        for ts, name in [("2023-01-01", "agis_old"), ("2024-06-01", "agis_new"), ("2022-01-01", "agis_oldest")]:
            d = projects / name
            d.mkdir()
            (d / "meta.json").write_text(json.dumps({"nome": "AGIS", "criado_em": ts}))
        result = _latest_project_by_name("AGIS", projects)
        assert result == projects / "agis_new"

    def test_skips_non_directories(self, tmp_path):
        projects = tmp_path / "projects"
        projects.mkdir()
        # a file in the projects root
        (projects / "readme.txt").write_text("hi")
        d = projects / "agis"
        d.mkdir()
        (d / "meta.json").write_text(json.dumps({"nome": "AGIS", "criado_em": "2024-01-01"}))
        result = _latest_project_by_name("AGIS", projects)
        assert result == d


# ---------------------------------------------------------------------------
# _sum_subtotal
# ---------------------------------------------------------------------------


class TestSumSubtotal:
    def test_empty_list(self):
        assert _sum_subtotal([], "sem_bdi") == 0.0

    def test_normal_accumulation(self):
        itens = [
            {"subtotal": {"sem_bdi": {"total": 100.0}}},
            {"subtotal": {"sem_bdi": {"total": 50.5}}},
        ]
        assert _sum_subtotal(itens, "sem_bdi") == 150.5

    def test_missing_subtotal_key(self):
        itens = [{"other": 1}, {"subtotal": {"com_bdi": {"total": 10.0}}}]
        assert _sum_subtotal(itens, "sem_bdi") == 0.0

    def test_malformed_total_skipped(self):
        itens = [
            {"subtotal": {"sem_bdi": {"total": "not_a_number"}}},
            {"subtotal": {"sem_bdi": {"total": 20.0}}},
        ]
        # "not_a_number" raises, so only 20.0 contributes
        assert _sum_subtotal(itens, "sem_bdi") == 20.0

    def test_none_total_treated_as_zero(self):
        itens = [{"subtotal": {"sem_bdi": {"total": None}}}]
        assert _sum_subtotal(itens, "sem_bdi") == 0.0

    def test_com_bdi_branch(self):
        itens = [{"subtotal": {"com_bdi": {"total": 200.0}}}]
        assert _sum_subtotal(itens, "com_bdi") == 200.0

    def test_rounds_to_two_decimal_places(self):
        itens = [{"subtotal": {"sem_bdi": {"total": 1.0 / 3}}}]
        result = _sum_subtotal(itens, "sem_bdi")
        assert result == round(1.0 / 3, 2)


# ---------------------------------------------------------------------------
# _bet_sum_equipes_custo
# ---------------------------------------------------------------------------


class TestBetSumEquipesCusto:
    def test_empty_list(self):
        assert _bet_sum_equipes_custo([]) == 0.0

    def test_normal_sum(self):
        equipes = [{"custo_total": 1000.0}, {"custo_total": 500.0}]
        assert _bet_sum_equipes_custo(equipes) == 1500.0

    def test_invalid_custo_total_skipped(self):
        equipes = [{"custo_total": "bad"}, {"custo_total": 200.0}]
        assert _bet_sum_equipes_custo(equipes) == 200.0

    def test_none_custo_total_treated_as_zero(self):
        equipes = [{"custo_total": None}]
        assert _bet_sum_equipes_custo(equipes) == 0.0

    def test_missing_key_treated_as_zero(self):
        equipes = [{"other": 99}]
        assert _bet_sum_equipes_custo(equipes) == 0.0


# ---------------------------------------------------------------------------
# _bet_build_indiretos
# ---------------------------------------------------------------------------


class TestBetBuildIndiretos:
    def test_empty_list(self):
        total, por_cat = _bet_build_indiretos([])
        assert total == 0.0
        assert por_cat == {}

    def test_skips_items_without_categoria(self):
        indiretos = [{"custo_total": 100.0}]  # no categoria
        total, por_cat = _bet_build_indiretos(indiretos)
        assert total == 0.0
        assert por_cat == {}

    def test_aggregates_by_category(self):
        indiretos = [
            {"categoria": "A", "custo_total": 100.0},
            {"categoria": "B", "custo_total": 50.0},
            {"categoria": "A", "custo_total": 75.0},
        ]
        total, por_cat = _bet_build_indiretos(indiretos)
        assert total == 225.0
        assert por_cat == {"A": 175.0, "B": 50.0}

    def test_correct_total(self):
        indiretos = [
            {"categoria": "X", "custo_total": 10.0},
            {"categoria": "Y", "custo_total": 20.0},
        ]
        total, _ = _bet_build_indiretos(indiretos)
        assert total == 30.0

    def test_none_custo_total_treated_as_zero(self):
        indiretos = [{"categoria": "A", "custo_total": None}]
        total, por_cat = _bet_build_indiretos(indiretos)
        assert total == 0.0
        assert por_cat == {"A": 0.0}


# ---------------------------------------------------------------------------
# _bet_extract_resultado
# ---------------------------------------------------------------------------


class TestBetExtractResultado:
    def test_missing_keys_default_to_none(self):
        resultado = {}
        consolidacao = _bet_extract_resultado(resultado)
        assert consolidacao["venda"]["total_sem_bdi"] is None
        assert consolidacao["venda"]["total_com_bdi"] is None
        assert consolidacao["venda"]["total_custo_plus_catalogo"] is None
        assert consolidacao["venda"]["total_custo_plus"] is None
        assert consolidacao["custo"]["total"] is None
        assert consolidacao["custo"]["direto_equipes"] is None
        assert consolidacao["margem_pct"] is None

    def test_full_dict_produced_correctly(self):
        resultado = {
            "venda": {
                "total_sem_bdi": 1000.0,
                "total_com_bdi": 1200.0,
                "total_custo_plus_catalogo": 1150.0,
                "total_custo_plus": 1100.0,
            },
            "custo": {"total": 800.0, "direto_equipes": 600.0},
            "margem_pct": 20.0,
        }
        consolidacao = _bet_extract_resultado(resultado)
        assert consolidacao["venda"]["total_sem_bdi"] == 1000.0
        assert consolidacao["venda"]["total_com_bdi"] == 1200.0
        assert consolidacao["venda"]["total_custo_plus_catalogo"] == 1150.0
        assert consolidacao["venda"]["total_custo_plus"] == 1100.0
        assert consolidacao["custo"]["total"] == 800.0
        assert consolidacao["custo"]["direto_equipes"] == 600.0
        assert consolidacao["margem_pct"] == 20.0

    def test_returns_dict_not_tuple(self):
        # Function signature says it returns tuple but actually returns dict
        resultado = {"venda": {"total_sem_bdi": 500.0}, "custo": {}, "margem_pct": 10.0}
        result = _bet_extract_resultado(resultado)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# _build_etapas_from_canonical
# ---------------------------------------------------------------------------


class TestBuildEtapasFromCanonical:
    def test_empty_canonical(self):
        etapas = _build_etapas_from_canonical({})
        assert etapas["03_equipes_e_alocacao"]["agregados"]["custo_direto_total_equipes"] == 0.0
        assert etapas["04_planejamento_bdi"]["itens_planejamento"] == 0
        assert etapas["05_indiretos"]["total_sem_bdi"] == 0.0
        assert etapas["05_indiretos"]["por_categoria"] == {}

    def test_wires_all_helpers(self):
        canonical = {
            "equipes_diretas": [
                {"item_id": "eq1", "custo_total": 1000.0},
                {"item_id": "eq2", "custo_total": 500.0},
            ],
            "planejamento": [
                {"subtotal": {"sem_bdi": {"total": 100.0}, "com_bdi": {"total": 120.0}}},
                {"subtotal": {"sem_bdi": {"total": 200.0}, "com_bdi": {"total": 240.0}}},
            ],
            "indiretos": [
                {"categoria": "BDI", "custo_total": 300.0},
                {"categoria": "ADM", "custo_total": 100.0},
            ],
            "resultado": {
                "venda": {"total_sem_bdi": 300.0, "total_com_bdi": 660.0},
                "custo": {"total": 1900.0, "direto_equipes": 1500.0},
                "margem_pct": 5.0,
            },
        }
        etapas = _build_etapas_from_canonical(canonical)
        assert etapas["03_equipes_e_alocacao"]["agregados"]["custo_direto_total_equipes"] == 1500.0
        assert len(etapas["03_equipes_e_alocacao"]["equipes"]) == 2
        assert etapas["04_planejamento_bdi"]["subtotal_sem_bdi_total"] == 300.0
        assert etapas["04_planejamento_bdi"]["subtotal_com_bdi_total"] == 360.0
        assert etapas["04_planejamento_bdi"]["itens_planejamento"] == 2
        assert etapas["05_indiretos"]["total_sem_bdi"] == 400.0
        assert "BDI" in etapas["05_indiretos"]["por_categoria"]
        assert etapas["06_consolidacao"]["resultado"]["margem_pct"] == 5.0

    def test_counts_planejamento_itens(self):
        canonical = {"planejamento": [{}, {}, {}]}
        etapas = _build_etapas_from_canonical(canonical)
        assert etapas["04_planejamento_bdi"]["itens_planejamento"] == 3


# ---------------------------------------------------------------------------
# _vpi_load_etapas
# ---------------------------------------------------------------------------


class TestVpiLoadEtapas:
    def test_loads_from_extracao_intermediarios_when_present(self, tmp_path):
        data_dir = tmp_path / "data" / "PROJ"
        data_dir.mkdir(parents=True)
        etapas_data = {
            "etapas": {
                "03_equipes_e_alocacao": {"agregados": {}, "equipes": []},
                "04_planejamento_bdi": {"subtotal_sem_bdi_total": 999.0, "itens_planejamento": 5},
            }
        }
        (data_dir / "extracao_intermediarios.json").write_text(json.dumps(etapas_data))
        ref = {"projeto": "PROJ"}
        result = _vpi_load_etapas(data_dir, ref, tmp_path, "PROJ")
        assert result["04_planejamento_bdi"]["subtotal_sem_bdi_total"] == 999.0

    def test_falls_back_to_benchmarks_projetos(self, tmp_path):
        data_dir = tmp_path / "data" / "PROJ"
        data_dir.mkdir(parents=True)
        # no extracao_intermediarios.json
        proj_dir = tmp_path / "benchmarks" / "projetos" / "proj_001"
        proj_dir.mkdir(parents=True)
        (proj_dir / "meta.json").write_text(json.dumps({"nome": "MYPROJETO", "criado_em": "2024-01-01"}))
        canonical = {
            "equipes_diretas": [],
            "planejamento": [],
            "indiretos": [],
            "resultado": {},
        }
        v1 = proj_dir / "v1"
        v1.mkdir()
        (v1 / "canonical.json").write_text(json.dumps(canonical))
        ref = {"projeto": "MYPROJETO"}
        result = _vpi_load_etapas(data_dir, ref, tmp_path, "MYSLUG")
        assert "03_equipes_e_alocacao" in result

    def test_falls_back_to_projetos_dir(self, tmp_path):
        data_dir = tmp_path / "data" / "PROJ"
        data_dir.mkdir(parents=True)
        # no extracao_intermediarios.json
        # no benchmarks/projetos match
        bench_proj = tmp_path / "benchmarks" / "projetos"
        bench_proj.mkdir(parents=True)
        # put project in projetos/ instead
        proj_dir = tmp_path / "projetos" / "proj_002"
        proj_dir.mkdir(parents=True)
        (proj_dir / "meta.json").write_text(json.dumps({"nome": "FALLBACK", "criado_em": "2024-05-01"}))
        canonical = {"equipes_diretas": [], "planejamento": [], "indiretos": [], "resultado": {}}
        v1 = proj_dir / "v1"
        v1.mkdir()
        (v1 / "canonical.json").write_text(json.dumps(canonical))
        ref = {"projeto": "FALLBACK"}
        result = _vpi_load_etapas(data_dir, ref, tmp_path, "FALLBACK")
        assert "03_equipes_e_alocacao" in result

    def test_raises_file_not_found_when_project_missing(self, tmp_path):
        data_dir = tmp_path / "data" / "PROJ"
        data_dir.mkdir(parents=True)
        bench_proj = tmp_path / "benchmarks" / "projetos"
        bench_proj.mkdir(parents=True)
        projetos = tmp_path / "projetos"
        projetos.mkdir(parents=True)
        ref = {"projeto": "NOTEXIST"}
        with pytest.raises(FileNotFoundError, match="Projeto não encontrado"):
            _vpi_load_etapas(data_dir, ref, tmp_path, "NOTEXIST")

    def test_uses_slug_when_projeto_missing_from_ref(self, tmp_path):
        data_dir = tmp_path / "data" / "MYSLUG"
        data_dir.mkdir(parents=True)
        bench_proj = tmp_path / "benchmarks" / "projetos"
        bench_proj.mkdir(parents=True)
        projetos = tmp_path / "projetos"
        projetos.mkdir(parents=True)
        ref = {}  # no projeto key
        with pytest.raises(FileNotFoundError):
            _vpi_load_etapas(data_dir, ref, tmp_path, "MYSLUG")


# ---------------------------------------------------------------------------
# _vpi_partition_ref
# ---------------------------------------------------------------------------


class TestVpiPartitionRef:
    def test_empty_list(self):
        com_dados, zerados = _vpi_partition_ref([])
        assert com_dados == []
        assert zerados == []

    def test_subtotal_sem_bdi_total_positive(self):
        items = [{"item_id": "A", "subtotal_sem_bdi": {"total": 100.0}}]
        com_dados, zerados = _vpi_partition_ref(items)
        assert len(com_dados) == 1
        assert len(zerados) == 0

    def test_subtotal_sem_bdi_total_zero(self):
        items = [{"item_id": "B", "subtotal_sem_bdi": {"total": 0.0}}]
        com_dados, zerados = _vpi_partition_ref(items)
        assert len(com_dados) == 0
        assert len(zerados) == 1

    def test_none_total_goes_to_zerados(self):
        items = [{"item_id": "C", "subtotal_sem_bdi": {"total": None}}]
        com_dados, zerados = _vpi_partition_ref(items)
        assert len(zerados) == 1

    def test_nested_subtotal_shape(self):
        # Falls back to subtotal.sem_bdi.total shape
        items = [{"item_id": "D", "subtotal": {"sem_bdi": {"total": 50.0}}}]
        com_dados, zerados = _vpi_partition_ref(items)
        assert len(com_dados) == 1

    def test_nested_subtotal_zero(self):
        items = [{"item_id": "E", "subtotal": {"sem_bdi": {"total": 0}}}]
        com_dados, zerados = _vpi_partition_ref(items)
        assert len(zerados) == 1

    def test_mixed_partition(self):
        items = [
            {"item_id": "X", "subtotal_sem_bdi": {"total": 200.0}},
            {"item_id": "Y", "subtotal_sem_bdi": {"total": 0.0}},
            {"item_id": "Z", "subtotal": {"sem_bdi": {"total": 100.0}}},
        ]
        com_dados, zerados = _vpi_partition_ref(items)
        assert len(com_dados) == 2
        assert len(zerados) == 1
        assert com_dados[0]["item_id"] == "X"
        assert com_dados[1]["item_id"] == "Z"


# ---------------------------------------------------------------------------
# _vpi_build_checkpoints
# ---------------------------------------------------------------------------


class TestVpiBuildCheckpoints:
    def _make_e4(self, sem_bdi=0.0, com_bdi=0.0):
        return {"subtotal_sem_bdi_total": sem_bdi, "subtotal_com_bdi_total": com_bdi}

    def _make_e6(self, sem_bdi=0.0, com_bdi=0.0, catalogo=0.0):
        return {
            "resultado": {
                "venda": {
                    "total_sem_bdi": sem_bdi,
                    "total_com_bdi": com_bdi,
                    "total_custo_plus_catalogo": catalogo,
                }
            }
        }

    def _e6_flat(self, sem_bdi=0.0, com_bdi=0.0, catalogo=0.0):
        return {
            "venda": {
                "total_sem_bdi": sem_bdi,
                "total_com_bdi": com_bdi,
                "total_custo_plus_catalogo": catalogo,
            }
        }

    def test_checkpoint_ok_when_delta_below_threshold(self):
        e4 = self._make_e4(sem_bdi=100.0, com_bdi=120.0)
        e6 = self._e6_flat(sem_bdi=100.0, com_bdi=120.0, catalogo=120.0)
        checkpoints = _vpi_build_checkpoints(e4, e6)
        assert checkpoints[0]["status"] == "OK"
        assert checkpoints[1]["status"] == "OK"

    def test_checkpoint_divergente_when_delta_at_or_above_threshold(self):
        e4 = self._make_e4(sem_bdi=100.0, com_bdi=100.0)
        # delta = 200 - 100 = 100 >= 0.05
        e6 = self._e6_flat(sem_bdi=200.0, com_bdi=100.0, catalogo=200.0)
        checkpoints = _vpi_build_checkpoints(e4, e6)
        assert checkpoints[0]["status"] == "DIVERGENTE"

    def test_second_checkpoint_divergente(self):
        e4 = self._make_e4(sem_bdi=100.0, com_bdi=100.0)
        # com_bdi != catalogo => divergente for checkpoint 2
        e6 = self._e6_flat(sem_bdi=100.0, com_bdi=150.0, catalogo=100.0)
        checkpoints = _vpi_build_checkpoints(e4, e6)
        assert checkpoints[1]["status"] == "DIVERGENTE"

    def test_returns_two_checkpoints(self):
        e4 = self._make_e4()
        e6 = self._e6_flat()
        checkpoints = _vpi_build_checkpoints(e4, e6)
        assert len(checkpoints) == 2

    def test_delta_fields_calculated(self):
        e4 = self._make_e4(sem_bdi=100.0, com_bdi=120.0)
        e6 = self._e6_flat(sem_bdi=110.0, com_bdi=120.0, catalogo=120.0)
        checkpoints = _vpi_build_checkpoints(e4, e6)
        assert checkpoints[0]["delta"] == 10.0

    def test_none_values_treated_as_zero(self):
        e4 = {"subtotal_sem_bdi_total": None, "subtotal_com_bdi_total": None}
        e6 = {"venda": {"total_sem_bdi": None, "total_com_bdi": None, "total_custo_plus_catalogo": None}}
        checkpoints = _vpi_build_checkpoints(e4, e6)
        assert checkpoints[0]["status"] == "OK"


# ---------------------------------------------------------------------------
# _vpi_build_output
# ---------------------------------------------------------------------------


class TestVpiBuildOutput:
    def _make_inputs(self):
        ref = {"projeto": "TEST", "slug": "TST"}
        slug = "TST"
        ref_planej = [{"item_id": "A"}, {"item_id": "B"}]
        ref_com_dados = [{"item_id": "A"}]
        ref_zerados = [{"item_id": "B"}]
        e3 = {"agregados": {"custo_direto_total_equipes": 1000.0}, "equipes": [{"item_id": "eq1"}]}
        e4 = {"subtotal_sem_bdi_total": 500.0, "subtotal_com_bdi_total": 600.0, "itens_planejamento": 2}
        e5 = {"total_sem_bdi": 100.0, "por_categoria": {"BDI": 100.0}}
        e6 = {"venda": {"total_sem_bdi": 500.0, "total_com_bdi": 700.0}, "custo": {"total": 900.0}, "margem_pct": 5.0}
        checkpoints = [{"checkpoint": "04→06", "status": "OK"}]
        return ref, slug, ref_planej, ref_com_dados, ref_zerados, e3, e4, e5, e6, checkpoints

    def test_output_structure(self):
        ref, slug, ref_planej, ref_com_dados, ref_zerados, e3, e4, e5, e6, checkpoints = self._make_inputs()
        out = _vpi_build_output(ref, slug, ref_planej, ref_com_dados, ref_zerados, e3, e4, e5, e6, checkpoints)
        assert out["projeto"] == "TEST"
        assert out["slug"] == "TST"
        assert out["analise_base_referencia"]["total_atividades"] == 2
        assert out["analise_base_referencia"]["atividades_com_dados"] == 1
        assert out["analise_base_referencia"]["atividades_zeradas"] == 1
        assert "A" in out["analise_base_referencia"]["atividades_com_dados_ids"]
        assert "B" in out["analise_base_referencia"]["atividades_zeradas_ids"]

    def test_pipeline_integrity_section(self):
        ref, slug, ref_planej, ref_com_dados, ref_zerados, e3, e4, e5, e6, checkpoints = self._make_inputs()
        out = _vpi_build_output(ref, slug, ref_planej, ref_com_dados, ref_zerados, e3, e4, e5, e6, checkpoints)
        pi = out["integridade_pipeline_concilium"]
        assert pi["03_equipes"]["custo_direto_total"] == 1000.0
        assert pi["03_equipes"]["equipes_count"] == 1
        assert pi["04_planejamento"]["subtotal_sem_bdi_total"] == 500.0
        assert pi["05_indiretos"]["total_sem_bdi"] == 100.0
        assert "BDI" in pi["05_indiretos"]["categorias"]
        assert pi["06_consolidacao"]["venda_total_sem_bdi"] == 500.0
        assert pi["06_consolidacao"]["custo_total"] == 900.0
        assert pi["06_consolidacao"]["margem_pct"] == 5.0

    def test_validacoes_fechamento_included(self):
        ref, slug, ref_planej, ref_com_dados, ref_zerados, e3, e4, e5, e6, checkpoints = self._make_inputs()
        out = _vpi_build_output(ref, slug, ref_planej, ref_com_dados, ref_zerados, e3, e4, e5, e6, checkpoints)
        assert out["validacoes_fechamento"] == checkpoints

    def test_slug_fallback_from_meta(self):
        ref = {"projeto": "TEST", "meta": {"slug": "META_SLUG"}}
        slug = "RAW_SLUG"
        ref_planej, ref_com_dados, ref_zerados = [], [], []
        e3 = {"agregados": {}, "equipes": []}
        e4 = {"subtotal_sem_bdi_total": 0, "subtotal_com_bdi_total": 0, "itens_planejamento": 0}
        e5 = {"total_sem_bdi": 0, "por_categoria": {}}
        e6 = {"venda": {}, "custo": {}, "margem_pct": None}
        checkpoints = []
        out = _vpi_build_output(ref, slug, ref_planej, ref_com_dados, ref_zerados, e3, e4, e5, e6, checkpoints)
        # ref has slug=None (not present), so falls to meta.slug
        assert out["slug"] == "META_SLUG"


# ---------------------------------------------------------------------------
# validate_pipeline_integrity — integration via tmp_path
# ---------------------------------------------------------------------------


class TestValidatePipelineIntegrity:
    def _write_json(self, path: Path, data: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def _make_referencia(self, projeto="MYPROJ", slug="MYSLUG"):
        return {
            "projeto": projeto,
            "slug": slug,
            "planejamento_detalhado": [
                {"item_id": "item_01", "subtotal_sem_bdi": {"total": 500.0}},
                {"item_id": "item_02", "subtotal_sem_bdi": {"total": 0.0}},
            ],
        }

    def _make_extracao(self):
        return {
            "etapas": {
                "03_equipes_e_alocacao": {
                    "agregados": {"custo_direto_total_equipes": 1000.0},
                    "equipes": [{"item_id": "eq1", "custo_total": 1000.0}],
                },
                "04_planejamento_bdi": {
                    "subtotal_sem_bdi_total": 500.0,
                    "subtotal_com_bdi_total": 600.0,
                    "itens_planejamento": 2,
                },
                "05_indiretos": {"total_sem_bdi": 200.0, "por_categoria": {"BDI": 200.0}},
                "06_consolidacao": {
                    "resultado": {
                        "venda": {
                            "total_sem_bdi": 500.0,
                            "total_com_bdi": 800.0,
                            "total_custo_plus_catalogo": 800.0,
                        },
                        "custo": {"total": 1200.0, "direto_equipes": 1000.0},
                        "margem_pct": 33.3,
                    }
                },
            }
        }

    def test_end_to_end_with_extracao_intermediarios(self, tmp_path):
        slug = "MYSLUG"
        data_dir = tmp_path / "benchmarks" / "data" / slug
        self._write_json(data_dir / "referencia.json", self._make_referencia())
        self._write_json(data_dir / "extracao_intermediarios.json", self._make_extracao())
        result = validate_pipeline_integrity(slug, root=tmp_path)
        assert result["projeto"] == "MYPROJ"
        assert result["slug"] == "MYSLUG"
        assert result["analise_base_referencia"]["total_atividades"] == 2
        assert result["analise_base_referencia"]["atividades_com_dados"] == 1
        assert result["analise_base_referencia"]["atividades_zeradas"] == 1
        assert "validacoes_fechamento" in result
        assert len(result["validacoes_fechamento"]) == 2

    def test_end_to_end_falling_back_to_canonical(self, tmp_path):
        slug = "CANONICAL"
        data_dir = tmp_path / "benchmarks" / "data" / slug
        self._write_json(data_dir / "referencia.json", self._make_referencia(projeto="MYCANON", slug=slug))
        # no extracao_intermediarios.json — must find canonical
        proj_dir = tmp_path / "benchmarks" / "projetos" / "mycanon_001"
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "meta.json").write_text(json.dumps({"nome": "MYCANON", "criado_em": "2024-01-01"}))
        canonical = {
            "equipes_diretas": [{"item_id": "eq1", "custo_total": 500.0}],
            "planejamento": [{"subtotal": {"sem_bdi": {"total": 300.0}, "com_bdi": {"total": 360.0}}}],
            "indiretos": [{"categoria": "BDI", "custo_total": 100.0}],
            "resultado": {
                "venda": {
                    "total_sem_bdi": 300.0,
                    "total_com_bdi": 460.0,
                    "total_custo_plus_catalogo": 460.0,
                },
                "custo": {"total": 700.0, "direto_equipes": 500.0},
                "margem_pct": 15.0,
            },
        }
        v1 = proj_dir / "v1"
        v1.mkdir()
        (v1 / "canonical.json").write_text(json.dumps(canonical))
        result = validate_pipeline_integrity(slug, root=tmp_path)
        assert result["projeto"] == "MYCANON"
        pi = result["integridade_pipeline_concilium"]
        assert pi["03_equipes"]["custo_direto_total"] == 500.0
        assert pi["04_planejamento"]["itens_planejamento"] == 1

    def test_file_not_found_propagated_when_project_missing(self, tmp_path):
        slug = "GHOST"
        data_dir = tmp_path / "benchmarks" / "data" / slug
        ref = self._make_referencia(projeto="GHOST_PROJ", slug=slug)
        self._write_json(data_dir / "referencia.json", ref)
        # ensure lookup dirs exist but are empty
        (tmp_path / "benchmarks" / "projetos").mkdir(parents=True, exist_ok=True)
        (tmp_path / "projetos").mkdir(parents=True, exist_ok=True)
        with pytest.raises(FileNotFoundError):
            validate_pipeline_integrity(slug, root=tmp_path)

    def test_planejamento_from_ref_planejamento_itens(self, tmp_path):
        """Test fallback ref structure: ref.planejamento.itens instead of planejamento_detalhado."""
        slug = "ALTREF"
        data_dir = tmp_path / "benchmarks" / "data" / slug
        ref = {
            "projeto": "ALTREF",
            "slug": slug,
            "planejamento": {
                "itens": [
                    {"item_id": "x1", "subtotal_sem_bdi": {"total": 100.0}},
                ]
            },
        }
        self._write_json(data_dir / "referencia.json", ref)
        extracao = self._make_extracao()
        self._write_json(data_dir / "extracao_intermediarios.json", extracao)
        result = validate_pipeline_integrity(slug, root=tmp_path)
        assert result["analise_base_referencia"]["total_atividades"] == 1

    def test_checkpoints_ok_when_values_match(self, tmp_path):
        slug = "BALANCED"
        data_dir = tmp_path / "benchmarks" / "data" / slug
        self._write_json(data_dir / "referencia.json", self._make_referencia(projeto="BALANCED", slug=slug))
        extracao = self._make_extracao()
        self._write_json(data_dir / "extracao_intermediarios.json", extracao)
        result = validate_pipeline_integrity(slug, root=tmp_path)
        checkpoints = result["validacoes_fechamento"]
        # checkpoint 0: e4.sem_bdi=500 vs e6.sem_bdi=500 → OK
        assert checkpoints[0]["status"] == "OK"
        # checkpoint 1: e6.com_bdi=800 vs e6.catalogo=800 → OK
        assert checkpoints[1]["status"] == "OK"
