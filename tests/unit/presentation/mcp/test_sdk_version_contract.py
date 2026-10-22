"""P25-A: lock the MCP SDK surface used by the production server.

This test intentionally imports neither the Concilium runtime nor the standalone
FastMCP distribution. It fails during collection whenever dependency resolution
reintroduces MCP SDK 2.x, so a large module-collection failure is prevented.
"""

from importlib.metadata import version


def test_native_mcp_sdk_major_is_compatible() -> None:
    installed = version("mcp")
    assert installed.split(".", 1)[0] == "1", (
        f"Concilium expects the MCP SDK 1.x FastMCP API; installed mcp=={installed}. "
        "A 2.x upgrade requires a coordinated MCPServer migration."
    )


def test_fastmcp_v1_public_server_contract() -> None:
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("concilium-sdk-smoke")
    assert server.name == "concilium-sdk-smoke"
    assert callable(server.tool)
    assert callable(server.resource)
    assert callable(server.streamable_http_app)


def test_v1_lowlevel_request_context_is_available() -> None:
    from mcp.server.lowlevel.server import request_ctx

    assert request_ctx is not None
