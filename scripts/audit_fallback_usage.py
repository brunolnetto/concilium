#!/usr/bin/env python3
"""
AUDITORIA PHASE 2: Fallback Usage Report

Objetivo: Quantificar uso real de fallback composição (Fonte 2)
para planejar deprecação segura.

Saída: Relatório de:
1. CPUs com producao_id_ref válido
2. CPUs com producao_id_ref vazio/inválido
3. Producoes com producao_horaria = 0 (fallback trigger)
4. Risk assessment por categoria
"""

import json
from pathlib import Path
from collections import defaultdict

# Paths
CPUS_DIR = Path("config/catalogos/mendeslobo/cpus")
PRODS_DIR = Path("config/catalogos/mendeslobo/produtividades")

# ============================================================================
# STEP 1: Load all Producao files into lookup
# ============================================================================

producoes = {}
for prod_file in PRODS_DIR.glob("*.json"):
    try:
        with open(prod_file) as f:
            prod = json.load(f)
        prod_id = prod.get("id") or prod_file.stem
        producoes[prod_id] = {
            "file": prod_file.name,
            "producao_horaria": float(prod.get("producao_horaria") or 0.0),
            "valid": float(prod.get("producao_horaria") or 0.0) > 0,
        }
    except Exception as e:
        print(f"⚠️  Error loading {prod_file.name}: {e}")

print(f"📊 Loaded {len(producoes)} Producao files")
print(f"   - Valid (producao_horaria > 0): {sum(1 for p in producoes.values() if p['valid'])}")
print(f"   - Invalid (producao_horaria = 0): {sum(1 for p in producoes.values() if not p['valid'])}\n")

# ============================================================================
# STEP 2: Analyze CPUs and categorize by fallback risk
# ============================================================================

cpu_files = list(CPUS_DIR.glob("*.json"))
print(f"📊 Analyzing {len(cpu_files)} CPU files...\n")

fallback_analysis = {
    "source_1_valid": [],      # producao_id_ref exists + producao_horaria > 0
    "source_1_incomplete": [],  # producao_id_ref exists + producao_horaria = 0
    "source_2_risk": [],        # producao_id_ref missing/empty
    "unknown": [],              # error loading
}

categoria_stats = defaultdict(lambda: {"total": 0, "source_1": 0, "source_2_risk": 0})

for cpu_file in sorted(cpu_files):
    try:
        with open(cpu_file) as f:
            cpu = json.load(f)
        
        cpu_id = cpu.get("codigo", cpu_file.stem)
        categoria = cpu.get("categoria", "UNKNOWN")
        categoria_stats[categoria]["total"] += 1
        
        prod_id_ref = cpu.get("producao_id_ref")
        
        if not prod_id_ref:
            # Source 2 risk: no producao reference
            fallback_analysis["source_2_risk"].append({
                "cpu_id": cpu_id,
                "categoria": categoria,
                "reason": "no producao_id_ref",
                "file": cpu_file.name,
            })
            categoria_stats[categoria]["source_2_risk"] += 1
        elif prod_id_ref not in producoes:
            # Source 2 risk: producao file not found
            fallback_analysis["source_2_risk"].append({
                "cpu_id": cpu_id,
                "categoria": categoria,
                "reason": f"producao {prod_id_ref} NOT FOUND",
                "file": cpu_file.name,
            })
            categoria_stats[categoria]["source_2_risk"] += 1
        elif not producoes[prod_id_ref]["valid"]:
            # Source 1 incomplete: producao exists but producao_horaria = 0
            fallback_analysis["source_1_incomplete"].append({
                "cpu_id": cpu_id,
                "categoria": categoria,
                "producao_id": prod_id_ref,
                "producao_horaria": producoes[prod_id_ref]["producao_horaria"],
                "file": cpu_file.name,
            })
            categoria_stats[categoria]["source_2_risk"] += 1  # Will use fallback
        else:
            # Source 1 valid: everything OK
            fallback_analysis["source_1_valid"].append({
                "cpu_id": cpu_id,
                "categoria": categoria,
                "producao_id": prod_id_ref,
                "producao_horaria": producoes[prod_id_ref]["producao_horaria"],
            })
            categoria_stats[categoria]["source_1"] += 1
    
    except Exception as e:
        fallback_analysis["unknown"].append({
            "file": cpu_file.name,
            "error": str(e),
        })

# ============================================================================
# STEP 3: Risk Classification
# ============================================================================

risk_high = fallback_analysis["source_2_risk"]
risk_medium = fallback_analysis["source_1_incomplete"]
risk_low = fallback_analysis["source_1_valid"]

print("=" * 80)
print("FALLBACK USAGE AUDIT — PHASE 2")
print("=" * 80)
print()

print("📈 SUMMARY BY RISK LEVEL")
print("-" * 80)
print(f"✅ GREEN  (Source 1 Valid)        : {len(risk_low):3d} CPUs ({len(risk_low)*100//len(cpu_files):2d}%)")
print(f"🟡 YELLOW (Source 1 Incomplete)   : {len(risk_medium):3d} CPUs ({len(risk_medium)*100//len(cpu_files):2d}%)")
print(f"🔴 RED    (Source 2 Fallback Risk): {len(risk_high):3d} CPUs ({len(risk_high)*100//len(cpu_files):2d}%)")
print(f"❓ UNKNOWN                        : {len(fallback_analysis['unknown']):3d} CPUs")
print(f"{'':40} ─────")
print(f"{'TOTAL':40} {len(cpu_files):3d} CPUs")
print()

print("=" * 80)
print("📊 BREAKDOWN BY CATEGORIA")
print("=" * 80)
for cat in sorted(categoria_stats.keys()):
    stats = categoria_stats[cat]
    total = stats["total"]
    src1 = stats["source_1"]
    src2 = stats["source_2_risk"]
    pct_safe = (src1 * 100 // total) if total > 0 else 0
    pct_risk = (src2 * 100 // total) if total > 0 else 0
    
    status = "✅" if pct_risk == 0 else "🔴" if pct_risk > 50 else "🟡"
    print(f"{status} {cat:30s} {total:3d} CPUs: {src1:3d} Safe, {src2:3d} Risk ({pct_risk:2d}%)")

# ============================================================================
# STEP 4: Detailed Risk Report
# ============================================================================

if risk_high:
    print()
    print("=" * 80)
    print("🔴 HIGH RISK — Source 2 Fallback (No Producao Reference)")
    print("=" * 80)
    print()
    
    by_reason = defaultdict(list)
    for item in risk_high:
        reason = item["reason"]
        by_reason[reason].append(item)
    
    for reason in sorted(by_reason.keys()):
        items = by_reason[reason]
        print(f"Reason: {reason} ({len(items)} CPUs)")
        for item in items[:5]:  # Show first 5
            print(f"  • {item['cpu_id']:30s} [{item['categoria']}]")
        if len(items) > 5:
            print(f"  ... and {len(items) - 5} more")
        print()

if risk_medium:
    print()
    print("=" * 80)
    print("🟡 MEDIUM RISK — Source 1 Incomplete (Producao exists but producao_horaria=0)")
    print("=" * 80)
    print()
    
    for item in risk_medium[:10]:  # Show first 10
        print(f"  • {item['cpu_id']:30s} → {item['producao_id']} (ρ={item['producao_horaria']})")
    if len(risk_medium) > 10:
        print(f"  ... and {len(risk_medium) - 10} more")
    print()

# ============================================================================
# STEP 5: Deprecation Readiness
# ============================================================================

print()
print("=" * 80)
print("🎯 DEPRECATION READINESS ASSESSMENT")
print("=" * 80)
print()

safe_pct = (len(risk_low) * 100) // len(cpu_files) if cpu_files else 0
risk_pct = (len(risk_high) * 100) // len(cpu_files) if cpu_files else 0

if safe_pct >= 95:
    readiness = "🟢 SAFE FOR REMOVAL"
    action = "Can proceed with deprecation phase"
elif safe_pct >= 90:
    readiness = "🟡 MOSTLY SAFE"
    action = "Fix medium-risk CPUs first (< 10% at risk)"
else:
    readiness = "🔴 NOT READY"
    action = "Need to fix all incomplete Producoes"

print(f"Status: {readiness}")
print(f"Action: {action}")
print()
print(f"Criteria for v2.1 removal:")
print(f"  ✓ 100% of CPUs have valid Producao with producao_horaria > 0")
print(f"  ✓ Currently at: {safe_pct}% (need to fix {len(risk_high) + len(risk_medium)} CPUs)")
print()

# ============================================================================
# STEP 6: Export data for further analysis
# ============================================================================

export_data = {
    "timestamp": "2026-08-14",
    "audit_type": "fallback_usage_phase_2",
    "summary": {
        "total_cpus": len(cpu_files),
        "source_1_valid": len(risk_low),
        "source_1_incomplete": len(risk_medium),
        "source_2_risk": len(risk_high),
        "safe_percentage": safe_pct,
        "risk_percentage": risk_pct,
    },
    "by_categoria": dict(categoria_stats),
    "high_risk_cpus": [
        {"cpu_id": r["cpu_id"], "categoria": r["categoria"], "reason": r["reason"]}
        for r in risk_high[:20]
    ],
}

export_file = Path("results/audit_fallback_usage_phase2.json")
export_file.parent.mkdir(parents=True, exist_ok=True)

with open(export_file, "w") as f:
    json.dump(export_data, f, indent=2)

print(f"📁 Detailed report saved to: {export_file}")
print()
