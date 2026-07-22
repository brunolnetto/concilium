"""API routes de observabilidade — ADR-112.

Expõe dados paginados das camadas Bronze (raw), Silver (normalizado) e Gold (agregado)
para consumo por ferramentas de análise, dashboards e integrações externas.

Endpoints:
  GET  /observability/gold/sli                  — SLI diário (p50/p95/p99 por skill)
  GET  /observability/gold/fallback-rate        — taxa de fallbacks por skill
  GET  /observability/gold/alertas              — alertas ativos
  GET  /observability/gold/cross-domain         — fallback rate × resultado financeiro por projeto
  GET  /observability/gold/tool-usage           — uso diário de tools MCP por status
  GET  /observability/gold/cubo/contrato        — dimensões/medidas disponíveis por cubo (ADR-147)
  GET  /observability/gold/cubo/{cubo}/projecao — projeção ad-hoc de um cubo Gold (ADR-147)
  GET  /observability/silver/{signal_type}      — records Silver normalizados (paginados)
  GET  /observability/bronze/{signal_type}      — records Bronze raw (paginados)
  GET  /observability/status                    — checkpoints por tipo de sinal
  GET  /observability/audit                     — invocações MCP recentes (ADR-118)
  POST /observability/pipeline/run              — dispara ciclo Bronze→Silver→Gold on-demand
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query

router = APIRouter(prefix="/observability", tags=["observability"])

_SIGNAL_TYPES = {"logs", "traces", "metrics", "tool_invocations"}

# ── Cubos Gold (ADR-147) — contrato navegável, mesmo padrão de cubo-analitico ──
# group_by/medidas do cliente são validados contra estes whitelists por cubo —
# nenhuma expressão SQL chega do cliente, só nomes de dimensão/medida do contrato.

_CUBO_NOME = Literal["spans", "logs", "metricas", "tool_invocations"]

_CUBO_DIMENSOES: dict[str, tuple[str, ...]] = {
    "spans": ("date", "skill_id", "project_id", "tool_name", "user_id", "status"),
    "logs": ("date", "skill_id", "project_id", "user_id", "severity", "fallback_type"),
    "metricas": ("date", "metric_name", "skill_id", "project_id", "tool_name", "status"),
    "tool_invocations": ("date", "tool_name", "user_id", "device_id", "status"),
}

_CUBO_MEDIDAS: dict[str, dict[str, str]] = {
    "spans": {
        "n": "COUNT(*)",
        "avg_ms": "AVG(duration_ms)",
        "p50_ms": "PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY duration_ms)",
        "p95_ms": "PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms)",
        "p99_ms": "PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duration_ms)",
    },
    "logs": {
        "n_total": "COUNT(*)",
        "n_fallbacks": "COUNT(*) FILTER (WHERE fallback_type IS NOT NULL)",
        "fallback_rate": (
            "ROUND(CAST(COUNT(*) FILTER (WHERE fallback_type IS NOT NULL) AS DOUBLE)"
            " / NULLIF(COUNT(*), 0), 4)"
        ),
    },
    "metricas": {
        "n": "COUNT(*)",
        "sum_value": "SUM(value)",
        "avg_value": "AVG(value)",
        "min_value": "MIN(value)",
        "max_value": "MAX(value)",
    },
    "tool_invocations": {
        "n": "COUNT(*)",
        "avg_ms": "AVG(duration_ms)",
        "p95_ms": "PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms)",
        "n_errors": "COUNT(*) FILTER (WHERE status != 'success')",
    },
}


def _build_cubo(cubo: str, storage: Any) -> Any:
    from concilium.infrastructure.observability.cubo_logs import CuboLogs
    from concilium.infrastructure.observability.cubo_metricas import CuboMetricas
    from concilium.infrastructure.observability.cubo_spans import CuboSpans
    from concilium.infrastructure.observability.cubo_tool_invocations import CuboToolInvocations
    from concilium.infrastructure.observability.pipeline import read_silver_records

    signal_por_cubo = {"spans": "traces", "logs": "logs", "metricas": "metrics", "tool_invocations": "tool_invocations"}
    classe_por_cubo = {
        "spans": CuboSpans,
        "logs": CuboLogs,
        "metricas": CuboMetricas,
        "tool_invocations": CuboToolInvocations,
    }
    records = read_silver_records(storage, signal_por_cubo[cubo])
    return classe_por_cubo[cubo].from_silver(records)


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


def _filter_eq(rows: list[dict[str, Any]], field: str, value: Any) -> list[dict[str, Any]]:
    if not value:
        return rows
    return [r for r in rows if r.get(field) == value]


def _filter_min(rows: list[dict[str, Any]], field: str, min_value: float | None) -> list[dict[str, Any]]:
    if min_value is None:
        return rows
    return [r for r in rows if (r.get(field) or 0.0) >= min_value]


def _filter_fallback_rows(
    rows: list[dict[str, Any]], skill_id: str | None, date: str | None, min_rate: float | None
) -> list[dict[str, Any]]:
    rows = _filter_eq(rows, "skill_id", skill_id)
    rows = _filter_eq(rows, "date", date)
    return _filter_min(rows, "fallback_rate", min_rate)


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
    rows = _filter_fallback_rows(rows, skill_id, date, min_rate)
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


@router.get(
    "/gold/tool-usage",
    summary="Uso diário de tools MCP por status (ADR-147 D7)",
    response_model=None,
)
def get_tool_usage(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    tool_name: str | None = Query(None),
    status: str | None = Query(None),
    date: str | None = Query(None),
    storage=Depends(_get_storage),
) -> dict[str, Any]:
    from concilium.infrastructure.observability.gold_aggregator import GoldAggregator

    agg = GoldAggregator(storage)
    rows = agg.build_tool_usage_diario()
    rows = _filter_eq(rows, "tool_name", tool_name)
    rows = _filter_eq(rows, "status", status)
    rows = _filter_eq(rows, "date", date)
    return _paginate(rows, page, page_size)


# ── Cubos Gold — projeção ad-hoc (ADR-147) ────────────────────────────────────


@router.get(
    "/gold/cubo/contrato",
    summary="Contrato navegável dos cubos Gold — dimensões e medidas por cubo",
    response_model=None,
)
def get_cubo_contrato() -> dict[str, Any]:
    return {
        "cubos": {
            nome: {"dimensoes": list(_CUBO_DIMENSOES[nome]), "medidas": list(_CUBO_MEDIDAS[nome].keys())}
            for nome in _CUBO_DIMENSOES
        }
    }


@router.get(
    "/gold/cubo/{cubo}/projecao",
    summary="Projeção ad-hoc de um cubo Gold — qualquer combinação de dimensões/medidas do contrato",
    response_model=None,
)
def get_cubo_projecao(
    cubo: _CUBO_NOME,
    group_by: str = Query(..., description="Dimensões separadas por vírgula — ver /gold/cubo/contrato"),
    medidas: str = Query(..., description="Medidas separadas por vírgula — ver /gold/cubo/contrato"),
    date: str | None = Query(None),
    skill_id: str | None = Query(None),
    project_id: str | None = Query(None),
    tool_name: str | None = Query(None),
    user_id: str | None = Query(None),
    status: str | None = Query(None),
    device_id: str | None = Query(None),
    severity: str | None = Query(None),
    fallback_type: str | None = Query(None),
    metric_name: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    storage=Depends(_get_storage),
) -> dict[str, Any]:
    dims_validas = _CUBO_DIMENSOES[cubo]
    medidas_validas = _CUBO_MEDIDAS[cubo]

    dims = [d.strip() for d in group_by.split(",") if d.strip()]
    med_names = [m.strip() for m in medidas.split(",") if m.strip()]

    invalid_dims = [d for d in dims if d not in dims_validas]
    if invalid_dims:
        raise HTTPException(
            400, detail=f"Dimensões inválidas para '{cubo}': {invalid_dims}. Válidas: {list(dims_validas)}"
        )
    invalid_medidas = [m for m in med_names if m not in medidas_validas]
    if invalid_medidas:
        raise HTTPException(
            400, detail=f"Medidas inválidas para '{cubo}': {invalid_medidas}. Válidas: {list(medidas_validas)}"
        )

    filtros_brutos = {
        "date": date,
        "skill_id": skill_id,
        "project_id": project_id,
        "tool_name": tool_name,
        "user_id": user_id,
        "status": status,
        "device_id": device_id,
        "severity": severity,
        "fallback_type": fallback_type,
        "metric_name": metric_name,
    }
    filtros = {k: v for k, v in filtros_brutos.items() if v is not None and k in dims_validas}

    cubo_obj = _build_cubo(cubo, storage)
    if filtros:
        cubo_obj = cubo_obj.slice(**filtros)
    aggs = {m: medidas_validas[m] for m in med_names}
    rows = cubo_obj.query(group_by=dims, aggs=aggs)
    return _paginate(rows, page, page_size)


# ── Silver endpoints ──────────────────────────────────────────────────────────


def _filter_silver_records(
    records: list[dict[str, Any]],
    severity: str | None,
    fallback_type: str | None,
    skill_id: str | None,
) -> list[dict[str, Any]]:
    if severity:
        records = [r for r in records if r.get("severity") == severity.upper()]
    records = _filter_eq(records, "fallback_type", fallback_type)
    return _filter_eq(records, "skill_id", skill_id)


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
    records = _filter_silver_records(records, severity, fallback_type, skill_id)
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
    import dataclasses

    from concilium.infrastructure.observability.checkpoint_store import CheckpointStore

    store = CheckpointStore(storage)
    checkpoints = {}
    for sig in sorted(_SIGNAL_TYPES):
        cp = store.load(sig)
        checkpoints[sig] = dataclasses.asdict(cp) if cp else None
    return {"checkpoints": checkpoints}


# ── Audit endpoints (ADR-118) ─────────────────────────────────────────────────


@router.get(
    "/audit",
    summary="Invocações MCP recentes — audit log de tools (ADR-118)",
    response_model=None,
)
def get_audit(
    limit: int = Query(100, ge=1, le=1000, description="Máximo de registros"),
    tool_name: str | None = Query(None, description="Filtrar por nome da tool"),
    user_id: str | None = Query(None, description="Filtrar por user_id"),
    status: str | None = Query(None, description="Filtrar por status: success | failed"),
) -> dict[str, Any]:
    from concilium.infrastructure.storage.store_factory import get_tool_invocation_store

    repo = get_tool_invocation_store()
    if tool_name:
        records = repo.list_by_tool(tool_name, limit=limit)
    elif user_id:
        records = repo.list_by_user(user_id, limit=limit)
    else:
        records = repo.list_recent(limit=limit)
    if status:
        records = [r for r in records if r.status == status]
    total = repo.count()
    return {
        "items": [r.to_dict() for r in records],
        "total_persisted": total,
        "returned": len(records),
    }


# ── Gold cross-domain endpoint (ADR-112 F8) ───────────────────────────────────


@router.get(
    "/gold/cross-domain",
    summary="Fallback rate × resultado financeiro por projeto (ADR-112 F8)",
    response_model=None,
)
def get_cross_domain(storage=Depends(_get_storage)) -> dict[str, Any]:
    import json

    path = "observability/gold/cross_domain.json"
    try:
        raw = storage.ler_blob(path)
        data = json.loads(raw.decode("utf-8"))
    except FileNotFoundError:
        data = []
    return {"items": data, "total": len(data)}


# ── Pipeline trigger (on-demand) ──────────────────────────────────────────────


@router.post(
    "/pipeline/run",
    summary="Dispara ciclo Bronze→Silver→Gold on-demand (dev/ops)",
    response_model=None,
)
def run_pipeline(
    force_gold: bool = Body(False, embed=True, description="Força execução do Gold mesmo fora do intervalo"),
    storage=Depends(_get_storage),
) -> dict[str, Any]:
    import datetime

    from concilium.infrastructure.observability.pipeline import ObservabilityScheduler

    scheduler = ObservabilityScheduler(
        storage,
        silver_interval_min=0,
        gold_interval_min=0 if force_gold else 60,
    )
    result = scheduler.run_cycle(now=datetime.datetime.now(datetime.UTC))
    return result
