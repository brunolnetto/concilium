"""Shared chart data shaping and Markdown docs for runtime visualizations."""

from __future__ import annotations

import json
from typing import Any

_MONTH_PT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def _is_nullish(value: Any) -> bool:
	return value is None or value == "" or value == [] or value == {}


def weekly_to_monthly_labels(labels: list[str]) -> list[str]:
	import datetime

	result: list[str] = []
	seen_months: set[str] = set()
	for label in labels:
		try:
			parts = label.split("-W")
			if len(parts) == 2:
				year, week = int(parts[0]), int(parts[1])
				date_value = datetime.datetime.strptime(f"{year}-W{week:02d}-1", "%G-W%V-%u")
				month_key = f"{date_value.month}-{date_value.year}"
				if month_key not in seen_months:
					seen_months.add(month_key)
					result.append(f"{_MONTH_PT[date_value.month - 1]}/{str(date_value.year)[2:]}")
				else:
					result.append(".")
			else:
				result.append(label)
		except Exception:
			result.append(label)
	return result


def _xychart(title: str, labels: list[str], values: list[Any], y_label: str, monthly_ticks: bool = False) -> list[str] | None:
	if not labels or not values:
		return None
	numeric_values: list[float] = []
	for value in values:
		try:
			numeric_values.append(float(value))
		except Exception:
			numeric_values.append(0.0)
	max_abs = max((abs(value) for value in numeric_values), default=0.0)
	y_top = max(1.0, max_abs * 1.2)
	display_labels = weekly_to_monthly_labels(labels) if monthly_ticks else labels
	return [
		"```mermaid",
		"xychart-beta",
		f'    title "{title}"',
		f"    x-axis {json.dumps(display_labels, ensure_ascii=False)}",
		f'    y-axis "{y_label}" 0 --> {y_top:.2f}',
		f"    bar {json.dumps([round(value, 2) for value in numeric_values], ensure_ascii=False)}",
		"```",
	]


def _xychart_bar_line(title: str, labels: list[str], bars: list[Any], line_values: list[Any], y_label: str) -> list[str] | None:
	if not labels:
		return None

	def _numbers(values: list[Any]) -> list[float]:
		result = []
		for value in values:
			try:
				result.append(float(value))
			except Exception:
				result.append(0.0)
		return result

	bar_values = _numbers(bars)
	line_data = _numbers(line_values)
	max_abs = max((abs(value) for value in bar_values + line_data), default=0.0)
	y_top = max(1.0, max_abs * 1.2)
	return [
		"```mermaid",
		"xychart-beta",
		f'    title "{title}"',
		f"    x-axis {json.dumps(labels, ensure_ascii=False)}",
		f'    y-axis "{y_label}" 0 --> {y_top:.2f}',
		f"    bar {json.dumps([round(value, 2) for value in bar_values], ensure_ascii=False)}",
		f"    line {json.dumps([round(value, 2) for value in line_data], ensure_ascii=False)}",
		"```",
	]


def _gantt_block(title: str, tasks: list[dict[str, Any]]) -> list[str] | None:
	if not tasks:
		return None
	block = [
		"```mermaid",
		"gantt",
		f'    title "{title}"',
		"    dateFormat  YYYY-MM-DD",
		"    axisFormat  %d/%m",
		"    section Cronograma",
	]
	for idx, task in enumerate(tasks, 1):
		name = str(task.get("name") or task.get("item_id") or f"Atividade {idx}")
		start = task.get("start")
		duration_days = task.get("duration_days")
		if not start or not duration_days:
			continue
		block.append(f"    {name} :task{idx}, {start}, {int(duration_days)}d")
	block.append("```")
	return block


def _markdown_exposure_block(labels: list[Any], exposure: list[Any]) -> list[str]:
	exposure_values = [float(value) if not _is_nullish(value) else 0.0 for value in exposure]
	max_abs = max((abs(value) for value in exposure_values), default=0.0)
	y_top = max(1.0, max_abs * 1.2)
	return [
		"### Exposicao Acumulada",
		"",
		"```mermaid",
		"xychart-beta",
		'    title "Exposicao Acumulada (Receita - Despesa acum.)"',
		f"    x-axis {json.dumps(labels, ensure_ascii=False)}",
		f'    y-axis "R$" 0 --> {y_top:.2f}',
		f"    line {json.dumps([round(value, 2) for value in exposure_values], ensure_ascii=False)}",
		"```",
		"",
	]


def _render_financial_markdown(graficos: dict) -> list[str]:
	financeiro = graficos.get("financeiro") or {}
	if not isinstance(financeiro, dict):
		return []
	labels = [str(label) for label in financeiro.get("labels", [])]
	receita = list(financeiro.get("receita", []))
	saldo = list(financeiro.get("saldo", []))
	exposicao = list(financeiro.get("exposicao", []))
	lines: list[str] = []
	if saldo and receita:
		chart = _xychart_bar_line("Fluxo de Caixa (barras=Saldo Rec-Desp, linha=Receita)", labels, saldo, receita, "R$")
		if chart:
			lines += ["### Fluxo de Caixa", ""] + chart + [""]
	if exposicao:
		lines += _markdown_exposure_block(labels, exposicao)
	return lines


def _append_histogram(lines: list[str], graficos: dict, key: str, title: str, ylabel: str) -> None:
	section = graficos.get(key) or {}
	if not isinstance(section, dict):
		return
	chart = _xychart(title, [str(label) for label in section.get("labels", [])], list(section.get("values", [])), ylabel, monthly_ticks=True)
	if chart:
		lines += [f"### {title}", ""] + chart + [""]


def render_chart_markdown_sections(graficos: dict) -> list[str]:
	if not graficos:
		return []
	lines: list[str] = ["## Graficos", ""]
	_append_histogram(lines, graficos, "equipamentos", "Histograma de Equipamentos", "Unidades")
	_append_histogram(lines, graficos, "mao_obra", "Histograma de Mao de Obra", "Pessoas")
	gantt = graficos.get("cronograma") or {}
	chart = _gantt_block("Cronograma de Execucao", list(gantt.get("tasks", []))) if isinstance(gantt, dict) else None
	if chart:
		lines += ["### Cronograma", ""] + chart + [""]
	lines += _render_financial_markdown(graficos)
	lines += ["", "---", ""]
	return lines


def build_chart_markdown_docs(graficos: dict) -> dict[str, str]:
	if not graficos:
		return {}

	docs: dict[str, str] = {}

	hist_equips: list[str] = ["# Grafico - Histograma de Equipamentos", ""]
	_append_histogram(hist_equips, graficos, "equipamentos", "Histograma de Equipamentos", "Unidades")
	if len(hist_equips) > 2:
		docs["grafico_equipamentos.md"] = "\n".join(hist_equips) + "\n"

	hist_labor: list[str] = ["# Grafico - Histograma de Mao de Obra", ""]
	_append_histogram(hist_labor, graficos, "mao_obra", "Histograma de Mao de Obra", "Pessoas")
	if len(hist_labor) > 2:
		docs["grafico_mao_obra.md"] = "\n".join(hist_labor) + "\n"

	cron_lines: list[str] = ["# Grafico - Cronograma", ""]
	gantt = graficos.get("cronograma") or {}
	chart = _gantt_block("Cronograma de Execucao", list(gantt.get("tasks", []))) if isinstance(gantt, dict) else None
	if chart:
		cron_lines += chart + [""]
		docs["grafico_cronograma.md"] = "\n".join(cron_lines) + "\n"

	financial_lines: list[str] = ["# Grafico - Financeiro", ""]
	financial_lines += _render_financial_markdown(graficos)
	if len(financial_lines) > 2:
		docs["grafico_financeiro.md"] = "\n".join(financial_lines) + "\n"

	return docs


__all__ = ["build_chart_markdown_docs", "render_chart_markdown_sections", "weekly_to_monthly_labels"]