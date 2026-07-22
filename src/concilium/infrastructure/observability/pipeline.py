"""ObservabilityWorker — ADR-112 F4.

Orquestra Bronze → Silver com fast-forward incremental e idempotência por event_id.
Silver é persistido no BlobStorage como NDJSON, garantindo que GoldAggregator
acesse os mesmos dados via o mesmo storage.
"""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any

from concilium.domain.repositories.blob_storage_port import BlobStoragePort

from .checkpoint_store import Checkpoint, CheckpointStore
from .silver_normalizer import (
    dedupe_records,
    normalize_log_record,
    normalize_metric_record,
    normalize_span_record,
    normalize_tool_invocation_record,
    record_key,
)

logger = logging.getLogger(__name__)

_BRONZE_PREFIX = "observability/bronze"
_SILVER_PREFIX = "observability/silver"

_NORMALIZERS = {
    "logs": normalize_log_record,
    "traces": normalize_span_record,
    "metrics": normalize_metric_record,
    "tool_invocations": normalize_tool_invocation_record,
}


def _make_storage() -> BlobStoragePort:
    """Cria o storage de observabilidade a partir de CONCILIUM__STORE_BACKEND.

    Observabilidade é dado de sistema (não de projeto), então usa o mesmo
    container/bucket/Drive "sistema" de auth/distribuição (ver
    build_system_blob_storage). No backend filesystem, preserva o default
    histórico de gravar em {root}/observability/... — os paths internos
    (_BRONZE_PREFIX/_SILVER_PREFIX) já incluem o prefixo "observability/", daí
    o root do storage ser {root} puro, e não {root}/observability (o que
    duplicaria o segmento).
    """
    from concilium.infrastructure.settings import get_storage
    from concilium.infrastructure.storage.store_factory import build_system_blob_storage, resolve_store_backend

    root_override: Path | None = None
    if resolve_store_backend() == "filesystem":
        cfg = get_storage()
        root_override = getattr(cfg, "root", None) or getattr(cfg, "config_root", None) or Path.cwd()
    return build_system_blob_storage(root_override=root_override)


def bronze_storage_for_bootstrap() -> BlobStoragePort | None:
    """Storage do Bronze para conectar ao BronzeLogHandler no bootstrap (ADR-121 D3).

    Retorna None quando OTel está desabilitado (TEST_ENV/CI) ou quando o
    backend configurado falha ao inicializar — nesses casos o logging segue
    sem o handler Bronze em vez de derrubar a aplicação.
    """
    from concilium.infrastructure.settings import get_telemetry

    if get_telemetry().otel_sdk_disabled:
        return None
    try:
        return _make_storage()
    except Exception:
        logger.warning(
            "Bronze storage indisponível no bootstrap; logging seguirá sem BronzeLogHandler.", exc_info=True
        )
        return None


class ObservabilityWorker:
    """Worker Bronze → Silver (ADR-112 D2–D3).

    Processa apenas arquivos Bronze novos desde o último checkpoint (fast-forward).
    Silver é persistido como NDJSON no BlobStorage — GoldAggregator lê do mesmo storage.
    Idempotente: upsert por event_id/span_id garante que re-processamento não duplica.
    """

    def __init__(self, storage: BlobStoragePort):
        self._storage = storage
        self._checkpoints = CheckpointStore(storage)

    # ── Leitura Bronze ──────────────────────────────────────────────────────

    def _read_ndjson(self, blob_path: str) -> list[dict[str, Any]]:
        raw = self._storage.ler_blob(blob_path).decode("utf-8")
        records = []
        for line in raw.splitlines():
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("Linha inválida em %s, ignorada", blob_path)
        return records

    # ── Silver persistido em BlobStorage ───────────────────────────────────

    def _silver_path(self, signal_type: str, date: str) -> str:
        return f"{_SILVER_PREFIX}/{signal_type}/{date}/records.ndjson"

    @staticmethod
    def _blob_date(blob_path: str) -> str:
        """Extrai a data do path do blob Bronze: `.../{signal_type}/{date}/{batch_id}.ndjson`."""
        return blob_path.rsplit("/", 2)[-2]

    def _upsert_silver(self, signal_type: str, records: list[dict[str, Any]], date: str) -> None:
        """Upsert records no Silver NDJSON do dia `date`. Deduplicação por event_id/span_id.

        `date` vem do path do blob Bronze de origem, não de `date.today()` — durante um
        backfill de dias/semanas, cada dia fica em seu próprio arquivo (memória limitada
        ao tamanho de um dia por vez), em vez de tudo colapsar num único arquivo "hoje"
        cada vez maior.
        """
        path = self._silver_path(signal_type, date)
        existing: dict[str, dict[str, Any]] = {}
        try:
            raw = self._storage.ler_blob(path)
            for line in raw.decode("utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    existing[record_key(rec)] = rec
        except FileNotFoundError:
            pass

        for rec in records:
            existing[record_key(rec)] = rec

        content = "\n".join(json.dumps(r, ensure_ascii=False) for r in existing.values()) + "\n"
        self._storage.gravar_blob(path, content.encode("utf-8"))

    def read_silver(self, signal_type: str) -> list[dict[str, Any]]:
        """Retorna todos os records Silver persistidos para o tipo de sinal, deduplicados.

        Dedup entre arquivos (um por dia) é necessário porque um dia pode ter sido
        reprocessado com particionamento diferente do original (ex.: antes do fix
        de particionamento por data do blob Bronze) — sem isso, o mesmo event_id
        apareceria duas vezes.
        """
        blobs = sorted(self._storage.listar_blobs(f"{_SILVER_PREFIX}/{signal_type}/"))
        records: list[dict[str, Any]] = []
        for path in blobs:
            try:
                raw = self._storage.ler_blob(path)
                for line in raw.decode("utf-8").splitlines():
                    if line.strip():
                        records.append(json.loads(line))
            except Exception:
                pass
        return dedupe_records(records)

    # ── Pipeline principal ──────────────────────────────────────────────────

    def _resolve_new_blobs(self, signal_type: str, checkpoint: Checkpoint | None, since: str | None) -> list[str]:
        last_path = checkpoint.last_processed_path if checkpoint else None
        all_blobs = sorted(self._storage.listar_blobs(f"{_BRONZE_PREFIX}/{signal_type}/"))
        if last_path:
            return [b for b in all_blobs if b > last_path]
        if since:
            return [b for b in all_blobs if since in b]
        return all_blobs

    def _process_new_blobs(self, signal_type: str, new_blobs: list[str], normalizer: Any, current_total: int) -> int:
        records_processed = 0
        for blob_path in new_blobs:
            raw_records = self._read_ndjson(blob_path)
            normalized = [normalizer(r) for r in raw_records]
            self._upsert_silver(signal_type, normalized, self._blob_date(blob_path))
            records_processed += len(raw_records)
            current_total += len(raw_records)
            self._checkpoints.save(
                Checkpoint(
                    signal_type=signal_type,
                    last_processed_path=blob_path,
                    last_processed_ts=datetime.datetime.now(datetime.UTC).isoformat(),
                    records_processed=current_total,
                )
            )
        return records_processed

    def run(
        self,
        signal_type: str = "logs",
        full_reload: bool = False,
        since: str | None = None,
    ) -> dict[str, Any]:
        """Processa Bronze → Silver incrementalmente.

        Args:
            signal_type:  "logs" | "traces" | "metrics" | "tool_invocations"
            full_reload:  True → apaga checkpoint e reprocessa tudo
            since:        ISO date string — processa apenas blobs desta data em diante

        Returns:
            {"blobs_processed": N, "records_processed": M}
        """
        if full_reload:
            self._checkpoints.delete(signal_type)

        checkpoint = self._checkpoints.load(signal_type)
        new_blobs = self._resolve_new_blobs(signal_type, checkpoint, since)

        normalizer = _NORMALIZERS.get(signal_type, normalize_log_record)
        current_total = checkpoint.records_processed if checkpoint else 0
        records_processed = self._process_new_blobs(signal_type, new_blobs, normalizer, current_total)

        logger.info(
            "Observability pipeline: %d blobs, %d records (%s)",
            len(new_blobs),
            records_processed,
            signal_type,
        )
        return {"blobs_processed": len(new_blobs), "records_processed": records_processed}


# ─────────────────────────────────────────────────────────────────────────────
# ObservabilityScheduler — ADR-112 F7
# Ciclo time-gated: Bronze→Silver a cada 15min, Silver→Gold a cada 1h.
# Idempotente; a cadência real (cron ACI) é configuração de deploy — esta classe
# decide o que rodar com base nos timestamps do último ciclo (via CheckpointStore).
# ─────────────────────────────────────────────────────────────────────────────

_SCHED_SILVER = "_scheduler_silver"
_SCHED_GOLD = "_scheduler_gold"
_SIGNAL_TYPES = ("logs", "traces", "metrics", "tool_invocations")


class ObservabilityScheduler:
    """Orquestra os estágios da pipeline conforme cadência (F7).

    Args:
        silver_interval_min: intervalo mínimo entre execuções Bronze→Silver (default 15).
        gold_interval_min:   intervalo mínimo entre execuções Silver→Gold (default 60).
    """

    def __init__(
        self,
        storage: BlobStoragePort,
        silver_interval_min: int = 15,
        gold_interval_min: int = 60,
    ):
        self._storage = storage
        self._checkpoints = CheckpointStore(storage)
        self.silver_interval_min = silver_interval_min
        self.gold_interval_min = gold_interval_min

    def _last_run(self, marker: str) -> datetime.datetime | None:
        cp = self._checkpoints.load(marker)
        if cp and cp.last_processed_ts:
            try:
                return datetime.datetime.fromisoformat(cp.last_processed_ts)
            except ValueError:
                return None
        return None

    def _mark_run(self, marker: str, now: datetime.datetime, records: int = 0) -> None:
        self._checkpoints.save(
            Checkpoint(
                signal_type=marker,
                last_processed_path="",
                last_processed_ts=now.isoformat(),
                records_processed=records,
            )
        )

    @staticmethod
    def _elapsed_min(last: datetime.datetime | None, now: datetime.datetime) -> float:
        if last is None:
            return float("inf")
        return (now - last).total_seconds() / 60.0

    def _run_silver_stage(self, now: datetime.datetime) -> tuple[bool, int]:
        """Bronze → Silver (cadência rápida)."""
        worker = ObservabilityWorker(self._storage)
        total = 0
        for sig in _SIGNAL_TYPES:
            try:
                total += worker.run(signal_type=sig).get("records_processed", 0)
            except Exception as e:
                logger.warning("Scheduler: falha em Silver(%s): %s", sig, e, exc_info=True)
        self._mark_run(_SCHED_SILVER, now, total)
        return True, total

    def _run_gold_stage(self, now: datetime.datetime) -> bool:
        try:
            from .gold_aggregator import GoldAggregator

            GoldAggregator(self._storage).write_gold()
            self._mark_run(_SCHED_GOLD, now)
            return True
        except Exception as e:
            logger.warning("Scheduler: falha em Gold: %s", e, exc_info=True)
            return False

    def _run_cross_domain_stage(self) -> bool | None:
        """Cross-domain Gold (ADR-112 F8): junta fallback_rate com resultado financeiro.

        Retorna None quando projects_root não está configurado (etapa não aplicável —
        não deve aparecer no resultado do ciclo).
        """
        try:
            from concilium.infrastructure.settings import get_storage as _get_storage_cfg

            from .cross_domain import CrossDomainBuilder, default_canonical_provider

            cfg = _get_storage_cfg()
            projects_root = getattr(cfg, "projects_root", None) or (
                getattr(cfg, "root", None) and cfg.root / "projetos"
            )
            if not projects_root:
                return None
            provider = default_canonical_provider(projects_root)
            CrossDomainBuilder(self._storage, provider).write()
            return True
        except Exception as e:
            logger.warning("Scheduler: falha em CrossDomain Gold: %s", e, exc_info=True)
            return False

    def run_cycle(self, now: datetime.datetime | None = None) -> dict[str, Any]:
        """Executa um ciclo. Roda Silver e/ou Gold conforme intervalos decorridos.

        Returns:
            {"silver_ran": bool, "gold_ran": bool, "silver_records": int}
        """
        if now is None:
            now = datetime.datetime.now(datetime.UTC)

        result: dict[str, Any] = {"silver_ran": False, "gold_ran": False, "silver_records": 0}

        if self._elapsed_min(self._last_run(_SCHED_SILVER), now) >= self.silver_interval_min:
            silver_ran, total = self._run_silver_stage(now)
            result["silver_ran"] = silver_ran
            result["silver_records"] = total

        if self._elapsed_min(self._last_run(_SCHED_GOLD), now) >= self.gold_interval_min:
            result["gold_ran"] = self._run_gold_stage(now)
            cross_domain_ran = self._run_cross_domain_stage()
            if cross_domain_ran is not None:
                result["cross_domain_ran"] = cross_domain_ran

        return result
