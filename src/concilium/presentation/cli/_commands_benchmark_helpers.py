"""Helpers extracted from commands_benchmark.py.

CLI commands para o grupo 'benchmark': run, analyze, trace, audit, cleanup.

Comandos:
    concilium benchmark run [--slug SLUG] [--reset]
    concilium benchmark analyze
    concilium benchmark trace --slug SLUG
    concilium benchmark audit --slug SLUG
    concilium benchmark cleanup
    concilium benchmark iterate --slug SLUG
    concilium benchmark schedule run <referencia.json>
    concilium benchmark summary
    concilium benchmark plan-space --slug SLUG [--reset] [--workers N]
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich import print as rprint
from rich.table import Table

from concilium.application.benchmarks.charts.output_packager import empacotar_outputs
from concilium.application.benchmarks.spec.spec_loader import load_spec_from_dict
from concilium.presentation.cli.shared import config_root as get_config_root

if TYPE_CHECKING:
    from concilium.application.benchmarks.spec.spec_loader import ProjectSpec

app = typer.Typer(
    name="benchmark",
    help="Operações de benchmark: run, audit, analyze, extract e correção de discrepâncias.",
    no_args_is_help=True,
)


def _mc_merge_alternativas(ref: dict, bench_dir: Path | str, changed: bool) -> tuple:
    """Embeds alternativas.json into ref['cenarios']. Returns (alt_path, changed)."""
    bench_dir = Path(bench_dir)
    alt_path = bench_dir / "alternativas.json"
    if alt_path.exists():
        alt_data = json.loads(alt_path.read_text(encoding="utf-8"))
        # v2: cenarios fica em spec; v1: fica no topo
        container = ref.get("spec")
        if not isinstance(container, dict):
            container = ref
        if container.get("cenarios") != alt_data:
            container["cenarios"] = alt_data
            changed = True
    return alt_path, changed


def _mc_merge_equipes(ref: dict, bench_dir: Path | str, changed: bool) -> tuple:
    """Embeds equipes.json into ref['equipes']. Returns (eq_path, changed)."""
    bench_dir = Path(bench_dir)
    eq_path = bench_dir / "equipes.json"
    if eq_path.exists():
        eq_data = json.loads(eq_path.read_text(encoding="utf-8"))
        if ref.get("equipes") != eq_data:
            ref["equipes"] = eq_data
            changed = True
    return eq_path, changed


def _mc_remove_historical(keep: bool, alt_path: Path | str, eq_path: Path | str) -> None:
    """Removes historical alternativas.json and equipes.json if keep is False."""
    if keep:
        return
    for p in (alt_path, eq_path):
        p = Path(p)
        if p.exists():
            p.unlink()
            rprint(f"[dim]removido: {p.name}[/dim]")


def _deep_merge_dict(base: dict, override: dict) -> dict:
    """Merge recursivo de dicionários para overlays de alternativas."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge_dict(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _discover_slugs(root: Path) -> list[str]:
    slugs = sorted(
        d.name for d in (root / "benchmarks" / "data").iterdir() if d.is_dir() and (d / "referencia.json").exists()
    )
    return slugs


def _empacotar_benchmark_cli(slug: str, root: Path, gerar_charts: bool = True) -> None:
    """Helper: gera charts (se solicitado) e cria ZIP dos artefatos."""

    try:
        zip_path = empacotar_outputs(
            slug=slug,
            config_root=get_config_root(),
            gerar_graficos=gerar_charts,
        )
        rprint(f"\n[green]📦 Pacote criado:[/green] {zip_path}")
        size_mb = zip_path.stat().st_size / (1024 * 1024)
        rprint(f"   Tamanho: {size_mb:.2f} MB")
    except Exception as e:
        rprint(f"[yellow]⚠ Empacotamento falhou: {e}[/yellow]")


def _make_silent_printer():
    from concilium.application.benchmarks.report.report_printer import BenchmarkReportPrinter

    class _SilentPrinterImpl(BenchmarkReportPrinter):
        def print(self, report: dict) -> None:  # noqa: A003
            pass

    return _SilentPrinterImpl()


def _run_one_plan_space(
    alt_id: str,
    modo: str,
    spec: ProjectSpec,
    reset: bool,
    cfg_root: Path,
    proj_root: Path,
    out_dir: Path,
) -> dict:
    from concilium.application.benchmarks import BenchmarkRunner
    from concilium.application.benchmarks.report.report_builder import BenchmarkReportBuilder

    runner = BenchmarkRunner(
        config_root=cfg_root,
        projects_root=proj_root,
        report_builder=BenchmarkReportBuilder(),
        report_printer=_make_silent_printer(),
    )
    report = runner.run(spec, reset=reset)
    report_file = out_dir / f"{alt_id}.benchmark_report.json"
    report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    deltas = (report.get("confronto") or {}).get("deltas") or {}
    delta_preco_venda = (deltas.get("preco_venda") or {}).get("percentual")
    rcpsp = report.get("rcpsp_schedule") or {}
    status = report.get("status_final") or ((report.get("quality_gates") or {}).get("decision") or "N/A")
    return {
        "alternativa": alt_id,
        "modo": modo,
        "status": status,
        "delta_preco_venda_pct": delta_preco_venda,
        "makespan_semanas": rcpsp.get("makespan_weeks"),
        "folga_semanas": rcpsp.get("folga_semanas"),
        "report_file": str(report_file),
    }


def _validate_and_apply_modo(alt_id: str, modo: str, variant_ref: dict) -> None:
    import typer
    from rich import print as rprint

    # v2: rcpsp_spec fica em spec; v1: fica no topo
    _spec_container = variant_ref.get("spec")
    if not isinstance(_spec_container, dict):
        _spec_container = variant_ref
    if modo == "MANUAL":
        _spec_container.pop("rcpsp_spec", None)
    elif modo == "AUTO":
        if not _spec_container.get("rcpsp_spec"):
            rprint(f"[red]Alternativa {alt_id}: modo AUTO exige rcpsp_spec.[/red]")
            raise typer.Exit(1) from None
    else:
        rprint(f"[red]Alternativa {alt_id}: modo inválido '{modo}' (use AUTO ou MANUAL).[/red]")
        raise typer.Exit(1) from None


def _prepare_one_task(alt: dict, base_ref: dict, ref_path, load_spec_from_dict):
    import typer
    from rich import print as rprint

    alt_id = str(alt.get("id") or "ALT")
    modo = str(alt.get("modo") or "AUTO").upper()
    # v2: mode fica em meta; v1: fica no topo
    _ref_mode = str((base_ref.get("meta") or base_ref).get("mode") or "").lower()
    if _ref_mode == "benchmark_config" and modo != "AUTO":
        rprint(f"[yellow]Alternativa {alt_id}: modo '{modo}' sobrescrito para AUTO (benchmark_config).[/yellow]")
        modo = "AUTO"
    overrides = alt.get("overrides") or {}
    if not isinstance(overrides, dict):
        rprint(f"[red]Alternativa {alt_id}: overrides deve ser objeto JSON.[/red]")
        raise typer.Exit(1) from None
    variant_ref = _deep_merge_dict(base_ref, overrides)
    _validate_and_apply_modo(alt_id, modo, variant_ref)
    spec = load_spec_from_dict(variant_ref, ref_path)
    base_name = spec.nome
    spec.nome = f"{base_name} [{alt_id}]"
    return (alt_id, modo, spec)


def _prepare_plan_space_tasks(base_ref: dict, ref_path: Path | str, alternativas: list) -> list:

    tasks: list = []
    for alt in alternativas:
        task = _prepare_one_task(alt, base_ref, ref_path, load_spec_from_dict)
        tasks.append(task)
    return tasks


def _execute_plan_space_tasks(
    tasks: list,
    num_workers: int,
    reset: bool,
    cfg_root: Path,
    proj_root: Path,
    out_dir: Path,
) -> tuple[list, list]:
    import concurrent.futures
    from threading import Lock

    print_lock = Lock()
    rows: list = []
    failed: list = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        future_to_id = {
            executor.submit(_run_one_plan_space, alt_id, modo, spec, reset, cfg_root, proj_root, out_dir): alt_id
            for alt_id, modo, spec in tasks
        }
        for future in concurrent.futures.as_completed(future_to_id):
            alt_id = future_to_id[future]
            try:
                row = future.result()
                with print_lock:
                    rows.append(row)
                    rprint(f"  [green]OK {alt_id}[/green]")
            except Exception as exc:  # noqa: BLE001
                failed.append(alt_id)
                with print_lock:
                    rprint(f"  [red]FAIL {alt_id}: {exc}[/red]")
    return rows, failed


def _save_plan_space_results(
    rows_sorted: list, slug_upper: str, root: Path, outputs_dir: Path, bench_dir: Path
) -> None:
    table = Table(title=f"Plan Space — {slug_upper}")
    table.add_column("Alternativa", style="cyan")
    table.add_column("Modo")
    table.add_column("Status")
    table.add_column("Delta Preco Venda %", justify="right")
    table.add_column("Makespan (sem)", justify="right")
    table.add_column("Folga (sem)", justify="right")
    for row in rows_sorted:
        dt = row["delta_preco_venda_pct"]
        dt_str = f"{float(dt):+.2f}%" if dt is not None else "N/A"
        mk = row["makespan_semanas"]
        mk_str = str(mk) if mk is not None else "N/A"
        fl = row["folga_semanas"]
        fl_str = str(fl) if fl is not None else "N/A"
        table.add_row(row["alternativa"], row["modo"], row["status"], dt_str, mk_str, fl_str)
    rprint(table)


def _save_plan_space_markdown(rows_sorted: list, slug_upper: str, outputs_dir: Path) -> None:
    md_lines = [
        f"# Plan Space — {slug_upper}",
        "",
        f"**Alternativas:** {len(rows_sorted)}  ",
        "",
        "| Alternativa | Modo | Status | Delta Preco Venda % | Makespan (sem) | Folga (sem) |",
        "|---|---|---|---:|---:|---:|",
    ]
    for row in rows_sorted:
        dt = row["delta_preco_venda_pct"]
        dt_str = f"{float(dt):+.2f}%" if dt is not None else "-"
        mk = row["makespan_semanas"]
        mk_str = str(mk) if mk is not None else "-"
        fl = row["folga_semanas"]
        fl_str = str(fl) if fl is not None else "-"
        status_badge = f"**{row['status']}**" if row["status"] == "INVIAVEL" else row["status"]
        md_lines.append(f"| {row['alternativa']} | {row['modo']} | {status_badge} | {dt_str} | {mk_str} | {fl_str} |")
    summary_md = outputs_dir / "plan_space_report.md"
    summary_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    rprint(f"[green]Relatório salvo em:[/green] {summary_md}")
