"""Projeções (faces) do Cubo de Estoque Consumível — ADR-128 F6."""

from ._dispatch import (
    _FACES,
    _GRANULARIDADES,
    cubo_estoque_consumivel_projection_contract,
    resolve_cubo_estoque_consumivel_projection,
)

__all__ = [
    "_FACES",
    "_GRANULARIDADES",
    "cubo_estoque_consumivel_projection_contract",
    "resolve_cubo_estoque_consumivel_projection",
]
