"""ConciliumService — parte extraída de concilium_service.py (mixin _MobilizacaoDeliverablesMixin)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .._concilium_service_helpers import (
    _cs_simulate_mobilizacao_policy,
    _cs_validate_mobilizacao_policies,
)

if TYPE_CHECKING:
    from ._host_protocol import ConciliumServiceHost

    _Base = ConciliumServiceHost
else:
    _Base = object


class _MobilizacaoDeliverablesMixin(_Base):
    """Métodos de mobilizacao_deliverables de ConciliumService."""

    def get_mobilizacao_policies(self, project_id: str) -> dict[str, Any]:
        return self._dependencies.override_service.get_mobilizacao_policies(project_id)

    def upsert_mobilizacao_policy(
        self, project_id: str, item_id: str, policy_data: dict[str, Any], actor: str = "system"
    ) -> None:
        self._dependencies.override_service.upsert_mobilizacao_policy(project_id, item_id, policy_data, actor=actor)

    def delete_mobilizacao_policy(self, project_id: str, item_id: str, actor: str = "system") -> None:
        self._dependencies.override_service.delete_mobilizacao_policy(project_id, item_id, actor=actor)

    def simulate_mobilizacao_policy(self, project_id: str, req: dict[str, Any]) -> dict[str, Any]:
        return _cs_simulate_mobilizacao_policy(project_id, req)

    def validate_mobilizacao_policies(self, project_id: str) -> list[dict[str, Any]]:
        return _cs_validate_mobilizacao_policies(self, project_id)

    def get_deliverables_config(self, project_id: str) -> dict[str, Any]:
        return self._dependencies.override_service.get_deliverables_config(project_id)

    def put_deliverables_config(self, project_id: str, config: dict[str, Any], actor: str = "system") -> dict[str, Any]:
        return self._dependencies.override_service.put_deliverables_config(project_id, config, actor=actor)

