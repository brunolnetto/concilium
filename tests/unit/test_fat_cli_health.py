"""Tests for concilium.presentation.cli.commands_health — covers missing lines.

Covers:
- _hc_check_catalogo_health: success path (ok + erros) and exception path
- _hc_check_catalogs: no-op paths (empty list, missing dir), runtime error, success
- _hc_check_sharepoint: no drive id, success ok, success with message, ImportError, generic exception
- health(): all_ok path, degraded path, missing dirs, SkillRegistry error, no contexts
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import typer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_cce(monkeypatch, return_value):
    """Patch collect_catalog_critical_errors at its source module."""
    import concilium.application.orchestrators.catalog_governance as cg_mod

    monkeypatch.setattr(cg_mod, "collect_catalog_critical_errors", lambda c: return_value)


def _patch_runtime(monkeypatch, runtime_instance=None, side_effect=None):
    import concilium.application.runtime as runtime_mod

    if side_effect is not None:
        monkeypatch.setattr(runtime_mod, "Runtime", MagicMock(side_effect=side_effect))
    else:
        monkeypatch.setattr(runtime_mod, "Runtime", MagicMock(return_value=runtime_instance))


def _patch_skill_registry(monkeypatch, registry_instance=None, side_effect=None):
    import concilium.application.skills.registry as reg_mod

    if side_effect is not None:
        monkeypatch.setattr(reg_mod, "SkillRegistry", MagicMock(side_effect=side_effect))
    else:
        monkeypatch.setattr(reg_mod, "SkillRegistry", MagicMock(return_value=registry_instance))


def _patch_get_storage(monkeypatch, drive_id=""):
    import concilium.infrastructure.settings as settings_mod

    storage_mock = MagicMock()
    storage_mock.sharepoint.drive_id = drive_id
    monkeypatch.setattr(settings_mod, "get_storage", lambda: storage_mock)
    return storage_mock


def _patch_shared(monkeypatch, config_dir: Path, proj_dir: Path):
    import concilium.presentation.cli.shared as shared_mod

    monkeypatch.setattr(shared_mod, "_config_root", lambda: config_dir)
    monkeypatch.setattr(shared_mod, "_projetos_root", lambda: proj_dir)


def _make_rt_mock(catalogo=None):
    rt = MagicMock()
    ctx = MagicMock()
    ctx.catalogo_id = "cat-default"
    rt.load_contexto.return_value = ctx
    rt.load_catalogo.return_value = catalogo or {"cpus": []}
    return rt


# ---------------------------------------------------------------------------
# _hc_check_catalogo_health
# ---------------------------------------------------------------------------


class TestHcCheckCatalogoHealth:
    def _fn(self):
        from concilium.presentation.cli.commands_health import _hc_check_catalogo_health

        return _hc_check_catalogo_health

    def test_success_no_errors(self, monkeypatch):
        _patch_cce(monkeypatch, [])
        rt = _make_rt_mock({"cpus": ["cpu1", "cpu2"]})
        ctx = MagicMock()
        ctx.catalogo_id = "cat-abc"
        rt.load_contexto.return_value = ctx

        name, ok, detail = self._fn()(rt, "ctx-1")

        assert name == "Catálogo [ctx-1]"
        assert ok is True
        assert "2 CPUs" in detail
        assert "erro" not in detail

    def test_success_with_errors(self, monkeypatch):
        _patch_cce(monkeypatch, ["err1", "err2"])
        rt = _make_rt_mock({"cpus": ["a"]})

        name, ok, detail = self._fn()(rt, "ctx-2")

        assert name == "Catálogo [ctx-2]"
        assert ok is False
        assert "2 erro(s)" in detail
        assert "1 CPUs" in detail

    def test_exception_path(self, monkeypatch):
        _patch_cce(monkeypatch, [])
        rt = MagicMock()
        rt.load_contexto.side_effect = RuntimeError("boom")

        name, ok, detail = self._fn()(rt, "ctx-err")

        assert name == "Catálogo [ctx-err]"
        assert ok is False
        assert "boom" in detail

    def test_no_cpus_key(self, monkeypatch):
        _patch_cce(monkeypatch, [])
        rt = _make_rt_mock({})  # no 'cpus' key

        name, ok, detail = self._fn()(rt, "ctx-nokey")

        assert ok is True
        assert "0 CPUs" in detail

    def test_load_catalogo_exception(self, monkeypatch):
        _patch_cce(monkeypatch, [])
        rt = MagicMock()
        rt.load_contexto.return_value = MagicMock(catalogo_id="x")
        rt.load_catalogo.side_effect = FileNotFoundError("no such catalog")

        name, ok, detail = self._fn()(rt, "ctx-missing-cat")

        assert ok is False
        assert "no such catalog" in detail


# ---------------------------------------------------------------------------
# _hc_check_catalogs
# ---------------------------------------------------------------------------


class TestHcCheckCatalogs:
    def _fn(self):
        from concilium.presentation.cli.commands_health import _hc_check_catalogs

        return _hc_check_catalogs

    def test_noop_empty_contexto_ids(self, tmp_path):
        rows = []
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        self._fn()(rows, [], config_dir)
        assert rows == []

    def test_noop_missing_config_dir(self, tmp_path):
        rows = []
        config_dir = tmp_path / "nonexistent"
        self._fn()(rows, ["ctx-1"], config_dir)
        assert rows == []

    def test_runtime_exception(self, tmp_path, monkeypatch):
        _patch_runtime(monkeypatch, side_effect=RuntimeError("rt-fail"))
        rows = []
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        self._fn()(rows, ["ctx-1"], config_dir)

        assert len(rows) == 1
        name, ok, detail = rows[0]
        assert name == "Runtime"
        assert ok is False
        assert "rt-fail" in detail

    def test_success_single_context(self, tmp_path, monkeypatch):
        mock_rt = _make_rt_mock({"cpus": ["c1", "c2"]})
        ctx = MagicMock()
        ctx.catalogo_id = "cat-ok"
        mock_rt.load_contexto.return_value = ctx

        _patch_runtime(monkeypatch, runtime_instance=mock_rt)
        _patch_cce(monkeypatch, [])

        rows = []
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        self._fn()(rows, ["ctx-ok"], config_dir)

        assert len(rows) == 1
        name, ok, detail = rows[0]
        assert "ctx-ok" in name
        assert ok is True
        assert "2 CPUs" in detail

    def test_success_multiple_contexts(self, tmp_path, monkeypatch):
        mock_rt = _make_rt_mock({"cpus": []})
        _patch_runtime(monkeypatch, runtime_instance=mock_rt)
        _patch_cce(monkeypatch, [])

        rows = []
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        self._fn()(rows, ["ctx-a", "ctx-b"], config_dir)

        assert len(rows) == 2


# ---------------------------------------------------------------------------
# _hc_check_sharepoint
# ---------------------------------------------------------------------------


class TestHcCheckSharepoint:
    def _fn(self):
        from concilium.presentation.cli.commands_health import _hc_check_sharepoint

        return _hc_check_sharepoint

    def test_noop_when_no_drive_id(self, monkeypatch):
        _patch_get_storage(monkeypatch, drive_id="")
        rows = []
        self._fn()(rows)
        assert rows == []

    def test_noop_when_drive_id_none(self, monkeypatch):
        import concilium.infrastructure.settings as settings_mod

        storage_mock = MagicMock()
        storage_mock.sharepoint.drive_id = None
        monkeypatch.setattr(settings_mod, "get_storage", lambda: storage_mock)
        rows = []
        self._fn()(rows)
        assert rows == []

    def test_success_status_ok_with_drive_name(self, monkeypatch):
        _patch_get_storage(monkeypatch, drive_id="drv-123")

        sp_storage = MagicMock()
        sp_storage.health_check.return_value = {"status": "ok", "drive_name": "My Drive"}

        import concilium.infrastructure.adapters.blob_storage.sharepoint as sp_mod

        monkeypatch.setattr(sp_mod, "SharePointBlobStorage", MagicMock(**{"from_env.return_value": sp_storage}))

        rows = []
        self._fn()(rows)

        assert len(rows) == 1
        name, ok, detail = rows[0]
        assert name == "SharePoint conectividade"
        assert ok is True
        assert detail == "My Drive"

    def test_success_status_not_ok_uses_message(self, monkeypatch):
        _patch_get_storage(monkeypatch, drive_id="drv-x")

        sp_storage = MagicMock()
        sp_storage.health_check.return_value = {"status": "error", "message": "timeout"}

        import concilium.infrastructure.adapters.blob_storage.sharepoint as sp_mod

        monkeypatch.setattr(sp_mod, "SharePointBlobStorage", MagicMock(**{"from_env.return_value": sp_storage}))

        rows = []
        self._fn()(rows)

        name, ok, detail = rows[0]
        assert ok is False
        assert "timeout" in detail

    def test_success_empty_drive_name_falls_back_to_ok(self, monkeypatch):
        _patch_get_storage(monkeypatch, drive_id="drv-y")

        sp_storage = MagicMock()
        sp_storage.health_check.return_value = {"status": "ok", "drive_name": "", "message": ""}

        import concilium.infrastructure.adapters.blob_storage.sharepoint as sp_mod

        monkeypatch.setattr(sp_mod, "SharePointBlobStorage", MagicMock(**{"from_env.return_value": sp_storage}))

        rows = []
        self._fn()(rows)

        name, ok, detail = rows[0]
        assert ok is True
        assert detail == "ok"

    def test_import_error_path(self, monkeypatch):
        """Simulate ImportError when sharepoint module itself cannot be imported."""
        _patch_get_storage(monkeypatch, drive_id="drv-123")

        import sys

        # Remove the module from sys.modules so the lazy import inside the function
        # will re-execute the import machinery, and we can inject a broken module.
        original_mod = sys.modules.pop("concilium.infrastructure.adapters.blob_storage.sharepoint", None)
        # Insert a sentinel that raises ImportError when accessed
        monkeypatch.setitem(
            sys.modules,
            "concilium.infrastructure.adapters.blob_storage.sharepoint",
            None,  # None in sys.modules causes ImportError on 'from ... import'
        )

        try:
            rows = []
            self._fn()(rows)
        finally:
            # Restore the original module
            if original_mod is not None:
                sys.modules["concilium.infrastructure.adapters.blob_storage.sharepoint"] = original_mod
            else:
                sys.modules.pop("concilium.infrastructure.adapters.blob_storage.sharepoint", None)

        assert len(rows) == 1
        name, ok, detail = rows[0]
        assert ok is False
        assert "pip install" in detail

    def test_generic_exception_path(self, monkeypatch):
        _patch_get_storage(monkeypatch, drive_id="drv-123")

        sp_storage = MagicMock()
        sp_storage.health_check.side_effect = Exception("connection refused")

        import concilium.infrastructure.adapters.blob_storage.sharepoint as sp_mod

        monkeypatch.setattr(sp_mod, "SharePointBlobStorage", MagicMock(**{"from_env.return_value": sp_storage}))

        rows = []
        self._fn()(rows)

        name, ok, detail = rows[0]
        assert ok is False
        assert "connection refused" in detail

    def test_from_env_generic_exception(self, monkeypatch):
        _patch_get_storage(monkeypatch, drive_id="drv-123")

        import concilium.infrastructure.adapters.blob_storage.sharepoint as sp_mod

        sp_cls_mock = MagicMock()
        sp_cls_mock.from_env.side_effect = ConnectionError("network error")
        monkeypatch.setattr(sp_mod, "SharePointBlobStorage", sp_cls_mock)

        rows = []
        self._fn()(rows)

        name, ok, detail = rows[0]
        assert ok is False
        assert "network error" in detail


# ---------------------------------------------------------------------------
# health() — top-level command
# ---------------------------------------------------------------------------


class TestHealthCommand:
    """Tests for health() function covering all branches."""

    def _make_config_dir(self, tmp_path, *, with_contextos=False, with_catalogos=False):
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True)
        if with_contextos:
            (config_dir / "contextos").mkdir()
        if with_catalogos:
            (config_dir / "catalogos").mkdir()
        return config_dir

    def _setup_common(self, monkeypatch, config_dir, proj_dir, *, n_skills=3, drive_id=""):
        _patch_shared(monkeypatch, config_dir, proj_dir)
        _patch_get_storage(monkeypatch, drive_id=drive_id)
        mock_registry = MagicMock()
        mock_registry.get_all_skills.return_value = ["s"] * n_skills
        _patch_skill_registry(monkeypatch, registry_instance=mock_registry)
        return mock_registry

    def test_all_ok_no_contexts(self, tmp_path, monkeypatch):
        """health() exits 0 when all env checks pass (no contexts present)."""
        config_dir = self._make_config_dir(tmp_path, with_contextos=True, with_catalogos=True)
        # Put one context so the "Contextos disponíveis" row is True
        (config_dir / "contextos" / "ctx-1.json").write_text('{"catalogo_id":"cat-1"}')
        proj_dir = tmp_path / "projetos"
        proj_dir.mkdir()

        self._setup_common(monkeypatch, config_dir, proj_dir)

        mock_rt = _make_rt_mock({"cpus": []})
        _patch_runtime(monkeypatch, runtime_instance=mock_rt)
        _patch_cce(monkeypatch, [])

        from concilium.presentation.cli.commands_health import health

        health()  # Must not raise

    def test_degraded_missing_config_dir(self, tmp_path, monkeypatch):
        """health() raises typer.Exit(1) when config dir is missing."""
        config_dir = tmp_path / "nonexistent_config"
        proj_dir = tmp_path / "projetos"
        proj_dir.mkdir()

        self._setup_common(monkeypatch, config_dir, proj_dir)

        from concilium.presentation.cli.commands_health import health

        with pytest.raises(typer.Exit) as exc_info:
            health()
        assert exc_info.value.exit_code == 1

    def test_degraded_skill_registry_exception(self, tmp_path, monkeypatch):
        """health() raises Exit(1) when SkillRegistry fails."""
        config_dir = self._make_config_dir(tmp_path, with_contextos=True, with_catalogos=True)
        (config_dir / "contextos" / "ctx-1.json").write_text('{"catalogo_id":"cat-1"}')
        proj_dir = tmp_path / "projetos"
        proj_dir.mkdir()

        _patch_shared(monkeypatch, config_dir, proj_dir)
        _patch_get_storage(monkeypatch, drive_id="")
        _patch_skill_registry(monkeypatch, side_effect=ImportError("no module"))
        _patch_runtime(monkeypatch, runtime_instance=_make_rt_mock({"cpus": []}))
        _patch_cce(monkeypatch, [])

        from concilium.presentation.cli.commands_health import health

        with pytest.raises(typer.Exit) as exc_info:
            health()
        assert exc_info.value.exit_code == 1

    def test_degraded_no_contexts_in_dir(self, tmp_path, monkeypatch):
        """health() exits 1 when contextos dir exists but has no .json files."""
        config_dir = self._make_config_dir(tmp_path, with_contextos=True, with_catalogos=True)
        # No .json files → contexto_ids is empty → "Contextos disponíveis" is False
        proj_dir = tmp_path / "projetos"
        proj_dir.mkdir()

        self._setup_common(monkeypatch, config_dir, proj_dir)

        from concilium.presentation.cli.commands_health import health

        with pytest.raises(typer.Exit) as exc_info:
            health()
        assert exc_info.value.exit_code == 1

    def test_degraded_missing_contextos_dir(self, tmp_path, monkeypatch):
        """health() exits 1 when contextos dir does not exist."""
        config_dir = self._make_config_dir(tmp_path, with_contextos=False, with_catalogos=True)
        proj_dir = tmp_path / "projetos"
        proj_dir.mkdir()

        self._setup_common(monkeypatch, config_dir, proj_dir)

        from concilium.presentation.cli.commands_health import health

        with pytest.raises(typer.Exit) as exc_info:
            health()
        assert exc_info.value.exit_code == 1

    def test_degraded_missing_catalogos_dir(self, tmp_path, monkeypatch):
        """health() exits 1 when catalogos dir does not exist."""
        config_dir = self._make_config_dir(tmp_path, with_contextos=True, with_catalogos=False)
        (config_dir / "contextos" / "ctx-1.json").write_text('{"catalogo_id":"cat-1"}')
        proj_dir = tmp_path / "projetos"
        proj_dir.mkdir()

        self._setup_common(monkeypatch, config_dir, proj_dir)

        from concilium.presentation.cli.commands_health import health

        with pytest.raises(typer.Exit) as exc_info:
            health()
        assert exc_info.value.exit_code == 1

    def test_all_ok_with_sharepoint(self, tmp_path, monkeypatch):
        """health() exits 0 with SharePoint connectivity passing."""
        config_dir = self._make_config_dir(tmp_path, with_contextos=True, with_catalogos=True)
        (config_dir / "contextos" / "ctx-sp.json").write_text('{"catalogo_id":"cat-sp"}')
        proj_dir = tmp_path / "projetos"
        proj_dir.mkdir()

        self._setup_common(monkeypatch, config_dir, proj_dir, drive_id="drv-abc")

        mock_rt = _make_rt_mock({"cpus": []})
        _patch_runtime(monkeypatch, runtime_instance=mock_rt)
        _patch_cce(monkeypatch, [])

        sp_storage = MagicMock()
        sp_storage.health_check.return_value = {"status": "ok", "drive_name": "SP Drive"}

        import concilium.infrastructure.adapters.blob_storage.sharepoint as sp_mod

        monkeypatch.setattr(sp_mod, "SharePointBlobStorage", MagicMock(**{"from_env.return_value": sp_storage}))

        from concilium.presentation.cli.commands_health import health

        health()  # Must not raise

    def test_degraded_runtime_error_in_catalogs(self, tmp_path, monkeypatch):
        """health() exits 1 when Runtime raises in _hc_check_catalogs."""
        config_dir = self._make_config_dir(tmp_path, with_contextos=True, with_catalogos=True)
        (config_dir / "contextos" / "ctx-fail.json").write_text('{"catalogo_id":"cat-fail"}')
        proj_dir = tmp_path / "projetos"
        proj_dir.mkdir()

        self._setup_common(monkeypatch, config_dir, proj_dir)
        _patch_runtime(monkeypatch, side_effect=RuntimeError("runtime explosion"))
        _patch_cce(monkeypatch, [])

        from concilium.presentation.cli.commands_health import health

        with pytest.raises(typer.Exit) as exc_info:
            health()
        assert exc_info.value.exit_code == 1

    def test_all_ok_multiple_contexts(self, tmp_path, monkeypatch):
        """health() exits 0 with multiple contexts all passing."""
        config_dir = self._make_config_dir(tmp_path, with_contextos=True, with_catalogos=True)
        for i in range(3):
            (config_dir / "contextos" / f"ctx-{i}.json").write_text(f'{{"catalogo_id":"cat-{i}"}}')
        proj_dir = tmp_path / "projetos"
        proj_dir.mkdir()

        self._setup_common(monkeypatch, config_dir, proj_dir)

        mock_rt = _make_rt_mock({"cpus": ["c1"]})
        _patch_runtime(monkeypatch, runtime_instance=mock_rt)
        _patch_cce(monkeypatch, [])

        from concilium.presentation.cli.commands_health import health

        health()  # Must not raise

    def test_degraded_catalog_with_errors(self, tmp_path, monkeypatch):
        """health() exits 1 when a catalog has critical errors."""
        config_dir = self._make_config_dir(tmp_path, with_contextos=True, with_catalogos=True)
        (config_dir / "contextos" / "ctx-err.json").write_text('{"catalogo_id":"cat-err"}')
        proj_dir = tmp_path / "projetos"
        proj_dir.mkdir()

        self._setup_common(monkeypatch, config_dir, proj_dir)

        mock_rt = _make_rt_mock({"cpus": []})
        _patch_runtime(monkeypatch, runtime_instance=mock_rt)
        _patch_cce(monkeypatch, ["critical error 1"])  # catalog has errors

        from concilium.presentation.cli.commands_health import health

        with pytest.raises(typer.Exit) as exc_info:
            health()
        assert exc_info.value.exit_code == 1
