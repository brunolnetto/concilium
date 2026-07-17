"""Scheduler do digest periódico de rascunhos de catálogo (ADR-141 D5).

Mesmo padrão de `JobService._garbage_collector_loop`
(`application/jobs/service.py`): thread daemon com `Event.wait(timeout=...)`
— sem fila/broker novo (ADR-140 D3).
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from concilium.application.services.catalog.draft_digest_service import enviar_digest_rascunhos_pendentes
from concilium.infrastructure.settings import get_catalog_digest

logger = logging.getLogger(__name__)


class DraftDigestScheduler:
    """Roda `enviar_digest_rascunhos_pendentes()` a cada `interval_seconds`.

    Só deve ser iniciado explicitamente pelo processo de servidor real
    (`presentation/api/app.py::main()`), nunca em `create_app()` (ADR-141 D6)
    — evita nascer um thread real a cada import de teste via `TestClient`.
    """

    def __init__(self, interval_seconds: float | None = None, config_root: Path | None = None) -> None:
        self._interval_seconds = (
            interval_seconds if interval_seconds is not None else get_catalog_digest().interval_hours * 3600
        )
        self._config_root = config_root
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="catalog-draft-digest")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop_event.wait(timeout=self._interval_seconds):
            try:
                enviar_digest_rascunhos_pendentes(self._config_root)
            except Exception:
                logger.exception("Falha ao enviar digest de rascunhos de catálogo pendentes")


_scheduler: DraftDigestScheduler | None = None
_scheduler_lock = threading.Lock()


def get_draft_digest_scheduler() -> DraftDigestScheduler:
    """Retorna o singleton de DraftDigestScheduler."""
    global _scheduler
    if _scheduler is None:
        with _scheduler_lock:
            if _scheduler is None:  # pragma: no cover
                _scheduler = DraftDigestScheduler()
    assert _scheduler is not None  # double-checked locking sempre atribui antes daqui
    return _scheduler
