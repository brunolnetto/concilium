"""Configuration discovery and management for Concilium.

Centralizes all tunable parameters, thresholds, and policy constants.
Eliminates hard-coded values scattered throughout the codebase.
"""

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
    def _load_config() -> None:
        """Load YAML configuration from config/concilium.yaml."""
        import yaml  # lazy: PyYAML leva ~220ms no cold import  # type: ignore[import-untyped]

        current = Path(__file__)
        project_root = current.parent.parent.parent
        config_path = project_root / "config" / "concilium.yaml"

        if not config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {config_path}\nExpected: {project_root}/config/concilium.yaml"
            )

        with open(config_path, encoding="utf-8") as f:
            ConfigurationManager._config = yaml.safe_load(f)

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
