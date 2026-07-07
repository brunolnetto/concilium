"""Gantt chart de cronograma de execução."""

from __future__ import annotations

from ._common import init_mpl

_GANTT_LEVEL_COLORS = ["#1a3a5c", "#2e6da4", "#5aabdc", "#c05c18", "#e8a030"]


def _draw_gantt_task(ax, mdates, idx: int, task: dict) -> None:
    """Desenha a barra horizontal + label de uma tarefa do Gantt."""
    import datetime as _dt

    name = str(task.get("name") or task.get("item_id") or f"Atividade {idx + 1}")
    start_str = task.get("start")
    # Chamadores só passam tasks de sorted_tasks (pré-filtradas por `if t.get("start")`
    # em build_gantt), logo start_str nunca é None aqui.
    assert start_str is not None
    duration_days = int(task.get("duration_days", 7))
    level = int(task.get("level", 0))
    start_dt = _dt.datetime.strptime(start_str, "%Y-%m-%d")
    start_num = mdates.date2num(start_dt)
    col = _GANTT_LEVEL_COLORS[level % len(_GANTT_LEVEL_COLORS)]
    ax.broken_barh([(start_num, duration_days)], (idx * 1.2, 0.9), facecolors=col, alpha=0.85)
    ax.text(
        start_num + duration_days / 2,
        idx * 1.2 + 0.45,
        (name[:38] + "...") if len(name) > 38 else name,
        ha="center",
        va="center",
        fontsize=7,
        color="white",
        fontweight="bold",
    )


def _style_gantt_axes(ax, fig, mdates, sorted_tasks: list) -> None:
    """Aplica eixos, título e formatação de data ao gráfico de Gantt."""
    ax.set_yticks([i * 1.2 + 0.45 for i in range(len(sorted_tasks))])
    ax.set_yticklabels(
        [str(t.get("name") or t.get("item_id") or "")[:35] for t in sorted_tasks],
        fontsize=8,
    )
    ax.xaxis_date()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b/%y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    fig.autofmt_xdate(rotation=45)
    ax.set_title("Cronograma de Execução", fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel("Período", fontsize=10)
    ax.grid(axis="x", alpha=0.3)


def _render_gantt_figure(plt, fig_to_bytes, mdates, sorted_tasks: list) -> bytes | None:
    """Constrói a figura do Gantt a partir das tarefas ordenadas. Fecha a figura em erro."""
    try:
        fig, ax = plt.subplots(figsize=(14, max(4, len(sorted_tasks) * 0.7 + 2)))
        for idx, task in enumerate(sorted_tasks):
            _draw_gantt_task(ax, mdates, idx, task)
        _style_gantt_axes(ax, fig, mdates, sorted_tasks)
        fig.tight_layout()
        return fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None


def build_gantt(cronograma: dict) -> bytes | None:
    tasks = list(cronograma.get("tasks", [])) if isinstance(cronograma, dict) else []
    if not tasks:
        return None
    sorted_tasks = sorted(
        [t for t in tasks if t.get("start")],
        key=lambda t: t.get("start", ""),
    )
    if not sorted_tasks:
        return None
    try:
        import matplotlib.dates as mdates

        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None
    return _render_gantt_figure(plt, fig_to_bytes, mdates, sorted_tasks)
