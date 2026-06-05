# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, 'src')
import json
from pathlib import Path
from concilium.application.catalog.pu_calculator import derivar_precos_unitarios_sbdi, ParametrosCalculo

base = Path('config/catalogos/mendeslobo')
cpu_id = 'CPU-DREN-BOCA-BTCC-350X350'

with open(base / 'cpus' / f'{cpu_id}.json', encoding='utf-8') as f:
    cpu = json.load(f)
with open(base / 'produtividades' / f'{cpu_id}-PROD-001.json', encoding='utf-8') as f:
    prod = json.load(f)

insumos = {}
for cat in ['mao_obra', 'equipamento']:
    for ins_file in (base / 'insumos' / cat).glob('*.json'):
        with open(ins_file, encoding='utf-8') as f:
            ins = json.load(f)
            insumos[ins['codigo']] = ins

params = ParametrosCalculo(preco_diesel=6.20, alpha_clt=1.777, alpha_pj=1.060, horas_mes=193.6)

print(f'CPU: {cpu_id}')
print(f'Preco catalogado: R$ {cpu["precos_unitarios_sbdi"]["total"]:.2f}/m3')
print(f'Produtividade: {prod["valor_horario"]:.2f} m3/h')

sbdi = derivar_precos_unitarios_sbdi(prod, insumos, params)

print(f'\nCalculado:')
print(f'  Total: R$ {sbdi["total"]:.2f}')
print(f'  MO: R$ {sbdi.get("mao_obra", 0):.2f}')
print(f'  EQ: R$ {sbdi.get("equipamentos", 0):.2f}')
print(f'  Diesel: R$ {sbdi.get("diesel", 0):.2f}')

delta_pct = (sbdi['total'] - cpu['precos_unitarios_sbdi']['total']) / cpu['precos_unitarios_sbdi']['total'] * 100
print(f'\nDelta: {delta_pct:.1f}%')

print(f'\nANALISE:')
print(f'  O pu_calculator retorna custo POR HORA de producao')
print(f'  Para obter custo POR UNIDADE: custo_hora / producao_hora')
print(f'  Teste: {sbdi["total"]:.2f} / {prod["valor_horario"]:.2f} = {sbdi["total"]/prod["valor_horario"]:.2f}')
