from __future__ import annotations

from threading import Lock

from concilium.application.runtime import Runtime
from concilium.application.services.audit_service import AuditService
from concilium.application.services.concilium_service import ConciliumDependencies, ConciliumService
from concilium.application.services.override_service import OverrideService
from concilium.application.services.pipeline_service import PipelineService
from concilium.application.services.project_input_builder import ProjectInputBuilder
from concilium.application.services.project_service import ProjectService
from concilium.infrastructure.storage.file_project_repository import FileProjectRepository
from concilium.presentation.cli.shared import config_root, projetos_root


class ServiceContainer:
    _instance: ServiceContainer | None = None
    _lock = Lock()

    def __init__(self) -> None:
        cfg_root = config_root()
        prj_root = projetos_root()
        benchmarks_root = cfg_root.parent / "benchmarks" / "data"
        prj_root.mkdir(parents=True, exist_ok=True)

        repository = FileProjectRepository(prj_root)
        audit_service = AuditService()
        project_service = ProjectService(repository, audit_service)
        override_service = OverrideService(repository, audit_service)
        pipeline_service = PipelineService(repository, audit_service, runtime_factory=lambda: Runtime(cfg_root))
        input_builder = ProjectInputBuilder(cfg_root, benchmarks_root)

        self.concilium_service = ConciliumService(
            ConciliumDependencies(
                input_builder=input_builder,
                repository=repository,
                project_service=project_service,
                override_service=override_service,
                pipeline_service=pipeline_service,
                audit_service=audit_service,
                benchmarks_root=benchmarks_root,
            )
        )

    @classmethod
    def instance(cls) -> ServiceContainer:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance


def get_concilium_service() -> ConciliumService:
    return ServiceContainer.instance().concilium_service
