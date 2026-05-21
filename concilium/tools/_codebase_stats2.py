"""Analisa cobertura e falhas de teste do projeto usando codebase_stats e pytest-json-report."""
import io, json, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 1. Cobertura via coverage.json ─────────────────────────────────────────────
cov_file = Path("coverage.json")
if cov_file.exists():
    cov = json.loads(cov_file.read_text(encoding="utf-8"))
    files = cov.get("files", {})
    totals = cov.get("totals", {})

    print("=" * 70)
    print("COBERTURA DO PROJETO")
    print("=" * 70)
    print(f"  Total: {totals.get('percent_covered', 0):.1f}% "
          f"({totals.get('covered_lines', 0)}/{totals.get('num_statements', 0)} statements)")
    print(f"  Arquivos analisados: {len(files)}")

    # Arquivos com cobertura < 60%
    low = []
    for path, data in files.items():
        summ = data.get("summary", {})
        pct  = summ.get("percent_covered", 100)
        stmts = summ.get("num_statements", 0)
        if stmts >= 10 and pct < 60:
            short = path.replace("\\", "/").split("concilium/")[-1] if "concilium" in path else path
            low.append((pct, short, summ.get("covered_lines",0), stmts))

    if low:
        low.sort()
        print(f"\n  Arquivos com cobertura < 60% ({len(low)}):")
        for pct, path, covered, total in low[:20]:
            print(f"    {pct:5.1f}%  {path}  ({covered}/{total})")

# ── 2. Análise com codebase_stats ────────────────────────────────────────────────
try:
    import codebase_stats as cs
    print("\n" + "=" * 70)
    print("MÉTRICAS DE COMPLEXIDADE (radon CC)")
    print("=" * 70)
    # Roda análise de complexidade nos arquivos de skills (os mais problemáticos)
    import subprocess, os
    result = subprocess.run(
        [sys.executable, "-m", "radon", "cc", "src/concilium/application/skills/manifests",
         "-s", "-a", "--total-average"],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.stdout:
        lines = [l for l in result.stdout.splitlines() if "Average" in l or "F " in l or "C " in l]
        for l in lines[:15]:
            print(f"  {l}")
except Exception as e:
    print(f"  radon não disponível: {e}")

# ── 3. Top funções com maior complexidade ciclomática ────────────────────────────
try:
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "radon", "cc", "src/concilium",
         "-s", "-n", "C", "--total-average"],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.stdout:
        print("\n" + "=" * 70)
        print("FUNÇÕES COM COMPLEXIDADE ALTA (CC >= C)")
        print("=" * 70)
        lines = result.stdout.splitlines()
        for l in lines[:30]:
            if l.strip() and ("F " in l or "M " in l or "C " in l or "Average" in l):
                print(f"  {l}")
except Exception as e:
    print(f"  {e}")

# ── 4. Mantainability Index ──────────────────────────────────────────────────────
try:
    result = subprocess.run(
        [sys.executable, "-m", "radon", "mi", "src/concilium", "-s", "-n", "B"],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.stdout:
        print("\n" + "=" * 70)
        print("ARQUIVOS COM MAINTAINABILITY INDEX BAIXO (MI < B)")
        print("=" * 70)
        for l in result.stdout.splitlines()[:20]:
            if l.strip():
                print(f"  {l}")
except Exception as e:
    print(f"  {e}")
