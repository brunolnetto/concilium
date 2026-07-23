"""Tests for small-gap files: benchmark repository port, week_sequence, config mixin,
permission_guard, rate_limit, jwt_auth, replan MCP tool."""

from __future__ import annotations

import pytest

# ─── presentation/mcp/rate_limit.py ───────────────────────────────────────────


class TestMcpRateLimit:
    def test_mcp_rate_limit_raises_when_limit_exceeded(self):
        """Linhas 50-52: chamadas acima do limite levantam RuntimeError com wait_s."""
        import concilium.presentation.mcp.rate_limit as rl_mod

        rl_mod._counters.clear()

        @rl_mod.mcp_rate_limit(calls=2, period_s=60)
        def minha_tool(project_id: str) -> dict:
            return {"ok": True}

        assert minha_tool(project_id="P1") == {"ok": True}
        assert minha_tool(project_id="P1") == {"ok": True}
        with pytest.raises(RuntimeError, match="Rate limit atingido"):
            minha_tool(project_id="P1")

        rl_mod._counters.clear()



