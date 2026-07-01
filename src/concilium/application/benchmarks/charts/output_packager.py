"""
Empacotador de saídas do benchmark em arquivo ZIP.

Cria um arquivo compactado com:
  graficos/    — PNGs gerados (se disponíveis)
  relatorio/   — relatório analítico (MD, JSON, XLSX)
  audit/       — benchmark_report.json do cenário M0
  manifest.json — metadados do pacote
"""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _tools_root_from_config(config_root: Path) -> Path:
    """Resolve raiz do workspace a partir do config_root."""
    return config_root.parent


def _find_benchmark_dir(slug: str, config_root: Path | None = None) -> Path | None:
    """Localiza o diretório do benchmark pelo slug."""
    candidates: list[Path] = []

    if config_root:
        candidates.append(_tools_root_from_config(config_root) / "benchmarks" / "data" / slug.upper())

    # Fallback: busca relativa ao arquivo
    candidates.append(Path(__file__).resolve().parents[4] / "benchmarks" / "data" / slug.upper())

    for c in candidates:
        if c.exists():
            return c
    return None


def _cf_collect_graficos(bench_dir: Path, collected: list) -> None:
    """Coleta PNGs e SVGs de outputs/ (recursivamente em visualizations/)."""
    # Tenta novo layout: outputs/visualizations/
    viz_dir = bench_dir / "artifacts" / "outputs" / "visualizations"
    if viz_dir.exists():
        for f in sorted(viz_dir.glob("*.png")):
            collected.append((f, f"graficos/{f.name}"))
        for f in sorted(viz_dir.glob("*.svg")):
            collected.append((f, f"graficos/{f.name}"))
        return

    # Fallback para layout legado
    outputs_dir = bench_dir / "outputs"
    if not outputs_dir.exists():
        return
    for f in sorted(outputs_dir.glob("*.png")):
        collected.append((f, f"graficos/{f.name}"))
    for f in sorted(outputs_dir.glob("*.svg")):
        collected.append((f, f"graficos/{f.name}"))


def _cf_collect_relatorios(bench_dir: Path, collected: list) -> None:
    """Coleta arquivos de relatorio de artifacts/outputs/ (recursivamente em reports/)."""
    # Tenta novo layout: outputs/reports/
    reports_dir = bench_dir / "artifacts" / "outputs" / "reports"
    if reports_dir.exists():
        for ext in ("*.md", "*.json", "*.xlsx", "*.csv", "*.pdf"):
            for f in sorted(reports_dir.glob(ext)):
                collected.append((f, f"relatorio/{f.name}"))
        return

    # Fallback para layout legado
    art_out = bench_dir / "artifacts" / "outputs"
    if not art_out.exists():
        return
    for ext in ("*.md", "*.json", "*.xlsx", "*.csv"):
        for f in sorted(art_out.glob(ext)):
            collected.append((f, f"relatorio/{f.name}"))


def _cf_collect_audit(bench_dir: Path, collected: list) -> None:
    """Coleta JSONs de audit/ (artifacts/audit/ com fallback em audit/)."""
    audit_dir = bench_dir / "artifacts" / "audit"
    if audit_dir.exists():
        for f in sorted(audit_dir.glob("*.json")):
            collected.append((f, f"audit/{f.name}"))
    audit_dir2 = bench_dir / "audit"
    if not audit_dir2.exists():
        return
    existing_arcs = {arc for _, arc in collected}
    for f in sorted(audit_dir2.glob("*.json")):
        arc = f"audit/{f.name}"
        if arc not in existing_arcs:
            collected.append((f, arc))


def _cf_collect_cenarios(bench_dir: Path, collected: list) -> None:
    """Coleta cenarios intermediarios de artifacts/intermediate/."""
    inter_dir = bench_dir / "artifacts" / "intermediate"
    if not inter_dir.exists():
        return
    for f in sorted(inter_dir.glob("*.benchmark_report.json")):
        collected.append((f, f"cenarios/{f.name}"))
    for f in sorted(inter_dir.glob("plan_space_report.*")):
        collected.append((f, f"cenarios/{f.name}"))


def _cf_collect_ref(bench_dir: Path, collected: list) -> None:
    """Coleta referencia.json de inputs (com fallback no raiz)."""
    ref_primary = bench_dir / "artifacts" / "inputs" / "referencia.json"
    if ref_primary.exists():
        collected.append((ref_primary, "inputs/referencia.json"))
        return
    ref_fallback = bench_dir / "referencia.json"
    if ref_fallback.exists():
        collected.append((ref_fallback, "inputs/referencia.json"))


def _collect_files(bench_dir: Path) -> list[tuple[Path, str]]:
    """
    Coleta arquivos a incluir no ZIP.
    Retorna lista de (path_real, path_no_zip).
    """
    collected: list[tuple[Path, str]] = []
    _cf_collect_graficos(bench_dir, collected)
    _cf_collect_relatorios(bench_dir, collected)
    _cf_collect_audit(bench_dir, collected)
    _cf_collect_cenarios(bench_dir, collected)
    _cf_collect_ref(bench_dir, collected)
    return collected


def _gerar_manifest(slug: str, files: list[tuple[Path, str]], bench_dir: Path) -> dict[str, Any]:
    """Cria o manifest.json com metadados do pacote."""
    return {
        "slug": slug.upper(),
        "gerado_em": datetime.now(UTC).isoformat(),
        "benchmark_dir": str(bench_dir),
        "arquivos": [arc_path for _, arc_path in files],
        "totais": {
            "graficos": sum(1 for _, p in files if p.startswith("graficos/")),
            "relatorio": sum(1 for _, p in files if p.startswith("relatorio/")),
            "audit": sum(1 for _, p in files if p.startswith("audit/")),
            "cenarios": sum(1 for _, p in files if p.startswith("cenarios/")),
        },
    }


def empacotar_outputs(
    slug: str,
    config_root: Path | None = None,
    output_path: Path | None = None,
    gerar_graficos: bool = True,
    incluir_cenarios: bool = False,
) -> Path:
    """
    Empacota todos os artefatos de saída de um benchmark em um arquivo ZIP.

    Args:
        slug:             Identificador do benchmark (ex: "AGIS")
        config_root:      Raiz do config para localizar o benchmark
        output_path:      Destino do ZIP (default: benchmark_dir/outputs/)
        gerar_graficos:   Tenta gerar PNGs se não existirem
        incluir_cenarios: Inclui JSONs dos 12 cenários intermediários

    Returns:
        Path do arquivo ZIP criado.
    """
    bench_dir = _find_benchmark_dir(slug, config_root)
    if bench_dir is None:
        raise FileNotFoundError(f"Benchmark '{slug}' não encontrado.")

    # Gera gráficos se solicitado e não existirem
    if gerar_graficos:
        _tentar_gerar_graficos(bench_dir, slug)

    # Coleta arquivos
    files = _collect_files(bench_dir)
    if not incluir_cenarios:
        files = [(p, a) for p, a in files if not a.startswith("cenarios/")]

    if not files:
        raise ValueError(f"Nenhum arquivo de saída encontrado para '{slug}'.")

    # Define destino do ZIP
    if output_path is None:
        outputs_dir = bench_dir / "artifacts" / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M")
        output_path = outputs_dir / f"benchmark_{slug.upper()}_{ts}.zip"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Cria ZIP
    manifest = _gerar_manifest(slug, files, bench_dir)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for real_path, arc_path in files:
            if real_path.exists():
                zf.write(real_path, arc_path)

        # Adiciona manifest
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

    return output_path


def _tentar_gerar_graficos(bench_dir: Path, slug: str) -> None:
    """Tenta gerar PNGs se matplotlib estiver disponível e outputs/ estiver vazio."""
    outputs_dir = bench_dir / "outputs"
    pngs_existentes = list(outputs_dir.glob("*.png")) if outputs_dir.exists() else []

    if pngs_existentes:
        return  # Já existem — não regenera

    try:
        from concilium.application.benchmarks.charts.chart_generator import gerar_graficos_benchmark

        gerar_graficos_benchmark(bench_dir=bench_dir, slug=slug)
    except ImportError:
        pass  # matplotlib não disponível — segue sem gráficos
    except Exception:  # pragma: no cover
        pass  # Falha silenciosa — não bloqueia o empacotamento
