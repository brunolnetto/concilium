import pandas as pd
import json
from pathlib import Path

excel_path = Path("benchmarks/data/AGIS/artifacts/outputs/resultado_planejamento.xlsx")

if not excel_path.exists():
    print(f"❌ Arquivo não encontrado: {excel_path}")
    exit(1)

# Read all sheets
xl = pd.ExcelFile(excel_path)
print(f"✅ Excel carregado: {len(xl.sheet_names)} abas")
print(f"Abas: {', '.join(xl.sheet_names)}\n")

# Read planejamento sheet (has CPU pricing per item)
if 'planejamento' in xl.sheet_names:
    df_plan = pd.read_excel(excel_path, sheet_name='planejamento')
    print("=== PLANEJAMENTO (primeiras 10 linhas) ===")
    print(df_plan.head(10).to_string())
    print(f"\nColunas: {list(df_plan.columns)}")

# Read equipes sheet if exists
if 'equipes' in xl.sheet_names:
    df_eq = pd.read_excel(excel_path, sheet_name='equipes')
    print(f"\n=== EQUIPES ===")
    print(f"Total equipes: {len(df_eq)}")
    if 'custo_material_mensal' in df_eq.columns:
        material_sum = df_eq['custo_material_mensal'].sum()
        print(f"Custo material total: R$ {material_sum:,.2f}")
        print(f"Equipes com material >0: {(df_eq['custo_material_mensal'] > 0).sum()}")
