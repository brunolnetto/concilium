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
