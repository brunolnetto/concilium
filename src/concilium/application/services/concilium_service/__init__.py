from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from concilium.application.benchmarks.execution.batch import discover_benchmark_slugs
from concilium.application.runtime import Runtime
from concilium.application.services.pipeline_service import PipelineService
from concilium.application.services.project.audit_service import AuditService
from concilium.application.services.project.override_service import OverrideService
from concilium.application.services.project.project_input_builder import ProjectInputBuilder
from concilium.application.services.project.project_repository import ProjectRepository
from concilium.application.services.project.project_service import ProjectService

from .._concilium_service_helpers import (
    _cs_get_enriched_cpus,
    _cs_simulate_mobilizacao_policy,
    _cs_upsert_catalog_cpu,
    _cs_validate_mobilizacao_policies,
    _enrich_cpus_with_producao,
)
from ..catalog.catalog_reasonability import build_catalog_reasonability_artifact
from ._artifacts_reference import _ArtifactsReferenceMixin
from ._catalog import _CatalogMixin
from ._cpu_resolution import _CpuResolutionMixin
from ._cubo_analitico import _CuboAnaliticoMixin
from ._cubo_estoque_consumivel import _CuboEstoqueConsumivelMixin
from ._cubo_roster_real import _CuboRosterRealMixin
from ._mobilizacao_deliverables import _MobilizacaoDeliverablesMixin
from ._project_crud import _ProjectCrudMixin
from ._run_version import _RunVersionMixin
from ._versioned_entities import _VersionedEntitiesMixin

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConciliumDependencies:
    input_builder: ProjectInputBuilder
    repository: ProjectRepository
    project_service: ProjectService
    override_service: OverrideService
    pipeline_service: PipelineService
    audit_service: AuditService
    benchmarks_root: Path


class ConciliumService(
    _CatalogMixin,
    _CpuResolutionMixin,
    _ProjectCrudMixin,
    _VersionedEntitiesMixin,
    _RunVersionMixin,
    _ArtifactsReferenceMixin,
    _CuboAnaliticoMixin,
    _CuboEstoqueConsumivelMixin,
    _CuboRosterRealMixin,
    _MobilizacaoDeliverablesMixin,
):
    def __init__(self, dependencies: ConciliumDependencies) -> None:
        self._dependencies = dependencies
        # Mixins declare config_root as writable state; snapshot the path exposed
        # by the input builder once when the service is assembled.
        self.config_root: Path = dependencies.input_builder._config_root  # type: ignore[attr-defined]
        # Cache: catalog_id → (bundle_mtime_ns, enriched_cpus)
        # Invalidada automaticamente quando o bundle é substituído (ADR-067 bust).
        self._enriched_cache: dict[str, tuple[int, list[dict[str, Any]]]] = {}
