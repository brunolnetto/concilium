#!/usr/bin/env python3
"""
_benchmark_runner.py â€” Framework unificado para execuÃ§Ã£o de projetos de benchmark.

Cada projeto define um ProjectSpec (dataclass) e chama `run_benchmark(spec)`.
O runner cuida de:
  1. CriaÃ§Ã£o/recuperaÃ§Ã£o do projeto no ProjectStore
  2. ExecuÃ§Ã£o sequencial da pipeline de skills
  3. Carregamento do referencia.json e confronto 1-a-1 com os resultados
  4. EmissÃ£o de um relatÃ³rio de desvios
"""

from __future__ import annotations

import sys as _sys
_sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import os
import sys
from pathlib import Path
from concilium.application.benchmarks import (
    BenchmarkReportBuilder,
    BenchmarkReportPrinter,
    BenchmarkRunner,
    ProjectSpec,
)

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent

sys.path.insert(0, str(_ROOT / "src"))

os.environ.setdefault("CONCILIUM__CONFIG_ROOT",    str(_ROOT / "config"))
os.environ.setdefault("CONCILIUM__PROJECTS_ROOT",  str(_ROOT / "benchmarks" / "projetos"))


def run_benchmark(spec: ProjectSpec, *, reset: bool = False) -> dict:
    """Executa a pipeline completa e retorna relatÃ³rio de confronto."""
    print(f"\n{'='*70}")
    print(f"  BENCHMARK : {spec.nome}")
    print(f"  Slug      : {spec.slug}")
    print(f"{'='*70}\n")

    runner = BenchmarkRunner(
        config_root=Path(os.environ["CONCILIUM__CONFIG_ROOT"]),
        projects_root=Path(os.environ["CONCILIUM__PROJECTS_ROOT"]),
        report_builder=BenchmarkReportBuilder(),
        report_printer=BenchmarkReportPrinter(),
    )
    return runner.run(spec, reset=reset)

# â”€â”€â”€ Entry point para uso direto â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

if __name__ == "__main__":
    print("Este mÃ³dulo deve ser importado por run_rosh.py, run_agis.py, etc.")
    print("Uso: python run_rosh.py [--reset]")
