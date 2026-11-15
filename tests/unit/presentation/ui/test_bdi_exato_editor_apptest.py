"""N9.1 (#206): the exact BDI editor rendered headless with Streamlit's AppTest (no browser, API stubbed)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest  # noqa: E402

from concilium.application.scheduling.project_bdi_exact_status import (  # noqa: E402
    exact_project_bdi_status,
    profile_rows_for_validation,
)
from concilium.application.scheduling.project_bdi_exact_store import (  # noqa: E402
    LEGACY_HEAD,
    ProjectBdiExactError,
    save_exact_project_bdi,
)

# Imported here so that the (slow, package-wide) first import is not charged to an AppTest script run.
from concilium.presentation.ui.organisms.layout import _bdi_exato_editor  # noqa: E402, F401

# Each script run takes several seconds: per the repo marker convention this is `slow`
# (CI's `-m "not slow"` skips it; the logic is covered fast in test_bdi_exato_helpers.py).
pytestmark = pytest.mark.slow

ROOT = Path(__file__).resolve().parents[4]
PROFILE = json.loads((ROOT / "config/perfis/mendeslobo.json").read_text(encoding="utf-8"))
_API = "concilium.presentation.ui.organisms.layout._bdi_exato_editor.api_call"


class FakeProject:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    def exists(self, relative_path: str) -> bool:
        return relative_path in self.files

    def read_json(self, relative_path: str, default: Any) -> Any:
        try:
            return json.loads(self.files[relative_path])
        except (KeyError, json.JSONDecodeError):
            return default

    def write_json(self, relative_path: str, payload: Any) -> None:
        self.files[relative_path] = json.dumps(payload, ensure_ascii=False)


def _fake_api(project: FakeProject, calls: list[dict]):
    """The two /bdi-exato routes backed by the real store and status code."""

    def api_call(method: str, path: str, base_url: str = "", payload: dict | None = None, **_kwargs: Any) -> dict:
        assert path == "/api/projects/p1/bdi-exato"
        if method == "POST":
            calls.append(payload or {})
            try:
                saved = save_exact_project_bdi(
                    project,
                    "p1",
                    payload["declaracao"],
                    confirmado_por=payload["confirmado_por"],
                    motivo_revisao=payload["motivo_revisao"],
                    profile_rows=profile_rows_for_validation(PROFILE),
                )
            except ProjectBdiExactError as exc:
                raise RuntimeError(f"HTTP 422: {exc}") from exc
            return {"salvo": {"versao": saved["versao"], "content_hash": saved["content_hash"]}}
        return exact_project_bdi_status(project, PROFILE, perfil_id="mendeslobo")

    return api_call


def _app() -> None:
    from concilium.presentation.ui.organisms.layout._bdi_exato_editor import render_bdi_exato

    render_bdi_exato("http://api", "p1", "ana")


def _run(monkeypatch, project: FakeProject, calls: list[dict]) -> AppTest:
    monkeypatch.setattr(_API, _fake_api(project, calls))
    at = AppTest.from_function(_app, default_timeout=180)
    at.run()
    assert not at.exception, at.exception
    return at


def _text(elements) -> str:
    return "\n".join(str(element.value) for element in elements)


def test_float_only_project_shows_the_blocking_banner_and_can_be_resaved_exactly(monkeypatch) -> None:
    project, calls = FakeProject(), []
    project.write_json(LEGACY_HEAD, {"versao": 1, "lucro": {"mao_obra": 0.08}})
    at = _run(monkeypatch, project, calls)
    assert "SOMENTE_LEGADO" in _text(at.error) and "PREÇO EXATO NÃO AVALIADO" in _text(at.error)
    assert not at.get("number_input") and not at.get("slider")

    at.text_input(key="bdi-exato-fonte-p1").input("ISS 2% — lei municipal")
    at.text_input(key="bdi-exato-p1-mao_obra-l").input("0.08")
    at.selectbox(key="bdi-exato-p1-mao_obra-iss-modo").select("aplicavel")
    at.text_input(key="bdi-exato-p1-mao_obra-iss-aliquota").input("1/50")
    at.button[0].click().run()
    assert not at.exception, at.exception
    assert calls == [
        {
            "declaracao": {
                "schema": "concilium.projeto.bdi-exato.v1",
                "fonte": "ISS 2% — lei municipal",
                "linhas": {"mao_obra": {"l": "0.08", "tributos": {"iss": {"aplicavel": True, "aliquota": "1/50"}}}},
            },
            "confirmado_por": "ana",
            "motivo_revisao": None,
        }
    ]
    assert "EXATO — " in _text(at.success) and "Declaração exata v1 salva" in _text(at.success)
    assert not at.error


def test_invalid_input_is_refused_in_the_page_with_the_reason_and_nothing_is_posted(monkeypatch) -> None:
    project, calls = FakeProject(), []
    at = _run(monkeypatch, project, calls)
    assert "NENHUM — " in _text(at.info)
    at.text_input(key="bdi-exato-fonte-p1").input("negociação")
    at.text_input(key="bdi-exato-p1-material-l").input("3,5%")
    at.button[0].click().run()
    assert "Declaração exata inválida" in _text(at.error) and "linhas.material.l" in _text(at.error)
    assert calls == [] and project.files == {}


def test_revision_requires_motivo_and_server_refusal_is_shown(monkeypatch) -> None:
    project, calls = FakeProject(), []
    declaration = {
        "schema": "concilium.projeto.bdi-exato.v1",
        "fonte": "v1",
        "linhas": {"mao_obra": {"l": "0.08"}},
    }
    save_exact_project_bdi(project, "p1", declaration, confirmado_por="Eng", motivo_revisao=None)
    at = _run(monkeypatch, project, calls)
    assert "EXATO — " in _text(at.success)
    assert at.text_input(key="bdi-exato-p1-mao_obra-l").value == "0.08"
    at.button[0].click().run()
    assert "motivo_revisao é obrigatório" in _text(at.error) and calls == []

    # Structurally valid, but over the profile row the taxes reach 100%: only the server knows.
    at.text_input(key="bdi-exato-motivo-p1").input("ISS")
    at.selectbox(key="bdi-exato-p1-mao_obra-iss-modo").select("aplicavel")
    at.text_input(key="bdi-exato-p1-mao_obra-iss-aliquota").input("0.96")
    at.button[0].click().run()
    assert len(calls) == 1 and "Declaração exata não salva" in _text(at.error) and "below 100%" in _text(at.error)
    assert "bdi/perfil_bdi_exato_v002.json" not in project.files
