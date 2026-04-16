#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Runner CLI de Evals — AGIS Gerente de Engenharia

Executa os testes das 4 layers + E2E + trieval (opcional)
e produz um relatório de qualidade no terminal.

Uso:
    python evals/run_evals.py                   # evals sem LLM
    python evals/run_evals.py --with-llm        # inclui trieval (requer OPENAI_API_KEY)
    python evals/run_evals.py --layer 2         # só Layer 2
    python evals/run_evals.py --only-e2e        # só E2E
    python evals/run_evals.py --report          # gera relatório JSON
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVALS_DIR = ROOT / "evals"


def run_pytest(
    args: list[str],
    label: str,
    capture: bool = False,
) -> tuple[int, str]:
    """Executa pytest e retorna (exit_code, output)."""
    cmd = [sys.executable, "-m", "pytest"] + args
    if capture:
        result = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True
        )
        return result.returncode, result.stdout + result.stderr
    else:
        print(f"\n{'='*60}")
        print(f"  {label}")
        print(f"{'='*60}")
        result = subprocess.run(cmd, cwd=ROOT)
        return result.returncode, ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Runner de evals AGIS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--layer", type=int, choices=[1, 2, 3, 4],
        help="Executar apenas evals de uma layer específica"
    )
    parser.add_argument(
        "--only-e2e", action="store_true",
        help="Executar apenas evals E2E"
    )
    parser.add_argument(
        "--with-llm", action="store_true",
        help="Incluir testes trieval (requer OPENAI_API_KEY)"
    )
    parser.add_argument(
        "--report", action="store_true",
        help="Gerar relatório JSON em evals/report.json"
    )
    parser.add_argument(
        "--fail-fast", "-x", action="store_true",
        help="Parar na primeira falha"
    )
    return parser.parse_args()


LAYER_FILES = {
    1: "evals/test_skill1_base_data.py",
    2: "evals/test_skill2_operational.py",
    3: "evals/test_skill3_planning.py",
    4: "evals/test_skill4_financial.py",
}

SUITE_LABELS = {
    1: "Layer 1 — Base Data",
    2: "Layer 2 — Cálculo Operacional",
    3: "Layer 3 — Planejamento",
    4: "Layer 4 — Validação Financeira",
    "e2e": "E2E — Workflow Completo (4 Gates)",
    "trieval": "trieval — RAG Quality (LLM)",
    "structure": "trieval — Estrutura dos Casos (sem LLM)",
}


def main() -> int:
    args = parse_args()
    results: dict[str, dict] = {}
    overall_exit = 0

    suites: list[tuple[str, list[str], str]] = []

    # ── Selecionar suítes ────────────────────────────────────────────────
    if args.layer:
        suites.append((
            str(args.layer),
            [LAYER_FILES[args.layer], "-v"],
            SUITE_LABELS[args.layer],
        ))
    elif args.only_e2e:
        suites.append((
            "e2e",
            ["evals/test_e2e_workflow.py", "-v"],
            SUITE_LABELS["e2e"],
        ))
    else:
        # Todos os layers + E2E
        for layer_id, path in LAYER_FILES.items():
            suites.append((str(layer_id), [path, "-v"], SUITE_LABELS[layer_id]))
        suites.append((
            "e2e",
            ["evals/test_e2e_workflow.py", "-v"],
            SUITE_LABELS["e2e"],
        ))
        # trieval — sempre roda a suite de estrutura (sem LLM)
        suites.append((
            "structure",
            [
                "evals/test_trieval_integration.py",
                "-v", "-m", "not trieval",
            ],
            SUITE_LABELS["structure"],
        ))

    # trieval com LLM é opt-in
    if args.with_llm:
        suites.append((
            "trieval",
            ["evals/test_trieval_integration.py", "-v", "-m", "trieval"],
            SUITE_LABELS["trieval"],
        ))

    # fail-fast flag
    base_flags: list[str] = []
    if args.fail_fast:
        base_flags.append("-x")

    # ── Executar suítes ──────────────────────────────────────────────────
    capture = args.report

    for suite_id, pytest_args, label in suites:
        full_args = pytest_args + base_flags
        exit_code, output = run_pytest(full_args, label, capture=capture)
        results[suite_id] = {
            "label": label,
            "exit_code": exit_code,
            "passed": exit_code == 0,
            "output": output if capture else None,
        }
        if exit_code != 0:
            overall_exit = 1

    # ── Resumo ───────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  RESUMO DE EVALS")
    print(f"{'='*60}")

    for suite_id, data in results.items():
        icon = "✅" if data["passed"] else "❌"
        print(f"  {icon}  {data['label']}")

    print(f"\n  Status geral: {'✅ PASSOU' if overall_exit == 0 else '❌ FALHOU'}")
    print(f"  Timestamp: {datetime.now(timezone.utc).isoformat()}")

    # ── Relatório JSON ───────────────────────────────────────────────────
    if args.report:
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_passed": overall_exit == 0,
            "suites": results,
        }
        report_path = EVALS_DIR / "report.json"
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"\n  Relatório salvo em: {report_path}")

    return overall_exit


if __name__ == "__main__":
    sys.exit(main())
