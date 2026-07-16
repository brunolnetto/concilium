"""Tests for CatalogDigestSettings (ADR-141 F1)."""

from __future__ import annotations

import pytest


class TestCatalogDigestSettingsDefaults:
    def test_defaults_when_no_env_vars(self, monkeypatch: pytest.MonkeyPatch):
        from concilium.infrastructure.settings._catalog_digest import CatalogDigestSettings

        monkeypatch.delenv("CONCILIUM__CATALOG_DIGEST_ENABLED", raising=False)
        monkeypatch.delenv("CONCILIUM__CATALOG_DIGEST_INTERVAL_HOURS", raising=False)

        settings = CatalogDigestSettings.from_env()

        assert settings.enabled is False
        assert settings.interval_hours == 24


class TestCatalogDigestSettingsOverrides:
    def test_enabled_flag_true(self, monkeypatch: pytest.MonkeyPatch):
        from concilium.infrastructure.settings._catalog_digest import CatalogDigestSettings

        monkeypatch.setenv("CONCILIUM__CATALOG_DIGEST_ENABLED", "1")
        settings = CatalogDigestSettings.from_env()
        assert settings.enabled is True

    def test_custom_interval(self, monkeypatch: pytest.MonkeyPatch):
        from concilium.infrastructure.settings._catalog_digest import CatalogDigestSettings

        monkeypatch.setenv("CONCILIUM__CATALOG_DIGEST_INTERVAL_HOURS", "6")
        settings = CatalogDigestSettings.from_env()
        assert settings.interval_hours == 6


class TestGetCatalogDigestSingleton:
    def test_returns_same_instance(self):
        from concilium.infrastructure.settings._catalog_digest import get_catalog_digest

        a = get_catalog_digest()
        b = get_catalog_digest()
        assert a is b

    def test_exported_from_settings_package(self):
        from concilium.infrastructure.settings import CatalogDigestSettings, get_catalog_digest

        assert get_catalog_digest() is not None
        assert isinstance(get_catalog_digest(), CatalogDigestSettings)
