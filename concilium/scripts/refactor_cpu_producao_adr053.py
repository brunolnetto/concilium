#!/usr/bin/env python3
import json
from pathlib import Path

base = Path(r'c:\Users\bruno\Documents\Agente Engenheiro Sênior\concilium\config\catalogos')

def process_catalog(catalog_name):
    cat_path = base / catalog_name
    print(f'\n📦 Processando {catalog_name}...')
    
    # 1. Atualizar CPUs com producao_id_ref
    cpu_file = cat_path / 'cpus.json'
    cpu_dir = cat_path / 'cpus'
    
    all_cpus = []
    
    # Caso 1: Arquivo centralizado (test/)
    if cpu_file.exists():
        with open(cpu_file, encoding='utf-8-sig') as f:
            data = json.load(f)
        added = 0
        for cpu in data.get('cpus', []):
            if 'producao_id_ref' not in cpu:
                cpu['producao_id_ref'] = cpu['codigo'] + '-PROD-001'
                added += 1
            all_cpus.append(cpu)
        with open(cpu_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f'  ✓ Arquivo centralizado: {added} CPUs')
    
    # Caso 2: Diretório com arquivos individuais (mendeslobo/, mendeslobo_backup_ids/)
    elif cpu_dir.exists():
        cpu_files = list(cpu_dir.glob('*.json'))
        added = 0
        for cf in cpu_files:
            with open(cf, encoding='utf-8-sig') as f:
                cpu = json.load(f)
            if 'producao_id_ref' not in cpu:
                cpu['producao_id_ref'] = cpu['codigo'] + '-PROD-001'
                added += 1
            all_cpus.append(cpu)
            with open(cf, 'w', encoding='utf-8') as f:
                json.dump(cpu, f, ensure_ascii=False, indent=2)
        print(f'  ✓ Diretório individual: {added} de {len(cpu_files)} CPUs')
    
    return all_cpus

# Processar catálogos
all_catalogos_cpus = {}
for cat in ['test', 'mendeslobo', 'mendeslobo_backup_ids', 'samples']:
    cpus = process_catalog(cat)
    if cpus:
        all_catalogos_cpus[cat] = cpus

# 2. Atualizar Produtividades com cpu_ids (referência reversa)
print(f'\n🔗 Atualizando Produtividades com referências reversas...')
for cat_name, cpus in all_catalogos_cpus.items():
    prod_base = base / cat_name / 'produtividades'
    if prod_base.exists():
        prod_files = list(prod_base.glob('*-PROD-*.json'))
        for pf in prod_files:
            try:
                with open(pf, encoding='utf-8-sig') as f:
                    prod_data = json.load(f)
                
                prod_id = prod_data.get('id')
                if prod_id and 'cpu_ids' not in prod_data:
                    matching_cpus = [c['codigo'] for c in cpus 
                                   if c.get('producao_id_ref') == prod_id]
                    if matching_cpus:
                        prod_data['cpu_ids'] = matching_cpus
                        with open(pf, 'w', encoding='utf-8') as f:
                            json.dump(prod_data, f, ensure_ascii=False, indent=2)
                        print(f'  ✓ {cat_name}/{prod_id}: {len(matching_cpus)} cpu_ids')
            except Exception as e:
                print(f'  ⚠ Erro processando {pf.name}: {e}')

print('\n✅ Refatoração ADR-053 completa (Fase 1: retrocompatibilidade)')
