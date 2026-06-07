"""ADR-004 / ADR-075: Activity Scheduling Algorithm Selection Strategy.

Public API
----------
Always available (no optional dependencies):
  SerialScheduler, select_scheduling_algorithm, explore_schedules, models.

Optional (require ortools / pulp — imported lazily inside explore_schedules):
  CpSatScheduler, LnsScheduler, MILPScheduler.
  Import them directly from their sub-modules when needed for testing or CLI use:
    from concilium.application.scheduling.cpsat_scheduler import CpSatScheduler
"""

from .compression_analysis import (
    CompressionResult,
    KScaleResult,
    compute_compression_sensitivities,
    format_compression_table,
)
from .models import (
    Activity,
    ActivityDAG,
    ResourcePool,
    ScheduledActivity,
    ScheduleError,
    ScheduleMetrics,
    ScheduleOutput,
    SchedulingStrategy,
)
from .pool_inference import (
    derivar_required_resources,
    inferir_pool_minimo,
    inferir_pool_minimo_from_spec,
    tipo_recurso_de_equip,
    validar_equipamentos_mapeaveis,
)
from .scheduler import SerialScheduler
from .selector import compare_all_algorithms, explore_schedules, select_scheduling_algorithm
from .validator import ScheduleValidator

__all__ = [
    "Activity",
    "ActivityDAG",
    "ResourcePool",
    "ScheduleError",
    "ScheduleMetrics",
    "ScheduleOutput",
    "ScheduledActivity",
    "SchedulingStrategy",
    "SerialScheduler",
    "ScheduleValidator",
    "select_scheduling_algorithm",
    "explore_schedules",
    "compare_all_algorithms",
    "inferir_pool_minimo",
    "inferir_pool_minimo_from_spec",
    "derivar_required_resources",
    "tipo_recurso_de_equip",
    "validar_equipamentos_mapeaveis",
    # Compression analysis (NEP-038)
    "CompressionResult",
    "KScaleResult",
    "compute_compression_sensitivities",
    "format_compression_table",
    # Optional schedulers — not exported here to avoid eager ortools/pulp import.
    # Import directly: from concilium.application.scheduling.cpsat_scheduler import CpSatScheduler
    # "CpSatScheduler", "ExtendedPrecedence", "LnsScheduler", "MILPScheduler"
]
