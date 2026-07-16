"""ConciliumService — parte extraída (mixin _CuboEstoqueConsumivelMixin, ADR-128 F6)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._host_protocol import ConciliumServiceHost

    _Base = ConciliumServiceHost
else:
    _Base = object


class _CuboEstoqueConsumivelMixin(_Base):
    """Métodos de cubo de estoque de consumíveis de ConciliumService (ADR-128 F6)."""

    @staticmethod
    def get_cubo_estoque_consumivel_projection_contract() -> dict[str, Any]:
        """ADR-128 F6: contrato navegável das faces do cubo de estoque de consumíveis."""
        from concilium.application.services.analytics.cubo_estoque_consumivel_projection import (
            cubo_estoque_consumivel_projection_contract,
        )

        return cubo_estoque_consumivel_projection_contract()

    def get_cubo_estoque_consumivel_projection(
        self,
        project_id: str,
        *,
        version: str | None = None,
        face: str = "resumo_por_recurso",
        granularidade: str = "mes",
        top_n: int = 300,
        resource_id: str | None = None,
    ) -> dict[str, Any]:
        """ADR-128 F6: projeção da contabilização de estoque de recursos consumíveis."""
        from concilium.application.services.analytics.cubo_estoque_consumivel_projection import (
            resolve_cubo_estoque_consumivel_projection,
        )

        canonical, resolved_version = self._load_canonical_for_version(project_id, version)
        if canonical is None:
            return {
                "version": resolved_version,
                "face": face,
                "rows": [],
                "narrativa": [],
                "filtros_aplicados": {},
                "invariantes_ok": True,
            }
        proj = resolve_cubo_estoque_consumivel_projection(
            canonical,
            face=face,
            granularidade=granularidade,
            top_n=top_n,
            resource_id=resource_id,
        )
        proj["version"] = resolved_version
        return proj
