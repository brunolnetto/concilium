"""Commands: run, approve."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich import print as rprint

from concilium.presentation.cli.shared import config_root, parse_project_version, resolve_project

if TYPE_CHECKING:
    from typing import Any

    from concilium.application.services.project.project_repository import EscopoHandle, ProjectHandle
    from concilium.application.skills.base import SkillResult

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


def _run_resolve_plano(es: "EscopoHandle", plano_id: str | None, resolved_escopo: str) -> str:
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
    # project.root é lógico (não-backed) em backends não-filesystem
    # (StorageProjectHandle) — sempre ler via read_json(), nunca um Path cru.
    loaded = project.read_json("overrides/insumos_override.json", {})
    if isinstance(loaded, dict):
        return [k for k in loaded.keys() if isinstance(k, str)]
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


def _approve_parse_and_resolve(arg: str) -> tuple["ProjectHandle", str]:
    """Parse project@version e resolve project + version ativa. Retorna (project, v)."""
    nome, ver = parse_project_version(arg)
    project = resolve_project(nome)
    v = ver or project.current_version()
    if v is None:
        rprint("[red]Nenhuma versão ativa.[/red]")
        raise typer.Exit(1)
    return project, v


def _approve_validate_prerequisites(
    project: "ProjectHandle",
    v: str,
    allow_pending_overrides: bool,
    justificativa_override: str | None,
) -> "Any":
    """Valida overrides pendentes e gate de aprovação. Retorna canonical."""
    from concilium.application.orchestrators.plano_approval_gate import (
        PlanoApprovalGateError,
        assert_pode_aprovar_plano,
    )
    from concilium.infrastructure.storage.flat_version_store import FlatVersionStore

    canonical = project.load_canonical(v)
    if canonical is None:
        rprint(f"[red]Sem canônico na versão {v}[/red]")
        raise typer.Exit(1)
    pending_override_ids = _approve_load_pending_overrides(project)
    if pending_override_ids and not allow_pending_overrides:
        preview = ", ".join(sorted(pending_override_ids)[:5])
        suffix = "" if len(pending_override_ids) <= 5 else f" ... (+{len(pending_override_ids) - 5})"
        rprint(
            "[yellow]Aprovação bloqueada: existem overrides pendentes de curadoria.[/yellow]\n"
            f"  Itens: {preview}{suffix}\n"
            "  Opções: promova/arquive os overrides ou reexecute com --allow-pending-overrides."
        )
        raise typer.Exit(1)
    try:
        assert_pode_aprovar_plano(FlatVersionStore(project, v), justificativa_override)
    except PlanoApprovalGateError as exc:
        rprint(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(1) from None
    return canonical


def _approve_execute_and_log(
    project: "ProjectHandle",
    v: str,
    canonical: "Any",
    papel: str,
    motivo: str,
    justificativa_override: str | None,
) -> None:
    """Executa aprovação, atualiza canonical, loga e exibe resultado."""
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
    rprint(f"[green][OK][/green] Versão [bold]{v}[/bold] aprovada por [bold]{papel}[/bold].")
    if motivo:
        rprint(f"  Motivo: {motivo}")
    if justificativa_override:
        rprint(f"  Justificativa de override: {justificativa_override}")
    rprint("  Arquivos agora read-only (chmod 444).")


@app.command()
@app.command("certificate")
def formalism_certificate(
    run_id: str = typer.Argument(..., help="ID do run retornado por run project."),
    projeto: str = typer.Option(..., "--project", "-p", help="Nome ou UUID do projeto."),
) -> None:
    """Consulta o certificado GO/NOGO persistido e revalida os fingerprints atuais."""
    from concilium.application.scheduling.formalism_certification_service import (
        FORMALISM_SHA256,
        ORACLE_SHA256,
        build_productivity_rate_witnesses,
        build_solver_context,
        certificate_summary,
        load_resolved_catalog_snapshot,
        read_current_project_certificate,
    )
    from concilium.application.services.project.project_files import DEFAULT_PROJECT_FILES

    project = resolve_project(projeto)
    runs = project.read_json(DEFAULT_PROJECT_FILES.runs, [])
    if not isinstance(runs, list):
        rprint("[yellow]Registro de runs indisponível.[/yellow]")
        raise typer.Exit(1)
    run_record = next(
        (
            row for row in runs
            if isinstance(row, dict) and row.get("run_id") == run_id
        ),
        None,
    )
    if run_record is None:
        rprint(f"[red]Run '{run_id}' não encontrado.[/red]")
        raise typer.Exit(1)

    version = run_record.get("version")
    certificate = run_record.get("formalism_certificate")
    evaluation_sha256 = (
        certificate.get("evaluation_sha256")
        if isinstance(certificate, dict) else None
    )
    if not isinstance(version, str) or not isinstance(evaluation_sha256, str):
        summary = {
            "status": "NOT_EVALUATED",
            "recorded_decision": None,
            "effective_decision": "NOT_CERTIFIABLE",
            "project_go": False,
            "scope": None,
            "reasons": ["este run ainda não possui avaliação formal persistida"],
            "gates": [],
            "invalidated_sources": [],
        }
    else:
        canonical = project.load_canonical(version)
        if canonical is None:
            rprint(f"[red]Canônico da versão '{version}' não encontrado.[/red]")
            raise typer.Exit(1)
        resolved_catalog = load_resolved_catalog_snapshot(project, version, run_id)
        productivity_witnesses = build_productivity_rate_witnesses(
            canonical, resolved_catalog,
        )
        solver_context = build_solver_context(run_record, version, canonical)
        current = read_current_project_certificate(
            project,
            run_id=run_id,
            evaluation_sha256=evaluation_sha256,
            canonical=canonical,
            resolved_catalog=resolved_catalog,
            productivity_witnesses=productivity_witnesses,
            solver_context=solver_context,
            current_formalism_sha256=FORMALISM_SHA256,
            current_oracle_sha256=ORACLE_SHA256,
        )
        summary = certificate_summary(current)

    rprint("[bold]Certificado formal — P23[/bold]")
    rprint(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


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
    """Aprova versão: atualiza status no canônico e torna arquivos read-only (chmod 444).

    Um gate bloqueia a aprovação (`assert_pode_aprovar_plano`, issue #123) quando a última
    execução de alguma skill nesta versão sinaliza inconsistência venda×operacional ou
    ERRO pendente (sem escape). Para aprovar com AVISO bloqueante, preencha --justificativa-override.
    """
    project, v = _approve_parse_and_resolve(arg)
    canonical = _approve_validate_prerequisites(
        project, v, allow_pending_overrides, justificativa_override
    )
    _approve_execute_and_log(project, v, canonical, papel, motivo, justificativa_override)
