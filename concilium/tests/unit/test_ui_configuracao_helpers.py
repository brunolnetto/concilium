from __future__ import annotations

import json

import pytest

streamlit = pytest.importorskip("streamlit", reason="streamlit nao instalado - pule este modulo de teste")

from concilium.presentation.ui.templates import _perfis_helpers_a as h_a
from concilium.presentation.ui.templates import _perfis_helpers_b as h_b
from concilium.presentation.ui.templates import _perfis_helpers_c as h_c


class _FakeTab:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeSt:
    def __init__(self):
        self.tab_labels: list[list[str]] = []
        self.expander_labels: list[str] = []

    def error(self, *_args, **_kwargs):
        return None

    def info(self, *_args, **_kwargs):
        return None

    def caption(self, *_args, **_kwargs):
        return None

    def dataframe(self, *_args, **_kwargs):
        return None

    def metric(self, *_args, **_kwargs):
        return None

    def columns(self, n):
        return [self for _ in range(n)]

    def selectbox(self, _label, options, key=None, format_func=None):
        return options[0]

    def tabs(self, labels):
        self.tab_labels.append(list(labels))
        return [_FakeTab() for _ in labels]

    def expander(self, label, expanded=False):
        self.expander_labels.append(label)
        return _FakeTab()


def test_format_diff_value_preserves_nested_json_readability() -> None:
    value = {"b": 2, "a": [1, 2]}
    out = h_a._format_diff_value(value)
    assert out == json.dumps(value, ensure_ascii=False, sort_keys=True)


def test_resolve_context_reference_statuses_marks_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = {
        "/api/catalogs": {"items": ["cat_v1"]},
        "/api/perfis": {"items": [{"id": "perfil_ok"}]},
        "/api/jurisdicoes": {"items": [{"id": "BR"}]},
        "/api/temas": {"items": [{"id": "tema_ok"}]},
    }

    def _fake_api_call(*, method, path, base_url, actor, payload=None, params=None):
        return responses.get(path, {"items": []})

    monkeypatch.setattr(h_b, "api_call", _fake_api_call)

    rows = h_b._resolve_context_reference_statuses(
        base_url="http://test",
        actor="tester",
        refs={
            "catalogo_id": "cat_v1",
            "perfil_id": "perfil_missing",
            "jurisdicao_id": "BR",
            "tema_id": "tema_ok",
        },
    )

    by_field = {row["Campo"]: row["Status"] for row in rows}
    assert by_field["catalogo_id"] == "ok"
    assert by_field["perfil_id"] == "nao encontrado"
    assert by_field["jurisdicao_id"] == "ok"
    assert by_field["tema_id"] == "ok"


def test_temas_section_uses_detail_tab_and_new_version_expander(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_st = _FakeSt()
    calls: list[str] = []

    def _fake_api_call(*, method, path, base_url, actor, payload=None, params=None):
        assert path == "/api/temas"
        return {
            "items": [
                {
                    "id": "tema-1",
                    "empresa": "Empresa",
                    "current_version": "v1",
                    "versions": [{"version": "v1"}],
                }
            ]
        }

    monkeypatch.setattr(h_b, "st", fake_st)
    monkeypatch.setattr(h_b, "api_call", _fake_api_call)
    monkeypatch.setattr(h_b, "_render_new_version_form", lambda **_kwargs: calls.append("new"))
    monkeypatch.setattr(h_b, "_render_version_history", lambda *_args, **_kwargs: calls.append("history"))
    monkeypatch.setattr(h_b, "_render_tema_editor", lambda *_args, **_kwargs: calls.append("edit"))
    monkeypatch.setattr(h_b, "_render_tema_detail", lambda *_args, **_kwargs: calls.append("detail"))

    h_b._render_temas_section(base_url="http://test", actor="tester")

    assert fake_st.expander_labels == ["➕ Nova versão"]
    assert fake_st.tab_labels[0] == ["🔍 Detalhe", "📜 Histórico", "✏️ Editar tema"]
    assert calls == ["new", "detail", "history", "edit"]


def test_jurisdicoes_section_uses_detail_tab_and_new_version_expander(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_st = _FakeSt()
    calls: list[str] = []

    def _fake_api_call(*, method, path, base_url, actor, payload=None, params=None):
        assert path == "/api/jurisdicoes"
        return {
            "items": [
                {
                    "id": "BR-SP",
                    "nome": "Sao Paulo",
                    "current_version": "v1",
                    "versions": [{"version": "v1"}],
                }
            ]
        }

    monkeypatch.setattr(h_c, "st", fake_st)
    monkeypatch.setattr(h_c, "api_call", _fake_api_call)
    monkeypatch.setattr(h_c, "_render_new_version_form", lambda **_kwargs: calls.append("new"))
    monkeypatch.setattr(h_c, "_render_version_history", lambda *_args, **_kwargs: calls.append("history"))
    monkeypatch.setattr(h_c, "_render_jurisdicao_editor", lambda *_args, **_kwargs: calls.append("edit"))
    monkeypatch.setattr(h_c, "_render_jurisdicao_detail", lambda *_args, **_kwargs: calls.append("detail"))

    h_c._render_jurisdicoes_section(base_url="http://test", actor="tester")

    assert fake_st.expander_labels == ["➕ Nova versão"]
    assert fake_st.tab_labels[0] == ["🔍 Detalhe", "📜 Histórico", "✏️ Editar overlay"]
    assert calls == ["new", "detail", "history", "edit"]
