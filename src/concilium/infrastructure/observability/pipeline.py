"""ObservabilityWorker — ADR-112 F4.

Orquestra Bronze → Silver com fast-forward incremental e idempotência por event_id.
Silver é persistido no BlobStorage como NDJSON, garantindo que GoldAggregator
acesse os mesmos dados via o mesmo storage.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from concilium.domain.repositories.blob_storage_port import BlobStoragePort

from .checkpoint_store import Checkpoint, CheckpointStore
from .silver_normalizer import normalize_log_record, normalize_metric_record, normalize_span_record

logger = logging.getLogger(__name__)

_BRONZE_PREFIX = "observability/bronze"
_SILVER_PREFIX = "observability/silver"

_NORMALIZERS = {
    "logs": normalize_log_record,
    "traces": normalize_span_record,
    "metrics": normalize_metric_record,
}


def _make_storage() -> BlobStoragePort:
    """Cria storage padrão a partir das configurações do ambiente."""
    from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage
    from concilium.infrastructure.settings import get_storage

    cfg = get_storage()
    root = getattr(cfg, "root", None) or getattr(cfg, "config_root", None)
    base = (root / "observability") if root else "observability"
    return LocalBlobStorage(base)


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

    def _silver_path(self, signal_type: str) -> str:
        date = datetime.date.today().isoformat()
        return f"{_SILVER_PREFIX}/{signal_type}/{date}/records.ndjson"

    def _upsert_silver(self, signal_type: str, records: list[dict[str, Any]]) -> None:
        """Upsert records no Silver NDJSON. Deduplicação por event_id/span_id."""
        path = self._silver_path(signal_type)
        existing: dict[str, dict[str, Any]] = {}
        try:
            raw = self._storage.ler_blob(path)
            for line in raw.decode("utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    key = self._record_key(rec)
                    existing[key] = rec
        except FileNotFoundError:
            pass

        for rec in records:
            existing[self._record_key(rec)] = rec

        content = "\n".join(json.dumps(r, ensure_ascii=False) for r in existing.values()) + "\n"
        self._storage.gravar_blob(path, content.encode("utf-8"))

    @staticmethod
    def _record_key(rec: dict[str, Any]) -> str:
        return (
            rec.get("event_id")
            or rec.get("span_id")
            or f"{rec.get('ts', '')}{rec.get('metric_name', '')}"
            or str(id(rec))
        )

    def read_silver(self, signal_type: str) -> list[dict[str, Any]]:
        """Retorna todos os records Silver persistidos para o tipo de sinal."""
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
        return records

    # ── Pipeline principal ──────────────────────────────────────────────────

    def run(
        self,
        signal_type: str = "logs",
        full_reload: bool = False,
        since: str | None = None,
    ) -> dict[str, Any]:
        """Processa Bronze → Silver incrementalmente.

        Args:
            signal_type:  "logs" | "traces" | "metrics"
            full_reload:  True → apaga checkpoint e reprocessa tudo
            since:        ISO date string — processa apenas blobs desta data em diante

        Returns:
            {"blobs_processed": N, "records_processed": M}
        """
        if full_reload:
            self._checkpoints.delete(signal_type)

        checkpoint = self._checkpoints.load(signal_type)
        last_path = checkpoint.last_processed_path if checkpoint else None

        all_blobs = sorted(self._storage.listar_blobs(f"{_BRONZE_PREFIX}/{signal_type}/"))

        if last_path:
            new_blobs = [b for b in all_blobs if b > last_path]
        elif since:
            new_blobs = [b for b in all_blobs if since in b]
        else:
            new_blobs = all_blobs

        normalizer = _NORMALIZERS.get(signal_type, normalize_log_record)
        records_processed = 0
        current_total = checkpoint.records_processed if checkpoint else 0

        for blob_path in new_blobs:
            raw_records = self._read_ndjson(blob_path)
            normalized = [normalizer(r) for r in raw_records]
            self._upsert_silver(signal_type, normalized)
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
_SIGNAL_TYPES = ("logs", "traces", "metrics")


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

    def run_cycle(self, now: datetime.datetime | None = None) -> dict[str, Any]:
        """Executa um ciclo. Roda Silver e/ou Gold conforme intervalos decorridos.

        Returns:
            {"silver_ran": bool, "gold_ran": bool, "silver_records": int}
        """
        if now is None:
            now = datetime.datetime.now(datetime.UTC)

        result: dict[str, Any] = {"silver_ran": False, "gold_ran": False, "silver_records": 0}

        # Bronze → Silver (cadência rápida)
        if self._elapsed_min(self._last_run(_SCHED_SILVER), now) >= self.silver_interval_min:
            worker = ObservabilityWorker(self._storage)
            total = 0
            for sig in _SIGNAL_TYPES:
                try:
                    total += worker.run(signal_type=sig).get("records_processed", 0)
                except Exception as e:
                    logger.warning("Scheduler: falha em Silver(%s): %s", sig, e, exc_info=True)
            self._mark_run(_SCHED_SILVER, now, total)
            result["silver_ran"] = True
            result["silver_records"] = total

        # Silver → Gold (cadência lenta)
        if self._elapsed_min(self._last_run(_SCHED_GOLD), now) >= self.gold_interval_min:
            try:
                from .gold_aggregator import GoldAggregator

                GoldAggregator(self._storage).write_gold()
                self._mark_run(_SCHED_GOLD, now)
                result["gold_ran"] = True
            except Exception as e:
                logger.warning("Scheduler: falha em Gold: %s", e, exc_info=True)

        return result
