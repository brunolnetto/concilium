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


def _render_sli_diario_table(sli: list) -> None:
    if not sli:
        rprint("[dim]SLI: sem dados de traces no Silver.[/dim]")
        return
    t = Table(title="SLI Diário (duration_ms)", show_header=True)
    for col in ("date", "skill_id", "p50_ms", "p95_ms", "p99_ms", "n_spans"):
        t.add_column(col)
    for row in sli:
        t.add_row(*[str(row.get(c, "")) for c in ("date", "skill_id", "p50_ms", "p95_ms", "p99_ms", "n_spans")])
    rprint(t)


def _render_fallback_rate_table(rates: list) -> None:
    if not rates:
        rprint("[dim]Fallback rate: sem dados de logs no Silver.[/dim]")
        return
    t = Table(title="Fallback Rate por Skill", show_header=True)
    for col in ("date", "skill_id", "n_fallbacks", "n_total", "fallback_rate"):
        t.add_column(col)
    for row in rates:
        t.add_row(*[str(row.get(c, "")) for c in ("date", "skill_id", "n_fallbacks", "n_total", "fallback_rate")])
    rprint(t)


def _render_alertas_ativos(alertas: list) -> None:
    if not alertas:
        rprint("\n[green]✓ Nenhum alerta ativo[/green]")
        return
    rprint(f"\n[bold red]⚠ {len(alertas)} alerta(s) ativo(s)[/bold red]")
    for a in alertas:
        rprint(f"  [red]• {a['tipo']}[/red] skill={a.get('skill_id')} date={a.get('date')}")


@observability_app.command("report")
def show_report() -> None:
    """Exibe tabelas Gold no terminal (SLIs, fallback rates, alertas)."""
    from concilium.infrastructure.observability.gold_aggregator import GoldAggregator

    storage = _get_storage()
    agg = GoldAggregator(storage)

    _render_sli_diario_table(agg.build_sli_diario())
    _render_fallback_rate_table(agg.build_fallback_rate_por_skill())
    _render_alertas_ativos(agg.build_alertas_ativos())


@observability_app.command("cycle")
def run_cycle() -> None:
    """Executa um ciclo do scheduler (ADR-112 F7): Bronze→Silver (15min) + Silver→Gold (1h).

    Idempotente e time-gated — seguro chamar via cron/ACI a cada poucos minutos.
    A cadência real é configurada no scheduler de deploy (ACI cron job).
    """
    from concilium.infrastructure.observability.pipeline import ObservabilityScheduler

    storage = _get_storage()
    result = ObservabilityScheduler(storage).run_cycle()
    silver = "✓" if result["silver_ran"] else "—"
    gold = "✓" if result["gold_ran"] else "—"
    rprint("[cyan]Ciclo de observabilidade:[/cyan]")
    rprint(
        f"  Silver (Bronze→Silver): [{'green' if result['silver_ran'] else 'dim'}]{silver}[/] "
        f"({result['silver_records']} records)"
    )
    rprint(f"  Gold (Silver→Gold):     [{'green' if result['gold_ran'] else 'dim'}]{gold}[/]")


@observability_app.command("cross-domain")
def show_cross_domain() -> None:
    """Cruza fallback_rate por projeto com custo/margem do canonical (ADR-112 F8)."""
    from concilium.infrastructure.observability.cross_domain import (
        CrossDomainBuilder,
        default_canonical_provider,
    )
    from concilium.infrastructure.settings import get_storage as _get_settings_storage

    storage = _get_storage()
    cfg = _get_settings_storage()
    bench_root = getattr(cfg, "benchmark_projects_root", None) or (
        (getattr(cfg, "root", None) or ".")
        and __import__("pathlib").Path(getattr(cfg, "root", ".")) / "benchmarks" / "projetos"
    )
    builder = CrossDomainBuilder(storage, canonical_provider=default_canonical_provider(bench_root))
    rows = builder.build()
    if not rows:
        rprint("[dim]Cross-domain: sem logs Silver com project_id.[/dim]")
        return
    t = Table(title="Cross-Domain: Fallback × Resultado Financeiro", show_header=True)
    for col in ("project_id", "n_fallbacks", "n_total", "fallback_rate", "custo_direto", "margem_pct"):
        t.add_column(col)
    for r in rows:
        t.add_row(
            *[
                str(r.get(c, ""))
                for c in ("project_id", "n_fallbacks", "n_total", "fallback_rate", "custo_direto", "margem_pct")
            ]
        )
    rprint(t)
    builder.write()
    rprint("[dim]Gravado em observability/gold/cross_domain.json[/dim]")
