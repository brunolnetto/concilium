"""Inspeciona dados reais dos erros e duplicatas para diagnóstico preciso."""
import io, json, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
bundle = json.loads((ROOT / "config/catalogos/mendeslobo/.catalog_bundle.json").read_text(encoding="utf-8"))
insumos = bundle.get("insumos", [])
ins_idx = {i["codigo"]: i for i in insumos if i.get("codigo")}
prods   = bundle.get("producoes", []) or bundle.get("produtividades", [])

ERROS = ["MO-ESTAGIARIO", "MO-P0001", "MO-P0070", "MO-OPERADOR-DE-MOTOSCRA"]
DUPL  = ["MO-P0007","MO-P0010","MO-P0013","MO-P0018","MO-P0020","MO-P0022","MO-P0023",
         "MO-P0024","MO-P0025","MO-P0026","MO-P0027","MO-P0030","MO-P0035","MO-P0036",
         "MO-P0037","MO-P0038","MO-P0039","MO-P0050","MO-P0052","MO-P0064","MO-P0065",
         "MO-P0066","MO-P0070","MO-P0072","MO-P0073","MO-P0074"]

print("=" * 70)
print("ERROS CRÍTICOS — dados completos")
print("=" * 70)
for cod in ERROS:
    ins = ins_idx.get(cod)
    if not ins:
        print(f"  {cod}: NÃO ENCONTRADO")
        continue
    attrs = ins.get("atributos_especificos") or {}
    print(f"\n  {cod}")
    print(f"    descricao          : {ins.get('descricao')}")
    print(f"    preco_unitario     : {ins.get('preco_unitario')} {ins.get('unidade')}")
    print(f"    tipo_contrato      : {attrs.get('tipo_contrato')}")
    print(f"    horas_mes          : {attrs.get('horas_mes')}")
    print(f"    percentual_enc_loc : {attrs.get('percentual_encargos_local')}")
    print(f"    salario_mensal     : {attrs.get('salario_mensal')}")
    if attrs.get("horas_mes") and ins.get("preco_unitario"):
        ph = float(ins["preco_unitario"]) / float(attrs["horas_mes"])
        print(f"    -> preco/hora      : R${ph:.4f}/h")

print("\n" + "=" * 70)
print("DUPLICATAS — mapa P#### → MO-NOME canônico")
print("=" * 70)
# Constrói mapa: (descricao_norm, preco) → primeiro código (canônico)
from collections import defaultdict
import unicodedata, re

def norm_desc(s):
    t = unicodedata.normalize("NFD", str(s).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()

grupos = defaultdict(list)
for ins in insumos:
    if ins.get("tipo") != "MAO_OBRA":
        continue
    key = (norm_desc(ins.get("descricao", "")), ins.get("preco_unitario"))
    grupos[key].append(ins["codigo"])

print(f"\n  Grupos com múltiplos códigos:")
dup_map = {}  # P#### → canonical MO-NOME
multi = {k: v for k, v in grupos.items() if len(v) > 1}
for key, codes in multi.items():
    canonical = next((c for c in codes if not c.startswith("P") and not c.startswith("MO-P")), codes[0])
    p_codes   = [c for c in codes if c != canonical]
    for pc in p_codes:
        dup_map[pc] = canonical
    desc = key[0][:40]
    print(f"  canônico={canonical:<30} duplicatas={p_codes}  desc={desc}")

# Onde os códigos P#### são referenciados em producoes
print(f"\n  Referências de P#### em producoes (funcao_id):")
refs_to_update = {}
for prod in prods:
    eq = prod.get("composicao_padrao_equipe") or prod.get("equipe") or {}
    for func in eq.get("funcoes", []) or []:
        fid = func.get("funcao_id", "")
        if fid in dup_map:
            refs_to_update.setdefault(fid, []).append(prod.get("id"))

for p_code, prod_ids in sorted(refs_to_update.items()):
    canon = dup_map[p_code]
    print(f"    {p_code} → {canon}  referenciado em: {prod_ids}")

print(f"\n  Total P#### a remover: {len(dup_map)}")
print(f"  Total referencias a atualizar: {sum(len(v) for v in refs_to_update.values())}")
