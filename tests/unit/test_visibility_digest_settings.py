"""Tests for VisibilityDigestSettings (ADR-143 F1)."""

from __future__ import annotations

import pytest


class TestVisibilityDigestSettingsDefaults:
    def test_defaults_when_no_env_vars(self, monkeypatch: pytest.MonkeyPatch):
        from concilium.infrastructure.settings._visibility_digest import VisibilityDigestSettings

        monkeypatch.delenv("CONCILIUM__VISIBILITY_DIGEST_ENABLED", raising=False)
        monkeypatch.delenv("CONCILIUM__VISIBILITY_DIGEST_INTERVAL_SECONDS", raising=False)

        settings = VisibilityDigestSettings.from_env()

        assert settings.enabled is False
        assert settings.interval_seconds == 300


class TestVisibilityDigestSettingsOverrides:
    def test_enabled_flag_true(self, monkeypatch: pytest.MonkeyPatch):
        from concilium.infrastructure.settings._visibility_digest import VisibilityDigestSettings

        monkeypatch.setenv("CONCILIUM__VISIBILITY_DIGEST_ENABLED", "1")
        settings = VisibilityDigestSettings.from_env()
        assert settings.enabled is True

    def test_custom_interval(self, monkeypatch: pytest.MonkeyPatch):
        from concilium.infrastructure.settings._visibility_digest import VisibilityDigestSettings

        monkeypatch.setenv("CONCILIUM__VISIBILITY_DIGEST_INTERVAL_SECONDS", "900")
        settings = VisibilityDigestSettings.from_env()
        assert settings.interval_seconds == 900


class TestGetVisibilityDigestSingleton:
    def test_returns_same_instance(self):
        from concilium.infrastructure.settings._visibility_digest import (
            _reset_visibility_digest,
            get_visibility_digest,
        )

        _reset_visibility_digest()
        try:
            a = get_visibility_digest()
            b = get_visibility_digest()
            assert a is b
        finally:
            _reset_visibility_digest()

    def test_exported_from_settings_package(self):
        from concilium.infrastructure.settings import VisibilityDigestSettings, get_visibility_digest

        assert get_visibility_digest() is not None
        assert isinstance(get_visibility_digest(), VisibilityDigestSettings)
