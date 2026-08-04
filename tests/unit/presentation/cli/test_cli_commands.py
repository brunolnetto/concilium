"""Real CLI integration tests using typer.testing.CliRunner.

These tests actually invoke CLI handlers end-to-end (no mocking of the
business logic) to provide genuine coverage of main.py command bodies.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from concilium.presentation.main import app

runner = CliRunner()


def _new_version(projects_root: Path, project_name: str) -> None:
    """Cria nova versão de projeto (substitui 'version new' CLI removida)."""
    from concilium.infrastructure.storage.store_factory import build_project_repository

    repo = build_project_repository(projects_root)
    for handle in repo.list_projects():
        if handle.meta.get("nome") == project_name:
            handle.new_version()
            return


# ── helpers ───────────────────────────────────────────────────────────────────


def _config_root() -> Path:
    return Path(__file__).resolve().parents[4] / "config"


# ── _startup_validation / callback ────────────────────────────────────────────


def test_cli_init_help(monkeypatch, tmp_path):
    """'init --help' exits 0 even without config dir set (help bypasses callback)."""
    result = runner.invoke(app, ["project", "init", "--help"])
    # Help always exits 0
    assert result.exit_code == 0


def test_cli_no_args_shows_help():
    result = runner.invoke(app, [])
    # no_args_is_help=True → typer shows help; CliRunner returns 0 or 2 depending on version
    assert result.exit_code in (0, 2)


# ── init command ─────────────────────────────────────────────────────────────


@pytest.fixture
def env_with_config(tmp_path, monkeypatch) -> dict[str, str]:
    """Set env vars so CLI uses real config + temp projects dir."""
    config = _config_root()
    projects = tmp_path / "projetos"
    projects.mkdir()
    monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(config))
    monkeypatch.setenv("CONCILIUM__PROJECTS_ROOT", str(projects))
    return {"config": str(config), "projects": str(projects)}


def test_cli_init_creates_project(env_with_config, tmp_path):
    result = runner.invoke(app, ["project", "init", "Meu Projeto Teste", "--contexto", "test"])
    assert result.exit_code == 0, result.output
    assert "Projeto criado" in result.output or "criado" in result.output.lower()
    # Verify project dir was created
    projects = Path(env_with_config["projects"])
    proj_dirs = [d for d in projects.iterdir() if d.is_dir() and (d / "meta.json").exists()]
    assert len(proj_dirs) == 1


@pytest.mark.slow
def test_cli_init_invalid_contexto(env_with_config):
    result = runner.invoke(app, ["project", "init", "Proj", "--contexto", "nonexistent_ctx"])
    assert result.exit_code != 0


def test_cli_init_missing_config(monkeypatch, tmp_path):
    """Startup callback exits 1 when config root doesn't exist."""
    monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(tmp_path / "no_config"))
    result = runner.invoke(app, ["project", "init", "X", "--contexto", "mendeslobo"])
    assert result.exit_code == 1


# ── snapshot command ──────────────────────────────────────────────────────────


# ── version command ───────────────────────────────────────────────────────────


def test_cli_version_new(env_with_config):
    runner.invoke(app, ["project", "init", "VerProj", "--contexto", "test"])
    # 'version new' foi removido — cria versão programaticamente
    _new_version(Path(env_with_config["projects"]), "VerProj")
    # Verifica que a versão foi criada
    from concilium.infrastructure.storage.store_factory import build_project_repository

    projects = Path(env_with_config["projects"])
    for handle in build_project_repository(projects).list_projects():
        if handle.meta.get("nome") == "VerProj":
            assert handle.current_version() is not None
            return
    pytest.fail("Versão não foi criada para VerProj")


# ── status command ────────────────────────────────────────────────────────────


def test_cli_status_new_project(env_with_config):
    runner.invoke(app, ["project", "init", "StatusProj", "--contexto", "test"])
    result = runner.invoke(app, ["project", "status", "StatusProj"])
    assert result.exit_code == 0
    assert "StatusProj" in result.output


def test_cli_status_project_not_found(env_with_config):
    result = runner.invoke(app, ["project", "status", "does_not_exist_abc"])
    assert result.exit_code != 0


# ── validate command ──────────────────────────────────────────────────────────


def test_cli_validate_no_canonical(env_with_config):
    """validate on a project with no canonical yet → exits 1."""
    runner.invoke(app, ["project", "init", "ValProj", "--contexto", "test"])
    _new_version(Path(env_with_config["projects"]), "ValProj")
    result = runner.invoke(app, ["project", "validate", "ValProj"])
    # No canonical saved yet → exits 1
    assert result.exit_code == 1


def test_cli_validate_with_canonical(env_with_config, tmp_path):
    """validate on a project with actual canonical data."""
    from concilium.application.runtime import Runtime
    from concilium.infrastructure.storage.store_factory import build_project_repository

    config_root = Path(env_with_config["config"])
    projects_root = Path(env_with_config["projects"])

    # Create project and run skill-00 to produce a canonical
    project = build_project_repository(projects_root).create_project("ValProj2", "test")
    project.new_version()

    rt = Runtime(config_root)
    rt.run_skill(
        "01-escopo-e-eap",
        project,
        inputs={
            "nome": "ValProj2",
            "tipo_obra": "terraplenagem",
            "localizacao": "Aracoiaba, CE",
            "coordenadas": {"lat": -4.36, "lng": -38.74},
            "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
            "data_inicio": "2026-06-01",
            "data_termino": "2026-12-31",
            "eap": [
                {
                    "item_id": "eap-01",
                    "ordem": 1,
                    "cpu_id": "ESCO-CARGA-1CAT-DMT2000",
                    "descricao": "Escavação",
                    "unidade": "m3",
                    "quantitativo": 1000,
                }
            ],
        },
    )
    result = runner.invoke(app, ["project", "validate", "ValProj2"])
    assert result.exit_code == 0
    # O validate mostra UUID ou nome do projeto no output
    assert "ValProj2" in result.output or "Validação" in result.output or len(result.output) > 0


# ── run command ───────────────────────────────────────────────────────────────


def test_cli_run_skill_no_version(env_with_config):
    """run without any version active → exits 1."""
    runner.invoke(app, ["project", "init", "RunProj", "--contexto", "test"])
    result = runner.invoke(app, ["project", "run", "01-escopo-e-eap", "--project", "RunProj"])
    # No version yet → exits 1 (RuntimeDomainError)
    assert result.exit_code != 0


@pytest.mark.slow
def test_cli_run_skill_with_inputs_json(env_with_config):
    """run with --inputs JSON string."""
    from concilium.presentation.cli.shared import resolve_project

    runner.invoke(app, ["project", "init", "RunProj2", "--contexto", "test"])
    # Resolve o projeto criado via a abstração (não via scan de filesystem) e
    # monta escopo + plano — precisa ser o mesmo repositório/handle que
    # `resolve_project()` usará em "project run" abaixo (StorageProjectHandle
    # em backend filesystem via ADR-047, não ProjectStore/EscopoStore legado —
    # nomes de arquivo divergem entre as duas implementações).
    project = resolve_project("RunProj2")
    project.create_escopo(
        "default",
        "Escopo padrão",
        tipo_obra="terraplenagem",
        localizacao="Aracoiaba, CE",
        coordenadas_lat=-4.36,
        coordenadas_lng=-38.74,
        data_inicio="2026-06-01",
        data_termino="2026-12-31",
    )
    es = project.escopo("default")
    es.create_plan("Plano 1")
    inputs = {
        "nome": "RunProj2",
        "tipo_obra": "terraplenagem",
        "localizacao": "Aracoiaba, CE",
        "coordenadas": {"lat": -4.36, "lng": -38.74},
        "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
        "data_inicio": "2026-06-01",
        "data_termino": "2026-12-31",
        "eap": [
            {
                "item_id": "eap-01",
                "ordem": 1,
                "cpu_id": "ESCO-CARGA-1CAT-DMT2000",
                "descricao": "Escavação",
                "unidade": "m3",
                "quantitativo": 1000,
            }
        ],
    }
    result = runner.invoke(
        app, ["project", "run", "01-escopo-e-eap", "--project", "RunProj2", "--inputs", json.dumps(inputs)]
    )
    assert result.exit_code == 0
    assert "sucesso" in result.output.lower() or "OK" in result.output


@pytest.mark.slow
def test_cli_run_skill_with_inputs_file(env_with_config, tmp_path):
    """run with --inputs pointing to a .json file."""
    from concilium.presentation.cli.shared import resolve_project

    runner.invoke(app, ["project", "init", "RunProj3", "--contexto", "test"])
    # Resolve o projeto criado via a abstração (não via scan de filesystem) e
    # monta escopo + plano — precisa ser o mesmo repositório/handle que
    # `resolve_project()` usará em "project run" abaixo (StorageProjectHandle
    # em backend filesystem via ADR-047, não ProjectStore/EscopoStore legado —
    # nomes de arquivo divergem entre as duas implementações).
    project = resolve_project("RunProj3")
    project.create_escopo(
        "default",
        "Escopo padrão",
        tipo_obra="terraplenagem",
        localizacao="Aracoiaba, CE",
        coordenadas_lat=-4.36,
        coordenadas_lng=-38.74,
        data_inicio="2026-06-01",
        data_termino="2026-12-31",
    )
    es = project.escopo("default")
    es.create_plan("Plano 1")
    inputs = {
        "nome": "RunProj3",
        "tipo_obra": "terraplenagem",
        "localizacao": "Aracoiaba, CE",
        "coordenadas": {"lat": -4.36, "lng": -38.74},
        "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
        "data_inicio": "2026-06-01",
        "data_termino": "2026-12-31",
        "eap": [
            {
                "item_id": "eap-01",
                "ordem": 1,
                "cpu_id": "ESCO-CARGA-1CAT-DMT2000",
                "descricao": "Escavação",
                "unidade": "m3",
                "quantitativo": 1000,
            }
        ],
    }
    inputs_file = tmp_path / "inputs.json"
    inputs_file.write_text(json.dumps(inputs), encoding="utf-8")
    result = runner.invoke(
        app, ["project", "run", "01-escopo-e-eap", "--project", "RunProj3", "--inputs", str(inputs_file)]
    )
    assert result.exit_code == 0


def test_cli_run_skill_runtime_error(env_with_config):
    """run skill that fails due to missing deps → exits 1."""
    runner.invoke(app, ["project", "init", "RunProj4", "--contexto", "test"])
    _new_version(Path(env_with_config["projects"]), "RunProj4")
    # 04-cronograma requires previous skills to have run
    result = runner.invoke(app, ["project", "run", "04-cronograma", "--project", "RunProj4"])
    assert result.exit_code != 0


# ── approve command ───────────────────────────────────────────────────────────


def test_cli_approve(env_with_config, tmp_path):
    """approve on a project with canonical."""
    from concilium.application.runtime import Runtime
    from concilium.infrastructure.storage.store_factory import build_project_repository

    config_root = Path(env_with_config["config"])
    projects_root = Path(env_with_config["projects"])

    project = build_project_repository(projects_root).create_project("ApproveProj", "test")
    project.new_version()
    rt = Runtime(config_root)
    rt.run_skill(
        "01-escopo-e-eap",
        project,
        inputs={
            "nome": "ApproveProj",
            "tipo_obra": "terraplenagem",
            "localizacao": "Aracoiaba, CE",
            "coordenadas": {"lat": -4.36, "lng": -38.74},
            "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
            "data_inicio": "2026-06-01",
            "data_termino": "2026-12-31",
            "eap": [
                {
                    "item_id": "eap-01",
                    "ordem": 1,
                    "cpu_id": "ESCO-CARGA-1CAT-DMT2000",
                    "descricao": "Escavação",
                    "unidade": "m3",
                    "quantitativo": 1000,
                }
            ],
        },
    )
    result = runner.invoke(app, ["project", "approve", "ApproveProj", "--as", "eng_senior"])
    assert result.exit_code == 0
    assert "aprovada" in result.output.lower() or "approved" in result.output.lower()


def test_cli_approve_blocks_when_pending_catalog_overrides(env_with_config):
    """approve blocks by default when project has pending catalog overrides (ADR-040)."""
    from concilium.application.runtime import Runtime
    from concilium.infrastructure.storage.store_factory import build_project_repository

    config_root = Path(env_with_config["config"])
    projects_root = Path(env_with_config["projects"])

    project = build_project_repository(projects_root).create_project("ApprovePendingOverrides", "test")
    project.new_version()
    rt = Runtime(config_root)
    rt.run_skill(
        "01-escopo-e-eap",
        project,
        inputs={
            "nome": "ApprovePendingOverrides",
            "tipo_obra": "terraplenagem",
            "localizacao": "Aracoiaba, CE",
            "coordenadas": {"lat": -4.36, "lng": -38.74},
            "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
            "data_inicio": "2026-06-01",
            "data_termino": "2026-12-31",
            "eap": [
                {
                    "item_id": "eap-01",
                    "ordem": 1,
                    "cpu_id": "ESCO-CARGA-1CAT-DMT2000",
                    "descricao": "Escavação",
                    "unidade": "m3",
                    "quantitativo": 1000,
                }
            ],
        },
    )

    project.write_json("overrides/insumos_override.json", {"INS-TESTE": {"preco_calibrado": 12.34}})

    result = runner.invoke(app, ["project", "approve", "ApprovePendingOverrides", "--as", "eng_senior"])
    assert result.exit_code != 0
    assert "overrides pendentes" in result.output.lower()


def test_cli_approve_allows_pending_overrides_with_explicit_flag(env_with_config):
    """approve succeeds with pending overrides when --allow-pending-overrides is passed."""
    from concilium.application.runtime import Runtime
    from concilium.infrastructure.storage.store_factory import build_project_repository

    config_root = Path(env_with_config["config"])
    projects_root = Path(env_with_config["projects"])

    project = build_project_repository(projects_root).create_project("ApproveWithPendingOverrides", "test")
    project.new_version()
    rt = Runtime(config_root)
    rt.run_skill(
        "01-escopo-e-eap",
        project,
        inputs={
            "nome": "ApproveWithPendingOverrides",
            "tipo_obra": "terraplenagem",
            "localizacao": "Aracoiaba, CE",
            "coordenadas": {"lat": -4.36, "lng": -38.74},
            "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
            "data_inicio": "2026-06-01",
            "data_termino": "2026-12-31",
            "eap": [
                {
                    "item_id": "eap-01",
                    "ordem": 1,
                    "cpu_id": "ESCO-CARGA-1CAT-DMT2000",
                    "descricao": "Escavação",
                    "unidade": "m3",
                    "quantitativo": 1000,
                }
            ],
        },
    )

    project.write_json("overrides/insumos_override.json", {"INS-TESTE": {"preco_calibrado": 12.34}})

    result = runner.invoke(
        app,
        ["project", "approve", "ApproveWithPendingOverrides", "--as", "eng_senior", "--allow-pending-overrides"],
    )
    assert result.exit_code == 0


def test_cli_approve_no_version(env_with_config):
    """approve with no version active → exits 1."""
    runner.invoke(app, ["project", "init", "NoVerProj", "--contexto", "test"])
    result = runner.invoke(app, ["project", "approve", "NoVerProj", "--as", "eng"])
    assert result.exit_code != 0


def test_cli_approve_no_canonical(env_with_config):
    """approve with version but no canonical → exits 1."""
    runner.invoke(app, ["project", "init", "NoCanoProj", "--contexto", "test"])
    _new_version(Path(env_with_config["projects"]), "NoCanoProj")
    result = runner.invoke(app, ["project", "approve", "NoCanoProj", "--as", "eng"])
    assert result.exit_code != 0


def _approve_project_with_canonical(env_with_config, nome: str):
    """Cria projeto, roda 01-escopo-e-eap (canônico mínimo) e retorna (project, v) — issue #123."""
    from concilium.application.runtime import Runtime
    from concilium.infrastructure.storage.store_factory import build_project_repository

    config_root = Path(env_with_config["config"])
    projects_root = Path(env_with_config["projects"])

    project = build_project_repository(projects_root).create_project(nome, "test")
    project.new_version()
    rt = Runtime(config_root)
    rt.run_skill(
        "01-escopo-e-eap",
        project,
        inputs={
            "nome": nome,
            "tipo_obra": "terraplenagem",
            "localizacao": "Aracoiaba, CE",
            "coordenadas": {"lat": -4.36, "lng": -38.74},
            "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
            "data_inicio": "2026-06-01",
            "data_termino": "2026-12-31",
            "eap": [
                {
                    "item_id": "eap-01",
                    "ordem": 1,
                    "cpu_id": "ESCO-CARGA-1CAT-DMT2000",
                    "descricao": "Escavação",
                    "unidade": "m3",
                    "quantitativo": 1000,
                }
            ],
        },
    )
    return project, project.current_version()


def test_cli_approve_flat_model_blocks_on_blocking_aviso(env_with_config):
    """issue #123: gate de aprovação (VAL-PROD-04 etc.) agora também bloqueia o modelo vN flat."""
    project, v = _approve_project_with_canonical(env_with_config, "FlatGateBlock")
    project.log_invocation(
        v,
        {"skill": "04-cronograma", "validacoes": [{"codigo": "VAL-PROD-04", "status": "AVISO"}]},
    )

    result = runner.invoke(app, ["project", "approve", "FlatGateBlock", "--as", "eng_senior"])
    assert result.exit_code != 0
    assert "VAL-PROD-04" in result.output


def test_cli_approve_flat_model_erro_blocks_even_with_justificativa(env_with_config):
    """ERRO pendente nunca tem escape, nem com --justificativa-override (issue #123)."""
    project, v = _approve_project_with_canonical(env_with_config, "FlatGateErro")
    project.log_invocation(
        v,
        {"skill": "04-cronograma", "validacoes": [{"codigo": "ERR-XPTO", "status": "ERRO"}]},
    )

    result = runner.invoke(
        app,
        ["project", "approve", "FlatGateErro", "--as", "eng_senior", "--justificativa-override", "aceito o risco"],
    )
    assert result.exit_code != 0
    assert "ERRO" in result.output


def test_cli_approve_flat_model_justificativa_override_allows(env_with_config):
    """--justificativa-override permite aprovar com AVISO bloqueante e fica registrada no log (issue #123)."""
    project, v = _approve_project_with_canonical(env_with_config, "FlatGateOverride")
    project.log_invocation(
        v,
        {"skill": "04-cronograma", "validacoes": [{"codigo": "VAL-PROD-04", "status": "AVISO"}]},
    )

    result = runner.invoke(
        app,
        [
            "project",
            "approve",
            "FlatGateOverride",
            "--as",
            "eng_senior",
            "--justificativa-override",
            "produtividade calibrada manualmente, risco aceito",
        ],
    )
    assert result.exit_code == 0

    invocacoes = [json.loads(line) for line in project.read_lines(f"{v}/{project.INVOCATIONS_LOG}")]
    assert any(entry.get("justificativa_override") for entry in invocacoes)


# ── adapter run command ───────────────────────────────────────────────────────


def test_cli_adapter_run_no_version(env_with_config):
    """adapter run with no version → exits 1."""
    runner.invoke(app, ["project", "init", "AdapterProj", "--contexto", "test"])
    result = runner.invoke(app, ["adapter", "run", "AdapterProj"])
    assert result.exit_code != 0


def test_cli_adapter_run_missing_deps(env_with_config):
    """adapter run when skill deps not met → exits 1."""
    runner.invoke(app, ["project", "init", "AdapterProj2", "--contexto", "test"])
    _new_version(Path(env_with_config["projects"]), "AdapterProj2")
    result = runner.invoke(app, ["adapter", "run", "AdapterProj2"])
    assert result.exit_code != 0


# ── scenario commands ─────────────────────────────────────────────────────────


def test_cli_scenario_compare_no_file(env_with_config):
    """scenario compare before running scenarios → exits 1."""
    runner.invoke(app, ["project", "init", "ScenProj", "--contexto", "test"])
    result = runner.invoke(app, ["scenario", "compare", "--project", "ScenProj"])
    assert result.exit_code != 0


def test_cli_scenario_compare_project_not_found(env_with_config):
    result = runner.invoke(app, ["scenario", "compare", "--project", "ghost_project"])
    assert result.exit_code != 0


# ── schedule weekly command ───────────────────────────────────────────────────


def test_cli_schedule_weekly_no_version(env_with_config):
    """schedule weekly with no version → exits 1."""
    runner.invoke(app, ["project", "init", "SchedProj", "--contexto", "test"])
    result = runner.invoke(app, ["schedule", "weekly", "--project", "SchedProj"])
    assert result.exit_code != 0


def test_cli_schedule_weekly_missing_deps(env_with_config):
    """schedule weekly when skill deps not met → exits 1."""
    runner.invoke(app, ["project", "init", "SchedProj2", "--contexto", "test"])
    _new_version(Path(env_with_config["projects"]), "SchedProj2")
    result = runner.invoke(app, ["schedule", "weekly", "--project", "SchedProj2"])
    assert result.exit_code != 0


# ── resolve project edge cases ─────────────────────────────────────────────────


def test_cli_resolve_project_by_uuid(env_with_config):
    """Can reference project by its UUID directory name."""
    from concilium.infrastructure.storage.store_factory import build_project_repository

    projects_root = Path(env_with_config["projects"])
    p = build_project_repository(projects_root).create_project("ByUUID", "test")
    uuid_name = p.root.name  # the actual directory name (UUID)
    result = runner.invoke(app, ["project", "status", uuid_name])
    assert result.exit_code == 0


def test_cli_resolve_project_multiple_same_name(env_with_config):
    """Two projects with same name → CLI reports ambiguity and exits 1."""
    from concilium.infrastructure.storage.store_factory import build_project_repository

    projects_root = Path(env_with_config["projects"])
    build_project_repository(projects_root).create_project("DupName", "test")
    build_project_repository(projects_root).create_project("DupName", "test")
    result = runner.invoke(app, ["project", "status", "DupName"])
    assert result.exit_code == 1


def test_cli_schedule_help():
    """schedule existe como comando oculto root."""
    result = runner.invoke(app, ["schedule", "--help"])
    assert result.exit_code == 0
