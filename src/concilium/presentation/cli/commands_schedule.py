"""CLI commands: schedule - RCPSP solver (ADR-046)."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich import print as rprint

app = typer.Typer(
    name="schedule",
    help="Escalonamento RCPSP baseado em restricoes de recursos (ADR-046).",
    no_args_is_help=True,
)


def _activities_from_spec(spec: dict):
    from concilium.application.scheduling import Activity

    return [
        Activity(
            activity_id=a["item_id"],
            description=a.get("descricao", a["item_id"]),
            duration_weeks=int(a["duration_weeks"]),
            required_resources=dict(a["required_resources"]),
        )
        for a in spec["activities"]
    ]


def _pool_from_spec(spec: dict):
    from concilium.application.scheduling import ResourcePool

    return ResourcePool(resources={k: int(v) for k, v in spec["resource_pool"].items()})


def _dag_from_spec(spec: dict, activities):
    from concilium.application.scheduling import ActivityDAG

    precedence = [(str(p[0]), str(p[1])) for p in spec.get("precedence", [])]
    return ActivityDAG(activities=activities, precedence=precedence)


def _resolve_deadline_weeks(deadline_weeks, ref_raw: dict) -> int:
    if deadline_weeks is not None:
        return deadline_weeks
    try:
        from datetime import date

        # v2: datas ficam em meta; v1: ficam no topo
        meta = ref_raw.get("meta") or ref_raw
        d_ini = date.fromisoformat(meta["data_inicio"])
        d_fim = date.fromisoformat(meta["data_termino"])
        return max(1, ((d_fim - d_ini).days // 7) + 1)
    except (KeyError, ValueError):
        return 60


@app.command("run")
def schedule_run(
    spec_path: Path = typer.Argument(
        ...,
        help="Caminho para referencia.json contendo seccao rcpsp_spec.",
        exists=True,
        readable=True,
    ),
    output: Path | None = typer.Option(None, "--output", "-o"),
    algorithm: str | None = typer.Option(None, "--algorithm", "-a"),
    deadline_weeks: int | None = typer.Option(None, "--deadline", "-d"),
    timeout: int = typer.Option(30, "--timeout", "-t"),
) -> None:
    """Executa o solver RCPSP sobre a referencia.json (ADR-046)."""
    from concilium.application.scheduling import explore_schedules

    ref_raw = json.loads(spec_path.read_text(encoding="utf-8"))
    # v2: rcpsp_spec fica em spec; v1: fica no topo
    rcpsp_spec = (ref_raw.get("spec") or ref_raw).get("rcpsp_spec")
    if not rcpsp_spec:
        rprint("[red]rcpsp_spec nao encontrado em referencia.json[/red]")
        raise typer.Exit(1)

    activities = _activities_from_spec(rcpsp_spec)
    pool = _pool_from_spec(rcpsp_spec)
    dag = _dag_from_spec(rcpsp_spec, activities)

    rprint(f"[cyan]RCPSP:[/cyan] {len(activities)} atividades, {len(pool.resources)} tipos de recurso")

    weeks = _resolve_deadline_weeks(deadline_weeks, ref_raw)

    heuristics = [algorithm] if algorithm and algorithm != "MILP" else ["MINSLK", "LPT", "MAXRES"]
    explored = explore_schedules(
        activities=activities,
        dag=dag,
        pool=pool,
        deadline_weeks=weeks,
        heuristics=heuristics,
        top_n=3,
    )

    if not explored:
        if algorithm == "MILP" or not algorithm:
            from concilium.application.scheduling.milp import MILPScheduler

            sched = MILPScheduler(timeout_seconds=timeout).schedule(
                activities=activities, dag=dag, pool=pool, deadline_weeks=weeks
            )
            if sched.feasible:
                result_data = {
                    "algorithm": "MILP",
                    "makespan": sched.makespan,
                    "feasible": True,
                    "scheduled_activities": [
                        {
                            "activity_id": a.activity_id,
                            "start_week": a.start_week,
                            "end_week": a.end_week,
                            "duration_weeks": a.duration_weeks,
                        }
                        for a in sched.scheduled_activities
                    ],
                }
                _emit_result(result_data, output)
                return
        rprint("[red]Solver nao encontrou solucao viavel.[/red]")
        raise typer.Exit(1)

    best = explored[0]
    result_data = {
        "algorithm": best.heuristic,
        "makespan": best.schedule.makespan,
        "quality_score": round(best.quality_score, 6),
        "feasible": best.schedule.feasible,
        "scheduled_activities": [
            {
                "activity_id": a.activity_id,
                "start_week": a.start_week,
                "end_week": a.end_week,
                "duration_weeks": a.duration_weeks,
                "assigned_resources": dict(a.assigned_resources),
            }
            for a in best.schedule.scheduled_activities
        ],
    }
    _emit_result(result_data, output)


def _emit_result(data: dict, output: Path | None) -> None:
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    if output:
        output.write_text(payload, encoding="utf-8")
        rprint(f"[green]Resultado salvo em:[/green] {output}")
    else:
        rprint(payload)


@app.command("compare")
def schedule_compare(
    spec_path: Path = typer.Argument(
        ...,
        help="Caminho para referencia.json contendo seccao rcpsp_spec.",
        exists=True,
        readable=True,
    ),
    algorithms: str = typer.Option(
        "",
        "--algorithms",
        "-a",
        help="Algoritmos separados por vírgula (default: CP-SAT,LNS,MINSLK).",
    ),
    deadline_weeks: int | None = typer.Option(None, "--deadline", "-d"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Salva resultado JSON neste caminho."),
) -> None:
    """Compara todos os algoritmos de scheduling sobre o mesmo rcpsp_spec.

    Opera diretamente no layer de scheduling (sem pipeline completo).
    Útil para comparar solvers num problema isolado antes de rodar o benchmark.

    Exemplos:\b
        concilium benchmark schedule compare referencia.json
        concilium benchmark schedule compare referencia.json --algorithms MINSLK,LPT,MAXRES
        concilium benchmark schedule compare referencia.json -d 52 -o result.json
    """
    from rich.table import Table

    from concilium.application.scheduling import compare_all_algorithms

    ref_raw = json.loads(spec_path.read_text(encoding="utf-8"))
    # v2: rcpsp_spec fica em spec; v1: fica no topo
    rcpsp_spec = (ref_raw.get("spec") or ref_raw).get("rcpsp_spec")
    if not rcpsp_spec:
        rprint("[red]rcpsp_spec nao encontrado em referencia.json[/red]")
        raise typer.Exit(1)

    activities = _activities_from_spec(rcpsp_spec)
    pool = _pool_from_spec(rcpsp_spec)
    dag = _dag_from_spec(rcpsp_spec, activities)
    weeks = _resolve_deadline_weeks(deadline_weeks, ref_raw)
    algos = [a.strip() for a in algorithms.split(",") if a.strip()] or None

    rprint(
        f"[cyan]Comparando algoritmos:[/cyan] {len(activities)} atividades, "
        f"{len(pool.resources)} tipo(s) de recurso, deadline={weeks}w"
    )

    results = compare_all_algorithms(activities, dag, pool, weeks, algorithms=algos)

    if not results:
        rprint("[red]Nenhum resultado obtido.[/red]")
        raise typer.Exit(1)

    # ── Rich table ────────────────────────────────────────────────────────────
    table = Table(title="Comparação de Algoritmos — RCPSP")
    table.add_column("Algoritmo", style="cyan")
    table.add_column("Makespan", justify="right")
    table.add_column("Quality", justify="right")
    table.add_column("Feasible")
    table.add_column("Status / Erro")

    best = next((r for r in results if not r.error and r.schedule.feasible), None)
    for r in results:
        if r.error:
            table.add_row(r.heuristic, "—", "—", "✗", f"[red]{r.error[:60]}[/red]")
        else:
            marker = " ◀" if r is best else ""
            table.add_row(
                r.heuristic,
                f"{r.schedule.makespan}w",
                f"{r.quality_score:.4f}",
                "[green]✓[/green]" if r.schedule.feasible else "[red]✗[/red]",
                f"[green]OK{marker}[/green]" if r.schedule.feasible else "[yellow]infeasible[/yellow]",
            )

    rprint(table)

    if output:
        data = [
            {
                "algorithm": r.heuristic,
                "makespan": r.schedule.makespan,
                "quality_score": round(r.quality_score, 6),
                "feasible": r.schedule.feasible,
                "error": r.error,
            }
            for r in results
        ]
        output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        rprint(f"[green]Salvo em:[/green] {output}")
