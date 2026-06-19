"""Tests for ConfigurationManager (infrastructure/config.py) and FastAPI deps (presentation/api/deps.py)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_singleton() -> None:
    """Reset ConfigurationManager singleton so each test starts clean."""
    from concilium.infrastructure import config as cfg_module

    cfg_module.ConfigurationManager._instance = None
    cfg_module.ConfigurationManager._config = None


def _make_mock_storage(root: Path, runtime_config_file: Path | None = None) -> MagicMock:
    st = MagicMock()
    st.root = root
    st.runtime_config_file = runtime_config_file
    return st


# ---------------------------------------------------------------------------
# Part 1 — ConfigurationManager
# ---------------------------------------------------------------------------


class TestCoerceEnvValue:
    """Static method _coerce_env_value — no singleton involved."""

    def setup_method(self):
        from concilium.infrastructure.config import ConfigurationManager

        self.coerce = ConfigurationManager._coerce_env_value

    def test_empty_string_returns_empty_string(self):
        assert self.coerce("") == ""

    def test_whitespace_only_returns_empty_string(self):
        assert self.coerce("   ") == ""

    def test_true_returns_bool_true(self):
        assert self.coerce("true") is True
        assert self.coerce("TRUE") is True
        assert self.coerce("True") is True

    def test_false_returns_bool_false(self):
        assert self.coerce("false") is False
        assert self.coerce("FALSE") is False

    def test_null_returns_none(self):
        assert self.coerce("null") is None
        assert self.coerce("NULL") is None

    def test_none_returns_none(self):
        assert self.coerce("none") is None
        assert self.coerce("None") is None

    def test_valid_json_dict(self):
        result = self.coerce('{"a": 1}')
        assert result == {"a": 1}

    def test_valid_json_list(self):
        result = self.coerce("[1, 2, 3]")
        assert result == [1, 2, 3]

    def test_valid_json_number(self):
        assert self.coerce("42") == 42
        assert self.coerce("3.14") == pytest.approx(3.14)

    def test_negative_number(self):
        assert self.coerce("-7") == -7

    def test_zero(self):
        assert self.coerce("0") == 0

    def test_plain_string(self):
        assert self.coerce("hello") == "hello"
        assert self.coerce("  hello  ") == "hello"

    def test_string_that_looks_like_broken_json(self):
        # Starts with '{' but is invalid JSON — should fall back to plain string
        result = self.coerce("{broken")
        assert result == "{broken"


class TestSetNestedValue:
    """Static method _set_nested_value — no singleton involved."""

    def setup_method(self):
        from concilium.infrastructure.config import ConfigurationManager

        self.setter = ConfigurationManager._set_nested_value

    def test_single_key(self):
        d: dict[str, Any] = {}
        self.setter(d, "key", "value")
        assert d == {"key": "value"}

    def test_nested_path(self):
        d: dict[str, Any] = {}
        self.setter(d, "a.b.c", 99)
        assert d == {"a": {"b": {"c": 99}}}

    def test_empty_path_is_noop(self):
        d: dict[str, Any] = {"x": 1}
        self.setter(d, "", "irrelevant")
        assert d == {"x": 1}

    def test_path_of_only_dots_is_noop(self):
        d: dict[str, Any] = {"x": 1}
        self.setter(d, "...", "irrelevant")
        assert d == {"x": 1}

    def test_overwrites_non_dict_intermediate(self):
        d: dict[str, Any] = {"a": "not_a_dict"}
        self.setter(d, "a.b", "new")
        assert d == {"a": {"b": "new"}}

    def test_overwrites_existing_leaf(self):
        d: dict[str, Any] = {"a": {"b": 1}}
        self.setter(d, "a.b", 2)
        assert d == {"a": {"b": 2}}


class TestLoadFile:
    """Static method _load_file — uses tmp_path, no singleton involved."""

    def setup_method(self):
        from concilium.infrastructure.config import ConfigurationManager

        self.loader = ConfigurationManager._load_file

    def test_json_file(self, tmp_path):
        p = tmp_path / "config.json"
        p.write_text(json.dumps({"foo": "bar", "num": 1}), encoding="utf-8")
        result = self.loader(p)
        assert result == {"foo": "bar", "num": 1}

    def test_toml_file(self, tmp_path):
        p = tmp_path / "config.toml"
        p.write_bytes(b'[section]\nkey = "value"\n')
        result = self.loader(p)
        assert result == {"section": {"key": "value"}}

    def test_yaml_file(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text("section:\n  key: value\n", encoding="utf-8")
        result = self.loader(p)
        assert result == {"section": {"key": "value"}}

    def test_yml_extension(self, tmp_path):
        p = tmp_path / "config.yml"
        p.write_text("x: 1\n", encoding="utf-8")
        result = self.loader(p)
        assert result == {"x": 1}

    def test_yaml_non_dict_returns_empty(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text("- item1\n- item2\n", encoding="utf-8")
        result = self.loader(p)
        assert result == {}

    def test_unsupported_extension_raises_value_error(self, tmp_path):
        p = tmp_path / "config.txt"
        p.write_text("key=value\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported runtime config extension"):
            self.loader(p)


class TestApplyEnvOverrides:
    """Static method _apply_env_overrides — patches os.environ."""

    def setup_method(self):
        from concilium.infrastructure.config import ConfigurationManager

        self.apply = ConfigurationManager._apply_env_overrides

    def test_applies_override_from_env(self):
        cfg: dict[str, Any] = {}
        with patch.dict("os.environ", {"CONCILIUM_CFG__section__key": "42"}):
            result = self.apply(cfg)
        assert result == {"section": {"key": 42}}

    def test_multiple_overrides(self):
        cfg: dict[str, Any] = {"existing": 1}
        env = {
            "CONCILIUM_CFG__a__b": "true",
            "CONCILIUM_CFG__a__c": "hello",
        }
        with patch.dict("os.environ", env):
            result = self.apply(cfg)
        assert result["a"]["b"] is True
        assert result["a"]["c"] == "hello"
        assert result["existing"] == 1

    def test_ignores_unrelated_env_vars(self):
        cfg: dict[str, Any] = {}
        with patch.dict("os.environ", {"SOME_OTHER_VAR": "xyz"}, clear=False):
            result = self.apply(cfg)
        assert "some_other_var" not in result

    def test_prefix_without_path_is_ignored(self):
        cfg: dict[str, Any] = {}
        # Key is exactly the prefix — path portion is empty after stripping
        with patch.dict("os.environ", {"CONCILIUM_CFG__": "oops"}):
            result = self.apply(cfg)
        assert result == {}


class TestResolveConfigPath:
    """Static method _resolve_config_path."""

    def setup_method(self):
        from concilium.infrastructure.config import ConfigurationManager

        self.resolve = ConfigurationManager._resolve_config_path

    def test_uses_runtime_config_file_when_set(self, tmp_path):
        runtime_file = tmp_path / "custom.yaml"
        mock_st = _make_mock_storage(tmp_path, runtime_config_file=runtime_file)
        with patch("concilium.infrastructure.config.get_storage", return_value=mock_st):
            result = self.resolve(tmp_path)
        assert result == runtime_file.resolve()

    def test_uses_concilium_config_root_env_var(self, tmp_path):
        mock_st = _make_mock_storage(tmp_path, runtime_config_file=None)
        with patch("concilium.infrastructure.config.get_storage", return_value=mock_st):
            with patch.dict("os.environ", {"CONCILIUM_CONFIG_ROOT": str(tmp_path)}):
                result = self.resolve(tmp_path)
        assert result == (tmp_path / "concilium.yaml").resolve()

    def test_default_fallback(self, tmp_path):
        mock_st = _make_mock_storage(tmp_path, runtime_config_file=None)
        with patch("concilium.infrastructure.config.get_storage", return_value=mock_st):
            with patch.dict("os.environ", {}, clear=False):
                # Remove CONCILIUM_CONFIG_ROOT if set in real env
                env_patch = {k: v for k, v in __import__("os").environ.items() if k != "CONCILIUM_CONFIG_ROOT"}
                with patch.dict("os.environ", env_patch, clear=True):
                    result = self.resolve(tmp_path)
        assert result == tmp_path / "config" / "concilium.yaml"


class TestConfigurationManagerFull:
    """Integration-level tests for __init__, get(), get_section(), all()."""

    def setup_method(self):
        _reset_singleton()

    def teardown_method(self):
        _reset_singleton()

    def _make_manager_with_json(self, tmp_path: Path, data: dict) -> Any:
        cfg_file = tmp_path / "concilium.json"
        cfg_file.write_text(json.dumps(data), encoding="utf-8")
        mock_st = _make_mock_storage(tmp_path, runtime_config_file=cfg_file)
        with patch("concilium.infrastructure.config.get_storage", return_value=mock_st):
            from concilium.infrastructure.config import ConfigurationManager

            return ConfigurationManager()

    def test_get_top_level_key(self, tmp_path):
        mgr = self._make_manager_with_json(tmp_path, {"timeout": 30})
        assert mgr.get("timeout") == 30

    def test_get_nested_key(self, tmp_path):
        mgr = self._make_manager_with_json(tmp_path, {"scheduling": {"timeout": 60}})
        assert mgr.get("scheduling.timeout") == 60

    def test_get_missing_key_returns_default(self, tmp_path):
        mgr = self._make_manager_with_json(tmp_path, {"existing": 1})
        assert mgr.get("missing.key", default=99) == 99
        assert mgr.get("missing.key") is None

    def test_get_intermediate_not_dict_returns_default(self, tmp_path):
        mgr = self._make_manager_with_json(tmp_path, {"a": "string_not_dict"})
        assert mgr.get("a.b", default="fallback") == "fallback"

    def test_get_section_known(self, tmp_path):
        mgr = self._make_manager_with_json(tmp_path, {"progress": {"spi": 1.05}})
        assert mgr.get_section("progress") == {"spi": 1.05}

    def test_get_section_unknown_returns_empty_dict(self, tmp_path):
        mgr = self._make_manager_with_json(tmp_path, {"progress": {}})
        assert mgr.get_section("nonexistent") == {}

    def test_all_returns_full_config(self, tmp_path):
        data = {"a": 1, "b": {"c": 2}}
        mgr = self._make_manager_with_json(tmp_path, data)
        assert mgr.all() == data

    def test_singleton_returns_same_instance(self, tmp_path):
        cfg_file = tmp_path / "concilium.json"
        cfg_file.write_text(json.dumps({"x": 1}), encoding="utf-8")
        mock_st = _make_mock_storage(tmp_path, runtime_config_file=cfg_file)
        with patch("concilium.infrastructure.config.get_storage", return_value=mock_st):
            from concilium.infrastructure.config import ConfigurationManager

            a = ConfigurationManager()
            b = ConfigurationManager()
        assert a is b

    def test_file_not_found_raises(self, tmp_path):
        missing_file = tmp_path / "does_not_exist.yaml"
        mock_st = _make_mock_storage(tmp_path, runtime_config_file=missing_file)
        with patch("concilium.infrastructure.config.get_storage", return_value=mock_st):
            from concilium.infrastructure.config import ConfigurationManager

            with pytest.raises(FileNotFoundError, match="Configuration file not found"):
                ConfigurationManager()

    def test_non_dict_config_root_raises(self, tmp_path):
        cfg_file = tmp_path / "concilium.json"
        # JSON array at root — not a dict
        cfg_file.write_text("[1, 2, 3]", encoding="utf-8")
        mock_st = _make_mock_storage(tmp_path, runtime_config_file=cfg_file)
        with patch("concilium.infrastructure.config.get_storage", return_value=mock_st):
            from concilium.infrastructure.config import ConfigurationManager

            with pytest.raises(ValueError, match="Invalid configuration root"):
                ConfigurationManager()


# ---------------------------------------------------------------------------
# Part 2 — FastAPI deps
# ---------------------------------------------------------------------------


class TestGetCurrentClaims:
    def test_returns_claims_when_jwt_claims_present(self):
        from concilium.presentation.api.deps import get_current_claims

        request = MagicMock()
        request.state.jwt_claims = {"sub": "client-1", "roles": ["admin"]}
        result = get_current_claims(request)
        assert result == {"sub": "client-1", "roles": ["admin"]}

    def test_returns_empty_dict_when_jwt_claims_absent(self):
        from concilium.presentation.api.deps import get_current_claims

        request = MagicMock(spec=["state"])
        # state is a plain object without jwt_claims attribute
        request.state = MagicMock(spec=[])
        result = get_current_claims(request)
        assert result == {}

    def test_returns_empty_dict_when_state_has_no_jwt_claims_attr(self):
        from concilium.presentation.api.deps import get_current_claims

        request = MagicMock()
        # Delete jwt_claims so getattr falls back to default
        del request.state.jwt_claims
        result = get_current_claims(request)
        assert result == {}


class TestGetCurrentSubject:
    def test_returns_sub_when_present(self):
        from concilium.presentation.api.deps import get_current_subject

        request = MagicMock()
        request.state.jwt_claims = {"sub": "client-42"}
        result = get_current_subject(request)
        assert result == "client-42"

    def test_returns_none_when_sub_missing(self):
        from concilium.presentation.api.deps import get_current_subject

        request = MagicMock()
        request.state.jwt_claims = {"roles": ["reader"]}
        result = get_current_subject(request)
        assert result is None

    def test_returns_none_when_no_claims(self):
        from concilium.presentation.api.deps import get_current_subject

        request = MagicMock(spec=["state"])
        request.state = MagicMock(spec=[])
        result = get_current_subject(request)
        assert result is None
