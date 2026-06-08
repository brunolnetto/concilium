#!/usr/bin/env python3
"""Fix MATEC_GUARULHOS and ODFJELL with proper referencia.json from planejamento.txt."""

import json
from pathlib import Path
from datetime import datetime, timedelta

def iso_weeks_between(start_date: str, end_date: str) -> list[str]:
    """Generate list of ISO week strings between start and end dates."""
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    weeks = []
    seen = set()

    current = start
    while current <= end:
        iso = current.isocalendar()
        week_key = f"{iso.year}-W{iso.week:02d}"
        if week_key not in seen:
            weeks.append(week_key)
            seen.add(week_key)
        current += timedelta(days=7)

    return weeks

def map_description_to_cpu(descricao: str, unit: str) -> str:
    """Map item description and unit to appropriate CPU."""
    d = descricao.lower()

    # Limpeza / Desmatamento
    if any(x in d for x in ['limpeza', 'desmatamento', 'destocamento']):
        return 'CPU-TERRA-ATI-003'  # Desmatamento

    # Carga e transporte
    if any(x in d for x in ['carga', 'transporte']):
        if '1' in descricao or 'primeira' in d:
            return 'CPU-TERRA-ESCO-CARGA-1CAT-DMT2000'
        elif '2' in descricao or 'segunda' in d:
            return 'CPU-TERRA-ESCO-CARGA-2CAT-DMT2000'
        else:
            return 'CPU-TERRA-ESCO-CARGA-3CAT-DMT2000'

    # Escavação
    if 'escav' in d:
        if '1' in descricao or 'primeira' in d:
            return 'CPU-TERRA-ESCO-CARGA-1CAT-DMT2000'
        else:
            return 'CPU-TERRA-ESCO-CARGA-2CAT-DMT2000'

    # Aterro / Compactação
    if any(x in d for x in ['aterro', 'compact']):
        return 'CPU-TERRA-COMPAC-PN'

    # Espalhamento
    if 'espalh' in d:
        return 'CPU-TERRA-ESCO-CARGA-3CAT-DMT2000'

    # Drenagem / Tubos
    if any(x in d for x in ['tubo', 'drenagem', 'canaleta', 'caixa']):
        return 'CPU-DREN-BOCA-BTCC-350X350'

    # Regularização / Subleito
    if any(x in d for x in ['regular', 'subleito']):
        return 'CPU-TERRA-ATI-002'

    # Geotêxtil / Brita / Areia
    if any(x in d for x in ['geotêxtil', 'brita', 'areia']):
        return 'CPU-TERRA-COMPAC-PN'

    # Default based on unit
    if unit.lower() in ['m2', 'm3']:
        return 'CPU-TERRA-ATI-003'
    elif unit.lower() in ['m', 'un', 'und']:
        return 'CPU-DREN-BOCA-BTCC-350X350'

    return 'CPU-TERRA-ATI-003'

def build_referencia(slug: str, planejamento_lines: list[str], project_root: Path):
    """Build referencia.json from planejamento lines."""
    # Extract items from planejamento (lines with item IDs like "1.1", "2.3", etc.)
    eap_items = []
    ordem = 0

    for line in planejamento_lines:
        parts = [p.strip() for p in line.split('\t')]
        if not parts or not parts[0]:
            continue

        item_id = parts[0].strip()

        # Skip header lines and section headers
        if not item_id or item_id in ['ITEM', 'BDI', 'INDML', 'INDML1', 'INDML2']:
            continue
        if item_id.startswith('DESPESAS') or item_id.startswith('DRENAGEM') or item_id.startswith('CAIXAS'):
            continue
        if not item_id[0].isdigit():
            continue
        if len(parts) < 4:
            continue

        # Skip if it's just a section header (no quantity)
        try:
            quantitativo = float(parts[3].replace(',', '.').replace('.', '', parts[3].count('.') - 1).replace(',', '.'))
        except:
            continue

        if quantitativo == 0:
            continue

        descricao = parts[1] if len(parts) > 1 else ''
        unidade = parts[2] if len(parts) > 2 else 'm'

        if not descricao.strip():
            continue

        ordem += 1
        cpu_id = map_description_to_cpu(descricao, unidade)

        eap_items.append({
            'item_id': item_id,
            'ordem': ordem,
            'cpu_id': cpu_id,
            'descricao': descricao,
            'unidade': unidade,
            'quantitativo': quantitativo,
            'predecessores': []
        })

    # Load existing referencia to get meta
    ref_path = project_root / 'benchmarks' / 'data' / slug / 'referencia.json'
    if ref_path.exists():
        existing_ref = json.loads(ref_path.read_text())
        meta = existing_ref.get('meta', {})
    else:
        meta = {
            'projeto': slug,
            'data_inicio': '2026-06-01',
            'data_termino': '2027-06-30',
            'localizacao': 'Brasil',
            'regime_trabalho': {
                'horas_dia': 8,
                'dias_semana': 6
            }
        }

    # Generate cronograma
    start_date = meta.get('data_inicio', '2026-06-01')
    end_date = meta.get('data_termino', '2027-06-30')
    weeks = iso_weeks_between(start_date, end_date)

    cronograma = []
    for item in eap_items:
        weeks_per_item = max(1, len(weeks) // max(len(eap_items), 1))
        quantitativo = item['quantitativo']
        producao_diaria = quantitativo / max(weeks_per_item * 5, 1)  # 5 working days per week

        item_cron = {
            'item_id': item['item_id'],
            'producao_diaria': round(producao_diaria, 2),
            'semanas': {}
        }

        start_week_idx = (eap_items.index(item) * weeks_per_item) % len(weeks)
        for week_offset in range(weeks_per_item):
            week_idx = (start_week_idx + week_offset) % len(weeks)
            if week_idx < len(weeks):
                week_key = weeks[week_idx]
                item_cron['semanas'][week_key] = {'num_equipes': 1}

        cronograma.append(item_cron)

    # Build referencia
    ref = {
        'meta': meta,
        'spec': {
            'eap': eap_items,
            'cronograma': cronograma,
            'bdi': {
                'mao_obra': {
                    'ac': 0.04,
                    'df': 0.08,
                    'r': 0.05,
                    'cr': 0.00,
                    'ir': 0.00
                },
                'material': {
                    'ac': 0.04,
                    'df': 0.08,
                    'r': 0.05,
                    'cr': 0.00,
                    'ir': 0.00
                },
                'servicos': {
                    'ac': 0.04,
                    'df': 0.08,
                    'r': 0.05,
                    'cr': 0.00,
                    'ir': 0.00
                },
                'diesel': {
                    'ac': 0.04,
                    'df': 0.08,
                    'r': 0.05,
                    'cr': 0.00,
                    'ir': 0.00
                },
                'indireto': {
                    'ac': 0.04,
                    'df': 0.08,
                    'r': 0.05,
                    'cr': 0.00,
                    'ir': 0.00
                }
            },
            'indiretos': []
        }
    }

    return ref, eap_items, len(weeks)

def main():
    project_root = Path(__file__).resolve().parent.parent

    # MATEC_GUARULHOS
    print("\n" + "="*80)
    print("FIXING MATEC_GUARULHOS")
    print("="*80)

    mg_path = project_root / 'benchmarks/data/MATEC_GUARULHOS/artifacts/raw/planejamento.txt'
    mg_lines = mg_path.read_text(encoding='utf-8').split('\n')
    mg_ref, mg_items, mg_weeks = build_referencia('MATEC_GUARULHOS', mg_lines, project_root)

    ref_path_mg = project_root / 'benchmarks/data/MATEC_GUARULHOS/referencia.json'
    ref_path_mg.write_text(json.dumps(mg_ref, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"✓ MATEC_GUARULHOS: {len(mg_items)} items, {mg_weeks} weeks")

    # ODFJELL
    print("\n" + "="*80)
    print("FIXING ODFJELL")
    print("="*80)

    od_path = project_root / 'benchmarks/data/ODFJELL/artifacts/raw/planejamento.txt'
    od_lines = od_path.read_text(encoding='utf-8').split('\n')
    od_ref, od_items, od_weeks = build_referencia('ODFJELL', od_lines, project_root)

    ref_path_od = project_root / 'benchmarks/data/ODFJELL/referencia.json'
    ref_path_od.write_text(json.dumps(od_ref, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"✓ ODFJELL: {len(od_items)} items, {od_weeks} weeks")

    print("\n" + "="*80)

if __name__ == "__main__":
    main()
