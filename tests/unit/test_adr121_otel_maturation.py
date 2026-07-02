"""TDD — ADR-121: Maturação da Instrumentação OpenTelemetry.

Cobre:
  F1-D1: LoggingHandler configurado em DEBUG (não WARNING)
  F1-D2: _JsonFormatter inclui fallback_type quando presente no extra
  F1-D3: configure_logging() conecta BronzeLogHandler quando bronze_storage fornecido
  F2-D4: McpAuthMiddleware extrai traceparent/tracestate via propagate.extract()
  F2-D5: explore_schedules() emite span.add_event() em decisões de scheduling
  F3-D6: McpAuthMiddleware injeta tenant_id e user_id como baggage após JWT decode
"""

from __future__ import annotations

import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch


def _make_receive(body: bytes = b"{}") -> AsyncMock:
    """ASGI receive() mock returning a single complete http.request message.

    A bare AsyncMock() has no notion of ASGI message shape: _is_public_tool_call()
    loops `while True: message = await receive()` until it sees more_body=False,
    so an unconfigured mock spins forever instead of raising.
    """
    return AsyncMock(return_value={"type": "http.request", "body": body, "more_body": False})


# ─────────────────────────────────────────────────────────────────────────────
# F1-D1  LoggingHandler em DEBUG
# ─────────────────────────────────────────────────────────────────────────────


class TestLoggingHandlerLevel:
    """D1: Bridge LoggingHandler deve exportar INFO e DEBUG, não apenas WARNING."""

    def test_logging_handler_level_constant_is_debug(self):
        """O módulo telemetry usa logging.DEBUG ao instanciar LoggingHandler (ADR-121 D1)."""
        import inspect

        import concilium.infrastructure.telemetry as tel_mod

        src = inspect.getsource(tel_mod)
        assert "LoggingHandler(level=logging.DEBUG" in src, (
            "LoggingHandler não usa logging.DEBUG (ADR-121 D1). "
            "Esperado: LoggingHandler(level=logging.DEBUG, logger_provider=...)"
        )

    def test_telemetry_module_uses_debug_level(self):
        """Verifica que o módulo telemetry não usa logging.WARNING para o LoggingHandler."""
        import ast
        import inspect

        import concilium.infrastructure.telemetry as tel_mod

        src = inspect.getsource(tel_mod)
        # Deve conter logging.DEBUG no contexto de LoggingHandler, não logging.WARNING
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                (
                    getattr(node.func, "id", None) or getattr(getattr(node.func, "attr", None), "__str__", lambda: "")()
                )
                if "LoggingHandler" not in str(getattr(node.func, "id", "")) and "LoggingHandler" not in str(
                    getattr(node.func, "attr", "")
                ):
                    continue
                for kw in node.keywords:
                    if kw.arg == "level":
                        val = kw.value
                        if isinstance(val, ast.Attribute) and val.attr == "WARNING":
                            raise AssertionError(
                                "LoggingHandler usa logging.WARNING — deve ser logging.DEBUG (ADR-121 D1)"
                            )


# ─────────────────────────────────────────────────────────────────────────────
# F1-D2  fallback_type no _JsonFormatter
# ─────────────────────────────────────────────────────────────────────────────


class TestJsonFormatterFallbackType:
    """D2: _JsonFormatter inclui fallback_type quando presente no log record."""

    def _make_record(self, msg: str, extra: dict | None = None) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for k, v in (extra or {}).items():
            setattr(record, k, v)
        return record

    def test_fallback_type_included_when_present(self):
        from concilium.infrastructure.observability.logging_config import _JsonFormatter

        fmt = _JsonFormatter()
        record = self._make_record("pool relaxado", extra={"fallback_type": "pool_relaxation"})
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed.get("fallback_type") == "pool_relaxation", "fallback_type ausente no JSON — ADR-121 D2"

    def test_fallback_type_absent_when_not_set(self):
        from concilium.infrastructure.observability.logging_config import _JsonFormatter

        fmt = _JsonFormatter()
        record = self._make_record("sem fallback")
        output = fmt.format(record)
        parsed = json.loads(output)
        assert "fallback_type" not in parsed

    def test_only_fallback_type_added_not_all_extras(self):
        """Apenas fallback_type é promovido — outros campos de extra não devem vazar."""
        from concilium.infrastructure.observability.logging_config import _JsonFormatter

        fmt = _JsonFormatter()
        record = self._make_record(
            "evento",
            extra={"fallback_type": "cpsat_infeasible", "custo_direto": 1_234_567.89},
        )
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed.get("fallback_type") == "cpsat_infeasible"
        assert "custo_direto" not in parsed, "dados de projeto não devem aparecer no log (ADR-095 D5)"

    def test_standard_fields_always_present(self):
        from concilium.infrastructure.observability.logging_config import _JsonFormatter

        fmt = _JsonFormatter()
        record = self._make_record("ok")
        parsed = json.loads(fmt.format(record))
        for field in ("ts", "severity", "logger", "message", "service"):
            assert field in parsed, f"campo obrigatório ausente: {field}"


# ─────────────────────────────────────────────────────────────────────────────
# F1-D3  BronzeLogHandler conectado ao configure_logging()
# ─────────────────────────────────────────────────────────────────────────────


class TestBronzeLogHandlerWiring:
    """D3: configure_logging() com bronze_storage conecta BronzeLogHandler ao root logger."""

    def _make_storage(self):
        storage = MagicMock()
        storage.gravar_blob = MagicMock()
        return storage

    def test_bronze_handler_added_when_storage_provided(self):
        from concilium.infrastructure.observability.bronze_writer import BronzeLogHandler
        from concilium.infrastructure.observability.logging_config import configure_logging

        storage = self._make_storage()
        root = logging.getLogger()
        before = [h for h in root.handlers if isinstance(h, BronzeLogHandler)]

        configure_logging(json_format=False, bronze_storage=storage)

        after = [h for h in root.handlers if isinstance(h, BronzeLogHandler)]
        assert len(after) >= 1, "BronzeLogHandler não adicionado ao root logger (ADR-121 D3)"

        # Cleanup
        for h in after:
            root.removeHandler(h)
        for h in before:
            if h not in root.handlers:
                root.addHandler(h)

    def test_bronze_handler_not_added_when_storage_absent(self):
        from concilium.infrastructure.observability.bronze_writer import BronzeLogHandler
        from concilium.infrastructure.observability.logging_config import configure_logging

        root = logging.getLogger()
        configure_logging(json_format=False)
        bronze_handlers = [h for h in root.handlers if isinstance(h, BronzeLogHandler)]
        assert len(bronze_handlers) == 0, "BronzeLogHandler adicionado sem storage — incorreto"

    def test_configure_logging_idempotent_with_storage(self):
        """Chamar configure_logging() duas vezes com storage não duplica BronzeLogHandler."""
        from concilium.infrastructure.observability.bronze_writer import BronzeLogHandler
        from concilium.infrastructure.observability.logging_config import configure_logging

        storage = self._make_storage()
        root = logging.getLogger()

        configure_logging(json_format=False, bronze_storage=storage)
        configure_logging(json_format=False, bronze_storage=storage)

        bronze_handlers = [h for h in root.handlers if isinstance(h, BronzeLogHandler)]
        assert len(bronze_handlers) == 1, (
            f"BronzeLogHandler duplicado após configure_logging() repetido: {len(bronze_handlers)}"
        )

        # Cleanup
        for h in bronze_handlers:
            root.removeHandler(h)

    def test_bronze_handler_emits_to_storage(self):
        """BronzeLogHandler escreve records no storage quando faz flush."""
        from concilium.infrastructure.observability.bronze_writer import BronzeLogHandler, BronzeWriter

        storage = self._make_storage()
        writer = BronzeWriter(storage, "logs")
        handler = BronzeLogHandler(writer, buffer_size=2)
        handler.setFormatter(logging.Formatter())

        record = logging.LogRecord("t", logging.INFO, "", 0, "hello bronze", (), None)
        handler.emit(record)
        handler.emit(record)  # triggers flush at buffer_size=2

        storage.gravar_blob.assert_called()
        path, content = storage.gravar_blob.call_args[0]
        assert "observability/bronze/logs/" in path
        assert b"hello bronze" in content


# ─────────────────────────────────────────────────────────────────────────────
# F2-D4  McpAuthMiddleware extrai traceparent
# ─────────────────────────────────────────────────────────────────────────────


class TestMiddlewareTraceparentExtraction:
    """D4: McpAuthMiddleware chama propagate.extract() com headers do request."""

    def _make_scope(self, headers: list[tuple[bytes, bytes]]) -> dict:
        return {
            "type": "http",
            "headers": headers,
            "method": "POST",
            "path": "/mcp",
            "query_string": b"",
        }

    def test_traceparent_header_triggers_propagate_extract(self):
        from concilium.presentation.mcp.middleware import McpAuthMiddleware

        extracted_carriers: list[dict] = []

        def fake_extract(carrier, context=None, getter=None):
            extracted_carriers.append(dict(carrier))
            return {}

        inner_called = []

        async def inner_app(scope, receive, send):
            inner_called.append(True)

        middleware = McpAuthMiddleware(inner_app)
        scope = self._make_scope(
            [
                (b"traceparent", b"00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"),
            ]
        )

        with patch("concilium.presentation.mcp.middleware.propagate") as mock_prop:
            mock_prop.extract.return_value = {}
            asyncio.get_event_loop().run_until_complete(middleware(scope, _make_receive(), AsyncMock()))
            mock_prop.extract.assert_called_once()
            carrier_arg = mock_prop.extract.call_args[0][0]
            assert (
                "traceparent" in carrier_arg
                or b"traceparent" in carrier_arg
                or any("traceparent" in str(k) for k in carrier_arg)
            ), "propagate.extract() chamado sem traceparent na carrier"

    def test_missing_traceparent_does_not_raise(self):
        """Request sem traceparent não deve quebrar o middleware."""
        from concilium.presentation.mcp.middleware import McpAuthMiddleware

        async def inner_app(scope, receive, send):
            pass

        middleware = McpAuthMiddleware(inner_app)
        scope = self._make_scope([])  # sem traceparent

        with patch("concilium.presentation.mcp.middleware.propagate", create=True) as mock_prop:
            mock_prop.extract.return_value = {}
            # Deve executar sem exceção
            asyncio.get_event_loop().run_until_complete(middleware(scope, _make_receive(), AsyncMock()))

    def test_traceparent_context_detached_after_request(self):
        """O contexto OTel anexado é desanexado no finally mesmo se o app interno levanta."""
        from concilium.presentation.mcp.middleware import McpAuthMiddleware

        async def failing_app(scope, receive, send):
            raise RuntimeError("inner failure")

        middleware = McpAuthMiddleware(failing_app)
        scope = self._make_scope(
            [
                (b"traceparent", b"00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"),
            ]
        )


        with (
            patch("concilium.presentation.mcp.middleware.propagate") as mock_prop,
            patch("concilium.presentation.mcp.middleware.context_detach") as mock_detach,
        ):
            mock_prop.extract.return_value = {}

            import contextlib

            with contextlib.suppress(RuntimeError):
                asyncio.get_event_loop().run_until_complete(middleware(scope, _make_receive(), AsyncMock()))
            # detach deve ter sido chamado mesmo com exceção
            mock_detach.assert_called()


# ─────────────────────────────────────────────────────────────────────────────
# F2-D5  span.add_event() em explore_schedules()
# ─────────────────────────────────────────────────────────────────────────────


class TestSchedulingSpanEvents:
    """D5: explore_schedules() emite span.add_event() nas decisões de algoritmo."""

    def _make_mock_span(self):
        span = MagicMock()
        span.add_event = MagicMock()
        span.is_recording = MagicMock(return_value=True)
        return span

    def _make_dag_and_pool(self):
        from concilium.application.scheduling.models import (
            Activity,
            ActivityDAG,
            ResourcePool,
        )

        a1 = Activity(activity_id="A1", description="Test", duration_weeks=2, required_resources={"T1": 1})
        dag = ActivityDAG(activities=[a1])
        pool = ResourcePool(resources={"T1": 2})
        return dag, pool

    def test_algorithm_selected_event_emitted(self, monkeypatch):
        """explore_schedules emite 'scheduling.algorithm.selected' com atributos."""
        from concilium.application.scheduling.models import SchedulingStrategy

        span = self._make_mock_span()

        # Use a strategy que vai direto para SerialScheduler (sem ortools necessário)
        strategy = SchedulingStrategy(algorithm="MINSLK", heuristics=["MINSLK"], timeout_seconds=0)

        with patch("concilium.application.scheduling.selector.trace") as mock_trace:
            mock_trace.get_current_span.return_value = span
            dag, pool = self._make_dag_and_pool()
            try:
                from concilium.application.scheduling.selector import explore_schedules

                explore_schedules(
                    activities=list(dag.activities),
                    dag=dag,
                    pool=pool,
                    deadline_weeks=10,
                    strategy=strategy,
                )
            except Exception:
                pass  # resultado não importa — só queremos verificar os eventos

        # Deve ter chamado add_event ao menos uma vez
        events = [call[0][0] for call in span.add_event.call_args_list]
        assert any("scheduling" in e for e in events), f"Nenhum span event de scheduling emitido. Events: {events}"

    def test_algorithm_selected_event_has_correct_attributes(self, monkeypatch):
        """O evento 'scheduling.algorithm.selected' carrega algorithm e n_activities."""
        from concilium.application.scheduling.models import SchedulingStrategy

        span = self._make_mock_span()
        strategy = SchedulingStrategy(algorithm="MINSLK", heuristics=["MINSLK"], timeout_seconds=0)

        with patch("concilium.application.scheduling.selector.trace") as mock_trace:
            mock_trace.get_current_span.return_value = span
            dag, pool = self._make_dag_and_pool()
            try:
                from concilium.application.scheduling.selector import explore_schedules

                explore_schedules(
                    activities=list(dag.activities),
                    dag=dag,
                    pool=pool,
                    deadline_weeks=10,
                    strategy=strategy,
                )
            except Exception:
                pass

        # Procura o evento scheduling.algorithm.selected
        selected_calls = [call for call in span.add_event.call_args_list if "algorithm.selected" in str(call[0][0])]
        assert selected_calls, "scheduling.algorithm.selected não emitido"
        attrs = selected_calls[0][0][1] if len(selected_calls[0][0]) > 1 else selected_calls[0][1].get("attributes", {})
        assert "algorithm" in str(attrs), "atributo 'algorithm' ausente no evento"
        assert "n_activities" in str(attrs), "atributo 'n_activities' ausente no evento"

    def test_span_events_no_op_when_no_active_span(self):
        """explore_schedules não levanta se não houver span OTel ativo."""
        from concilium.application.scheduling.models import SchedulingStrategy
        from concilium.application.scheduling.selector import explore_schedules

        strategy = SchedulingStrategy(algorithm="MINSLK", heuristics=["MINSLK"], timeout_seconds=0)
        dag, pool = self._make_dag_and_pool()

        # Sem patch de trace — usa o SDK real com OTEL_SDK_DISABLED
        try:
            explore_schedules(
                activities=list(dag.activities),
                dag=dag,
                pool=pool,
                deadline_weeks=10,
                strategy=strategy,
            )
        except Exception as e:
            # Apenas ScheduleError (sem ortools) é aceitável — RuntimeError não
            from concilium.application.scheduling.models import ScheduleError

            if not isinstance(e, ScheduleError):
                raise AssertionError(f"Exceção inesperada: {e}") from e


# ─────────────────────────────────────────────────────────────────────────────
# F3-D6  Baggage no McpAuthMiddleware
# ─────────────────────────────────────────────────────────────────────────────


class TestMiddlewareBaggageInjection:
    """D6: McpAuthMiddleware injeta tenant_id e user_id como baggage após JWT decode."""

    def _make_scope_with_token(self) -> dict:
        return {
            "type": "http",
            "headers": [(b"authorization", b"Bearer fake.token.here")],
            "method": "POST",
            "path": "/mcp",
            "query_string": b"",
        }

    def test_tenant_id_injected_as_baggage(self):
        from concilium.presentation.mcp.middleware import McpAuthMiddleware

        baggage_set_calls: list[tuple] = []

        def fake_set_baggage(key, value, context=None):
            baggage_set_calls.append((key, value))
            return context or {}

        async def inner_app(scope, receive, send):
            pass

        middleware = McpAuthMiddleware(inner_app)
        scope = self._make_scope_with_token()

        with (
            patch("concilium.presentation.mcp.middleware.set_baggage", fake_set_baggage, create=True),
            patch("concilium.infrastructure.auth.token_service.decode_token") as mock_decode,
            patch("concilium.infrastructure.auth.permission_guard.roles_from_token", return_value=["operator"]),
            patch("concilium.presentation.mcp.middleware.propagate") as mock_prop,
        ):
            mock_decode.return_value = {"sub": "usr-42", "tid": "tenant-abc", "roles": ["operator"]}
            mock_prop.extract.return_value = {}

            asyncio.get_event_loop().run_until_complete(middleware(scope, _make_receive(), AsyncMock()))

        keys_set = [k for k, _ in baggage_set_calls]
        assert "tenant.id" in keys_set, f"tenant.id não injetado como baggage. Calls: {baggage_set_calls}"
        assert "user.id" in keys_set, f"user.id não injetado como baggage. Calls: {baggage_set_calls}"

    def test_baggage_values_match_jwt_claims(self):
        from concilium.presentation.mcp.middleware import McpAuthMiddleware

        captured: dict[str, str] = {}

        def fake_set_baggage(key, value, context=None):
            captured[key] = value
            return context or {}

        async def inner_app(scope, receive, send):
            pass

        middleware = McpAuthMiddleware(inner_app)
        scope = self._make_scope_with_token()

        with (
            patch("concilium.presentation.mcp.middleware.set_baggage", fake_set_baggage, create=True),
            patch("concilium.infrastructure.auth.token_service.decode_token") as mock_decode,
            patch("concilium.infrastructure.auth.permission_guard.roles_from_token", return_value=["operator"]),
            patch("concilium.presentation.mcp.middleware.propagate") as mock_prop,
        ):
            mock_decode.return_value = {"sub": "usr-007", "tid": "mendeslobo", "roles": ["operator"]}
            mock_prop.extract.return_value = {}

            asyncio.get_event_loop().run_until_complete(middleware(scope, _make_receive(), AsyncMock()))

        assert captured.get("tenant.id") == "mendeslobo"
        assert captured.get("user.id") == "usr-007"

    def test_baggage_not_set_for_missing_claims(self):
        """Quando tid/sub estão ausentes do token, baggage não é injetado com None."""
        from concilium.presentation.mcp.middleware import McpAuthMiddleware

        baggage_calls: list[tuple] = []

        def fake_set_baggage(key, value, context=None):
            baggage_calls.append((key, value))
            return context or {}

        async def inner_app(scope, receive, send):
            pass

        middleware = McpAuthMiddleware(inner_app)
        scope = self._make_scope_with_token()

        with (
            patch("concilium.presentation.mcp.middleware.set_baggage", fake_set_baggage, create=True),
            patch("concilium.infrastructure.auth.token_service.decode_token") as mock_decode,
            patch("concilium.infrastructure.auth.permission_guard.roles_from_token", return_value=["operator"]),
            patch("concilium.presentation.mcp.middleware.propagate") as mock_prop,
        ):
            mock_decode.return_value = {"roles": ["operator"]}  # sem sub nem tid
            mock_prop.extract.return_value = {}

            asyncio.get_event_loop().run_until_complete(middleware(scope, _make_receive(), AsyncMock()))

        # None não deve ser injetado como valor de baggage
        none_values = [(k, v) for k, v in baggage_calls if v is None]
        assert not none_values, f"Valores None injetados no baggage: {none_values}"

    def test_baggage_detached_after_request(self):
        """Contexto de baggage é desanexado no finally mesmo com inner app falhando."""
        from concilium.presentation.mcp.middleware import McpAuthMiddleware

        async def failing_inner(scope, receive, send):
            raise RuntimeError("inner error")

        middleware = McpAuthMiddleware(failing_inner)
        scope = self._make_scope_with_token()

        with (
            patch("concilium.presentation.mcp.middleware.set_baggage", return_value={}, create=True),
            patch("concilium.presentation.mcp.middleware.context_detach") as mock_detach,
            patch("concilium.infrastructure.auth.token_service.decode_token") as mock_decode,
            patch("concilium.infrastructure.auth.permission_guard.roles_from_token", return_value=[]),
            patch("concilium.presentation.mcp.middleware.propagate") as mock_prop,
        ):
            mock_decode.return_value = {"sub": "u", "tid": "t"}
            mock_prop.extract.return_value = {}

            import contextlib

            with contextlib.suppress(RuntimeError):
                asyncio.get_event_loop().run_until_complete(middleware(scope, _make_receive(), AsyncMock()))
            mock_detach.assert_called()
