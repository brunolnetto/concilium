"""Relatório de plausibilidade completo do catálogo."""
import io, json, sys
from pathlib import Path
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from concilium.application.catalog.plausibility_checker import verificar_plausibilidade

bundle  = json.loads((ROOT / "config/catalogos/mendeslobo/.catalog_bundle.json").read_text(encoding="utf-8"))
insumos  = bundle.get("insumos", [])
producoes = bundle.get("producoes", []) or bundle.get("produtividades", [])
cpus     = bundle.get("cpus", [])

resultado = verificar_plausibilidade(insumos, producoes, cpus)
r = resultado["resumo"]

print(f"{'='*70}")
print(f"RELATÓRIO DE PLAUSIBILIDADE — catálogo mendeslobo")
print(f"{'='*70}")
print(f"  Insumos:    {r['total_insumos']}")
print(f"  Producoes:  {r['total_producoes']}")
print(f"  Status:     {'OK' if resultado['ok'] else 'PROBLEMAS ENCONTRADOS'}")
print(f"  Erros:      {r['erros']}")
print(f"  Avisos:     {r['avisos']}")
print(f"  Infos:      {r['infos']}")

tipo_counts = Counter(a["tipo"] for a in resultado["anomalias"])
print(f"\n  Por tipo:")
for tipo, cnt in sorted(tipo_counts.items(), key=lambda x: -x[1]):
    print(f"    {tipo:<15}: {cnt}")

for sev in ("ERRO", "AVISO", "INFO"):
    items = [a for a in resultado["anomalias"] if a["severidade"] == sev]
    if not items:
        continue
    print(f"\n{'─'*70}")
    print(f"  {sev} ({len(items)}):")
    for a in items[:30]:
        print(f"  [{a['tipo']:<13}] {a['codigo']:<35} {a['mensagem'][:60]}")
    if len(items) > 30:
        print(f"  ... e mais {len(items)-30}")
