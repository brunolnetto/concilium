# -*- coding: utf-8 -*-
"""
NEP-029 F3.1: Validação de Convergência pu_calculator

Compara preços bottom-up (derivar_precos_unitarios_sbdi) vs catálogo AGIS.
Meta: delta ≤ 1% para CPUs com produtividade completa.
"""

import sys
sys.path.insert(0, 'src')

import json
from pathlib import Path
from concilium.application.catalog.pu_calculator import derivar_precos_unitarios_sbdi, ParametrosCalculo

def load_catalog(catalog_name='mendeslobo'):
    base = Path(f"config/catalogos/{catalog_name}")
    
    cpus = []
    for cpu_file in (base / "cpus").glob("*.json"):
        with open(cpu_file, encoding='utf-8') as f:
            cpus.append(json.load(f))
    
    insumos = {}
    for cat in ['mao_obra', 'equipamento', 'material']:
        cat_path = base / "insumos" / cat
        if cat_path.exists():
            for ins_file in cat_path.glob("*.json"):
                with open(ins_file, encoding='utf-8') as f:
                    ins = json.load(f)
                    insumos[ins['codigo']] = ins
    
    produtividades = {}
    for prod_file in (base / "produtividades").glob("*.json"):
        with open(prod_file, encoding='utf-8') as f:
            prod = json.load(f)
            produtividades[prod['codigo']] = prod
    
    return cpus, insumos, produtividades

def analyze_convergence():
    cpus, insumos, produtividades = load_catalog()
    print(f"Catalogo: {len(cpus)} CPUs, {len(insumos)} insumos, {len(produtividades)} produtividades\n")
    
    params = ParametrosCalculo(
        preco_diesel=6.20,
        alpha_clt=1.777,
        alpha_pj=1.060,
        horas_mes=193.6
    )
    
    results = []
    
    for cpu in cpus:
        cpu_id = cpu.get('codigo')
        prod = produtividades.get(cpu_id)
        
        if not prod:
            continue
        
        sbdi_catalog = cpu.get('precos_unitarios_sbdi', {})
        preco_catalog = float(sbdi_catalog.get('total', 0) or 0)
        
        if preco_catalog == 0:
            continue
        
        try:
            sbdi_calc = derivar_precos_unitarios_sbdi(prod, insumos, params)
            preco_calc = float(sbdi_calc.get('total', 0) or 0) if sbdi_calc else 0
        except Exception as e:
            continue
        
        if preco_calc == 0:
            continue
        
        delta = preco_calc - preco_catalog
        delta_pct = (delta / preco_catalog * 100) if preco_catalog > 0 else 0
        
        status = "OK" if abs(delta_pct) <= 1.0 else "DIVERGENTE"
        if abs(delta_pct) > 5.0:
            status = "CRITICO"
        
        results.append({
            'cpu_id': cpu_id,
            'catalog': preco_catalog,
            'calculated': preco_calc,
            'delta': delta,
            'delta_pct': delta_pct,
            'status': status
        })
    
    results.sort(key=lambda x: abs(x['delta_pct']), reverse=True)
    
    print("=" * 100)
    print("  CONVERGENCIA pu_calculator vs Catalogo")
    print("=" * 100)
    print(f"{'CPU':<40} {'Catalogo (R)':>15} {'Calculado (R)':>15} {'Delta':>10} {'Delta %':>10} {'Status'}")
    print("-" * 100)
    
    for r in results[:20]:
        print(f"{r['cpu_id']:<40} {r['catalog']:>15.2f} {r['calculated']:>15.2f} {r['delta']:>10.2f} {r['delta_pct']:>9.1f}% {r['status']}")
    
    print("-" * 100)
    
    total = len(results)
    ok = sum(1 for r in results if abs(r['delta_pct']) <= 1.0)
    divergent = sum(1 for r in results if 1.0 < abs(r['delta_pct']) <= 5.0)
    critical = sum(1 for r in results if abs(r['delta_pct']) > 5.0)
    
    avg_delta = sum(abs(r['delta_pct']) for r in results) / total if total > 0 else 0
    
    print(f"\nRESUMO:")
    print(f"  Total CPUs: {total}")
    print(f"  Convergentes (<=1%): {ok} ({ok/total*100:.1f}%)")
    print(f"  Divergentes (1-5%): {divergent} ({divergent/total*100:.1f}%)")
    print(f"  Criticos (>5%): {critical} ({critical/total*100:.1f}%)")
    print(f"  Delta medio: {avg_delta:.2f}%")
    
    if ok / total >= 0.95:
        print(f"\nMETA ATINGIDA: {ok/total*100:.1f}% dos CPUs convergentes!")
        return True
    else:
        print(f"\nMETA NAO ATINGIDA: {ok/total*100:.1f}% convergentes (meta: 95%)")
        return False

if __name__ == "__main__":
    success = analyze_convergence()
    exit(0 if success else 1)
