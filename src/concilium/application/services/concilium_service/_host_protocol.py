"""Protocol descrevendo a superfície cruzada entre mixins de ConciliumService.

ConciliumService é composto por múltiplos mixins (_CatalogMixin,
_CpuResolutionMixin, _ProjectCrudMixin, _VersionedEntitiesMixin,
_RunVersionMixin, _ArtifactsReferenceMixin, _CuboAnaliticoMixin,
_MobilizacaoDeliverablesMixin) que se chamam entre si via `self`. Cada
mixin isolado não enxerga os atributos/métodos dos outros — este Protocol
existe só para checagem de tipos (TYPE_CHECKING), permitindo que cada mixin
declare `self` com essa forma sem introduzir uma dependência real em tempo
de execução.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class ConciliumServiceHost(Protocol):
    """Superfície do ConciliumService composto, do ponto de vista de um mixin individual."""

    _dependencies: Any
    _enriched_cache: dict[str, tuple[int, list[dict[str, Any]]]]
    config_root: Path

    def get_catalog_cpu(self, catalog_id: str, cpu_id: str) -> dict[str, Any] | None: ...
    def _load_canonical_for_version(self, project_id: str, version: str | None = None) -> Any: ...
