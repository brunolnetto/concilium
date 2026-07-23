from unittest.mock import MagicMock, patch

import pytest

from concilium.presentation.api.container import ServiceContainer, get_concilium_service

PATCHES = {
    "config_root": "concilium.presentation.api.container.config_root",
    "projetos_root": "concilium.presentation.api.container.projetos_root",
    "build_project_repository": "concilium.presentation.api.container.build_project_repository",
    "AuditService": "concilium.presentation.api.container.AuditService",
    "ProjectService": "concilium.presentation.api.container.ProjectService",
    "OverrideService": "concilium.presentation.api.container.OverrideService",
    "PipelineService": "concilium.presentation.api.container.PipelineService",
    "ProjectInputBuilder": "concilium.presentation.api.container.ProjectInputBuilder",
    "ConciliumService": "concilium.presentation.api.container.ConciliumService",
    "ConciliumDependencies": "concilium.presentation.api.container.ConciliumDependencies",
    "Runtime": "concilium.presentation.api.container.Runtime",
}


@pytest.fixture(autouse=True)
def reset_singleton():
    ServiceContainer._instance = None
    yield
    ServiceContainer._instance = None


def _make_mocks():
    mocks = {k: MagicMock() for k in PATCHES}
    cfg_root = mocks["config_root"].return_value
    cfg_root.parent = MagicMock()
    benchmarks_root = cfg_root.parent.__truediv__.return_value.__truediv__.return_value
    prj_root = mocks["projetos_root"].return_value
    return mocks, cfg_root, prj_root, benchmarks_root


def test_init_builds_concilium_service():
    mocks, cfg_root, prj_root, benchmarks_root = _make_mocks()

    with (
        patch(PATCHES["config_root"], mocks["config_root"]),
        patch(PATCHES["projetos_root"], mocks["projetos_root"]),
        patch(PATCHES["build_project_repository"], mocks["build_project_repository"]),
        patch(PATCHES["AuditService"], mocks["AuditService"]),
        patch(PATCHES["ProjectService"], mocks["ProjectService"]),
        patch(PATCHES["OverrideService"], mocks["OverrideService"]),
        patch(PATCHES["PipelineService"], mocks["PipelineService"]),
        patch(PATCHES["ProjectInputBuilder"], mocks["ProjectInputBuilder"]),
        patch(PATCHES["ConciliumService"], mocks["ConciliumService"]),
        patch(PATCHES["ConciliumDependencies"], mocks["ConciliumDependencies"]),
        patch(PATCHES["Runtime"], mocks["Runtime"]),
    ):
        sc = ServiceContainer()

    prj_root.mkdir.assert_called_once_with(parents=True, exist_ok=True)
    mocks["build_project_repository"].assert_called_once_with(prj_root)
    mocks["AuditService"].assert_called_once_with()
    mocks["ProjectService"].assert_called_once()
    mocks["OverrideService"].assert_called_once()
    mocks["PipelineService"].assert_called_once()
    mocks["ProjectInputBuilder"].assert_called_once()
    mocks["ConciliumService"].assert_called_once()
    assert sc.concilium_service is mocks["ConciliumService"].return_value


def test_runtime_factory_invokes_runtime():
    mocks, cfg_root, prj_root, benchmarks_root = _make_mocks()
    captured_factory = {}

    def capture_pipeline_service(*args, **kwargs):
        factory = kwargs.get("runtime_factory")
        if factory is None:
            for _a in args:
                pass
        captured_factory["fn"] = factory
        return MagicMock()

    mocks["PipelineService"].side_effect = capture_pipeline_service

    with (
        patch(PATCHES["config_root"], mocks["config_root"]),
        patch(PATCHES["projetos_root"], mocks["projetos_root"]),
        patch(PATCHES["build_project_repository"], mocks["build_project_repository"]),
        patch(PATCHES["AuditService"], mocks["AuditService"]),
        patch(PATCHES["ProjectService"], mocks["ProjectService"]),
        patch(PATCHES["OverrideService"], mocks["OverrideService"]),
        patch(PATCHES["PipelineService"], mocks["PipelineService"]),
        patch(PATCHES["ProjectInputBuilder"], mocks["ProjectInputBuilder"]),
        patch(PATCHES["ConciliumService"], mocks["ConciliumService"]),
        patch(PATCHES["ConciliumDependencies"], mocks["ConciliumDependencies"]),
        patch(PATCHES["Runtime"], mocks["Runtime"]),
    ):
        ServiceContainer()
        if captured_factory.get("fn"):
            captured_factory["fn"]()
            mocks["Runtime"].assert_called_with(cfg_root)


def test_instance_returns_same_object_on_two_calls():
    mocks, cfg_root, prj_root, benchmarks_root = _make_mocks()

    with (
        patch(PATCHES["config_root"], mocks["config_root"]),
        patch(PATCHES["projetos_root"], mocks["projetos_root"]),
        patch(PATCHES["build_project_repository"], mocks["build_project_repository"]),
        patch(PATCHES["AuditService"], mocks["AuditService"]),
        patch(PATCHES["ProjectService"], mocks["ProjectService"]),
        patch(PATCHES["OverrideService"], mocks["OverrideService"]),
        patch(PATCHES["PipelineService"], mocks["PipelineService"]),
        patch(PATCHES["ProjectInputBuilder"], mocks["ProjectInputBuilder"]),
        patch(PATCHES["ConciliumService"], mocks["ConciliumService"]),
        patch(PATCHES["ConciliumDependencies"], mocks["ConciliumDependencies"]),
        patch(PATCHES["Runtime"], mocks["Runtime"]),
    ):
        first = ServiceContainer.instance()
        second = ServiceContainer.instance()

    assert first is second


def test_instance_is_none_before_first_call():
    assert ServiceContainer._instance is None


def test_instance_sets_class_attribute():
    mocks, cfg_root, prj_root, benchmarks_root = _make_mocks()

    with (
        patch(PATCHES["config_root"], mocks["config_root"]),
        patch(PATCHES["projetos_root"], mocks["projetos_root"]),
        patch(PATCHES["build_project_repository"], mocks["build_project_repository"]),
        patch(PATCHES["AuditService"], mocks["AuditService"]),
        patch(PATCHES["ProjectService"], mocks["ProjectService"]),
        patch(PATCHES["OverrideService"], mocks["OverrideService"]),
        patch(PATCHES["PipelineService"], mocks["PipelineService"]),
        patch(PATCHES["ProjectInputBuilder"], mocks["ProjectInputBuilder"]),
        patch(PATCHES["ConciliumService"], mocks["ConciliumService"]),
        patch(PATCHES["ConciliumDependencies"], mocks["ConciliumDependencies"]),
        patch(PATCHES["Runtime"], mocks["Runtime"]),
    ):
        ServiceContainer.instance()

    assert ServiceContainer._instance is not None


def test_instance_race_skips_second_construction():
    """Simula a corrida do double-checked locking: outra thread já setou
    `_instance` enquanto esta aguardava o lock, exercitando o ramo em que
    o `if cls._instance is None` interno é falso e a instância existente
    é reaproveitada em vez de reconstruída."""
    sentinel = MagicMock()

    class _RaceLock:
        def __enter__(self):
            ServiceContainer._instance = sentinel
            return self

        def __exit__(self, *exc):
            return False

    with patch.object(ServiceContainer, "_lock", _RaceLock()):
        result = ServiceContainer.instance()

    assert result is sentinel


def test_get_concilium_service_returns_attribute():
    mocks, cfg_root, prj_root, benchmarks_root = _make_mocks()

    with (
        patch(PATCHES["config_root"], mocks["config_root"]),
        patch(PATCHES["projetos_root"], mocks["projetos_root"]),
        patch(PATCHES["build_project_repository"], mocks["build_project_repository"]),
        patch(PATCHES["AuditService"], mocks["AuditService"]),
        patch(PATCHES["ProjectService"], mocks["ProjectService"]),
        patch(PATCHES["OverrideService"], mocks["OverrideService"]),
        patch(PATCHES["PipelineService"], mocks["PipelineService"]),
        patch(PATCHES["ProjectInputBuilder"], mocks["ProjectInputBuilder"]),
        patch(PATCHES["ConciliumService"], mocks["ConciliumService"]),
        patch(PATCHES["ConciliumDependencies"], mocks["ConciliumDependencies"]),
        patch(PATCHES["Runtime"], mocks["Runtime"]),
    ):
        result = get_concilium_service()

    assert result is mocks["ConciliumService"].return_value


def test_get_concilium_service_uses_singleton():
    mocks, cfg_root, prj_root, benchmarks_root = _make_mocks()

    with (
        patch(PATCHES["config_root"], mocks["config_root"]),
        patch(PATCHES["projetos_root"], mocks["projetos_root"]),
        patch(PATCHES["build_project_repository"], mocks["build_project_repository"]),
        patch(PATCHES["AuditService"], mocks["AuditService"]),
        patch(PATCHES["ProjectService"], mocks["ProjectService"]),
        patch(PATCHES["OverrideService"], mocks["OverrideService"]),
        patch(PATCHES["PipelineService"], mocks["PipelineService"]),
        patch(PATCHES["ProjectInputBuilder"], mocks["ProjectInputBuilder"]),
        patch(PATCHES["ConciliumService"], mocks["ConciliumService"]),
        patch(PATCHES["ConciliumDependencies"], mocks["ConciliumDependencies"]),
        patch(PATCHES["Runtime"], mocks["Runtime"]),
    ):
        r1 = get_concilium_service()
        r2 = get_concilium_service()

    assert r1 is r2
    mocks["ConciliumService"].assert_called_once()
