from dataclasses import dataclass, field
from typing import Literal


SourceType = Literal[
    "feriados_api",
]

DestinationType = Literal[
    "json",
    "csv",
    "parquet",
    "duckdb",
]


@dataclass(slots=True)
class PipelineConfig:

    name: str

    source: SourceType

    destination: DestinationType

    source_options: dict = field(
        default_factory=dict
    )

    destination_options: dict = field(
        default_factory=dict
    )

    transformers: list[str] = field(
        default_factory=list
    )