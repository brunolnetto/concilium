"""Helper functions for commands_manage (B)."""

# ruff: noqa: F401
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from concilium.presentation.cli.shared import resolve_project

from ._commands_manage_helpers_a import _append_jsonl, _load_json, _write_json


def _cs_resolve_layer(
    target: str | None,
    output: str | None,
) -> tuple[str, str | None]:
    layer: str | None = (target or "").strip().lower() or None
    if layer is None and output and output.strip().lower() in {"project", "master"}:
        layer = output.strip().lower()
        output = None
    if layer is None:
        layer = "project"
    if layer not in {"project", "master"}:
        rprint("[red]Valor inválido para camada. Use --target project|master.[/red]")
        raise typer.Exit(1)
    return layer, output


def _cs_validate_layer(layer: str, projeto: str | None, confirm_master: bool) -> None:
    if layer == "project" and not projeto:
        rprint(
            "[red]ADR-040: survey agora salva em projeto por padrão.[/red] "
            "Informe --project <id|nome> ou use --target master --confirm-master."
        )
        raise typer.Exit(1)
    if layer == "master" and not confirm_master:
        rprint("[red]Escrita em master requer confirmação explícita.[/red] Use --confirm-master para prosseguir.")
        raise typer.Exit(1)


def _cs_resolve_path(output, layer, survey_type, contexto_id, projeto, catalogo_id, config_root_fn) -> Path:
    if output and output.strip().lower() not in {"project", "master"}:
        return Path(output)
    filename = f"pesquisa_{survey_type}_{contexto_id}.xlsx"
    if layer == "project":
        project_store = resolve_project(projeto)
        return project_store.root / "overrides" / "surveys" / filename
    return config_root_fn() / "catalogos" / catalogo_id / "surveys" / filename


def _impl_catalog_survey(
    contexto_id: str = typer.Option("mendeslobo", "--contexto", "-c", help="ID do contexto"),
    jurisdicao_id: str = typer.Option(None, "--jurisdicao", "-j", help="ID da jurisdição para benchmark regional"),
    survey_type: str = typer.Option("price", "--type", "-t", help="Tipo de pesquisa: 'price' ou 'productivity'"),
    output: str = typer.Option(
        None, "--output", "-o", help="Caminho do arquivo de saída (.xlsx) ou camada project/master"
    ),
    target: str = typer.Option(None, "--target", help="Camada de persistência: project|master (ADR-040)."),
    projeto: str = typer.Option(None, "--project", "-p", help="Projeto alvo quando target=project."),
    confirm_master: bool = typer.Option(
        False, "--confirm-master", help="Confirma gravação explícita na camada master."
    ),
    actor: str = typer.Option("cli", "--actor", help="Ator para trilha de auditoria quando target=project."),
):
    """Gera planilha de pesquisa (Mapa de Cotação ou Aferição de Produtividade)."""
    from concilium.infrastructure.exporters.price_survey import PriceSurveyExporter
    from concilium.infrastructure.exporters.productivity_survey import ProductivitySurveyExporter
    from concilium.presentation.mcp._context import _config_root, _runtime

    rt = _runtime()
    ctx = rt.load_contexto(contexto_id)
    catalogo = rt.load_catalogo(ctx.catalogo_id)
    # ADR-065: TemaVisual substitui identidade_visual em ContextoObra
    catalogo["identidade_visual"] = rt.load_tema(ctx.tema_id).to_catalogo_dict()
    console = Console()

    layer, output = _cs_resolve_layer(target, output)
    _cs_validate_layer(layer, projeto, confirm_master)
    path = _cs_resolve_path(output, layer, survey_type, contexto_id, projeto, ctx.catalogo_id, _config_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    jur_id = jurisdicao_id or ctx.jurisdicao_id

    with console.status(f"[bold yellow]Gerando mapa de cotação ({jur_id}) em {path.name}..."):
        try:
            if survey_type == "price":
                exporter = PriceSurveyExporter(catalogo, jurisdicao_id=jur_id)
            else:
                exporter = ProductivitySurveyExporter(catalogo, jurisdicao_id=jur_id)  # type: ignore[assignment]
            exporter.export(path)
            console.print(
                f"\n[bold yellow][OK] Mapa de Cotação gerado ({layer}):[/bold yellow] [cyan]{path.absolute()}[/cyan]"
            )
            console.print("Dica: Os campos em destaque Amarelo são para preenchimento do fornecedor.")
            if layer == "project":
                project_store = resolve_project(projeto)
                _append_jsonl(
                    project_store.root / "audit_log.jsonl",
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "actor": actor,
                        "action": "catalog_survey_export",
                        "payload": {
                            "contexto_id": contexto_id,
                            "survey_type": survey_type,
                            "jurisdicao_id": jur_id,
                            "target": layer,
                            "path": str(path),
                        },
                        "result": {"status": "OK"},
                        "status": "OK",
                        "error": None,
                    },
                )
        except Exception as e:
            console.print(f"[bold red]Erro ao gerar pesquisa:[/bold red] {e}")
            raise typer.Exit(1) from None


def _cp_validate_override(overrides: dict, insumo_id: str) -> tuple[dict, object]:
    """Valida e extrai override_item e novo_preco. Levanta typer.Exit se inválido."""
    import typer

    if insumo_id not in overrides:
        from rich import print as rprint

        rprint(f"[red]Insumo {insumo_id} não encontrado em overrides do projeto.[/red]")
        raise typer.Exit(1)
    override_item = overrides.get(insumo_id, {})
    if not isinstance(override_item, dict):
        from rich import print as rprint

        rprint(f"[red]Override inválido para {insumo_id}. Esperado objeto JSON.[/red]")
        raise typer.Exit(1)
    novo_preco = (
        override_item.get("preco_calibrado") or override_item.get("preco_unitario") or override_item.get("preco")
    )
    if novo_preco is None:
        from rich import print as rprint

        rprint(f"[red]Override de {insumo_id} não possui preço calibrado para promoção.[/red]")
        raise typer.Exit(1)
    return override_item, novo_preco


def _cp_update_price_history(
    historico: list,
    preco_float: float,
    dt_iso: str,
    project_store: object,
    justificativa: str,
) -> None:
    open_entry = None
    for registro in reversed(historico):
        if isinstance(registro, dict) and registro.get("data_fim_vigencia") is None:
            open_entry = registro
            break
    if not (isinstance(open_entry, dict) and float(open_entry.get("preco_unitario", -1)) == preco_float):
        for registro in historico:
            if not isinstance(registro, dict):
                continue
            if registro.get("data_fim_vigencia") is None:
                registro["data_fim_vigencia"] = dt_iso
        historico.append(
            {
                "preco_unitario": preco_float,
                "data_inicio_vigencia": dt_iso,
                "data_fim_vigencia": None,
                "fonte": "PROMOTED_FROM_PROJECT_OVERRIDE",
                "projeto_origem": str(project_store.meta.get("id", project_store.root.name)),
                "justificativa": justificativa,
            }
        )


def _impl_catalog_promote(
    projeto: str = typer.Option(..., "--project", "-p", help="Projeto de origem do override."),
    insumo_id: str = typer.Option(..., "--insumo", "-i", help="Código do insumo a promover."),
    justificativa: str = typer.Option(..., "--justificativa", "-j", help="Justificativa da promoção para master."),
    contexto_id: str = typer.Option(None, "--contexto", "-c", help="Override do contexto (opcional)."),
    data_vigencia: str = typer.Option(None, "--data-vigencia", help="Data efetiva da promoção (YYYY-MM-DD)."),
    actor: str = typer.Option("cli", "--actor", help="Ator para trilha de auditoria."),
    force: bool = typer.Option(False, "--force", help="Confirma ação de promoção para camada master."),
) -> None:
    """Promove override de insumo do projeto para o catálogo master (ADR-040 + ADR-041)."""
    from concilium.application.orchestrators.catalog_governance import (
        CatalogGovernanceError,
        validate_and_resolve_insumo_file,
    )
    from concilium.presentation.mcp._context import _config_root, _runtime

    if not force:
        rprint(
            "[red]Promoção para master requer confirmação explícita.[/red] "
            "Reexecute com --force quando a curadoria estiver aprovada."
        )
        raise typer.Exit(1)

    project_store = resolve_project(projeto)
    override_file = project_store.root / "overrides" / "insumos_override.json"
    overrides = _load_json(override_file, {})
    override_item, novo_preco = _cp_validate_override(overrides, insumo_id)

    try:
        dt_vigencia = date.fromisoformat(data_vigencia) if data_vigencia else date.today()
    except ValueError:
        rprint("[red]--data-vigencia inválida. Use formato YYYY-MM-DD.[/red]")
        raise typer.Exit(1) from None

    contexto_efetivo = contexto_id or project_store.meta.get("contexto_id")
    if not contexto_efetivo:
        rprint("[red]Não foi possível determinar contexto do projeto para promoção.[/red]")
        raise typer.Exit(1)

    rt = _runtime()
    ctx = rt.load_contexto(contexto_efetivo)
    catalog_root = _config_root() / "catalogos" / ctx.catalogo_id
    try:
        insumo_file = validate_and_resolve_insumo_file(catalog_root, insumo_id, float(novo_preco))
    except CatalogGovernanceError as exc:
        rprint(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None

    insumo_master = _load_json(insumo_file, {})
    historico = insumo_master.setdefault("historico_precos", [])
    if not isinstance(historico, list):
        historico = []
        insumo_master["historico_precos"] = historico

    preco_float = float(novo_preco)
    dt_iso = dt_vigencia.isoformat()
    _cp_update_price_history(historico, preco_float, dt_iso, project_store, justificativa)

    insumo_master["preco_unitario"] = preco_float
    _write_json(insumo_file, insumo_master)

    promotion_event = {
        "timestamp": datetime.now(UTC).isoformat(),
        "contexto_id": contexto_efetivo,
        "catalogo_id": ctx.catalogo_id,
        "insumo_id": insumo_id,
        "novo_preco": preco_float,
        "data_vigencia": dt_iso,
        "justificativa": justificativa,
        "actor": actor,
        "source_override": override_item,
    }
    _append_jsonl(project_store.root / "overrides" / "historico" / "promotions.jsonl", promotion_event)

    overrides.pop(insumo_id, None)
    _write_json(override_file, overrides)

    _append_jsonl(
        project_store.root / "audit_log.jsonl",
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "actor": actor,
            "action": "catalog_promote_insumo",
            "payload": {
                "insumo_id": insumo_id,
                "novo_preco": preco_float,
                "data_vigencia": dt_iso,
                "justificativa": justificativa,
                "contexto_id": contexto_efetivo,
            },
            "result": {"status": "OK", "catalogo_id": ctx.catalogo_id},
            "status": "OK",
            "error": None,
        },
    )

    rprint(f"[green]Promoção concluída.[/green] {insumo_id} -> master ({ctx.catalogo_id}) com vigência {dt_iso}.")


def _impl_catalog_search(
    contexto_id: str = typer.Option(..., "--contexto", "-c"), query: str = typer.Argument(..., help="Termo de busca")
):
    """Busca CPUs por termo no código ou descrição."""
    from concilium.presentation.mcp._context import _runtime

    rt = _runtime()
    ctx = rt.load_contexto(contexto_id)
    catalogo = rt.load_catalogo(ctx.catalogo_id)

    console = Console()
    table = Table(title=f"Busca: '{query}' em {contexto_id}")
    table.add_column("Código", style="cyan")
    table.add_column("Descrição")

    q = query.lower()
    for cpu in catalogo.get("cpus", []):
        if q in str(cpu.get("codigo")).lower() or q in str(cpu.get("descricao")).lower():
            table.add_row(cpu.get("codigo"), cpu.get("descricao"))

    console.print(table)
