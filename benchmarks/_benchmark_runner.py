#!/usr/bin/env python3
“””Framework unificado para execução de projetos de benchmark.

Cada projeto define um ProjectSpec (dataclass) e chama `run_benchmark(spec)`.
O runner cuida de:
  1. Criação/recuperação do projeto no ProjectStore
  2. Execução sequencial da pipeline de skills
  3. Carregamento do referencia.json e confronto 1-a-1 com os resultados
  4. Emissão de um relatório de desvios
  5. Registro da execução no BenchmarkStore para auditabilidade (NEP-039)

Configuração via CONCILIUM__* env vars (infrastructure/settings.py):
  CONCILIUM__CONFIG_ROOT              — catálogo, perfis, contextos
  CONCILIUM__BENCHMARK_PROJECTS_ROOT  — sorvedouro de projetos de benchmark
“””

from __future__ import annotations

import sys as _sys

_sys.stdout.reconfigure(encoding=”utf-8”, errors=”replace”)

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT / “src”))

from concilium.application.benchmarks import (
    BenchmarkReportBuilder,
    BenchmarkReportPrinter,
    BenchmarkRunner,
    ProjectSpec,
)


def run_benchmark(spec: ProjectSpec, *, reset: bool = False) -> dict:
    “””Executa a pipeline completa e retorna relatório de confronto.

    Usa BenchmarkRunner.from_settings() — lê caminhos de CONCILIUM__* env vars
    via infrastructure/settings.py. Não é necessário patchear env vars manualmente.
    “””
    print(f”\n{'='*70}”)
    print(f”  BENCHMARK : {spec.nome}”)
    print(f”  Slug      : {spec.slug}”)
    print(f”{'='*70}\n”)

    runner = BenchmarkRunner.from_settings(
        report_builder=BenchmarkReportBuilder(),
        report_printer=BenchmarkReportPrinter(),
    )
    return runner.run(spec, reset=reset)


# ---------------- Entry point para uso direto ----------------------------------------

if __name__ == “__main__”:
    print(“Este módulo deve ser importado por run_rosh.py, run_agis.py, etc.”)
    print(“Uso: python run_rosh.py [--reset]”)
