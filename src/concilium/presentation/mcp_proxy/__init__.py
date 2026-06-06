"""Compat shim: encaminha pacote legado para ``concilium.presentation.mcp.proxy``."""

from __future__ import annotations

import importlib
import sys

_TARGET = "concilium.presentation.mcp.proxy"

proxy = importlib.import_module(_TARGET)
sys.modules[f"{__name__}.proxy"] = proxy

# Re-exporta símbolos de alto nível usados por entrypoints e imports antigos.
main = proxy.main

__all__ = ["main", "proxy"]
