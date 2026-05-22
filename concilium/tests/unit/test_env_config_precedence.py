from __future__ import annotations

from pathlib import Path

from concilium.infrastructure.catalog.mapping import cpu_mapper
from concilium.presentation.api import config as api_config
from concilium.presentation.ui import config as ui_config


def test_cpu_mapping_rules_prefers_benchmark_env(monkeypatch, tmp_path: Path) -> None:
    bench_rules = tmp_path / "bench_rules.json"
    legacy_rules = tmp_path / "legacy_rules.json"
    monkeypatch.setenv("CONCILIUM_BENCHMARK_CPU_MAPPING_RULES_FILE", str(bench_rules))
    monkeypatch.setenv("CONCILIUM_CPU_MAPPING_RULES_FILE", str(legacy_rules))

    assert cpu_mapper._rules_file() == bench_rules


def test_cpu_mapping_rules_uses_legacy_env_when_benchmark_absent(monkeypatch, tmp_path: Path) -> None:
    legacy_rules = tmp_path / "legacy_rules.json"
    monkeypatch.delenv("CONCILIUM_BENCHMARK_CPU_MAPPING_RULES_FILE", raising=False)
    monkeypatch.setenv("CONCILIUM_CPU_MAPPING_RULES_FILE", str(legacy_rules))

    assert cpu_mapper._rules_file() == legacy_rules


def test_cpu_mapping_rules_falls_back_to_default_path(monkeypatch) -> None:
    monkeypatch.delenv("CONCILIUM_BENCHMARK_CPU_MAPPING_RULES_FILE", raising=False)
    monkeypatch.delenv("CONCILIUM_CPU_MAPPING_RULES_FILE", raising=False)

    expected = cpu_mapper._tools_root() / "config" / "referencias" / "cpu_mapping_rules.json"
    assert cpu_mapper._rules_file() == expected


def test_ui_api_base_url_prefers_ui_override(monkeypatch) -> None:
    monkeypatch.setenv("CONCILIUM_UI_API_BASE_URL", "http://ui-override:9000/")
    monkeypatch.setenv("CONCILIUM_API_BASE_URL", "http://shared-api:8000")
    monkeypatch.setenv("CONCILIUM_API_HOST", "host-ignored")
    monkeypatch.setenv("CONCILIUM_API_PORT", "9999")

    assert ui_config.resolve_api_base_url() == "http://ui-override:9000"


def test_ui_api_base_url_uses_shared_base_when_no_ui_override(monkeypatch) -> None:
    monkeypatch.delenv("CONCILIUM_UI_API_BASE_URL", raising=False)
    monkeypatch.setenv("CONCILIUM_API_BASE_URL", "http://shared-api:8100/")
    monkeypatch.setenv("CONCILIUM_API_HOST", "host-ignored")
    monkeypatch.setenv("CONCILIUM_API_PORT", "9999")

    assert ui_config.resolve_api_base_url() == "http://shared-api:8100"


def test_ui_api_base_url_uses_host_port_when_no_explicit_base(monkeypatch) -> None:
    monkeypatch.delenv("CONCILIUM_UI_API_BASE_URL", raising=False)
    monkeypatch.delenv("CONCILIUM_API_BASE_URL", raising=False)
    monkeypatch.setenv("CONCILIUM_API_HOST", "api-internal")
    monkeypatch.setenv("CONCILIUM_API_PORT", "8123")

    assert ui_config.resolve_api_base_url() == "http://api-internal:8123"


def test_ui_bind_port_invalid_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("CONCILIUM_UI_PORT", "invalid")

    assert ui_config.resolve_ui_bind_port() == 8501


def test_api_bind_reads_env_vars(monkeypatch) -> None:
    monkeypatch.setenv("CONCILIUM_API_HOST", "0.0.0.0")
    monkeypatch.setenv("CONCILIUM_API_PORT", "8088")

    assert api_config.resolve_api_bind() == ("0.0.0.0", 8088)


def test_api_bind_invalid_port_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("CONCILIUM_API_HOST", "127.0.0.1")
    monkeypatch.setenv("CONCILIUM_API_PORT", "invalid")

    assert api_config.resolve_api_bind() == ("127.0.0.1", 8000)


def test_api_bind_missing_host_falls_back(monkeypatch) -> None:
    monkeypatch.delenv("CONCILIUM_API_HOST", raising=False)
    monkeypatch.delenv("CONCILIUM_API_PORT", raising=False)

    assert api_config.resolve_api_bind() == ("127.0.0.1", 8000)
