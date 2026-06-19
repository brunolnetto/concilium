"""Tests for src/concilium/application/benchmarks/report_printer.py"""

from __future__ import annotations

from concilium.application.benchmarks.report.report_printer import (
    BenchmarkReportPrinter,
    _print_pe_ferramenta,
    _print_pe_referencia,
)

# ---------------------------------------------------------------------------
# _print_pe_referencia
# ---------------------------------------------------------------------------


class TestPrintPeReferencia:
    def test_none_returns_early(self, capsys):
        _print_pe_referencia(None)
        out = capsys.readouterr().out
        assert out == ""

    def test_empty_dict_returns_early(self, capsys):
        _print_pe_referencia({})
        out = capsys.readouterr().out
        assert out == ""

    def test_prints_header(self, capsys):
        _print_pe_referencia({"total_hc": 10, "total_custo_fixo": 5000.0, "equipes": 3})
        out = capsys.readouterr().out
        assert "Ponto de Equilibrio (referencia)" in out

    def test_prints_total_hc(self, capsys):
        _print_pe_referencia({"total_hc": 42})
        out = capsys.readouterr().out
        assert "42" in out

    def test_prints_custo_fixo(self, capsys):
        _print_pe_referencia({"total_custo_fixo": 12345.67})
        out = capsys.readouterr().out
        assert "12,345.67" in out

    def test_custo_fixo_none_defaults_to_zero(self, capsys):
        _print_pe_referencia({"total_custo_fixo": None})
        out = capsys.readouterr().out
        assert "0.00" in out

    def test_prints_equipes(self, capsys):
        _print_pe_referencia({"equipes": 7})
        out = capsys.readouterr().out
        assert "7" in out

    def test_missing_keys_show_question_mark(self, capsys):
        _print_pe_referencia({"dummy": 1})  # non-empty so not early-return
        out = capsys.readouterr().out
        assert "?" in out


# ---------------------------------------------------------------------------
# _print_pe_ferramenta
# ---------------------------------------------------------------------------


class TestPrintPeFerramenta:
    def test_none_returns_early(self, capsys):
        _print_pe_ferramenta(None)
        assert capsys.readouterr().out == ""

    def test_empty_dict_returns_early(self, capsys):
        _print_pe_ferramenta({})
        assert capsys.readouterr().out == ""

    def test_prints_header(self, capsys):
        _print_pe_ferramenta({"total_hc": 5})
        out = capsys.readouterr().out
        assert "Ponto de Equilibrio Estrutural (Ferramenta)" in out

    def test_prints_hc_fields(self, capsys):
        _print_pe_ferramenta(
            {
                "total_hc_operacional": 10,
                "total_hc_indireto": 2,
                "total_hc": 12,
            }
        )
        out = capsys.readouterr().out
        assert "10" in out
        assert "2" in out
        assert "12" in out

    def test_prints_custo_fixo_mensal(self, capsys):
        _print_pe_ferramenta({"custo_fixo_mensal": 9999.99})
        out = capsys.readouterr().out
        assert "9,999.99" in out

    def test_prints_custo_fixo_total(self, capsys):
        _print_pe_ferramenta({"custo_fixo_total": 199999.00})
        out = capsys.readouterr().out
        assert "199,999.00" in out

    def test_prints_equipes(self, capsys):
        _print_pe_ferramenta({"equipes": 4})
        out = capsys.readouterr().out
        assert "4" in out

    def test_missing_custo_fixo_defaults_to_zero(self, capsys):
        _print_pe_ferramenta({"custo_fixo_mensal": None, "custo_fixo_total": None})
        out = capsys.readouterr().out
        assert "0.00" in out


# ---------------------------------------------------------------------------
# BenchmarkReportPrinter._print_header
# ---------------------------------------------------------------------------


class TestPrintHeader:
    def setup_method(self):
        self.printer = BenchmarkReportPrinter()

    def test_basic_header(self, capsys):
        report = {"projeto": "TestProject"}
        self.printer._print_header(report)
        out = capsys.readouterr().out
        assert "TestProject" in out
        assert "RELATORIO DE CONFRONTO" in out

    def test_status_final_from_report(self, capsys):
        report = {"projeto": "P", "status_final": "APROVADO", "quality_gates": {}}
        self.printer._print_header(report)
        out = capsys.readouterr().out
        assert "APROVADO" in out

    def test_status_final_from_quality_gates(self, capsys):
        report = {"projeto": "P", "quality_gates": {"decision": "REPROVADO"}}
        self.printer._print_header(report)
        out = capsys.readouterr().out
        assert "REPROVADO" in out

    def test_worst_severity_shown(self, capsys):
        report = {
            "projeto": "P",
            "status_final": "APROVADO",
            "quality_gates": {"worst_severity": "S2"},
        }
        self.printer._print_header(report)
        out = capsys.readouterr().out
        assert "S2" in out

    def test_worst_severity_defaults_to_s0(self, capsys):
        report = {
            "projeto": "P",
            "status_final": "OK",
            "quality_gates": {},
        }
        self.printer._print_header(report)
        out = capsys.readouterr().out
        assert "S0" in out

    def test_critical_metric_over_10pct_shown(self, capsys):
        report = {
            "projeto": "P",
            "status_final": "OK",
            "quality_gates": {"critical_metric_over_10pct": True},
        }
        self.printer._print_header(report)
        out = capsys.readouterr().out
        assert "BLOQUEIO" in out

    def test_critical_metric_false_not_shown(self, capsys):
        report = {
            "projeto": "P",
            "status_final": "OK",
            "quality_gates": {"critical_metric_over_10pct": False},
        }
        self.printer._print_header(report)
        out = capsys.readouterr().out
        assert "BLOQUEIO" not in out

    def test_no_status_final(self, capsys):
        report = {"projeto": "P", "quality_gates": {}}
        self.printer._print_header(report)
        out = capsys.readouterr().out
        assert "GATE" not in out


# ---------------------------------------------------------------------------
# BenchmarkReportPrinter._print_referencia
# ---------------------------------------------------------------------------


class TestPrintReferencia:
    def setup_method(self):
        self.printer = BenchmarkReportPrinter()

    def test_no_referencia_returns_early(self, capsys):
        self.printer._print_referencia({})
        assert capsys.readouterr().out == ""

    def test_none_referencia_returns_early(self, capsys):
        self.printer._print_referencia({"referencia": None})
        assert capsys.readouterr().out == ""

    def test_prints_referencia_header(self, capsys):
        confronto = {"referencia": {"custo_direto": 1000.0}}
        self.printer._print_referencia(confronto)
        out = capsys.readouterr().out
        assert "Referencia (planilha real)" in out

    def test_prints_value(self, capsys):
        confronto = {"referencia": {"custo_direto": 5000.0}}
        self.printer._print_referencia(confronto)
        out = capsys.readouterr().out
        assert "5,000.00" in out

    def test_none_value_shows_not_available(self, capsys):
        confronto = {"referencia": {"custo_direto": None}}
        self.printer._print_referencia(confronto)
        out = capsys.readouterr().out
        assert "nao disponivel" in out


# ---------------------------------------------------------------------------
# BenchmarkReportPrinter._print_ferramenta
# ---------------------------------------------------------------------------


class TestPrintFerramenta:
    def setup_method(self):
        self.printer = BenchmarkReportPrinter()

    def test_no_ferramenta_returns_early(self, capsys):
        self.printer._print_ferramenta({})
        assert capsys.readouterr().out == ""

    def test_none_ferramenta_key_returns_early(self, capsys):
        # None is falsy so the guard on line 53 triggers an early-return — no output at all
        self.printer._print_ferramenta({"ferramenta": None})
        out = capsys.readouterr().out
        assert out == ""

    def test_empty_ferramenta_returns_early(self, capsys):
        # Empty dict is falsy so the guard on line 53 triggers an early-return — no output at all
        self.printer._print_ferramenta({"ferramenta": {}})
        out = capsys.readouterr().out
        assert out == ""

    def test_custo_direto_shown(self, capsys):
        confronto = {"ferramenta": {"custo_direto": 100000.0}}
        self.printer._print_ferramenta(confronto)
        out = capsys.readouterr().out
        assert "100,000.00" in out

    def test_custo_direto_none_shows_not_available(self, capsys):
        confronto = {"ferramenta": {"custo_direto": None}}
        self.printer._print_ferramenta(confronto)
        out = capsys.readouterr().out
        assert "nao disponivel" in out

    def test_custo_execucao_pool_shown(self, capsys):
        confronto = {"ferramenta": {"custo_execucao_pool": 55000.0}}
        self.printer._print_ferramenta(confronto)
        out = capsys.readouterr().out
        assert "55,000.00" in out

    def test_custo_execucao_pool_none(self, capsys):
        confronto = {"ferramenta": {"custo_execucao_pool": None}}
        self.printer._print_ferramenta(confronto)
        out = capsys.readouterr().out
        assert "nao disponivel" in out

    def test_custo_indireto_shown(self, capsys):
        confronto = {"ferramenta": {"custo_indireto": 20000.0}}
        self.printer._print_ferramenta(confronto)
        out = capsys.readouterr().out
        assert "20,000.00" in out

    def test_custo_indireto_none(self, capsys):
        confronto = {"ferramenta": {"custo_indireto": None}}
        self.printer._print_ferramenta(confronto)
        out = capsys.readouterr().out
        assert "nao disponivel" in out

    def test_preco_venda_shown(self, capsys):
        confronto = {"ferramenta": {"preco_venda": 130000.0}}
        self.printer._print_ferramenta(confronto)
        out = capsys.readouterr().out
        assert "130,000.00" in out

    def test_preco_venda_none(self, capsys):
        confronto = {"ferramenta": {"preco_venda": None}}
        self.printer._print_ferramenta(confronto)
        out = capsys.readouterr().out
        assert "nao disponivel" in out

    def test_bdi_shown_as_percent(self, capsys):
        confronto = {"ferramenta": {"bdi_lucro_impostos": 0.25}}
        self.printer._print_ferramenta(confronto)
        out = capsys.readouterr().out
        assert "25.00%" in out

    def test_bdi_none_shows_na(self, capsys):
        confronto = {"ferramenta": {"bdi_lucro_impostos": None}}
        self.printer._print_ferramenta(confronto)
        out = capsys.readouterr().out
        assert "N/A" in out

    def test_preco_venda_catalogo_shown_when_present(self, capsys):
        confronto = {"ferramenta": {"preco_venda_catalogo": 150000.0}}
        self.printer._print_ferramenta(confronto)
        out = capsys.readouterr().out
        assert "150,000.00" in out
        assert "PUxQ" in out

    def test_preco_venda_catalogo_none_not_shown(self, capsys):
        confronto = {"ferramenta": {"preco_venda_catalogo": None}}
        self.printer._print_ferramenta(confronto)
        out = capsys.readouterr().out
        # The conditional preco_venda (PUxQ) line should NOT appear when preco_venda_catalogo is None
        assert "preco_venda (PUxQ)" not in out


# ---------------------------------------------------------------------------
# BenchmarkReportPrinter._print_composicao_final
# ---------------------------------------------------------------------------


class TestPrintComposicaoFinal:
    def setup_method(self):
        self.printer = BenchmarkReportPrinter()

    def test_no_composicao_returns_early(self, capsys):
        self.printer._print_composicao_final({})
        assert capsys.readouterr().out == ""

    def test_none_composicao_returns_early(self, capsys):
        self.printer._print_composicao_final({"composicao_final": None})
        assert capsys.readouterr().out == ""

    def test_prints_header(self, capsys):
        confronto = {
            "composicao_final": {
                "custo_total": {
                    "referencia": 100.0,
                    "ferramenta": 110.0,
                    "delta_absoluto": 10.0,
                    "delta_percentual": 10.0,
                }
            }
        }
        self.printer._print_composicao_final(confronto)
        out = capsys.readouterr().out
        assert "COMPOSICAO FINAL" in out

    def test_prints_delta_pct(self, capsys):
        confronto = {
            "composicao_final": {
                "custo_total": {
                    "referencia": 100.0,
                    "ferramenta": 110.0,
                    "delta_absoluto": 10.0,
                    "delta_percentual": 10.0,
                }
            }
        }
        self.printer._print_composicao_final(confronto)
        out = capsys.readouterr().out
        assert "+10.00%" in out

    def test_delta_pct_none_shows_na(self, capsys):
        confronto = {
            "composicao_final": {
                "custo_total": {
                    "referencia": None,
                    "ferramenta": None,
                    "delta_absoluto": None,
                    "delta_percentual": None,
                }
            }
        }
        self.printer._print_composicao_final(confronto)
        out = capsys.readouterr().out
        assert "N/A" in out
        assert "nao disponivel" in out


# ---------------------------------------------------------------------------
# BenchmarkReportPrinter._print_breakdown
# ---------------------------------------------------------------------------


class TestPrintBreakdown:
    def setup_method(self):
        self.printer = BenchmarkReportPrinter()

    def test_no_breakdown_returns_early(self, capsys):
        self.printer._print_breakdown({})
        assert capsys.readouterr().out == ""

    def test_none_breakdown_returns_early(self, capsys):
        self.printer._print_breakdown({"breakdown_por_fase": None})
        assert capsys.readouterr().out == ""

    def test_prints_direto_section(self, capsys):
        confronto = {
            "breakdown_por_fase": {
                "direto": {
                    "base": "equipes",
                    "mao_obra_total": 10000.0,
                    "equipamentos_total": 5000.0,
                    "diesel_total": 2000.0,
                    "materiais_total": 500.0,
                    "direto_total": 17500.0,
                }
            }
        }
        self.printer._print_breakdown(confronto)
        out = capsys.readouterr().out
        assert "DIRETO" in out
        assert "equipes" in out
        assert "10,000.00" in out

    def test_direto_uses_direto_total_equipes_fallback(self, capsys):
        confronto = {
            "breakdown_por_fase": {
                "direto": {
                    "base": "equipes",
                    "direto_total_equipes": 9999.0,
                }
            }
        }
        self.printer._print_breakdown(confronto)
        out = capsys.readouterr().out
        assert "9,999.00" in out

    def test_prints_indireto_section(self, capsys):
        confronto = {
            "breakdown_por_fase": {
                "indireto": {
                    "adm": 1000.0,
                    "top": 500.0,
                    "lab": 200.0,
                    "qsms": 100.0,
                    "mob": 300.0,
                    "total": 2100.0,
                }
            }
        }
        self.printer._print_breakdown(confronto)
        out = capsys.readouterr().out
        assert "INDIRETO" in out
        assert "1,000.00" in out
        assert "2,100.00" in out

    def test_empty_direto_skipped(self, capsys):
        confronto = {"breakdown_por_fase": {"direto": {}, "indireto": {"total": 100.0}}}
        self.printer._print_breakdown(confronto)
        out = capsys.readouterr().out
        assert "[DIRETO]" not in out
        assert "[INDIRETO]" in out

    def test_empty_indireto_skipped(self, capsys):
        confronto = {
            "breakdown_por_fase": {
                "direto": {"direto_total": 1000.0},
                "indireto": {},
            }
        }
        self.printer._print_breakdown(confronto)
        out = capsys.readouterr().out
        assert "[DIRETO]" in out
        assert "[INDIRETO]" not in out


# ---------------------------------------------------------------------------
# BenchmarkReportPrinter._print_ponto_equilibrio
# ---------------------------------------------------------------------------


class TestPrintPontoEquilibrio:
    def setup_method(self):
        self.printer = BenchmarkReportPrinter()

    def test_delegates_to_ref_and_tool(self, capsys):
        confronto = {
            "ponto_equilibrio_referencia": {"total_hc": 5, "total_custo_fixo": 1000.0},
            "ponto_equilibrio_ferramenta": {"total_hc": 5, "custo_fixo_total": 2000.0},
        }
        self.printer._print_ponto_equilibrio(confronto)
        out = capsys.readouterr().out
        assert "Ponto de Equilibrio (referencia)" in out
        assert "Ponto de Equilibrio Estrutural (Ferramenta)" in out

    def test_both_none_no_output(self, capsys):
        confronto = {}
        self.printer._print_ponto_equilibrio(confronto)
        assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# BenchmarkReportPrinter._print_insights
# ---------------------------------------------------------------------------


class TestPrintInsights:
    def setup_method(self):
        self.printer = BenchmarkReportPrinter()

    def test_no_insights_returns_early(self, capsys):
        self.printer._print_insights({})
        assert capsys.readouterr().out == ""

    def test_none_insights_returns_early(self, capsys):
        self.printer._print_insights({"actionable_insights": None})
        assert capsys.readouterr().out == ""

    def test_prints_criticidade(self, capsys):
        confronto = {"actionable_insights": {"criticidade": "ALTA"}}
        self.printer._print_insights(confronto)
        out = capsys.readouterr().out
        assert "ALTA" in out

    def test_prints_sensibilidade(self, capsys):
        confronto = {"actionable_insights": {"sensibilidade": "MEDIA"}}
        self.printer._print_insights(confronto)
        out = capsys.readouterr().out
        assert "MEDIA" in out

    def test_prints_intervencao(self, capsys):
        confronto = {"actionable_insights": {"intervencao": "IMEDIATA"}}
        self.printer._print_insights(confronto)
        out = capsys.readouterr().out
        assert "IMEDIATA" in out

    def test_missing_keys_not_printed(self, capsys):
        confronto = {"actionable_insights": {"criticidade": "BAIXA"}}
        self.printer._print_insights(confronto)
        out = capsys.readouterr().out
        assert "Sensibilidade" not in out
        assert "Intervencao" not in out


# ---------------------------------------------------------------------------
# BenchmarkReportPrinter._print_acoes
# ---------------------------------------------------------------------------


class TestPrintAcoes:
    def setup_method(self):
        self.printer = BenchmarkReportPrinter()

    def test_no_action_report_returns_early(self, capsys):
        self.printer._print_acoes({})
        assert capsys.readouterr().out == ""

    def test_none_action_report_returns_early(self, capsys):
        self.printer._print_acoes({"action_report": None})
        assert capsys.readouterr().out == ""

    def test_prints_acoes_header(self, capsys):
        report = {
            "action_report": [
                {
                    "fase": "TERRAPLANAGEM",
                    "metric": "custo_direto",
                    "classe": "critica",
                    "severidade": "S2",
                    "delta_percentual": 15.5,
                    "acao_recomendada": "Revisar orçamento",
                }
            ]
        }
        self.printer._print_acoes(report)
        out = capsys.readouterr().out
        assert "ACOES GRANULARES" in out

    def test_prints_action_row(self, capsys):
        report = {
            "action_report": [
                {
                    "fase": "TERRAPLANAGEM",
                    "metric": "custo_direto",
                    "classe": "critica",
                    "severidade": "S2",
                    "delta_percentual": 15.5,
                    "acao_recomendada": "Revisar",
                }
            ]
        }
        self.printer._print_acoes(report)
        out = capsys.readouterr().out
        assert "TERRAPLANAGEM" in out
        assert "+15.50%" in out
        assert "Revisar" in out

    def test_delta_pct_none_shows_na(self, capsys):
        report = {
            "action_report": [
                {
                    "fase": "X",
                    "metric": "y",
                    "classe": "z",
                    "severidade": "S1",
                    "delta_percentual": None,
                    "acao_recomendada": "act",
                }
            ]
        }
        self.printer._print_acoes(report)
        out = capsys.readouterr().out
        assert "N/A" in out

    def test_multiple_actions_printed(self, capsys):
        report = {
            "action_report": [
                {
                    "fase": "A",
                    "metric": "m1",
                    "classe": "c1",
                    "severidade": "S1",
                    "delta_percentual": 1.0,
                    "acao_recomendada": "act1",
                },
                {
                    "fase": "B",
                    "metric": "m2",
                    "classe": "c2",
                    "severidade": "S2",
                    "delta_percentual": -2.0,
                    "acao_recomendada": "act2",
                },
            ]
        }
        self.printer._print_acoes(report)
        out = capsys.readouterr().out
        assert "act1" in out
        assert "act2" in out


# ---------------------------------------------------------------------------
# BenchmarkReportPrinter.print (integration)
# ---------------------------------------------------------------------------


class TestPrint:
    def setup_method(self):
        self.printer = BenchmarkReportPrinter()

    def _minimal_report(self, **overrides):
        base = {"projeto": "TestProj", "quality_gates": {}, "confronto": {}}
        base.update(overrides)
        return base

    def test_print_full_report(self, capsys):
        report = {
            "projeto": "AGIS",
            "status_final": "APROVADO",
            "quality_gates": {"worst_severity": "S1", "critical_metric_over_10pct": False},
            "confronto": {
                "referencia": {"custo_direto": 500000.0},
                "ferramenta": {
                    "custo_direto": 510000.0,
                    "custo_execucao_pool": 490000.0,
                    "custo_indireto": 50000.0,
                    "preco_venda": 560000.0,
                    "bdi_lucro_impostos": 0.18,
                    "preco_venda_catalogo": 565000.0,
                },
                "composicao_final": {
                    "preco_total": {
                        "referencia": 500000.0,
                        "ferramenta": 510000.0,
                        "delta_absoluto": 10000.0,
                        "delta_percentual": 2.0,
                    }
                },
                "breakdown_por_fase": {
                    "direto": {
                        "base": "equipes",
                        "mao_obra_total": 200000.0,
                        "equipamentos_total": 100000.0,
                        "diesel_total": 50000.0,
                        "materiais_total": 10000.0,
                        "direto_total": 360000.0,
                    },
                    "indireto": {
                        "adm": 20000.0,
                        "top": 10000.0,
                        "lab": 5000.0,
                        "qsms": 3000.0,
                        "mob": 2000.0,
                        "total": 40000.0,
                    },
                },
                "ponto_equilibrio_referencia": {
                    "total_hc": 100,
                    "total_custo_fixo": 400000.0,
                    "equipes": 5,
                },
                "ponto_equilibrio_ferramenta": {
                    "total_hc_operacional": 80,
                    "total_hc_indireto": 20,
                    "total_hc": 100,
                    "custo_fixo_mensal": 40000.0,
                    "custo_fixo_total": 400000.0,
                    "equipes": 5,
                },
                "actionable_insights": {
                    "criticidade": "MEDIA",
                    "sensibilidade": "BAIXA",
                    "intervencao": "MONITORAR",
                },
            },
            "action_report": [
                {
                    "fase": "ATERRO",
                    "metric": "custo_direto",
                    "classe": "alerta",
                    "severidade": "S1",
                    "delta_percentual": 2.0,
                    "acao_recomendada": "Monitorar",
                }
            ],
        }
        self.printer.print(report)
        out = capsys.readouterr().out
        assert "AGIS" in out
        assert "APROVADO" in out
        assert "500,000.00" in out
        assert "DIRETO" in out
        assert "INDIRETO" in out
        assert "Ponto de Equilibrio (referencia)" in out
        assert "Ponto de Equilibrio Estrutural (Ferramenta)" in out
        assert "MEDIA" in out
        assert "Monitorar" in out

    def test_print_no_referencia_shows_warn(self, capsys):
        report = self._minimal_report()
        self.printer.print(report)
        out = capsys.readouterr().out
        assert "WARN" in out
        assert "Sem dados de referencia" in out

    def test_print_with_referencia_no_warn(self, capsys):
        report = self._minimal_report(confronto={"referencia": {"custo_direto": 1000.0}})
        self.printer.print(report)
        out = capsys.readouterr().out
        assert "WARN" not in out

    def test_print_minimal_report_no_crash(self, capsys):
        report = {"projeto": "Min", "confronto": {}}
        self.printer.print(report)
        out = capsys.readouterr().out
        assert "Min" in out
