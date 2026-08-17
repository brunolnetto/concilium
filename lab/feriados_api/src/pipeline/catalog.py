from dataclasses import dataclass


@dataclass(frozen=True)
class ComponentCatalog:

    sources: dict[str, str]

    transformers: dict[str, str]

    sinks: dict[str, str]


CATALOG = ComponentCatalog(

    sources={
        "feriados_api":
            "src.sources.feriados_api.FeriadosAPISource",
    },


    transformers={
        "holidays":
            "src.transformers.holidays.normalize_holidays",
    },


    sinks={

        "duckdb":
            "src.sinks.duckdb.DuckDBSink",

        "parquet":
            "src.sinks.parquet.ParquetSink",

        "json":
            "src.sinks.json.JsonSink",

    },
)