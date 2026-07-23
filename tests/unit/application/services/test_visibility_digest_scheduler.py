"""Tests for VisibilityDigestScheduler (ADR-143 D8)."""

from __future__ import annotations

import threading
from unittest.mock import patch

from concilium.application.services.visibility_digest_scheduler import VisibilityDigestScheduler

_SIGNAL_TIMEOUT = 2.0


class TestSchedulerStartStop:
    def test_start_runs_digest_at_least_once_then_stop_joins_thread(self):
        called = threading.Event()

        def _fake_digest():
            called.set()
            return 0

        scheduler = VisibilityDigestScheduler(interval_seconds=0.01)
        with patch(
            "concilium.application.services.visibility_digest_scheduler.enviar_digest_visibilidade",
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
        scheduler = VisibilityDigestScheduler(interval_seconds=10)
        with patch(
            "concilium.application.services.visibility_digest_scheduler.enviar_digest_visibilidade",
            return_value=0,
        ):
            scheduler.start()
            first_thread = scheduler._thread
            scheduler.start()
            second_thread = scheduler._thread
            scheduler.stop()

        assert first_thread is second_thread

    def test_stop_without_start_is_a_noop(self):
        scheduler = VisibilityDigestScheduler(interval_seconds=10)
        scheduler.stop()  # não deve lançar
        assert scheduler._thread is None

    def test_exception_in_digest_does_not_kill_loop(self):
        calls: list[int] = []
        second_call = threading.Event()

        def _fake_digest():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("SMTP indisponível")
            second_call.set()
            return 0

        scheduler = VisibilityDigestScheduler(interval_seconds=0.01)
        with patch(
            "concilium.application.services.visibility_digest_scheduler.enviar_digest_visibilidade",
            side_effect=_fake_digest,
        ):
            scheduler.start()
            assert second_call.wait(timeout=_SIGNAL_TIMEOUT), "loop não sobreviveu à exceção da 1ª execução"
            scheduler.stop()

        assert len(calls) >= 2


class TestGetVisibilityDigestSchedulerSingleton:
    def test_returns_same_instance(self):
        import concilium.application.services.visibility_digest_scheduler as mod

        try:
            a = mod.get_visibility_digest_scheduler()
            b = mod.get_visibility_digest_scheduler()
            assert a is b
        finally:
            mod._scheduler = None


class TestSchedulerDefaultInterval:
    def test_default_interval_derives_from_settings(self, monkeypatch):
        monkeypatch.setenv("CONCILIUM__VISIBILITY_DIGEST_INTERVAL_SECONDS", "900")
        from concilium.infrastructure.settings._visibility_digest import _reset_visibility_digest

        _reset_visibility_digest()
        try:
            scheduler = VisibilityDigestScheduler()
            assert scheduler._interval_seconds == 900
        finally:
            _reset_visibility_digest()
