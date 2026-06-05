from __future__ import annotations

import pytest

streamlit = pytest.importorskip("streamlit", reason="streamlit nao instalado - pule este modulo de teste")

from concilium.presentation.ui.templates import _perfis_helpers_a as h_a
from concilium.presentation.ui.templates import perfis_contextos_page as page


class _FakeTab:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeStreamlit:
    def __init__(self):
        self.tab_labels: list[list[str]] = []

    def expander(self, *_args, **_kwargs):
        return _FakeTab()

    def error(self, *_args, **_kwargs):
        return None

    def info(self, *_args, **_kwargs):
        return None

    def selectbox(self, _label, options, key=None, format_func=None):
        return options[0]

    def tabs(self, labels):
        self.tab_labels.append(list(labels))
        return [_FakeTab() for _ in labels]


def test_context_tabs_render_detail_first_and_call_order(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_st = _FakeStreamlit()
    calls: list[str] = []

    def _fake_api_call(*, method, path, base_url, actor, payload=None, params=None):
        assert path == "/api/contextos"
        return {
            "items": [
                {
                    "id": "ctx-1",
                    "nome": "Contexto 1",
                    "current_version": "v2",
                    "versions": [{"version": "v1"}, {"version": "v2"}],
                }
            ]
        }

    monkeypatch.setattr(h_a, "st", fake_st)
    monkeypatch.setattr(h_a, "api_call", _fake_api_call)
    monkeypatch.setattr(h_a, "_render_version_history", lambda *_args, **_kwargs: calls.append("history"))
    monkeypatch.setattr(h_a, "_render_version_compare", lambda *_args, **_kwargs: calls.append("compare"))
    monkeypatch.setattr(h_a, "_render_new_version_form", lambda *_args, **_kwargs: calls.append("new"))

    def _extra(*_args, **_kwargs):
        calls.append("detail")

    h_a._render_entity_section(
        base_url="http://test",
        actor="tester",
        list_path="/api/contextos",
        versions_path_tpl="/api/contextos/{id}/versions",
        compare_path="/api/contextos/compare",
        entity_label="Contexto",
        key_prefix="ctx",
        extra_renderer=_extra,
    )

    assert fake_st.tab_labels[0] == ["🔍 Detalhe", "📜 Histórico", "🔀 Comparar versões"]
    assert calls == ["new", "detail", "history", "compare"]


def test_config_page_wires_contexto_detail_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    monkeypatch.setattr(page, "render_page_heading", lambda *_args, **_kwargs: None)

    class _FakePageSt:
        def tabs(self, _labels):
            return [_FakeTab(), _FakeTab(), _FakeTab(), _FakeTab()]

        def divider(self):
            return None

    monkeypatch.setattr(page, "st", _FakePageSt())
    monkeypatch.setattr(page, "_render_jurisdicoes_section", lambda **_kwargs: None)
    monkeypatch.setattr(page, "_render_temas_section", lambda **_kwargs: None)

    def _fake_render_entity_section(**kwargs):
        if kwargs.get("key_prefix") == "ctx":
            captured.update(kwargs)

    monkeypatch.setattr(page, "_render_entity_section", _fake_render_entity_section)

    page.render_configuracao_page()

    assert captured.get("key_prefix") == "ctx"
    assert captured.get("extra_renderer") is page._render_contexto_detail
