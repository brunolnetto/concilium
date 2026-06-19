"""API routes de observabilidade — ADR-112.

Expõe dados paginados das camadas Bronze (raw), Silver (normalizado) e Gold (agregado)
para consumo por ferramentas de análise, dashboards e integrações externas.

Endpoints:
  GET /observability/gold/sli                  — SLI diário (p50/p95/p99 por skill)
  GET /observability/gold/fallback-rate        — taxa de fallbacks por skill
  GET /observability/gold/alertas              — alertas ativos
  GET /observability/silver/{signal_type}      — records Silver normalizados (paginados)
  GET /observability/bronze/{signal_type}      — records Bronze raw (paginados)
  GET /observability/status                    — checkpoints por tipo de sinal
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

router = APIRouter(prefix="/observability", tags=["observability"])

_SIGNAL_TYPES = {"logs", "traces", "metrics"}


# ── Dependency: storage ───────────────────────────────────────────────────────

def _get_storage():
    """Retorna o BlobStorage configurado para observabilidade."""
    from concilium.infrastructure.observability.pipeline import _make_storage
    return _make_storage()


# ── Helpers de paginação ─────────────────────────────────────────────────────

def _paginate(items: list[Any], page: int, page_size: int) -> dict[str, Any]:
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": items[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


def _read_silver_records(storage, signal_type: str) -> list[dict[str, Any]]:
    import json
    blobs = sorted(storage.listar_blobs(f"observability/silver/{signal_type}/"))
    records: list[dict[str, Any]] = []
    for path in blobs:
        try:
            raw = storage.ler_blob(path).decode("utf-8")
            for line in raw.splitlines():
                if line.strip():
                    records.append(json.loads(line))
        except Exception:
            pass
    return records


def _read_bronze_records(storage, signal_type: str, date: str | None) -> list[dict[str, Any]]:
    import json
    prefix = f"observability/bronze/{signal_type}/"
    if date:
        prefix += f"{date}/"
    blobs = sorted(storage.listar_blobs(prefix))
    records: list[dict[str, Any]] = []
    for path in blobs:
        try:
            raw = storage.ler_blob(path).decode("utf-8")
            for line in raw.splitlines():
                if line.strip():
                    records.append(json.loads(line))
        except Exception:
            pass
    return records


# ── Gold endpoints ────────────────────────────────────────────────────────────

@router.get(
    "/gold/sli",
    summary="SLI diário — p50/p95/p99 de duration_ms por skill",
    response_model=None,
)
def get_sli_diario(
    page: int = Query(1, ge=1, description="Página (1-indexed)"),
    page_size: int = Query(50, ge=1, le=500, description="Registros por página"),
    skill_id: str | None = Query(None, description="Filtrar por skill_id"),
    date: str | None = Query(None, description="Filtrar por data ISO (YYYY-MM-DD)"),
    storage=Depends(_get_storage),
) -> dict[str, Any]:
    from concilium.infrastructure.observability.gold_aggregator import GoldAggregator
    agg = GoldAggregator(storage)
    rows = agg.build_sli_diario()
    if skill_id:
        rows = [r for r in rows if r.get("skill_id") == skill_id]
    if date:
        rows = [r for r in rows if r.get("date") == date]
    return _paginate(rows, page, page_size)


@router.get(
    "/gold/fallback-rate",
    summary="Taxa de fallbacks por skill (ADR-110 patterns)",
    response_model=None,
)
def get_fallback_rate(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    skill_id: str | None = Query(None),
    date: str | None = Query(None),
    min_rate: float | None = Query(None, ge=0.0, le=1.0, description="Filtrar por taxa mínima"),
    storage=Depends(_get_storage),
) -> dict[str, Any]:
    from concilium.infrastructure.observability.gold_aggregator import GoldAggregator
    agg = GoldAggregator(storage)
    rows = agg.build_fallback_rate_por_skill()
    if skill_id:
        rows = [r for r in rows if r.get("skill_id") == skill_id]
    if date:
        rows = [r for r in rows if r.get("date") == date]
    if min_rate is not None:
        rows = [r for r in rows if (r.get("fallback_rate") or 0.0) >= min_rate]
    return _paginate(rows, page, page_size)


@router.get(
    "/gold/alertas",
    summary="Alertas ativos (p99 > 30s ou fallback_rate > 5%)",
    response_model=None,
)
def get_alertas_ativos(
    tipo: str | None = Query(None, description="Filtrar por tipo: p99_alto | fallback_alto"),
    storage=Depends(_get_storage),
) -> dict[str, Any]:
    from concilium.infrastructure.observability.gold_aggregator import GoldAggregator
    agg = GoldAggregator(storage)
    alertas = agg.build_alertas_ativos()
    if tipo:
        alertas = [a for a in alertas if a.get("tipo") == tipo]
    return {"alertas": alertas, "total": len(alertas)}


# ── Silver endpoints ──────────────────────────────────────────────────────────

@router.get(
    "/silver/{signal_type}",
    summary="Records Silver normalizados (com fallback_type para logs)",
    response_model=None,
)
def get_silver(
    signal_type: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    severity: str | None = Query(None, description="Filtrar por severity (logs)"),
    fallback_type: str | None = Query(None, description="Filtrar por fallback_type (logs)"),
    skill_id: str | None = Query(None),
    storage=Depends(_get_storage),
) -> dict[str, Any]:
    if signal_type not in _SIGNAL_TYPES:
        raise HTTPException(400, detail=f"signal_type inválido: '{signal_type}'. Use: {sorted(_SIGNAL_TYPES)}")
    records = _read_silver_records(storage, signal_type)
    if severity:
        records = [r for r in records if r.get("severity") == severity.upper()]
    if fallback_type:
        records = [r for r in records if r.get("fallback_type") == fallback_type]
    if skill_id:
        records = [r for r in records if r.get("skill_id") == skill_id]
    return _paginate(records, page, page_size)


# ── Bronze endpoints ──────────────────────────────────────────────────────────

@router.get(
    "/bronze/{signal_type}",
    summary="Records Bronze raw — dados brutos antes da normalização",
    response_model=None,
)
def get_bronze(
    signal_type: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    date: str | None = Query(None, description="Filtrar por data ISO (YYYY-MM-DD)"),
    storage=Depends(_get_storage),
) -> dict[str, Any]:
    if signal_type not in _SIGNAL_TYPES:
        raise HTTPException(400, detail=f"signal_type inválido: '{signal_type}'. Use: {sorted(_SIGNAL_TYPES)}")
    records = _read_bronze_records(storage, signal_type, date)
    return _paginate(records, page, page_size)


# ── Status endpoint ───────────────────────────────────────────────────────────

@router.get(
    "/status",
    summary="Checkpoints do pipeline — último blob processado por sinal",
    response_model=None,
)
def get_status(storage=Depends(_get_storage)) -> dict[str, Any]:
    from concilium.infrastructure.observability.checkpoint_store import CheckpointStore
    import dataclasses

    store = CheckpointStore(storage)
    checkpoints = {}
    for sig in sorted(_SIGNAL_TYPES):
        cp = store.load(sig)
        checkpoints[sig] = dataclasses.asdict(cp) if cp else None
    return {"checkpoints": checkpoints}
