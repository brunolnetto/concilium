"""Coverage sweep 2 — medium missing-line files (8-25 lines)."""

from __future__ import annotations

from unittest.mock import patch

# ─── jwt_auth middleware ──────────────────────────────────────────────────────


class TestJwtAuth:
    def test_unauthorized_returns_401(self):
        from concilium.presentation.api.middleware.jwt_auth import _unauthorized

        resp = _unauthorized("missing token")
        assert resp.status_code == 401

    def test_auth_enabled_reads_setting(self):
        from concilium.presentation.api.middleware.jwt_auth import _auth_enabled

        with patch("concilium.presentation.api.middleware.jwt_auth.get_auth") as mock_ga:
            mock_ga.return_value.enabled = False
            assert _auth_enabled() is False
            mock_ga.return_value.enabled = True
            assert _auth_enabled() is True

    def test_skip_paths_contains_health(self):
        from concilium.presentation.api.middleware.jwt_auth import _SKIP_PATHS

        assert "/health" in _SKIP_PATHS
        assert "/auth/token" in _SKIP_PATHS



