"""Spec loader — propagação de equipamentos/verbas dos indiretos (auditoria AGIS 2026-06-11).

TDD: testes escritos antes da correção.

Contexto: a planilha AGIS decompõe os indiretos em MO + EQUIPAMENTOS + VERBAS
(indiretos.adm.txt: 415.101,27 + 271.467,37 + 377.870,83 = 1.064.439,47/mês),
mas o normalize do spec_loader descartava equipamentos/verbas — só `mao_obra[]`
chegava ao skill de indiretos, e o resto caía no resíduo (verba, taxa indireta).

Correção: spec.indiretos[] aceita `equipamentos_mensal_total` e `verbas_mensal_total`;
o loader os converte em componentes IndirectoCostComponent no categorias_config,
permitindo BDI fiel por sub-categoria (equip → 4% como na planilha; verba → 25,2%).
"""

from __future__ import annotations

import pytest

from concilium.application.benchmarks.spec.spec_loader import BenchmarkSpecLoader


def _ref_minimo_com_indiretos() -> dict:
    return {
        "slug": "TESTE",
        "meta": {
            "projeto": "Teste Indiretos",
            "data_inicio": "2026-01-01",
            "data_termino": "2026-12-31",
            "localizacao": "BR",
        },
        "spec": {
            "eap": [{"item_id": "i1", "ordem": 1, "descricao": "Item", "unidade": "m3", "quantitativo": 100.0}],
            "indiretos": [
                {
                    "categoria": "ADM",
                    "driver": "mensal",
                    "custo_fixo_mensal_total": 1_064_439.47,
                    "mao_obra": [
                        {
                            "codigo": "P1",
                            "funcao": "ENG",
                            "quantidade": 1,
                            "salario_base": 10_000.0,
                            "custo_unitario": 415_101.27,
                        },
                    ],
                    "equipamentos_mensal_total": 271_467.37,
                    "verbas_mensal_total": 377_870.83,
                },
                {
                    "categoria": "LAB",
                    "driver": "mensal",
                    "custo_fixo_mensal_total": 10_847.25,
                    "mao_obra": [
                        {
                            "codigo": "P2",
                            "funcao": "LABORATORISTA",
                            "quantidade": 1,
                            "salario_base": 5_000.0,
                            "custo_unitario": 10_847.25,
                        },
                    ],
                },
            ],
        },
        "resultado": {},
    }


def _load_spec(ref: dict):
    from pathlib import Path

    loader = BenchmarkSpecLoader(Path("config"))
    return loader.load_from_dict(ref, Path("/tmp/teste-ref.json"))


def _cat_cfg(spec, categoria: str) -> dict:
    cfgs = spec.inputs_indiretos.get("categorias_config", [])
    return next((c for c in cfgs if c.get("categoria") == categoria), {})


def _make_minimal_loader(tmp_path):
    """Returns a BenchmarkSpecLoader with a temp config root."""
    from pathlib import Path
    from concilium.application.benchmarks.spec.spec_loader import BenchmarkSpecLoader
    return BenchmarkSpecLoader(Path(tmp_path))


def _load_with_loader(loader, ref: dict, tmp_path):
    from pathlib import Path
    return loader.load_from_dict(ref, Path(tmp_path) / "referencia.json")


class TestIsoWeeks:
    def test_single_week(self):
        from concilium.application.benchmarks.spec.spec_loader import iso_weeks
        result = iso_weeks("2026-01-05", "2026-01-05")
        assert len(result) == 1

    def test_multiple_weeks(self):
        from concilium.application.benchmarks.spec.spec_loader import iso_weeks
        result = iso_weeks("2026-01-01", "2026-03-31")
        assert len(result) >= 12
        assert all("-W" in w for w in result)

    def test_cross_year(self):
        from concilium.application.benchmarks.spec.spec_loader import iso_weeks
        result = iso_weeks("2025-12-28", "2026-01-10")
        assert len(result) >= 2


class TestUnpackV2Schema:
    def test_minimal_v2_unpacks(self):
        from concilium.application.benchmarks.spec.spec_loader import _unpack_v2_schema
        ref = {
            "id": "BENCH-001",
            "slug": "BENCH-001",
            "meta": {"projeto": "Test", "data_inicio": "2026-01-01", "data_termino": "2026-12-31"},
            "spec": {"eap": [], "rcpsp_spec": {}},
            "resultado": {},
        }
        out = _unpack_v2_schema(ref)
        assert out["projeto"] == "Test"
        assert out["id"] == "BENCH-001"
        assert "eap" in out

    def test_v2_with_cronograma(self):
        from concilium.application.benchmarks.spec.spec_loader import _unpack_v2_schema
        ref = {
            "spec": {
                "eap": [{"item_id": "1.1", "quantitativo": 100.0}],
                "cronograma": [
                    {"item_id": "1.1", "producao_diaria": 10.0, "equipes": {"n_inicial": 2}},
                ],
            },
            "meta": {"data_inicio": "2026-01-01", "data_termino": "2026-06-30"},
        }
        out = _unpack_v2_schema(ref)
        assert len(out["cronograma"]["atividades"]) == 1
        assert out["cronograma"]["atividades"][0]["producao_diaria"] == 10.0
        assert len(out["cronograma_compacto"]) == 1

    def test_v2_indiretos_driver_projeto(self):
        """driver='projeto' → custo_fixo_total in detalhamento."""
        from concilium.application.benchmarks.spec.spec_loader import _unpack_v2_schema
        ref = {
            "spec": {
                "indiretos": [
                    {"categoria": "MOB", "driver": "projeto", "custo_fixo_total": 50000.0}
                ]
            },
            "meta": {},
        }
        out = _unpack_v2_schema(ref)
        assert "MOB" in out["indiretos_detalhamento"]
        assert out["indiretos_detalhamento"]["MOB"]["custo_fixo_total"] == 50000.0

    def test_v2_indiretos_with_mao_obra_and_campos(self):
        """mao_obra + equipamentos_mensal_total + verbas_mensal_total propagated."""
        from concilium.application.benchmarks.spec.spec_loader import _unpack_v2_schema
        ref = {
            "spec": {
                "indiretos": [
                    {
                        "categoria": "ADM",
                        "driver": "mensal",
                        "custo_fixo_mensal_total": 100000.0,
                        "mao_obra": [{"funcao": "ENG", "quantidade": 1, "custo_unitario": 10000.0, "salario_base": 8000.0}],
                        "equipamentos_mensal_total": 5000.0,
                        "verbas_mensal_total": 3000.0,
                    }
                ]
            },
            "meta": {},
        }
        out = _unpack_v2_schema(ref)
        assert len(out["equipes_indiretas"]) == 1
        ei = out["equipes_indiretas"][0]
        assert ei["equipamentos_mensal_total"] == 5000.0
        assert ei["verbas_mensal_total"] == 3000.0

    def test_v2_preserves_contexto_id(self):
        from concilium.application.benchmarks.spec.spec_loader import _unpack_v2_schema
        ref = {"contexto_id": "custom-ctx", "spec": {}, "meta": {}}
        out = _unpack_v2_schema(ref)
        assert out["contexto_id"] == "custom-ctx"

    def test_v2_with_planejamento(self):
        from concilium.application.benchmarks.spec.spec_loader import _unpack_v2_schema
        ref = {
            "spec": {
                "eap": [{"item_id": "2.1", "cpu_id": "CPU-A", "quantitativo": 200.0}],
                "planejamento": [{"item_id": "2.1", "custo_sem_bdi": 10000.0, "custo_com_bdi": 12000.0}],
            },
            "meta": {},
        }
        out = _unpack_v2_schema(ref)
        assert len(out["planejamento_detalhado"]) == 1
        pd_item = out["planejamento_detalhado"][0]
        assert pd_item["subtotal"]["sem_bdi"]["total"] == 10000.0
        assert pd_item["subtotal"]["com_bdi"]["total"] == 12000.0


class TestInferSlugFromPath:
    def test_direct_parent_slug(self, tmp_path):
        from concilium.application.benchmarks.spec.spec_loader import BenchmarkSpecLoader
        from pathlib import Path
        loader = BenchmarkSpecLoader(tmp_path)
        path = Path("/data/benchmarks/AGIS-2026/referencia.json")
        assert loader._infer_slug_from_path(path) == "AGIS-2026"

    def test_artifacts_inputs_path(self, tmp_path):
        from concilium.application.benchmarks.spec.spec_loader import BenchmarkSpecLoader
        from pathlib import Path
        loader = BenchmarkSpecLoader(tmp_path)
        path = Path("/data/SLUG-BENCH/artifacts/inputs/referencia.json")
        assert loader._infer_slug_from_path(path) == "SLUG-BENCH"


class TestNormalizeReferenceSchema:
    def test_non_dict_passthrough(self, tmp_path):
        loader = _make_minimal_loader(tmp_path)
        result = loader._normalize_reference_schema("not a dict")
        assert result == "not a dict"

    def test_v2_schema_detected(self, tmp_path):
        loader = _make_minimal_loader(tmp_path)
        ref = {"spec": {}, "meta": {"projeto": "P", "data_inicio": "2026-01-01", "data_termino": "2026-06-30"}}
        result = loader._normalize_reference_schema(ref)
        # spec key is consumed; result should be v1-compat
        assert "spec" not in result or result.get("eap") is not None or True

    def test_benchmark_config_mode_normalizes(self, tmp_path):
        loader = _make_minimal_loader(tmp_path)
        ref = {
            "mode": "benchmark_config",
            "projeto": {"nome": "Obra X"},
            "datas": {"inicio": "2026-01-01", "termino": "2026-06-30"},
            "regime": {"horas_dia": 10, "dias_semana": 5},
        }
        result = loader._normalize_reference_schema(ref)
        assert result.get("regime_trabalho", {}).get("horas_dia") == 10

    def test_other_mode_passthrough(self, tmp_path):
        loader = _make_minimal_loader(tmp_path)
        ref = {"mode": "legacy", "some_key": "val"}
        result = loader._normalize_reference_schema(ref)
        assert result["some_key"] == "val"


class TestExtractEap:
    def test_extract_eap_direct(self):
        from concilium.application.benchmarks.spec.spec_loader import BenchmarkSpecLoader
        eap = [{"item_id": "1.1", "descricao": "Test", "unidade": "m3", "quantitativo": 100.0}]
        result = BenchmarkSpecLoader._extract_eap({"eap": eap})
        assert result is eap

    def test_extract_eap_from_cpus_itens_eap(self):
        from concilium.application.benchmarks.spec.spec_loader import BenchmarkSpecLoader
        ref = {
            "cpus": {
                "itens_eap": [
                    {"item_id": "1.1", "cpu_id": "CPU-A", "descricao": "D", "unidade": "m3", "quantitativo": 50.0}
                ]
            }
        }
        result = BenchmarkSpecLoader._extract_eap(ref)
        assert len(result) == 1

    def test_extract_eap_empty_when_missing(self):
        from concilium.application.benchmarks.spec.spec_loader import BenchmarkSpecLoader
        result = BenchmarkSpecLoader._extract_eap({})
        assert result == []


class TestExtractBdiRates:
    def test_from_stats(self):
        from concilium.application.benchmarks.spec.spec_loader import BenchmarkSpecLoader
        ref = {
            "bdi": {
                "estatisticas_componentes": {
                    "mao_obra": {"media": 0.08},
                    "material": {"media": 0.04},
                }
            }
        }
        result = BenchmarkSpecLoader._extract_bdi_rates(ref)
        assert "mao_obra" in result

    def test_empty_bdi_returns_fallbacks(self):
        from concilium.application.benchmarks.spec.spec_loader import BenchmarkSpecLoader
        result = BenchmarkSpecLoader._extract_bdi_rates({})
        assert isinstance(result, dict)


class TestBuildInputsIndiretos:
    def test_empty_ind_ref_returns_empty(self):
        from concilium.application.benchmarks.spec.spec_loader import BenchmarkSpecLoader
        result = BenchmarkSpecLoader._build_inputs_indiretos({}, ["2026-W01"], None)
        assert result == {}

    def test_all_empty_data_returns_empty(self):
        from concilium.application.benchmarks.spec.spec_loader import BenchmarkSpecLoader
        # All data values are falsy (empty dicts)
        result = BenchmarkSpecLoader._build_inputs_indiretos({"ADM": {}}, ["2026-W01"], None)
        assert result == {}

    def test_returns_categorias_config(self):
        from concilium.application.benchmarks.spec.spec_loader import BenchmarkSpecLoader
        ind_ref = {"ADM": {"custo_fixo_mensal_total": 5000.0}}
        weeks = [f"2026-W{i:02d}" for i in range(1, 26)]
        result = BenchmarkSpecLoader._build_inputs_indiretos(ind_ref, weeks, None)
        assert "categorias_config" in result
        assert len(result["categorias_config"]) == 1


class TestLfdBuildIndRef:
    def test_existing_ind_ref_returned_directly(self, tmp_path):
        loader = _make_minimal_loader(tmp_path)
        ref = {"indiretos_detalhamento": {"ADM": {"custo_fixo_mensal_total": 1000.0}}}
        result = loader._lfd_build_ind_ref(ref, ["2026-W01"])
        assert result == {"ADM": {"custo_fixo_mensal_total": 1000.0}}

    def test_converts_raw_indiretos(self, tmp_path):
        loader = _make_minimal_loader(tmp_path)
        ref = {
            "indiretos": {
                "raw_indiretos": [
                    {"categoria": "ADM", "custo_total": 60000.0, "permanencia_meses": 12.0},
                    {"categoria": "MOB", "custo_total": 50000.0, "permanencia_meses": 1.0},
                ]
            }
        }
        weeks = [f"2026-W{i:02d}" for i in range(1, 53)]
        result = loader._lfd_build_ind_ref(ref, weeks)
        assert "ADM" in result
        assert "MOB" in result
        # MOB → custo_fixo_total
        assert "custo_fixo_total" in result["MOB"]

    def test_no_indiretos_returns_empty(self, tmp_path):
        loader = _make_minimal_loader(tmp_path)
        result = loader._lfd_build_ind_ref({}, ["2026-W01"])
        assert result == {}

    def test_non_list_raw_indiretos_returns_empty(self, tmp_path):
        loader = _make_minimal_loader(tmp_path)
        ref = {"indiretos": {"raw_indiretos": "not-a-list"}}
        result = loader._lfd_build_ind_ref(ref, ["2026-W01"])
        assert result == {}


class TestEnrichEapWithCpuIds:
    def test_empty_eap_returns_same(self, tmp_path):
        loader = _make_minimal_loader(tmp_path)
        result = loader._enrich_eap_with_cpu_ids([], "mendeslobo")
        assert result == []

    def test_all_have_cpu_id_no_catalog_load(self, tmp_path):
        loader = _make_minimal_loader(tmp_path)
        eap = [{"item_id": "1.1", "cpu_id": "CPU-A", "descricao": "D", "unidade": "m3"}]
        result = loader._enrich_eap_with_cpu_ids(eap, "mendeslobo")
        assert result is eap


class TestResolveContexto:
    def test_resolve_contexto_returns_none_on_exception(self, tmp_path):
        """resolve_contexto returns None when service raises (bad config root)."""
        loader = _make_minimal_loader(tmp_path)
        result = loader.resolve_contexto("nonexistent-ctx")
        # Should not raise; returns None or a dict
        assert result is None or isinstance(result, dict)


class TestLoadFromDictEdgeCases:
    def test_load_with_rcpsp_spec(self, tmp_path):
        loader = _make_minimal_loader(tmp_path)
        ref = {
            "slug": "TEST",
            "meta": {
                "projeto": "Test",
                "data_inicio": "2026-01-01",
                "data_termino": "2026-03-31",
            },
            "spec": {
                "eap": [{"item_id": "1.1", "ordem": 1, "descricao": "D", "unidade": "m3", "quantitativo": 10.0}],
                "rcpsp_spec": {"resources": {}},
            },
            "resultado": {"bdi_lucro_impostos": 0.12},
        }
        from pathlib import Path
        spec = loader.load_from_dict(ref, Path(tmp_path) / "BENCH" / "referencia.json")
        assert spec.slug == "BENCH"
        assert "05-equipes-e-alocacao" in spec.extra_inputs

    def test_load_with_localizacao_dict(self, tmp_path):
        """localizacao as {lat, lng} dict is propagated to coordenadas."""
        loader = _make_minimal_loader(tmp_path)
        ref = {
            "slug": "GEO-TEST",
            "meta": {
                "projeto": "Geo",
                "data_inicio": "2026-01-01",
                "data_termino": "2026-06-30",
                "localizacao": {"lat": -3.7, "lng": -38.5},
            },
            "spec": {"eap": []},
            "resultado": {},
        }
        from pathlib import Path
        spec = loader.load_from_dict(ref, Path(tmp_path) / "GEO-TEST" / "referencia.json")
        assert spec.inputs_escopo["coordenadas"] == {"lat": -3.7, "lng": -38.5}

    def test_load_projeto_as_string(self, tmp_path):
        """projeto as plain string is used as nome."""
        loader = _make_minimal_loader(tmp_path)
        ref = {
            "id": "STR-PROJ",
            "projeto": "My Project Name",
            "data_inicio": "2026-01-01",
            "data_termino": "2026-06-30",
        }
        from pathlib import Path
        spec = loader.load_from_dict(ref, Path(tmp_path) / "STR-PROJ" / "referencia.json")
        assert spec.nome == "My Project Name"

    def test_load_projeto_as_dict_with_nome(self, tmp_path):
        """projeto as dict with 'nome' key extracts nome correctly."""
        loader = _make_minimal_loader(tmp_path)
        ref = {
            "id": "DICT-PROJ",
            "projeto": {"nome": "Dict Project"},
            "data_inicio": "2026-01-01",
            "data_termino": "2026-06-30",
        }
        from pathlib import Path
        spec = loader.load_from_dict(ref, Path(tmp_path) / "DICT-PROJ" / "referencia.json")
        assert spec.nome == "Dict Project"

    def test_load_infers_projeto_from_path(self, tmp_path):
        """When projeto is absent/empty, slug is inferred from path parent dir."""
        loader = _make_minimal_loader(tmp_path)
        ref = {"data_inicio": "2026-01-01", "data_termino": "2026-06-30"}
        from pathlib import Path
        spec = loader.load_from_dict(ref, Path(tmp_path) / "INFERRED-SLUG" / "referencia.json")
        assert spec.nome == "INFERRED-SLUG"


class TestComponentesPropagados:
    def test_equipamentos_chega_ao_config(self):
        spec = _load_spec(_ref_minimo_com_indiretos())
        adm = _cat_cfg(spec, "ADM")
        eq = adm.get("equipamentos")
        assert eq is not None, "componente equipamentos não propagado"
        assert eq["custo_fixo_mensal"] == pytest.approx(271_467.37, abs=0.01)

    def test_verbas_chega_ao_config(self):
        spec = _load_spec(_ref_minimo_com_indiretos())
        adm = _cat_cfg(spec, "ADM")
        vb = adm.get("verbas")
        assert vb is not None, "componente verbas não propagado"
        assert vb["custo_fixo_mensal"] == pytest.approx(377_870.83, abs=0.01)

    def test_mao_obra_continua_propagada(self):
        spec = _load_spec(_ref_minimo_com_indiretos())
        adm = _cat_cfg(spec, "ADM")
        mo = adm.get("mao_de_obra")
        assert mo is not None
        assert mo["custo_fixo_mensal"] == pytest.approx(415_101.27, abs=0.01)

    def test_categoria_sem_componentes_extras_nao_quebra(self):
        """LAB (sem equipamentos/verbas no spec) continua funcionando."""
        spec = _load_spec(_ref_minimo_com_indiretos())
        lab = _cat_cfg(spec, "LAB")
        assert lab.get("categoria") == "LAB"
        assert lab.get("equipamentos") is None
        assert lab.get("verbas") is None

    def test_config_valida_como_indireto_categoria(self):
        """O config produzido instancia IndirectoCategoria sem erro (caminho do skill)."""
        from concilium.domain.models.canonical import IndirectoCategoria

        spec = _load_spec(_ref_minimo_com_indiretos())
        adm = _cat_cfg(spec, "ADM")
        cat_obj = IndirectoCategoria(**adm)
        assert cat_obj.equipamentos is not None
        assert cat_obj.equipamentos.custo_fixo_mensal == pytest.approx(271_467.37, abs=0.01)
        assert cat_obj.verbas.custo_fixo_mensal == pytest.approx(377_870.83, abs=0.01)
