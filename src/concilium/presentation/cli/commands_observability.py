"""CLI para o pipeline de observabilidade — ADR-112 F6.

Comandos:
    concilium pipeline observability run      — incremental desde último checkpoint
    concilium pipeline observability run --full-reload
    concilium pipeline observability run --signal logs|traces|metrics
    concilium pipeline observability status   — mostra checkpoints por sinal
    concilium pipeline observability report   — exibe tabelas Gold no terminal
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich import print as rprint
from rich.table import Table

observability_app = typer.Typer(
    name="observability",
    help="Pipeline de observabilidade: Bronze → Silver → Gold (ADR-112).",
    no_args_is_help=True,
)

_SIGNAL_TYPES = ["logs", "traces", "metrics"]


def _get_storage():
    from concilium.infrastructure.observability.pipeline import _make_storage
    return _make_storage()


@observability_app.command("run")
def run_pipeline(
    signal: Annotated[str, typer.Option(help="Tipo de sinal: logs | traces | metrics")] = "logs",
    full_reload: Annotated[bool, typer.Option("--full-reload", help="Apaga checkpoints e reprocessa tudo")] = False,
    since: Annotated[str | None, typer.Option(help="ISO date (YYYY-MM-DD) — fast-forward desde esta data")] = None,
    all_signals: Annotated[bool, typer.Option("--all", help="Processa todos os tipos de sinal")] = False,
) -> None:
    """Executa o pipeline Bronze → Silver de forma incremental."""
    from concilium.infrastructure.observability.pipeline import ObservabilityWorker

    storage = _get_storage()
    worker = ObservabilityWorker(storage)
    signals = _SIGNAL_TYPES if all_signals else [signal]

    for sig in signals:
        rprint(f"[bold cyan]▶ Processando {sig}...[/bold cyan]")
        result = worker.run(signal_type=sig, full_reload=full_reload, since=since)
        blobs = result["blobs_processed"]
        records = result["records_processed"]
        if blobs == 0:
            rprint(f"  [dim]Nenhum blob novo ({sig})[/dim]")
        else:
            rprint(f"  [green]✓ {blobs} blobs · {records} records processados[/green]")


@observability_app.command("status")
def show_status() -> None:
    """Exibe o último checkpoint por tipo de sinal."""
    from concilium.infrastructure.observability.checkpoint_store import CheckpointStore

    storage = _get_storage()
    store = CheckpointStore(storage)

    table = Table(title="Checkpoints de Observabilidade", show_header=True)
    table.add_column("Sinal", style="cyan")
    table.add_column("Último blob processado", style="dim")
    table.add_column("Timestamp", style="dim")
    table.add_column("Records", justify="right")

    found = False
    for sig in _SIGNAL_TYPES:
        cp = store.load(sig)
        if cp:
            found = True
            table.add_row(
                sig,
                cp.last_processed_path or "—",
                cp.last_processed_ts or "—",
                str(cp.records_processed),
            )

    if not found:
        rprint("[yellow]Nenhum checkpoint encontrado. Execute 'run' primeiro.[/yellow]")
        return

    rprint(table)


@observability_app.command("report")
def show_report() -> None:
    """Exibe tabelas Gold no terminal (SLIs, fallback rates, alertas)."""
    from concilium.infrastructure.observability.gold_aggregator import GoldAggregator

    storage = _get_storage()
    agg = GoldAggregator(storage)

    # SLIs
    sli = agg.build_sli_diario()
    if sli:
        t = Table(title="SLI Diário (duration_ms)", show_header=True)
        for col in ("date", "skill_id", "p50_ms", "p95_ms", "p99_ms", "n_spans"):
            t.add_column(col)
        for row in sli:
            t.add_row(*[str(row.get(c, "")) for c in ("date", "skill_id", "p50_ms", "p95_ms", "p99_ms", "n_spans")])
        rprint(t)
    else:
        rprint("[dim]SLI: sem dados de traces no Silver.[/dim]")

    # Fallback rates
    rates = agg.build_fallback_rate_por_skill()
    if rates:
        t = Table(title="Fallback Rate por Skill", show_header=True)
        for col in ("date", "skill_id", "n_fallbacks", "n_total", "fallback_rate"):
            t.add_column(col)
        for row in rates:
            t.add_row(*[str(row.get(c, "")) for c in ("date", "skill_id", "n_fallbacks", "n_total", "fallback_rate")])
        rprint(t)
    else:
        rprint("[dim]Fallback rate: sem dados de logs no Silver.[/dim]")

    # Alertas
    alertas = agg.build_alertas_ativos()
    if alertas:
        rprint(f"\n[bold red]⚠ {len(alertas)} alerta(s) ativo(s)[/bold red]")
        for a in alertas:
            rprint(f"  [red]• {a['tipo']}[/red] skill={a.get('skill_id')} date={a.get('date')}")
    else:
        rprint("\n[green]✓ Nenhum alerta ativo[/green]")
