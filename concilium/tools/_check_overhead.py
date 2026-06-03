"""Quick check: overhead_ocioso values in latest canonical.json — ADR-083 verification."""
import json
import glob
import os

BASE = "/home/pingu/github/agente_engenheiro_senior/concilium/benchmarks/projetos"
canonicals = sorted(glob.glob(f"{BASE}/*/v1/canonical.json"))
if not canonicals:
    print("No canonical.json found.")
    raise SystemExit(1)

path = canonicals[-1]
print(f"Reading: {path}")
with open(path) as f:
    c = json.load(f)

skills = c.get("skills", [])
sk05 = next((s for s in skills if s.get("skill_id") == "05-equipes-e-alocacao"), None)
if sk05 is None:
    print("Skill-05 not found in canonical.")
    raise SystemExit(1)

out = sk05["output"]
contratos = out.get("contratos_recurso", [])
print(f"\n=== contratos_recurso: {len(contratos)} ===")
non_zero = []
for ct in contratos:
    for p in ct.get("particao_por_item", []):
        v = p.get("overhead_ocioso", 0)
        if v:
            non_zero.append((ct["tipo_id"], p["item_id"], v, p.get("custo_ocioso_imputado", 0)))

if non_zero:
    print(f"\n✅ {len(non_zero)} itens com overhead_ocioso > 0:")
    for tipo, item, oh, custo in non_zero:
        print(f"  {tipo}  item={item}  overhead_ocioso={oh}w  custo_imputado=R${custo:,.2f}")
else:
    print("\n⚠ TODOS overhead_ocioso == 0")
    # Show sample
    if contratos:
        ct = contratos[0]
        print(f"  (amostra: {ct['tipo_id']})")
        for p in ct.get("particao_por_item", [])[:3]:
            print(f"    item={p['item_id']}  overhead_ocioso={p.get('overhead_ocioso')}  custo={p.get('custo_ocioso_imputado')}")

# Also check segmentos_atividade on instancias
instancias = out.get("instancias_recurso", [])
print(f"\n=== instancias_recurso: {len(instancias)} ===")
with_segs = [i for i in instancias if i.get("segmentos_atividade")]
print(f"  instâncias com segmentos_atividade: {len(with_segs)}")
if with_segs:
    sample = with_segs[0]
    segs = sample["segmentos_atividade"]
    print(f"  amostra ({sample['tipo_id']}-{sample['instance_id']:02d}): {len(segs)} segmentos")
    for s in segs:
        print(f"    {s['activity_id']}  {s['semana_inicio']} → {s['semana_fim']}  ({s['machine_weeks']}w)")
