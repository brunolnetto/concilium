from dataclasses import dataclass

from src.client import FeriadosClient


@dataclass(slots=True)
class PipelineContext:

    client: FeriadosClient