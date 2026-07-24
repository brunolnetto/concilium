"""Tests for application/benchmarks/spec/spec_loader/_host_protocol.py.

The Protocol is only referenced under TYPE_CHECKING elsewhere, so it is
0% covered at runtime unless something imports it directly.
"""

from __future__ import annotations


class TestBenchmarkSpecLoaderHostProtocol:
    def test_import_succeeds_and_defines_expected_members(self):
        from concilium.application.benchmarks.spec.spec_loader._host_protocol import (
            BenchmarkSpecLoaderHost,
        )

        assert hasattr(BenchmarkSpecLoaderHost, "resolve_contexto")
        assert hasattr(BenchmarkSpecLoaderHost, "load_from_dict")
        assert hasattr(BenchmarkSpecLoaderHost, "_normalize_reference_schema")
        assert hasattr(BenchmarkSpecLoaderHost, "_infer_slug_from_path")
        assert hasattr(BenchmarkSpecLoaderHost, "_extract_eap")
        assert hasattr(BenchmarkSpecLoaderHost, "_extract_bdi_rates")

    def test_is_runtime_checkable_protocol_class(self):
        from typing import Protocol

        from concilium.application.benchmarks.spec.spec_loader._host_protocol import (
            BenchmarkSpecLoaderHost,
        )

        assert issubclass(BenchmarkSpecLoaderHost, Protocol)
        assert BenchmarkSpecLoaderHost.__mro__[0] is BenchmarkSpecLoaderHost
