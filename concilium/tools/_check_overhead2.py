"""Quick check: overhead_ocioso values in latest canonical.json — ADR-083 verification."""
import json
import glob

BASE = "/home/pingu/github/agente_engenheiro_senior/concilium/benchmarks/projetos"
canonicals = sorted(glob.glob(f"{BASE}/*/v1/canonical.json"))
if not canonicals:
    print("No canonical.json found.")
    raise SystemExit(1)

path = canonicals[-1]
print(f"Reading: {path}")
with open(path) as f:
    c = json.load(f)

contratos = c.get("contratos_recurso", [])
print(f"\n=== contratos_recurso: {len(contratos)} ===")
non_zero = []
for ct in contratos:
    for p in ct.get("particao_por_item", []):
        v = p.get("overhead_ocioso", 0)
        if v:
            non_zero.append((ct["tipo_id"], p["item_id"], v, p.get("custo_ocioso_imputado", 0)))

if non_zero:
    print(f"\n OK  {len(non_zero)} itens com overhead_ocioso > 0:")
    for tipo, item, oh, custo in non_zero:
        print(f"  {tipo}  item={item}  overhead_ocioso={oh}w  custo_imputado=R${custo:,.2f}")
else:
    print("\n WARN TODOS overhead_ocioso == 0")
    if contratos:
        ct = contratos[0]
        print(f"  (amostra: {ct['tipo_id']})")
        for p in ct.get("particao_por_item", [])[:3]:
            print(f"    item={p['item_id']}  overhead_ocioso={p.get('overhead_ocioso')}  custo={p.get('custo_ocioso_imputado')}")

# Check segmentos_atividade on instancias
instancias = c.get("instancias_recurso", [])
print(f"\n=== instancias_recurso: {len(instancias)} ===")
with_segs = [i for i in instancias if i.get("segmentos_atividade")]
print(f"  instancias com segmentos_atividade: {len(with_segs)}")
if with_segs:
    sample = with_segs[0]
    segs = sample["segmentos_atividade"]
    print(f"  amostra ({sample['tipo_id']}-{sample['instance_id']:02d}): {len(segs)} segmentos")
    for s in segs:
        print(f"    {s['activity_id']}  {s['semana_inicio']} -> {s['semana_fim']}  ({s['machine_weeks']}w)")
