from .registry import load_component


class PipelineRunner:


    def __init__(
        self,
        config,
        *,
        context=None,
    ):
        self.config = config
        self.context = context or {}



    async def run(self):

        print(
            f"Running pipeline: {self.config.name}"
        )


        source = self.create_source()


        raw = await source.extract()


        data = raw


        for transformer in (
            self.config.transformers
        ):

            fn = load_component(
                transformer
            )

            data = fn(
                data,
                **self.context,
            )



        sink = self.create_sink()


        sink.write(
            data,
            **self.config.destination_options,
        )



    def create_source(self):

        sources = {

            "feriados_api":
                "src.sources.feriados_api.FeriadosAPISource"

        }


        component = load_component(
            sources[
                self.config.source
            ]
        )


        return component(
            **self.context,
            **self.config.source_options,
        )



    def create_sink(self):

        sinks = {

            "duckdb":
                "src.sinks.duckdb.DuckDBSink",

            "parquet":
                "src.sinks.parquet.ParquetSink",

            "json":
                "src.sinks.json.JsonSink",

            "csv":
                "src.sinks.csv.CsvSink",

        }


        component = load_component(
            sinks[
                self.config.destination
            ]
        )


        return component()