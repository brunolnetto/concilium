from ..models import PipelineConfig


HOLIDAYS_2026 = PipelineConfig(
    name="holidays_2026",
    source="feriados_api",
    destination="duckdb",
    source_options={
        "year": 2026,
        "states": True,
    },
    destination_options={
        "database":
            "data/gold/feriados.duckdb",
        "table":
            "dim_holiday",
    },
    transformers=[
        "src.transformers.holidays.normalize_holidays",
    ],
)