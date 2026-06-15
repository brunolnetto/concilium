"""CLI commands para o grupo 'benchmark': run, analyze, trace, audit, cleanup.

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

import json
from pathlib import Path

import typer
from rich import print as rprint
from rich.table import Table

from concilium.application.benchmarks import BenchmarkBatchRunner, BenchmarkRunner
from concilium.application.benchmarks.algorithm_comparison import AlgorithmComparisonRunner
from concilium.application.benchmarks.analysis import build_stage_discrepancy_summary
from concilium.application.benchmarks.analysis.audit_six_questions import run_audit
from concilium.application.benchmarks.analysis.pipeline_validator import validate_pipeline_integrity
from concilium.application.benchmarks.execution.batch import discover_benchmark_slugs, find_benchmark_reference
from concilium.application.benchmarks.charts.output_packager import empacotar_outputs
from concilium.application.benchmarks.report.report_builder import BenchmarkReportBuilder
from concilium.application.benchmarks.report.report_printer import BenchmarkReportPrinter
from concilium.application.benchmarks.spec.spec_loader import BenchmarkSpecLoader
from concilium.infrastructure.catalog.extraction.engine_refs import (
    extract_engine_iteration_references,
    iter_benchmark_reports,
)
from concilium.presentation.cli.shared import (
    _tools_root,
    benchmark_projects_root,
    config_root,
)
from ._commands_benchmark_helpers import (
    _empacotar_benchmark_cli,
    _execute_plan_space_tasks,
    _mc_merge_alternativas,
    _mc_merge_equipes,
    _mc_remove_historical,
    _prepare_plan_space_tasks,
    _save_plan_space_markdown,
    _save_plan_space_results,
)

get_config_root = config_root  # alias used in tests and some command bodies

app = typer.Typer(
    name="benchmark",
    help="Operações de benchmark: run, audit, analyze, extract e correção de discrepâncias.",
    no_args_is_help=True,
)


@app.command("list")
def list_benchmarks() -> None:
    """Lista benchmarks disponíveis com slug e status."""

    root = _DEFAULT_ROOT / "benchmarks" / "data"
    slugs = discover_benchmark_slugs(root)
    if not slugs:
        rprint("[yellow]Nenhum benchmark encontrado.[/yellow]")
        return

    t = Table(show_header=True, header_style="bold")
    t.add_column("Slug", style="cyan")
    t.add_column("Referência")
    for slug in slugs:
        bench_dir = root / slug
        ref_file = next((c for c in (bench_dir / "referencia.json", bench_dir / "referencia.yaml") if c.exists()), None)
        t.add_row(slug, ref_file.name if ref_file else "[yellow]sem referencia.json[/yellow]")
    rprint(t)


@app.command("merge-catalog")
def merge_catalog(
    slug: str = typer.Argument(..., help="Slug do benchmark (ex: CTC)"),
    keep: bool = typer.Option(False, "--keep", help="Manter alternativas.json e equipes.json apos merge."),
) -> None:
    """Consolida alternativas.json e equipes.json no referencia.json do benchmark."""
    root = _DEFAULT_ROOT
    bench_dir = root / "benchmarks" / "data" / slug.upper()
    ref_path = bench_dir / "referencia.json"
    if not ref_path.exists():
        rprint(f"[red]referencia.json nao encontrado: {ref_path}[/red]")
        raise typer.Exit(1) from None

    ref = json.loads(ref_path.read_text(encoding="utf-8"))
    changed = False

    alt_path, changed = _mc_merge_alternativas(ref, bench_dir, changed)
    eq_path, changed = _mc_merge_equipes(ref, bench_dir, changed)

    if not changed:
        rprint("[yellow]Nenhuma alteracao necessaria. referencia.json ja esta consolidado.[/yellow]")
        return

    ref_path.write_text(json.dumps(ref, indent=2, ensure_ascii=False), encoding="utf-8")
    rprint(f"[green]referencia.json atualizado:[/green] {ref_path}")
    _mc_remove_historical(keep, alt_path, eq_path)


_DEFAULT_ROOT = Path(__file__).resolve().parents[4]


@app.command("run-batch")
def run_benchmarks_batch(
    reset: bool = typer.Option(False, "--reset", help="Força re-execução mesmo se já existir resultado."),
    quiet: bool = typer.Option(False, "-q", "--quiet", help="Modo silencioso: apenas status por linha."),
    json_output: bool = typer.Option(False, "--json", help="Output em JSON puro (sem tabela)."),
    pack: bool = typer.Option(False, "--pack", help="Empacota artefatos ao final (requer slug)."),
) -> None:
    """Executa todos os benchmarks em modo batch silencioso e eficiente."""
    from datetime import UTC, datetime


    root = _tools_root()
    batch_runner = BenchmarkBatchRunner(
        benchmarks_root=root / "benchmarks" / "data",
        config_root=config_root(),
        projects_root=benchmark_projects_root(),
    )

    if not quiet:
        rprint(f"\n[cyan]Executando {len(batch_runner.discover_specs())} benchmarks...[/cyan]\n")

    reports = batch_runner.run_all(reset=reset, quiet=quiet)
    summary = batch_runner.build_summary(reports)

    if json_output:
        output = {
            "meta": {"timestamp": datetime.now(UTC).isoformat(), "total": len(reports)},
            "summary": summary,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
    else:
        if summary and not quiet:
            rprint("\n")
            table = Table(title="📊 Benchmark — Resumo")
            table.add_column("Projeto", style="cyan")
            table.add_column("Status", style="bold")
            table.add_column("Delta Direto %", justify="right")
            table.add_column("Delta Indireto %", justify="right")
            table.add_column("Delta Total %", justify="right")
            table.add_column("Delta Venda %", justify="right")
            for row in summary:
                status_style = "green" if "OK" in row["Status"] else "yellow" if "AVISO" in row["Status"] else "red"
                table.add_row(
                    row["Projeto"],
                    row["Status"],
                    row["Delta Direto %"],
                    row["Delta Indireto %"],
                    row["Delta Total %"],
                    row["Delta Venda %"],
                    style=status_style,
                )
            rprint(table)

        # Save summary file
        summary_file = root / "BENCHMARK_SUMMARY.json"
        summary_artifact = {
            "meta": {"timestamp": datetime.now(UTC).isoformat(), "total": len(reports)},
            "summary": summary,
        }
        summary_file.write_text(
            json.dumps(summary_artifact, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )
        rprint(f"\n✓ Resumo salvo em: {summary_file}")


@app.command("run")
def run_benchmarks(
    slug: str = typer.Option("", help="Slug do benchmark (ex: CTC). Omita para todos (use run-batch para batch mode)."),
    reset: bool = typer.Option(False, "--reset", help="Força re-execução mesmo se já existir resultado."),
    pack: bool = typer.Option(False, "--pack", help="Empacota artefatos de saída em ZIP ao final."),
    charts: bool = typer.Option(False, "--charts", help="Gera gráficos PNG antes de empacotar (requer matplotlib)."),
) -> None:
    """Executa um benchmark específico ou todos (use run-batch para modo batch)."""

    root = _tools_root()
    batch_runner = BenchmarkBatchRunner(
        benchmarks_root=root / "benchmarks" / "data",
        config_root=config_root(),
        projects_root=benchmark_projects_root(),
    )

    if not slug:
        reports = batch_runner.run_all(reset=reset)
        summary = batch_runner.build_summary(reports)
        if summary:
            table = Table(title="Benchmark — Resumo")
            table.add_column("Projeto", style="cyan")
            table.add_column("Status")
            table.add_column("Delta Direto %", justify="right")
            table.add_column("Delta Indireto %", justify="right")
            table.add_column("Delta Total %", justify="right")
            table.add_column("Delta Venda %", justify="right")
            for row in summary:
                table.add_row(
                    row["Projeto"],
                    row["Status"],
                    row["Delta Direto %"],
                    row["Delta Indireto %"],
                    row["Delta Total %"],
                    row["Delta Venda %"],
                )
            rprint(table)
        return

    target_slug = slug.upper()
    target_ref = find_benchmark_reference(batch_runner.benchmarks_root, target_slug)
    if target_ref is None:
        available = ", ".join(discover_benchmark_slugs(batch_runner.benchmarks_root)) or "(nenhum benchmark encontrado)"
        rprint(f"[red]Benchmark '{target_slug}' não encontrado.[/red] Disponíveis: {available}")
        raise typer.Exit(1) from None

    target_spec = BenchmarkSpecLoader(config_root()).load(target_ref)

    runner = BenchmarkRunner(
        config_root=config_root(),
        projects_root=benchmark_projects_root(),
        report_builder=BenchmarkReportBuilder(),
        report_printer=BenchmarkReportPrinter(),
    )
    rprint(f"[cyan]-> {target_slug}[/cyan]", end=" ")
    try:
        runner.run(target_spec, reset=reset)
        rprint("[green]OK[/green]")
    except Exception as e:
        rprint(f"[red]ERRO: {e}[/red]")
        raise typer.Exit(1) from None

    if pack or charts:
        _empacotar_benchmark_cli(target_slug, root, gerar_charts=charts or pack)


@app.command("pack")
def pack_benchmark(
    slug: str = typer.Option(..., "--slug", help="Slug do benchmark (ex: AGIS)."),
    output: str = typer.Option("", "--output", "-o", help="Caminho do ZIP de saída (default: outputs/)."),
    charts: bool = typer.Option(True, "--charts/--no-charts", help="Gera/atualiza PNGs antes de empacotar."),
    cenarios: bool = typer.Option(False, "--cenarios", help="Inclui JSONs dos cenários intermediários."),
) -> None:
    """Empacota artefatos de saída do benchmark (PNGs, relatórios, audit) em ZIP."""
    from pathlib import Path as _Path


    rprint(f"[cyan]Empacotando benchmark {slug.upper()}...[/cyan]")

    try:
        zip_path = empacotar_outputs(
            slug=slug,
            config_root=get_config_root(),
            output_path=_Path(output) if output else None,
            gerar_graficos=charts,
            incluir_cenarios=cenarios,
        )
    except Exception as e:
        rprint(f"[red]Erro: {e}[/red]")
        raise typer.Exit(1) from None

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    rprint(f"[green]Pacote criado:[/green] {zip_path}")
    rprint(f"  Tamanho: [bold]{size_mb:.2f} MB[/bold]")

    # Lista conteúdo
    import zipfile

    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        for pasta in ("graficos", "relatorio", "audit", "cenarios", "inputs"):
            items = [i for i in infos if i.filename.startswith(pasta + "/")]
            if items:
                rprint(f"  [dim]{pasta}/[/dim]  {len(items)} arquivo(s)")


@app.command("analyze")
def analyze() -> None:
    """Exibe tabela de deltas de custo direto para todos os benchmarks."""

    root = _tools_root()
    root / "benchmarks" / "data"

    table = Table(title="Benchmark — Custo Direto")
    table.add_column("Projeto", style="cyan")
    table.add_column("CD Ref (R$)", justify="right")
    table.add_column("CD Engine (R$)", justify="right")
    table.add_column("Delta (%)", justify="right")

    for benchmark_file in sorted(root.glob("benchmark_*.json")):
        try:
            data = json.loads(benchmark_file.read_text(encoding="utf-8"))
            confronto = data.get("confronto", {})
            ref = confronto.get("referencia", {})
            ferr = confronto.get("ferramenta", {})
            deltas = confronto.get("deltas", {})
            slug = data.get("slug", benchmark_file.stem)
            cd_ref = float(ref.get("custo_direto") or 0)
            cd_eq = float(ferr.get("custo_direto") or 0)
            delta_pct = float((deltas.get("custo_direto") or {}).get("percentual") or 0)
            color = "green" if abs(delta_pct) < 5 else "yellow" if abs(delta_pct) < 20 else "red"
            table.add_row(slug, f"{cd_ref:,.2f}", f"{cd_eq:,.2f}", f"[{color}]{delta_pct:+.2f}%[/{color}]")
        except Exception:
            continue

    rprint(table)


@app.command("trace")
def extract_trace(
    slug: str = typer.Argument(..., help="Slug do benchmark (ex: CTC)"),
) -> None:
    """Extrai referências de iteração do engine para um benchmark."""

    root = _tools_root()
    reports = [p for p in iter_benchmark_reports(root) if slug.upper() in p.name.upper()]
    if not reports:
        rprint(f"[red]Benchmark report não encontrado para {slug}[/red]")
        raise typer.Exit(1) from None

    out = extract_engine_iteration_references(reports[0], root=root)
    rprint(f"[green]Extraído:[/green] {len(out.get('equipes', {}).get('equipes', []))} equipes")


@app.command("audit")
def audit(
    slug: str = typer.Argument(..., help="Slug do benchmark (ex: CTC)"),
) -> None:
    """Executa a auditoria das 6 perguntas para um benchmark."""

    root = _tools_root()
    result = run_audit(slug.upper(), root=root)
    rprint(json.dumps(result, indent=2, ensure_ascii=False))


@app.command("cleanup")
def cleanup() -> None:
    """Remove intermediários temporários de benchmarks (logs de rerun, JSONs de extracao)."""

    root = _tools_root()
    removed = 0
    for pattern in ("**/rerun.log", "benchmarks/stage_discrepancias_resumo.json"):
        for f in root.glob(pattern):
            f.unlink()
            removed += 1
            rprint(f"[dim]removido: {f.relative_to(root)}[/dim]")
    rprint(f"[green]Limpeza concluída. {removed} arquivos removidos.[/green]")


@app.command("summary")
def stage_summary(
    output: str = typer.Option("", help="Caminho para salvar JSON de saída."),
) -> None:
    """Gera sumário de discrepâncias por etapa para todos os benchmarks."""

    root = _tools_root()
    summary = build_stage_discrepancy_summary(root=root)
    meta = summary["meta"]
    rprint(f"[bold]Benchmarks analisados:[/bold] {meta['total_benchmarks_com_extracao']}")
    rprint(f"Com equipes zeradas: {meta['benchmarks_com_equipes_zeradas']}")
    rprint(f"Com planejamento zerado: {meta['benchmarks_com_itens_planejamento_zerados']}")

    if output:
        Path(output).write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        rprint(f"[green]Salvo em {output}[/green]")


@app.command("iterate")
def iterate_correction(
    slug: str = typer.Argument(..., help="Slug do benchmark (ex: CTC)"),
) -> None:
    """Orquestra ciclo completo: correcao -> rerun -> extract -> validate."""

    root = _tools_root()

    # 1) Re-run do benchmark
    runner = BenchmarkBatchRunner(
        benchmarks_root=root / "benchmarks" / "data",
        config_root=root / "config",
        projects_root=benchmark_projects_root(),
    )
    # Run single benchmark by slug
    specs = [s for s in runner.discover_specs() if s.slug.upper() == slug.upper()]
    if specs:
        bench_runner = BenchmarkRunner(
            config_root=runner.config_root,
            projects_root=runner.projects_root,
            report_builder=BenchmarkReportBuilder(),
            report_printer=BenchmarkReportPrinter(),
        )
        bench_runner.run(specs[0], reset=True)

    # 2) Re-extração
    reports = [p for p in iter_benchmark_reports(root) if slug.upper() in p.name.upper()]
    if reports:
        extract_engine_iteration_references(reports[0], root=root)

    # 3) Validações
    pipeline = validate_pipeline_integrity(slug.upper(), root=root)
    audit = run_audit(slug.upper(), root=root)

    rprint("[green]Iteração concluída.[/green]")
    rprint(
        json.dumps(
            {"pipeline": pipeline.get("validacoes_fechamento", []), "audit": audit.get("resumo", {})},
            indent=2,
            ensure_ascii=False,
        )
    )


@app.command("plan-space")
def plan_space(
    slug: str = typer.Option(..., "--slug", help="Slug do benchmark (ex: AGIS)."),
    reset: bool = typer.Option(True, "--reset/--no-reset", help="Reexecuta limpo cada alternativa."),
    workers: int = typer.Option(0, "--workers", help="Threads paralelas (0 = auto: min(alternativas, 8))."),
) -> None:
    """Explora cenários de benchmark (AUTO) sem poluir projetos reais."""

    root = _tools_root()
    slug_upper = slug.upper()
    bench_dir = root / "benchmarks" / "data" / slug_upper
    ref_path = bench_dir / "referencia.json"
    if not ref_path.exists():
        ref_path = bench_dir / "artifacts" / "inputs" / "referencia.json"
    if not ref_path.exists():
        rprint(f"[red]referencia.json não encontrado para slug {slug_upper}.[/red]")
        raise typer.Exit(1) from None

    base_ref = json.loads(ref_path.read_text(encoding="utf-8"))
    # v2: cenarios fica em spec; v1: fica no topo
    cenarios_embutidos = (base_ref.get("spec") or base_ref).get("cenarios")
    alternativas = cenarios_embutidos if isinstance(cenarios_embutidos, list) and cenarios_embutidos else []

    if not alternativas:
        rprint("[red]Sem cenários em referencia.json. Defina 'cenarios' obrigatoriamente.[/red]")
        raise typer.Exit(1) from None

    out_dir = bench_dir / "artifacts" / "intermediate"
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir = bench_dir / "artifacts" / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    cfg_root = config_root()
    proj_root = benchmark_projects_root()

    tasks = _prepare_plan_space_tasks(base_ref, ref_path, alternativas)
    num_workers = workers if workers > 0 else min(len(tasks), 8)
    rprint(f"[bold]Executando {len(tasks)} alternativas com {num_workers} worker(s)...[/bold]")

    rows, failed = _execute_plan_space_tasks(tasks, num_workers, reset, cfg_root, proj_root, out_dir)

    if failed:
        rprint(f"[red]{len(failed)} alternativa(s) falharam: {', '.join(failed)}[/red]")
        raise typer.Exit(1) from None

    rows_sorted = sorted(
        rows,
        key=lambda r: (
            r["makespan_semanas"] or 9999,
            abs(float(r["delta_preco_venda_pct"])) if r["delta_preco_venda_pct"] is not None else 999999,
        ),
    )

    _save_plan_space_results(rows_sorted, slug_upper, root, outputs_dir, bench_dir)

    summary = {"slug": slug_upper, "projects_root": str(benchmark_projects_root()), "rows": rows_sorted}
    (out_dir / "plan_space_report.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    _save_plan_space_markdown(rows_sorted, slug_upper, outputs_dir)


@app.command("compare")
def compare_algorithms(
    slug: str = typer.Option(..., "--slug", "-s", help="Slug do benchmark (ex: CTC)."),
    algorithms: str = typer.Option(
        "",
        "--algorithms",
        "-a",
        help="Algoritmos separados por vírgula (default: CP-SAT,LNS,MINSLK).",
    ),
    reset: bool = typer.Option(False, "--reset", help="Remove projeto existente antes de rodar."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Salva relatório JSON neste caminho."),
) -> None:
    """Compara CP-SAT, LNS e MINSLK no mesmo benchmark e reporta impacto nos entregáveis.

    Roda o pipeline uma vez por algoritmo (cada execução permanece single-algo),
    consolida makespan, quality_score, custo total e custo de mob e exibe tabela
    comparativa.

    Exemplos:\b
        concilium benchmark compare --slug CTC
        concilium benchmark compare --slug CTC --algorithms MINSLK,LPT
        concilium benchmark compare --slug CTC --reset --output comparison.json
    """

    root = _tools_root()
    target_slug = slug.upper()
    target_ref = find_benchmark_reference(root / "benchmarks" / "data", target_slug)
    if target_ref is None:
        available = ", ".join(discover_benchmark_slugs(root / "benchmarks" / "data")) or "(nenhum benchmark encontrado)"
        rprint(f"[red]Benchmark '{target_slug}' não encontrado.[/red] Disponíveis: {available}")
        raise typer.Exit(1) from None

    spec = BenchmarkSpecLoader(config_root()).load(target_ref)
    algos = [a.strip() for a in algorithms.split(",") if a.strip()] or None

    rprint(f"[bold cyan]Comparação de algoritmos:[/bold cyan] {target_slug}")

    runner = AlgorithmComparisonRunner(
        config_root=config_root(),
        projects_root=benchmark_projects_root(),
    )
    try:
        runner.compare(spec, algorithms=algos, reset=reset, save_json=output)
    except Exception as exc:
        rprint(f"[red]ERRO: {exc}[/red]")
        raise typer.Exit(1) from None
