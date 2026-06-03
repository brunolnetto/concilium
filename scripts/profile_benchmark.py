#!/usr/bin/env python3
"""Profila um benchmark (padrão: PRIVATE_LOG) e exibe top gargalos.

Uso:
    python scripts/profile_benchmark.py [--slug SLUG] [--top N]

Saída:
    - Tempo por skill (do invocations.log)
    - Top N funções por tempo cumulativo (cProfile)
    - Resumo textual dos gargalos
"""

from __future__ import annotations

import argparse
import cProfile
import io
import json
import os
import pstats
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT / "src"))

os.environ.setdefault("CONCILIUM_CONFIG_ROOT", str(_ROOT / "config"))
os.environ.setdefault("CONCILIUM_PROJECTS_ROOT", str(_ROOT / "projetos"))


def _run_benchmark(slug: str) -> tuple[dict, Path | None]:
    from concilium.application.benchmarks import BenchmarkFacade

    root = _ROOT
    facade = BenchmarkFacade.from_root(root)
    report = facade.run_single(slug.upper(), reset=True)

    # Localiza o projeto recém-criado para ler o invocations.log
    project_dir = None
    slug_upper = slug.upper()
    nome_esperado = report.get("spec", {}).get("nome") or slug_upper
    if facade.projects_root.exists():
        for d in facade.projects_root.iterdir():
            meta_path = d / "meta.json"
            if d.is_dir() and meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    if meta.get("nome") == nome_esperado or slug_upper in meta.get("nome", "").upper():
                        project_dir = d
                        break
                except Exception:
                    pass
    return report, project_dir


def _read_skill_timings(project_dir: Path) -> list[dict]:
    if project_dir is None:
        return []
    log_path = project_dir / "v1" / "invocations.log"
    if not log_path.exists():
        return []
    rows = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if "skill" in entry and "duration_ms" in entry:
                rows.append({"skill": entry["skill"], "duration_ms": entry["duration_ms"], "status": entry.get("status", "?")})
        except Exception:
            pass
    return sorted(rows, key=lambda r: r["duration_ms"], reverse=True)


def _print_skill_timings(timings: list[dict]) -> None:
    total = sum(r["duration_ms"] for r in timings)
    print(f"\n{'='*60}")
    print(f"  TEMPO POR SKILL  (total pipeline: {total} ms)")
    print(f"{'='*60}")
    print(f"  {'Skill':<35} {'ms':>7}  {'%':>6}  Status")
    print(f"  {'-'*35} {'-'*7}  {'-'*6}  ------")
    for r in timings:
        pct = r["duration_ms"] / total * 100 if total else 0
        bar = "#" * int(pct / 2)
        print(f"  {r['skill']:<35} {r['duration_ms']:>7}  {pct:>5.1f}%  {r['status']}  {bar}")
    print(f"  {'TOTAL':<35} {total:>7}  100.0%")


def _print_cprofile_top(pr: cProfile.Profile, top_n: int) -> None:
    stream = io.StringIO()
    ps = pstats.Stats(pr, stream=stream)
    ps.sort_stats("cumulative")
    ps.print_stats(top_n)
    output = stream.getvalue()

    print(f"\n{'='*60}")
    print(f"  TOP {top_n} FUNÇÕES (tempo cumulativo — cProfile)")
    print(f"{'='*60}")
    # Filtra linhas relevantes (remove linhas de built-ins e stdlib curtas)
    skip_patterns = ("<frozen", "importlib", "_bootstrap", "posixpath", "ntpath")
    for line in output.splitlines():
        if any(p in line for p in skip_patterns):
            continue
        print(line)


def main() -> int:
    parser = argparse.ArgumentParser(description="Profila benchmark Concilium")
    parser.add_argument("--slug", default="PRIVATE_LOG", help="Slug do benchmark")
    parser.add_argument("--top", type=int, default=25, help="Top N funções no cProfile")
    args = parser.parse_args()

    print(f"\n[PROFILE] Iniciando profiling do benchmark '{args.slug}'...")
    print("[PROFILE] Reset=True — projeto será recriado do zero.\n")

    pr = cProfile.Profile()
    t0 = time.perf_counter()
    pr.enable()
    try:
        report, project_dir = _run_benchmark(args.slug)
    finally:
        pr.disable()
    elapsed = time.perf_counter() - t0

    timings = _read_skill_timings(project_dir)
    _print_skill_timings(timings)
    _print_cprofile_top(pr, args.top)

    print(f"\n[PROFILE] Tempo total medido externamente: {elapsed:.2f}s")
    print(f"[PROFILE] Projeto: {project_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
