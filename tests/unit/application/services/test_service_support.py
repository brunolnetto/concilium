"""Coverage batch 4 — small missing-line targets across many files."""

from __future__ import annotations

from types import SimpleNamespace

# service_support.py line 25: build_summary with resultado=None → short dict
# ---------------------------------------------------------------------------


class TestBuildSummaryResultadoNone:
    def test_resultado_none_returns_short_dict(self):
        """No result → counters plus a NOT-evaluated exact view (no legacy key, no number)."""
        from concilium.application.services.service_support import build_summary

        pe1 = SimpleNamespace(status_validacao="ERRO")
        pe2 = SimpleNamespace(status_validacao="AVISO")
        canonical = SimpleNamespace(resultado=None, ponto_equilibrio=[pe1, pe2])
        result = build_summary(canonical)
        assert set(result) == {"financeiro_exato", "pe_deficit_items", "pe_alerta_items"}
        assert result["pe_deficit_items"] == 1 and result["pe_alerta_items"] == 1
        assert result["financeiro_exato"]["status"] == "NAO_AVALIADO"
        assert [r["code"] for r in result["financeiro_exato"]["reasons"]] == ["RESULTADO_AUSENTE"]
        assert "preco_venda_total" not in result


# ---------------------------------------------------------------------------





# service_support.py line 25: build_summary returns early when result is None
# ---------------------------------------------------------------------------


class TestServiceSupportBuildSummaryNoneResult:
    def test_returns_partial_dict_when_no_resultado(self):
        """Line 25: canonical has no resultado → result=None → early return dict."""
        from concilium.application.services.service_support import build_summary

        canonical = SimpleNamespace(ponto_equilibrio=[])
        result = build_summary(canonical)
        assert "pe_deficit_items" in result
        assert "pe_alerta_items" in result
        assert "custo_total" not in result  # early return, not full dict


# ---------------------------------------------------------------------------





# ─── service_support.py (also covered in batch4, adding extra paths here) ─────


class TestServiceSupport:
    def test_deep_merge_nested(self):
        from concilium.application.services.service_support import deep_merge

        result = deep_merge({"a": {"x": 1, "y": 2}}, {"a": {"y": 99}})
        assert result["a"]["x"] == 1
        assert result["a"]["y"] == 99

    def test_build_summary_none_returns_empty(self):
        from concilium.application.services.service_support import build_summary

        assert build_summary(None) == {}





# ─── #206 W3-A: the summary is built on the exact financial view ──────────────


class TestBuildSummaryExactView:
    LEGACY_KEYS = ("preco_venda_total", "custo_total", "resultado_bruto", "margem_pct", "status_margem")

    def test_evaluated_summary_carries_the_exact_view_and_no_legacy_key(self):
        from concilium.application.scheduling.exact_financial_view import build_exact_financial_view
        from concilium.application.services.service_support import build_summary
        from tests.support.exact_financial import canonical, evaluated_resultado

        can = canonical(evaluated_resultado())
        can.ponto_equilibrio = [SimpleNamespace(status_validacao="ERRO")]
        summary = build_summary(can)

        assert set(summary) == {"financeiro_exato", "pe_deficit_items", "pe_alerta_items"}
        assert not set(self.LEGACY_KEYS) & set(summary)
        assert summary["financeiro_exato"] == build_exact_financial_view(can)
        assert summary["financeiro_exato"]["status"] == "AVALIADO"
        assert summary["financeiro_exato"]["price"] == "159/5"
        assert summary["financeiro_exato"]["certificate"] is None  # lives at run level, revalidated on read
        assert summary["pe_deficit_items"] == 1 and summary["pe_alerta_items"] == 0

    def test_summary_is_json_persistable_without_floats(self):
        import json

        from concilium.application.services.service_support import build_summary
        from tests.support.exact_financial import canonical, evaluated_resultado

        summary = build_summary(canonical(evaluated_resultado()))
        dumped = json.dumps(summary)
        assert json.loads(dumped) == summary
        assert "e+30" not in dumped and "12345.678" not in dumped and "NaN" not in dumped

    def test_not_evaluated_summary_has_reasons_and_no_number(self):
        from concilium.application.services.service_support import build_summary
        from tests.support.exact_financial import canonical, contract, unknown_resultado

        summary = build_summary(canonical(unknown_resultado(), contracts=[contract("c-eq", witnessed=False)], p18=None))
        view = summary["financeiro_exato"]
        assert view["status"] == "NAO_AVALIADO"
        assert [r["code"] for r in view["reasons"]] == ["CONTRATO_SEM_TESTEMUNHA_P16", "DECLARACAO_PRECO_AUSENTE"]
        assert set(view) == {"schema", "status", "reasons", "certificate"}

    def test_compare_versions_reports_exact_deltas_or_not_evaluated(self):
        from unittest.mock import MagicMock, patch

        from concilium.application.services.project.project_service import ProjectService
        from tests.support.exact_financial import canonical, evaluated_resultado, unknown_resultado

        left = canonical(evaluated_resultado())
        right = canonical(evaluated_resultado(minimum_profit_margin=None))
        right.resultado.pricing_diagnostics["total_cost"] = "53/2"
        project = MagicMock()
        project.meta = {"version_history": {}}
        versions = {"v1": left, "v2": right, "v3": canonical(unknown_resultado())}
        project.load_canonical.side_effect = versions.__getitem__
        repo = MagicMock()
        repo.get_project.return_value = project
        svc = ProjectService.__new__(ProjectService)
        svc._repository = repo
        target = "concilium.application.services.project.project_service._versions_artifacts.resolve_compare_version"
        with patch(target, side_effect=lambda p, v: v):
            evaluated = svc.compare_versions("p1", "v1", "v2")
            not_evaluated = svc.compare_versions("p1", "v1", "v3")

        assert set(evaluated["deltas"]) == {"pe_deficit_items", "financeiro_exato"}
        assert evaluated["deltas"]["financeiro_exato"]["status"] == "AVALIADO"
        assert evaluated["deltas"]["financeiro_exato"]["deltas"]["custo_total"] == "1"
        assert evaluated["deltas"]["financeiro_exato"]["deltas"]["preco"] == "0"
        assert not set(self.LEGACY_KEYS) & (set(evaluated["left"]) | set(evaluated["deltas"]))

        exact = not_evaluated["deltas"]["financeiro_exato"]
        assert exact["status"] == "NAO_AVALIADO"
        assert all(value is None for value in exact["deltas"].values())
        assert [r["side"] for r in exact["reasons"]] == ["right"]
