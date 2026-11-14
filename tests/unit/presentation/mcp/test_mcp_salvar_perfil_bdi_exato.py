"""N9.1 (#206): `salvar_perfil_bdi` saves the project's exact BDI declaration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from mcp.server.fastmcp import FastMCP

from concilium.presentation.mcp.tools.projeto import register

_PROJECT = "concilium.presentation.mcp.tools.projeto._project"
EXATA = {
    "schema": "concilium.projeto.bdi-exato.v1",
    "fonte": "ISS 2% — lei municipal",
    "linhas": {"mao_obra": {"l": "0.08", "tributos": {"iss": {"aplicavel": True, "aliquota": "0.02"}}}},
}
_APLICACAO = {
    name: {"aplicavel": True, "aliquota": rate}
    for name, rate in (("iss", 0.02), ("cofins", 0.03), ("pis", 0.0065), ("cssl", 0.0199), ("ir", 0.0274))
}
TRIBUTARIO = {
    "regime": "lucro_presumido",
    "municipio": "Fortaleza",
    "iss_aliquota_municipal": 0.02,
    **dict.fromkeys(("mao_obra", "material", "servicos", "indireto", "diesel"), _APLICACAO),
}
LUCRO = {"mao_obra": 0.09, "material": 0.0, "servicos": 0.09, "indireto": 0.02, "diesel": 0.05}


class FileProject:
    """Project handle over a real directory (the legacy tool writes through `root`)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.meta = {"id": "proj-001"}

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


@pytest.fixture()
def salvar():
    server = FastMCP("test")
    register(server)
    return server._tool_manager._tools["salvar_perfil_bdi"].fn


def _files(root: Path) -> set[str]:
    return {p.name for p in (root / "bdi").glob("*")} if (root / "bdi").exists() else set()


def test_exact_only_save_writes_only_the_exact_files(salvar, tmp_path) -> None:
    with patch(_PROJECT, return_value=FileProject(tmp_path)):
        result = salvar(project_id="proj-001", confirmado_por="Eng. A", declaracao_exata=EXATA)
    assert "erro" not in result
    assert result["exato"]["versao"] == 1 and len(result["exato"]["content_hash"]) == 64
    assert _files(tmp_path) == {"perfil_bdi_exato.json", "perfil_bdi_exato_v001.json"}
    stored = json.loads((tmp_path / "bdi/perfil_bdi_exato.json").read_text(encoding="utf-8"))
    assert stored["declaracao"] == EXATA and stored["confirmado_por"] == "Eng. A"


def test_exact_update_requires_reason_and_returns_diff(salvar, tmp_path) -> None:
    revised = {**EXATA, "linhas": {"mao_obra": {"l": "0.07"}}}
    with patch(_PROJECT, return_value=FileProject(tmp_path)):
        salvar(project_id="proj-001", confirmado_por="Eng. A", declaracao_exata=EXATA)
        refused = salvar(project_id="proj-001", confirmado_por="Eng. A", declaracao_exata=revised)
        saved = salvar(
            project_id="proj-001", confirmado_por="Eng. A", declaracao_exata=revised, motivo_revisao="lucro 7%"
        )
    assert "motivo_revisao is required" in refused["erro"]
    assert saved["exato"]["versao"] == 2
    assert "linhas.mao_obra.l" in saved["exato"]["diff"]["campos_alterados"]
    assert {"perfil_bdi_exato_v001.json", "perfil_bdi_exato_v002.json", "perfil_bdi_exato_diff_v002.json"} <= _files(
        tmp_path
    )


@pytest.mark.parametrize(
    ("declaration", "match"),
    [
        ({**EXATA, "linhas": {"mao_obra": {"l": 0.08}}}, "exact decimal or rational string"),
        ({**EXATA, "linhas": {"equipamento": {"l": "0.08"}}}, "unknown row"),
        ({"tributario": TRIBUTARIO, "lucro": LUCRO}, "exactly schema, fonte and linhas"),
    ],
)
def test_invalid_exact_declaration_is_rejected_with_the_reason(salvar, tmp_path, declaration, match) -> None:
    with patch(_PROJECT, return_value=FileProject(tmp_path)):
        result = salvar(project_id="proj-001", confirmado_por="Eng. A", declaracao_exata=declaration)
    assert "Declaração exata inválida" in result["erro"] and match in result["erro"]
    assert _files(tmp_path) == set()


def test_invalid_exact_declaration_blocks_the_legacy_save_too(salvar, tmp_path) -> None:
    with patch(_PROJECT, return_value=FileProject(tmp_path)):
        result = salvar(
            project_id="proj-001",
            tributario=TRIBUTARIO,
            lucro=LUCRO,
            confirmado_por="Eng. A",
            declaracao_exata={**EXATA, "linhas": {"mao_obra": {"l": 0.08}}},
        )
    assert "Declaração exata inválida" in result["erro"]
    assert _files(tmp_path) == set()


def test_float_profile_alone_never_writes_the_exact_file(salvar, tmp_path) -> None:
    with patch(_PROJECT, return_value=FileProject(tmp_path)):
        result = salvar(project_id="proj-001", tributario=TRIBUTARIO, lucro=LUCRO, confirmado_por="Eng. A")
    assert result["versao"] == 1 and "exato" not in result
    assert _files(tmp_path) == {"perfil_bdi.json", "perfil_bdi_v001.json"}


def test_both_forms_are_saved_side_by_side(salvar, tmp_path) -> None:
    with patch(_PROJECT, return_value=FileProject(tmp_path)):
        result = salvar(
            project_id="proj-001", tributario=TRIBUTARIO, lucro=LUCRO, confirmado_por="Eng. A", declaracao_exata=EXATA
        )
    assert result["versao"] == 1 and result["exato"]["versao"] == 1
    assert _files(tmp_path) == {
        "perfil_bdi.json",
        "perfil_bdi_v001.json",
        "perfil_bdi_exato.json",
        "perfil_bdi_exato_v001.json",
    }
    # The exact file holds the exact declaration, not anything derived from the float model.
    stored = json.loads((tmp_path / "bdi/perfil_bdi_exato.json").read_text(encoding="utf-8"))
    assert stored["declaracao"] == EXATA


def test_nothing_to_save_and_missing_confirmation_are_errors(salvar, tmp_path) -> None:
    with patch(_PROJECT, return_value=FileProject(tmp_path)):
        assert "erro" in salvar(project_id="proj-001", confirmado_por="Eng. A")
        assert "confirmado_por" in salvar(project_id="proj-001", declaracao_exata=EXATA)["erro"]
    assert _files(tmp_path) == set()
