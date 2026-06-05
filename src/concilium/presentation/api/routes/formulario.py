"""REST endpoints do formulário QQP/EAP — ADR-092.

POST /api/formulario/sugerir-cpus  — mapeia serviços → cpu_ids (sem criar projeto)
POST /api/formulario/projeto       — cria projeto completo a partir de serviços
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from concilium.infrastructure.auth.permission_guard import permission
from concilium.presentation.api.rate_limit import limiter

router = APIRouter(prefix="/api/formulario", tags=["projects - runs"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class ServicoInput(BaseModel):
    descricao: str
    quantidade: float = Field(ge=0)
    unidade: str = "un"
    cpu_id: str | None = None
    predecessores: list[dict[str, Any]] = Field(default_factory=list)
    item_id: str | None = None


class SugerirCpusRequest(BaseModel):
    servicos: list[ServicoInput]


class CriarProjetoFormularioRequest(BaseModel):
    nome: str
    contexto_id: str
    tipo_obra: str
    localizacao: str
    data_inicio: str = Field(description="YYYY-MM-DD")
    servicos: list[ServicoInput]
    data_termino: str | None = None
    coordenadas_lat: float = 0.0
    coordenadas_lng: float = 0.0
    dias_semana: int = Field(default=6, ge=1, le=7)
    horas_dia: int = Field(default=8, ge=4, le=12)
    objetivo_pool: str = "balanceado"


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/sugerir-cpus",
    summary="Sugerir cpu_ids para uma lista de serviços (sem criar projeto)",
    status_code=status.HTTP_200_OK,
)
@limiter.limit("60/minute")
@permission("catalog:read")
def sugerir_cpus(request: Request, response: Response, body: SugerirCpusRequest) -> dict[str, Any]:
    """Mapeia descrições de serviços para cpu_ids sem criar o projeto.

    Útil para pré-visualização no formulário UI antes do submit final.
    """
    from concilium.application.services.formulario_service import build_eap

    result = build_eap([s.model_dump() for s in body.servicos])
    return {
        "mapeados": [
            {
                "descricao": it["descricao"],
                "cpu_id": it["cpu_id"],
                "confianca": it["_confianca"],
                "item_id": it["item_id"],
            }
            for it in result["mapeados"]
        ],
        "nao_mapeados": [
            {"descricao": it["descricao"], "item_id": it["item_id"]}
            for it in result["nao_mapeados"]
        ],
        "total": result["total"],
        "todos_mapeados": len(result["nao_mapeados"]) == 0,
    }


@router.post(
    "/projeto",
    summary="Criar projeto a partir de lista de serviços QQP (ADR-092)",
    status_code=status.HTTP_200_OK,
)
@limiter.limit("10/minute")
@permission("project:create")
def criar_projeto_formulario(
    request: Request,
    response: Response,
    body: CriarProjetoFormularioRequest,
) -> dict[str, Any]:
    """Traduz QQP (serviços em linguagem natural) para EAP e cria o projeto.

    Se todos os serviços forem mapeados: cria o projeto e retorna `project_id`.
    Se houver itens sem cpu_id: retorna preview para o usuário corrigir.

    Para itens não mapeados, use `GET /api/catalogs/cpus?q=<termo>` para
    encontrar o cpu_id e repita a chamada com `cpu_id` preenchido.
    """
    from concilium.application.services.formulario_service import criar_projeto

    try:
        result = criar_projeto(
            nome=body.nome,
            contexto_id=body.contexto_id,
            tipo_obra=body.tipo_obra,
            localizacao=body.localizacao,
            data_inicio=body.data_inicio,
            servicos=[s.model_dump() for s in body.servicos],
            data_termino=body.data_termino or "",
            coordenadas_lat=body.coordenadas_lat,
            coordenadas_lng=body.coordenadas_lng,
            dias_semana=body.dias_semana,
            horas_dia=body.horas_dia,
            objetivo_pool=body.objetivo_pool,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result.get("status") == "erro":
        raise HTTPException(status_code=400, detail=result.get("erro", "Erro desconhecido"))

    return result
