"""Verify ADR-083 deliverables in AGIS benchmark artifacts — reads from canonical.json."""
import sys
import json
from pathlib import Path

sys.path.insert(0, "src")

root = Path(".")

# Find the AGIS project canonical — newest project in benchmarks/projetos
bench_projetos = root / "benchmarks" / "projetos"
proj_dirs = sorted(bench_projetos.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
if not proj_dirs:
    print("ERROR: no projects in benchmarks/projetos")
    sys.exit(1)

proj_dir = proj_dirs[0]
canon_path = proj_dir / "v1" / "canonical.json"
print("=== Reading canonical.json ===")
print("  project:", proj_dir.name)
if not canon_path.exists():
    print("ERROR: canonical.json not found at", canon_path)
    sys.exit(1)

canon = json.loads(canon_path.read_text())

# Also read benchmark_report for status
audit_dir = root / "benchmarks" / "data" / "AGIS" / "audit"
report = json.loads((audit_dir / "benchmark_report.json").read_text())
print()
print("=== BENCHMARK STATUS ===")
print("  status_final:", report.get("status_final"))
qg = report.get("quality_gates") or {}
print("  quality_gates:", qg.get("decision"))

# D1: contratos_recurso with particao_por_item
contratos = canon.get("contratos_recurso", [])
print()
print("=== ADR-083 D1: contratos_recurso com particao_por_item ===")
print("  total contratos:", len(contratos))

any_populated = False
for c in contratos[:8]:
    particao = c.get("particao_por_item", [])
    tipo = c.get("tipo_id", "?")
    custo = c.get("custo_total", 0)
    print(f"  contrato tipo={tipo} custo_total={custo:,.0f} particao_por_item={len(particao)} itens")
    if particao:
        any_populated = True
        for p in particao[:3]:
            item = p.get("item_id", "?")
            produtivo = p.get("custo_produtivo", 0)
            mob_imp = p.get("custo_mob_imputado", 0)
            ocioso_imp = p.get("custo_ocioso_imputado", 0)
            eco = p.get("economia_mob", 0)
            overhead = p.get("overhead_ocioso", 0)
            total_part = p.get("custo_total_particionado", 0)
            print(f"    item={item} produtivo={produtivo:,.0f} mob_imp={mob_imp:,.0f} ocioso_imp={ocioso_imp:,.0f}")
            print(f"      overhead_ocioso={overhead:,.0f} economia_mob={eco:,.0f} total_particionado={total_part:,.0f}")

if not any_populated:
    print("  NOTE: All particao_por_item are empty lists.")
    print("  AGIS uses RCPSP pool contracts — checking if field key exists in JSON...")
    found_key = any("particao_por_item" in str(c) for c in contratos)
    print("  'particao_por_item' key present in any contrato:", found_key)

# Conservation invariant
print()
print("=== Conservation invariant: sum(custo_total_particionado) ~= custo_total ===")
checked = 0
for c in contratos:
    particao = c.get("particao_por_item", [])
    if not particao:
        continue
    custo_contrato = c.get("custo_total", 0)
    soma = sum(p.get("custo_total_particionado", 0) for p in particao)
    delta = abs(soma - custo_contrato)
    ok = "OK" if delta < 1.0 else "FAIL"
    tipo = c.get("tipo_id", "?")
    print(f"  tipo={tipo}: soma_particao={soma:,.2f} custo_total={custo_contrato:,.2f} delta={delta:.2f} [{ok}]")
    checked += 1

if checked == 0:
    print("  No contracts with non-empty particao_por_item — invariant vacuously satisfied")

# D3: PontoEquilibrio lever fechar_gap_pool
print()
print("=== ADR-083 D3: lever fechar_gap_pool com restricoes ===")
equipes = canon.get("equipes_diretas", [])
print("  total equipes:", len(equipes))
levers_found = 0
items_with_pool = []
for eq in equipes:
    pe = eq.get("ponto_equilibrio") or {}
    gp = pe.get("gap_pool_abs")
    if gp is not None and gp != 0:
        items_with_pool.append((eq.get("item_id", "?"), gp))
    levers = pe.get("levers_equilibrio", [])
    for lv in levers:
        if lv.get("id") == "fechar_gap_pool":
            levers_found += 1
            restricoes = lv.get("restricoes", [])
            item = eq.get("item_id", "?")
            print(f"  [{levers_found}] equipe={item} gap_pool_abs={gp:,.0f}")
            for r in restricoes:
                print(f"       restricao: {r}")
            break

if levers_found == 0:
    print(f"  Nenhum lever 'fechar_gap_pool' encontrado")
    print(f"  Equipes com gap_pool_abs != 0: {len(items_with_pool)}")
    for item, gp in items_with_pool[:5]:
        sign = "overhead (lever esperado)" if gp > 0 else "economia (lever omitido, D3 correto)"
        print(f"    item={item} gap_pool_abs={gp:,.0f} -> {sign}")

print()
print("=== DONE ===")
