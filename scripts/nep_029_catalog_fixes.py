"""
NEP-029 F2.2: Correções de Catálogo

Aplica 3 correções identificadas na análise NEP-029:
1. MA-AGIS-CPU-TERRA-COMPAC-FINAL-ROCHA: R$ 17,26 → R$ 14,44
2. EQ-E0016: Adicionar consumo_litros_hora faltante  
3. CPU-TERRA-ESCO-CARGA-1CAT-DMT2000: Completar composicao_itens (adicionar MO e equipamento)
"""

import json
from pathlib import Path
from datetime import datetime

def apply_catalog_fixes():
    """Aplica as 3 correções de catálogo da NEP-029 F2.2."""
    
    fixes_applied = []
    base_path = Path("config/catalogos/mendeslobo")
    
    # FIX 1: MA-AGIS-CPU-TERRA-COMPAC-FINAL-ROCHA
    fix1_files = list(base_path.glob("insumos/material/*COMPAC*ROCHA*.json"))
    
    if fix1_files:
        fix1_path = fix1_files[0]
        with open(fix1_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        old_price = float(data.get("preco_unitario", 0.0))
        new_price = 14.44
        
        if abs(old_price - 17.26) < 1.0:  
            data["preco_unitario"] = new_price
            
            with open(fix1_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            fixes_applied.append({
                "fix": "F2.2a - MA-AGIS-COMPAC-ROCHA",
                "file": str(fix1_path),
                "old_value": old_price,
                "new_value": new_price,
                "status": "✅ Aplicado"
            })
        else:
            fixes_applied.append({
                "fix": "F2.2a",
                "status": f"ℹ️  Valor atual {old_price}"
            })
    
    # FIX 2: EQ-E0016
    eq_files = list(base_path.glob("insumos/equipamento/*E0016*.json"))
    
    for eq_path in eq_files:
        with open(eq_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if "consumo_litros_hora" not in data or not data.get("consumo_litros_hora"):
            data["consumo_litros_hora"] = 7.0
            
            with open(eq_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            fixes_applied.append({
                "fix": "F2.2b - EQ-E0016",
                "file": str(eq_path),
                "new_value": 7.0,
                "status": "✅ Aplicado"
            })
    
    # FIX 3: CPU-TERRA-ESCO
    cpu_files = list(base_path.glob("cpus/CPU-TERRA-ESCO-CARGA-1CAT*.json"))
    
    if cpu_files:
        cpu_path = cpu_files[0]
        with open(cpu_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        comp_itens = data.get("composicao_itens", [])
        has_only_diesel = len(comp_itens) == 1 and comp_itens[0].get("categoria_custo", "").upper() == "DIESEL"
        
        if has_only_diesel:
            comp_itens_new = [
                comp_itens[0],
                {
                    "insumo_id": "AGIS-FN-OPERADOR-ESCAVADEIRA-1CAT",
                    "coeficiente": 0.0050,
                    "categoria_custo": "MAO_OBRA",
                    "unidade": "h"
                },
                {
                    "insumo_id": "EQ-ESCAVADEIRA-HIDRAULICA-1CAT-PNEU",
                    "coeficiente": 0.0050,
                    "categoria_custo": "EQUIPAMENTO",
                    "unidade": "h"
                }
            ]
            
            data["composicao_itens"] = comp_itens_new
            
            with open(cpu_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            fixes_applied.append({
                "fix": "F2.2c - CPU-TERRA-ESCO",
                "file": str(cpu_path),
                "status": "✅ Aplicado"
            })
    
    return fixes_applied

if __name__ == "__main__":
    print("NEP-029 F2.2: Aplicando correções...")
    fixes = apply_catalog_fixes()
    
    for fix in fixes:
        print(f"{fix['fix']}: {fix['status']}")
    
    applied = sum(1 for f in fixes if '✅' in f['status'])
    print(f"\n✅ {applied} correções aplicadas")
