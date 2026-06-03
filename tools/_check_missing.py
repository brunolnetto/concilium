"""Diagnóstico de produções sem composição + análise de plausibilidade inicial."""
import io, json, sys, statistics
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

bundle = json.loads((ROOT / "config/catalogos/mendeslobo/.catalog_bundle.json").read_text(encoding="utf-8"))
prods   = bundle.get("producoes", []) or bundle.get("produtividades", [])
insumos = bundle.get("insumos", [])
ins_idx = {i["codigo"]: i for i in insumos if i.get("codigo")}

# ── 1. Produções sem composição ───────────────────────────────────────────────
sem_comp = []
for p in prods:
    eq = p.get("composicao_padrao_equipe") or p.get("equipe") or {}
    if not (eq.get("funcoes") or eq.get("equipamentos")):
        sem_comp.append(p)

print(f"{'='*70}")
print(f"PRODUÇÕES SEM COMPOSIÇÃO DE EQUIPE: {len(sem_comp)}")
print(f"{'='*70}")
for p in sem_comp:
    vh   = p.get("valor_horario")
    orig = p.get("origem") or "?"
    orig_str = orig if isinstance(orig, str) else orig.get("tipo", "?")
    eq   = p.get("composicao_padrao_equipe") or p.get("equipe") or {}
    mats = eq.get("materiais", []) or []
    pid  = p.get("id", "?")
    print(f"  {pid:<45} vh={str(vh):<8} origem={orig_str[:20]}")
    if mats:
        for m in mats:
            print(f"      material: {m.get('insumo_id')} consumo={m.get('consumo_por_hora')}")
    else:
        print(f"      (sem MO, sem EQ, sem material)")

# ── 2. Plausibilidade MAO_OBRA ────────────────────────────────────────────────
mo_insumos = [i for i in insumos if i.get("tipo") == "MAO_OBRA" and i.get("preco_unitario", 0) > 0]
mo_prices  = [i["preco_unitario"] for i in mo_insumos]

print(f"\n{'='*70}")
print(f"ANÁLISE DE PLAUSIBILIDADE — MAO_OBRA ({len(mo_insumos)} itens)")
print(f"{'='*70}")
if len(mo_prices) >= 2:
    mu   = statistics.mean(mo_prices)
    sd   = statistics.stdev(mo_prices)
    med  = statistics.median(mo_prices)
    p10  = sorted(mo_prices)[int(len(mo_prices)*0.10)]
    p90  = sorted(mo_prices)[int(len(mo_prices)*0.90)]
    print(f"  Salário mensal: μ={mu:.2f}  σ={sd:.2f}  mediana={med:.2f}  P10={p10:.2f}  P90={p90:.2f}")
    # Z-score outliers
    outliers = [(i["codigo"], i["preco_unitario"], (i["preco_unitario"]-mu)/sd)
                for i in mo_insumos if abs((i["preco_unitario"]-mu)/sd) > 2.5]
    if outliers:
        print(f"  Outliers (|z|>2.5):")
        for cod, preco, z in sorted(outliers, key=lambda x: abs(x[2]), reverse=True):
            ins  = ins_idx.get(cod, {})
            desc = ins.get("descricao", "")[:40]
            print(f"    z={z:+.2f}  {cod:<25} R${preco:<10.2f} {desc}")

# ── 3. Plausibilidade EQUIPAMENTO ─────────────────────────────────────────────
eq_insumos = [i for i in insumos if i.get("tipo") == "EQUIPAMENTO" and i.get("preco_unitario", 0) > 0]
print(f"\n{'='*70}")
print(f"ANÁLISE DE PLAUSIBILIDADE — EQUIPAMENTO ({len(eq_insumos)} itens)")
print(f"{'='*70}")

# Valida consumo de diesel via regressão consumo ~ potência
diesel_checks = []
for ins in eq_insumos:
    attrs = ins.get("atributos_especificos") or {}
    consumo = attrs.get("consumo_litros_hora")
    pot_cv  = attrs.get("potencia_cv") or attrs.get("potencia_hp", 0)
    if consumo and pot_cv and float(pot_cv) > 0:
        # Regra técnica: ~0.20–0.27 L/h por CV a 70-80% carga
        esperado_min = float(pot_cv) * 0.20
        esperado_max = float(pot_cv) * 0.27
        c = float(consumo)
        if c < esperado_min * 0.6 or c > esperado_max * 1.6:
            diesel_checks.append({
                "codigo": ins["codigo"],
                "descricao": ins.get("descricao", "")[:35],
                "consumo_real": c,
                "potencia_cv": float(pot_cv),
                "esperado": f"{esperado_min:.1f}–{esperado_max:.1f}",
            })

if diesel_checks:
    print(f"  Consumo diesel improvável (fora de ±60% do esperado por CV):")
    for d in diesel_checks:
        print(f"    {d['codigo']:<25} consumo={d['consumo_real']}L/h  pot={d['potencia_cv']}CV  esperado={d['esperado']}")
else:
    print(f"  Consumo diesel: todos plausíveis (regra 0.20-0.27 L/h/CV)")

# Z-score preço
eq_prices = [i["preco_unitario"] for i in eq_insumos]
if len(eq_prices) >= 2:
    mu = statistics.mean(eq_prices)
    sd = statistics.stdev(eq_prices)
    print(f"  Preço R$/h: μ={mu:.2f}  σ={sd:.2f}  mediana={statistics.median(eq_prices):.2f}")
    outliers_eq = [(i["codigo"], i["preco_unitario"], (i["preco_unitario"]-mu)/sd)
                   for i in eq_insumos if abs((i["preco_unitario"]-mu)/sd) > 2.5]
    if outliers_eq:
        print(f"  Outliers preço (|z|>2.5):")
        for cod, preco, z in sorted(outliers_eq, key=lambda x: abs(x[2]), reverse=True)[:10]:
            desc = ins_idx.get(cod, {}).get("descricao", "")[:35]
            print(f"    z={z:+.2f}  {cod:<25} R${preco}/h  {desc}")

# ── 4. Plausibilidade Produtividade ───────────────────────────────────────────
print(f"\n{'='*70}")
print(f"ANÁLISE DE PLAUSIBILIDADE — PRODUTIVIDADES ({len(prods)} itens)")
print(f"{'='*70}")

from concilium.application.catalog.pu_calculator import calcular_catalogo, ParametrosCalculo
result = calcular_catalogo(prods, insumos, ParametrosCalculo())

pus = [(bd["producao_id"], bd["pu_calculado"], bd["valor_horario"], bd["breakdown"]["total_h"])
       for bd in result["breakdown_por_producao"]
       if bd["pu_calculado"] and bd["pu_calculado"] > 0]

if len(pus) >= 2:
    pu_vals = [p[1] for p in pus]
    mu  = statistics.mean(pu_vals)
    sd  = statistics.stdev(pu_vals)
    med = statistics.median(pu_vals)
    p10 = sorted(pu_vals)[int(len(pu_vals)*0.10)]
    p90 = sorted(pu_vals)[int(len(pu_vals)*0.90)]
    print(f"  PU calculado: μ={mu:.2f}  σ={sd:.2f}  mediana={med:.2f}  P10={p10:.4f}  P90={p90:.2f}")
    pu_outliers = [(pid, pu, (pu-mu)/sd) for pid, pu, _, _ in pus if abs((pu-mu)/sd) > 3.0]
    if pu_outliers:
        print(f"  PU outliers extremos (|z|>3.0):")
        for pid, pu, z in sorted(pu_outliers, key=lambda x: abs(x[2]), reverse=True)[:10]:
            prod = next((p for p in prods if p.get("id") == pid), {})
            print(f"    z={z:+.2f}  {pid:<40} PU={pu:.4f}  VH={prod.get('valor_horario')}")

print(f"\n  Verificação referencial: {len(result['referencias_faltantes'])} faltantes")
print(f"  Status global: {'OK' if result['ok'] else 'ERRO'}")
