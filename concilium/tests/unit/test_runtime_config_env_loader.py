"""Testa carregamento de config runtime via env vars — settings.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _reload_settings(monkeypatch):
    """Invalida singletons de settings para forçar releitura de env vars."""
    from concilium.infrastructure import settings

    settings._reset_all()
    return settings


def test_runtime_config_loads_from_json_file(monkeypatch, tmp_path):
    cfg_file = tmp_path / "runtime.json"
    cfg_file.write_text(json.dumps({}))
    monkeypatch.setenv("CONCILIUM__RUNTIME_CONFIG_FILE", str(cfg_file))
    mod = _reload_settings(monkeypatch)
    st = mod.get_storage()
    assert st.runtime_config_file == cfg_file


def test_runtime_config_env_override_has_precedence(monkeypatch, tmp_path):
    f1 = tmp_path / "base.json"
    f1.write_text("{}")
    monkeypatch.setenv("CONCILIUM__RUNTIME_CONFIG_FILE", str(f1))
    mod = _reload_settings(monkeypatch)
    assert mod.get_storage().runtime_config_file == f1

    f2 = tmp_path / "override.json"
    f2.write_text("{}")
    mod._reset_all()
    monkeypatch.setenv("CONCILIUM__RUNTIME_CONFIG_FILE", str(f2))
    assert mod.get_storage().runtime_config_file == f2


def test_runtime_config_file_legacy_alias_is_supported(monkeypatch, tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text("{}")
    monkeypatch.setenv("CONCILIUM__CONFIG_FILE", str(cfg_file))
    mod = _reload_settings(monkeypatch)
    st = mod.get_storage()
    assert st.config_file_legacy == cfg_file
