from __future__ import annotations

from typing import Any

from ..audit_service import AuditService
from ..project_files import DEFAULT_PROJECT_FILES, ProjectFiles
from ..project_repository import ProjectRepository
from ._benchmark_eap import _BenchmarkEapMixin
from ._crud import _CrudMixin
from ._eap import _EapMixin
from ._shared import (
    _as_dict_rows,
    _canonical_eap_to_rows,
    _catalog_is_deficit,
    _cpu_has_equipe_composicao,
    _debug_storage_info,
    _extract_canonical_eap_rows,
    _extract_historical_eap_rows,
    _is_valid_canonical_eap,
    _latest_version_with_eap,
    _ps_build_list_item,
    _resolve_project_type,
)
from ._validation import _ValidationMixin
from ._versioned_entities import _VersionedEntitiesMixin
from ._versions_artifacts import _VersionsArtifactsMixin


class ProjectService(
    _CrudMixin,
    _EapMixin,
    _VersionsArtifactsMixin,
    _VersionedEntitiesMixin,
    _ValidationMixin,
    _BenchmarkEapMixin,
):
    def __init__(
        self, repository: ProjectRepository, audit_service: AuditService, files: ProjectFiles = DEFAULT_PROJECT_FILES
    ):
        self._repository = repository
        self._audit_service = audit_service
        self._files = files
