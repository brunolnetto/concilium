"""Commands: run, approve."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich import print as rprint

from concilium.presentation.cli.shared import config_root, parse_project_version, resolve_project

if TYPE_CHECKING:
    from concilium.application.services.project.project_repository import ProjectHandle
    from concilium.application.skills.base import SkillResult
    from concilium.infrastructure.storage.escopo_store import EscopoStore

# Runtime Ã© importado dentro de cada funÃ§Ã£o para evitar cascade Pydantic no startup.

app = typer.Typer(name="run", help="Execucao de skills.", no_args_is_help=True)


def _run_parse_inputs(inputs_json: str | None) -> dict:
    if not inputs_json:
        return {}
    try:
        is_file = Path(inputs_json).exists()
    except OSError:
        is_file = False
    if is_file:
        return json.loads(Path(inputs_json).read_text(encoding="utf-8"))
    return json.loads(inputs_json)


def _run_resolve_escopo(project: "ProjectHandle", escopo_id: str | None) -> str:
    escopos = project.list_escopos()
    if not escopos:
        rprint("[red]Nenhum escopo encontrado no projeto. Use 'escopo criar' primeiro.[/red]")
        raise typer.Exit(1)
    if escopo_id is not None:
        return escopo_id
    if len(escopos) == 1:
        return escopos[0]
    rprint("[red]Projeto tem múltiplos escopos. Use --escopo.[/red]")
    for eid in escopos:
        rprint(f"  \u2022 {eid}")
    raise typer.Exit(1)


def _run_resolve_plano(es: "EscopoStore", plano_id: str | None, resolved_escopo: str) -> str:
    if plano_id is not None:
        return plano_id
    active = es.active_plan()
    if active is None:
        rprint(f"[red]Nenhum plano ativo no escopo '{resolved_escopo}'. Use 'plano criar' primeiro.[/red]")
        raise typer.Exit(1)
    return active.plano_id


def _run_report_result(result: "SkillResult", skill: str) -> None:
    if result.has_errors:
        rprint(f"[red][X][/red] Skill {skill} falhou:")
    else:
        rprint(f"[green][OK][/green] Skill {skill} executada com sucesso.")
    for v in result.validacoes:
        cor = {"OK": "green", "AVISO": "yellow", "ERRO": "red"}[v.status]
        msg = f": {v.mensagem}" if v.mensagem else ""
        rprint(f"  [{cor}]{v.status:5s}[/{cor}] {v.codigo}{msg}")


def _approve_load_pending_overrides(project: "ProjectHandle") -> list[str]:
    overrides_path = project.root / "overrides" / "insumos_override.json"
    if not overrides_path.exists():
        return []
    try:
        loaded = json.loads(overrides_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            return [k for k in loaded.keys() if isinstance(k, str)]
    except Exception:
        pass
    return []


@app.command()
def run(
    skill: str = typer.Argument(..., help="ID da skill (ex.: 02-produtividade-climatica)."),
    projeto: str = typer.Option(..., "--project", "-p", help="Nome ou UUID do projeto."),
    version: str | None = typer.Option(None, "--version", "-v", help="Versao alvo (obsoleto; ignorado)."),
    inputs_json: str | None = typer.Option(
        None, "--inputs", "-i", help="JSON com inputs da skill, ou path para arquivo .json"
    ),
    escopo_id: str | None = typer.Option(None, "--escopo", "-e", help="ID do escopo. Auto-inferido se unico."),
    plano_id: str | None = typer.Option(None, "--plano", help="ID do plano. Auto-inferido se unico."),
) -> None:
    """Invoca uma skill. Persiste canônico se sucesso. Sempre registra log."""
    from concilium.application.runtime import Runtime, RuntimeError

    project = resolve_project(projeto)
    rt = Runtime(config_root())
    inputs = _run_parse_inputs(inputs_json)
    _ = version

    resolved_escopo = _run_resolve_escopo(project, escopo_id)
    es = project.escopo(resolved_escopo)
    resolved_plano = _run_resolve_plano(es, plano_id, resolved_escopo)
    ps = es.plan(resolved_plano)
    try:
        from concilium.application.orchestrators.lifecycle_coordinator import LifecycleCoordinator

        coordinator = LifecycleCoordinator(rt)
        result = coordinator.avancar_plano(skill, project, ps, inputs=inputs)
    except RuntimeError as e:
        rprint(f"[red]Erro de runtime: {e}[/red]")
        raise typer.Exit(1) from None
    except Exception as e:
        rprint(f"[red]Erro inesperado na skill: {e}[/red]")
        raise typer.Exit(2) from None

    _run_report_result(result, skill)
    if result.has_errors:
        raise typer.Exit(1)


@app.command()
def approve(
    arg: str = typer.Argument(..., help="projeto ou projeto@vN"),
    papel: str = typer.Option(..., "--as", help="Papel do aprovador (ex.: eng_senior, diretor)."),
    motivo: str = typer.Option("", "--motivo", "-m", help="Motivacao da aprovacao."),
    allow_pending_overrides: bool = typer.Option(
        False,
        "--allow-pending-overrides",
        help="Permite aprovar mesmo com overrides de catálogo pendentes de curadoria.",
    ),
    justificativa_override: str | None = typer.Option(
        None,
        "--justificativa-override",
        help=(
            "Justificativa para aprovar mesmo com AVISO bloqueante de inconsistência "
            "venda×operacional (VAL-COB-NEG/VAL-PROD-04/VAL-PROD-VS-PU/"
            "VAL-GAP-CATALOGO-OPERACIONAL/VAL-STALE-UPSTREAM). Registrada no invocations.log."
        ),
    ),
) -> None:
    """Aprova versÃ£o: atualiza status no canÃ´nico e torna arquivos read-only (chmod 444).

    Um gate bloqueia a aprovação (`assert_pode_aprovar_plano`, issue #123 — paridade com
    `aprovar_versao` do modelo escopo/plano) quando a última execução de alguma skill nesta
    versão sinaliza inconsistência não resolvida entre preço de venda e custo operacional, ou
    qualquer ERRO pendente (sem escape). Para aprovar mesmo com um AVISO bloqueante, preencha
    --justificativa-override.
    """
    from concilium.application.orchestrators.plano_approval_gate import (
        PlanoApprovalGateError,
        assert_pode_aprovar_plano,
    )
    from concilium.infrastructure.storage.flat_version_store import FlatVersionStore

    nome, ver = parse_project_version(arg)
    project = resolve_project(nome)
    v = ver or project.current_version()
    if v is None:
        rprint("[red]Nenhuma versÃ£o ativa.[/red]")
        raise typer.Exit(1)

    canonical = project.load_canonical(v)
    if canonical is None:
        rprint(f"[red]Sem canÃ´nico na versÃ£o {v}[/red]")
        raise typer.Exit(1)

    pending_override_ids = _approve_load_pending_overrides(project)
    if pending_override_ids and not allow_pending_overrides:
        preview = ", ".join(sorted(pending_override_ids)[:5])
        suffix = "" if len(pending_override_ids) <= 5 else f" ... (+{len(pending_override_ids) - 5})"
        rprint(
            "[yellow]AprovaÃ§Ã£o bloqueada: existem overrides pendentes de curadoria.[/yellow]\n"
            f"  Itens: {preview}{suffix}\n"
            "  OpÃ§Ãµes: promova/arquive os overrides ou reexecute com --allow-pending-overrides."
        )
        raise typer.Exit(1)

    try:
        assert_pode_aprovar_plano(FlatVersionStore(project, v), justificativa_override)
    except PlanoApprovalGateError as exc:
        rprint(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(1) from None

    try:
        novo_projeto = canonical.projeto.with_status("APROVADO")
    except ValueError as exc:
        rprint(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    canonical_aprovado = canonical.model_copy(update={"projeto": novo_projeto})
    project.save_canonical(canonical_aprovado, v)

    log_entry = {
        "ts": datetime.now(UTC).isoformat(),
        "acao": "APPROVE",
        "papel": papel,
        "motivo": motivo,
    }
    if justificativa_override and justificativa_override.strip():
        log_entry["justificativa_override"] = justificativa_override.strip()
    project.log_invocation(v, log_entry)

    project.approve(v)

    rprint(f"[green][OK][/green] VersÃ£o [bold]{v}[/bold] aprovada por [bold]{papel}[/bold].")
    if motivo:
        rprint(f"  Motivo: {motivo}")
    if justificativa_override:
        rprint(f"  Justificativa de override: {justificativa_override}")
    rprint("  Arquivos agora read-only (chmod 444).")
