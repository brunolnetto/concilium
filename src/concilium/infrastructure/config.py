"""Configuration discovery and management for Concilium.

Centralizes all tunable parameters, thresholds, and policy constants.
Eliminates hard-coded values scattered throughout the codebase.
"""

import json
import os
import tomllib
from pathlib import Path
from typing import Any


class ConfigurationManager:
    """Singleton configuration manager."""

    _instance: "ConfigurationManager | None" = None
    _config: dict[str, Any] | None = None

    def __new__(cls) -> "ConfigurationManager":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize configuration (once)."""
        if self._config is None:
            self._load_config()

    @staticmethod
    def _project_root() -> Path:
        """Resolve project root with optional env override."""
        env_root = (os.environ.get("CONCILIUM_ROOT") or "").strip()
        if env_root:
            return Path(env_root).expanduser().resolve()
        return Path(__file__).resolve().parents[3]

    @staticmethod
    def _resolve_config_path(project_root: Path) -> Path:
        """Resolve runtime config file path with precedence by environment."""
        runtime_file = (os.environ.get("CONCILIUM_RUNTIME_CONFIG_FILE") or "").strip()
        if runtime_file:
            return Path(runtime_file).expanduser().resolve()

        legacy_file = (os.environ.get("CONCILIUM_CONFIG_FILE") or "").strip()
        if legacy_file:
            return Path(legacy_file).expanduser().resolve()

        config_root = (os.environ.get("CONCILIUM_CONFIG_ROOT") or "").strip()
        if config_root:
            return Path(config_root).expanduser().resolve() / "concilium.yaml"

        return project_root / "config" / "concilium.yaml"

    @staticmethod
    def _load_file(config_path: Path) -> dict[str, Any]:
        suffix = config_path.suffix.lower()
        if suffix == ".json":
            return json.loads(config_path.read_text(encoding="utf-8"))
        if suffix in {".toml", ".tml"}:
            with open(config_path, "rb") as f:
                return tomllib.load(f)
        if suffix in {".yaml", ".yml"}:
            import yaml  # lazy: PyYAML leva ~220ms no cold import  # type: ignore[import-untyped]

            with open(config_path, encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
            return loaded if isinstance(loaded, dict) else {}

        raise ValueError(
            f"Unsupported runtime config extension '{config_path.suffix}' in {config_path}. "
            "Use .yaml/.yml, .json or .toml."
        )

    @staticmethod
    def _coerce_env_value(raw: str) -> Any:
        value = raw.strip()
        if not value:
            return ""
        low = value.lower()
        if low in {"true", "false"}:
            return low == "true"
        if low in {"null", "none"}:
            return None
        try:
            if value.startswith(("{", "[", '"')) or value in {"0", "-0"} or value[0].isdigit() or value[0] == "-":
                return json.loads(value)
        except Exception:
            pass
        return value

    @staticmethod
    def _set_nested_value(config_data: dict[str, Any], dotted_path: str, value: Any) -> None:
        cursor = config_data
        keys = [k for k in dotted_path.split(".") if k]
        if not keys:
            return
        for key in keys[:-1]:
            current = cursor.get(key)
            if not isinstance(current, dict):
                cursor[key] = {}
            cursor = cursor[key]
        cursor[keys[-1]] = value

    @staticmethod
    def _apply_env_overrides(config_data: dict[str, Any]) -> dict[str, Any]:
        """Apply env overrides like CONCILIUM_CFG__progress__spi__ahead_threshold=1.1."""
        prefix = "CONCILIUM_CFG__"
        for env_key, raw_value in os.environ.items():
            if not env_key.startswith(prefix):
                continue
            path = env_key[len(prefix) :].strip("_").replace("__", ".").lower()
            if not path:
                continue
            ConfigurationManager._set_nested_value(config_data, path, ConfigurationManager._coerce_env_value(raw_value))
        return config_data

    @staticmethod
    def _load_config() -> None:
        """Load runtime configuration from YAML/JSON/TOML with optional env overrides."""
        project_root = ConfigurationManager._project_root()
        config_path = ConfigurationManager._resolve_config_path(project_root)

        if not config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {config_path}\n"
                "Configure CONCILIUM_RUNTIME_CONFIG_FILE or ensure config/concilium.yaml exists."
            )

        loaded = ConfigurationManager._load_file(config_path)
        if not isinstance(loaded, dict):
            raise ValueError(f"Invalid configuration root in {config_path}: expected mapping/dict.")
        ConfigurationManager._config = ConfigurationManager._apply_env_overrides(loaded)

    def get(self, key_path: str, default: Any = None) -> Any:
        """Get configuration value by dot-notation path.

        Examples:
            config.get("progress.spi.ahead_threshold")  # 1.05
            config.get("scheduling.algorithms.serial_prb.timeout_small")  # 30
            config.get("missing.key", default=100)  # 100
        """
        if self._config is None:
            raise RuntimeError("Configuration not loaded")

        keys = key_path.split(".")
        value = self._config

        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)  # type: ignore[assignment]
                if value is None:
                    return default
            else:
                return default

        return value if value is not None else default

    def get_section(self, section: str) -> dict[str, Any]:
        """Get entire configuration section."""
        if self._config is None:
            raise RuntimeError("Configuration not loaded")

        return self._config.get(section, {})

    def all(self) -> dict[str, Any]:
        """Return entire configuration."""
        if self._config is None:
            raise RuntimeError("Configuration not loaded")
        return self._config


# Global singleton instance
config = ConfigurationManager()


# Convenience functions for common lookups
def get_progress_config() -> dict[str, Any]:
    """Get progress tracking configuration (ADR-003)."""
    return config.get_section("progress")


def get_scheduling_config() -> dict[str, Any]:
    """Get scheduling configuration (ADR-004)."""
    return config.get_section("scheduling")


def get_replanning_config() -> dict[str, Any]:
    """Get replanning configuration (ADR-005)."""
    return config.get_section("replanning")


def get_team_config() -> dict[str, Any]:
    """Get team composition configuration (ADR-006)."""
    return config.get_section("team_composition")


def get_productivity_config() -> dict[str, Any]:
    """Get productivity configuration (ADR-007)."""
    return config.get_section("productivity")
