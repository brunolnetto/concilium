"""Loader de referência de benchmark — produz ProjectSpec a partir de referencia.json."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...input_derivation import BenchmarkInputDeriver
from ._inputs import _InputsMixin
from ._load_dict import _LoadDictMixin
from ._normalize import _NormalizeMixin
from ._project_spec import ProjectSpec, iso_weeks
from ._resolve import _ResolveMixin
from ._v2_schema import _unpack_v2_schema

__all__ = [
    "BenchmarkSpecLoader",
    "ProjectSpec",
    "iso_weeks",
    "load_spec_from_dict",
    "load_spec_from_json",
]


class BenchmarkSpecLoader(_ResolveMixin, _InputsMixin, _LoadDictMixin, _NormalizeMixin):
    """Carrega referencia.json e produz um ProjectSpec compatível com o runner."""

    def __init__(self, config_root: Path) -> None:
        self._config_root = config_root
        self._project_root = self._config_root.parent
        self._input_deriver = BenchmarkInputDeriver(config_root)


def load_spec_from_json(path: Path | str) -> ProjectSpec:
    from concilium.infrastructure.settings import get_storage

    config_root = get_storage().config_root
    return BenchmarkSpecLoader(config_root).load(path)


def load_spec_from_dict(ref: dict[str, Any], path: Path | str) -> ProjectSpec:
    """Carrega ProjectSpec a partir de um dict ja em memoria (sem I/O de disco)."""
    from concilium.infrastructure.settings import get_storage

    config_root = get_storage().config_root
    return BenchmarkSpecLoader(config_root).load_from_dict(ref, path)
