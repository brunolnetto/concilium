"""Testes para flush periódico + shutdown-drain do BronzeLogHandler (fix: buffer
size-only nunca esvaziava em processos de baixo volume/scale-to-zero)."""

from __future__ import annotations

import logging
import time
from unittest.mock import MagicMock

import pytest

from concilium.infrastructure.observability.bronze_writer import BronzeLogHandler, BronzeWriter, _PeriodicFlusher


def _log_record(message="hello"):
    return logging.LogRecord("t", logging.INFO, "", 0, message, (), None)


class TestPeriodicFlusherLifecycle:
    def test_calls_flush_fn_repeatedly_until_stopped(self):
        calls = []
        flusher = _PeriodicFlusher(lambda: calls.append(1), interval_s=0.05)
        flusher.start()
        time.sleep(0.23)
        flusher.stop()
        assert len(calls) >= 2

    def test_stop_before_start_is_safe(self):
        flusher = _PeriodicFlusher(lambda: None, interval_s=10)
        flusher.stop()  # não deve lançar

    def test_start_twice_does_not_spawn_second_thread(self):
        calls = []
        flusher = _PeriodicFlusher(lambda: calls.append(1), interval_s=0.05)
        flusher.start()
        flusher.start()
        thread_first = flusher._thread
        time.sleep(0.12)
        flusher.stop()
        assert flusher._thread is None
        assert thread_first is not None

    def test_exception_in_flush_fn_does_not_kill_loop(self):
        calls = []

        def _flaky():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("boom")

        flusher = _PeriodicFlusher(_flaky, interval_s=0.05)
        flusher.start()
        time.sleep(0.17)
        flusher.stop()
        assert len(calls) >= 2  # sobreviveu à primeira exceção e continuou chamando


class TestBronzeLogHandlerPeriodicFlush:
    def _make_storage(self):
        storage = MagicMock()
        storage.gravar_blob = MagicMock()
        return storage

    def test_start_periodic_flush_drains_buffer_below_threshold(self):
        """Sem flush periódico, 1 registro nunca atingiria buffer_size=50 e ficaria
        preso no buffer indefinidamente — o bug real observado em produção."""
        storage = self._make_storage()
        writer = BronzeWriter(storage, "logs")
        handler = BronzeLogHandler(writer, buffer_size=50, flush_interval_s=0.05)
        handler.setFormatter(logging.Formatter())

        handler.emit(_log_record())
        storage.gravar_blob.assert_not_called()  # buffer_size não atingido ainda

        handler.start_periodic_flush()
        time.sleep(0.15)
        handler.close()

        storage.gravar_blob.assert_called()

    def test_no_periodic_flush_when_interval_is_zero(self):
        """flush_interval_s=0 desliga o flush periódico (usado nos testes existentes,
        que não esperam nenhuma thread em background)."""
        storage = self._make_storage()
        writer = BronzeWriter(storage, "logs")
        handler = BronzeLogHandler(writer, buffer_size=50, flush_interval_s=0)

        handler.start_periodic_flush()  # não deve criar thread nenhuma
        assert handler._flusher is None

        handler.close()  # não deve lançar

    def test_close_stops_periodic_flush_and_drains_remaining_buffer(self):
        storage = self._make_storage()
        writer = BronzeWriter(storage, "logs")
        handler = BronzeLogHandler(writer, buffer_size=50, flush_interval_s=5)
        handler.setFormatter(logging.Formatter())
        handler.start_periodic_flush()

        handler.emit(_log_record("shutdown drain"))
        handler.close()

        storage.gravar_blob.assert_called_once()
        path, content = storage.gravar_blob.call_args[0]
        assert b"shutdown drain" in content

    def test_close_is_idempotent(self):
        storage = self._make_storage()
        writer = BronzeWriter(storage, "logs")
        handler = BronzeLogHandler(writer, buffer_size=50, flush_interval_s=5)
        handler.start_periodic_flush()

        handler.close()
        handler.close()  # não deve lançar nem duplicar flush

    def test_emit_and_periodic_flush_are_thread_safe(self):
        """Concorrência entre emit() (thread principal) e o flush periódico
        (thread de background) não deve corromper o buffer nem duplicar batches."""
        storage = self._make_storage()
        writer = BronzeWriter(storage, "logs")
        handler = BronzeLogHandler(writer, buffer_size=1000, flush_interval_s=0.02)
        handler.setFormatter(logging.Formatter())
        handler.start_periodic_flush()

        for i in range(50):
            handler.emit(_log_record(f"msg-{i}"))
            time.sleep(0.001)

        handler.close()

        # Reconstrói todas as mensagens gravadas em todos os batches — nenhuma perdida/duplicada.
        import json

        seen = []
        for call in storage.gravar_blob.call_args_list:
            _, content = call[0]
            for line in content.decode("utf-8").strip().splitlines():
                seen.append(json.loads(line)["message"])
        assert sorted(seen) == sorted(f"msg-{i}" for i in range(50))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
