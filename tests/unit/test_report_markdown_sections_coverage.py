"""Unit tests para report_markdown_sections.py (CC=15C, coverage 68.3%).

Cobre as linhas ausentes:
  11-12 (_brl exception), 22-23 (_pct conversão fracionária), 29 (non-dict),
  122 (razao_ind > 0), 142 (compressao não-dict), 167-176 (delta_max > 0),
  178-199 (tabela compressao), 206-211 (detalhamento viáveis),
  219-228 (oportunidades com gap_max_dict), 230-237 (tabela oportunidades),
  241, 244-255, 266-267, 273, 288 (pool_economia_origem),
  352-369 (tabela compressao linhas adicionais), 434 (fim pool_economia_origem).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# _brl e _pct — helpers internos
# ---------------------------------------------------------------------------


class TestBrlHelper:
    def test_valid_float(self):
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import _brl

        assert "R$" in _brl(1234.5)

    def test_invalid_value_returns_str(self):
        """Caminho de exceção: converte para str."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import _brl

        result = _brl("not_a_number")
        assert result == "not_a_number"

    def test_none_returns_str(self):
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import _brl

        result = _brl(None)
        assert result == "None"


class TestPctHelper:
    def test_large_value_stays_as_is(self):
        """v > 1.0 não é multiplicado por 100."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import _pct

        result = _pct(17.5)
        assert "17.5%" in result

    def test_fraction_converted_to_pct(self):
        """v entre -1 e 1 → multiplica por 100."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import _pct

        result = _pct(0.175)
        assert "17.5%" in result

    def test_negative_fraction_converted(self):
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import _pct

        result = _pct(-0.05)
        assert "-5.0%" in result

    def test_invalid_value_returns_str(self):
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import _pct

        result = _pct("bad")
        assert result == "bad"


# ---------------------------------------------------------------------------
# render_executive_summary
# ---------------------------------------------------------------------------


class TestRenderExecutiveSummary:
    def test_non_dict_resumo_returns_empty(self):
        """resumo não-dict → retorna []."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import render_executive_summary

        assert render_executive_summary("not_a_dict", {}) == []

    def test_non_dict_resultado_returns_empty(self):
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import render_executive_summary

        assert render_executive_summary({}, None) == []

    def test_minimal_data_returns_lines(self):
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import render_executive_summary

        resumo = {"projeto": "TestProj"}
        resultado = {}
        lines = render_executive_summary(resumo, resultado)
        assert "## Sumário Executivo" in lines
        assert any("TestProj" in ln for ln in lines)

    def test_with_preco_venda_status_verde(self):
        """Caminho com preco_venda > 0 e status VERDE."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import render_executive_summary

        resumo = {
            "projeto": "Proj",
            "tipo_obra": "terraplenagem",
            "localizacao": "SP",
            "periodo": "2025",
            "status": "ativo",
        }
        resultado = {
            "preco_venda_total": 500_000,
            "custo_total": 450_000,
            "custo_direto": 350_000,
            "custo_indireto": 100_000,
            "resultado_bruto": 50_000,
            "margem_pct": 0.10,
            "status_margem": "VERDE",
            "razao_indireto_direto": 0.286,
        }
        lines = render_executive_summary(resumo, resultado)
        assert any("dentro da faixa objetivo" in ln for ln in lines)
        assert any("razão" in ln for ln in lines)

    def test_with_preco_venda_status_amarelo(self):
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import render_executive_summary

        resumo = {"projeto": "P"}
        resultado = {
            "preco_venda_total": 100_000,
            "custo_total": 95_000,
            "custo_direto": 80_000,
            "custo_indireto": 15_000,
            "resultado_bruto": 5_000,
            "margem_pct": 0.05,
            "status_margem": "AMARELO",
            "razao_indireto_direto": 0.0,
        }
        lines = render_executive_summary(resumo, resultado)
        assert any("próxima ao limite mínimo" in ln for ln in lines)

    def test_with_preco_venda_status_vermelho(self):
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import render_executive_summary

        resumo = {"projeto": "P"}
        resultado = {
            "preco_venda_total": 100_000,
            "custo_total": 98_000,
            "custo_direto": 80_000,
            "custo_indireto": 18_000,
            "resultado_bruto": 2_000,
            "margem_pct": 0.02,
            "status_margem": "VERMELHO",
            "razao_indireto_direto": 0.0,
        }
        lines = render_executive_summary(resumo, resultado)
        assert any("abaixo do mínimo" in ln for ln in lines)

    def test_without_status_margem(self):
        """status_margem vazio: margem_label vazio, sem texto adicional."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import render_executive_summary

        resumo = {"projeto": "P"}
        resultado = {
            "preco_venda_total": 100_000,
            "custo_total": 90_000,
            "custo_direto": 80_000,
            "custo_indireto": 10_000,
            "resultado_bruto": 10_000,
            "margem_pct": 0.10,
            "status_margem": "",
            "razao_indireto_direto": 0.0,
        }
        lines = render_executive_summary(resumo, resultado)
        # Deve ter linhas, mas sem label de margem
        assert any("R$" in ln for ln in lines)

    def test_razao_ind_zero_not_appended(self):
        """razao_ind == 0: não adiciona texto de razão."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import render_executive_summary

        resumo = {"projeto": "P"}
        resultado = {
            "preco_venda_total": 100_000,
            "custo_total": 90_000,
            "custo_direto": 80_000,
            "custo_indireto": 10_000,
            "resultado_bruto": 10_000,
            "margem_pct": 0.10,
            "status_margem": "VERDE",
            "razao_indireto_direto": 0.0,
        }
        lines = render_executive_summary(resumo, resultado)
        assert not any("razão" in ln for ln in lines)


# ---------------------------------------------------------------------------
# render_compressao_cronograma
# ---------------------------------------------------------------------------


class TestRenderCompressaoCronograma:
    def test_non_dict_returns_empty(self):
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import (
            render_compressao_cronograma,
        )

        assert render_compressao_cronograma(None) == []
        assert render_compressao_cronograma("string") == []

    def test_empty_itens_returns_empty(self):
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import (
            render_compressao_cronograma,
        )

        assert render_compressao_cronograma({"itens": []}) == []

    def test_delta_max_zero_no_compression(self):
        """delta_max == 0 → frase 'nenhuma atividade'."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import (
            render_compressao_cronograma,
        )

        comp = {
            "itens": [
                {
                    "activity_id": "eap-1",
                    "tipo_recurso": "EQ",
                    "duration_base": 10,
                    "float_rcpsp": 0,
                    "criticality_class": "PC",
                    "k_otimo": None,
                    "gamma_otimo": None,
                    "delta_makespan": 0,
                    "roi": None,
                }
            ],
            "makespan_base": 20,
            "makespan_otimo": 20,
            "delta_makespan_max": 0,
            "poupanca_total_max": 0,
            "n_viáveis": 0,
            "custo_semana": 10_000,
        }
        lines = render_compressao_cronograma(comp)
        assert any("Nenhuma atividade" in ln for ln in lines)

    def test_delta_max_positive_with_viable_item(self):
        """delta_max > 0 com k_otimo: frase de potencial + detalhamento."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import (
            render_compressao_cronograma,
        )

        comp = {
            "itens": [
                {
                    "activity_id": "eap-1",
                    "tipo_recurso": "EQ",
                    "duration_base": 10,
                    "float_rcpsp": 0.0,
                    "criticality_class": "PC",
                    "k_otimo": 2,
                    "gamma_otimo": 0.5,
                    "delta_makespan": 3,
                    "roi": 2.5,
                    "n_base": 2,
                    "poupanca": 30_000,
                }
            ],
            "makespan_base": 20,
            "makespan_otimo": 17,
            "delta_makespan_max": 3,
            "poupanca_total_max": 30_000,
            "n_viáveis": 1,
            "custo_semana": 10_000,
        }
        lines = render_compressao_cronograma(comp)
        assert any("Potencial identificado" in ln for ln in lines)
        assert any("Detalhamento" in ln for ln in lines)
        assert any("k=2" in ln for ln in lines)

    def test_table_row_with_no_k_otimo(self):
        """Linha de tabela com k_otimo=None → k_str='—'."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import (
            render_compressao_cronograma,
        )

        comp = {
            "itens": [
                {
                    "activity_id": "eap-2",
                    "tipo_recurso": "MO",
                    "duration_base": 5,
                    "float_rcpsp": 2.0,
                    "criticality_class": "Livre",
                    "k_otimo": None,
                    "gamma_otimo": None,
                    "delta_makespan": 0,
                    "roi": None,
                }
            ],
            "makespan_base": 10,
            "makespan_otimo": 10,
            "delta_makespan_max": 1,
            "poupanca_total_max": 5_000,
            "n_viáveis": 0,
            "custo_semana": 5_000,
        }
        lines = render_compressao_cronograma(comp)
        assert any("eap-2" in ln for ln in lines)
        # k_str = '—' deve aparecer
        assert any("—" in ln for ln in lines)

    def test_cls_icon_mapping(self):
        """Classe 'GW' é mapeada para 'Gateway' na tabela."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import (
            render_compressao_cronograma,
        )

        comp = {
            "itens": [
                {
                    "activity_id": "eap-3",
                    "tipo_recurso": "EQ",
                    "duration_base": 8,
                    "float_rcpsp": 0.0,
                    "criticality_class": "GW",
                    "k_otimo": None,
                    "gamma_otimo": None,
                    "delta_makespan": 0,
                    "roi": None,
                }
            ],
            "makespan_base": 15,
            "makespan_otimo": 15,
            "delta_makespan_max": 1,
            "poupanca_total_max": 0,
            "n_viáveis": 0,
            "custo_semana": 8_000,
        }
        lines = render_compressao_cronograma(comp)
        assert any("Gateway" in ln for ln in lines)

    def test_roi_inf_when_k_otimo_no_roi(self):
        """k_otimo set mas roi=None → roi_str='inf'."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import (
            render_compressao_cronograma,
        )

        comp = {
            "itens": [
                {
                    "activity_id": "eap-4",
                    "tipo_recurso": "EQ",
                    "duration_base": 6,
                    "float_rcpsp": 0.0,
                    "criticality_class": "RC",
                    "k_otimo": 2,
                    "gamma_otimo": 0.3,
                    "delta_makespan": 2,
                    "roi": None,
                    "n_base": 1,
                    "poupanca": 0,
                }
            ],
            "makespan_base": 10,
            "makespan_otimo": 8,
            "delta_makespan_max": 2,
            "poupanca_total_max": 0,
            "n_viáveis": 0,
            "custo_semana": 5_000,
        }
        lines = render_compressao_cronograma(comp)
        assert any("inf" in ln for ln in lines)


# ---------------------------------------------------------------------------
# render_oportunidades
# ---------------------------------------------------------------------------


class TestRenderOportunidades:
    def test_none_returns_empty(self):
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import render_oportunidades

        assert render_oportunidades(None) == []

    def test_zero_total_returns_empty(self):
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import render_oportunidades

        assert render_oportunidades({"total_oportunidades": 0}) == []

    def test_with_oportunidades_list(self):
        """Oportunidades com lista de itens renderiza tabela."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import render_oportunidades

        relatorio = {
            "total_oportunidades": 2,
            "total_economia_pot": 50_000,
            "oportunidades_podadas": 1,
            "lambda0_total": 5_000,
            "gap_max_por_tipo": {"EQ": 3, "MO": 9999},
            "oportunidades": [
                {
                    "atividade_i": "eap-1",
                    "atividade_j": "eap-2",
                    "tipo_id": "EQ",
                    "gap_semanas": 2,
                    "gap_max_semanas": 3,
                    "eta": 0.85,
                    "omega_bundle": 0.9,
                    "delta_c_pot": 20_000,
                    "lambda0": 2_000,
                    "economicamente_viavel": True,
                },
                {
                    "atividade_i": "eap-3",
                    "atividade_j": "eap-4",
                    "tipo_id": "MO",
                    "gap_semanas": 5,
                    "gap_max_semanas": 4,
                    "eta": 0.60,
                    "omega_bundle": 0.7,
                    "delta_c_pot": 10_000,
                    "lambda0": 1_000,
                    "economicamente_viavel": False,
                },
            ],
        }
        lines = render_oportunidades(relatorio)
        assert any("Oportunidades de Compartilhamento de Recursos" in ln for ln in lines)
        assert any("eap-1" in ln for ln in lines)
        assert any("✅" in ln for ln in lines)
        assert any("❌" in ln for ln in lines)

    def test_gap_max_dict_table(self):
        """gap_max_por_tipo com ∞ (9999) renderiza corretamente."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import render_oportunidades

        relatorio = {
            "total_oportunidades": 1,
            "total_economia_pot": 1_000,
            "oportunidades_podadas": 0,
            "lambda0_total": 100,
            "gap_max_por_tipo": {"EQ": 9999},
            "oportunidades": [],
        }
        lines = render_oportunidades(relatorio)
        assert any("∞" in ln for ln in lines)
        assert any("sem custo idle" in ln for ln in lines)

    def test_pydantic_like_object_accepted(self):
        """Aceita objetos com getattr (Pydantic-like) além de dicts."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import render_oportunidades

        rel = SimpleNamespace(
            total_oportunidades=1,
            total_economia_pot=1_000,
            oportunidades_podadas=0,
            lambda0_total=100,
            gap_max_por_tipo={},
            oportunidades=[],
        )
        lines = render_oportunidades(rel)
        assert any("Oportunidades de Compartilhamento de Recursos" in ln for ln in lines)


# ---------------------------------------------------------------------------
# render_pool_economia_origem
# ---------------------------------------------------------------------------


class TestRenderPoolEconomiaOrigem:
    def test_none_canonical_returns_empty(self):
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import (
            render_pool_economia_origem,
        )

        assert render_pool_economia_origem(None) == []

    def test_exception_returns_empty(self):
        """Exceção em resolve_cubo_pool_projection → retorna []."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import (
            render_pool_economia_origem,
        )

        with patch(
            "concilium.application.services.analytics.cubo_pool_projection.resolve_cubo_pool_projection",
            side_effect=Exception("fail"),
        ):
            result = render_pool_economia_origem(MagicMock())
        assert result == []

    def test_empty_eco_rows_returns_empty(self):
        """eco_rows vazio (custo_autonomo=0) → retorna []."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import (
            render_pool_economia_origem,
        )

        eco_proj = {"rows": [{"atividade_id": "eap-1", "custo_autonomo": 0.0}], "operator_meta": {}}
        causa_proj = {"rows": []}
        with patch(
            "concilium.application.services.analytics.cubo_pool_projection.resolve_cubo_pool_projection",
            side_effect=[eco_proj, causa_proj],
        ):
            result = render_pool_economia_origem(MagicMock())
        assert result == []

    def test_with_top_pos_and_top_neg(self):
        """Renderiza tabelas de economias positivas e sobrecustos."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import (
            render_pool_economia_origem,
        )

        eco_proj = {
            "rows": [
                {"atividade_id": "eap-1", "custo_autonomo": 50_000, "economia": 10_000, "economia_pct": 20.0},
                {"atividade_id": "eap-2", "custo_autonomo": 30_000, "economia": -5_000, "economia_pct": -16.7},
            ],
            "operator_meta": {
                "custo_autonomo_total": 80_000,
                "custo_instancial_total": 75_000,
                "economia_total": 5_000,
            },
        }
        causa_proj = {
            "rows": [
                {
                    "atividade_id": "eap-1",
                    "produtivo_compartilhado": 8_000,
                    "ocioso_imputado": 500,
                    "mob_demob_imputado": 1_500,
                },
                {
                    "atividade_id": "eap-2",
                    "produtivo_compartilhado": 0,
                    "ocioso_imputado": 3_000,
                    "mob_demob_imputado": 2_000,
                },
            ]
        }
        with patch(
            "concilium.application.services.analytics.cubo_pool_projection.resolve_cubo_pool_projection",
            side_effect=[eco_proj, causa_proj],
        ):
            lines = render_pool_economia_origem(MagicMock())

        assert any("Economia por Compartilhamento de Frente" in ln for ln in lines)
        assert any("Principais Economias de Pool" in ln for ln in lines)  # ADR terminology update
        assert any("Sobrecusto" in ln or "sobrecusto" in ln for ln in lines)
        assert any("eap-1" in ln for ln in lines)
        assert any("eap-2" in ln for ln in lines)

    def test_top_neg_mob_dominates(self):
        """mob_demob > ocioso_imputado → motivo 'mobilização/desmobilização'."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import (
            render_pool_economia_origem,
        )

        eco_proj = {
            "rows": [{"atividade_id": "eap-A", "custo_autonomo": 20_000, "economia": -8_000, "economia_pct": -40}],
            "operator_meta": {
                "custo_autonomo_total": 20_000,
                "custo_instancial_total": 28_000,
                "economia_total": -8_000,
            },
        }
        causa_proj = {
            "rows": [
                {
                    "atividade_id": "eap-A",
                    "produtivo_compartilhado": 0,
                    "ocioso_imputado": 2_000,
                    "mob_demob_imputado": 6_000,
                }
            ]
        }
        with patch(
            "concilium.application.services.analytics.cubo_pool_projection.resolve_cubo_pool_projection",
            side_effect=[eco_proj, causa_proj],
        ):
            lines = render_pool_economia_origem(MagicMock())

        assert any("mobilização/desmobilização" in ln for ln in lines)
