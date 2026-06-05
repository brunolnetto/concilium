"""Modelo ContextoObra — agrega os IDs de configuração de uma obra."""

from pydantic import BaseModel, ConfigDict


class ContextoObra(BaseModel):
    """Agrega os IDs de configuração que definem o contexto de planejamento de uma obra.

    Armazenado em config/contextos/{id}.json.
    Permite que o Runtime resolva perfil, jurisdição, referência, catálogo e tema
    a partir de um único identificador.

    ADR-065: tema_id substitui identidade_visual (dict não-tipado) → TemaVisual.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    perfil_id: str
    jurisdicao_id: str
    referencia_id: str
    catalogo_id: str
    tema_id: str | None = None  # ADR-065: None → Runtime usa tema "default"
