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
app_structure = typer.Typer(name="structure", help="Gestão de Escopos e Planos (ADR-031).", no_args_is_help=True)


@app_catalog.command("quality")
def catalog_quality(contexto_id: str = typer.Option(..., "--contexto", "-c", help="ID do contexto")):
    return _impl_catalog_quality(contexto_id)


@app_catalog.command("simulate")
def catalog_simulate(
    cpu_id: str = typer.Argument(..., help="Código da CPU"),
    contexto_id: str = typer.Option("mendeslobo", "--contexto", "-c", help="ID do contexto"),
    dias: int = typer.Option(30, "--dias", "-d", help="Período em dias corridos"),
    regime: str = typer.Option("6x1", "--regime", "-r", help="Regime (6x1, 5x2, 7x0)"),
    horas_dia: float = typer.Option(8.0, "--horas-dia", "-h", help="Carga horária diária"),
):
    return _impl_catalog_simulate(cpu_id, contexto_id, dias, regime, horas_dia)


@app_catalog.command("export")
def catalog_export(
    contexto_id: str = typer.Option("mendeslobo", "--contexto", "-c", help="ID do contexto"),
    output: str = typer.Option(None, "--output", "-o", help="Caminho do arquivo de saída (.xlsx)"),
):
    return _impl_catalog_export(contexto_id, output)


@app_catalog.command("survey")
def catalog_survey(
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
    insumo_id: str = typer.Option(..., "--insumo", "-i", help="Código do insumo a promover."),
    justificativa: str = typer.Option(..., "--justificativa", "-j", help="Justificativa da promoção para master."),
    contexto_id: str = typer.Option(None, "--contexto", "-c", help="Override do contexto (opcional)."),
    data_vigencia: str = typer.Option(None, "--data-vigencia", help="Data efetiva da promoção (YYYY-MM-DD)."),
    actor: str = typer.Option("cli", "--actor", help="Ator para trilha de auditoria."),
    force: bool = typer.Option(False, "--force", help="Confirma ação de promoção para camada master."),
) -> None:
    return _impl_catalog_promote(
        projeto,
        insumo_id,
        justificativa,
        contexto_id,
        data_vigencia,
        actor,
        force,
    )


@app_catalog.command("search")
def catalog_search(
    contexto_id: str = typer.Option(..., "--contexto", "-c"), query: str = typer.Argument(..., help="Termo de busca")
):
    return _impl_catalog_search(contexto_id, query)


@app_catalog.command("validate-schema")
def catalog_validate_schema(
    contexto_id: str = typer.Option(..., "--contexto", "-c", help="ID do contexto"),
    fail_on_warning: bool = typer.Option(False, "--strict", help="Falha também em avisos semânticos"),
):
    return _impl_catalog_validate_schema(contexto_id, fail_on_warning)


@app_catalog.command("cure-schema")
def catalog_cure_schema(
    contexto_id: str = typer.Option(..., "--contexto", "-c", help="ID do contexto"),
    apply: bool = typer.Option(True, "--apply/--dry-run", help="Aplica correções (padrão: --apply)"),
):
    return _impl_catalog_cure_schema(contexto_id, apply)


@app_catalog.command("tendencia")
def catalog_tendencia(
    contexto_id: str = typer.Option(..., "--contexto", "-c", help="ID do contexto"),
    jurisdicao_id: str = typer.Option(None, "--jurisdicao", "-j", help="UF (ex: BR-CE) — usa preços SICRO regionais"),
    output: str = typer.Option("", "--output", "-o", help="Salva relatório JSON"),
):
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
