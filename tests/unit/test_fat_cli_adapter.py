"""Tests for concilium.presentation.cli.commands_adapter — covers adapter_run command.

Covers:
- happy path: skill runs successfully, prints green output path, exits 0
- no active version: project.current_version() returns None, exits with code 1
- RuntimeError raised by rt.run_skill, exits with code 1
- result.has_errors is True, iterates validacoes and prints per-status colour, exits with code 1
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from concilium.presentation.cli.commands_adapter import app


# ---------------------------------------------------------------------------
# Fake domain objects
# ---------------------------------------------------------------------------


class FakeValidacao(NamedTuple):
    status: str
    codigo: str
    mensagem: str | None = None


class FakeResult:
    def __init__(self, has_errors: bool, validacoes=None):
        self.has_errors = has_errors
        self.validacoes = validacoes or []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

runner = CliRunner()


def _make_project_mock(version: str | None = "v1", version_path: Path | None = None):
    """Build a project mock with current_version and version_path configured."""
    project = MagicMock()
    project.current_version.return_value = version
    if version_path is None:
        version_path = Path("/tmp/proj/v1")
    project.version_path.return_value = version_path
    return project


def _patch_shared(parse_return, resolve_return):
    """Return a context manager pair that patches parse_project_version and resolve_project."""
    patch_parse = patch(
        "concilium.presentation.cli.commands_adapter.parse_project_version",
        return_value=parse_return,
    )
    patch_resolve = patch(
        "concilium.presentation.cli.commands_adapter.resolve_project",
        return_value=resolve_return,
    )
    return patch_parse, patch_resolve


def _patch_config_root(tmp_path: Path):
    """Patch config_root() to return a temp dir that actually exists."""
    return patch(
        "concilium.presentation.cli.commands_adapter.config_root",
        return_value=tmp_path,
    )


def _patch_runtime(runtime_instance=None, side_effect=None, runtime_error_cls=None):
    """
    Patch concilium.application.runtime.Runtime (and RuntimeError).

    The inline `from concilium.application.runtime import Runtime, RuntimeError`
    inside adapter_run means we must patch at the source module, not at the
    commands_adapter namespace.
    """
    import concilium.application.runtime as runtime_mod

    # Use the real RuntimeError unless a fake class is supplied
    fake_cls = runtime_error_cls or runtime_mod.RuntimeError  # type: ignore[attr-defined]

    if side_effect is not None:
        runtime_mock = MagicMock(side_effect=side_effect)
    else:
        rt = runtime_instance or MagicMock()
        runtime_mock = MagicMock(return_value=rt)

    patch_rt = patch.object(runtime_mod, "Runtime", runtime_mock)
    patch_re = patch.object(runtime_mod, "RuntimeError", fake_cls)
    return patch_rt, patch_re, runtime_mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAdapterRunHappyPath:
    """Happy path: skill succeeds and prints green output path."""

    def test_exit_code_zero(self, tmp_path):
        project = _make_project_mock(version="v1", version_path=tmp_path / "proj" / "v1")
        result_obj = FakeResult(has_errors=False)

        import concilium.application.runtime as runtime_mod

        rt_instance = MagicMock()
        rt_instance.run_skill.return_value = result_obj

        patch_parse, patch_resolve = _patch_shared(("meu-projeto", None), project)
        patch_rt, patch_re, _ = _patch_runtime(runtime_instance=rt_instance)

        with patch_parse, patch_resolve, patch_rt, patch_re, _patch_config_root(tmp_path):
            result = runner.invoke(app, ["meu-projeto"])

        assert result.exit_code == 0

    def test_green_output_path_in_stdout(self, tmp_path):
        output_path = tmp_path / "proj" / "v1"
        project = _make_project_mock(version="v1", version_path=output_path)
        result_obj = FakeResult(has_errors=False)

        rt_instance = MagicMock()
        rt_instance.run_skill.return_value = result_obj

        patch_parse, patch_resolve = _patch_shared(("meu-projeto", None), project)
        patch_rt, patch_re, _ = _patch_runtime(runtime_instance=rt_instance)

        with patch_parse, patch_resolve, patch_rt, patch_re, _patch_config_root(tmp_path):
            result = runner.invoke(app, ["meu-projeto"])

        assert "relatorio.json" in result.output

    def test_run_skill_called_with_correct_skill_name(self, tmp_path):
        project = _make_project_mock(version="v2")
        result_obj = FakeResult(has_errors=False)

        rt_instance = MagicMock()
        rt_instance.run_skill.return_value = result_obj

        patch_parse, patch_resolve = _patch_shared(("proj", None), project)
        patch_rt, patch_re, _ = _patch_runtime(runtime_instance=rt_instance)

        with patch_parse, patch_resolve, patch_rt, patch_re, _patch_config_root(tmp_path):
            runner.invoke(app, ["proj"])

        rt_instance.run_skill.assert_called_once_with(
            "09-relatorio-e-artefatos", project, version="v2", inputs={}
        )

    def test_explicit_version_in_arg(self, tmp_path):
        """When arg contains @vN the explicit version is passed to run_skill."""
        project = _make_project_mock(version=None)  # current_version not consulted
        result_obj = FakeResult(has_errors=False)

        rt_instance = MagicMock()
        rt_instance.run_skill.return_value = result_obj

        # parse_project_version returns ("proj", "v3") for "proj@v3"
        patch_parse, patch_resolve = _patch_shared(("proj", "v3"), project)
        patch_rt, patch_re, _ = _patch_runtime(runtime_instance=rt_instance)

        with patch_parse, patch_resolve, patch_rt, patch_re, _patch_config_root(tmp_path):
            result = runner.invoke(app, ["proj@v3"])

        assert result.exit_code == 0
        rt_instance.run_skill.assert_called_once_with(
            "09-relatorio-e-artefatos", project, version="v3", inputs={}
        )


class TestAdapterRunNoActiveVersion:
    """project.current_version() returns None and no explicit version → Exit(1)."""

    def test_exit_code_one(self, tmp_path):
        project = _make_project_mock(version=None)

        rt_instance = MagicMock()

        patch_parse, patch_resolve = _patch_shared(("proj", None), project)
        patch_rt, patch_re, _ = _patch_runtime(runtime_instance=rt_instance)

        with patch_parse, patch_resolve, patch_rt, patch_re, _patch_config_root(tmp_path):
            result = runner.invoke(app, ["proj"])

        assert result.exit_code == 1

    def test_red_message_in_output(self, tmp_path):
        project = _make_project_mock(version=None)

        rt_instance = MagicMock()

        patch_parse, patch_resolve = _patch_shared(("proj", None), project)
        patch_rt, patch_re, _ = _patch_runtime(runtime_instance=rt_instance)

        with patch_parse, patch_resolve, patch_rt, patch_re, _patch_config_root(tmp_path):
            result = runner.invoke(app, ["proj"])

        assert "vers" in result.output.lower() or "ativa" in result.output.lower() or "nenhuma" in result.output.lower()

    def test_run_skill_not_called(self, tmp_path):
        project = _make_project_mock(version=None)

        rt_instance = MagicMock()

        patch_parse, patch_resolve = _patch_shared(("proj", None), project)
        patch_rt, patch_re, _ = _patch_runtime(runtime_instance=rt_instance)

        with patch_parse, patch_resolve, patch_rt, patch_re, _patch_config_root(tmp_path):
            runner.invoke(app, ["proj"])

        rt_instance.run_skill.assert_not_called()


class TestAdapterRunRuntimeError:
    """RuntimeError raised by rt.run_skill → Exit(1) with red message."""

    def test_exit_code_one(self, tmp_path):
        project = _make_project_mock(version="v1")

        import concilium.application.runtime as runtime_mod

        rt_instance = MagicMock()
        rt_instance.run_skill.side_effect = runtime_mod.RuntimeError("skill explodiu")

        patch_parse, patch_resolve = _patch_shared(("proj", None), project)
        patch_rt, patch_re, _ = _patch_runtime(runtime_instance=rt_instance)

        with patch_parse, patch_resolve, patch_rt, patch_re, _patch_config_root(tmp_path):
            result = runner.invoke(app, ["proj"])

        assert result.exit_code == 1

    def test_error_message_in_output(self, tmp_path):
        project = _make_project_mock(version="v1")

        import concilium.application.runtime as runtime_mod

        rt_instance = MagicMock()
        rt_instance.run_skill.side_effect = runtime_mod.RuntimeError("skill explodiu")

        patch_parse, patch_resolve = _patch_shared(("proj", None), project)
        patch_rt, patch_re, _ = _patch_runtime(runtime_instance=rt_instance)

        with patch_parse, patch_resolve, patch_rt, patch_re, _patch_config_root(tmp_path):
            result = runner.invoke(app, ["proj"])

        assert "skill explodiu" in result.output

    def test_no_traceback_leaked(self, tmp_path):
        """Exception is caught; no Python traceback should appear in output."""
        project = _make_project_mock(version="v1")

        import concilium.application.runtime as runtime_mod

        rt_instance = MagicMock()
        rt_instance.run_skill.side_effect = runtime_mod.RuntimeError("boom")

        patch_parse, patch_resolve = _patch_shared(("proj", None), project)
        patch_rt, patch_re, _ = _patch_runtime(runtime_instance=rt_instance)

        with patch_parse, patch_resolve, patch_rt, patch_re, _patch_config_root(tmp_path):
            result = runner.invoke(app, ["proj"])

        assert "Traceback" not in result.output


class TestAdapterRunHasErrors:
    """result.has_errors is True → iterates validacoes, exits 1."""

    def _make_result_with_errors(self, validacoes):
        return FakeResult(has_errors=True, validacoes=validacoes)

    def test_exit_code_one_when_has_errors(self, tmp_path):
        project = _make_project_mock(version="v1")
        validacoes = [FakeValidacao("ERRO", "E001", "algo errado")]
        result_obj = self._make_result_with_errors(validacoes)

        rt_instance = MagicMock()
        rt_instance.run_skill.return_value = result_obj

        patch_parse, patch_resolve = _patch_shared(("proj", None), project)
        patch_rt, patch_re, _ = _patch_runtime(runtime_instance=rt_instance)

        with patch_parse, patch_resolve, patch_rt, patch_re, _patch_config_root(tmp_path):
            result = runner.invoke(app, ["proj"])

        assert result.exit_code == 1

    def test_validacao_codigo_in_output(self, tmp_path):
        project = _make_project_mock(version="v1")
        validacoes = [FakeValidacao("ERRO", "E001", "algo errado")]
        result_obj = self._make_result_with_errors(validacoes)

        rt_instance = MagicMock()
        rt_instance.run_skill.return_value = result_obj

        patch_parse, patch_resolve = _patch_shared(("proj", None), project)
        patch_rt, patch_re, _ = _patch_runtime(runtime_instance=rt_instance)

        with patch_parse, patch_resolve, patch_rt, patch_re, _patch_config_root(tmp_path):
            result = runner.invoke(app, ["proj"])

        assert "E001" in result.output
        assert "algo errado" in result.output

    def test_aviso_status_in_output(self, tmp_path):
        project = _make_project_mock(version="v1")
        validacoes = [FakeValidacao("AVISO", "W001", "cuidado")]
        result_obj = self._make_result_with_errors(validacoes)

        rt_instance = MagicMock()
        rt_instance.run_skill.return_value = result_obj

        patch_parse, patch_resolve = _patch_shared(("proj", None), project)
        patch_rt, patch_re, _ = _patch_runtime(runtime_instance=rt_instance)

        with patch_parse, patch_resolve, patch_rt, patch_re, _patch_config_root(tmp_path):
            result = runner.invoke(app, ["proj"])

        assert "W001" in result.output
        assert "cuidado" in result.output

    def test_ok_status_in_output(self, tmp_path):
        project = _make_project_mock(version="v1")
        validacoes = [FakeValidacao("OK", "I001", "tudo bem")]
        result_obj = self._make_result_with_errors(validacoes)

        rt_instance = MagicMock()
        rt_instance.run_skill.return_value = result_obj

        patch_parse, patch_resolve = _patch_shared(("proj", None), project)
        patch_rt, patch_re, _ = _patch_runtime(runtime_instance=rt_instance)

        with patch_parse, patch_resolve, patch_rt, patch_re, _patch_config_root(tmp_path):
            result = runner.invoke(app, ["proj"])

        assert "I001" in result.output

    def test_multiple_validacoes_all_in_output(self, tmp_path):
        project = _make_project_mock(version="v1")
        validacoes = [
            FakeValidacao("ERRO", "E001", "erro principal"),
            FakeValidacao("AVISO", "W002", "aviso sec"),
            FakeValidacao("OK", "I003", None),
        ]
        result_obj = self._make_result_with_errors(validacoes)

        rt_instance = MagicMock()
        rt_instance.run_skill.return_value = result_obj

        patch_parse, patch_resolve = _patch_shared(("proj", None), project)
        patch_rt, patch_re, _ = _patch_runtime(runtime_instance=rt_instance)

        with patch_parse, patch_resolve, patch_rt, patch_re, _patch_config_root(tmp_path):
            result = runner.invoke(app, ["proj"])

        assert "E001" in result.output
        assert "W002" in result.output
        assert "I003" in result.output
        assert result.exit_code == 1

    def test_validacao_none_mensagem_handled(self, tmp_path):
        """mensagem=None should not cause a crash (empty string fallback in code)."""
        project = _make_project_mock(version="v1")
        validacoes = [FakeValidacao("ERRO", "E999", None)]
        result_obj = self._make_result_with_errors(validacoes)

        rt_instance = MagicMock()
        rt_instance.run_skill.return_value = result_obj

        patch_parse, patch_resolve = _patch_shared(("proj", None), project)
        patch_rt, patch_re, _ = _patch_runtime(runtime_instance=rt_instance)

        with patch_parse, patch_resolve, patch_rt, patch_re, _patch_config_root(tmp_path):
            result = runner.invoke(app, ["proj"])

        assert "E999" in result.output
        assert result.exit_code == 1
