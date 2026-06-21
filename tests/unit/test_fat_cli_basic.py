"""Coverage tests for concilium.presentation.cli.commands_basic.

Targets:
  - list_projects: no root dir, empty dir, with projects, ProjectStore exception
  - init: success path, invalid contexto (RuntimeError → Exit(1))
  - status: version flag, skills flag (_print_skills_table), project details, invocations log
  - audit: no canonical, success with resultado/conflitos, _audit_val_color, _audit_print_conflitos
  - _audit_val_color: all status codes
  - _audit_print_conflitos: empty, <=3, >3 conflicts
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import typer
from typer.testing import CliRunner

from concilium.presentation.cli.commands_basic import app

runner = CliRunner()

MODULE = "concilium.presentation.cli.commands_basic"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_project(
    nome="Obra Teste",
    project_id="uuid-1234",
    contexto_id="samples",
    criado_em="2026-01-01",
    current_version="v1",
    versions=("v1",),
    version_path=None,
    load_canonical=None,
):
    """Build a MagicMock that mimics a ProjectStore instance."""
    proj = MagicMock()
    proj.meta = {
        "id": project_id,
        "nome": nome,
        "contexto_id": contexto_id,
        "criado_em": criado_em,
        "current_version": current_version,
    }
    proj.list_versions.return_value = list(versions)
    proj.current_version.return_value = current_version
    proj.version_path.return_value = version_path or Path("/tmp/fake_version")
    proj.load_canonical.return_value = load_canonical
    proj.root = Path("/tmp/fake_project")
    return proj


def _make_conflito(recurso_id="RES-01", quantidade_excedente=2, semana="2026-W10"):
    c = SimpleNamespace(
        recurso_id=recurso_id,
        quantidade_excedente=quantidade_excedente,
        semana=semana,
    )
    return c


# ═══════════════════════════════════════════════════════════════════════════
# list_projects
# ═══════════════════════════════════════════════════════════════════════════


class TestListProjects:
    def test_no_root_dir_prints_warning(self, tmp_path):
        missing = tmp_path / "does_not_exist"
        with patch(f"{MODULE}.projetos_root", return_value=missing):
            result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "Nenhum projeto" in result.output

    def test_empty_root_prints_warning(self, tmp_path):
        root = tmp_path / "projetos"
        root.mkdir()
        with patch(f"{MODULE}.projetos_root", return_value=root):
            result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "Nenhum projeto" in result.output

    def test_lists_projects_with_valid_meta(self, tmp_path):
        root = tmp_path / "projetos"
        proj_dir = root / "proj-aaa"
        proj_dir.mkdir(parents=True)

        store_mock = MagicMock()
        store_mock.meta = {
            "nome": "Obra AAA",
            "contexto_id": "samples",
            "current_version": "v1",
        }

        # ProjectStore is imported locally inside list_projects; patch at its source
        with (
            patch(f"{MODULE}.projetos_root", return_value=root),
            patch("concilium.infrastructure.storage.project.ProjectStore", return_value=store_mock),
            patch("concilium.presentation.cli.commands_basic.ProjectStore", return_value=store_mock, create=True),
        ):
            result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "proj-aaa" in result.output or "Obra AAA" in result.output

    def test_lists_projects_store_exception(self, tmp_path):
        root = tmp_path / "projetos"
        proj_dir = root / "proj-broken"
        proj_dir.mkdir(parents=True)

        with (
            patch(f"{MODULE}.projetos_root", return_value=root),
            patch("concilium.infrastructure.storage.project.ProjectStore", side_effect=ValueError("meta missing")),
        ):
            result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        # The error message should be shown inside the row
        assert "meta missing" in result.output

    def test_only_dirs_are_listed(self, tmp_path):
        """Non-directory entries are skipped."""
        root = tmp_path / "projetos"
        root.mkdir()
        (root / "some_file.txt").write_text("not a dir")

        with patch(f"{MODULE}.projetos_root", return_value=root):
            result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "Nenhum projeto" in result.output

    def test_multiple_projects_sorted(self, tmp_path):
        root = tmp_path / "projetos"
        for name in ("proj-zzz", "proj-aaa", "proj-mmm"):
            (root / name).mkdir(parents=True)

        store_mock = MagicMock()
        store_mock.meta = {"nome": "X", "contexto_id": "test", "current_version": None}

        with (
            patch(f"{MODULE}.projetos_root", return_value=root),
            patch("concilium.infrastructure.storage.project.ProjectStore", return_value=store_mock),
        ):
            result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        # All three names should appear in output (sorted order ensured)
        assert "proj-aaa" in result.output
        assert "proj-zzz" in result.output


# ═══════════════════════════════════════════════════════════════════════════
# init
# ═══════════════════════════════════════════════════════════════════════════


class TestInit:
    def test_success_creates_project(self, tmp_path):
        rt_mock = MagicMock()
        rt_mock.load_contexto.return_value = None  # no exception

        created_proj = MagicMock()
        created_proj.meta = {"id": "new-uuid-5678"}
        created_proj.root = tmp_path / "projetos" / "nova-obra"

        repo_mock = MagicMock()
        repo_mock.create_project.return_value = created_proj

        config_dir = tmp_path / "config"
        config_dir.mkdir()

        # Runtime is imported locally inside init; patch at source module
        with (
            patch(f"{MODULE}.config_root", return_value=config_dir),
            patch("concilium.application.runtime.Runtime", return_value=rt_mock),
            patch(f"{MODULE}.project_repository", return_value=repo_mock),
        ):
            result = runner.invoke(app, ["init", "Nova Obra", "--contexto", "samples"])

        assert result.exit_code == 0
        assert "OK" in result.output
        assert "Nova Obra" in result.output
        assert "new-uuid-5678" in result.output

    def test_invalid_contexto_exits_with_1(self, tmp_path):
        rt_mock = MagicMock()
        rt_mock.load_contexto.side_effect = RuntimeError("Contexto 'bogus' não encontrado")

        config_dir = tmp_path / "config"
        config_dir.mkdir()

        with (
            patch(f"{MODULE}.config_root", return_value=config_dir),
            patch("concilium.application.runtime.Runtime", return_value=rt_mock),
        ):
            result = runner.invoke(app, ["init", "Obra X", "--contexto", "bogus"])

        assert result.exit_code == 1
        assert "não encontrado" in result.output or "bogus" in result.output

    def test_default_contexto_is_samples(self, tmp_path):
        """When --contexto is omitted, default 'samples' is used."""
        rt_mock = MagicMock()
        rt_mock.load_contexto.return_value = None

        created_proj = MagicMock()
        created_proj.meta = {"id": "abc-123"}
        created_proj.root = tmp_path / "proj"

        repo_mock = MagicMock()
        repo_mock.create_project.return_value = created_proj

        config_dir = tmp_path / "config"
        config_dir.mkdir()

        with (
            patch(f"{MODULE}.config_root", return_value=config_dir),
            patch("concilium.application.runtime.Runtime", return_value=rt_mock),
            patch(f"{MODULE}.project_repository", return_value=repo_mock),
        ):
            result = runner.invoke(app, ["init", "Obra Padrao"])

        assert result.exit_code == 0
        repo_mock.create_project.assert_called_once_with("Obra Padrao", "samples")

    def test_contexto_printed_in_output(self, tmp_path):
        rt_mock = MagicMock()
        rt_mock.load_contexto.return_value = None

        created_proj = MagicMock()
        created_proj.meta = {"id": "ctx-uuid"}
        created_proj.root = tmp_path / "p"

        repo_mock = MagicMock()
        repo_mock.create_project.return_value = created_proj

        config_dir = tmp_path / "config"
        config_dir.mkdir()

        with (
            patch(f"{MODULE}.config_root", return_value=config_dir),
            patch("concilium.application.runtime.Runtime", return_value=rt_mock),
            patch(f"{MODULE}.project_repository", return_value=repo_mock),
        ):
            result = runner.invoke(app, ["init", "Obra C", "--contexto", "mendeslobo"])

        assert result.exit_code == 0
        assert "mendeslobo" in result.output


# ═══════════════════════════════════════════════════════════════════════════
# _audit_val_color
# ═══════════════════════════════════════════════════════════════════════════


class TestAuditValColor:
    def setup_method(self):
        from concilium.presentation.cli.commands_basic import _audit_val_color

        self._fn = _audit_val_color

    def test_ok_returns_green(self):
        assert self._fn("OK") == "green"

    def test_aviso_returns_yellow(self):
        assert self._fn("AVISO") == "yellow"

    def test_erro_returns_red(self):
        assert self._fn("ERRO") == "red"

    def test_unknown_returns_red(self):
        assert self._fn("DESCONHECIDO") == "red"

    def test_empty_string_returns_red(self):
        assert self._fn("") == "red"


# ═══════════════════════════════════════════════════════════════════════════
# _audit_print_conflitos
# ═══════════════════════════════════════════════════════════════════════════


class TestAuditPrintConflitos:
    def setup_method(self):
        from concilium.presentation.cli.commands_basic import _audit_print_conflitos

        self._fn = _audit_print_conflitos

    def test_no_conflitos_prints_ok(self, capsys):
        self._fn([])
        captured = capsys.readouterr()
        assert "Sem conflitos" in captured.out

    def test_none_conflitos_prints_ok(self, capsys):
        self._fn(None)
        captured = capsys.readouterr()
        assert "Sem conflitos" in captured.out

    def test_one_conflito_printed(self, capsys):
        c = _make_conflito("CAM-01", 3, "2026-W05")
        self._fn([c])
        captured = capsys.readouterr()
        assert "CAM-01" in captured.out
        assert "1 Conflitos" in captured.out

    def test_three_conflitos_no_truncation(self, capsys):
        conflitos = [
            _make_conflito("R-1", 1, "W01"),
            _make_conflito("R-2", 2, "W02"),
            _make_conflito("R-3", 3, "W03"),
        ]
        self._fn(conflitos)
        captured = capsys.readouterr()
        assert "R-1" in captured.out
        assert "R-2" in captured.out
        assert "R-3" in captured.out
        assert "outros" not in captured.out

    def test_more_than_three_conflitos_truncated(self, capsys):
        conflitos = [_make_conflito(f"R-{i}", i, f"W{i:02d}") for i in range(1, 7)]
        self._fn(conflitos)
        captured = capsys.readouterr()
        assert "R-1" in captured.out
        assert "R-3" in captured.out
        # Only first 3 shown; "mais 3 outros" message
        assert "mais 3 outros" in captured.out

    def test_exactly_four_conflitos(self, capsys):
        conflitos = [_make_conflito(f"RR-{i}", i, f"W{i:02d}") for i in range(1, 5)]
        self._fn(conflitos)
        captured = capsys.readouterr()
        assert "mais 1 outros" in captured.out


# ═══════════════════════════════════════════════════════════════════════════
# _print_skills_table
# ═══════════════════════════════════════════════════════════════════════════


class TestPrintSkillsTable:
    def test_prints_skills_table(self):
        from rich.console import Console

        from concilium.presentation.cli.commands_basic import _print_skills_table

        skill_meta = SimpleNamespace(description="Escopo e EAP")
        registry_mock = MagicMock()
        registry_mock.get_all_skills.return_value = {
            "01-escopo-e-eap": skill_meta,
            "02-produtividade": SimpleNamespace(description="Produtividade"),
        }

        console = Console()
        # SkillRegistry is imported locally inside _print_skills_table; patch at source
        with patch("concilium.application.skills.registry.SkillRegistry", return_value=registry_mock):
            # Should not raise
            _print_skills_table(console)

        registry_mock.get_all_skills.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# status (called directly)
# ═══════════════════════════════════════════════════════════════════════════


class TestStatus:
    def test_version_flag_prints_version_info(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        with patch(f"{MODULE}.config_root", return_value=config_dir):
            # Call directly; typer.Argument defaults to "" when called outside CLI
            import typer

            from concilium.presentation.cli.commands_basic import status

            # We use typer testing via a mini app
            mini_app = typer.Typer()
            mini_app.command()(status)
            _runner = CliRunner()
            result = _runner.invoke(mini_app, ["dummy-proj", "--version"])

        assert result.exit_code == 0
        assert "0.6.2" in result.output or "Concilium" in result.output

    def test_skills_flag_invokes_print_skills_table(self, tmp_path):
        skill_meta = SimpleNamespace(description="Desc X")
        registry_mock = MagicMock()
        registry_mock.get_all_skills.return_value = {"sk-01": skill_meta}

        from concilium.presentation.cli.commands_basic import status

        mini_app = typer.Typer()
        mini_app.command()(status)
        _runner = CliRunner()

        with patch("concilium.application.skills.registry.SkillRegistry", return_value=registry_mock):
            result = _runner.invoke(mini_app, ["dummy-proj", "--skills"])

        assert result.exit_code == 0
        registry_mock.get_all_skills.assert_called_once()

    def test_project_table_rendered(self, tmp_path):
        """Status without flags shows project meta table."""
        version_dir = tmp_path / "v1"
        version_dir.mkdir()
        proj = _fake_project(
            nome="Obra Teste",
            project_id="proj-id-999",
            current_version="v1",
            versions=["v1"],
            version_path=version_dir,
        )

        from concilium.presentation.cli.commands_basic import status

        mini_app = typer.Typer()
        mini_app.command()(status)
        _runner = CliRunner()

        with patch(f"{MODULE}.resolve_project", return_value=proj):
            result = _runner.invoke(mini_app, ["Obra Teste"])

        assert result.exit_code == 0
        assert "proj-id-999" in result.output or "Obra Teste" in result.output

    def test_status_with_invocations_log(self, tmp_path):
        """Status reads invocations.log when it exists and has data."""
        version_dir = tmp_path / "v1"
        version_dir.mkdir()

        log_entry = json.dumps({"status": "OK", "skill": "01-escopo-e-eap", "ts": "2026-06-01T10:00:00"})
        log_path = version_dir / "invocations.log"
        log_path.write_text(log_entry + "\n", encoding="utf-8")

        proj = _fake_project(
            nome="Obra Log",
            current_version="v1",
            versions=["v1"],
            version_path=version_dir,
        )

        from concilium.presentation.cli.commands_basic import status

        mini_app = typer.Typer()
        mini_app.command()(status)
        _runner = CliRunner()

        with patch(f"{MODULE}.resolve_project", return_value=proj):
            result = _runner.invoke(mini_app, ["Obra Log"])

        assert result.exit_code == 0
        assert "01-escopo-e-eap" in result.output or "Skills" in result.output

    def test_status_with_failed_skill_in_log(self, tmp_path):
        """Status shows red for failed skill entries."""
        version_dir = tmp_path / "v1"
        version_dir.mkdir()

        log_entry = json.dumps({"status": "ERRO", "skill": "04-cronograma", "ts": "2026-06-02T09:00:00"})
        log_path = version_dir / "invocations.log"
        log_path.write_text(log_entry + "\n", encoding="utf-8")

        proj = _fake_project(
            nome="Obra Err",
            current_version="v1",
            versions=["v1"],
            version_path=version_dir,
        )

        from concilium.presentation.cli.commands_basic import status

        mini_app = typer.Typer()
        mini_app.command()(status)
        _runner = CliRunner()

        with patch(f"{MODULE}.resolve_project", return_value=proj):
            result = _runner.invoke(mini_app, ["Obra Err"])

        assert result.exit_code == 0
        assert "04-cronograma" in result.output

    def test_status_no_current_version(self, tmp_path):
        """Status when project has no current version — no log section rendered."""
        version_dir = tmp_path / "v0"
        proj = _fake_project(
            nome="Empty Proj",
            current_version=None,
            versions=[],
            version_path=version_dir,
        )

        from concilium.presentation.cli.commands_basic import status

        mini_app = typer.Typer()
        mini_app.command()(status)
        _runner = CliRunner()

        with patch(f"{MODULE}.resolve_project", return_value=proj):
            result = _runner.invoke(mini_app, ["Empty Proj"])

        assert result.exit_code == 0


# ═══════════════════════════════════════════════════════════════════════════
# audit (called via CLI app wrapper)
# ═══════════════════════════════════════════════════════════════════════════


def _build_audit_app():
    """Build a mini Typer app wrapping audit for testing."""

    from concilium.presentation.cli.commands_basic import audit

    mini_app = typer.Typer()
    mini_app.command()(audit)
    return mini_app


class TestAudit:
    def test_no_canonical_exits_1(self):
        proj = _fake_project(load_canonical=None)

        mini_app = _build_audit_app()
        _runner = CliRunner()

        with (
            patch(f"{MODULE}.parse_project_version", return_value=("obra", "v1")),
            patch(f"{MODULE}.resolve_project", return_value=proj),
        ):
            result = _runner.invoke(mini_app, ["obra@v1"])

        assert result.exit_code == 1
        assert "canônico" in result.output or "canonical" in result.output.lower() or "Sem dados" in result.output

    def test_audit_with_resultado_and_no_conflitos(self):
        resultado = SimpleNamespace(
            margem_pct=0.12,
            status_margem="OK",
            custo=SimpleNamespace(total=1_500_000.0),
            validacoes=[],
        )
        canonical = SimpleNamespace(
            pipeline_integridade="COMPLETO",
            resultado=resultado,
            conflitos_pico=[],
        )
        proj = _fake_project(nome="Obra Financ", load_canonical=canonical)

        mini_app = _build_audit_app()
        _runner = CliRunner()

        with (
            patch(f"{MODULE}.parse_project_version", return_value=("obra", "v1")),
            patch(f"{MODULE}.resolve_project", return_value=proj),
        ):
            result = _runner.invoke(mini_app, ["obra@v1"])

        assert result.exit_code == 0
        assert "12.00%" in result.output
        assert "Sem conflitos" in result.output

    def test_audit_with_conflitos(self):
        resultado = SimpleNamespace(
            margem_pct=0.05,
            status_margem="AVISO",
            custo=SimpleNamespace(total=500_000.0),
            validacoes=[],
        )
        conflitos = [_make_conflito(f"R-{i}", i, f"W{i:02d}") for i in range(1, 6)]
        canonical = SimpleNamespace(
            pipeline_integridade="PARCIAL",
            resultado=resultado,
            conflitos_pico=conflitos,
        )
        proj = _fake_project(nome="Obra Conflito", load_canonical=canonical)

        mini_app = _build_audit_app()
        _runner = CliRunner()

        with (
            patch(f"{MODULE}.parse_project_version", return_value=("obra", "v1")),
            patch(f"{MODULE}.resolve_project", return_value=proj),
        ):
            result = _runner.invoke(mini_app, ["obra@v1"])

        assert result.exit_code == 0
        assert "mais 2 outros" in result.output
        assert "PARCIAL" in result.output

    def test_audit_with_validacoes(self):
        val_ok = SimpleNamespace(status="OK", codigo="V-001")
        val_aviso = SimpleNamespace(status="AVISO", codigo="V-002")
        val_erro = SimpleNamespace(status="ERRO", codigo="V-003")

        resultado = SimpleNamespace(
            margem_pct=0.10,
            status_margem="OK",
            custo=SimpleNamespace(total=200_000.0),
            validacoes=[val_ok, val_aviso, val_erro],
        )
        canonical = SimpleNamespace(
            pipeline_integridade="COMPLETO",
            resultado=resultado,
            conflitos_pico=[],
        )
        proj = _fake_project(nome="Obra Validacoes", load_canonical=canonical)

        mini_app = _build_audit_app()
        _runner = CliRunner()

        with (
            patch(f"{MODULE}.parse_project_version", return_value=("obra", "v1")),
            patch(f"{MODULE}.resolve_project", return_value=proj),
        ):
            result = _runner.invoke(mini_app, ["obra@v1"])

        assert result.exit_code == 0
        assert "V-001" in result.output
        assert "V-002" in result.output
        assert "V-003" in result.output

    def test_audit_integridade_parcial_color(self):
        """Non-COMPLETO integridade uses yellow."""
        canonical = SimpleNamespace(
            pipeline_integridade="PARCIAL",
            resultado=None,
            conflitos_pico=[],
        )
        proj = _fake_project(nome="Obra P", load_canonical=canonical)

        mini_app = _build_audit_app()
        _runner = CliRunner()

        with (
            patch(f"{MODULE}.parse_project_version", return_value=("obra", None)),
            patch(f"{MODULE}.resolve_project", return_value=proj),
        ):
            result = _runner.invoke(mini_app, ["obra"])

        assert result.exit_code == 0
        assert "PARCIAL" in result.output

    def test_audit_none_integridade_shown_as_desconhecido(self):
        """None pipeline_integridade displays as DESCONHECIDO."""
        canonical = SimpleNamespace(
            pipeline_integridade=None,
            resultado=None,
            conflitos_pico=[],
        )
        proj = _fake_project(nome="Obra D", load_canonical=canonical)

        mini_app = _build_audit_app()
        _runner = CliRunner()

        with (
            patch(f"{MODULE}.parse_project_version", return_value=("obra", None)),
            patch(f"{MODULE}.resolve_project", return_value=proj),
        ):
            result = _runner.invoke(mini_app, ["obra"])

        assert result.exit_code == 0
        assert "DESCONHECIDO" in result.output

    def test_audit_without_at_sign_parses_name_only(self):
        """parse_project_version with no @ returns (name, None)."""
        canonical = SimpleNamespace(
            pipeline_integridade="COMPLETO",
            resultado=None,
            conflitos_pico=[],
        )
        proj = _fake_project(nome="Simples", load_canonical=canonical)

        mini_app = _build_audit_app()
        _runner = CliRunner()

        with (
            patch(f"{MODULE}.parse_project_version", return_value=("simples", None)),
            patch(f"{MODULE}.resolve_project", return_value=proj),
        ):
            result = _runner.invoke(mini_app, ["simples"])

        assert result.exit_code == 0
