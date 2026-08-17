from dataclasses import dataclass, field


@dataclass(slots=True)
class PipelineConfig:

    year: int

    exporters: list[str] = field(
        default_factory=list
    )

    duckdb_path: str = "holidays.duckdb"

    # Requires a plan with municipality quota (e.g. Dev, 5.000
    # req/month) — crawls all 5.570 cities instead of just capitals.
    include_municipalities: bool = False