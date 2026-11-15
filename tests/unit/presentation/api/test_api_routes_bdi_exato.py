"""N9.1 (#206): API of the project's exact BDI declaration (read by the UI editor)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from concilium.application.scheduling.project_bdi_exact_store import HEAD, LEGACY_HEAD, ProjectBdiExactError
from concilium.application.services.concilium_service import ConciliumService
from concilium.presentation.api.routes.overrides import get_project_bdi_exato, save_project_bdi_exato
from concilium.presentation.api.schemas import ProjectBdiExatoSaveRequest

ROOT = Path(__file__).resolve().parents[4]
DECLARATION = {
    "schema": "concilium.projeto.bdi-exato.v1",
    "fonte": "ISS 2% — lei municipal",
    "linhas": {"mao_obra": {"l": "0.08", "tributos": {"iss": {"aplicavel": True, "aliquota": "0.02"}}}},
}


class FakeProject:
    def __init__(self, contexto_id: str | None = "mendeslobo") -> None:
        self.files: dict[str, str] = {}
        self.meta: dict[str, Any] = {"id": "proj-1"}
        if contexto_id:
            self.meta["contexto_id"] = contexto_id

    def exists(self, relative_path: str) -> bool:
        return relative_path in self.files

    def read_json(self, relative_path: str, default: Any) -> Any:
        try:
            return json.loads(self.files[relative_path])
        except (KeyError, json.JSONDecodeError):
            return default

    def write_json(self, relative_path: str, payload: Any) -> None:
        self.files[relative_path] = json.dumps(payload, ensure_ascii=False)


def _service(project: FakeProject) -> tuple[ConciliumService, MagicMock]:
    audit = MagicMock()
    repository = SimpleNamespace(get_project=lambda project_id: project)
    deps = SimpleNamespace(
        input_builder=SimpleNamespace(_config_root=ROOT / "config"), repository=repository, audit_service=audit
    )
    return ConciliumService(deps), audit  # type: ignore[arg-type]


def _request(declaracao: dict = DECLARATION, confirmado_por: str = "Eng", motivo: str | None = None):
    return ProjectBdiExatoSaveRequest(declaracao=declaracao, confirmado_por=confirmado_por, motivo_revisao=motivo)


def test_get_reports_none_then_exact_with_merged_layers() -> None:
    project = FakeProject()
    service, audit = _service(project)
    status = get_project_bdi_exato("proj-1", service=service)
    assert status["estado"] == "NENHUM" and status["perfil_id"] == "mendeslobo" and status["camadas"] is not None

    saved = save_project_bdi_exato("proj-1", _request(), x_user="ana", service=service)
    assert saved["salvo"]["versao"] == 1 and len(saved["salvo"]["content_hash"]) == 64
    assert saved["status"]["estado"] == "EXATO"
    assert saved["status"]["camadas"]["categorias"]["MO"]["l"] == {"valor": "0.08", "origem": "project"}
    assert json.loads(project.files[HEAD])["declaracao"] == DECLARATION
    assert audit.log.call_args.kwargs["action"] == "save_project_bdi_exato"
    assert audit.log.call_args.kwargs["actor"] == "ana"
    assert get_project_bdi_exato("proj-1", service=service)["registro"]["confirmado_por"] == "Eng"
    json.dumps(saved)  # the whole response is JSON-able


def test_revision_requires_motivo_and_returns_diff() -> None:
    project = FakeProject()
    service, _audit = _service(project)
    save_project_bdi_exato("proj-1", _request(), x_user="ana", service=service)
    revised = {**DECLARATION, "linhas": {"mao_obra": {"l": "0.07"}}}
    with pytest.raises(HTTPException) as exc:
        save_project_bdi_exato("proj-1", _request(revised), x_user="ana", service=service)
    assert exc.value.status_code == 422 and "motivo_revisao is required" in exc.value.detail
    assert "bdi/perfil_bdi_exato_v002.json" not in project.files
    saved = save_project_bdi_exato("proj-1", _request(revised, motivo="lucro 7%"), x_user="ana", service=service)
    assert saved["salvo"]["versao"] == 2 and "linhas.mao_obra.l" in saved["salvo"]["diff"]["campos_alterados"]


@pytest.mark.parametrize(
    ("declaracao", "confirmado_por", "needle"),
    [
        ({**DECLARATION, "linhas": {"mao_obra": {"l": 0.08}}}, "Eng", "exact decimal or rational string"),
        ({**DECLARATION, "linhas": {"mao_obra": {"ac": "0.01"}}}, "Eng", "overrides only l and tributos"),
        (DECLARATION, "  ", "confirmado_por is required"),
        # Valid on its own, but over the real profile row the taxes reach 100%: checked as the price does.
        (
            {**DECLARATION, "linhas": {"mao_obra": {"tributos": {"iss": {"aplicavel": True, "aliquota": "0.96"}}}}},
            "Eng",
            "below 100%",
        ),
    ],
)
def test_invalid_declaration_is_refused_with_the_reason_and_nothing_is_written(
    declaracao: dict, confirmado_por: str, needle: str
) -> None:
    project = FakeProject()
    service, audit = _service(project)
    with pytest.raises(HTTPException) as exc:
        save_project_bdi_exato("proj-1", _request(declaracao, confirmado_por), x_user="ana", service=service)
    assert exc.value.status_code == 422 and needle in exc.value.detail
    assert project.files == {} and not audit.log.called


def test_float_only_and_unknown_profile_are_visible() -> None:
    project = FakeProject(contexto_id=None)
    project.write_json(LEGACY_HEAD, {"versao": 1, "lucro": {"mao_obra": 0.08}})
    service, _audit = _service(project)
    status = get_project_bdi_exato("proj-1", service=service)
    assert status["estado"] == "SOMENTE_LEGADO" and status["preco_exato_bloqueado"] is True
    # Re-saving in exact form is the way out, even when the profile cannot be resolved (structural check).
    saved = save_project_bdi_exato("proj-1", _request(), x_user="ana", service=service)
    assert saved["status"]["estado"] == "EXATO" and "contexto_id" in saved["status"]["camadas_motivo"]
    assert LEGACY_HEAD in project.files  # the float profile is left as it was


def test_routes_map_missing_project_and_store_errors() -> None:
    service = MagicMock()
    service.get_project_bdi_exato.side_effect = FileNotFoundError("nope")
    with pytest.raises(HTTPException) as exc:
        get_project_bdi_exato("x", service=service)
    assert exc.value.status_code == 404
    service.save_project_bdi_exato.side_effect = FileNotFoundError("nope")
    with pytest.raises(HTTPException) as exc:
        save_project_bdi_exato("x", _request(), x_user="ana", service=service)
    assert exc.value.status_code == 404
    service.save_project_bdi_exato.side_effect = ProjectBdiExactError("damaged head; it is not overwritten")
    with pytest.raises(HTTPException) as exc:
        save_project_bdi_exato("x", _request(), x_user="ana", service=service)
    assert exc.value.status_code == 422 and "not overwritten" in exc.value.detail
