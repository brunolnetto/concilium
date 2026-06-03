from __future__ import annotations

from concilium.presentation.api import config as api_config
from concilium.presentation.ui import config as ui_config


def test_ui_api_base_url_prefers_ui_override(monkeypatch) -> None:
    monkeypatch.setenv("CONCILIUM__UI_API_BASE_URL", "http://ui-override:9000/")
    monkeypatch.setenv("CONCILIUM__API_BASE_URL", "http://shared-api:8000")
    monkeypatch.setenv("CONCILIUM__API_HOST", "host-ignored")
    monkeypatch.setenv("CONCILIUM__API_PORT", "9999")

    assert ui_config.resolve_api_base_url() == "http://ui-override:9000"


def test_ui_api_base_url_uses_shared_base_when_no_ui_override(monkeypatch) -> None:
    monkeypatch.delenv("CONCILIUM__UI_API_BASE_URL", raising=False)
    monkeypatch.setenv("CONCILIUM__API_BASE_URL", "http://shared-api:8100/")
    monkeypatch.setenv("CONCILIUM__API_HOST", "host-ignored")
    monkeypatch.setenv("CONCILIUM__API_PORT", "9999")

    assert ui_config.resolve_api_base_url() == "http://shared-api:8100"


def test_ui_api_base_url_uses_host_port_when_no_explicit_base(monkeypatch) -> None:
    monkeypatch.delenv("CONCILIUM__UI_API_BASE_URL", raising=False)
    monkeypatch.delenv("CONCILIUM__API_BASE_URL", raising=False)
    monkeypatch.setenv("CONCILIUM__API_HOST", "api-internal")
    monkeypatch.setenv("CONCILIUM__API_PORT", "8123")

    assert ui_config.resolve_api_base_url() == "http://api-internal:8123"


def test_ui_bind_port_invalid_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("CONCILIUM__UI_PORT", "invalid")

    assert ui_config.resolve_ui_bind_port() == 8501


def test_api_bind_reads_env_vars(monkeypatch) -> None:
    monkeypatch.setenv("CONCILIUM__API_HOST", "0.0.0.0")
    monkeypatch.setenv("CONCILIUM__API_PORT", "8088")

    assert api_config.resolve_api_bind() == ("0.0.0.0", 8088)


def test_api_bind_invalid_port_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("CONCILIUM__API_HOST", "127.0.0.1")
    monkeypatch.setenv("CONCILIUM__API_PORT", "invalid")

    assert api_config.resolve_api_bind() == ("127.0.0.1", 8000)


def test_api_bind_missing_host_falls_back(monkeypatch) -> None:
    monkeypatch.delenv("CONCILIUM__API_HOST", raising=False)
    monkeypatch.delenv("CONCILIUM__API_PORT", raising=False)

    assert api_config.resolve_api_bind() == ("127.0.0.1", 8000)
