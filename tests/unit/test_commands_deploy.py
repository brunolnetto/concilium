"""Tests for concilium.presentation.cli.commands_deploy (ADR-144 D1).

TDD: escritos antes da implementação. `record-promotion` é o comando
executado dentro do container recém-promovido (via `az containerapp exec`,
ADR-144 D1 opção b) — usa as credenciais reais de storage já configuradas no
runtime, evitando a ambiguidade de qual backend o CI enxergaria.

Nota sobre invocação nos testes: `deploy_app` hoje só tem 1 comando
registrado — Typer "colapsa" um Typer de comando único quando ele é o alvo
*direto* do CliRunner (não aceita o nome do subcomando nesse caso). Isso não
reflete o uso real: em produção, `deploy_app` é composto dentro de `ops_app`
(múltiplos typers), onde o Typer pai sempre expõe "record-promotion" como
subcomando de verdade (confirmado via `python -m concilium.presentation.main
ops deploy --help`). Por isso os testes invocam através de um Typer pai
mínimo — mesma topologia de composição do `main.py` real — em vez de invocar
`deploy_app` isoladamente.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import typer
from typer.testing import CliRunner

from concilium.presentation.cli.commands_deploy import deploy_app

runner = CliRunner()

_STORE_PATH = "concilium.presentation.cli.commands_deploy._get_deploy_log_store"


def _root_app():
    """Mesma topologia de composição do main.py real: deploy_app nested num pai."""
    root = typer.Typer()
    root.add_typer(deploy_app, name="deploy")
    return root


class TestRecordPromotion:
    def test_saves_entry_with_given_fields(self):
        store = MagicMock()
        with patch(_STORE_PATH, return_value=store):
            result = runner.invoke(
                _root_app(),
                [
                    "deploy",
                    "record-promotion",
                    "--image-tag",
                    "90caf8ae",
                    "--api-revision",
                    "concilium-api--0000091",
                    "--mcp-revision",
                    "concilium-mcp--0000097",
                    "--resumo",
                    "ADR-144: notificação embutida em ping()",
                ],
            )

        assert result.exit_code == 0, result.output
        store.save_latest.assert_called_once()
        entry = store.save_latest.call_args.args[0]
        assert entry.image_tag == "90caf8ae"
        assert entry.api_revision == "concilium-api--0000091"
        assert entry.mcp_revision == "concilium-mcp--0000097"
        assert entry.resumo == "ADR-144: notificação embutida em ping()"
        assert entry.promoted_at  # timestamp não vazio

    def test_promoted_at_is_iso_utc(self):
        store = MagicMock()
        with patch(_STORE_PATH, return_value=store):
            runner.invoke(
                _root_app(),
                [
                    "deploy",
                    "record-promotion",
                    "--image-tag",
                    "abc123",
                    "--api-revision",
                    "api--1",
                    "--mcp-revision",
                    "mcp--1",
                ],
            )

        entry = store.save_latest.call_args.args[0]
        from datetime import datetime

        parsed = datetime.fromisoformat(entry.promoted_at)
        assert parsed.tzinfo is not None

    def test_resumo_defaults_to_empty_string(self):
        store = MagicMock()
        with patch(_STORE_PATH, return_value=store):
            runner.invoke(
                _root_app(),
                [
                    "deploy",
                    "record-promotion",
                    "--image-tag",
                    "abc123",
                    "--api-revision",
                    "api--1",
                    "--mcp-revision",
                    "mcp--1",
                ],
            )

        entry = store.save_latest.call_args.args[0]
        assert entry.resumo == ""

    def test_prints_confirmation(self):
        store = MagicMock()
        with patch(_STORE_PATH, return_value=store):
            result = runner.invoke(
                _root_app(),
                [
                    "deploy",
                    "record-promotion",
                    "--image-tag",
                    "abc123",
                    "--api-revision",
                    "api--1",
                    "--mcp-revision",
                    "mcp--1",
                ],
            )

        assert "abc123" in result.output
