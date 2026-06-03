"""
Correções finais do pipeline ADR-045:
  1. Aceita preços SICRO para os 6 SUSPENSOS (variação > 40%)
     — a maioria são erros de preço no catálogo, não no SICRO
  2. Injeta preços SICRO em regionalizacao.BR-CE para MAO_OBRA
     sem alterar preco_unitario (unidades incompatíveis: h vs mes)
"""
import io, json, sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "config/catalogos/mendeslobo/.catalog_bundle.json"
SICRO  = ROOT / "config/referencias/SICRO/BR-CE/insumos.json"

bundle     = json.loads(BUNDLE.read_text(encoding="utf-8"))
sicro_data = json.loads(SICRO.read_text(encoding="utf-8"))
ins_list   = bundle.get("insumos", [])
ins_idx    = {i["codigo"]: i for i in ins_list if i.get("codigo")}
sicro_ins  = sicro_data.get("insumos", [])
sicro_idx  = {s["codigo_referencia"]: s for s in sicro_ins if s.get("codigo_referencia")}

SICRO_DATA_VIG = sicro_data.get("data_vigencia", "2026-01-01")[:10]
NOW = datetime.now(timezone.utc).isoformat()

def _set_regz(ins, preco, sicro_cod):
    r = ins.get("regionalizacao") or {}
    if isinstance(r, list):
        r = {x.get("jurisdicao_id","?"): x for x in r}
    r["BR-CE"] = {
        "preco": round(preco, 4),
        "fonte_provedor": "SICRO",
        "fonte_codigo_externo": sicro_cod,
        "data_referencia": SICRO_DATA_VIG,
        "versao_tabela": "2026-01",
        "atualizado_em": NOW,
    }
    ins["regionalizacao"] = r

import re, unicodedata
_STOP = {"de","do","da","dos","das","e","a","o","em","com","para","por"}
def _norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return {w for w in t.split() if w not in _STOP and len(w) > 1}
def _jacc(a, b):
    ta, tb = _norm(a), _norm(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0

# ── 1. SUSPENSOS — aceita SICRO para erros claros de catálogo ─────────────────
# Análise manual:
#   EQ-BETONEIRA-600L : cat=R$3/h     SICRO=R$62.45/h  → ACEITA (R$3/h impossível)
#   EQ-CAM-BASC-14M3  : cat=R$110/h   SICRO=R$331.9/h  → REJEITA (match duvidoso, SICRO alto)
#   EQ-E0042 (Vibr.)  : cat=R$33/h    SICRO=R$430.4/h  → ACEITA (R$33 impossível para vibracab.)
#   EQ-E0045 (Roçad.) : cat=R$198/h   SICRO=R$8.8/h   → REJEITA (match provavelmente errado)
#   EQ-E0047 (Guind.) : cat=R$78.4/h  SICRO=R$505.5/h  → ACEITA (R$78 impossível p/ guindaste 40t)
#   MA-BRITA-1        : cat=R$78/m3   SICRO=R$156.1/m3 → ACEITA (inflação 2025-2026 plausível)

ACEITAR_SUSPENSOS = {
    "EQ-BETONEIRA-600L": ("E9033", "Betoneira"),    # R$3 impossível
    "EQ-E0042":          None,                       # busca por desc
    "EQ-E0047":          None,                       # busca por desc
    "MA-BRITA-1":        ("M0191", "Brita 1"),       # inflação
}

print("=" * 65)
print("SUSPENSOS — aplicando SICRO para erros de catálogo")
print("=" * 65)

for cat_cod, sicro_hint in ACEITAR_SUSPENSOS.items():
    ins = ins_idx.get(cat_cod)
    if ins is None:
        print(f"  [SKIP] {cat_cod} não encontrado no catálogo")
        continue
    # Resolve SICRO item
    sicro_item = None
    if sicro_hint:
        sicro_item = sicro_idx.get(sicro_hint[0])
    if sicro_item is None:
        # Busca por descrição
        best, best_s = None, 0.0
        tipo = ins.get("tipo", "")
        for s in sicro_ins:
            if s.get("tipo") != tipo:
                continue
            sc = _jacc(ins.get("descricao",""), s.get("descricao",""))
            if sc > best_s:
                best_s, best = sc, s
        if best and best_s >= 0.55:
            sicro_item = best
            print(f"  [AUTO] {cat_cod}: melhor match SICRO={best['codigo_referencia']} score={best_s:.2f}")

    if sicro_item is None:
        print(f"  [SKIP] {cat_cod}: SICRO item não encontrado")
        continue

    tipo = ins.get("tipo","")
    if tipo == "EQUIPAMENTO":
        novo = float(sicro_item.get("custo_produtivo") or 0)
    else:
        novo = float(sicro_item.get("preco_publicado") or 0)

    cat_preco = float(ins.get("preco_unitario") or 0)
    var = (novo - cat_preco) / cat_preco * 100 if cat_preco else 0

    # Atualiza preco_unitario e regionalizacao
    ins["preco_unitario"]        = round(novo, 4)
    ins["data_referencia_preco"] = SICRO_DATA_VIG
    ins["fonte_preco"]           = "tabela_referencia"
    _set_regz(ins, novo, sicro_item["codigo_referencia"])
    print(f"  {cat_cod:<30} R${cat_preco:.2f} → R${novo:.4f} ({var:+.1f}%)")

# ── 2. MAO_OBRA — injeta SICRO em regionalizacao sem mudar preco_unitario ──────
# Match por descrição SICRO MAO_OBRA → catálogo MAO_OBRA
# Não atualiza preco_unitario (unidades diferentes: SICRO=R$/h, catálogo=R$/mes)

print(f"\n{'='*65}")
print("MAO_OBRA — injetando SICRO em regionalizacao.BR-CE")
print("="*65)

sicro_mo = [s for s in sicro_ins if s.get("tipo") == "MAO_OBRA"]
cat_mo   = [i for i in ins_list  if i.get("tipo") == "MAO_OBRA"]

matched_mo, skipped_mo = 0, 0
for cat_ins in cat_mo:
    cat_cod  = cat_ins.get("codigo","")
    cat_desc = cat_ins.get("descricao","")
    best, best_s = None, 0.0
    for s in sicro_mo:
        sc = _jacc(cat_desc, s.get("descricao",""))
        if sc > best_s:
            best_s, best = sc, s
    if best is None or best_s < 0.65:
        skipped_mo += 1
        continue
    preco_sicro = float(best.get("preco_publicado") or 0)
    if preco_sicro <= 0:
        skipped_mo += 1
        continue
    _set_regz(cat_ins, preco_sicro, best["codigo_referencia"])
    matched_mo += 1

print(f"  MAO_OBRA matched: {matched_mo}  skipped: {skipped_mo}")
print(f"  (regionalizacao.BR-CE = custo horário SICRO totalmente carregado)")

# ── Salva bundle ────────────────────────────────────────────────────────────────
bundle["insumos"] = ins_list
BUNDLE.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\n  Bundle salvo. Insumos: {len(ins_list)}")

# ── Valida STALE residual ─────────────────────────────────────────────────────
stale = [i for i in ins_list if (i.get("data_referencia_preco") or "") <= "2025-12-31"]
por_tipo = {}
for i in stale:
    t = i.get("tipo","?")
    por_tipo[t] = por_tipo.get(t,0)+1
print(f"\n  STALE residual: {len(stale)}")
for t, n in sorted(por_tipo.items()):
    print(f"    {t}: {n}")

# Conta regionalizacao BR-CE populada
com_regz = sum(1 for i in ins_list
               if isinstance(i.get("regionalizacao"),dict)
               and "BR-CE" in i.get("regionalizacao",{}))
print(f"  Com regionalizacao.BR-CE: {com_regz} de {len(ins_list)}")
