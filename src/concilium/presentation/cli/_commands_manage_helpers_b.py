"""Helper functions for commands_manage (B)."""

# ruff: noqa: F401
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from concilium.presentation.cli.shared import resolve_project


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


def _cs_survey_filename(survey_type: str, contexto_id: str) -> str:
    return f"pesquisa_{survey_type}_{contexto_id}.xlsx"


def _cs_resolve_path(output, layer, survey_type, contexto_id, projeto, catalogo_id, config_root_fn) -> Path:
    """Resolve o Path real de saída — só para --output explícito ou camada master.

    Camada "project" NÃO resolve para um Path de filesystem: `ProjectHandle.root`
    é lógico (não-backed) em backends não-filesystem (StorageProjectHandle);
    o caller grava via `project_store.write_bytes(...)` em vez de um Path real."""
    if output and output.strip().lower() not in {"project", "master"}:
        return Path(output)
    filename = _cs_survey_filename(survey_type, contexto_id)
    return config_root_fn() / "catalogos" / catalogo_id / "surveys" / filename


def _impl_catalog_survey(
    contexto_id: str = typer.Option("mendeslobo", "--contexto", "-c", help="ID do contexto"),
    jurisdicao_id: str = typer.Option(None, "--jurisdicao", "-j", help="ID da jurisdição para benchmark regional"),
    survey_type: str = typer.Option("price", "--type", "-t", help="Tipo de pesquisa: 'price' ou 'productivity'"),
    output: str | None = typer.Option(
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

    filename = _cs_survey_filename(survey_type, contexto_id)
    explicit_output = bool(output and output.strip().lower() not in {"project", "master"})
    jur_id = jurisdicao_id or ctx.jurisdicao_id

    with console.status(f"[bold yellow]Gerando mapa de cotação ({jur_id}) em {filename}..."):
        try:
            if survey_type == "price":
                exporter = PriceSurveyExporter(catalogo, jurisdicao_id=jur_id)
            else:
                exporter = ProductivitySurveyExporter(catalogo, jurisdicao_id=jur_id)  # type: ignore[assignment]

            if layer == "project" and not explicit_output:
                # Camada project: grava via ProjectHandle.write_bytes, nunca um Path real
                # de filesystem — project_store.root é lógico (não-backed) em backends
                # não-filesystem (StorageProjectHandle).
                import tempfile

                relative_path = f"overrides/surveys/{filename}"
                with tempfile.NamedTemporaryFile(suffix=".xlsx") as tmp:
                    exporter.export(Path(tmp.name))
                    data = Path(tmp.name).read_bytes()
                project_store = resolve_project(projeto)
                project_store.write_bytes(relative_path, data)
                display_path = f"{relative_path} (projeto {projeto})"
            else:
                path = _cs_resolve_path(output, layer, survey_type, contexto_id, projeto, ctx.catalogo_id, _config_root)
                path.parent.mkdir(parents=True, exist_ok=True)
                exporter.export(path)
                display_path = str(path.absolute())

            console.print(
                f"\n[bold yellow][OK] Mapa de Cotação gerado ({layer}):[/bold yellow] [cyan]{display_path}[/cyan]"
            )
            console.print("Dica: Os campos em destaque Amarelo são para preenchimento do fornecedor.")
            if layer == "project":
                project_store = resolve_project(projeto)
                project_store.append_jsonl(
                    "audit_log.jsonl",
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "actor": actor,
                        "action": "catalog_survey_export",
                        "payload": {
                            "contexto_id": contexto_id,
                            "survey_type": survey_type,
                            "jurisdicao_id": jur_id,
                            "target": layer,
                            "path": display_path,
                        },
                        "result": {"status": "OK"},
                        "status": "OK",
                        "error": None,
                    },
                )
        except Exception as e:
            console.print(f"[bold red]Erro ao gerar pesquisa:[/bold red] {e}")
            raise typer.Exit(1) from None


def _impl_catalog_promote(
    projeto: str = typer.Option(..., "--project", "-p", help="Projeto de origem do override."),
    justificativa: str = typer.Option(..., "--justificativa", "-j", help="Justificativa da promoção para master."),
    contexto_id: str = typer.Option(None, "--contexto", "-c", help="Override do contexto (opcional)."),
    actor: str = typer.Option("cli", "--actor", help="Ator para trilha de auditoria e regra dos quatro-olhos."),
    force: bool = typer.Option(False, "--force", help="Confirma ação de promoção para camada master."),
) -> None:
    """Promove os overrides de insumo e CPU pendentes do projeto para o catálogo master (ADR-150 D4).

    Antes desta ADR, este comando gravava direto em `insumo_file` via
    `_write_json` — sem rascunho, sem `CatalogSnapshot`, sem quatro-olhos, sem
    checar sequer a chave composta (`codigo::jurisdicao`) usada por
    `atualizar_preco_insumo(projeto_id=...)`, o que na prática fazia a
    promoção nunca encontrar os overrides gravados por aquele tool (ADR-150
    P2). Substituído pelo mesmo caminho gated do tool MCP
    `promover_override_projeto` — reaproveita `RepositorioInsumo.atualizar_preco()`
    (SCD2 real) e `CatalogSnapshot`/`CatalogDiff` em vez de reimplementar
    histórico de preço manualmente.

    A CLI é um ator de confiança local, sem token JWT real — roda com role
    `admin` (equivalente a um operador já autorizado a mexer no catálogo
    mestre localmente), mas ainda respeita a regra dos quatro-olhos
    (quem editou o override não pode ser `--actor`) e, se
    `CONCILIUM__AUTH_ENABLED=1`, o gate de ownership do projeto (ADR-126).
    `--force` continua sendo a confirmação de intenção explícita.

    Promove TODOS os overrides de insumo E de CPU pendentes do projeto de uma
    vez — a granularidade por `--insumo`/`--data-vigencia` foi descontinuada.
    `bdi_override.json` não é coberto (ver ADR-150, seção Achados: arquivo sem
    leitor no pipeline real).
    """
    from concilium.infrastructure.auth.permission_guard import (
        _current_roles,
        reset_auth_context,
        set_auth_context,
        set_roles,
    )
    from concilium.presentation.mcp.tools._catalogo_tools_helpers_c import _impl_promover_override_projeto

    if not force:
        rprint(
            "[red]Promoção para master requer confirmação explícita.[/red] "
            "Reexecute com --force quando a curadoria estiver aprovada."
        )
        raise typer.Exit(1)

    project_store = resolve_project(projeto)
    roles_token = set_roles(["admin"])
    auth_tokens = set_auth_context(user_id=actor, tenant_id=None)
    try:
        result = _impl_promover_override_projeto(project_store.root.name, contexto_id, justificativa)
    finally:
        reset_auth_context(auth_tokens)
        _current_roles.reset(roles_token)

    if "erro" in result:
        rprint(f"[red]{result['erro']}[/red]")
        raise typer.Exit(1)

    rprint(f"[bold green][OK][/bold green] Promoção concluída: {result}")


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
