"""N9.1 (#206): `concilium bdi show` shows what the exact price reads, in every state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner

from concilium.application.scheduling.project_bdi_exact_store import HEAD, LEGACY_HEAD, save_exact_project_bdi
from concilium.presentation.cli.commands_bdi import app as bdi_app

runner = CliRunner()
_MOD = "concilium.presentation.cli.commands_bdi"
ROOT = Path(__file__).resolve().parents[4]
PROFILE = json.loads((ROOT / "config/perfis/mendeslobo.json").read_text(encoding="utf-8"))
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
        self.meta = {"id": "proj-uuid-001", "contexto_id": "mendeslobo"}

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


def _show(project: FileProject, profile: tuple = ("mendeslobo", PROFILE, None)) -> str:
    with patch(f"{_MOD}.resolve_project", return_value=project), patch(f"{_MOD}._load_profile", return_value=profile):
        result = runner.invoke(bdi_app, ["show", "mypro"])
    assert result.exit_code == 0, result.output
    return result.output


def test_exact_declaration_saved(tmp_path) -> None:
    project = FileProject(tmp_path)
    save_exact_project_bdi(project, "proj-uuid-001", EXATA, confirmado_por="Eng. A", motivo_revisao=None)
    save_exact_project_bdi(
        project,
        "proj-uuid-001",
        {**EXATA, "fonte": "revisão"},
        confirmado_por="Eng. B",
        motivo_revisao="nova fonte",
    )
    record = project.read_json(HEAD, None)
    out = _show(project)
    assert "Estado: EXATO" in out and "NÃO AVALIADO" not in out
    assert "Versão:          2" in out and "Confirmado por:  Eng. B" in out
    assert f"Data:            {record['confirmado_em']}" in out
    assert f"Content hash:    {record['content_hash']}" in out
    assert "Motivo revisão:  nova fonte" in out and "Fonte:           revisão" in out
    assert "mao_obra.l = 0.08" in out and "mao_obra.iss = 0.02" in out and "mao_obra.cofins = não aplicável" in out
    assert "Camadas efetivas por categoria (perfil 'mendeslobo'" in out
    assert "l=0.08 [projeto]" in out and "iss=0.02 [projeto]" in out and "cofins=0 [projeto]" in out
    assert "ac=0.05 [perfil]" in out and "l=0.09 [perfil]" in out  # servicos keeps the profile's profit
    mo_line = next(line for line in out.splitlines() if line.strip().startswith("MO (linha mao_obra"))
    assert "markup = " in mo_line and "(≈ " in mo_line and "aproximado)" in mo_line
    assert "Para declarar em forma exata" not in out


def test_float_profile_only(tmp_path) -> None:
    project = FileProject(tmp_path)
    project.write_json(
        LEGACY_HEAD, {"versao": 2, "confirmado_por": "Eng. Legado", "lucro": {"mao_obra": 0.0812}}
    )
    out = _show(project)
    assert "Estado: SOMENTE_LEGADO" in out and "PREÇO EXATO NÃO AVALIADO" in out
    assert "never converted" in out
    assert "bdi/perfil_bdi.json v2 (confirmado por Eng. Legado)" in out and "não é usado pelo preço exato" in out
    assert "0.0812" not in out and "8.1" not in out  # legacy floats are not displayed
    assert "Camadas efetivas não exibidas" in out
    assert "concilium bdi update mypro --from-file" in out and "concilium.projeto.bdi-exato.v1" in out


def test_damaged_exact_head(tmp_path) -> None:
    project = FileProject(tmp_path)
    save_exact_project_bdi(project, "proj-uuid-001", EXATA, confirmado_por="Eng. A", motivo_revisao=None)
    record = project.read_json(HEAD, None)
    record["content_hash"] = "0" * 64
    project.write_json(HEAD, record)
    out = _show(project)
    assert "Estado: DANIFICADO" in out and "PREÇO EXATO NÃO AVALIADO" in out
    assert "content_hash does not match the stored declaration" in out
    assert "Versão:" not in out and "[projeto]" not in out


def test_no_profile_at_all(tmp_path) -> None:
    out = _show(FileProject(tmp_path))
    assert "Estado: NENHUM" in out and "valem as camadas do perfil da construtora" in out
    assert "NÃO AVALIADO" not in out and "[projeto]" not in out and "l=0.09 [perfil]" in out
    assert "Para declarar em forma exata" in out


def test_unresolvable_profile_is_stated(tmp_path) -> None:
    project = FileProject(tmp_path)
    save_exact_project_bdi(project, "proj-uuid-001", EXATA, confirmado_por="Eng. A", motivo_revisao=None)
    out = _show(project, (None, None, "the construction profile of context 'x' could not be loaded: gone"))
    assert "Estado: EXATO" in out and "mao_obra.l = 0.08" in out
    assert "Camadas efetivas não exibidas: the construction profile of context 'x' could not be loaded" in out


def test_profile_is_resolved_from_the_project_context(tmp_path, monkeypatch) -> None:
    """Without patching `_load_profile`: the project's contexto_id leads to the configured profile."""
    monkeypatch.setattr("concilium.presentation.cli.shared._config_root", lambda: ROOT / "config")
    with patch(f"{_MOD}.resolve_project", return_value=FileProject(tmp_path)):
        result = runner.invoke(bdi_app, ["show", "mypro"])
    assert result.exit_code == 0, result.output
    assert "perfil 'mendeslobo'" in result.output
