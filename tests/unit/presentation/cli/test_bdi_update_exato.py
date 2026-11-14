"""N9.1 (#206): `concilium bdi update` saves the project's exact BDI declaration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner

from concilium.presentation.cli.commands_bdi import app as bdi_app

runner = CliRunner()
_RESOLVE = "concilium.presentation.cli.commands_bdi.resolve_project"
EXATA = {
    "schema": "concilium.projeto.bdi-exato.v1",
    "fonte": "ISS 2% — lei municipal",
    "linhas": {
        "mao_obra": {
            "l": "0.08",
            "tributos": {"iss": {"aplicavel": True, "aliquota": "0.02"}, "cofins": {"aplicavel": False}},
        }
    },
}


class FileProject:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.meta = {"id": "proj-uuid-001"}

    def exists(self, relative_path: str) -> bool:
        return (self.root / relative_path).exists()

    def read_json(self, relative_path: str, default: Any) -> Any:
        try:
            return json.loads((self.root / relative_path).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    def write_json(self, relative_path: str, payload: Any) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _invoke(tmp_path: Path, declaration: dict, *extra: str):
    root = tmp_path / "proj"
    root.mkdir(exist_ok=True)
    source = tmp_path / "exato.json"
    source.write_text(json.dumps(declaration), encoding="utf-8")
    with patch(_RESOLVE, return_value=FileProject(root)):
        result = runner.invoke(
            bdi_app, ["update", "mypro", "--from-file", str(source), "--confirmado-por", "Eng", *extra]
        )
    files = {p.name for p in (root / "bdi").glob("*")} if (root / "bdi").exists() else set()
    return result, files, root


def test_exact_file_is_saved_as_version_1(tmp_path) -> None:
    result, files, root = _invoke(tmp_path, EXATA, "--yes")
    assert result.exit_code == 0, result.output
    assert "v1" in result.output and "mao_obra.iss = 0.02" in result.output
    assert files == {"perfil_bdi_exato.json", "perfil_bdi_exato_v001.json"}
    stored = json.loads((root / "bdi/perfil_bdi_exato.json").read_text(encoding="utf-8"))
    assert stored["declaracao"] == EXATA and stored["projeto_id"] == "proj-uuid-001"


def test_exact_update_needs_motivo_then_versions(tmp_path) -> None:
    _invoke(tmp_path, EXATA, "--yes")
    revised = {**EXATA, "linhas": {"mao_obra": {"l": "0.07"}}}
    refused, files, _root = _invoke(tmp_path, revised, "--yes")
    assert refused.exit_code == 1 and "motivo_revisao is required" in refused.output
    assert "perfil_bdi_exato_v002.json" not in files
    saved, files, _root = _invoke(tmp_path, revised, "--yes", "--motivo", "lucro 7%")
    assert saved.exit_code == 0, saved.output
    assert {"perfil_bdi_exato_v002.json", "perfil_bdi_exato_diff_v002.json"} <= files
    assert "linhas.mao_obra.l" in saved.output


def test_float_in_exact_file_is_rejected_before_anything_is_written(tmp_path) -> None:
    result, files, _root = _invoke(tmp_path, {**EXATA, "linhas": {"mao_obra": {"l": 0.08}}}, "--yes")
    assert result.exit_code == 1
    assert "Declaração exata inválida" in result.output and "exact decimal or rational string" in result.output
    assert files == set()


def test_unconfirmed_exact_save_writes_nothing(tmp_path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    source = tmp_path / "exato.json"
    source.write_text(json.dumps(EXATA), encoding="utf-8")
    with patch(_RESOLVE, return_value=FileProject(root)):
        result = runner.invoke(
            bdi_app, ["update", "mypro", "--from-file", str(source), "--confirmado-por", "Eng"], input="n\n"
        )
    assert result.exit_code == 0 and "cancelada" in result.output
    assert not (root / "bdi").exists()
