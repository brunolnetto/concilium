#!/usr/bin/env python3
"""Analyze indirect costs composition across all 12 benchmarks."""

import json
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple


def parse_planejamento_indiretos(content: str) -> List[Dict]:
    """Extract indirect cost items from planejamento.txt TSV."""
    indiretos = []
    lines = content.split('\n')

    for line in lines:
        if not line.strip():
            continue

        parts = [p.strip() for p in line.split('\t')]
        if not parts or not parts[0]:
            continue

        item_id = parts[0]

        # Match indirect cost items: INDML*, DESP*, or items starting with numbers but in indirect section
        # Indicators: INDML prefix, or descriptions with "indir", "mob", "canteiro", "despesa", etc.
        is_indirect = (
            item_id.startswith('INDML') or
            item_id.startswith('DESP') or
            (len(parts) > 1 and any(word in parts[1].lower() for word in [
                'indir', 'mobiliz', 'canteiro', 'despesa', 'administr',
                'engenharia', 'topografia', 'laborat', 'segur', 'ambiental'
            ]))
        )

        if not is_indirect:
            continue

        # Try to extract cost values (usually column indices vary by file)
        # Look for values with , or . as decimal separator
        description = parts[1] if len(parts) > 1 else ''

        # Find cost values (columns with currency-like numbers)
        custo_sbdi = None
        for i in range(2, min(len(parts), 15)):
            try:
                val = float(parts[i].replace(',', '.').replace('.', '', parts[i].count('.') - 1).replace(',', '.'))
                if val > 0 and custo_sbdi is None:
                    custo_sbdi = val
                    break
            except:
                pass

        if custo_sbdi and custo_sbdi > 0:
            indiretos.append({
                'item_id': item_id,
                'descricao': description,
                'custo': custo_sbdi,
                'raw_line': line
            })

    return indiretos


def categorize_indirect(descricao: str) -> str:
    """Categorize indirect cost by description."""
    d = descricao.lower()

    if any(x in d for x in ['mobiliz', 'desmobil']):
        return 'MOB'
    elif any(x in d for x in ['administr', 'gerenc']):
        return 'ADM'
    elif any(x in d for x in ['topogra', 'levant']):
        return 'TOP'
    elif any(x in d for x in ['laborat', 'ensaio']):
        return 'LAB'
    elif any(x in d for x in ['segur', 'qsms', 'saude', 'ambient']):
        return 'QSMS'
    elif any(x in d for x in ['canteiro', 'aluguel', 'agua', 'luz', 'energia']):
        return 'CANTEIRO'
    elif any(x in d for x in ['equipamento', 'aluguel', 'uso geral']):
        return 'EQUIP'
    elif any(x in d for x in ['engenharia', 'projeto', 'design']):
        return 'ENG'
    elif any(x in d for x in ['despesa', 'geral']):
        return 'DESPESA'
    else:
        return 'OUTRO'


def main():
    project_root = Path(__file__).resolve().parent.parent
    benchmarks_root = project_root / 'benchmarks' / 'data'

    benchmarks = [
        'AGIS', 'CTC', 'LUNDIN', 'MARA_ROSA', 'MATEC_GUARULHOS', 'MATEC_HINES',
        'MATEC_UBERLANDIA', 'ODFJELL', 'PRIVATE_LOG', 'ROSH', 'RUMO', 'VALE'
    ]

    print("\n" + "="*100)
    print("ANÁLISE DE COMPOSIÇÃO DE INDIRETOS — 12 BENCHMARKS")
    print("="*100)

    all_data = {}

    for slug in benchmarks:
        planejamento_path = benchmarks_root / slug / 'artifacts' / 'raw' / 'planejamento.txt'

        if not planejamento_path.exists():
            print(f"\n✗ {slug:20} planejamento.txt não encontrado")
            continue

        content = planejamento_path.read_text(encoding='utf-8')
        indiretos = parse_planejamento_indiretos(content)

        if not indiretos:
            print(f"\n? {slug:20} nenhum indireto encontrado")
            continue

        # Categorize and sum
        por_categoria = defaultdict(float)
        for item in indiretos:
            cat = categorize_indirect(item['descricao'])
            por_categoria[cat] += item['custo']

        total_indireto = sum(por_categoria.values())

        # Load referencia to get direct costs for percentage
        ref_path = benchmarks_root / slug / 'referencia.json'
        custo_direto = None
        if ref_path.exists():
            try:
                ref = json.load(open(ref_path))
                # Try to find custo_direto in resultado or from artifact reports
                if 'resultado' in ref and 'benchmark_confronto_referencia' in ref['resultado']:
                    custo_direto = ref['resultado']['benchmark_confronto_referencia'].get('custo_direto')
            except:
                pass

        # Try to get from benchmark report
        report_path = benchmarks_root / slug / 'artifacts' / 'audit' / 'benchmark_report.json'
        if not custo_direto and report_path.exists():
            try:
                report = json.load(open(report_path))
                if 'confronto' in report and 'ferramenta' in report['confronto']:
                    custo_direto = report['confronto']['ferramenta'].get('custo_direto_pu_q')
            except:
                pass

        pct_indireto = (total_indireto / (custo_direto + total_indireto) * 100) if custo_direto else None

        all_data[slug] = {
            'indiretos': indiretos,
            'por_categoria': dict(por_categoria),
            'total': total_indireto,
            'custo_direto': custo_direto,
            'percentual': pct_indireto
        }

        print(f"\n✓ {slug:20} Total indireto: R$ {total_indireto:>12,.0f}", end="")
        if pct_indireto:
            print(f"  ({pct_indireto:>5.1f}% do total)")
        else:
            print()

        for cat in sorted(por_categoria.keys()):
            valor = por_categoria[cat]
            pct = valor / total_indireto * 100
            print(f"    {cat:15} R$ {valor:>12,.0f}  ({pct:>5.1f}%)")

    # Summary statistics
    print("\n" + "="*100)
    print("RESUMO COMPARATIVO")
    print("="*100)

    print(f"\n{'Projeto':<20} {'Total Indireto':>15} {'% do Total':>12} {'Principais Categorias':>50}")
    print("-" * 100)

    for slug in benchmarks:
        if slug not in all_data:
            continue

        data = all_data[slug]
        total = data['total']
        pct = data['percentual']

        # Top 3 categories
        top_cats = sorted(data['por_categoria'].items(), key=lambda x: -x[1])[:3]
        cat_str = ', '.join([f"{cat} ({pct:.0f}%)" for cat, pct in [(c, v/total*100) for c, v in top_cats]])

        pct_str = f"{pct:.1f}%" if pct else "N/A"
        print(f"{slug:<20} R$ {total:>13,.0f}  {pct_str:>12} {cat_str:>50}")

    # Aggregate by category
    print("\n" + "="*100)
    print("CATEGORIAS DE INDIRETOS — FREQUÊNCIA E VALORES MÉDIOS")
    print("="*100)

    todas_categorias = defaultdict(list)
    for data in all_data.values():
        for cat, valor in data['por_categoria'].items():
            todas_categorias[cat].append(valor)

    print(f"\n{'Categoria':<15} {'Frequência':>12} {'Valor Médio':>15} {'Min':>15} {'Max':>15}")
    print("-" * 75)

    for cat in sorted(todas_categorias.keys()):
        valores = todas_categorias[cat]
        freq = len(valores)
        media = sum(valores) / len(valores)
        minval = min(valores)
        maxval = max(valores)

        print(f"{cat:<15} {freq:>12} R$ {media:>13,.0f} R$ {minval:>13,.0f} R$ {maxval:>13,.0f}")

    # Pattern analysis
    print("\n" + "="*100)
    print("PADRÕES OBSERVADOS")
    print("="*100)

    # Count which categories appear in how many projects
    cat_frequency = defaultdict(int)
    for data in all_data.values():
        for cat in data['por_categoria'].keys():
            cat_frequency[cat] += 1

    universal = [c for c, f in cat_frequency.items() if f == len(all_data)]
    common = [c for c, f in cat_frequency.items() if f >= len(all_data) * 0.5]
    rare = [c for c, f in cat_frequency.items() if f < len(all_data) * 0.25]

    print(f"\nUniversais (em todos os projetos): {universal}")
    print(f"Comuns (em ≥50% dos projetos): {common}")
    print(f"Raros (em <25% dos projetos): {rare}")

    # Cost ratios
    print(f"\nRazão Indireto/Total:")
    ratios = [d['percentual'] for d in all_data.values() if d['percentual']]
    if ratios:
        print(f"  Média: {sum(ratios)/len(ratios):.1f}%")
        print(f"  Min: {min(ratios):.1f}%")
        print(f"  Max: {max(ratios):.1f}%")

    print("\n" + "="*100 + "\n")


if __name__ == "__main__":
    main()
