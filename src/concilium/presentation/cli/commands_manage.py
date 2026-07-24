"""Commands: catalog, bdi, structure (Escopo/Plano)."""

from __future__ import annotations

import typer

from ._commands_manage_helpers_a import (
    _impl_catalog_export,
    _impl_catalog_quality,
    _impl_catalog_simulate,
)
from ._commands_manage_helpers_b import (
    _impl_catalog_promote,
    _impl_catalog_search,
    _impl_catalog_survey,
)
from ._commands_manage_helpers_c import (
    _impl_catalog_cure_plausibility,
    _impl_catalog_merge_rfi,
    _impl_plan_init,
    _impl_structure_list,
)
from ._commands_manage_helpers_d import (
    _impl_catalog_audit_reasonability,
    _impl_catalog_cure_schema,
    _impl_catalog_tendencia,
    _impl_catalog_validate_schema,
)

app_catalog = typer.Typer(name="catalog", help="Gestão de Catálogos Corporativos.", no_args_is_help=True)
app_bdi = typer.Typer(name="bdi", help="Gestão do perfil BDI do projeto.", no_args_is_help=True)
app_structure = typer.Typer(name="structure", help="Gestão de Escopos e Planos.", no_args_is_help=True)


@app_catalog.command("list")
def catalog_list() -> None:
    """Lista os catálogos disponíveis no sistema."""
    from rich import print as rprint
    from rich.table import Table

    from concilium.presentation.mcp._context import _runtime

    rt = _runtime()
    catalogs_dir = rt.config_root / "catalogos"
    dirs = [d for d in sorted(catalogs_dir.iterdir()) if d.is_dir()]
    if not dirs:
        rprint("[yellow]Nenhum catálogo encontrado.[/yellow]")
        return

    t = Table(show_header=True, header_style="bold")
    t.add_column("Catálogo", style="cyan")
    t.add_column("CPUs", justify="right")
    t.add_column("Produções", justify="right")
    t.add_column("Insumos", justify="right")
    for d in dirs:
        try:
            catalogo = rt.load_catalogo(d.name)
            n_cpu = len(catalogo.get("cpus", []))
            n_prod = len(catalogo.get("producoes", []))
            n_ins = len(catalogo.get("insumos", []))
        except Exception:
            n_cpu = n_prod = n_ins = "?"
        t.add_row(d.name, str(n_cpu), str(n_prod), str(n_ins))
    rprint(t)


@app_catalog.command("browse")
def catalog_browse(
    contexto_id: str = typer.Option(..., "--contexto", "-c", help="ID do contexto"),
    tipo: str = typer.Option("cpu", "--tipo", "-t", help="Entidade: cpu | insumo"),
    categoria: str = typer.Option(None, "--categoria", help="Filtrar por categoria (ex: TERRAPLENAGEM)"),
    pagina: int = typer.Option(1, "--pagina", "-p", help="Página (25 itens por página)"),
) -> None:
    """Pagina entidades do catálogo: CPUs ou insumos."""
    import math

    from rich import print as rprint
    from rich.table import Table

    from concilium.presentation.mcp._context import _runtime

    PAGE_SIZE = 25
    rt = _runtime()
    ctx = rt.load_contexto(contexto_id)
    catalogo = rt.load_catalogo(ctx.catalogo_id)

    if tipo.lower() == "cpu":
        cpus = catalogo.get("cpus", [])
        if categoria:
            cpus = [c for c in cpus if c.get("categoria", "").upper() == categoria.upper()]
        cpus = sorted(cpus, key=lambda c: c.get("codigo", ""))
        total = len(cpus)
        total_pags = max(1, math.ceil(total / PAGE_SIZE))
        pagina = max(1, min(pagina, total_pags))
        page = cpus[(pagina - 1) * PAGE_SIZE : pagina * PAGE_SIZE]

        t = Table(show_header=True, header_style="bold", caption=f"Página {pagina}/{total_pags} — {total} CPUs")
        t.add_column("Código", style="cyan")
        t.add_column("Descrição")
        t.add_column("Un.")
        t.add_column("Categoria")
        for c in page:
            t.add_row(c.get("codigo", "?"), c.get("descricao", "?"), c.get("unidade", "?"), c.get("categoria", "?"))
        rprint(t)

    elif tipo.lower() == "insumo":
        insumos = sorted(catalogo.get("insumos", []), key=lambda i: i.get("codigo", ""))
        total = len(insumos)
        total_pags = max(1, math.ceil(total / PAGE_SIZE))
        pagina = max(1, min(pagina, total_pags))
        page = insumos[(pagina - 1) * PAGE_SIZE : pagina * PAGE_SIZE]

        t = Table(show_header=True, header_style="bold", caption=f"Página {pagina}/{total_pags} — {total} insumos")
        t.add_column("Código", style="cyan")
        t.add_column("Tipo")
        t.add_column("Descrição")
        t.add_column("Un.")
        t.add_column("Preço (R$)")
        for i in page:
            t.add_row(
                i.get("codigo", "?"),
                i.get("tipo", "?"),
                i.get("descricao", "?"),
                i.get("unidade", "?"),
                str(i.get("preco_unitario", "?")),
            )
        rprint(t)

    else:
        rprint(f"[red]Tipo desconhecido: '{tipo}'. Use cpu ou insumo.[/red]")
        raise typer.Exit(1)


@app_catalog.command("quality")
def catalog_quality(contexto_id: str = typer.Option(..., "--contexto", "-c", help="ID do contexto")):
    """Relatório de qualidade e cobertura do catálogo."""
    return _impl_catalog_quality(contexto_id)


@app_catalog.command("simulate")
def catalog_simulate(
    cpu_id: str = typer.Argument(..., help="Código da CPU"),
    contexto_id: str = typer.Option("mendeslobo", "--contexto", "-c", help="ID do contexto"),
    dias: int = typer.Option(30, "--dias", "-d", help="Período em dias corridos"),
    regime: str = typer.Option("6x1", "--regime", "-r", help="Regime (6x1, 5x2, 7x0)"),
    horas_dia: float = typer.Option(8.0, "--horas-dia", "-h", help="Carga horária diária"),
):
    """Simula horas e custo direto de uma CPU em um período."""
    return _impl_catalog_simulate(cpu_id, contexto_id, dias, regime, horas_dia)


@app_catalog.command("export")
def catalog_export(
    contexto_id: str = typer.Option("mendeslobo", "--contexto", "-c", help="ID do contexto"),
    output: str = typer.Option(None, "--output", "-o", help="Caminho do arquivo de saída (.xlsx)"),
):
    """Exporta o catálogo completo para planilha Excel."""
    return _impl_catalog_export(contexto_id, output)


@app_catalog.command("survey")
def catalog_survey(
    contexto_id: str = typer.Option("mendeslobo", "--contexto", "-c", help="ID do contexto"),
    jurisdicao_id: str = typer.Option(None, "--jurisdicao", "-j", help="ID da jurisdição para benchmark regional"),
    survey_type: str = typer.Option("price", "--type", "-t", help="Tipo de pesquisa: 'price' ou 'productivity'"),
    output: str = typer.Option(
        None, "--output", "-o", help="Caminho do arquivo de saída (.xlsx) ou camada project/master"
    ),
    target: str = typer.Option(None, "--target", help="Camada de persistência: project|master."),
    projeto: str = typer.Option(None, "--project", "-p", help="Projeto alvo quando target=project."),
    confirm_master: bool = typer.Option(
        False, "--confirm-master", help="Confirma gravação explícita na camada master."
    ),
    actor: str = typer.Option("cli", "--actor", help="Ator para trilha de auditoria quando target=project."),
):
    """Pesquisa e atualiza preços ou produtividades no catálogo."""
    return _impl_catalog_survey(
        contexto_id,
        jurisdicao_id,
        survey_type,
        output,
        target,
        projeto,
        confirm_master,
        actor,
    )


@app_catalog.command("promote")
def catalog_promote(
    projeto: str = typer.Option(..., "--project", "-p", help="Projeto de origem do override."),
    justificativa: str = typer.Option(..., "--justificativa", "-j", help="Justificativa da promoção para master."),
    contexto_id: str = typer.Option(None, "--contexto", "-c", help="Override do contexto (opcional)."),
    actor: str = typer.Option("cli", "--actor", help="Ator para trilha de auditoria e regra dos quatro-olhos."),
    force: bool = typer.Option(False, "--force", help="Confirma ação de promoção para camada master."),
) -> None:
    """Promove os overrides de insumo pendentes do projeto para a camada master (ADR-150)."""
    return _impl_catalog_promote(
        projeto,
        justificativa,
        contexto_id,
        actor,
        force,
    )


@app_catalog.command("search")
def catalog_search(
    contexto_id: str = typer.Option(..., "--contexto", "-c"), query: str = typer.Argument(..., help="Termo de busca")
):
    """Busca CPUs e insumos no catálogo por termo livre."""
    return _impl_catalog_search(contexto_id, query)


@app_catalog.command("validate")
def catalog_validate_schema(
    contexto_id: str = typer.Option(..., "--contexto", "-c", help="ID do contexto"),
    fail_on_warning: bool = typer.Option(False, "--strict", help="Falha também em avisos semânticos"),
):
    """Valida todos os arquivos do catálogo contra o schema JSON."""
    return _impl_catalog_validate_schema(contexto_id, fail_on_warning)


@app_catalog.command("cure")
def catalog_cure_schema(
    contexto_id: str = typer.Option(..., "--contexto", "-c", help="ID do contexto"),
    apply: bool = typer.Option(True, "--apply/--dry-run", help="Aplica correções (padrão: --apply)"),
):
    """Corrige automaticamente violações de schema no catálogo."""
    return _impl_catalog_cure_schema(contexto_id, apply)


@app_catalog.command("tendencia")
def catalog_tendencia(
    contexto_id: str = typer.Option(..., "--contexto", "-c", help="ID do contexto"),
    jurisdicao_id: str = typer.Option(None, "--jurisdicao", "-j", help="UF (ex: BR-CE) — usa preços SICRO regionais"),
    output: str = typer.Option("", "--output", "-o", help="Salva relatório JSON"),
):
    """Analisa tendência de variação de preços do catálogo."""
    return _impl_catalog_tendencia(contexto_id, jurisdicao_id, output)


@app_catalog.command("audit-reasonability")
def catalog_audit_reasonability(
    contexto_id: str = typer.Option("mendeslobo", "--contexto", "-c", help="ID do contexto"),
    output: str = typer.Option(
        "",
        "--output",
        "-o",
        help="Caminho do artefato JSON de saída (default: artifacts/audit/catalog_reasonability_<catalogo>.json)",
    ),
    max_findings: int = typer.Option(20, "--max-findings", help="Máximo de achados exibidos no terminal"),
):
    """Audita razoabilidade de preços e produtividades."""
    return _impl_catalog_audit_reasonability(contexto_id, output, max_findings)


def catalog_merge_rfi(
    contexto_id: str = typer.Argument(..., help="ID do contexto do catálogo."),
    apply: bool = typer.Option(False, "--apply", help="Aplica as mudanças no bundle (default: dry-run)."),
    verify_pu: bool = typer.Option(False, "--verify-pu", help="Verifica integridade referencial após merge."),
    report_json: str = typer.Option(None, "--report-json", help="Salva relatório detalhado em JSON."),
):
    return _impl_catalog_merge_rfi(contexto_id, apply, verify_pu, report_json)


def catalog_cure_plausibility(
    contexto_id: str = typer.Option(..., "--contexto", "-c", help="ID do contexto"),
    apply: bool = typer.Option(False, "--apply", help="Aplica correções (padrão: dry-run)"),
):
    return _impl_catalog_cure_plausibility(contexto_id, apply)


@app_structure.command("list")
def structure_list(projeto: str):
    return _impl_structure_list(projeto)


@app_structure.command("plan-init")
def plan_init(
    projeto: str,
    nome: str = typer.Option("Plano Principal", "--nome", "-n"),
    escopo: str = typer.Option("default", "--escopo", "-e"),
):
    return _impl_plan_init(projeto, nome, escopo)
