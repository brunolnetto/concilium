import io, json, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
bundle = json.loads(Path("config/catalogos/mendeslobo/.catalog_bundle.json").read_text(encoding="utf-8"))
insumos = bundle.get("insumos", [])
stale = [i for i in insumos if (i.get("data_referencia_preco") or "") <= "2025-12-31"]
print(f"Stale antes : 156")
print(f"Stale depois: {len(stale)}")
print(f"Reduzidos   : {156 - len(stale)}")
by_tipo = {}
for i in stale:
    t = i.get("tipo","?")
    by_tipo[t] = by_tipo.get(t,0)+1
print("Restantes:")
for t, n in sorted(by_tipo.items()): print(f"  {t}: {n}")
# Atualizados via SICRO
atualiz = [i for i in insumos if i.get("data_referencia_preco","") >= "2026-01-01"
           and not i.get("_rfi_updated_at") and not i.get("_rfi_imported_at")]
print(f"Com data >= 2026-01-01 (SICRO/ANP): {len(atualiz)}")
for i in atualiz[:8]:
    r = i.get("regionalizacao") or {}
    if isinstance(r, list): r = {x.get("jurisdicao_id","?"): x for x in r}
    rce = r.get("BR-CE") or {}
    print(f"  {i['codigo']:30} R${i['preco_unitario']:>10.4f}  SICRO_CE={rce.get('preco','—')}")
# Suspensos
cov = json.loads(next(iter(sorted(
    Path("config/referencias/pesquisas/logs").glob("cobertura_CE_*.json"), reverse=True
))).read_text(encoding="utf-8"))
print(f"\nSuspensos (var>40%): {len(cov.get('suspensos',[]))}")
for s in cov.get("suspensos",[]):
    print(f"  {s['concilium_id']:30} cat={s['preco_atual']} SICRO={s['preco_sicro']} ({s['variacao_pct']:+.1f}%)")
print(f"Sem match: {len(cov.get('sem_match',[]))}")
