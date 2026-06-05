import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# ADR-043: Usar BenchmarkFacade como ponto de entrada unificado.
# Se CONCILIUM__ROOT estiver definido (execução via C:\Temp\), usa-o.
# Caso contrário, infere a raiz a partir deste arquivo.
from concilium.application.benchmarks import BenchmarkFacade, BenchmarkBatchRunner

def run_all():
    root = Path(os.environ.get("CONCILIUM__ROOT", Path(__file__).resolve().parent.parent))
    concilium_root = Path(root)

    os.environ.setdefault("CONCILIUM__CONFIG_ROOT", str(concilium_root / "config"))
    os.environ.setdefault("CONCILIUM__PROJECTS_ROOT", str(concilium_root / "benchmarks" / "projetos"))

    facade = BenchmarkFacade.from_root(concilium_root)
    reports = facade.run_all(reset=True)

    batch_runner = BenchmarkBatchRunner(
        benchmarks_root=facade.benchmarks_root,
        config_root=facade.config_root,
        projects_root=facade.projects_root,
    )
    summary = batch_runner.build_summary(reports)
    from datetime import UTC, datetime
    summary_artifact = {
        "meta": {"gerado_em": datetime.now(UTC).isoformat(), "total": len(reports)},
        "rows": summary,
    }

    summary_file = concilium_root / "BENCHMARK_SUMMARY.json"
    summary_file.write_text(json.dumps(summary_artifact, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
            
    print(f"\n\n{'='*92}")
    print(f"{'RESUMO DOS BENCHMARKS':^92}")
    print(f"{'='*92}")
    print(f"{'PROJETO':<28} | {'STATUS':<26} | {'DIR %':<10} | {'IND %':<10} | {'TOTAL %':<10} | {'VENDA %':<10}")
    print("-" * 92)
    for s in summary:
        print(
            f"{s['Projeto']:<28} | {s['Status']:<26} | {s['Delta Direto %']:<10} | {s['Delta Indireto %']:<10} | {s['Delta Total %']:<10} | {s['Delta Venda %']:<10}"
        )
    print(f"{'='*92}\n")
    from collections import Counter
    status_counts = Counter(s["Status"] for s in summary)
    print(f"[OK] Summary salvo em: {summary_file}")
    print(f"[OK] Status counts: {dict(status_counts)}")

if __name__ == "__main__":
    run_all()
