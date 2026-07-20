"""Scheduler do digest periódico de visibilidade de usuários (ADR-143 D8).

Mesmo padrão de `JobService._garbage_collector_loop` /
`DraftDigestScheduler` (ADR-140/141): thread daemon com `Event.wait(timeout=...)`
— sem fila/broker novo. Intervalo bem mais curto que o digest de catálogo
(default 5min vs. 24h) porque o gatilho de envio é time-gated por conteúdo
(D8): o tick sozinho, sem consulta nova pendente, nunca chama
`NotificationService.send()` — ver `enviar_digest_visibilidade`.

Não reaproveita o job `concilium-observability` (ADR-112) — mesmo princípio
de time-gating, mas responsabilidade e domínio distintos (D8/A7).
"""

from __future__ import annotations

import logging
import threading

from concilium.application.services.visibility_digest_service import enviar_digest_visibilidade
from concilium.infrastructure.settings import get_visibility_digest

logger = logging.getLogger(__name__)


class VisibilityDigestScheduler:
    """Roda `enviar_digest_visibilidade()` a cada `interval_seconds`.

    Só deve ser iniciado explicitamente pelo processo de servidor real
    (`presentation/api/app.py::main()`), nunca em `create_app()` (mesma
    convenção do ADR-141 D6) — evita nascer um thread real a cada import de
    teste via `TestClient`.
    """

    def __init__(self, interval_seconds: float | None = None) -> None:
        self._interval_seconds = (
            interval_seconds if interval_seconds is not None else get_visibility_digest().interval_seconds
        )
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="visibility-digest")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop_event.wait(timeout=self._interval_seconds):
            try:
                enviar_digest_visibilidade()
            except Exception:
                logger.exception("Falha ao enviar digest de visibilidade de usuários")


_scheduler: VisibilityDigestScheduler | None = None
_scheduler_lock = threading.Lock()


def get_visibility_digest_scheduler() -> VisibilityDigestScheduler:
    """Retorna o singleton de VisibilityDigestScheduler."""
    global _scheduler
    if _scheduler is None:
        with _scheduler_lock:
            if _scheduler is None:  # pragma: no cover
                _scheduler = VisibilityDigestScheduler()
    assert _scheduler is not None  # double-checked locking sempre atribui antes daqui
    return _scheduler
