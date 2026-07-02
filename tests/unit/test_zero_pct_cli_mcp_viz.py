"""Tests for modules at 0% coverage:

- src/concilium/presentation/mcp/proxy.py
- src/concilium/application/runtime/deliverables/visualizations/eficiencia/eta_obra.py
- src/concilium/application/runtime/deliverables/visualizations/eficiencia/pareto_perdas.py
- src/concilium/application/runtime/deliverables/visualizations/eficiencia/__init__.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Section 1: proxy.py — sync helpers
# ─────────────────────────────────────────────────────────────────────────────

# The proxy module calls get_mcp_proxy() at import time; patch it before import.
_fake_proxy_settings = MagicMock()
_fake_proxy_settings.server_url = "https://mcp.example.com"
_fake_proxy_settings.device_id = "test-device"
_fake_proxy_settings.client_code = "RCODE-TEST"


@pytest.fixture(scope="module")
def proxy_module():
    """Import proxy with get_mcp_proxy stubbed out."""
    with patch(
        "concilium.infrastructure.settings.get_mcp_proxy",
        return_value=_fake_proxy_settings,
    ):
        import concilium.presentation.mcp.proxy as _proxy_mod

        # Patch the module-level vars that were set at import time
        _proxy_mod._SERVER_URL = "https://mcp.example.com"
        _proxy_mod._DEVICE_ID = "test-device"
        _proxy_mod._CLIENT_CODE = "RCODE-TEST"
        return _proxy_mod


class TestProxyTokenPath:
    def test_returns_path_in_token_dir(self, proxy_module, tmp_path):
        """_token_path() returns a Path inside a ~/.concilium/tokens/ style directory."""
        original_token_dir = proxy_module._TOKEN_DIR
        proxy_module._TOKEN_DIR = tmp_path / "tokens"
        proxy_module._TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        try:
            result = proxy_module._token_path()
            assert isinstance(result, Path)
            assert result.parent == proxy_module._TOKEN_DIR
            assert result.name == "test-device.json"
        finally:
            proxy_module._TOKEN_DIR = original_token_dir


class TestProxyLoadCache:
    def test_no_file_returns_empty_dict(self, proxy_module, tmp_path):
        """_load_cache() returns {} when the token file does not exist."""
        token_dir = tmp_path / "tokens"
        token_dir.mkdir()
        original_token_dir = proxy_module._TOKEN_DIR
        proxy_module._TOKEN_DIR = token_dir
        try:
            result = proxy_module._load_cache()
            assert result == {}
        finally:
            proxy_module._TOKEN_DIR = original_token_dir

    def test_valid_json_file_returns_dict(self, proxy_module, tmp_path):
        """_load_cache() returns parsed dict when a valid JSON token file exists."""
        token_dir = tmp_path / "tokens"
        token_dir.mkdir()
        token_file = token_dir / "test-device.json"
        token_file.write_text(
            json.dumps({"refresh_token": "rt-abc123", "scopes": ["read"]}),
            encoding="utf-8",
        )

        original_token_dir = proxy_module._TOKEN_DIR
        proxy_module._TOKEN_DIR = token_dir
        try:
            result = proxy_module._load_cache()
            assert result == {"refresh_token": "rt-abc123", "scopes": ["read"]}
        finally:
            proxy_module._TOKEN_DIR = original_token_dir

    def test_corrupted_json_returns_empty_dict(self, proxy_module, tmp_path):
        """_load_cache() returns {} when token file contains invalid JSON."""
        token_dir = tmp_path / "tokens"
        token_dir.mkdir()
        token_file = token_dir / "test-device.json"
        token_file.write_text("NOT VALID JSON {{{{", encoding="utf-8")

        original_token_dir = proxy_module._TOKEN_DIR
        proxy_module._TOKEN_DIR = token_dir
        try:
            result = proxy_module._load_cache()
            assert result == {}
        finally:
            proxy_module._TOKEN_DIR = original_token_dir


class TestProxySaveCache:
    def test_writes_json_and_chmod_600(self, proxy_module, tmp_path):
        """_save_cache() writes JSON to the token file and sets permissions to 0o600."""
        token_dir = tmp_path / "tokens"
        token_dir.mkdir()
        original_token_dir = proxy_module._TOKEN_DIR
        proxy_module._TOKEN_DIR = token_dir
        try:
            data = {"refresh_token": "rt-xyz", "scopes": ["admin"]}
            proxy_module._save_cache(data)

            token_file = token_dir / "test-device.json"
            assert token_file.exists()

            written = json.loads(token_file.read_text(encoding="utf-8"))
            assert written == data

            # chmod 600 → stat mode ends in 0o600
            mode = token_file.stat().st_mode & 0o777
            assert mode == 0o600
        finally:
            proxy_module._TOKEN_DIR = original_token_dir


class TestProxyWriteError:
    def test_write_error_format(self, proxy_module, capsys):
        """_write_error writes a valid JSON-RPC error envelope to stdout."""
        msg = {"jsonrpc": "2.0", "id": 42, "method": "tools/list"}
        proxy_module._write_error(msg, "something went wrong")
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 42
        assert parsed["error"]["code"] == -32000
        assert "something went wrong" in parsed["error"]["message"]

    def test_write_error_null_id(self, proxy_module, capsys):
        """_write_error propagates None id when message has no id field."""
        proxy_module._write_error({}, "oops")
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed["id"] is None


class TestProxyLog:
    def test_log_writes_to_stderr(self, proxy_module, capsys):
        """_log writes a prefixed message to stderr."""
        proxy_module._log("hello from proxy")
        captured = capsys.readouterr()
        assert "[concilium-mcp-proxy]" in captured.err
        assert "hello from proxy" in captured.err


class TestProxyState:
    def test_state_stores_token_and_expire(self, proxy_module):
        """_State initialises with the provided token and expiry."""
        import threading

        state = proxy_module._State("tok-abc", 9999.0)
        assert state.access_token == "tok-abc"
        assert state.expire_at == 9999.0
        assert isinstance(state.lock, type(threading.Lock()))


# ─────────────────────────────────────────────────────────────────────────────
# Section 3: eta_obra.py
# ─────────────────────────────────────────────────────────────────────────────

# We load the module with matplotlib mocked so the import succeeds in CI.
_mock_matplotlib = MagicMock()
_mock_plt = MagicMock()
_mock_matplotlib.pyplot = _mock_plt


def _make_campo_eta(eta_dict: dict) -> MagicMock:
    campo = MagicMock()
    campo.eta_obra.return_value = eta_dict
    campo.semanas = list(eta_dict.keys())
    campo.atividades = ["eap-1"]
    campo.E = {"eap-1": eta_dict}
    return campo


class TestPlotEtaObra:
    def test_matplotlib_not_installed_returns_none(self):
        """plot_eta_obra returns None when matplotlib is not available."""
        with patch.dict(
            "sys.modules",
            {"matplotlib": None, "matplotlib.pyplot": None},
        ):
            # Force reimport without matplotlib
            mod_name = "concilium.application.runtime.deliverables.visualizations.eficiencia.eta_obra"
            if mod_name in sys.modules:
                del sys.modules[mod_name]
            from concilium.application.runtime.deliverables.visualizations.eficiencia.eta_obra import (
                plot_eta_obra,
            )

            campo = MagicMock()
            result = plot_eta_obra(campo)
            assert result is None

    def test_empty_eta_serie_returns_none(self):
        """plot_eta_obra returns None when campo.eta_obra() returns {}."""
        with patch.dict(
            "sys.modules",
            {
                "matplotlib": _mock_matplotlib,
                "matplotlib.pyplot": _mock_plt,
            },
        ):
            mod_name = "concilium.application.runtime.deliverables.visualizations.eficiencia.eta_obra"
            if mod_name in sys.modules:
                del sys.modules[mod_name]
            from concilium.application.runtime.deliverables.visualizations.eficiencia.eta_obra import (
                plot_eta_obra,
            )

            campo = _make_campo_eta({})
            result = plot_eta_obra(campo)
            assert result is None

    def test_with_data_calls_plt_and_returns_figure(self):
        """plot_eta_obra calls pyplot and returns the figure mock when data is present."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        local_plt = MagicMock()
        local_plt.subplots.return_value = (mock_fig, mock_ax)

        local_mpl = MagicMock()
        local_mpl.pyplot = local_plt

        with patch.dict(
            "sys.modules",
            {
                "matplotlib": local_mpl,
                "matplotlib.pyplot": local_plt,
            },
        ):
            mod_name = "concilium.application.runtime.deliverables.visualizations.eficiencia.eta_obra"
            if mod_name in sys.modules:
                del sys.modules[mod_name]
            from concilium.application.runtime.deliverables.visualizations.eficiencia.eta_obra import (
                plot_eta_obra,
            )

            campo = _make_campo_eta({"2026-W01": 0.9, "2026-W02": 0.85})
            result = plot_eta_obra(campo)

        assert result is mock_fig
        local_plt.subplots.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Section 4: pareto_perdas.py
# ─────────────────────────────────────────────────────────────────────────────

_PARETO_DATA = [
    {"item_id": "eap-1", "pct_perda": 25.0, "perda_fisica_total": 1000.0},
    {"item_id": "eap-2", "pct_perda": 15.0, "perda_fisica_total": 500.0},
]

_PARETO_MOD = "concilium.application.runtime.deliverables.visualizations.eficiencia.pareto_perdas"


def _make_campo_pareto(pareto_list: list) -> MagicMock:
    campo = MagicMock()
    campo.pareto_perdas.return_value = pareto_list
    return campo


class TestPlotParetoPerdas:
    def test_matplotlib_not_installed_returns_none(self):
        """plot_pareto_perdas returns None when matplotlib is not available."""
        with patch.dict("sys.modules", {"matplotlib": None, "matplotlib.pyplot": None}):
            if _PARETO_MOD in sys.modules:
                del sys.modules[_PARETO_MOD]
            from concilium.application.runtime.deliverables.visualizations.eficiencia.pareto_perdas import (
                plot_pareto_perdas,
            )

            campo = MagicMock()
            result = plot_pareto_perdas(campo)
            assert result is None

    def test_empty_pareto_returns_none(self):
        """plot_pareto_perdas returns None when pareto_perdas() returns []."""
        with patch.dict(
            "sys.modules",
            {"matplotlib": _mock_matplotlib, "matplotlib.pyplot": _mock_plt},
        ):
            if _PARETO_MOD in sys.modules:
                del sys.modules[_PARETO_MOD]
            from concilium.application.runtime.deliverables.visualizations.eficiencia.pareto_perdas import (
                plot_pareto_perdas,
            )

            campo = _make_campo_pareto([])
            result = plot_pareto_perdas(campo)
            assert result is None

    def test_with_data_calls_plt_and_returns_figure(self):
        """plot_pareto_perdas calls pyplot and returns figure mock when data is present."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        # barh returns a list of bar objects; ax.text does nothing
        mock_bars = [MagicMock(), MagicMock()]
        mock_ax.barh.return_value = mock_bars
        # Each bar needs get_width(), get_y(), get_height()
        for bar in mock_bars:
            bar.get_width.return_value = 500.0
            bar.get_y.return_value = 0.0
            bar.get_height.return_value = 0.5

        local_plt = MagicMock()
        local_plt.subplots.return_value = (mock_fig, mock_ax)
        local_mpl = MagicMock()
        local_mpl.pyplot = local_plt

        with patch.dict(
            "sys.modules",
            {"matplotlib": local_mpl, "matplotlib.pyplot": local_plt},
        ):
            if _PARETO_MOD in sys.modules:
                del sys.modules[_PARETO_MOD]
            from concilium.application.runtime.deliverables.visualizations.eficiencia.pareto_perdas import (
                plot_pareto_perdas,
            )

            campo = _make_campo_pareto(_PARETO_DATA)
            result = plot_pareto_perdas(campo)

        assert result is mock_fig
        local_plt.subplots.assert_called_once()

    def test_pareto_perdas_called_with_default_top_n(self):
        """plot_pareto_perdas passes top_n=10 by default to campo.pareto_perdas."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_bar = MagicMock()
        mock_bar.get_width.return_value = 100.0
        mock_bar.get_y.return_value = 0.0
        mock_bar.get_height.return_value = 0.5
        mock_ax.barh.return_value = [mock_bar]

        local_plt = MagicMock()
        local_plt.subplots.return_value = (mock_fig, mock_ax)
        local_mpl = MagicMock()
        local_mpl.pyplot = local_plt

        with patch.dict(
            "sys.modules",
            {"matplotlib": local_mpl, "matplotlib.pyplot": local_plt},
        ):
            if _PARETO_MOD in sys.modules:
                del sys.modules[_PARETO_MOD]
            from concilium.application.runtime.deliverables.visualizations.eficiencia.pareto_perdas import (
                plot_pareto_perdas,
            )

            campo = _make_campo_pareto([{"item_id": "eap-X", "pct_perda": 50.0, "perda_fisica_total": 200.0}])
            plot_pareto_perdas(campo)

        campo.pareto_perdas.assert_called_once_with(top_n=10)


# ─────────────────────────────────────────────────────────────────────────────
# Section 5: eficiencia __init__.py — verify it exports the four functions
# ─────────────────────────────────────────────────────────────────────────────

_INIT_MOD = "concilium.application.runtime.deliverables.visualizations.eficiencia"


class TestEficienciaInit:
    def test_module_loads_and_exports_all(self):
        """The eficiencia __init__ exports the four expected functions."""
        with patch.dict(
            "sys.modules",
            {
                "matplotlib": _mock_matplotlib,
                "matplotlib.pyplot": _mock_plt,
            },
        ):
            # Clean any cached submodule imports so __init__ re-runs with mocked plt
            for key in list(sys.modules.keys()):
                if key.startswith(_INIT_MOD):
                    del sys.modules[key]

            import importlib

            mod = importlib.import_module(_INIT_MOD)

        assert hasattr(mod, "plot_eta_obra")
        assert hasattr(mod, "plot_pareto_perdas")
        assert hasattr(mod, "plot_heatmap_top_n")
        assert hasattr(mod, "plot_waterfall_causal")

    def test_all_exports_are_callable(self):
        """All four symbols exported from the package are callable."""
        with patch.dict(
            "sys.modules",
            {
                "matplotlib": _mock_matplotlib,
                "matplotlib.pyplot": _mock_plt,
            },
        ):
            for key in list(sys.modules.keys()):
                if key.startswith(_INIT_MOD):
                    del sys.modules[key]
            import importlib

            mod = importlib.import_module(_INIT_MOD)

        for name in ("plot_eta_obra", "plot_pareto_perdas", "plot_heatmap_top_n", "plot_waterfall_causal"):
            assert callable(getattr(mod, name)), f"{name} must be callable"
