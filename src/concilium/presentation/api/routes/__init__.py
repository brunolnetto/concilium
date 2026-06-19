from .analysis import router as analysis_router
from .auth import router as auth_router
from .benchmarks import router as benchmarks_router
from .campaign import router as campaign_router
from .catalog import router as catalog_router
from .catalogs import router as catalogs_router
from .configuration import router as configuration_router
from .formulario import router as formulario_router
from .mobilization import router as mobilization_router
from .observability import router as observability_router
from .overrides import router as overrides_router
from .projects import router as projects_router
from .runs import router as runs_router
from .system import router as system_router

__all__ = [
    "analysis_router",
    "auth_router",
    "campaign_router",
    "formulario_router",
    "benchmarks_router",
    "catalog_router",
    "catalogs_router",
    "configuration_router",
    "mobilization_router",
    "observability_router",
    "overrides_router",
    "projects_router",
    "runs_router",
    "system_router",
]
