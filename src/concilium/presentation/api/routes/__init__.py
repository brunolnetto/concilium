from .analysis import router as analysis_router
from .benchmarks import router as benchmarks_router
from .catalog import router as catalog_router
from .catalogs import router as catalogs_router
from .configuration import router as configuration_router
from .mobilization import router as mobilization_router
from .overrides import router as overrides_router
from .projects import router as projects_router
from .runs import router as runs_router
from .system import router as system_router

__all__ = [
    "analysis_router",
    "benchmarks_router",
    "catalog_router",
    "catalogs_router",
    "configuration_router",
    "mobilization_router",
    "overrides_router",
    "projects_router",
    "runs_router",
    "system_router",
]
