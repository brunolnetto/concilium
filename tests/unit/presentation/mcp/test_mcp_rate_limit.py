"""Tests for small-gap files: benchmark repository port, week_sequence, config mixin,
permission_guard, rate_limit, jwt_auth, replan MCP tool."""

from __future__ import annotations

import inspect

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

    async def test_mcp_rate_limit_preserva_async_e_executa_a_coroutine(self):
        """2026-08-12: bug real achado no PR #159 — envolver uma tool `async def`

        produzia um wrapper síncrono que devolvia a coroutine sem executá-la
        (mesma classe do issue #148, ver permission_guard.permission). O FastMCP
        decide se dá `await` inspecionando o wrapper mais externo, não a função
        original — por isso o retorno era `<coroutine object ...>` em vez do
        resultado real, e o corpo da tool nunca rodava.
        """
        import concilium.presentation.mcp.rate_limit as rl_mod

        rl_mod._counters.clear()

        @rl_mod.mcp_rate_limit(calls=5, period_s=60)
        async def minha_tool_async(project_id: str) -> dict:
            return {"ok": True, "project_id": project_id}

        assert inspect.iscoroutinefunction(minha_tool_async)
        resultado = await minha_tool_async(project_id="P1")
        assert resultado == {"ok": True, "project_id": "P1"}

        rl_mod._counters.clear()

    async def test_mcp_rate_limit_async_tambem_bloqueia_acima_do_limite(self):
        import concilium.presentation.mcp.rate_limit as rl_mod

        rl_mod._counters.clear()

        @rl_mod.mcp_rate_limit(calls=1, period_s=60)
        async def minha_tool_async(project_id: str) -> dict:
            return {"ok": True}

        assert await minha_tool_async(project_id="P1") == {"ok": True}
        with pytest.raises(RuntimeError, match="Rate limit atingido"):
            await minha_tool_async(project_id="P1")

        rl_mod._counters.clear()



