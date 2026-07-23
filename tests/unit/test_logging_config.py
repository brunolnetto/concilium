"""Coverage batch 7 — scheduler, campaign_store, migrator, logging gaps."""

from __future__ import annotations

import sys
from unittest.mock import patch

# logging_config.py lines 31-32: except Exception when trace fails
# logging_config.py lines 45-46: except Exception when auth import fails
# ---------------------------------------------------------------------------


class TestLoggingConfigExceptionPaths:
    def test_get_trace_context_exception_returns_empty(self):
        """Lines 31-32: exception in trace.get_current_span → except → return '', ''."""
        from concilium.infrastructure.observability.logging_config import _get_trace_context

        with patch.dict(sys.modules, {"opentelemetry": None}):
            result = _get_trace_context()
        assert result == ("", "")

    def test_get_auth_context_exception_returns_empty(self):
        """Lines 45-46: import fails → except Exception → return '', ''."""
        from concilium.infrastructure.observability.logging_config import _get_auth_context

        with patch.dict(
            sys.modules,
            {"concilium.infrastructure.middleware.auth_context": None},
        ):
            result = _get_auth_context()
        assert result == ("", "")

