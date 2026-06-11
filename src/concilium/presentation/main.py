"""CLI entry point para Concilium. Agrega comandos de submodules."""

import sys

import typer
from rich import print as rprint

app = typer.Typer(
    name="concilium",
    help="Framework determinístico de planejamento de obras.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _startup_validation(ctx: typer.Context) -> None:
    """Valida pré-condições básicas de ambiente ao iniciar a CLI."""
    if ctx.resilient_parsing or any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        return
    if ctx.invoked_subcommand == "health":
        return
    from concilium.presentation.cli.shared import config_root

    try:
        config_root()
    except RuntimeError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1) from None


# Pre-registra os grupos no topo: nomes e help já aparecem no --help raiz
# sem importar nenhum módulo de comandos.
catalog_app = typer.Typer(
    name="catalog",
    help="Catálogo corporativo de insumos e serviços (Master).",
    no_args_is_help=True,
)
project_app = typer.Typer(
    name="project",
    help="Ciclo de vida e dados do projeto.",
    no_args_is_help=True,
)
configuration_app = typer.Typer(
    name="configuration",
    help="Configuração: skills, contextos, perfis, temas e jurisdições.",
    no_args_is_help=True,
)
benchmark_app = typer.Typer(
    name="benchmark",
    help="Execução, análise e auditoria de benchmarks.",
    no_args_is_help=True,
)
auth_app = typer.Typer(
    name="auth",
    help="Gestão de usuários, dispositivos e tokens JWT.",
    no_args_is_help=True,
)
skills_app = typer.Typer(
    name="skills",
    help="Gerenciamento e exportação dos manifests de skills.",
    no_args_is_help=True,
)

# Context and perfil versioning + temas/jurisdicoes
from concilium.presentation.cli.commands_config_version import app_context, app_perfil  # noqa: E402
from concilium.presentation.cli.commands_configuration import app_jurisdicao, app_temas  # noqa: E402

configuration_app.add_typer(skills_app)
configuration_app.add_typer(app_context, name="contexto")
configuration_app.add_typer(app_perfil)
configuration_app.add_typer(app_temas)
configuration_app.add_typer(app_jurisdicao)

app.add_typer(catalog_app)
app.add_typer(project_app)
app.add_typer(configuration_app)
app.add_typer(benchmark_app)
app.add_typer(auth_app)


# ── Loaders por grupo ────────────────────────────────────────────────────────


def _populate_catalog_into(target: typer.Typer, cmd) -> None:
    target.command("list")(cmd.catalog_list)
    target.command("browse")(cmd.catalog_browse)
    target.command("quality")(cmd.catalog_quality)
    target.command("simulate")(cmd.catalog_simulate)
    target.command("export")(cmd.catalog_export)
    target.command("survey")(cmd.catalog_survey)
    target.command("promote")(cmd.catalog_promote)
    target.command("search")(cmd.catalog_search)
    if hasattr(cmd, "catalog_audit_reasonability"):
        target.command("audit")(cmd.catalog_audit_reasonability)
    if hasattr(cmd, "catalog_validate_schema"):
        target.command("validate")(cmd.catalog_validate_schema)
    if hasattr(cmd, "catalog_cure_schema"):
        target.command("cure")(cmd.catalog_cure_schema)


def _load_catalog() -> None:
    from concilium.presentation.cli import commands_manage

    _populate_catalog_into(catalog_app, commands_manage)


def _load_project() -> None:
    from concilium.presentation.cli import (
        commands_adapter,
        commands_basic,
        commands_bdi,
        commands_manage,
        commands_run,
        commands_validate,
    )

    project_app.command("list")(commands_basic.list_projects)
    project_app.command("init")(commands_basic.init)
    project_app.command("status")(commands_basic.status)
    project_app.command("run")(commands_run.run)
    project_app.command("audit")(commands_basic.audit)
    project_app.command("approve")(commands_run.approve)

    project_catalog = typer.Typer(
        name="catalog",
        help="Catálogo de overrides do projeto.",
        no_args_is_help=True,
    )
    _populate_catalog_into(project_catalog, commands_manage)
    project_app.add_typer(project_catalog)

    commands_manage.app_structure.add_typer(commands_bdi.app, name="bdi")
    project_app.add_typer(commands_manage.app_structure)

    project_export = typer.Typer(
        name="export",
        help="Exporta artefatos do projeto (relatório, Excel).",
        no_args_is_help=True,
    )
    project_export.add_typer(commands_adapter.app, name="excel")
    project_app.add_typer(project_export)

    project_app.command("validate")(commands_validate.validate_project)


def _load_benchmark() -> None:
    from concilium.presentation.cli import commands_benchmark, commands_schedule

    benchmark_app.command("list")(commands_benchmark.list_benchmarks)
    benchmark_app.command("run-batch")(commands_benchmark.run_benchmarks_batch)
    benchmark_app.command("run")(commands_benchmark.run_benchmarks)
    benchmark_app.command("analyze")(commands_benchmark.analyze)
    benchmark_app.command("trace")(commands_benchmark.extract_trace)
    benchmark_app.command("audit")(commands_benchmark.audit)
    benchmark_app.command("cleanup")(commands_benchmark.cleanup)
    benchmark_app.command("summary")(commands_benchmark.stage_summary)
    benchmark_app.command("iterate")(commands_benchmark.iterate_correction)
    benchmark_app.command("plan-space")(commands_benchmark.plan_space)
    benchmark_app.command("pack")(commands_benchmark.pack_benchmark)
    benchmark_app.command("compare")(commands_benchmark.compare_algorithms)
    benchmark_app.add_typer(commands_schedule.app, name="schedule")


def _load_validate() -> None:
    from concilium.presentation.cli import commands_validate

    validate_app = typer.Typer(
        name="validate",
        help="Validação unificada de projeto/benchmark.",
        no_args_is_help=True,
    )
    validate_app.command("project")(commands_validate.validate_project)
    validate_app.command("benchmark")(commands_validate.validate_benchmark)
    app.add_typer(validate_app, hidden=True)


def _load_schedule() -> None:
    from concilium.presentation.cli import commands_schedule

    app.add_typer(commands_schedule.app, hidden=True)


def _load_auth() -> None:
    from concilium.presentation.cli.commands_auth import (
        add_user,
        list_devices,
        list_users,
        new_device,
        remove_user,
        revoke_device,
    )

    auth_app.command("add-user")(add_user)
    auth_app.command("list-users")(list_users)
    auth_app.command("remove-user")(remove_user)
    auth_app.command("new-device")(new_device)
    auth_app.command("list-devices")(list_devices)
    auth_app.command("revoke-device")(revoke_device)


def _load_health() -> None:
    from concilium.presentation.cli import commands_health

    app.command("health", hidden=True)(commands_health.health)


_all_loaded = False


def _load_all() -> None:
    """Carrega todos os grupos. Idempotente — seguro chamar múltiplas vezes."""
    global _all_loaded
    if _all_loaded:
        return
    _all_loaded = True
    from concilium.presentation.cli import (
        commands_health,
        commands_schedule,
        commands_validate,
    )

    _load_catalog()
    _load_project()
    _load_benchmark()
    _load_configuration()
    _load_auth()

    validate_app = typer.Typer(
        name="validate",
        help="Validação unificada de projeto/benchmark.",
        no_args_is_help=True,
    )
    validate_app.command("project")(commands_validate.validate_project)
    validate_app.command("benchmark")(commands_validate.validate_benchmark)
    app.add_typer(validate_app, hidden=True)
    app.add_typer(commands_schedule.app, hidden=True)
    app.command("health", hidden=True)(commands_health.health)


# ── Dispatcher ───────────────────────────────────────────────────────────────

_configuration_loaded = False


def _load_configuration() -> None:
    global _configuration_loaded
    if _configuration_loaded:
        return
    _configuration_loaded = True
    from concilium.presentation.cli.commands_skills import skills_export

    skills_app.command("export")(skills_export)


# Ensure key command trees are present when tests invoke `app` directly
# via CliRunner (without calling main()/dispatch).
_load_configuration()
_load_schedule()


_GROUP_LOADERS = {
    "catalog": _load_catalog,
    "project": _load_project,
    "benchmark": _load_benchmark,
    "validate": _load_validate,
    "schedule": _load_schedule,
    "health": _load_health,
    "configuration": _load_configuration,
    "auth": _load_auth,
}


def _is_in_test_context() -> bool:
    argv0 = sys.argv[0] if sys.argv else ""
    if any(k in argv0.lower() for k in ("pytest", "py.test", "_jb_pytest")):
        return True
    for a in sys.argv[1:3]:
        for k in ("--collect", "--tb", "-p", "conftest"):
            if k in a:
                return True
    return False


# Em contexto de teste o CliRunner invoca ``app`` diretamente (sem passar por
# main()/_dispatch), então todos os grupos precisam estar carregados já no import
# — caso contrário comandos como ``project init`` ficam indisponíveis e o resultado
# passa a depender da ordem de coleta dos testes (qualquer teste que dispare
# _load_all() "consertaria" os demais). Carregar tudo aqui torna a CLI determinística
# sob pytest sem afetar o caminho de produção (lazy dispatch permanece em main()).
if _is_in_test_context():
    _load_all()


def _get_non_flags() -> list:
    result = []
    for a in sys.argv[1:]:
        if not a.startswith("-"):
            result.append(a)
    return result


def _dispatch() -> None:
    """Importa apenas o(s) módulo(s) necessários para o comando invocado.

    Em contexto de teste (pytest / CliRunner não modifica sys.argv), carrega
    todos os grupos para garantir que a CLI esteja completa.
    """
    if _is_in_test_context():
        _load_all()
        return

    non_flags = _get_non_flags()
    group = non_flags[0] if non_flags else None

    loader = _GROUP_LOADERS.get(group)  # type: ignore[arg-type]
    if loader is not None:
        loader()
    elif group is not None:
        # Comando desconhecido: carrega tudo para que o Typer emita erro correto
        _load_all()
    # group is None → help raiz: grupos já registrados, nada a importar


def main() -> None:
    """Entry point para console script."""
    _dispatch()
    app()


if __name__ == "__main__":
    main()
