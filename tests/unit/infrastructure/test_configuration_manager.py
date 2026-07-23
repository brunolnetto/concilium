"""Coverage batch 6 — config.py, insumo.py, and other infrastructure gaps."""

from __future__ import annotations

import pytest

# config.py lines 141, 159, 166: RuntimeError when _config is None
# config.py lines 177, 182, 187, 192, 197: convenience function calls
# ---------------------------------------------------------------------------


class TestConfigurationManagerNoneConfig:
    """Tests that force the singleton's _config to None to hit RuntimeError paths."""

    def test_get_raises_when_config_none(self):
        """Line 141: get() with _config=None → RuntimeError."""
        from concilium.infrastructure.config import ConfigurationManager

        inst = ConfigurationManager()
        original = inst._config
        try:
            inst._config = None
            with pytest.raises(RuntimeError, match="not loaded"):
                inst.get("some.key")
        finally:
            inst._config = original

    def test_get_section_raises_when_config_none(self):
        """Line 159: get_section() with _config=None → RuntimeError."""
        from concilium.infrastructure.config import ConfigurationManager

        inst = ConfigurationManager()
        original = inst._config
        try:
            inst._config = None
            with pytest.raises(RuntimeError, match="not loaded"):
                inst.get_section("progress")
        finally:
            inst._config = original

    def test_all_raises_when_config_none(self):
        """Line 166: all() with _config=None → RuntimeError."""
        from concilium.infrastructure.config import ConfigurationManager

        inst = ConfigurationManager()
        original = inst._config
        try:
            inst._config = None
            with pytest.raises(RuntimeError, match="not loaded"):
                inst.all()
        finally:
            inst._config = original


class TestConfigConvenienceFunctions:
    """Lines 177, 182, 187, 192, 197: convenience getters."""

    def test_get_progress_config(self):
        """Line 177: get_progress_config() returns dict."""
        from concilium.infrastructure.config import get_progress_config

        result = get_progress_config()
        assert isinstance(result, dict)

    def test_get_scheduling_config(self):
        """Line 182: get_scheduling_config() returns dict."""
        from concilium.infrastructure.config import get_scheduling_config

        result = get_scheduling_config()
        assert isinstance(result, dict)

    def test_get_replanning_config(self):
        """Line 187: get_replanning_config() returns dict."""
        from concilium.infrastructure.config import get_replanning_config

        result = get_replanning_config()
        assert isinstance(result, dict)

    def test_get_team_config(self):
        """Line 192: get_team_config() returns dict."""
        from concilium.infrastructure.config import get_team_config

        result = get_team_config()
        assert isinstance(result, dict)

    def test_get_productivity_config(self):
        """Line 197: get_productivity_config() returns dict."""
        from concilium.infrastructure.config import get_productivity_config

        result = get_productivity_config()
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------

