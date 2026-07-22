"""Silver Normalizer — ADR-112 F3.

Transforma records Bronze (OTLP JSON raw / _JsonFormatter JSON) em schema Silver normalizado.
Classifica fallback_type baseado nos padrões da ADR-110.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Classificação de fallback_type (padrões da ADR-110)
# ─────────────────────────────────────────────────────────────────────────────

_FALLBACK_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("preco_unitario", re.compile(r"preco_unitario|sem preco", re.I)),
    ("bdi_ausente", re.compile(r"BDI sem taxa|bdi.*ausente", re.I)),
    ("cpu_fallback", re.compile(r"Falha ao resolver CPU|CPU.*não encontrad", re.I)),
    ("producao_horaria", re.compile(r"produção horária não encontrada|producao_horaria não encontrad", re.I)),
    ("contexto_fallback", re.compile(r"Falha ao resolver contexto", re.I)),
    ("canonical_fallback", re.compile(r"Falha ao carregar canonical", re.I)),
    ("conversion_float", re.compile(r"Conversão float falhou", re.I)),
]


def classify_fallback_type(message: str, logger_name: str = "") -> str | None:
    """Classifica o tipo de fallback com base na mensagem e nome do logger.

    Retorna o tipo mais específico encontrado, ou None se não reconhecido.
    """
    combined = f"{message} {logger_name}"
    for fallback_type, pattern in _FALLBACK_PATTERNS:
        if pattern.search(combined):
            return fallback_type
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Extração de skill_id
# ─────────────────────────────────────────────────────────────────────────────

_SKILL_ID_RE = re.compile(r"(?:skills?[./](?:manifests?[./])?|skill[_-])(\d{2})", re.I)


def _extract_skill_id(logger_name: str) -> str | None:
    """Extrai o número da skill do logger name (ex: concilium.skills.manifests.05-... → '05')."""
    m = _SKILL_ID_RE.search(logger_name)
    return m.group(1) if m else None


# ─────────────────────────────────────────────────────────────────────────────
# event_id determinístico
# ─────────────────────────────────────────────────────────────────────────────


def _make_event_id(record: dict[str, Any]) -> str:
    """Gera event_id determinístico para dedup na Silver.

    Prefere span_id quando disponível (mais específico).
    Fallback: hash SHA1 de (ts, logger, message).
    """
    span_id = record.get("span_id") or ""
    if span_id and span_id != "0" * 16:
        return span_id
    raw = f"{record.get('ts', '')}{record.get('logger', '')}{record.get('message', '')}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _make_metric_event_id(record: dict[str, Any]) -> str:
    """Gera event_id determinístico para dedup de metric data points na Silver.

    ts + metric_name sozinhos colidem quando duas séries do mesmo metric (labels
    diferentes) caem na mesma coleta periódica — ex.: concilium.mcp.tool.calls
    com dois tools distintos no mesmo ciclo. Inclui um hash das labels
    (ordenadas, para não depender da ordem de inserção do dict) para
    diferenciá-las sem perder idempotência entre reprocessamentos/backfill.
    """
    labels = record.get("labels") or {}
    raw = f"{record.get('ts', '')}{record.get('metric_name', '')}{json.dumps(labels, sort_keys=True, default=str)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


# ─────────────────────────────────────────────────────────────────────────────
# Dedup entre arquivos Silver
# ─────────────────────────────────────────────────────────────────────────────


def record_key(rec: dict[str, Any]) -> str:
    """Chave de dedup de um record Silver — mesmo critério do upsert dentro de um
    arquivo (event_id > span_id > ts+metric_name > id do objeto)."""
    return (
        rec.get("event_id")
        or rec.get("span_id")
        or f"{rec.get('ts', '')}{rec.get('metric_name', '')}"
        or str(id(rec))
    )


def dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplica records por record_key(), mantendo a última ocorrência.

    Necessário ao ler MÚLTIPLOS arquivos Silver (um por dia): se um dia for
    reprocessado depois de já existir um arquivo com o particionamento antigo
    (ex.: antes do fix de particionamento por data do blob Bronze), o mesmo
    event_id pode aparecer em dois arquivos — sem isso, Gold conta em dobro.
    """
    deduped: dict[str, dict[str, Any]] = {}
    for rec in records:
        deduped[record_key(rec)] = rec
    return list(deduped.values())


# ─────────────────────────────────────────────────────────────────────────────
# Normalização
# ─────────────────────────────────────────────────────────────────────────────


def normalize_log_record(record: dict[str, Any]) -> dict[str, Any]:
    """Normaliza um log record Bronze → schema Silver logs."""
    logger_name = record.get("logger", "")
    message = record.get("message", "")
    return {
        "event_id": _make_event_id(record),
        "trace_id": record.get("trace_id", ""),
        "span_id": record.get("span_id", ""),
        "ts": record.get("ts", ""),
        "severity": record.get("severity", ""),
        "logger": logger_name,
        "message": message,
        "service": record.get("service", ""),
        "project_id": record.get("project_id"),
        "skill_id": _extract_skill_id(logger_name),
        "fallback_type": classify_fallback_type(message, logger_name),
        "user_id": record.get("user_id") or None,
        "request_id": record.get("request_id") or None,
    }


def normalize_span_record(record: dict[str, Any]) -> dict[str, Any]:
    """Normaliza um span record Bronze → schema Silver traces."""
    return {
        "span_id": record.get("span_id", ""),
        "trace_id": record.get("trace_id", ""),
        "parent_span_id": record.get("parent_span_id"),
        "service": record.get("service", ""),
        "operation": record.get("operation", ""),
        "start_ts": record.get("start_ts", ""),
        "end_ts": record.get("end_ts", ""),
        "duration_ms": int(record.get("duration_ms", 0)),
        "status": record.get("status", ""),
        "project_id": record.get("project_id"),
        "skill_id": record.get("skill_id") or _extract_skill_id(record.get("operation", "")),
        "tool_name": record.get("tool_name"),
        "user_id": record.get("user_id"),
        "request_id": record.get("request_id"),
    }


def normalize_metric_record(record: dict[str, Any]) -> dict[str, Any]:
    """Normaliza um metric record Bronze → schema Silver metrics.

    Projeção dimensional (ADR-146, "status" adicionada na ADR-147): as chaves
    canônicas de label ("skill", "tool", "project.id", "status" — ver
    METRIC_LABEL_* em infrastructure/telemetry, o dono do contrato; este
    módulo permanece puro e usa os literais) são promovidas a colunas de
    primeira classe, tornando DIM_SKILL/DIM_TOOL/DIM_PROJECT/DIM_STATUS
    alcançáveis sem parsear `labels`. A promoção é aditiva — `labels` segue
    íntegro para fidelidade — e retroativa, pois essas chaves são o que a
    instrumentação sempre emitiu.
    """
    labels = record.get("labels") or {}
    return {
        "event_id": _make_metric_event_id(record),
        "metric_name": record.get("metric_name", ""),
        "ts": record.get("ts", ""),
        "value": float(record.get("value", 0.0)),
        "labels": labels,
        "service": record.get("service", ""),
        "skill_id": labels.get("skill"),
        "tool_name": labels.get("tool"),
        "project_id": labels.get("project.id"),
        "status": labels.get("status"),
    }


def normalize_tool_invocation_record(record: dict[str, Any]) -> dict[str, Any]:
    """Normaliza um tool_invocation record Bronze → schema Silver tool_invocations.

    "event_id" (não "id") é deliberado: reaproveita o fallback de dedup já
    existente em record_key()/dedupe_records(), que prioriza event_id — sem
    isso, este sinal cairia no fallback genérico str(id(rec)), que nunca dedupa.
    """
    return {
        "event_id": record.get("id", ""),
        "tool_name": record.get("tool_name", ""),
        "user_id": record.get("user_id"),
        "tenant_id": record.get("tenant_id"),
        "status": record.get("status", ""),
        "started_at": record.get("started_at", ""),
        "finished_at": record.get("finished_at", ""),
        "error_type": record.get("error_type"),
        "device_id": record.get("device_id"),
        "mcp_session_id": record.get("mcp_session_id"),
    }
