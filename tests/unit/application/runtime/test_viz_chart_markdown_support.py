"""Tests for chart_markdown_support module — covers all missing lines."""

from concilium.application.runtime.deliverables.visualizations.chart_markdown_support import (
    _append_histogram,
    _gantt_block,
    _is_nullish,
    _markdown_exposure_block,
    _render_financial_markdown,
    _xychart,
    _xychart_bar_line,
    build_chart_markdown_docs,
    render_chart_markdown_sections,
    weekly_to_monthly_labels,
)

# ---------------------------------------------------------------------------
# _is_nullish — line 12
# ---------------------------------------------------------------------------


def test_is_nullish_none():
    assert _is_nullish(None) is True


def test_is_nullish_empty_string():
    assert _is_nullish("") is True


def test_is_nullish_empty_list():
    assert _is_nullish([]) is True


def test_is_nullish_empty_dict():
    assert _is_nullish({}) is True


def test_is_nullish_false_for_zero():
    assert _is_nullish(0) is False


def test_is_nullish_false_for_nonempty():
    assert _is_nullish("x") is False
    assert _is_nullish([1]) is False
    assert _is_nullish({"a": 1}) is False


# ---------------------------------------------------------------------------
# weekly_to_monthly_labels — lines 16, 18-29, 31, 33-36
# ---------------------------------------------------------------------------


def test_weekly_to_monthly_labels_basic():
    # two weeks in same month → first gets label, second gets "."
    labels = ["2024-W01", "2024-W02"]
    result = weekly_to_monthly_labels(labels)
    assert len(result) == 2
    assert "/" in result[0]  # e.g. "Jan/24"
    assert result[1] == "."


def test_weekly_to_monthly_labels_different_months():
    # W01 = Jan (month 1), W09 = Feb (month 2)
    labels = ["2024-W01", "2024-W09"]
    result = weekly_to_monthly_labels(labels)
    assert len(result) == 2
    assert result[0] != result[1]
    assert result[0] != "."
    assert result[1] != "."


def test_weekly_to_monthly_labels_invalid_format():
    # no "-W" separator → falls to else branch (line 33)
    labels = ["not-a-week"]
    result = weekly_to_monthly_labels(labels)
    assert result == ["not-a-week"]


def test_weekly_to_monthly_labels_unparseable():
    # has "-W" but malformed year → exception branch (line 35)
    labels = ["XXXX-W99"]
    result = weekly_to_monthly_labels(labels)
    assert result == ["XXXX-W99"]


def test_weekly_to_monthly_labels_empty():
    assert weekly_to_monthly_labels([]) == []


# ---------------------------------------------------------------------------
# _xychart — lines 42-53, 67-68
# ---------------------------------------------------------------------------


def test_xychart_returns_none_when_empty_labels():
    assert _xychart("T", [], [1, 2], "Y") is None


def test_xychart_returns_none_when_empty_values():
    assert _xychart("T", ["a"], [], "Y") is None


def test_xychart_basic():
    result = _xychart("My Chart", ["a", "b"], [10, 20], "Units")
    assert result is not None
    assert result[0] == "```mermaid"
    assert result[-1] == "```"
    assert 'title "My Chart"' in result[2]
    assert "y-axis" in result[4]
    assert "bar" in result[5]


def test_xychart_y_top_minimum_one():
    # all zeros → y_top should be 1.0 (max(1.0, 0 * 1.2))
    result = _xychart("T", ["a"], [0], "Y")
    assert result is not None
    assert "1.00" in result[4]


def test_xychart_y_top_scales_with_max():
    result = _xychart("T", ["a"], [100], "Y")
    assert result is not None
    # y_top = max(1.0, 100 * 1.2) = 120.0
    assert "120.00" in result[4]


def test_xychart_non_numeric_value_coerced_to_zero():
    result = _xychart("T", ["a", "b"], ["nan_text", 5], "Y")
    assert result is not None
    assert "0" in result[5]


def test_xychart_monthly_ticks():
    # monthly_ticks=True triggers weekly_to_monthly_labels
    result = _xychart("T", ["2024-W01", "2024-W02"], [1, 2], "Y", monthly_ticks=True)
    assert result is not None
    # The display labels are month labels, not original week strings
    assert "2024-W01" not in result[3]


# ---------------------------------------------------------------------------
# _xychart_bar_line — lines 67-68, 70-77, 79-83
# ---------------------------------------------------------------------------


def test_xychart_bar_line_returns_none_when_empty_labels():
    assert _xychart_bar_line("T", [], [1], [2], "Y") is None


def test_xychart_bar_line_basic():
    result = _xychart_bar_line("Cash Flow", ["W1", "W2"], [10, 20], [5, 15], "R$")
    assert result is not None
    assert result[0] == "```mermaid"
    assert result[-1] == "```"
    assert "bar" in result[5]
    assert "line" in result[6]


def test_xychart_bar_line_non_numeric_coerced():
    result = _xychart_bar_line("T", ["a"], ["bad"], ["also_bad"], "Y")
    assert result is not None
    assert "[0.0]" in result[5] or "0" in result[5]


def test_xychart_bar_line_y_top_minimum():
    result = _xychart_bar_line("T", ["a"], [0], [0], "Y")
    assert result is not None
    assert "1.00" in result[4]


def test_xychart_bar_line_y_top_from_combined():
    # max abs across bars + line determines y_top
    result = _xychart_bar_line("T", ["a"], [50], [100], "Y")
    assert result is not None
    # y_top = max(1, 100 * 1.2) = 120.0
    assert "120.00" in result[4]


# ---------------------------------------------------------------------------
# _gantt_block — lines 96-98, 106-114
# ---------------------------------------------------------------------------


def test_gantt_block_returns_none_when_empty():
    assert _gantt_block("T", []) is None


def test_gantt_block_basic():
    tasks = [{"name": "Task A", "start": "2024-01-01", "duration_days": 5}]
    result = _gantt_block("My Gantt", tasks)
    assert result is not None
    assert result[0] == "```mermaid"
    assert result[-1] == "```"
    assert "Task A" in result[-2]
    assert "5d" in result[-2]


def test_gantt_block_skips_task_without_start():
    tasks = [
        {"name": "No Start", "duration_days": 5},
        {"name": "OK Task", "start": "2024-01-01", "duration_days": 3},
    ]
    result = _gantt_block("G", tasks)
    assert result is not None
    # Only the second task should appear
    assert any("OK Task" in ln for ln in result)
    assert not any("No Start" in ln for ln in result)


def test_gantt_block_skips_task_without_duration():
    tasks = [{"name": "No Duration", "start": "2024-01-01"}]
    result = _gantt_block("G", tasks)
    assert result is not None
    # No task entry lines besides header/footer
    assert not any("No Duration" in ln for ln in result)


def test_gantt_block_uses_item_id_when_no_name():
    tasks = [{"item_id": "IT-42", "start": "2024-01-01", "duration_days": 2}]
    result = _gantt_block("G", tasks)
    assert result is not None
    assert any("IT-42" in ln for ln in result)


def test_gantt_block_fallback_name():
    tasks = [{"start": "2024-01-01", "duration_days": 2}]
    result = _gantt_block("G", tasks)
    assert result is not None
    assert any("Atividade 1" in ln for ln in result)


# ---------------------------------------------------------------------------
# _markdown_exposure_block — lines 118-121, 136-150
# ---------------------------------------------------------------------------


def test_markdown_exposure_block_basic():
    labels = ["W1", "W2"]
    exposure = [100, 200]
    result = _markdown_exposure_block(labels, exposure)
    assert result[0] == "### Exposicao Acumulada"
    assert "```mermaid" in result
    assert "line" in result[-3]


def test_markdown_exposure_block_nullish_values():
    labels = ["W1", "W2"]
    exposure = [None, ""]
    result = _markdown_exposure_block(labels, exposure)
    # nullish values become 0.0 → y_top = 1.0; y-axis is at index 6
    assert "1.00" in result[6]


def test_markdown_exposure_block_y_top():
    result = _markdown_exposure_block(["a"], [500])
    # y_top = 500 * 1.2 = 600.0; y-axis is at index 6
    assert "600.00" in result[6]


# ---------------------------------------------------------------------------
# _render_financial_markdown — lines 136-150
# ---------------------------------------------------------------------------


def test_render_financial_markdown_empty_graficos():
    assert _render_financial_markdown({}) == []


def test_render_financial_markdown_non_dict_financeiro():
    assert _render_financial_markdown({"financeiro": "bad"}) == []


def test_render_financial_markdown_with_saldo_receita():
    graficos = {
        "financeiro": {
            "labels": ["W1", "W2"],
            "receita": [100, 200],
            "saldo": [50, 80],
            "exposicao": [],
        }
    }
    result = _render_financial_markdown(graficos)
    assert any("Fluxo de Caixa" in ln for ln in result)
    assert "```mermaid" in result


def test_render_financial_markdown_with_exposicao():
    graficos = {
        "financeiro": {
            "labels": ["W1"],
            "receita": [],
            "saldo": [],
            "exposicao": [300],
        }
    }
    result = _render_financial_markdown(graficos)
    assert any("Exposicao" in ln for ln in result)


def test_render_financial_markdown_both():
    graficos = {
        "financeiro": {
            "labels": ["W1", "W2"],
            "receita": [100, 200],
            "saldo": [50, 80],
            "exposicao": [300, 400],
        }
    }
    result = _render_financial_markdown(graficos)
    assert any("Fluxo de Caixa" in ln for ln in result)
    assert any("Exposicao" in ln for ln in result)


def test_render_financial_markdown_no_saldo_no_chart():
    # saldo is empty → no cash flow chart
    graficos = {
        "financeiro": {
            "labels": ["W1"],
            "receita": [100],
            "saldo": [],
            "exposicao": [],
        }
    }
    result = _render_financial_markdown(graficos)
    assert not any("Fluxo de Caixa" in ln for ln in result)


# ---------------------------------------------------------------------------
# _append_histogram — lines 154-157, 164-165
# ---------------------------------------------------------------------------


def test_append_histogram_no_section():
    lines: list[str] = []
    _append_histogram(lines, {}, "missing_key", "Title", "Y")
    assert lines == []


def test_append_histogram_non_dict_section():
    lines: list[str] = []
    _append_histogram(lines, {"key": "bad_value"}, "key", "Title", "Y")
    assert lines == []


def test_append_histogram_empty_labels():
    lines: list[str] = []
    _append_histogram(lines, {"key": {"labels": [], "values": []}}, "key", "Title", "Y")
    assert lines == []


def test_append_histogram_appends_correctly():
    lines: list[str] = []
    _append_histogram(
        lines,
        {"equip": {"labels": ["2024-W01", "2024-W02"], "values": [10, 20]}},
        "equip",
        "Histograma",
        "Unidades",
    )
    assert any("Histograma" in ln for ln in lines)
    assert "```mermaid" in lines


# ---------------------------------------------------------------------------
# render_chart_markdown_sections — lines 169-180
# ---------------------------------------------------------------------------


def test_render_chart_markdown_sections_empty():
    assert render_chart_markdown_sections({}) == []


def test_render_chart_markdown_sections_no_data():
    result = render_chart_markdown_sections({"other": {}})
    assert result[0] == "## Graficos"
    assert "---" in result


def test_render_chart_markdown_sections_with_equipamentos():
    graficos = {
        "equipamentos": {"labels": ["2024-W01"], "values": [5]},
    }
    result = render_chart_markdown_sections(graficos)
    assert any("Equipamentos" in ln for ln in result)


def test_render_chart_markdown_sections_with_mao_obra():
    graficos = {
        "mao_obra": {"labels": ["2024-W01"], "values": [3]},
    }
    result = render_chart_markdown_sections(graficos)
    assert any("Mao de Obra" in ln for ln in result)


def test_render_chart_markdown_sections_with_cronograma():
    graficos = {"cronograma": {"tasks": [{"name": "T1", "start": "2024-01-01", "duration_days": 7}]}}
    result = render_chart_markdown_sections(graficos)
    assert any("Cronograma" in ln for ln in result)


def test_render_chart_markdown_sections_cronograma_non_dict():
    # gantt should be None when cronograma is not a dict
    graficos = {"cronograma": "bad"}
    result = render_chart_markdown_sections(graficos)
    assert "## Graficos" in result


def test_render_chart_markdown_sections_with_financial():
    graficos = {
        "financeiro": {
            "labels": ["W1"],
            "receita": [100],
            "saldo": [50],
            "exposicao": [200],
        }
    }
    result = render_chart_markdown_sections(graficos)
    assert any("Fluxo de Caixa" in ln or "Exposicao" in ln for ln in result)


# ---------------------------------------------------------------------------
# build_chart_markdown_docs — lines 184-185, 187, 189-192, 194-197, 199-204, 206-209, 211
# ---------------------------------------------------------------------------


def test_build_chart_markdown_docs_empty():
    assert build_chart_markdown_docs({}) == {}


def test_build_chart_markdown_docs_with_equipamentos():
    graficos = {"equipamentos": {"labels": ["2024-W01", "2024-W02"], "values": [10, 20]}}
    result = build_chart_markdown_docs(graficos)
    assert "grafico_equipamentos.md" in result
    assert "```mermaid" in result["grafico_equipamentos.md"]


def test_build_chart_markdown_docs_without_equipamentos_no_key():
    graficos = {"mao_obra": {"labels": ["2024-W01"], "values": [5]}}
    result = build_chart_markdown_docs(graficos)
    assert "grafico_equipamentos.md" not in result
    assert "grafico_mao_obra.md" in result


def test_build_chart_markdown_docs_with_mao_obra():
    graficos = {"mao_obra": {"labels": ["2024-W01"], "values": [3]}}
    result = build_chart_markdown_docs(graficos)
    assert "grafico_mao_obra.md" in result
    assert "Mao de Obra" in result["grafico_mao_obra.md"]


def test_build_chart_markdown_docs_with_cronograma():
    graficos = {"cronograma": {"tasks": [{"name": "T1", "start": "2024-01-01", "duration_days": 5}]}}
    result = build_chart_markdown_docs(graficos)
    assert "grafico_cronograma.md" in result
    assert "gantt" in result["grafico_cronograma.md"]


def test_build_chart_markdown_docs_cronograma_no_tasks():
    graficos = {"cronograma": {"tasks": []}}
    result = build_chart_markdown_docs(graficos)
    assert "grafico_cronograma.md" not in result


def test_build_chart_markdown_docs_cronograma_non_dict():
    graficos = {"cronograma": "bad"}
    result = build_chart_markdown_docs(graficos)
    assert "grafico_cronograma.md" not in result


def test_build_chart_markdown_docs_with_financial():
    graficos = {
        "financeiro": {
            "labels": ["W1", "W2"],
            "receita": [100, 200],
            "saldo": [50, 80],
            "exposicao": [],
        }
    }
    result = build_chart_markdown_docs(graficos)
    assert "grafico_financeiro.md" in result
    assert "Fluxo de Caixa" in result["grafico_financeiro.md"]


def test_build_chart_markdown_docs_financial_no_content():
    # financeiro is empty → no key added
    graficos = {"financeiro": {"labels": [], "receita": [], "saldo": [], "exposicao": []}}
    result = build_chart_markdown_docs(graficos)
    assert "grafico_financeiro.md" not in result


def test_build_chart_markdown_docs_all_sections():
    graficos = {
        "equipamentos": {"labels": ["2024-W01"], "values": [5]},
        "mao_obra": {"labels": ["2024-W02"], "values": [2]},
        "cronograma": {"tasks": [{"name": "T", "start": "2024-01-01", "duration_days": 3}]},
        "financeiro": {
            "labels": ["W1"],
            "receita": [100],
            "saldo": [50],
            "exposicao": [200],
        },
    }
    result = build_chart_markdown_docs(graficos)
    assert "grafico_equipamentos.md" in result
    assert "grafico_mao_obra.md" in result
    assert "grafico_cronograma.md" in result
    assert "grafico_financeiro.md" in result






# chart_markdown_support.py line 146->148:
# _xychart_bar_line returns None (empty labels) → if chart: False → go to exposicao check
# ---------------------------------------------------------------------------


class TestRenderFinancialMarkdownEmptyLabels:
    def test_chart_is_none_when_labels_empty(self):
        """Line 146->148: labels=[] → _xychart_bar_line returns None → if chart: False."""
        from concilium.application.runtime.deliverables.visualizations.chart_markdown_support import (
            _render_financial_markdown,
        )

        graficos = {
            "financeiro": {
                "labels": [],  # empty → xychart returns None
                "saldo": [100.0],  # non-empty → saldo and receita is True
                "receita": [200.0],
            }
        }
        result = _render_financial_markdown(graficos)
        # chart was None → the "### Fluxo de Caixa" block was not added
        assert not any("Fluxo de Caixa" in line for line in result)

