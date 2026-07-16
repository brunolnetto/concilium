"""Tests for DraftDigestScheduler (ADR-141 F5).

Usa interval_seconds minúsculo (não interval_hours) para manter os testes
rápidos e determinísticos — sem sleep de polling, só Event.wait com timeout
generoso para sincronizar com o thread real.
"""

from __future__ import annotations

import threading
from unittest.mock import patch

from concilium.application.services.catalog.draft_digest_scheduler import DraftDigestScheduler

_SIGNAL_TIMEOUT = 2.0


class TestSchedulerStartStop:
    def test_start_runs_digest_at_least_once_then_stop_joins_thread(self):
        called = threading.Event()

        def _fake_digest(config_root=None):
            called.set()
            return 0

        scheduler = DraftDigestScheduler(interval_seconds=0.01)
        with patch(
            "concilium.application.services.catalog.draft_digest_scheduler.enviar_digest_rascunhos_pendentes",
            side_effect=_fake_digest,
        ):
            scheduler.start()
            assert called.wait(timeout=_SIGNAL_TIMEOUT), "digest não rodou dentro do timeout"
            thread = scheduler._thread
            scheduler.stop()

        assert scheduler._thread is None
        assert thread is not None
        assert not thread.is_alive()

    def test_start_called_twice_does_not_spawn_second_thread(self):
        scheduler = DraftDigestScheduler(interval_seconds=10)
        with patch(
            "concilium.application.services.catalog.draft_digest_scheduler.enviar_digest_rascunhos_pendentes",
            return_value=0,
        ):
            scheduler.start()
            first_thread = scheduler._thread
            scheduler.start()
            second_thread = scheduler._thread
            scheduler.stop()

        assert first_thread is second_thread

    def test_stop_without_start_is_a_noop(self):
        scheduler = DraftDigestScheduler(interval_seconds=10)
        scheduler.stop()  # não deve lançar
        assert scheduler._thread is None

    def test_exception_in_digest_does_not_kill_loop(self):
        calls: list[int] = []
        second_call = threading.Event()

        def _fake_digest(config_root=None):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("SMTP indisponível")
            second_call.set()
            return 0

        scheduler = DraftDigestScheduler(interval_seconds=0.01)
        with patch(
            "concilium.application.services.catalog.draft_digest_scheduler.enviar_digest_rascunhos_pendentes",
            side_effect=_fake_digest,
        ):
            scheduler.start()
            assert second_call.wait(timeout=_SIGNAL_TIMEOUT), "loop não sobreviveu à exceção da 1ª execução"
            scheduler.stop()

        assert len(calls) >= 2


class TestSchedulerDefaultInterval:
    def test_default_interval_derives_from_settings(self, monkeypatch):
        monkeypatch.setenv("CONCILIUM__CATALOG_DIGEST_INTERVAL_HOURS", "6")
        from concilium.infrastructure.settings._catalog_digest import _reset_catalog_digest

        _reset_catalog_digest()
        try:
            scheduler = DraftDigestScheduler()
            assert scheduler._interval_seconds == 6 * 3600
        finally:
            _reset_catalog_digest()
