#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Investigation using pandas directly (avoids openpyxl formatting issues)"""

from pathlib import Path
from openpyxl import load_workbook

SPREADSHEET = r"C:\Users\GustavoArruda\Mendes Lobo\TI - Documentos\IA\planilha_investimento\2026_03_30_PLANEJAMENTO_LOTE 09 e 10_(CE).xlsm"

output_file = Path(SPREADSHEET).parent / "INVESTIGATION_RESULTS.txt"

with open(output_file, "w", encoding="utf-8") as out:
    out.write("[+] Investigating mystery sheets using pandas...\n\n")
    
    mystery_sheets = ["CPU", "MATERIAIS", "ENCARGOS", "DD - C. EXAMES E EPI", "Transportes"]
    
    try:
        import pandas as pd
        
        for sheet_name in mystery_sheets:
            try:
                out.write(f"\n{'='*80}\n")
                out.write(f"{sheet_name}\n")
                out.write(f"{'='*80}\n\n")
                
                df = pd.read_excel(SPREADSHEET, sheet_name=sheet_name, nrows=8, header=None)
                
                # Write dataframe
                out.write(df.to_string())
                out.write("\n\n")
                out.write(f"Columns: {list(df.columns[:10])}\n")
                out.write(f"Shape: {df.shape}\n")
                
            except Exception as e:
                out.write(f"ERROR reading {sheet_name}: {type(e).__name__}: {str(e)[:100]}\n")
            
            out.flush()
        
        # Check PLANEJAMENTO line 52
        out.write(f"\n{'='*80}\n")
        out.write("PLANEJAMENTO - examining rows 50-55\n")
        out.write(f"{'='*80}\n\n")
        
        df_plan = pd.read_excel(SPREADSHEET, sheet_name="PLANEJAMENTO", nrows=60, header=None)
        out.write(df_plan.loc[49:54, :15].to_string())
        out.write("\n")
        
    except ImportError:
        out.write("pandas not available\n")
    except Exception as e:
        out.write(f"Error: {type(e).__name__}: {e}\n")
    
    out.write("\n[OK] Complete\n")

print(f"Results written to: {output_file}")
