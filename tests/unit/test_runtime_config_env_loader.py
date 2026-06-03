from __future__ import annotations

import importlib
import json
from pathlib import Path


def _reload_config_module():
    module = importlib.import_module("concilium.infrastructure.config")
    return importlib.reload(module)


def test_runtime_config_loads_from_json_file(monkeypatch, tmp_path: Path) -> None:
    cfg_path = tmp_path / "runtime_config.json"
    cfg_path.write_text(
        json.dumps({"progress": {"spi": {"ahead_threshold": 1.05}}}),
        encoding="utf-8",
    )

    monkeypatch.setenv("CONCILIUM_RUNTIME_CONFIG_FILE", str(cfg_path))
    monkeypatch.delenv("CONCILIUM_CFG__progress__spi__ahead_threshold", raising=False)

    mod = _reload_config_module()

    assert mod.config.get("progress.spi.ahead_threshold") == 1.05


def test_runtime_config_env_override_has_precedence(monkeypatch, tmp_path: Path) -> None:
    cfg_path = tmp_path / "runtime_config.json"
    cfg_path.write_text(
        json.dumps({"progress": {"spi": {"ahead_threshold": 1.01}}}),
        encoding="utf-8",
    )

    monkeypatch.setenv("CONCILIUM_RUNTIME_CONFIG_FILE", str(cfg_path))
    monkeypatch.setenv("CONCILIUM_CFG__progress__spi__ahead_threshold", "1.2")

    mod = _reload_config_module()

    assert mod.config.get("progress.spi.ahead_threshold") == 1.2


def test_runtime_config_file_legacy_alias_is_supported(monkeypatch, tmp_path: Path) -> None:
    cfg_path = tmp_path / "runtime_config.json"
    cfg_path.write_text(
        json.dumps({"team_composition": {"default_num_equipes": 2}}),
        encoding="utf-8",
    )

    monkeypatch.delenv("CONCILIUM_RUNTIME_CONFIG_FILE", raising=False)
    monkeypatch.setenv("CONCILIUM_CONFIG_FILE", str(cfg_path))

    mod = _reload_config_module()

    assert mod.config.get("team_composition.default_num_equipes") == 2
