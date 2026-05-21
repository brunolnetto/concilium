"""Usa codebase_stats para analisar cobertura e métricas do projeto."""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import codebase_stats as cs

# Carrega cobertura
cov = cs.load_coverage("coverage.json")
print(f"Coverage carregada: {len(cov)} arquivos")

# Arquivos com cobertura abaixo de 50%
print("\n=== ARQUIVOS COM COBERTURA < 50% ===")
low = []
for path, data in cov.items():
    if "concilium" not in path:
        continue
    total = data.get("summary", {}).get("num_statements", 0)
    covered = data.get("summary", {}).get("covered_lines", 0)
    pct = data.get("summary", {}).get("percent_covered", 0)
    if pct < 50 and total > 10:
        low.append((pct, path, covered, total))

low.sort()
for pct, path, covered, total in low[:25]:
    short = path.replace("\\", "/").split("concilium/")[-1]
    print(f"  {pct:5.1f}%  {short}  ({covered}/{total} linhas)")

# Resumo geral
print("\n=== RESUMO GERAL ===")
totals = {"statements": 0, "covered": 0, "missing": 0}
for path, data in cov.items():
    if "concilium" not in path:
        continue
    s = data.get("summary", {})
    totals["statements"] += s.get("num_statements", 0)
    totals["covered"]    += s.get("covered_lines", 0)
    totals["missing"]    += s.get("missing_lines", 0)

if totals["statements"]:
    pct = 100 * totals["covered"] / totals["statements"]
    print(f"  Total: {pct:.1f}% ({totals['covered']}/{totals['statements']} statements)")
    print(f"  Faltando: {totals['missing']} statements sem cobertura")
