"""Helper functions for commands_manage (B)."""

# ruff: noqa: F401
from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from concilium.presentation.cli.shared import resolve_project
from concilium.presentation.mcp._context import _config_root, _runtime


def _build_schema_validators(schema_root: Path) -> tuple:
    """Loads JSON schemas and builds Draft 2020-12 validators. Raises typer.Exit(2) on missing files."""
    from jsonschema import Draft202012Validator, RefResolver

    cpu_schema_path = schema_root / "cpu.schema.json"
    prod_schema_path = schema_root / "producao.schema.json"
    insumo_schema_path = schema_root / "insumo.schema.json"
    for p in [cpu_schema_path, prod_schema_path, insumo_schema_path]:
        if not p.exists():
            rprint(f"[red]Schema não encontrado:[/red] {p}")
            raise typer.Exit(2)
    cpu_schema = json.loads(cpu_schema_path.read_text(encoding="utf-8"))
    prod_schema = json.loads(prod_schema_path.read_text(encoding="utf-8"))
    insumo_schema = json.loads(insumo_schema_path.read_text(encoding="utf-8"))
    common_path = schema_root / "common.schema.json"
    extra = [json.loads(common_path.read_text(encoding="utf-8"))] if common_path.exists() else []
    base_uri = schema_root.resolve().as_uri() + "/"
    schema_store = {s["$id"]: s for s in [cpu_schema, prod_schema, insumo_schema, *extra] if "$id" in s}
    cpu_v = Draft202012Validator(
        cpu_schema, resolver=RefResolver(base_uri=base_uri, referrer=cpu_schema, store=schema_store)
    )
    prod_v = Draft202012Validator(
        prod_schema, resolver=RefResolver(base_uri=base_uri, referrer=prod_schema, store=schema_store)
    )
    ins_v = Draft202012Validator(
        insumo_schema, resolver=RefResolver(base_uri=base_uri, referrer=insumo_schema, store=schema_store)
    )
    return cpu_v, prod_v, ins_v


def _run_schema_validation(validator: object, items: list, entity_prefix: str, id_field: str, erros: list) -> None:
    for item in items:
        item_id = item.get(id_field, f"<sem-{id_field}>")
        for err in validator.iter_errors(item):
            path = ".".join([str(x) for x in err.absolute_path])
            erros.append(f"{entity_prefix} {item_id}: {path or '<root>'} -> {err.message}")


def _check_catalog_semantics(cpus: list, prods: list, erros: list, avisos: list) -> None:
    prod_ids = {p.get("id") for p in prods if p.get("id")}
    for cpu in cpus:
        ref = cpu.get("producao_id_ref")
        if ref and ref not in prod_ids:
            erros.append(f"CPU {cpu.get('codigo')}: producao_id_ref inexistente ({ref})")
    historical_keys = ["producao_horaria", "producao_id", "equipe"]
    for cpu in cpus:
        presentes = [k for k in historical_keys if k in cpu]
        if presentes:
            avisos.append(f"CPU {cpu.get('codigo')}: campos legados presentes {presentes}")


def _print_messages_section(console: Console, messages: list, title_markup: str, tail_text: str, limit: int) -> None:
    if not messages:
        return
    console.print(f"\n{title_markup}")
    for msg in messages[:limit]:
        console.print(f" - {msg}")
    if len(messages) > limit:
        console.print(f" ... mais {len(messages) - limit} {tail_text}")


def _print_catalog_validation_results(
    console: Console, cpus: list, prods: list, insumos: list, erros: list, avisos: list, catalogo_id: str
) -> None:
    table = Table(title=f"Validação Schema - {catalogo_id}", show_header=True, header_style="bold cyan")
    table.add_column("Entidade")
    table.add_column("Total")
    table.add_column("Erros")
    table.add_column("Avisos")
    table.add_row(
        "CPU",
        str(len(cpus)),
        str(sum(1 for e in erros if e.startswith("CPU "))),
        str(sum(1 for w in avisos if w.startswith("CPU "))),
    )
    table.add_row("PRODUCAO", str(len(prods)), str(sum(1 for e in erros if e.startswith("PRODUCAO "))), "0")
    table.add_row("INSUMO", str(len(insumos)), str(sum(1 for e in erros if e.startswith("INSUMO "))), "0")
    console.print(table)
    _print_messages_section(console, erros, "[bold red]Erros de schema/semântica:[/bold red]", "erros", 30)
    _print_messages_section(console, avisos, "[bold yellow]Avisos:[/bold yellow]", "avisos", 20)


def _impl_catalog_validate_schema(
    contexto_id: str = typer.Option(..., "--contexto", "-c", help="ID do contexto"),
    fail_on_warning: bool = typer.Option(False, "--strict", help="Falha também em avisos semânticos"),
):
    """Valida catálogo contra JSON Schemas (Draft 2020-12) e regras semânticas básicas."""

    try:
        cpu_v, prod_v, ins_v = _build_schema_validators(Path("config") / "schemas" / "catalog")
    except ImportError:
        rprint("[red]Dependência 'jsonschema' não encontrada.[/red] Instale com: uv add jsonschema")
        raise typer.Exit(2) from None

    rt = _runtime()
    ctx = rt.load_contexto(contexto_id)
    catalogo = rt.load_catalogo(ctx.catalogo_id)
    console = Console()

    cpus = catalogo.get("cpus", [])
    insumos = catalogo.get("insumos", [])
    produtividades = catalogo.get("produtividades") if isinstance(catalogo.get("produtividades"), list) else []
    producoes_legado = catalogo.get("producoes") if isinstance(catalogo.get("producoes"), list) else []
    prods = produtividades + producoes_legado

    erros: list[str] = []
    avisos: list[str] = []
    _run_schema_validation(cpu_v, cpus, "CPU", "codigo", erros)
    _run_schema_validation(prod_v, prods, "PRODUCAO", "id", erros)
    _run_schema_validation(ins_v, insumos, "INSUMO", "codigo", erros)
    _check_catalog_semantics(cpus, prods, erros, avisos)
    _print_catalog_validation_results(console, cpus, prods, insumos, erros, avisos, ctx.catalogo_id)

    if erros or (fail_on_warning and avisos):
        raise typer.Exit(1)

    console.print("\n[bold green]Schema validation OK[/bold green]")


def _impl_catalog_tendencia(
    contexto_id: str = typer.Option(..., "--contexto", "-c", help="ID do contexto"),
    jurisdicao_id: str = typer.Option(None, "--jurisdicao", "-j", help="UF (ex: BR-CE) — usa preços SICRO regionais"),
    output: str = typer.Option("", "--output", "-o", help="Salva relatório JSON"),
):
    """Índice de Tendência de Preços (ADR-041 §D5 — Skill 20).

    Calcula variação de preço por categoria usando historico_precos (SCD Type 2)
    e preços SICRO regionais. Identifica categorias com inflação acima da média.
    """
    import json
    from pathlib import Path

    from concilium.application.catalog.price_trend import calcular_tendencia

    console = Console()
    bundle_path = _config_root() / "catalogos" / contexto_id / ".catalog_bundle.json"
    if not bundle_path.exists():
        rprint(f"[red]Bundle não encontrado: {bundle_path}[/red]")
        raise typer.Exit(1)

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    insumos = bundle.get("insumos", [])

    relatorio = calcular_tendencia(insumos, jurisdicao_id=jurisdicao_id, contexto_id=contexto_id)

    table = Table(
        title=f"Índice de Tendência de Preços — {contexto_id}" + (f" ({jurisdicao_id})" if jurisdicao_id else ""),
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Categoria")
    table.add_column("Total", justify="right")
    table.add_column("Com Histórico", justify="right")
    table.add_column("Var. Média %", justify="right")
    table.add_column("Var. Mediana %", justify="right")
    table.add_column("Var. Máx %", justify="right")

    for idx in relatorio.indices_por_categoria:

        def _fmt(v):
            return f"{v:+.1f}%" if v is not None else "—"

        color = "green"
        if idx.variacao_media_pct and idx.variacao_media_pct > 15:
            color = "yellow"
        if idx.variacao_media_pct and idx.variacao_media_pct > 30:
            color = "red"
        table.add_row(
            idx.tipo,
            str(idx.n_insumos_total),
            str(idx.n_insumos_com_historico),
            f"[{color}]{_fmt(idx.variacao_media_pct)}[/{color}]",
            _fmt(idx.variacao_mediana_pct),
            _fmt(idx.variacao_max_pct),
        )
    console.print(table)
    console.print(f"\n  Insumos analisados: {relatorio.resumo['total_insumos']}")
    console.print(f"  Com histórico SCD-2: {relatorio.resumo['total_com_historico']}")
    if jurisdicao_id:
        console.print(f"  Com preço SICRO {jurisdicao_id}: {relatorio.resumo['total_com_sicro_regional']}")

    if output:
        import dataclasses

        def _ser(obj):
            if dataclasses.is_dataclass(obj):
                return dataclasses.asdict(obj)
            raise TypeError(f"{type(obj)}")

        Path(output).write_text(
            json.dumps(dataclasses.asdict(relatorio), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        console.print(f"\n[dim]Relatório salvo: {output}[/dim]")


def _impl_catalog_audit_reasonability(
    contexto_id: str = typer.Option("mendeslobo", "--contexto", "-c", help="ID do contexto"),
    output: str = typer.Option(
        "",
        "--output",
        "-o",
        help="Caminho do artefato JSON de saída (default: artifacts/audit/catalog_reasonability_<catalogo>.json)",
    ),
    max_findings: int = typer.Option(20, "--max-findings", help="Máximo de achados exibidos no terminal"),
) -> None:
    """Gera artefato auditável de razoabilidade CPU x equipe x produtividade via CLI."""
    from concilium.application.services.catalog.catalog_reasonability import build_catalog_reasonability_artifact

    rt = _runtime()
    ctx = rt.load_contexto(contexto_id)
    catalogo = rt.load_catalogo(ctx.catalogo_id)
    cpus = catalogo.get("cpus") if isinstance(catalogo.get("cpus"), list) else []
    produtividades = catalogo.get("produtividades") if isinstance(catalogo.get("produtividades"), list) else []
    producoes_legado = catalogo.get("producoes") if isinstance(catalogo.get("producoes"), list) else []
    artifact = build_catalog_reasonability_artifact(ctx.catalogo_id, cpus, produtividades + producoes_legado)

    destination = (
        Path(output) if output else Path("artifacts") / "audit" / f"catalog_reasonability_{ctx.catalogo_id}.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = artifact.get("summary", {})
    findings = artifact.get("findings", [])
    console = Console()

    table = Table(title=f"Auditoria de Razoabilidade — {ctx.catalogo_id}", show_header=True, header_style="bold cyan")
    table.add_column("Métrica")
    table.add_column("Valor", justify="right")
    table.add_row("CPUs", str(summary.get("total_cpus", 0)))
    table.add_row("Erros", str(summary.get("erros", 0)))
    table.add_row("Avisos", str(summary.get("avisos", 0)))
    table.add_row("Outliers", str(summary.get("outliers", 0)))
    table.add_row("Mediana Prod/h", f"{float(summary.get('mediana_producao_horaria', 0.0)):.2f}")
    console.print(table)

    if findings:
        console.print("\n[bold yellow]Top achados:[/bold yellow]")
        for item in findings[: max(1, max_findings)]:
            issues = " | ".join(item.get("issues") or [])
            console.print(f" - {item.get('severity', 'OK'):5s} {item.get('cpu_id', '')}: {issues}")
    else:
        console.print("\n[bold green]Nenhum achado crítico identificado.[/bold green]")

    console.print(f"\n[dim]Artefato salvo em: {destination}[/dim]")


def _impl_catalog_cure_schema(
    contexto_id: str = typer.Option(..., "--contexto", "-c", help="ID do contexto"),
    apply: bool = typer.Option(True, "--apply/--dry-run", help="Aplica correções (padrão: --apply)"),
) -> None:
    """Executa curação estrita para remover/migrar campos legados do catálogo."""
    script = Path("scripts") / "cure_catalog.py"
    if not script.exists():
        rprint(f"[red]Script não encontrado:[/red] {script}")
        raise typer.Exit(2)

    cmd = [sys.executable, str(script), "--contexto", contexto_id]
    if apply:
        cmd.append("--apply")

    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)
