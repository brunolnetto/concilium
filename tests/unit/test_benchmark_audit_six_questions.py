"""Testes unitários para audit_six_questions.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from concilium.application.benchmarks.analysis._audit_utils import (
    _is_close,
    _norm_float,
    _sum_dict_counter,
)
from concilium.application.benchmarks.analysis.audit_six_questions import (
    Answer,
    _aq1_build_eq_map,
    _aq1_resolve_ref_equipes,
    _aq3_build_cur_items,
    _aq3_resolve_ref_planejamento,
    _aq4_indireto_fallback,
    _aq4_resolve_ref_resultado,
    _aq5_build_pe_map,
    _audit_q1_insumos_equipes,
    _audit_q2_custo_direto,
    _audit_q3_orcamento,
    _audit_q4_indiretos,
    _audit_q5_ponto_equilibrio,
    _audit_q6_resultado,
    _brt_custo_triple,
    _brt_preco_venda_triple,
    _build_pe_mismatch,
    _build_resultado_triples,
    _extract_ref_item_subtotal,
    _resolve_cur_custo_direto,
    _resolve_ref_custo_direto,
    _resolve_ref_indireto,
    run_audit,
)

# ---------------------------------------------------------------------------
# Answer dataclass
# ---------------------------------------------------------------------------


class TestAnswerDataclass:
    def test_basic_construction(self):
        a = Answer(pergunta="Q1", status="PASSA", evidencia={"ok": True})
        assert a.pergunta == "Q1"
        assert a.status == "PASSA"
        assert a.evidencia == {"ok": True}

    def test_falha_status(self):
        a = Answer(pergunta="Q2", status="FALHA", evidencia={})
        assert a.status == "FALHA"

    def test_na_status(self):
        a = Answer(pergunta="Q5", status="N/A", evidencia={})
        assert a.status == "N/A"


# ---------------------------------------------------------------------------
# _audit_utils pure functions
# ---------------------------------------------------------------------------


class TestIsClose:
    def test_exact_match(self):
        assert _is_close(100.0, 100.0)

    def test_within_abs_tol(self):
        # TOL is 0.05 by default
        assert _is_close(100.0, 100.04)

    def test_beyond_abs_tol(self):
        # For 100.0, limit = max(0.05, 0.001*100) = 0.1, so 0.2 is beyond it
        assert not _is_close(100.0, 100.2)

    def test_rel_tol_large_values(self):
        # For large values, rel_tol (0.1%) dominates: limit = max(0.05, 0.001*1M) = 1000
        assert _is_close(1_000_000.0, 1_000_999.0)

    def test_zero_vs_small(self):
        # Both zero → equal
        assert _is_close(0.0, 0.0)

    def test_zero_vs_beyond_tol(self):
        assert not _is_close(0.0, 1.0)


class TestNormFloat:
    def test_int(self):
        assert _norm_float(42) == 42.0

    def test_string_number(self):
        assert _norm_float("3.14") == pytest.approx(3.14)

    def test_none(self):
        assert _norm_float(None) == 0.0

    def test_zero_string(self):
        assert _norm_float("0") == 0.0

    def test_invalid_string(self):
        assert _norm_float("abc") == 0.0


class TestSumDictCounter:
    def test_basic_sum(self):
        entries = [
            {"funcao_id": "op", "num_pessoas": 2},
            {"funcao_id": "op", "num_pessoas": 1},
            {"funcao_id": "aux", "num_pessoas": 3},
        ]
        result = dict(_sum_dict_counter(entries, "funcao_id", "num_pessoas"))
        assert result == {"op": 3, "aux": 3}

    def test_missing_key_skipped(self):
        entries = [{"num_pessoas": 2}, {"funcao_id": "op", "num_pessoas": 1}]
        result = dict(_sum_dict_counter(entries, "funcao_id", "num_pessoas"))
        assert result == {"op": 1}

    def test_empty_list(self):
        assert dict(_sum_dict_counter([], "funcao_id", "num_pessoas")) == {}

    def test_none_entries(self):
        assert dict(_sum_dict_counter(None, "funcao_id", "num_pessoas")) == {}


# ---------------------------------------------------------------------------
# Q1 helpers
# ---------------------------------------------------------------------------


class TestAq1ResolveRefEquipes:
    def test_equipes_detalhadas(self):
        ref = {"equipes_detalhadas": [{"item_id": "1"}]}
        assert _aq1_resolve_ref_equipes(ref) == [{"item_id": "1"}]

    def test_equipes_detalhes(self):
        ref = {"equipes": {"detalhes": [{"item_id": "2"}]}}
        assert _aq1_resolve_ref_equipes(ref) == [{"item_id": "2"}]

    def test_equipes_equipes(self):
        ref = {"equipes": {"equipes": [{"item_id": "3"}]}}
        assert _aq1_resolve_ref_equipes(ref) == [{"item_id": "3"}]

    def test_empty(self):
        assert _aq1_resolve_ref_equipes({}) == []

    def test_priority_equipes_detalhadas_over_detalhes(self):
        ref = {
            "equipes_detalhadas": [{"item_id": "a"}],
            "equipes": {"detalhes": [{"item_id": "b"}]},
        }
        result = _aq1_resolve_ref_equipes(ref)
        assert result == [{"item_id": "a"}]


class TestAq1BuildEqMap:
    def test_basic(self):
        equipes = [
            {
                "item_id": "eap-01",
                "funcoes": [{"funcao_id": "op", "num_pessoas": 2}],
                "equipamentos": [{"equip_id": "moto", "num_unidades": 1}],
            }
        ]
        result = _aq1_build_eq_map(equipes)
        assert "eap-01" in result
        assert result["eap-01"]["funcoes"] == {"op": 2}
        assert result["eap-01"]["equipamentos"] == {"moto": 1}

    def test_skip_missing_item_id(self):
        equipes = [{"funcoes": [{"funcao_id": "op", "num_pessoas": 1}]}]
        result = _aq1_build_eq_map(equipes)
        assert result == {}

    def test_empty_list(self):
        assert _aq1_build_eq_map([]) == {}

    def test_sum_same_funcao(self):
        equipes = [
            {
                "item_id": "eap-01",
                "funcoes": [
                    {"funcao_id": "op", "num_pessoas": 1},
                    {"funcao_id": "op", "num_pessoas": 2},
                ],
                "equipamentos": [],
            }
        ]
        result = _aq1_build_eq_map(equipes)
        assert result["eap-01"]["funcoes"] == {"op": 3}


# ---------------------------------------------------------------------------
# Q1 audit function
# ---------------------------------------------------------------------------


class TestAuditQ1InsumosequipEs:
    def _make_ref(self, eap=None, equipes=None):
        return {
            "eap": eap or [],
            "equipes_detalhadas": equipes or [],
        }

    def _make_cur(self, eap=None, equipes_diretas=None):
        return {
            "eap": eap or [],
            "equipes_diretas": equipes_diretas or [],
        }

    def test_passa_when_both_match(self):
        eap = [{"item_id": "eap-01", "cpu_id": "CPU-A"}]
        equipes = [
            {
                "item_id": "eap-01",
                "funcoes": [{"funcao_id": "op", "num_pessoas": 2}],
                "equipamentos": [],
            }
        ]
        ref = self._make_ref(eap=eap, equipes=equipes)
        cur = {
            "eap": eap,
            "equipes_diretas": equipes,
        }
        answer = _audit_q1_insumos_equipes(ref, cur)
        assert answer.status == "PASSA"
        assert answer.evidencia["cpus_iguais"] is True
        assert answer.evidencia["equipes_iguais"] is True

    def test_falha_when_cpu_differs(self):
        ref = {"eap": [{"item_id": "eap-01", "cpu_id": "CPU-A"}], "equipes_detalhadas": []}
        cur = {"eap": [{"item_id": "eap-01", "cpu_id": "CPU-B"}], "equipes_diretas": []}
        answer = _audit_q1_insumos_equipes(ref, cur)
        assert answer.status == "FALHA"
        assert answer.evidencia["cpus_iguais"] is False

    def test_falha_when_equipes_differ(self):
        eap = [{"item_id": "eap-01", "cpu_id": "CPU-A"}]
        ref = {
            "eap": eap,
            "equipes_detalhadas": [
                {
                    "item_id": "eap-01",
                    "funcoes": [{"funcao_id": "op", "num_pessoas": 3}],
                    "equipamentos": [],
                }
            ],
        }
        cur = {
            "eap": eap,
            "equipes_diretas": [
                {
                    "item_id": "eap-01",
                    "funcoes": [{"funcao_id": "op", "num_pessoas": 2}],
                    "equipamentos": [],
                }
            ],
        }
        answer = _audit_q1_insumos_equipes(ref, cur)
        assert answer.status == "FALHA"
        assert answer.evidencia["equipes_iguais"] is False

    def test_empty_both(self):
        answer = _audit_q1_insumos_equipes({}, {})
        assert answer.status == "PASSA"

    def test_uses_legacy_cpus_field(self):
        """Ref com cpus.itens_eap em vez de eap."""
        ref = {
            "cpus": {"itens_eap": [{"item_id": "eap-01", "cpu_id": "CPU-A"}]},
            "equipes_detalhadas": [],
        }
        cur = {"eap": [{"item_id": "eap-01", "cpu_id": "CPU-A"}], "equipes_diretas": []}
        answer = _audit_q1_insumos_equipes(ref, cur)
        assert answer.evidencia["cpus_iguais"] is True


# ---------------------------------------------------------------------------
# Q2 helpers and audit
# ---------------------------------------------------------------------------


class TestResolveCustoDireto:
    def test_resolve_ref_from_custo_direto_total(self):
        ref_resultado = {"custo_direto_total": 1000.0}
        ref_confronto = {}
        assert _resolve_ref_custo_direto(ref_resultado, ref_confronto) == 1000.0

    def test_resolve_ref_fallback_direto_equipes(self):
        ref_resultado = {"custo": {"direto_equipes": 500.0}}
        ref_confronto = {}
        assert _resolve_ref_custo_direto(ref_resultado, ref_confronto) == 500.0

    def test_resolve_ref_fallback_confronto(self):
        ref_resultado = {}
        ref_confronto = {"custo_direto": 750.0}
        assert _resolve_ref_custo_direto(ref_resultado, ref_confronto) == 750.0

    def test_resolve_ref_all_zero(self):
        assert _resolve_ref_custo_direto({}, {}) == 0.0

    def test_resolve_cur_from_direto_equipes(self):
        cur_res = {"custo": {"direto_equipes": 800.0}}
        assert _resolve_cur_custo_direto(cur_res) == 800.0

    def test_resolve_cur_fallback_custo_direto_total_equipes(self):
        cur_res = {"custo_direto_total_equipes": 600.0}
        assert _resolve_cur_custo_direto(cur_res) == 600.0

    def test_resolve_cur_zero(self):
        assert _resolve_cur_custo_direto({}) == 0.0


class TestAuditQ2CustoDireto:
    def test_passa_exact_match(self):
        ref = {"resultado": {"custo_direto_total": 1000.0}}
        cur = {"resultado": {"custo": {"direto_equipes": 1000.0}}}
        answer = _audit_q2_custo_direto(ref, cur)
        assert answer.status == "PASSA"
        assert answer.evidencia["delta"] == 0.0

    def test_passa_within_tolerance(self):
        ref = {"resultado": {"custo_direto_total": 1000.0}}
        cur = {"resultado": {"custo": {"direto_equipes": 1000.03}}}
        answer = _audit_q2_custo_direto(ref, cur)
        assert answer.status == "PASSA"

    def test_falha_beyond_tolerance(self):
        ref = {"resultado": {"custo_direto_total": 1000.0}}
        cur = {"resultado": {"custo": {"direto_equipes": 1200.0}}}
        answer = _audit_q2_custo_direto(ref, cur)
        assert answer.status == "FALHA"
        assert answer.evidencia["delta"] == pytest.approx(200.0)

    def test_zero_both(self):
        answer = _audit_q2_custo_direto({}, {})
        assert answer.status == "PASSA"

    def test_canonical_ref_format(self):
        ref = {
            "resultado": {
                "canonical": {"custo_direto_total": 900.0},
            }
        }
        cur = {"resultado": {"custo": {"direto_equipes": 900.0}}}
        answer = _audit_q2_custo_direto(ref, cur)
        assert answer.status == "PASSA"


# ---------------------------------------------------------------------------
# _extract_ref_item_subtotal
# ---------------------------------------------------------------------------


class TestExtractRefItemSubtotal:
    def test_subtotal_com_bdi_total(self):
        i = {"subtotal_com_bdi": {"total": 500.0}}
        assert _extract_ref_item_subtotal(i) == 500.0

    def test_subtotal_com_bdi_nested(self):
        i = {"subtotal": {"com_bdi": {"total": 300.0}}}
        assert _extract_ref_item_subtotal(i) == 300.0

    def test_total_projeto_sum(self):
        i = {
            "total_projeto": {
                "servicos": 100.0,
                "material": 50.0,
                "diesel": 20.0,
                "mo": 30.0,
            }
        }
        assert _extract_ref_item_subtotal(i) == 200.0

    def test_custo_unit_sbdi_times_quantitativo(self):
        i = {"custo_unit_sbdi": 10.0, "quantitativo": 5.0}
        assert _extract_ref_item_subtotal(i) == 50.0

    def test_empty_item(self):
        assert _extract_ref_item_subtotal({}) == 0.0


# ---------------------------------------------------------------------------
# Q3 helpers and audit
# ---------------------------------------------------------------------------


class TestAq3ResolveRefPlanejamento:
    def test_planejamento_detalhado(self):
        ref = {"planejamento_detalhado": [{"item_id": "1"}]}
        assert _aq3_resolve_ref_planejamento(ref) == [{"item_id": "1"}]

    def test_planejamento_itens(self):
        ref = {"planejamento": {"itens": [{"item_id": "2"}]}}
        assert _aq3_resolve_ref_planejamento(ref) == [{"item_id": "2"}]

    def test_cpus_itens_eap_fallback(self):
        ref = {"cpus": {"itens_eap": [{"item_id": "3"}]}}
        assert _aq3_resolve_ref_planejamento(ref) == [{"item_id": "3"}]

    def test_empty(self):
        assert _aq3_resolve_ref_planejamento({}) == []


class TestAq3BuildCurItems:
    def test_basic(self):
        cur = {
            "planejamento": [
                {"item_id": "eap-01", "subtotal": {"sem_bdi": {"total": 1000.0}}},
            ]
        }
        result = _aq3_build_cur_items(cur)
        assert result == {"eap-01": 1000.0}

    def test_missing_subtotal(self):
        cur = {"planejamento": [{"item_id": "eap-01"}]}
        result = _aq3_build_cur_items(cur)
        assert result == {"eap-01": 0.0}

    def test_empty(self):
        assert _aq3_build_cur_items({}) == {}


class TestAuditQ3Orcamento:
    def test_na_when_no_ref_planejamento(self):
        answer = _audit_q3_orcamento({}, {})
        assert answer.status == "N/A"
        assert answer.evidencia["qtd_itens"] == 0

    def test_passa_when_items_match(self):
        ref = {
            "planejamento_detalhado": [
                {"item_id": "eap-01", "subtotal_com_bdi": {"total": 1000.0}},
            ]
        }
        cur = {
            "planejamento": [
                {"item_id": "eap-01", "subtotal": {"sem_bdi": {"total": 1000.0}}},
            ]
        }
        answer = _audit_q3_orcamento(ref, cur)
        assert answer.status == "PASSA"

    def test_falha_when_mismatch(self):
        ref = {
            "planejamento_detalhado": [
                {"item_id": "eap-01", "subtotal_com_bdi": {"total": 1000.0}},
            ]
        }
        cur = {
            "planejamento": [
                {"item_id": "eap-01", "subtotal": {"sem_bdi": {"total": 1500.0}}},
            ]
        }
        answer = _audit_q3_orcamento(ref, cur)
        assert answer.status == "FALHA"
        assert abs(answer.evidencia["itens"]["eap-01"]) > 0

    def test_missing_cur_item_counted_as_zero(self):
        ref = {
            "planejamento_detalhado": [
                {"item_id": "eap-01", "subtotal_com_bdi": {"total": 500.0}},
            ]
        }
        cur = {"planejamento": []}
        answer = _audit_q3_orcamento(ref, cur)
        assert answer.status == "FALHA"
        assert answer.evidencia["itens"]["eap-01"] == -500.0


# ---------------------------------------------------------------------------
# Q4 helpers and audit
# ---------------------------------------------------------------------------


class TestResolveRefIndireto:
    def test_from_confronto(self):
        ref_resultado = {}
        ref_confronto = {"custo_indireto": 200.0}
        assert _resolve_ref_indireto(ref_resultado, ref_confronto) == 200.0

    def test_from_resultado_custo_indireto_total(self):
        ref_resultado = {"custo_indireto_total": 150.0}
        ref_confronto = {}
        assert _resolve_ref_indireto(ref_resultado, ref_confronto) == 150.0

    def test_from_resultado_indireto_prefix_sum(self):
        ref_resultado = {"custo": {"indireto_bdi": 100.0, "indireto_admin": 50.0, "direto": 999.0}}
        ref_confronto = {}
        assert _resolve_ref_indireto(ref_resultado, ref_confronto) == pytest.approx(150.0)

    def test_zero(self):
        assert _resolve_ref_indireto({}, {}) == 0.0


class TestAq4ResolveRefResultado:
    def test_canonical_path(self):
        ref = {"resultado": {"canonical": {"custo_indireto_total": 300.0}}}
        assert _aq4_resolve_ref_resultado(ref) == {"custo_indireto_total": 300.0}

    def test_direct_path(self):
        ref = {"resultado": {"custo_indireto_total": 300.0}}
        assert _aq4_resolve_ref_resultado(ref) == {"custo_indireto_total": 300.0}

    def test_empty(self):
        assert _aq4_resolve_ref_resultado({}) == {}


class TestAq4IndiretoFallback:
    def test_sums_prefixed_keys(self):
        cur = {"resultado": {"custo": {"indireto_x": 100.0, "indireto_y": 50.0, "direto": 999.0}}}
        assert _aq4_indireto_fallback(cur) == pytest.approx(150.0)

    def test_no_indireto_keys(self):
        cur = {"resultado": {"custo": {"direto": 100.0}}}
        assert _aq4_indireto_fallback(cur) == 0.0

    def test_empty(self):
        assert _aq4_indireto_fallback({}) == 0.0


class TestAuditQ4Indiretos:
    def test_passa_exact(self):
        ref = {"resultado": {"canonical": {"custo_indireto_total": 200.0}}}
        cur = {"resultado": {"custo_indireto_total": 200.0}}
        answer = _audit_q4_indiretos(ref, cur)
        assert answer.status == "PASSA"

    def test_falha_beyond_tolerance(self):
        ref = {"resultado": {"canonical": {"custo_indireto_total": 200.0}}}
        cur = {"resultado": {"custo_indireto_total": 300.0}}
        answer = _audit_q4_indiretos(ref, cur)
        assert answer.status == "FALHA"
        assert answer.evidencia["delta"] == pytest.approx(100.0)

    def test_fallback_prefix_sum(self):
        ref = {"resultado": {"canonical": {}}}
        cur = {"resultado": {"custo": {"indireto_adm": 100.0}}}
        answer = _audit_q4_indiretos(ref, cur)
        # ref=0, cur=100 → beyond tol
        assert answer.status == "FALHA"

    def test_zero_both_passa(self):
        answer = _audit_q4_indiretos({}, {})
        assert answer.status == "PASSA"

    def test_uses_confronto_for_ref(self):
        ref = {
            "resultado": {
                "benchmark_confronto_referencia": {"custo_indireto": 500.0},
            }
        }
        cur = {"resultado": {"custo_indireto_total": 500.0}}
        answer = _audit_q4_indiretos(ref, cur)
        assert answer.status == "PASSA"


# ---------------------------------------------------------------------------
# Q5 helpers and audit
# ---------------------------------------------------------------------------


class TestBuildPeMismatch:
    def _make_pe_item(self, custo_fixo, custo_venda, delta):
        return {"custo_fixo_equipe": custo_fixo, "custo_venda_cpu": custo_venda, "delta": delta}

    def test_no_mismatch(self):
        ref_pe = {"eap-01": self._make_pe_item(100.0, 200.0, 100.0)}
        cur_pe = {"eap-01": self._make_pe_item(100.0, 200.0, 100.0)}
        result = _build_pe_mismatch(ref_pe, cur_pe)
        assert result == {}

    def test_mismatch_on_delta(self):
        ref_pe = {"eap-01": self._make_pe_item(100.0, 200.0, 100.0)}
        cur_pe = {"eap-01": self._make_pe_item(100.0, 200.0, 50.0)}
        result = _build_pe_mismatch(ref_pe, cur_pe)
        assert "eap-01" in result
        assert "delta" in result["eap-01"]

    def test_no_common_items(self):
        ref_pe = {"eap-01": self._make_pe_item(100.0, 200.0, 100.0)}
        cur_pe = {"eap-02": self._make_pe_item(100.0, 200.0, 100.0)}
        result = _build_pe_mismatch(ref_pe, cur_pe)
        assert result == {}

    def test_within_tol_not_reported(self):
        ref_pe = {"eap-01": self._make_pe_item(100.0, 200.0, 100.0)}
        # delta within _TOL (0.05)
        cur_pe = {"eap-01": self._make_pe_item(100.0, 200.0, 100.04)}
        result = _build_pe_mismatch(ref_pe, cur_pe)
        assert result == {}


class TestAq5BuildPeMap:
    def test_basic(self):
        items = [{"item_id": "eap-01", "delta": 100.0}, {"item_id": "eap-02", "delta": 50.0}]
        result = _aq5_build_pe_map(items)
        assert set(result.keys()) == {"eap-01", "eap-02"}

    def test_skip_missing_item_id(self):
        items = [{"delta": 100.0}, {"item_id": "eap-01", "delta": 50.0}]
        result = _aq5_build_pe_map(items)
        assert list(result.keys()) == ["eap-01"]

    def test_none_input(self):
        assert _aq5_build_pe_map(None) == {}

    def test_empty_list(self):
        assert _aq5_build_pe_map([]) == {}


class TestAuditQ5PontoEquilibrio:
    def _make_pe_item(self, item_id, custo_fixo=100.0, custo_venda=200.0, delta=100.0):
        return {
            "item_id": item_id,
            "custo_fixo_equipe": custo_fixo,
            "custo_venda_cpu": custo_venda,
            "delta": delta,
        }

    def test_na_when_no_ref_pe(self):
        answer = _audit_q5_ponto_equilibrio({}, {})
        assert answer.status == "N/A"
        assert "motivo" in answer.evidencia

    def test_passa_full_match(self):
        item = self._make_pe_item("eap-01")
        ref = {"ponto_equilibrio": [item]}
        cur = {"ponto_equilibrio": [item]}
        answer = _audit_q5_ponto_equilibrio(ref, cur)
        assert answer.status == "PASSA"
        assert answer.evidencia["mismatch"] == {}

    def test_falha_missing_ref_items(self):
        """Ref has items that cur doesn't have."""
        item = self._make_pe_item("eap-01")
        ref = {"ponto_equilibrio": [item]}
        cur = {"ponto_equilibrio": []}
        answer = _audit_q5_ponto_equilibrio(ref, cur)
        assert answer.status == "FALHA"
        assert "eap-01" in answer.evidencia["missing_ref"]

    def test_falha_extra_cur_items(self):
        """Cur has items that ref doesn't have."""
        item_ref = self._make_pe_item("eap-01")
        item_cur_extra = self._make_pe_item("eap-02")
        ref = {"ponto_equilibrio": [item_ref]}
        cur = {"ponto_equilibrio": [item_ref, item_cur_extra]}
        answer = _audit_q5_ponto_equilibrio(ref, cur)
        assert answer.status == "FALHA"
        assert "eap-02" in answer.evidencia["missing_cur"]

    def test_falha_numeric_mismatch(self):
        item_ref = self._make_pe_item("eap-01", custo_fixo=100.0, custo_venda=200.0, delta=100.0)
        item_cur = self._make_pe_item("eap-01", custo_fixo=100.0, custo_venda=200.0, delta=50.0)
        ref = {"ponto_equilibrio": [item_ref]}
        cur = {"ponto_equilibrio": [item_cur]}
        answer = _audit_q5_ponto_equilibrio(ref, cur)
        assert answer.status == "FALHA"
        assert "eap-01" in answer.evidencia["mismatch"]

    def test_ref_count_in_evidencia(self):
        items = [self._make_pe_item("eap-01"), self._make_pe_item("eap-02")]
        ref = {"ponto_equilibrio": items}
        cur = {"ponto_equilibrio": items}
        answer = _audit_q5_ponto_equilibrio(ref, cur)
        assert answer.evidencia["ref_count"] == 2
        assert answer.evidencia["concilium_count"] == 2


# ---------------------------------------------------------------------------
# Q6 helpers and audit
# ---------------------------------------------------------------------------


class TestBrtPrecoVendaTriple:
    def test_from_confronto(self):
        ref_confronto = {"preco_venda": 5000.0}
        ref_resultado = {}
        cur_res = {"preco_venda_total": 4800.0}
        ref_pv, cur_pv = _brt_preco_venda_triple(ref_resultado, ref_confronto, cur_res)
        assert ref_pv == 5000.0
        assert cur_pv == 4800.0

    def test_fallback_ref_preco_venda_total(self):
        ref_resultado = {"preco_venda_total": 3000.0}
        ref_confronto = {}
        cur_res = {}
        ref_pv, cur_pv = _brt_preco_venda_triple(ref_resultado, ref_confronto, cur_res)
        assert ref_pv == 3000.0

    def test_fallback_ref_venda_total_com_bdi(self):
        ref_resultado = {"venda": {"total_com_bdi": 2500.0}}
        ref_confronto = {}
        cur_res = {}
        ref_pv, _ = _brt_preco_venda_triple(ref_resultado, ref_confronto, cur_res)
        assert ref_pv == 2500.0

    def test_cur_venda_total_custo_plus_catalogo(self):
        ref_resultado = {}
        ref_confronto = {}
        cur_res = {"venda": {"total_custo_plus_catalogo": 1500.0}}
        _, cur_pv = _brt_preco_venda_triple(ref_resultado, ref_confronto, cur_res)
        assert cur_pv == 1500.0

    def test_zeros(self):
        ref_pv, cur_pv = _brt_preco_venda_triple({}, {}, {})
        assert ref_pv == 0.0
        assert cur_pv == 0.0


class TestBrtCustoTriple:
    def test_from_confronto(self):
        ref_confronto = {"custo_total": 4000.0}
        ref_resultado = {}
        cur_res = {"custo_total": 4000.0}
        ref_ct, cur_ct = _brt_custo_triple(ref_resultado, ref_confronto, cur_res)
        assert ref_ct == 4000.0
        assert cur_ct == 4000.0

    def test_fallback_ref_custo_total(self):
        ref_resultado = {"custo_total": 3500.0}
        ref_confronto = {}
        cur_res = {}
        ref_ct, _ = _brt_custo_triple(ref_resultado, ref_confronto, cur_res)
        assert ref_ct == 3500.0

    def test_fallback_custo_total_nested(self):
        ref_resultado = {"custo": {"total": 2500.0}}
        ref_confronto = {}
        cur_res = {"custo": {"total": 2000.0}}
        ref_ct, cur_ct = _brt_custo_triple(ref_resultado, ref_confronto, cur_res)
        assert ref_ct == 2500.0
        assert cur_ct == 2000.0

    def test_zeros(self):
        ref_ct, cur_ct = _brt_custo_triple({}, {}, {})
        assert ref_ct == 0.0
        assert cur_ct == 0.0


class TestBuildResultadoTriples:
    def test_basic_structure(self):
        ref_resultado = {
            "margem_bruta": 0.25,
        }
        ref_confronto = {
            "preco_venda": 1000.0,
            "custo_total": 750.0,
        }
        cur_res = {
            "preco_venda_total": 1000.0,
            "custo_total": 750.0,
            "margem_bruta": 0.25,
        }
        triples = _build_resultado_triples(ref_resultado, ref_confronto, cur_res)
        assert "preco_venda_total" in triples
        assert "custo_total" in triples
        assert "margem_bruta" in triples
        assert triples["preco_venda_total"] == (1000.0, 1000.0)
        assert triples["custo_total"] == (750.0, 750.0)

    def test_derived_margem_when_no_explicit(self):
        """Margem derivada de (preco_venda - custo_total)/preco_venda."""
        ref_resultado = {}
        ref_confronto = {"preco_venda": 1000.0, "custo_total": 800.0}
        cur_res = {"margem_pct": 0.2}
        triples = _build_resultado_triples(ref_resultado, ref_confronto, cur_res)
        ref_margem, _ = triples["margem_bruta"]
        assert ref_margem == pytest.approx(0.2)

    def test_zero_preco_venda_no_division(self):
        ref_resultado = {}
        ref_confronto = {"preco_venda": 0.0, "custo_total": 0.0}
        cur_res = {}
        triples = _build_resultado_triples(ref_resultado, ref_confronto, cur_res)
        ref_margem, cur_margem = triples["margem_bruta"]
        assert ref_margem == 0.0
        assert cur_margem == 0.0


class TestAuditQ6Resultado:
    def test_passa_when_all_match(self):
        ref = {
            "resultado": {
                "canonical": {
                    "preco_venda_total": 1000.0,
                    "custo_total": 750.0,
                    "margem_bruta": 0.25,
                }
            }
        }
        cur = {
            "resultado": {
                "preco_venda_total": 1000.0,
                "custo_total": 750.0,
                "margem_bruta": 0.25,
            }
        }
        answer = _audit_q6_resultado(ref, cur)
        assert answer.status == "PASSA"

    def test_falha_when_preco_venda_differs(self):
        ref = {
            "resultado": {
                "benchmark_confronto_referencia": {
                    "preco_venda": 1000.0,
                    "custo_total": 750.0,
                },
                "margem_bruta": 0.25,
            }
        }
        cur = {
            "resultado": {
                "preco_venda_total": 1200.0,
                "custo_total": 750.0,
                "margem_bruta": 0.25,
            }
        }
        answer = _audit_q6_resultado(ref, cur)
        assert answer.status == "FALHA"

    def test_zero_all_passes(self):
        answer = _audit_q6_resultado({}, {})
        assert answer.status == "PASSA"

    def test_evidencia_has_deltas(self):
        ref = {
            "resultado": {
                "benchmark_confronto_referencia": {
                    "preco_venda": 1000.0,
                    "custo_total": 800.0,
                }
            }
        }
        cur = {
            "resultado": {
                "preco_venda_total": 1000.0,
                "custo_total": 800.0,
                "margem_bruta": 0.2,
            }
        }
        answer = _audit_q6_resultado(ref, cur)
        assert "deltas" in answer.evidencia
        assert "preco_venda_total" in answer.evidencia["deltas"]


# ---------------------------------------------------------------------------
# run_audit end-to-end with mocked I/O
# ---------------------------------------------------------------------------


def _make_complete_ref():
    """Minimal reference dict that passes all six questions."""
    return {
        "projeto": "TesteProjeto",
        "eap": [{"item_id": "eap-01", "cpu_id": "CPU-A"}],
        "equipes_detalhadas": [
            {
                "item_id": "eap-01",
                "funcoes": [{"funcao_id": "op", "num_pessoas": 2}],
                "equipamentos": [],
            }
        ],
        "resultado": {
            "custo_direto_total": 1000.0,
            "custo_indireto_total": 200.0,
            "preco_venda_total": 1500.0,
            "custo_total": 1200.0,
            "margem_bruta": 0.2,
        },
        "planejamento_detalhado": [
            {"item_id": "eap-01", "subtotal_com_bdi": {"total": 1000.0}},
        ],
        "ponto_equilibrio": [
            {
                "item_id": "eap-01",
                "custo_fixo_equipe": 100.0,
                "custo_venda_cpu": 200.0,
                "delta": 100.0,
            }
        ],
    }


def _make_complete_cur():
    """Minimal current canonical dict that matches the reference."""
    return {
        "eap": [{"item_id": "eap-01", "cpu_id": "CPU-A"}],
        "equipes_diretas": [
            {
                "item_id": "eap-01",
                "funcoes": [{"funcao_id": "op", "num_pessoas": 2}],
                "equipamentos": [],
            }
        ],
        "resultado": {
            "custo": {"direto_equipes": 1000.0},
            "custo_indireto_total": 200.0,
            "preco_venda_total": 1500.0,
            "custo_total": 1200.0,
            "margem_bruta": 0.2,
        },
        "planejamento": [
            {"item_id": "eap-01", "subtotal": {"sem_bdi": {"total": 1000.0}}},
        ],
        "ponto_equilibrio": [
            {
                "item_id": "eap-01",
                "custo_fixo_equipe": 100.0,
                "custo_venda_cpu": 200.0,
                "delta": 100.0,
            }
        ],
    }


class TestRunAudit:
    def _patch_run_audit(self, ref_data, cur_data):
        """Helper to patch run_audit so it never touches the filesystem.

        run_audit calls _load_json for: (1) ref, (2) optionally extr, (3) cur.
        We patch Path.exists so that extracao_intermediarios.json is absent
        (to keep the call count predictable: ref → cur only).
        """
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True

        def _mock_exists(self_path):
            if "extracao_intermediarios" in str(self_path):
                return False
            return True

        with (
            patch(
                "concilium.application.benchmarks.analysis.audit_six_questions._load_json",
                side_effect=[ref_data, cur_data],
            ),
            patch(
                "concilium.application.benchmarks.analysis.audit_six_questions._resolve_canonical_path",
                return_value=mock_path,
            ),
            patch.object(Path, "exists", _mock_exists),
        ):
            return run_audit("TEST-SLUG")

    def test_resumo_all_passa(self):
        ref = _make_complete_ref()
        cur = _make_complete_cur()
        result = self._patch_run_audit(ref, cur)
        assert result["slug"] == "TEST-SLUG"
        assert result["resumo"]["total"] == 6
        assert result["resumo"]["falha"] == 0

    def test_resumo_keys_present(self):
        ref = _make_complete_ref()
        cur = _make_complete_cur()
        result = self._patch_run_audit(ref, cur)
        assert "passa" in result["resumo"]
        assert "falha" in result["resumo"]
        assert "na" in result["resumo"]
        assert "total" in result["resumo"]

    def test_resumo_na_count(self):
        """With no ponto_equilibrio, Q5 should be N/A."""
        ref = _make_complete_ref()
        del ref["ponto_equilibrio"]
        cur = _make_complete_cur()
        result = self._patch_run_audit(ref, cur)
        assert result["resumo"]["na"] >= 1

    def test_respostas_length(self):
        ref = _make_complete_ref()
        cur = _make_complete_cur()
        result = self._patch_run_audit(ref, cur)
        assert len(result["respostas"]) == 6

    def test_respostas_structure(self):
        ref = _make_complete_ref()
        cur = _make_complete_cur()
        result = self._patch_run_audit(ref, cur)
        for r in result["respostas"]:
            assert "pergunta" in r
            assert "status" in r
            assert "evidencia" in r

    def test_file_not_found_when_no_ref(self):
        """run_audit raises FileNotFoundError when referencia.json not found."""
        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(FileNotFoundError):
                run_audit("MISSING-SLUG")

    def test_extr_json_optional(self):
        """run_audit works when extracao_intermediarios.json doesn't exist."""
        ref = _make_complete_ref()
        cur = _make_complete_cur()

        call_count = [0]

        def _load_side_effect(path):
            call_count[0] += 1
            if call_count[0] == 1:
                return ref
            return cur

        mock_canonical = MagicMock(spec=Path)
        mock_canonical.exists.return_value = True

        with (
            patch(
                "concilium.application.benchmarks.analysis.audit_six_questions._load_json",
                side_effect=_load_side_effect,
            ),
            patch(
                "concilium.application.benchmarks.analysis.audit_six_questions._resolve_canonical_path",
                return_value=mock_canonical,
            ),
        ):
            # Make referencia.json exist but extracao_intermediarios.json not exist
            original_exists = Path.exists

            def mock_exists(self):
                if "extracao_intermediarios" in str(self):
                    return False
                return True

            with patch.object(Path, "exists", mock_exists):
                result = run_audit("TEST-SLUG")
        assert result["slug"] == "TEST-SLUG"

    def test_falha_counter_increments(self):
        """When cur data diverges from ref, falha counter increases."""
        ref = _make_complete_ref()
        # Make cur have very different custo_direto to force Q2 FALHA
        cur = _make_complete_cur()
        cur["resultado"]["custo"]["direto_equipes"] = 9999999.0

        result = self._patch_run_audit(ref, cur)
        assert result["resumo"]["falha"] >= 1
