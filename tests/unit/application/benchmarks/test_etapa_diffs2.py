"""Tests for application/benchmarks/analysis/etapa_diffs.py."""

from __future__ import annotations


class TestCes03Helpers:
    def test_cost_severidade_critica(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _ces03_cost_severidade

        assert _ces03_cost_severidade(0, 100, 50) == "CRITICA"

    def test_cost_severidade_alta(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _ces03_cost_severidade

        assert _ces03_cost_severidade(100, 80, 15) == "ALTA"

    def test_cost_severidade_media(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _ces03_cost_severidade

        assert _ces03_cost_severidade(100, 95, 5) == "MEDIA"

    def test_compare_item_no_diffs(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _ces03_compare_item

        can = {"funcoes": [1, 2], "equipamentos": [1], "custo_total": 100.0}
        ref = {"funcoes": [1, 2], "equipamentos": [1], "custo_total": 100.0}
        diffs = _ces03_compare_item("A1", can, ref)
        assert diffs == []

    def test_compare_item_funcoes_diff(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _ces03_compare_item

        can = {"funcoes": [], "equipamentos": [], "custo_total": 0}
        ref = {"funcoes": [1, 2], "equipamentos": [], "custo_total": 100}
        diffs = _ces03_compare_item("A1", can, ref)
        assert any(d["campo"] == "funcoes_count" for d in diffs)
        assert any(d["severidade"] == "CRITICA" for d in diffs)

    def test_compare_item_equipamentos_diff(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _ces03_compare_item

        can = {"funcoes": [1], "equipamentos": [1, 2], "custo_total": 100}
        ref = {"funcoes": [1], "equipamentos": [1], "custo_total": 100}
        diffs = _ces03_compare_item("A1", can, ref)
        assert any(d["campo"] == "equipamentos_count" for d in diffs)

    def test_compare_item_cost_diff(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _ces03_compare_item

        can = {"funcoes": [1], "equipamentos": [1], "custo_total": 1200.0}
        ref = {"funcoes": [1], "equipamentos": [1], "custo_total": 1000.0}
        diffs = _ces03_compare_item("A1", can, ref)
        assert any(d["campo"] == "custo_total" for d in diffs)
        assert any(d.get("severidade") == "ALTA" for d in diffs)


class TestCompareEquipesSkill05:
    def test_no_matching_items(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import compare_equipes_skill05

        can = [{"item_id": "A1", "funcoes": [], "equipamentos": [], "custo_total": 100}]
        ref = [{"item_id": "A2", "funcoes": [], "equipamentos": [], "custo_total": 100}]
        result = compare_equipes_skill05(can, ref)
        assert result == []

    def test_matching_items_no_diff(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import compare_equipes_skill05

        eq = {"item_id": "A1", "funcoes": [1], "equipamentos": [1], "custo_total": 100.0}
        result = compare_equipes_skill05([eq], [eq])
        assert result == []


class TestNormalizeRefEquipes:
    def test_list_passthrough(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_ref_equipes

        data = [{"item_id": "A1"}]
        result = _normalize_ref_equipes(data)
        assert result == data

    def test_dict_with_equipes_key(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_ref_equipes

        data = {"equipes": [{"item_id": "A1"}]}
        result = _normalize_ref_equipes(data)
        assert result == [{"item_id": "A1"}]

    def test_dict_with_detalhes_key(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_ref_equipes

        data = {"detalhes": [{"equipe_id": "E1"}]}
        result = _normalize_ref_equipes(data)
        assert isinstance(result, list)

    def test_non_dict_non_list(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_ref_equipes

        result = _normalize_ref_equipes("invalid")
        assert result == []


class TestComparePlanejamento:
    def test_empty_both(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import compare_planejamento_skill04

        result = compare_planejamento_skill04([], [])
        assert result == []

    def test_no_match(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import compare_planejamento_skill04

        can = [{"item_id": "A1", "descricao": "Test", "subtotal": {"sem_bdi": 100}}]
        ref = [{"item_id": "A2", "descricao": "Other", "subtotal": {"sem_bdi": 200}}]
        result = compare_planejamento_skill04(can, ref)
        assert result == []

    def test_with_delta(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import compare_planejamento_skill04

        # canonical: subtotal.sem_bdi.total, ref: subtotal_com_bdi.total
        can = [{"item_id": "A1", "subtotal": {"sem_bdi": {"total": 1200}}}]
        ref = [{"item_id": "A1", "subtotal_com_bdi": {"total": 1000}}]
        result = compare_planejamento_skill04(can, ref)
        assert len(result) > 0


class TestCompareResultadoSkill06:
    def test_empty(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import compare_resultado_skill06

        result = compare_resultado_skill06({}, {})
        assert isinstance(result, list)

    def test_with_diff(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import compare_resultado_skill06

        # Fields: venda, custo, margem from nested structure
        can = {"venda": {"total_com_bdi": 1600000}, "custo": {"total": 1200000}, "margem_pct": 0.12}
        ref = {"venda": {"total_com_bdi": 1500000}, "custo": {"total": 1000000}, "margem_pct": 0.10}
        result = compare_resultado_skill06(can, ref)
        assert len(result) > 0  # venda and/or custo differ


class TestToFloat:
    def test_from_int(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _to_float

        assert _to_float(100) == 100.0

    def test_from_dict_keys(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _to_float

        assert _to_float({"total": 50.0}, ("total",)) == 50.0

    def test_from_empty(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _to_float

        assert _to_float(None) == 0.0

    def test_from_dict_no_matching_key_exhausts_loop(self):
        """Nenhuma das keys casa com um valor numérico -> percorre todo o loop e retorna 0.0."""
        from concilium.application.benchmarks.analysis.etapa_diffs import _to_float

        assert _to_float({"other": "text", "another": None}, ("total", "valor")) == 0.0


class TestSummarize:
    def test_basic(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _summarize

        diffs = [{"campo": "custo", "severidade": "ALTA"}]
        result = _summarize(diffs)
        assert isinstance(result, str)
        assert "ALTA" in result

    def test_empty(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _summarize

        result = _summarize([])
        assert "0" in result  # "0 CRITICA, 0 ALTA, 0 MEDIA"


class TestFindBenchmarkHelpers:
    def test_find_benchmark_report_not_found(self, tmp_path):
        from concilium.application.benchmarks.analysis.etapa_diffs import _find_benchmark_report

        result = _find_benchmark_report("MISSING", tmp_path)
        assert result is None

    def test_find_benchmark_report_found(self, tmp_path):
        from concilium.application.benchmarks.analysis.etapa_diffs import _find_benchmark_report

        # Correct path: benchmarks/data/AGIS/audit/benchmark_report.json
        audit_dir = tmp_path / "benchmarks" / "data" / "AGIS" / "audit"
        audit_dir.mkdir(parents=True)
        (audit_dir / "benchmark_report.json").write_text('{"slug": "AGIS"}')
        result = _find_benchmark_report("AGIS", tmp_path)
        assert result is not None

    def test_find_reference_payload_not_found(self, tmp_path):
        from concilium.application.benchmarks.analysis.etapa_diffs import _find_reference_payload

        result = _find_reference_payload("MISSING", tmp_path)
        assert result is None

    def test_normalize_ref_equipes_empty_dict(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_ref_equipes

        result = _normalize_ref_equipes({})
        assert result == []


class TestNormalizeResultadoPairs:
    def test_basic(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_resultado_pairs

        can = {"venda": {"total_com_bdi": 1000}, "custo": {"total": 800}, "margem_pct": 0.2}
        ref = {"venda": {"total_com_bdi": 900}, "custo": {"total": 700}, "margem_pct": 0.18}
        result = _normalize_resultado_pairs(can, ref)
        assert len(result) == 3  # venda, custo, margem

    def test_empty_dicts(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_resultado_pairs

        result = _normalize_resultado_pairs({}, {})
        assert len(result) == 3  # all zeros

    def test_benchmark_confronto_ferramenta(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_resultado_pairs

        can = {}
        ref = {"benchmark_confronto_ferramenta": {"preco_venda": 1000, "custo_direto": 700, "custo_indireto": 100}}
        result = _normalize_resultado_pairs(can, ref)
        # ref_venda should be 1000
        assert any(t[0] == "venda" and t[2] == 1000.0 for t in result)

    def test_benchmark_confronto_referencia(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_resultado_pairs

        can = {}
        ref = {"benchmark_confronto_referencia": {"preco_venda": 2000, "custo_total": 1500}}
        result = _normalize_resultado_pairs(can, ref)
        # ref_venda should be 2000
        assert any(t[0] == "venda" and t[2] == 2000.0 for t in result)

    def test_confronto_referencia_zero_venda_gives_zero_margem(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_resultado_pairs

        ref = {"benchmark_confronto_referencia": {"preco_venda": 0.0, "custo_total": 100.0}}
        result = _normalize_resultado_pairs({}, ref)
        margem_row = next(t for t in result if t[0] == "margem")
        assert margem_row[2] == 0.0

    def test_confronto_ferramenta_positive_venda_gives_nonzero_margem(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_resultado_pairs

        ref = {"benchmark_confronto_ferramenta": {"preco_venda": 1000, "custo_indireto": 100, "custo_direto": 700}}
        result = _normalize_resultado_pairs({}, ref)
        margem_row = next(t for t in result if t[0] == "margem")
        # (1000 - 800) / 1000 = 0.2
        assert abs(margem_row[2] - 0.2) < 1e-6

    def test_none_inputs_treated_as_empty_dicts(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_resultado_pairs

        result = _normalize_resultado_pairs(None, None)
        assert len(result) == 3


class TestNormalizeRefPlanejamento:
    def test_list_passthrough(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_ref_planejamento

        data = [{"item_id": "A1"}]
        assert _normalize_ref_planejamento(data) == data

    def test_non_dict_non_list_returns_empty(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_ref_planejamento

        assert _normalize_ref_planejamento("invalid") == []
        assert _normalize_ref_planejamento(42) == []

    def test_dict_with_itens_com_precos(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_ref_planejamento

        data = {"itens_com_precos": [{"item_id": "A1", "subtotal_com_bdi": {"total": 100}}]}
        result = _normalize_ref_planejamento(data)
        assert result == [{"item_id": "A1", "subtotal_com_bdi": {"total": 100}}]

    def test_dict_with_itens_key_normalizes(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_ref_planejamento

        data = {"itens": [{"item_id": "A1", "subtotal": {"sem_bdi": {"total": 500.0}}}]}
        result = _normalize_ref_planejamento(data)
        assert len(result) == 1
        assert result[0]["subtotal_com_bdi"]["total"] == 500.0

    def test_dict_without_itens_returns_empty(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_ref_planejamento

        result = _normalize_ref_planejamento({"other_key": []})
        assert result == []


class TestNormalizeRefIndiretos:
    def test_non_dict_returns_empty(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_ref_indiretos

        assert _normalize_ref_indiretos([]) == {}
        assert _normalize_ref_indiretos("x") == {}

    def test_direct_cat_keys_passthrough(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_ref_indiretos

        data = {cat: {"custo_com_bdi": float(i * 100)} for i, cat in enumerate(("ADM", "TOP", "LAB", "QSMS", "MOB"))}
        result = _normalize_ref_indiretos(data)
        assert result == data

    def test_raw_indiretos_list(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_ref_indiretos

        data = {
            "raw_indiretos": [{"categoria": "ADM", "custo_total": 500.0}, {"categoria": "TOP", "custo_total": 200.0}]
        }
        result = _normalize_ref_indiretos(data)
        assert result["ADM"]["custo_com_bdi"] == 500.0
        assert result["TOP"]["custo_com_bdi"] == 200.0

    def test_raw_indiretos_com_bdi_list(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_ref_indiretos

        data = {"raw_indiretos_com_bdi": [{"categoria": "LAB", "custo_com_bdi": 300.0}]}
        result = _normalize_ref_indiretos(data)
        assert result["LAB"]["custo_com_bdi"] == 300.0

    def test_empty_dict_returns_zero_categories(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_ref_indiretos

        result = _normalize_ref_indiretos({})
        for cat in ("ADM", "TOP", "LAB", "QSMS", "MOB"):
            assert result[cat]["custo_com_bdi"] == 0.0

    def test_raw_indiretos_unknown_categoria_is_skipped(self):
        """categoria fora do conjunto conhecido não deve ser adicionada a out."""
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_ref_indiretos

        data = {"raw_indiretos": [{"categoria": "DESCONHECIDA", "custo_total": 999.0}]}
        result = _normalize_ref_indiretos(data)
        assert "DESCONHECIDA" not in result
        for cat in ("ADM", "TOP", "LAB", "QSMS", "MOB"):
            assert result[cat]["custo_com_bdi"] == 0.0


class TestCompareIndiretos:
    def test_no_discrepancy_when_equal(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import compare_indiretos_skill05

        canonical = [{"categoria": "ADM", "custo_total": 1000.0}]
        ref = {
            "ADM": {"custo_com_bdi": 1000.0},
            "TOP": {"custo_com_bdi": 0.0},
            "LAB": {"custo_com_bdi": 0.0},
            "QSMS": {"custo_com_bdi": 0.0},
            "MOB": {"custo_com_bdi": 0.0},
        }
        result = compare_indiretos_skill05(canonical, ref)
        assert result == []

    def test_critica_when_can_zero_ref_positive(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import compare_indiretos_skill05

        canonical = []
        ref = {
            "ADM": {"custo_com_bdi": 5000.0},
            "TOP": {"custo_com_bdi": 0.0},
            "LAB": {"custo_com_bdi": 0.0},
            "QSMS": {"custo_com_bdi": 0.0},
            "MOB": {"custo_com_bdi": 0.0},
        }
        result = compare_indiretos_skill05(canonical, ref)
        adm = next(d for d in result if d["categoria"] == "ADM")
        assert "CRÍT" in adm["severidade"] or adm["severidade"].startswith("CR")

    def test_ref_val_zero_gives_zero_pct(self):
        """When ref_val=0 and can_val≠0, pct_diff=0 (no division by zero)."""
        from concilium.application.benchmarks.analysis.etapa_diffs import compare_indiretos_skill05

        canonical = [{"categoria": "ADM", "custo_total": 1000.0}]
        ref = {
            "ADM": {"custo_com_bdi": 0.0},
            "TOP": {"custo_com_bdi": 0.0},
            "LAB": {"custo_com_bdi": 0.0},
            "QSMS": {"custo_com_bdi": 0.0},
            "MOB": {"custo_com_bdi": 0.0},
        }
        result = compare_indiretos_skill05(canonical, ref)
        assert any(d["categoria"] == "ADM" for d in result)
        adm = next(d for d in result if d["categoria"] == "ADM")
        assert adm["pct_diff"] == 0.0


class TestNormalizeReferencePayload:
    def test_non_dict_returns_empty(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_reference_payload

        assert _normalize_reference_payload(None) == {}
        assert _normalize_reference_payload([]) == {}

    def test_already_normalized_passthrough(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_reference_payload

        data = {"equipes": [], "planejamento": [], "indiretos": {}, "resultado": {}}
        result = _normalize_reference_payload(data)
        assert result == data

    def test_agis_format_with_cat_keys(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_reference_payload

        data = {
            "equipes_detalhadas": [],
            "planejamento_detalhado": [],
            "resultado": {},
            "rcpsp_spec": {"deadline_weeks": 52},
            "ADM": {"custo_fixo_mensal_total": 100.0, "custo_fixo_total": 0.0},
            "TOP": {"custo_fixo_mensal_total": 50.0, "custo_fixo_total": 0.0},
            "LAB": {"custo_fixo_mensal_total": 0.0, "custo_fixo_total": 0.0},
            "QSMS": {"custo_fixo_mensal_total": 0.0, "custo_fixo_total": 0.0},
            "MOB": {"custo_fixo_mensal_total": 0.0, "custo_fixo_total": 0.0},
        }
        result = _normalize_reference_payload(data)
        assert "equipes" in result
        assert "indiretos" in result
        assert "ADM" in result["indiretos"]
        assert result["indiretos"]["ADM"]["custo_com_bdi"] > 0

    def test_agis_zero_deadline_weeks(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_reference_payload

        data = {
            "equipes_detalhadas": [],
            "planejamento_detalhado": [],
            "resultado": {},
            "rcpsp_spec": {"deadline_weeks": 0},
            "ADM": {"custo_fixo_mensal_total": 100.0, "custo_fixo_total": 0.0},
            "TOP": {"custo_fixo_mensal_total": 0.0, "custo_fixo_total": 0.0},
            "LAB": {"custo_fixo_mensal_total": 0.0, "custo_fixo_total": 0.0},
            "QSMS": {"custo_fixo_mensal_total": 0.0, "custo_fixo_total": 0.0},
            "MOB": {"custo_fixo_mensal_total": 0.0, "custo_fixo_total": 0.0},
        }
        result = _normalize_reference_payload(data)
        # With 0 deadline_weeks, meses_estimados=0, monthly cost contributes nothing
        assert result["indiretos"]["ADM"]["custo_com_bdi"] == 0.0

    def test_missing_cat_keys_skips_indiretos_derivation(self):
        """Payload sem os 5 campos de categoria não deve derivar indiretos (mantém {})."""
        from concilium.application.benchmarks.analysis.etapa_diffs import _normalize_reference_payload

        data = {
            "equipes_detalhadas": [],
            "planejamento_detalhado": [],
            "resultado": {},
            "ADM": {"custo_fixo_mensal_total": 100.0},
            # TOP, LAB, QSMS, MOB ausentes.
        }
        result = _normalize_reference_payload(data)
        assert result["indiretos"] == {}


class TestGenerateDiffsForBenchmark:
    def test_returns_none_when_reference_payload_missing(self, tmp_path):
        from concilium.application.benchmarks.analysis.etapa_diffs import generate_diffs_for_benchmark

        result = generate_diffs_for_benchmark("MISSING_SLUG", tmp_path)
        assert result is None

    def test_returns_none_when_benchmark_report_missing(self, tmp_path):
        import json

        from concilium.application.benchmarks.analysis.etapa_diffs import generate_diffs_for_benchmark

        slug_u = "AGIS"
        ref_dir = tmp_path / "benchmarks" / "data" / slug_u
        ref_dir.mkdir(parents=True)
        (ref_dir / "referencia.json").write_text(json.dumps({"resultado": {}}))
        # Nenhum benchmark_report.json criado.

        result = generate_diffs_for_benchmark(slug_u, tmp_path)
        assert result is None


class TestPlanejamentoSeveridade:
    def test_alta_when_pct_over_20(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import compare_planejamento_skill04

        can = [{"item_id": "A1", "subtotal": {"sem_bdi": {"total": 1500}}}]
        ref = [{"item_id": "A1", "subtotal_com_bdi": {"total": 1000}}]
        result = compare_planejamento_skill04(can, ref)
        assert len(result) > 0
        # pct_diff = |500 / (1000 + 0.01)| × 100 ≈ 50% → ALTA
        assert result[0]["severidade"] == "ALTA"

    def test_media_when_pct_5_to_20(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import compare_planejamento_skill04

        can = [{"item_id": "A1", "subtotal": {"sem_bdi": {"total": 1100}}}]
        ref = [{"item_id": "A1", "subtotal_com_bdi": {"total": 1000}}]
        result = compare_planejamento_skill04(can, ref)
        assert len(result) > 0
        # pct_diff ≈ 10% → MÉDIA
        assert "ÉDIA" in result[0]["severidade"] or result[0]["severidade"] == "MÉ" or "M" in result[0]["severidade"]

    def test_baixa_when_pct_under_5(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import compare_planejamento_skill04

        can = [{"item_id": "A1", "subtotal": {"sem_bdi": {"total": 1020}}}]
        ref = [{"item_id": "A1", "subtotal_com_bdi": {"total": 1000}}]
        result = compare_planejamento_skill04(can, ref)
        assert len(result) > 0
        assert result[0]["severidade"] == "BAIXA"


class TestFindBenchmarkReportFallback:
    def test_fallback_benchmark_json_at_root(self, tmp_path):
        from concilium.application.benchmarks.analysis.etapa_diffs import _find_benchmark_report

        p = tmp_path / "benchmark_agis.json"
        p.write_text('{"slug": "AGIS"}')
        result = _find_benchmark_report("AGIS", tmp_path)
        assert result == p

    def test_organized_path_preferred_over_fallback(self, tmp_path):
        from concilium.application.benchmarks.analysis.etapa_diffs import _find_benchmark_report

        fallback = tmp_path / "benchmark_agis.json"
        fallback.write_text('{"fallback": true}')
        organized = tmp_path / "benchmarks" / "data" / "AGIS" / "artifacts" / "outputs" / "benchmark_report.json"
        organized.parent.mkdir(parents=True)
        organized.write_text('{"organized": true}')
        result = _find_benchmark_report("AGIS", tmp_path)
        assert result == organized


class TestFindReferencePayload:
    def test_finds_iteracao_referencias_at_root_bench(self, tmp_path):
        from concilium.application.benchmarks.analysis.etapa_diffs import _find_reference_payload

        path = tmp_path / "benchmarks" / "data" / "AGIS" / "iteracao_referencias_agis.json"
        path.parent.mkdir(parents=True)
        path.write_text("{}")
        result = _find_reference_payload("AGIS", tmp_path)
        assert result == path

    def test_finds_referencia_json_at_data_slug(self, tmp_path):
        from concilium.application.benchmarks.analysis.etapa_diffs import _find_reference_payload

        path = tmp_path / "benchmarks" / "data" / "AGIS" / "referencia.json"
        path.parent.mkdir(parents=True)
        path.write_text("{}")
        result = _find_reference_payload("AGIS", tmp_path)
        assert result == path


class TestGdfbLoadCanonical:
    def test_returns_empty_when_no_projetos_dir(self, tmp_path):
        from concilium.application.benchmarks.analysis.etapa_diffs import _gdfb_load_canonical

        bench = {"projeto": "MyProject"}
        result = _gdfb_load_canonical(bench, tmp_path)
        assert result == {}

    def test_skips_non_directory_entries(self, tmp_path):
        import json

        from concilium.application.benchmarks.analysis.etapa_diffs import _gdfb_load_canonical

        projetos_dir = tmp_path / "projetos"
        projetos_dir.mkdir(parents=True)
        (projetos_dir / "stray_file.txt").write_text("not a project")
        proj_dir = projetos_dir / "proj1"
        v1_dir = proj_dir / "v1"
        v1_dir.mkdir(parents=True)
        (proj_dir / "meta.json").write_text(json.dumps({"nome": "MyProject", "current_version": "v1"}))
        (v1_dir / "canonical.json").write_text(json.dumps({"projeto_id": "p1"}))

        bench = {"projeto": "MyProject"}
        result = _gdfb_load_canonical(bench, tmp_path)
        assert result.get("projeto_id") == "p1"

    def test_skips_directory_without_meta_json(self, tmp_path):
        import json

        from concilium.application.benchmarks.analysis.etapa_diffs import _gdfb_load_canonical

        projetos_dir = tmp_path / "projetos"
        no_meta_dir = projetos_dir / "no_meta"
        no_meta_dir.mkdir(parents=True)

        proj_dir = projetos_dir / "proj1"
        v1_dir = proj_dir / "v1"
        v1_dir.mkdir(parents=True)
        (proj_dir / "meta.json").write_text(json.dumps({"nome": "MyProject", "current_version": "v1"}))
        (v1_dir / "canonical.json").write_text(json.dumps({"projeto_id": "p1"}))

        bench = {"projeto": "MyProject"}
        result = _gdfb_load_canonical(bench, tmp_path)
        assert result.get("projeto_id") == "p1"

    def test_no_canonical_file_in_any_candidate_continues_outer_loop(self, tmp_path):
        """Nenhum canonical.json existe para o projeto encontrado -> loop interno se esgota."""
        import json

        from concilium.application.benchmarks.analysis.etapa_diffs import _gdfb_load_canonical

        projetos_dir = tmp_path / "projetos"
        proj_dir = projetos_dir / "proj1"
        proj_dir.mkdir(parents=True)
        (proj_dir / "meta.json").write_text(json.dumps({"nome": "MyProject", "current_version": "v2"}))
        # Nem v2/canonical.json nem v1/canonical.json existem.

        bench = {"projeto": "MyProject"}
        result = _gdfb_load_canonical(bench, tmp_path)
        assert result == {}

    def test_falls_back_to_v1_when_current_version_canonical_missing(self, tmp_path):
        """current_version/canonical.json ausente, mas v1/canonical.json presente."""
        import json

        from concilium.application.benchmarks.analysis.etapa_diffs import _gdfb_load_canonical

        projetos_dir = tmp_path / "projetos"
        proj_dir = projetos_dir / "proj1"
        v1_dir = proj_dir / "v1"
        v1_dir.mkdir(parents=True)
        (proj_dir / "meta.json").write_text(json.dumps({"nome": "MyProject", "current_version": "v2"}))
        (v1_dir / "canonical.json").write_text(json.dumps({"projeto_id": "fallback"}))

        bench = {"projeto": "MyProject"}
        result = _gdfb_load_canonical(bench, tmp_path)
        assert result.get("projeto_id") == "fallback"

    def test_returns_canonical_when_found(self, tmp_path):
        import json

        from concilium.application.benchmarks.analysis.etapa_diffs import _gdfb_load_canonical

        projeto_dir = tmp_path / "projetos" / "proj1"
        v1_dir = projeto_dir / "v1"
        v1_dir.mkdir(parents=True)
        (projeto_dir / "meta.json").write_text(json.dumps({"nome": "MyProject", "current_version": "v1"}))
        (v1_dir / "canonical.json").write_text(json.dumps({"projeto_id": "p1"}))

        bench = {"projeto": "MyProject"}
        result = _gdfb_load_canonical(bench, tmp_path)
        assert result.get("projeto_id") == "p1"

    def test_skips_bad_meta_json(self, tmp_path):
        from concilium.application.benchmarks.analysis.etapa_diffs import _gdfb_load_canonical

        projeto_dir = tmp_path / "projetos" / "proj_bad"
        projeto_dir.mkdir(parents=True)
        (projeto_dir / "meta.json").write_text("not_valid_json{{{")

        bench = {"projeto": "SomeProject"}
        result = _gdfb_load_canonical(bench, tmp_path)
        assert result == {}

    def test_returns_empty_when_projeto_nome_mismatch(self, tmp_path):
        import json

        from concilium.application.benchmarks.analysis.etapa_diffs import _gdfb_load_canonical

        projeto_dir = tmp_path / "projetos" / "proj1"
        v1_dir = projeto_dir / "v1"
        v1_dir.mkdir(parents=True)
        (projeto_dir / "meta.json").write_text(json.dumps({"nome": "OtherProject"}))
        (v1_dir / "canonical.json").write_text(json.dumps({"projeto_id": "p1"}))

        bench = {"projeto": "MyProject"}
        result = _gdfb_load_canonical(bench, tmp_path)
        assert result == {}
