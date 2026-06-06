"""Compat shim: encaminha imports legados para ``concilium.presentation.mcp``."""

from __future__ import annotations

import importlib
import sys

_LEGACY_BASE = __name__
_NEW_BASE = "concilium.presentation.mcp"
_FORWARDED_SUBMODULES = (
	"_context",
	"guards",
	"middleware",
	"rate_limit",
	"server",
	"tools",
)


def _forward_submodule(name: str):
	new_mod = importlib.import_module(f"{_NEW_BASE}.{name}")
	sys.modules[f"{_LEGACY_BASE}.{name}"] = new_mod
	return new_mod


for _submodule in _FORWARDED_SUBMODULES:
	_forward_submodule(_submodule)


def __getattr__(name: str):
	# Forward top-level symbols (ex.: build_server/main) to the new server module.
	server_mod = _forward_submodule("server")
	if hasattr(server_mod, name):
		return getattr(server_mod, name)
	raise AttributeError(f"module '{__name__}' has no attribute {name!r}")


__all__ = ["_FORWARDED_SUBMODULES"]
