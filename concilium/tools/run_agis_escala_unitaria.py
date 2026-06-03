"""Executa o benchmark AGIS com o cenário 'Escala Unitária' (fechar_gap_escala).

O cenário usa referencia_escala_unitaria.json — gerado por
tools/generate_escala_unitaria_scenario.py — onde cada item do cronograma
executa com 1 equipe por semana (prazo estendido de 56 → 203 semanas).

Uso:
    python3 tools/run_agis_escala_unitaria.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from concilium.application.benchmarks.input_derivation import normalize_referencia_weeks
from concilium.application.benchmarks.report_builder import BenchmarkReportBuilder
from concilium.application.benchmarks.report_printer import BenchmarkReportPrinter
from concilium.application.benchmarks.runner import BenchmarkRunner
from concilium.application.benchmarks.spec_loader import load_spec_from_dict


def main() -> int:
    ref_path = ROOT / "benchmarks" / "data" / "AGIS" / "referencia_escala_unitaria.json"
    if not ref_path.exists():
        print(f"[ERRO] Referência não encontrada: {ref_path}")
        print("       Execute primeiro: python3 tools/generate_escala_unitaria_scenario.py")
        return 1

    print(f"\n  Carregando cenário: {ref_path.name}")
    ref_data = json.loads(ref_path.read_text(encoding="utf-8"))
    normalize_referencia_weeks(ref_data)

    spec = load_spec_from_dict(ref_data, ref_path)
    # Override slug e nome para separar artefatos do benchmark baseline
    spec.nome = "AGIS - Ferrovia Nova Transnordestina (Supressao e Terraplanagem - Cenário Escala Unitária)"
    spec.slug = "AGIS_ESCALA_UNITARIA"

    # Force MANUAL_ALLOCATION mode: _norm_ref_ensure_rcpsp_spec auto-generates a
    # rcpsp_spec with activities=[] when the reference has no rcpsp_spec block,
    # which would trigger AUTO_SCHEDULE mode and fail with "rcpsp_spec sem atividades."
    spec.inputs_cronograma.pop("rcpsp_spec", None)

    runner = BenchmarkRunner(
        config_root=ROOT / "config",
        projects_root=ROOT / "benchmarks" / "projetos",
        report_builder=BenchmarkReportBuilder(),
        report_printer=BenchmarkReportPrinter(),
    )

    report = runner.run(spec, reset=True)

    # Save benchmark report to AGIS cenarios dir
    cenario_dir = ROOT / "benchmarks" / "data" / "AGIS" / "cenarios" / "escala_unitaria"
    cenario_dir.mkdir(parents=True, exist_ok=True)
    (cenario_dir / "benchmark_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"\n  [SAVE] Relatório adicional em: {cenario_dir / 'benchmark_report.json'}")
    print(f"  status_final  : {report.get('status_final')}")
    print(f"  quality_gates : {(report.get('quality_gates') or {}).get('decision')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
