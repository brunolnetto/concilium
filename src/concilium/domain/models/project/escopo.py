"""Entidades de domínio: Escopo e PlanoTrabalho (ADR-031).

Escopo representa uma obra específica dentro de um projeto (lote, fase, subdivisão
contratual). PlanoTrabalho representa um planejamento nomeado e paralelo para um escopo.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    pass

StatusPlano = Literal["RASCUNHO", "EM_ANALISE", "APROVADO", "ARQUIVADO"]


class Escopo(BaseModel):
    """Unidade de pipeline dentro de um projeto (ADR-031 §D1).

    Representa uma obra específica (lote, fase, subdivisão contratual) com sua
    própria EAP, tipo de obra, datas e cronograma independente. O pipeline
    (skills 00->11) opera sobre um Escopo + PlanoTrabalho, não sobre o Projeto.
    """

    model_config = ConfigDict(extra="ignore")

    escopo_id: str = Field(description="Slug único dentro do projeto. Ex.: 'lote-a', 'default'.")
    projeto_id: str = Field(description="UUID do projeto pai.")
    nome: str = Field(description="Nome legível. Ex.: 'Lote A — Terraplenagem'.")
    tipo_obra: Literal["terraplenagem", "pavimentacao", "saneamento"]
    localizacao: str
    coordenadas_lat: float = Field(ge=-90, le=90)
    coordenadas_lng: float = Field(ge=-180, le=180)
    dias_semana: int = Field(default=6, ge=1, le=7)
    horas_dia: int = Field(default=8, ge=1, le=24)
    data_inicio: date
    data_termino: date
    status: Literal["RASCUNHO", "EM_VALIDACAO", "APROVADO", "EM_EXECUCAO", "CONCLUIDO"] = "RASCUNHO"
    criado_em: datetime = Field(default_factory=lambda: datetime.now())
    # ADR-033: Arbitragem temporal para congelamento de preços de orçamento
    data_base_orcamento: date | None = Field(
        default=None, description="Data de referência para resgate de preços de insumos"
    )
    tag_versao_catalogo: str | None = Field(default=None, description="Tag da versão importada do Blob Storage")
    # ADR-038: Jurisdição fiscal e geográfica do escopo (determina BDI e preços regionais)
    jurisdicao_id: str | None = Field(
        default=None,
        description="Código da jurisdição (ex.: 'BR-CE'). Usado para resolver preços regionais e alíquotas BDI.",
    )
    # ADR-129 D5: raio de busca por proximidade geográfica (cotação de preços regionais)
    raio_cotacao_km: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Raio (km) para resolução de preço por município mais próximo às coordenadas do "
            "escopo (ADR-129 D2). None (default) preserva o comportamento atual por UF — a "
            "camada de proximidade é opt-in por este campo, não pela mera presença de coordenadas."
        ),
    )
    # Snapshots de catálogo e perfil BDI (podem diferir entre escopos do mesmo projeto)
    snapshot_catalogo_id: str = ""
    snapshot_perfil_id: str = ""
    bdi_perfil_id: str | None = None
    revisao: int = Field(default=1, ge=1)


class PlanoTrabalho(BaseModel):
    """Instância de planejamento para um escopo (ADR-031 §D2).

    Múltiplos planos coexistem em paralelo para o mesmo escopo. Cada plano tem
    seu próprio pipeline independente (canonical isolado).

    Ciclo de vida:
      RASCUNHO -> EM_ANALISE -> APROVADO
                             ↘ ARQUIVADO
    """

    model_config = ConfigDict(extra="ignore")

    plano_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="UUID gerado automaticamente ou slug descritivo.",
    )
    escopo_id: str
    projeto_id: str
    nome: str = Field(description="Ex.: 'Plano Agressivo — 4 equipes'.")
    status: StatusPlano = "RASCUNHO"
    criado_em: datetime = Field(default_factory=lambda: datetime.now())
    # Hipótese principal que diferencia este plano dos demais (opcional, livre)
    hipotese: str | None = None
    # Iteração dentro do mesmo plano (copy-on-write incremental)
    versao_iteracao: int = Field(default=1, ge=1)
