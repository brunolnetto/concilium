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


# ---------------------------------------------------------------------------
# listar_benchmarks — bench_root exists, various slug-dir layouts
# ---------------------------------------------------------------------------


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
            result = tools["empacotar_benchmark"](slug="AGIS", gerar_graficos=True, incluir_cenarios=False)

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


# ---------------------------------------------------------------------------
# executar_benchmark — runner.run raises Exception
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# executar_benchmark — happy path, empacotar=True, empacotar_outputs OK
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# executar_benchmark — happy path, empacotar=True, empacotar_outputs fails
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# executar_benchmark — happy path, empacotar=False
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# executar_benchmark — _SilentPrinter.print is a no-op
# ---------------------------------------------------------------------------
