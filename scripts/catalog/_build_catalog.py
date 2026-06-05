import sys, pathlib, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOT = pathlib.Path(r'C:\Users\bruno\OneDrive - Mendes Lobo\MendesLobo Construtora\Agente Engenheiro Sênior\concilium')
EXTRACTED = ROOT / 'benchmarks' / 'data' / 'AGIS' / 'extracted_catalog.json'
REFERENCIA = ROOT / 'benchmarks' / 'data' / 'AGIS' / 'referencia.json'
CATALOG = ROOT / 'config' / 'catalogos' / 'mendeslobo'

data = json.loads(EXTRACTED.read_text(encoding='utf-8'))
ref = json.loads(REFERENCIA.read_text(encoding='utf-8'))

cpus_blk = data['cpus']
mo_insums = data['mao_obra']
eq_insums = data['equipamentos']
eap_items = ref['cpus']['itens_eap']

blk_to_cpu_id = {}
terra_items = sorted(
    [it for it in eap_items if it.get('item_planilha', '').startswith('1.')],
    key=lambda x: int(x['item_planilha'].split('.')[1])
)
for i, it in enumerate(terra_items):
    if i < 12:
        blk_to_cpu_id[i] = it['cpu_id']

dren_map = {
    12: 'CPU-DREN-ESCAV-VALA-1CAT',
    13: 'CPU-DREN-CORPO-BSTC-100-PA1',
    14: 'CPU-DREN-CORPO-BSTC-100-PA2',
    15: 'CPU-DREN-CORPO-BSTC-120-PA2',
    16: 'CPU-DREN-CORPO-BSTC-120-PA3',
    17: 'CPU-DREN-BOCA-BSTC-100',
    18: 'CPU-DREN-BOCA-BSTC-120',
    19: 'CPU-DREN-CORPO-BDTC-100-PA1',
    20: 'CPU-DREN-CORPO-BDTC-100-PA2',
    21: 'CPU-DREN-CORPO-BDTC-120-PA2',
    22: 'CPU-DREN-BOCA-BDTC-100',
    23: 'CPU-DREN-BOCA-BDTC-120',
    24: 'CPU-DREN-CORPO-BTTC-120-PA2',
    25: 'CPU-DREN-BOCA-BTTC-120',
    26: 'CPU-DREN-CORPO-BSCC-150X200',
    27: 'CPU-DREN-CORPO-BSCC-100-200X150',
    28: 'CPU-DREN-CORPO-BSCC-200X200',
    29: 'CPU-DREN-CORPO-BSCC-100-200X200',
    30: 'CPU-DREN-CORPO-BSCC-250X250',
    31: 'CPU-DREN-CORPO-BSCC-100-300X200',
    32: 'CPU-DREN-CORPO-BSCC-300X250',
    33: 'CPU-DREN-BOCA-BSCC-200X150',
    34: 'CPU-DREN-BOCA-BSCC-200X200',
    35: 'CPU-DREN-BOCA-BSCC-250X250',
    36: 'CPU-DREN-BOCA-BSCC-300X200',
    37: 'CPU-DREN-CORPO-BDCC',
    38: 'CPU-DREN-CORPO-BDCC-100',
    39: 'CPU-DREN-CORPO-BDCC-100',
    40: 'CPU-DREN-BOCA-BDCC',
    41: 'CPU-DREN-CORPO-BTCC',
    42: 'CPU-DREN-CORPO-BTCC-100',
    43: 'CPU-DREN-BOCA-BTCC-300X300',
    44: 'CPU-DREN-BOCA-BTCC-350X350',
    45: 'CPU-DREN-REATERRO-COMPAC',
    46: 'CPU-TERRA-COMPAC-FINAL-ROCHA',
}
blk_to_cpu_id.update(dren_map)

mo_dir = CATALOG / 'insumos' / 'mao_obra'
mo_dir.mkdir(parents=True, exist_ok=True)
created_mo = 0
for cod, mo in mo_insums.items():
    fpath = mo_dir / f'{cod}.json'
    if fpath.exists():
        continue
    obj = {
        'codigo': cod, 'tipo': 'MAO_OBRA', 'descricao': mo['descricao'],
        'unidade': mo.get('unidade', 'mes'),
        'preco_unitario': round(mo.get('custo_com_encargos', mo.get('salario', 0)), 4),
        'fonte_preco': 'PLANILHA_AGIS_2026_05', 'data_referencia_preco': '2026-05-01',
        'atributos_especificos': {
            'salario_base': round(mo.get('salario', 0), 4),
            'custo_com_encargos': round(mo.get('custo_com_encargos', 0), 4),
        }
    }
    fpath.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    created_mo += 1
print(f'MO insumos criados: {created_mo}')

eq_dir = CATALOG / 'insumos' / 'equipamento'
eq_dir.mkdir(parents=True, exist_ok=True)
created_eq = 0
for cod, eq in eq_insums.items():
    fpath = eq_dir / f'{cod}.json'
    if fpath.exists():
        continue
    obj = {
        'codigo': cod, 'tipo': 'EQUIPAMENTO', 'descricao': eq['descricao'],
        'unidade': 'h',
        'preco_unitario': round(eq.get('custo_hora', 0), 4),
        'fonte_preco': 'PLANILHA_AGIS_2026_05', 'data_referencia_preco': '2026-05-01',
        'atributos_especificos': {'horas_mes': eq.get('horas_mes', 200)}
    }
    fpath.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    created_eq += 1
print(f'EQ insumos criados: {created_eq}')

cpu_dir = CATALOG / 'cpus'
existing_cpus = {}
for f in cpu_dir.glob('*.json'):
    try:
        obj = json.loads(f.read_text(encoding='utf-8'))
        existing_cpus[obj['codigo']] = (f, obj)
    except Exception:
        pass
print(f'Existing CPU files: {len(existing_cpus)}')

mo_by_desc = {v['descricao'].lower().strip(): k for k, v in mo_insums.items()}
updated_cpus = 0
skipped = 0

for blk_idx, cpu_id in blk_to_cpu_id.items():
    if blk_idx >= len(cpus_blk):
        continue
    blk = cpus_blk[blk_idx]
    if cpu_id not in existing_cpus:
        print(f'  WARN: {cpu_id} not in catalog (blk {blk_idx+1})')
        skipped += 1
        continue
    fpath, existing = existing_cpus[cpu_id]
    equip_list = blk.get('equipamentos', [])
    mo_list = blk.get('mao_obra', [])
    prod_h = blk.get('producao_horaria')
    custo_dir = blk.get('custo_direto_unitario')
    equipamentos = []
    for eq in equip_list:
        ecod = eq.get('codigo', '')
        if not ecod or not ecod.startswith('E'):
            continue
        equipamentos.append({'equipamento_id': ecod, 'quantidade': eq.get('quant', 1), 'utilizacao_produtiva': 1.0})
    funcoes = []
    for mo in mo_list:
        desc_lower = mo['descricao'].lower().strip()
        p_code = mo_by_desc.get(desc_lower)
        if not p_code:
            for k, v in mo_by_desc.items():
                if desc_lower[:20] in k or k[:20] in desc_lower:
                    p_code = v
                    break
        if p_code:
            funcoes.append({'funcao_id': p_code, 'quantidade': mo.get('quant', 1)})
        else:
            print(f'    WARN: MO not found: "{mo["descricao"]}" blk {blk_idx+1}')
    equipe = {}
    if funcoes:
        equipe['funcoes'] = funcoes
    if equipamentos:
        equipe['equipamentos'] = equipamentos
    updated = dict(existing)
    updated['equipe'] = equipe
    if prod_h and isinstance(prod_h, float) and prod_h > 0:
        updated['producao_horaria'] = round(prod_h, 6)
    if custo_dir and isinstance(custo_dir, float) and custo_dir > 0:
        updated['custo_direto_unitario_planilha'] = round(custo_dir, 6)
    comp_itens = [c for c in updated.get('composicao_itens', []) if not c.get('insumo_id', '').startswith('MA-AGIS-CPU')]
    updated['composicao_itens'] = comp_itens
    fpath.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding='utf-8')
    updated_cpus += 1
    print(f'  UPDATED Blk{blk_idx+1:02}: {cpu_id} | equip={len(equipamentos)} mo={len(funcoes)}')

print(f'Total CPUs atualizados: {updated_cpus}')
print(f'Pulados: {skipped}')