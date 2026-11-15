"""Tests for presentation/cli/commands_validate.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from concilium.presentation.cli.commands_validate import (
    _collect_project_validacoes,
    _empty_resumo,
    _tally_resumo,
    _val_status_color,
    app,
)
from tests.support.exact_financial import evaluated_resultado, unknown_resultado

runner = CliRunner()


class TestHelpers:
    def test_empty_resumo(self):
        r = _empty_resumo()
        assert r == {"verde": 0, "amarelo": 0, "vermelho": 0}

    def test_tally_resumo(self):
        resumo = _empty_resumo()
        validacoes = [
            {"status": "OK"},
            {"status": "AVISO"},
            {"status": "ERRO"},
            {"status": "EXCEPTION"},
        ]
        _tally_resumo(validacoes, resumo)
        assert resumo["verde"] == 1
        assert resumo["amarelo"] == 1
        assert resumo["vermelho"] == 2

    def test_tally_resumo_unknown_status_not_counted(self):
        """Status fora de OK/AVISO/ERRO/EXCEPTION não incrementa nenhum contador
        (cobre o ramo falso do último elif, que apenas segue para a próxima
        validação sem tocar em resumo)."""
        resumo = _empty_resumo()
        _tally_resumo([{"status": "DESCONHECIDO"}], resumo)
        assert resumo == {"verde": 0, "amarelo": 0, "vermelho": 0}

    def test_val_status_color_ok(self):
        assert _val_status_color("OK") == "green"

    def test_val_status_color_aviso(self):
        assert _val_status_color("AVISO") == "yellow"

    def test_val_status_color_erro(self):
        assert _val_status_color("ERRO") == "red"

    def test_collect_project_validacoes_empty(self):
        validacoes, resumo = _collect_project_validacoes({})
        assert validacoes == []
        assert resumo == {"verde": 0, "amarelo": 0, "vermelho": 0}

    def test_collect_project_validacoes_with_data(self):
        canonical = {
            "resultado": {
                "validacoes": [
                    {"status": "OK", "codigo": "VAL-01", "mensagem": "ok"},
                    {"status": "AVISO", "codigo": "VAL-02", "mensagem": "warn"},
                ]
            }
        }
        validacoes, resumo = _collect_project_validacoes(canonical)
        assert len(validacoes) == 2
        assert resumo["verde"] == 1
        assert resumo["amarelo"] == 1

    def test_collect_project_validacoes_skips_non_dicts(self):
        canonical = {"resultado": {"validacoes": ["bad", None, {"status": "OK", "codigo": "VAL-1"}]}}
        validacoes, _ = _collect_project_validacoes(canonical)
        assert len(validacoes) == 1


class TestValidateProjectCommand:
    def _setup_project(self, canonical_mock=None):
        project = MagicMock()
        project.meta = {"id": "proj-1", "contexto_id": "ctx"}
        project.current_version.return_value = "v1"
        if canonical_mock is None:
            canonical = MagicMock()
            canonical.model_dump.return_value = {}
            canonical.resultado = None
        else:
            canonical = canonical_mock
        project.load_canonical.return_value = canonical
        return project

    def test_project_no_canonical_exits_1(self):
        project = MagicMock()
        project.meta = {"id": "p"}
        project.current_version.return_value = "v1"
        project.load_canonical.return_value = None

        with (
            patch("concilium.presentation.cli.commands_validate.parse_project_version", return_value=("p", None)),
            patch("concilium.presentation.cli.commands_validate.resolve_project", return_value=project),
        ):
            result = runner.invoke(app, ["project", "p"])
        assert result.exit_code != 0

    def test_project_json_output(self):
        project = self._setup_project()

        with (
            patch("concilium.presentation.cli.commands_validate.parse_project_version", return_value=("p", None)),
            patch("concilium.presentation.cli.commands_validate.resolve_project", return_value=project),
        ):
            result = runner.invoke(app, ["project", "p", "--json"])
        assert result.exit_code == 0
        assert "target_type" in result.output

    def test_project_human_output(self):
        project = self._setup_project()

        with (
            patch("concilium.presentation.cli.commands_validate.parse_project_version", return_value=("p", None)),
            patch("concilium.presentation.cli.commands_validate.resolve_project", return_value=project),
        ):
            result = runner.invoke(app, ["project", "p"])
        assert result.exit_code == 0

    def test_project_with_exact_financials(self):
        """#206: the payload carries the exact view; the legacy margin/status are not emitted.

        Replaces the former assertion that "margem_pct"/"15.00" appeared in the output.
        """
        canonical = MagicMock()
        canonical.model_dump.return_value = {}
        canonical.resultado = evaluated_resultado(legacy={"margem_pct": 0.15, "status_margem": "APROVADO"})
        project = self._setup_project(canonical)

        with (
            patch("concilium.presentation.cli.commands_validate.parse_project_version", return_value=("p", None)),
            patch("concilium.presentation.cli.commands_validate.resolve_project", return_value=project),
        ):
            result = runner.invoke(app, ["project", "p", "--json"])
        assert result.exit_code == 0
        output = result.output
        assert "financeiro_exato" in output and "AVALIADO" in output and "159/5" in output
        assert "margem_pct" not in output and "status_margem" not in output and "APROVADO" not in output

    @pytest.mark.parametrize("exact", [True, False])
    def test_project_human_output_shows_layers_or_not_evaluated(self, exact):
        canonical = MagicMock()
        canonical.model_dump.return_value = {}
        legacy = {"margem_pct": 0.15, "status_margem": "APROVADO"}
        canonical.resultado = evaluated_resultado(legacy=legacy) if exact else unknown_resultado(legacy=legacy)
        canonical.contratos_recurso = []
        project = self._setup_project(canonical)

        with (
            patch("concilium.presentation.cli.commands_validate.parse_project_version", return_value=("p", None)),
            patch("concilium.presentation.cli.commands_validate.resolve_project", return_value=project),
        ):
            result = runner.invoke(app, ["project", "p"])
        assert result.exit_code == 0
        output = result.output
        assert "Margem" not in output and "APROVADO" not in output and "15.00" not in output
        if exact:
            assert "Overhead" in output and "Lucro" in output and "Tributos" in output
            assert "Gates de preço: PASS" in output
        else:
            assert "Financeiro exato: não avaliado" in output and "Como resolver" in output
            assert "Overhead" not in output


class TestValidateBenchmarkCommand:
    def test_benchmark_json_output(self, tmp_path):
        validate_result = {
            "validacoes_fechamento": [
                {"status": "ok", "checkpoint": "CP1", "delta": 0.001},
                {"status": "erro", "checkpoint": "CP2", "delta": 0.5},
            ],
            "analise_base_referencia": {"contexto_id": "mendeslobo"},
        }

        with (
            patch("concilium.presentation.cli.commands_validate._tools_root", return_value=tmp_path),
            patch(
                "concilium.application.benchmarks.analysis.validate_pipeline_integrity", return_value=validate_result
            ),
        ):
            result = runner.invoke(app, ["benchmark", "AGIS", "--json"])
        assert result.exit_code == 0
        assert "target_type" in result.output

    def test_benchmark_human_output(self, tmp_path):
        validate_result = {
            "validacoes_fechamento": [{"status": "ok", "checkpoint": "CP1", "delta": 0}],
            "analise_base_referencia": {},
        }

        with (
            patch("concilium.presentation.cli.commands_validate._tools_root", return_value=tmp_path),
            patch(
                "concilium.application.benchmarks.analysis.validate_pipeline_integrity", return_value=validate_result
            ),
        ):
            result = runner.invoke(app, ["benchmark", "AGIS"])
        assert result.exit_code == 0

    def test_benchmark_empty_checkpoints(self, tmp_path):
        validate_result = {"validacoes_fechamento": [], "analise_base_referencia": {}}

        with (
            patch("concilium.presentation.cli.commands_validate._tools_root", return_value=tmp_path),
            patch(
                "concilium.application.benchmarks.analysis.validate_pipeline_integrity", return_value=validate_result
            ),
        ):
            result = runner.invoke(app, ["benchmark", "AGIS", "--json"])
        assert result.exit_code == 0
