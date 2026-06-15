"""Tests for MCP benchmark tools: listar_benchmarks, empacotar_benchmark,
download_benchmark_zip, executar_benchmark.

Coverage targets:
  benchmark.py lines 23-24, 26-27, 29-35, 37-42, 44-50, 52, 64, 82, 84-85,
  91-94, 96, 98-102, 104, 130-132, 134-135, 137-138, 140-145, 148, 150-153,
  155-157, 163-164, 192-197, 199-200, 202-204, 206-208, 210-211, 217-220,
  222, 230-231, 233-238, 240
"""

from __future__ import annotations

import base64
import json
import os
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from concilium.presentation.mcp.tools.benchmark import register


# ---------------------------------------------------------------------------
# Helper: build a FastMCP server with benchmark tools registered and extract
# the inner callables by name.
# ---------------------------------------------------------------------------

def _make_server_and_tools(monkeypatch, config_dir: Path) -> dict:
    """Register benchmark tools and return a dict of {name: callable}."""
    monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(config_dir))

    server = FastMCP("test-bench")
    register(server)

    tools: dict = {}
    for tool_obj in server._tool_manager.list_tools():
        fn = getattr(tool_obj, "fn", None) or getattr(tool_obj, "func", None)
        tools[tool_obj.name] = fn
    return tools


def _bench_root(config_dir: Path) -> Path:
    """Mirror the path computed inside the tool closure."""
    return config_dir.parent / "benchmarks" / "data"


# ---------------------------------------------------------------------------
# listar_benchmarks — bench_root does not exist
# ---------------------------------------------------------------------------


def test_listar_benchmarks_no_bench_root(monkeypatch, tmp_path):
    """bench_root missing → returns empty benchmarks list (lines 23-27)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    tools = _make_server_and_tools(monkeypatch, config_dir)
    result = tools["listar_benchmarks"]()

    assert "benchmarks" in result
    assert result["benchmarks"] == []


# ---------------------------------------------------------------------------
# listar_benchmarks — bench_root exists, various slug-dir layouts
# ---------------------------------------------------------------------------


def test_listar_benchmarks_slug_with_referencia_at_root(monkeypatch, tmp_path):
    """Slug dir with referencia.json at root → reads nome from 'projeto' key (lines 29-64)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    bench_root = _bench_root(config_dir)
    slug_dir = bench_root / "AGIS"
    slug_dir.mkdir(parents=True)

    ref = {"projeto": "AGIS Projeto Teste"}
    (slug_dir / "referencia.json").write_text(json.dumps(ref), encoding="utf-8")

    tools = _make_server_and_tools(monkeypatch, config_dir)
    result = tools["listar_benchmarks"]()

    assert result["total"] == 1
    assert result["benchmarks"][0]["nome"] == "AGIS Projeto Teste"
    assert result["benchmarks"][0]["slug"] == "AGIS"
    assert "schema_version" in result


def test_listar_benchmarks_referencia_under_artifacts_inputs(monkeypatch, tmp_path):
    """referencia.json under artifacts/inputs is found (lines 33-35)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    bench_root = _bench_root(config_dir)
    slug_dir = bench_root / "FOO"
    art_in = slug_dir / "artifacts" / "inputs"
    art_in.mkdir(parents=True)

    ref = {"projeto": "Foo Benchmark"}
    (art_in / "referencia.json").write_text(json.dumps(ref), encoding="utf-8")

    tools = _make_server_and_tools(monkeypatch, config_dir)
    result = tools["listar_benchmarks"]()

    assert result["benchmarks"][0]["nome"] == "Foo Benchmark"
    assert result["benchmarks"][0]["tem_referencia"] is True


def test_listar_benchmarks_outputs_pngs_zips_reports(monkeypatch, tmp_path):
    """outputs dir with PNGs and ZIPs; artifacts/outputs with .md reports (lines 37-42)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    bench_root = _bench_root(config_dir)
    slug_dir = bench_root / "BAR"
    outputs_dir = slug_dir / "outputs"
    outputs_dir.mkdir(parents=True)
    (outputs_dir / "chart.png").write_bytes(b"")
    (outputs_dir / "results.zip").write_bytes(b"PK")

    art_out = slug_dir / "artifacts" / "outputs"
    art_out.mkdir(parents=True)
    (art_out / "report.md").write_text("# report")
    (art_out / "data.json").write_text("{}")

    audit_dir = slug_dir / "artifacts" / "audit"
    audit_dir.mkdir(parents=True)
    (audit_dir / "benchmark_report.json").write_text("{}")

    tools = _make_server_and_tools(monkeypatch, config_dir)
    result = tools["listar_benchmarks"]()

    entry = result["benchmarks"][0]
    assert entry["graficos"] == 1
    assert "results.zip" in entry["zips_disponiveis"]
    assert entry["relatorios"] == 2
    assert entry["tem_audit"] is True


def test_listar_benchmarks_referencia_json_parse_error(monkeypatch, tmp_path):
    """referencia.json with invalid JSON → falls back to slug name (lines 46-50)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    bench_root = _bench_root(config_dir)
    slug_dir = bench_root / "BADSIG"
    slug_dir.mkdir(parents=True)
    (slug_dir / "referencia.json").write_text("NOT JSON {{{{ invalid", encoding="utf-8")

    tools = _make_server_and_tools(monkeypatch, config_dir)
    result = tools["listar_benchmarks"]()

    assert result["benchmarks"][0]["nome"] == "BADSIG"


def test_listar_benchmarks_skips_files_at_bench_root(monkeypatch, tmp_path):
    """Non-directory entries at bench_root are skipped (lines 30-32)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    bench_root = _bench_root(config_dir)
    bench_root.mkdir(parents=True)
    (bench_root / "some_file.txt").write_text("ignored")

    slug_dir = bench_root / "REAL"
    slug_dir.mkdir()
    (slug_dir / "referencia.json").write_text(json.dumps({"projeto": "Real"}))

    tools = _make_server_and_tools(monkeypatch, config_dir)
    result = tools["listar_benchmarks"]()

    slugs = [b["slug"] for b in result["benchmarks"]]
    assert "REAL" in slugs
    assert "some_file.txt" not in slugs


def test_listar_benchmarks_total_count(monkeypatch, tmp_path):
    """total key reflects number of benchmarks found (line 64)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    bench_root = _bench_root(config_dir)
    for name in ("A1", "A2", "A3"):
        d = bench_root / name
        d.mkdir(parents=True)
        (d / "referencia.json").write_text(json.dumps({"projeto": name}))

    tools = _make_server_and_tools(monkeypatch, config_dir)
    result = tools["listar_benchmarks"]()

    assert result["total"] == 3


# ---------------------------------------------------------------------------
# empacotar_benchmark — happy path
# ---------------------------------------------------------------------------


def test_empacotar_benchmark_happy_path(monkeypatch, tmp_path):
    """empacotar_outputs succeeds → zipfile introspected, _wrap_response returned (lines 82-104)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Create a real tiny zip file so zipfile.ZipFile can open it
    zip_path = tmp_path / "pack.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("relatorio/report.md", "# report")
        zf.writestr("graficos/chart.png", b"\x89PNG")

    # Make the zip_path a real Path with a known stat
    mock_zip_path = MagicMock(spec=Path)
    mock_zip_path.__str__ = lambda s: str(zip_path)
    mock_zip_path.__truediv__ = lambda s, o: zip_path / o
    # Make stat().st_size return a small number
    mock_stat = MagicMock()
    mock_stat.st_size = 1024
    mock_zip_path.stat.return_value = mock_stat

    with patch(
        "concilium.application.benchmarks.charts.output_packager.empacotar_outputs",
        return_value=mock_zip_path,
    ) as mock_pack:
        # Also patch zipfile.ZipFile to use the real file
        original_zipfile = zipfile.ZipFile

        def _open_real(path, *args, **kwargs):
            return original_zipfile(zip_path, *args, **kwargs)

        with patch("zipfile.ZipFile", side_effect=_open_real):
            tools = _make_server_and_tools(monkeypatch, config_dir)
            result = tools["empacotar_benchmark"](
                slug="AGIS", gerar_graficos=True, incluir_cenarios=False
            )

    assert "zip_path" in result
    assert "tamanho_bytes" in result
    assert "conteudo" in result
    assert "schema_version" in result
    mock_pack.assert_called_once()


# ---------------------------------------------------------------------------
# empacotar_benchmark — error paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc,expected_fragment",
    [
        (FileNotFoundError("Benchmark AGIS não encontrado"), "Benchmark AGIS não encontrado"),
        (RuntimeError("erro genérico"), "Falha ao empacotar:"),
    ],
)
def test_empacotar_benchmark_errors(monkeypatch, tmp_path, exc, expected_fragment):
    """FileNotFoundError and generic Exception → respective error dicts (lines 91-94)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    with patch(
        "concilium.application.benchmarks.charts.output_packager.empacotar_outputs",
        side_effect=exc,
    ):
        tools = _make_server_and_tools(monkeypatch, config_dir)
        result = tools["empacotar_benchmark"](slug="AGIS")

    assert "erro" in result
    assert expected_fragment in result["erro"]


# ---------------------------------------------------------------------------
# download_benchmark_zip — slug_dir does not exist
# ---------------------------------------------------------------------------


def test_download_benchmark_zip_slug_not_found(monkeypatch, tmp_path):
    """slug_dir missing → {"erro": ...} (lines 130-135)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    bench_root = _bench_root(config_dir)
    bench_root.mkdir(parents=True)

    tools = _make_server_and_tools(monkeypatch, config_dir)
    result = tools["download_benchmark_zip"](slug="GHOST")

    assert "erro" in result
    assert "GHOST" in result["erro"]


# ---------------------------------------------------------------------------
# download_benchmark_zip — zip_nome specified, file exists
# ---------------------------------------------------------------------------


def test_download_benchmark_zip_zip_nome_exists(monkeypatch, tmp_path):
    """zip_nome given and target exists → base64 response (lines 137-145, 155-164)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    bench_root = _bench_root(config_dir)
    slug_dir = bench_root / "AGIS"
    outputs_dir = slug_dir / "outputs"
    outputs_dir.mkdir(parents=True)

    # Create a small real zip
    zip_path = outputs_dir / "pack.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("hello.txt", "hello")

    tools = _make_server_and_tools(monkeypatch, config_dir)
    result = tools["download_benchmark_zip"](slug="AGIS", zip_nome="pack.zip")

    assert "conteudo_base64" in result
    decoded = base64.b64decode(result["conteudo_base64"])
    assert decoded[:2] == b"PK"  # ZIP magic bytes
    assert "schema_version" in result


# ---------------------------------------------------------------------------
# download_benchmark_zip — zip_nome specified but missing
# ---------------------------------------------------------------------------


def test_download_benchmark_zip_zip_nome_missing(monkeypatch, tmp_path):
    """zip_nome given but not on disk → {"erro": ...} (lines 140-143)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    bench_root = _bench_root(config_dir)
    slug_dir = bench_root / "AGIS"
    (slug_dir / "outputs").mkdir(parents=True)

    tools = _make_server_and_tools(monkeypatch, config_dir)
    result = tools["download_benchmark_zip"](slug="AGIS", zip_nome="missing.zip")

    assert "erro" in result
    assert "missing.zip" in result["erro"]


# ---------------------------------------------------------------------------
# download_benchmark_zip — no zip_nome, zips present → picks most recent
# ---------------------------------------------------------------------------


def test_download_benchmark_zip_picks_most_recent_zip(monkeypatch, tmp_path):
    """no zip_nome, zips sorted → picks first (most recent) (lines 144-145)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    bench_root = _bench_root(config_dir)
    slug_dir = bench_root / "AGIS"
    outputs_dir = slug_dir / "outputs"
    outputs_dir.mkdir(parents=True)

    # Two zips — sorted(..., reverse=True) gives "z_later.zip" first alphabetically
    for name in ("a_older.zip", "z_later.zip"):
        p = outputs_dir / name
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr(f"{name}.txt", "data")

    tools = _make_server_and_tools(monkeypatch, config_dir)
    result = tools["download_benchmark_zip"](slug="AGIS")

    assert "conteudo_base64" in result
    assert result["nome_arquivo"] == "z_later.zip"


# ---------------------------------------------------------------------------
# download_benchmark_zip — no zip_nome, no zips → calls empacotar_outputs; exception
# ---------------------------------------------------------------------------


def test_download_benchmark_zip_no_zips_empacotar_fails(monkeypatch, tmp_path):
    """no zips → calls empacotar_outputs; exception → {"erro": ...} (lines 148-153)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    bench_root = _bench_root(config_dir)
    slug_dir = bench_root / "AGIS"
    (slug_dir / "outputs").mkdir(parents=True)

    with patch(
        "concilium.application.benchmarks.charts.output_packager.empacotar_outputs",
        side_effect=RuntimeError("pack failed"),
    ):
        tools = _make_server_and_tools(monkeypatch, config_dir)
        result = tools["download_benchmark_zip"](slug="AGIS")

    assert "erro" in result
    assert "pack failed" in result["erro"]


# ---------------------------------------------------------------------------
# download_benchmark_zip — file > 20 MB → aviso response
# ---------------------------------------------------------------------------


def test_download_benchmark_zip_large_file_aviso(monkeypatch, tmp_path):
    """size > 20 MB → aviso dict without base64 (lines 155-161).

    Strategy: write a file large enough to actually exceed 20 MB so no stat
    patching is needed and glob / is_dir work normally.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    bench_root = _bench_root(config_dir)
    slug_dir = bench_root / "AGIS"
    outputs_dir = slug_dir / "outputs"
    outputs_dir.mkdir(parents=True)

    # Write a real zip that is > 20 MB when read via stat().st_size.
    # We store uncompressed data so the ZIP on-disk is large.
    zip_path = outputs_dir / "huge.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
        # 21 MB of zeros — stored uncompressed
        zf.writestr("big.bin", b"\x00" * (21 * 1024 * 1024))

    tools = _make_server_and_tools(monkeypatch, config_dir)
    result = tools["download_benchmark_zip"](slug="AGIS", zip_nome="huge.zip")

    assert "aviso" in result
    assert "zip_path" in result
    assert "instrucao" in result


# ---------------------------------------------------------------------------
# download_benchmark_zip — no zip_nome, no zips → empacotar OK, size <= 20 MB
# ---------------------------------------------------------------------------


def test_download_benchmark_zip_no_zips_empacotar_ok_small(monkeypatch, tmp_path):
    """no zips → empacotar_outputs OK, size <= 20 MB → base64 content (lines 148-164)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    bench_root = _bench_root(config_dir)
    slug_dir = bench_root / "AGIS"
    (slug_dir / "outputs").mkdir(parents=True)

    # Create a real zip to return from empacotar_outputs
    zip_path = tmp_path / "generated.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("report.txt", "benchmark output")

    with patch(
        "concilium.application.benchmarks.charts.output_packager.empacotar_outputs",
        return_value=zip_path,
    ):
        tools = _make_server_and_tools(monkeypatch, config_dir)
        result = tools["download_benchmark_zip"](slug="AGIS")

    assert "conteudo_base64" in result
    assert "schema_version" in result


# ---------------------------------------------------------------------------
# executar_benchmark — find_benchmark_reference returns None
# ---------------------------------------------------------------------------


def test_executar_benchmark_not_found(monkeypatch, tmp_path):
    """find_benchmark_reference None → {"erro": ...} (lines 192-204)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    bench_root = _bench_root(config_dir)
    bench_root.mkdir(parents=True)

    with patch(
        "concilium.application.benchmarks.execution.batch.find_benchmark_reference",
        return_value=None,
    ):
        tools = _make_server_and_tools(monkeypatch, config_dir)
        result = tools["executar_benchmark"](slug="MISSING")

    assert "erro" in result
    assert "MISSING" in result["erro"]


# ---------------------------------------------------------------------------
# executar_benchmark — runner.run raises Exception
# ---------------------------------------------------------------------------


def test_executar_benchmark_runner_raises(monkeypatch, tmp_path):
    """runner.run raises → {"erro": "Falha na execução: ..."} (lines 217-220)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    bench_root = _bench_root(config_dir)
    bench_root.mkdir(parents=True)

    fake_ref_path = tmp_path / "referencia.json"
    fake_ref_path.write_text(json.dumps({"projeto": "Test"}))

    mock_spec = MagicMock()

    with (
        patch(
            "concilium.application.benchmarks.execution.batch.find_benchmark_reference",
            return_value=fake_ref_path,
        ),
        patch(
            "concilium.application.benchmarks.spec.spec_loader.BenchmarkSpecLoader.load",
            return_value=mock_spec,
        ),
        patch(
            "concilium.application.benchmarks.execution.runner.BenchmarkRunner.run",
            side_effect=RuntimeError("execution failed"),
        ),
    ):
        tools = _make_server_and_tools(monkeypatch, config_dir)
        result = tools["executar_benchmark"](slug="AGIS")

    assert "erro" in result
    assert "Falha na execução:" in result["erro"]


# ---------------------------------------------------------------------------
# executar_benchmark — happy path, empacotar=True, empacotar_outputs OK
# ---------------------------------------------------------------------------


def test_executar_benchmark_happy_empacotar_true(monkeypatch, tmp_path):
    """Happy path with empacotar=True → resultado includes zip_path/zip_mb (lines 222-240)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    bench_root = _bench_root(config_dir)
    bench_root.mkdir(parents=True)

    fake_ref_path = tmp_path / "referencia.json"
    fake_ref_path.write_text(json.dumps({"projeto": "Test"}))

    mock_spec = MagicMock()
    mock_report = {
        "status_final": "OK",
        "confronto": {"deltas": {"preco_venda": {"percentual": 1.5}}},
    }

    zip_path = tmp_path / "output.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("x.txt", "data")

    with (
        patch(
            "concilium.application.benchmarks.execution.batch.find_benchmark_reference",
            return_value=fake_ref_path,
        ),
        patch(
            "concilium.application.benchmarks.spec.spec_loader.BenchmarkSpecLoader.load",
            return_value=mock_spec,
        ),
        patch(
            "concilium.application.benchmarks.execution.runner.BenchmarkRunner.run",
            return_value=mock_report,
        ),
        patch(
            "concilium.application.benchmarks.charts.output_packager.empacotar_outputs",
            return_value=zip_path,
        ),
    ):
        tools = _make_server_and_tools(monkeypatch, config_dir)
        result = tools["executar_benchmark"](slug="AGIS", empacotar=True)

    assert "zip_path" in result
    assert "zip_mb" in result
    assert result["slug"] == "AGIS"
    assert "schema_version" in result


# ---------------------------------------------------------------------------
# executar_benchmark — happy path, empacotar=True, empacotar_outputs fails
# ---------------------------------------------------------------------------


def test_executar_benchmark_empacotar_fails(monkeypatch, tmp_path):
    """empacotar_outputs raises after successful run → aviso_pack in resultado (lines 233-238)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    bench_root = _bench_root(config_dir)
    bench_root.mkdir(parents=True)

    fake_ref_path = tmp_path / "referencia.json"
    fake_ref_path.write_text(json.dumps({"projeto": "Test"}))

    mock_spec = MagicMock()
    mock_report = {"status_final": "OK", "confronto": {}}

    with (
        patch(
            "concilium.application.benchmarks.execution.batch.find_benchmark_reference",
            return_value=fake_ref_path,
        ),
        patch(
            "concilium.application.benchmarks.spec.spec_loader.BenchmarkSpecLoader.load",
            return_value=mock_spec,
        ),
        patch(
            "concilium.application.benchmarks.execution.runner.BenchmarkRunner.run",
            return_value=mock_report,
        ),
        patch(
            "concilium.application.benchmarks.charts.output_packager.empacotar_outputs",
            side_effect=OSError("disk full"),
        ),
    ):
        tools = _make_server_and_tools(monkeypatch, config_dir)
        result = tools["executar_benchmark"](slug="AGIS", empacotar=True)

    assert "aviso_pack" in result
    assert "disk full" in result["aviso_pack"]
    assert "schema_version" in result


# ---------------------------------------------------------------------------
# executar_benchmark — happy path, empacotar=False
# ---------------------------------------------------------------------------


def test_executar_benchmark_no_empacotar(monkeypatch, tmp_path):
    """empacotar=False → no zip keys in resultado (lines 230, 240)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    bench_root = _bench_root(config_dir)
    bench_root.mkdir(parents=True)

    fake_ref_path = tmp_path / "referencia.json"
    fake_ref_path.write_text(json.dumps({"projeto": "Test"}))

    mock_spec = MagicMock()
    mock_report = {
        "quality_gates": {"decision": "APROVADO"},
        "confronto": {"deltas": {}},
    }

    with (
        patch(
            "concilium.application.benchmarks.execution.batch.find_benchmark_reference",
            return_value=fake_ref_path,
        ),
        patch(
            "concilium.application.benchmarks.spec.spec_loader.BenchmarkSpecLoader.load",
            return_value=mock_spec,
        ),
        patch(
            "concilium.application.benchmarks.execution.runner.BenchmarkRunner.run",
            return_value=mock_report,
        ),
    ):
        tools = _make_server_and_tools(monkeypatch, config_dir)
        result = tools["executar_benchmark"](slug="AGIS", empacotar=False)

    assert "zip_path" not in result
    assert "zip_mb" not in result
    assert result["slug"] == "AGIS"
    assert "schema_version" in result


# ---------------------------------------------------------------------------
# executar_benchmark — _SilentPrinter.print is a no-op
# ---------------------------------------------------------------------------


def test_executar_benchmark_silent_printer_noop(monkeypatch, tmp_path):
    """_SilentPrinter.print is a no-op — calling it does not raise (lines 206-208)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    bench_root = _bench_root(config_dir)
    bench_root.mkdir(parents=True)

    fake_ref_path = tmp_path / "referencia.json"
    fake_ref_path.write_text(json.dumps({"projeto": "Test"}))

    mock_spec = MagicMock()
    mock_report = {"status_final": "OK", "confronto": {}}

    captured_printer = {}

    original_init = __import__(
        "concilium.application.benchmarks.execution.runner",
        fromlist=["BenchmarkRunner"],
    ).BenchmarkRunner.__init__

    def _capturing_init(self, **kwargs):
        captured_printer["printer"] = kwargs.get("report_printer")
        object.__setattr__(self, "config_root", kwargs["config_root"])
        object.__setattr__(self, "projects_root", kwargs["projects_root"])
        object.__setattr__(self, "report_builder", kwargs["report_builder"])
        object.__setattr__(self, "report_printer", kwargs["report_printer"])

    with (
        patch(
            "concilium.application.benchmarks.execution.batch.find_benchmark_reference",
            return_value=fake_ref_path,
        ),
        patch(
            "concilium.application.benchmarks.spec.spec_loader.BenchmarkSpecLoader.load",
            return_value=mock_spec,
        ),
        patch(
            "concilium.application.benchmarks.execution.runner.BenchmarkRunner.run",
            return_value=mock_report,
        ),
        patch(
            "concilium.application.benchmarks.charts.output_packager.empacotar_outputs",
            side_effect=OSError("skip"),
        ),
        patch(
            "concilium.application.benchmarks.execution.runner.BenchmarkRunner.__init__",
            _capturing_init,
        ),
    ):
        tools = _make_server_and_tools(monkeypatch, config_dir)
        tools["executar_benchmark"](slug="AGIS", empacotar=True)

    printer = captured_printer.get("printer")
    if printer is not None:
        # _SilentPrinter.print should silently accept any dict without error
        printer.print({"status": "OK"})  # must not raise
