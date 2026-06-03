"""Inspeciona INNER_LOW em detalhe para diagnóstico de divergências."""
import io, json, sys, unicodedata, re
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
bundle = json.loads((ROOT / "config/catalogos/mendeslobo/.catalog_bundle.json").read_text(encoding="utf-8"))
rfi    = json.loads((ROOT / "tools/rfi_extracted.json").read_text(encoding="utf-8"))

cat_insumos   = {e["codigo"]: e for e in bundle.get("insumos", [])}
cat_producoes = {e["id"]: e     for e in (bundle.get("producoes") or bundle.get("produtividades", []))}
rfi_insumos   = {e["codigo"]: e for e in rfi["insumos"]}
rfi_producoes = {e["id"]: e     for e in rfi["producoes"]}

_STOP = {"de", "do", "da", "dos", "das", "e", "a", "o", "em", "com", "para", "por"}
def _norm(text):
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return {w for w in t.split() if w not in _STOP and len(w) > 1}

def jaccard(a, b):
    ta, tb = _norm(a), _norm(b)
    if not ta or not tb: return 0.0
    return round(len(ta & tb) / len(ta | tb), 3)

# ── Equipment INNER_LOW (code match, low desc_sim) ──────────────────────────
EQ_PAIRS = [
    ("EQ-E0030","EQ-E0030"), ("EQ-E0031","EQ-E0031"), ("EQ-E0032","EQ-E0032"),
    ("EQ-E0033","EQ-E0034"), ("EQ-E0034","EQ-E0035"),  # note: códigos RFI podem ser diferentes
    ("EQ-E0037","EQ-E0037"), ("EQ-E0038","EQ-E0038"), ("EQ-E0039","EQ-E0039"),
    ("EQ-E0040","EQ-E0040"), ("EQ-E0041","EQ-E0041"), ("EQ-E0042","EQ-E0042"),
    ("EQ-E0043","EQ-E0043"), ("EQ-E0044","EQ-E0044"), ("EQ-E0045","EQ-E0045"),
]

print("=" * 75)
print("EQUIPAMENTOS — INNER_LOW (descrição completa + Jaccard)")
print("=" * 75)

# Varre TODOS os rfi_insumos do tipo EQUIPAMENTO com código EQ-E####
rfi_eq = {c: e for c, e in rfi_insumos.items() if e.get("tipo") == "EQUIPAMENTO"}
cat_eq = {c: e for c, e in cat_insumos.items() if e.get("tipo") == "EQUIPAMENTO"}

for rfi_cod, rfi_e in sorted(rfi_eq.items()):
    cat_e = cat_eq.get(rfi_cod)
    if not cat_e:
        continue
    d_cat = cat_e.get("descricao", "")
    d_rfi = rfi_e.get("descricao", "")
    j = jaccard(d_cat, d_rfi)
    if j >= 0.35:
        continue  # verdadeiro match, já vai como INNER_HIGH
    print(f"\n  código : {rfi_cod}")
    print(f"  CATALOG: {d_cat}")
    print(f"  RFI    : {d_rfi}")
    print(f"  Jaccard: {j:.3f}  preco_cat={cat_e.get('preco_unitario')} preco_rfi={rfi_e.get('preco_unitario')}")

# Casos borderline (Jaccard entre 0.20 e 0.35)
print("\n\n  === Borderline (0.20 ≤ Jaccard < 0.35) ===")
for rfi_cod, rfi_e in sorted(rfi_eq.items()):
    cat_e = cat_eq.get(rfi_cod)
    if not cat_e:
        continue
    j = jaccard(cat_e.get("descricao",""), rfi_e.get("descricao",""))
    if 0.20 <= j < 0.35:
        print(f"  {rfi_cod}: j={j:.3f}  CAT={cat_e.get('descricao','')[:50]}  RFI={rfi_e.get('descricao','')[:50]}")

# ── Production INNER_LOW ─────────────────────────────────────────────────────
ATI_LOW = ["ATI-012","ATI-021","ATI-022","ATI-023","ATI-024",
           "ATI-025","ATI-027","ATI-028","ATI-052","ATI-055","ATI-058","ATI-063","ATI-070"]

print("\n" + "=" * 75)
print("PRODUCOES — INNER_LOW (código, descrição completa, unidade, Jaccard)")
print("=" * 75)
for pid in ATI_LOW:
    cat_p = cat_producoes.get(pid)
    rfi_p = rfi_producoes.get(pid)
    if not cat_p or not rfi_p:
        print(f"\n  {pid}: não encontrado em um dos lados")
        continue
    d_cat = cat_p.get("descricao", "")
    d_rfi = rfi_p.get("descricao", "")
    u_cat = cat_p.get("unidade","?")
    u_rfi = rfi_p.get("unidade","?")
    j = jaccard(d_cat, d_rfi)
    print(f"\n  {pid}  Jaccard={j:.3f}  unidade: {u_cat} / {u_rfi}")
    print(f"    CATALOG: {d_cat}")
    print(f"    RFI    : {d_rfi}")
