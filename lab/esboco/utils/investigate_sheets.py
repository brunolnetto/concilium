#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deep Investigation Script: Understand the mystery sheets (CPU, MATERIAIS, ENCARGOS, DD)
"""

from pathlib import Path
import tempfile
import shutil
from openpyxl import load_workbook
import pandas as pd

# Spreadsheet path
SPREADSHEET = r"C:\Users\GustavoArruda\Mendes Lobo\TI - Documentos\IA\planilha_investimento\2026_03_30_PLANEJAMENTO_LOTE 09 e 10_(CE).xlsm"

def copy_and_load_workbook():
    """Create temp copy and load workbook"""
    src = Path(SPREADSHEET)
    dst = Path(tempfile.gettempdir()) / "agis_skills" / "investigate.xlsm"
    dst.parent.mkdir(exist_ok=True)
    
    if not src.exists():
        print(f"ERROR: File not found: {SPREADSHEET}")
        return None
    
    shutil.copy2(src, dst)
    return load_workbook(dst, data_only=True)

def investigate_sheet(wb, sheet_name, max_rows=10, max_cols=15):
    """Investigate a single sheet"""
    print(f"\n{'='*80}")
    print(f"INVESTIGATING: {sheet_name}")
    print(f"{'='*80}\n")
    
    try:
        ws = wb[sheet_name]
        print(f"Dimensions: {ws.max_row} rows x {ws.max_column} cols")
        print(f"\nFirst {min(max_rows, ws.max_row)} rows (first {min(max_cols, ws.max_column)} cols):\n")
        
        # Read with pandas for better display
        try:
            df = pd.read_excel(
                SPREADSHEET,
                sheet_name=sheet_name,
                nrows=max_rows,
                usecols=range(max_cols),
                header=0
            )
            print(df.to_string())
            print(f"\nColumns: {list(df.columns)[:max_cols]}")
        except Exception as e:
            print(f"Could not read with pandas: {e}")
            print("Fallback - reading raw cells from openpyxl:")
            for row in range(1, min(max_rows + 1, ws.max_row + 1)):
                row_data = []
                for col in range(1, min(max_cols + 1, ws.max_column + 1)):
                    cell = ws.cell(row, col)
                    value = cell.value
                    row_data.append(str(value)[:15] if value else "")
                print(" | ".join(f"{v:15s}" for v in row_data))
    
    except Exception as e:
        print(f"ERROR investigating {sheet_name}: {e}")

def investigate_planejamento_linha_52(wb):
    """Investigate PLANEJAMENTO row 52 (line 52)"""
    print(f"\n{'='*80}")
    print(f"INVESTIGATING: PLANEJAMENTO LINE 52 (Possible CPU reference)")
    print(f"{'='*80}\n")
    
    try:
        ws = wb["PLANEJAMENTO"]
        
        print(f"Row 52 content (first 20 columns):\n")
        
        row_52_data = []
        for col in range(1, min(21, ws.max_column + 1)):
            cell = ws.cell(52, col)
            col_letter = cell.column_letter
            value = cell.value
            
            # Try to detect formulas
            formula = cell.value if isinstance(cell.value, str) and cell.value.startswith("=") else None
            
            row_52_data.append({
                "Col": col_letter,
                "Value": str(value)[:30] if value else "[empty]",
                "Type": type(cell.value).__name__
            })
        
        # Display as formatted table
        for item in row_52_data:
            print(f"{item['Col']:4s} | {item['Value']:30s} | {item['Type']}")
        
        # Check if any values reference CPU sheet
        print("\n\nChecking for CPU references in row 52:")
        for col in range(1, ws.max_column + 1):
            cell = ws.cell(52, col)
            value = str(cell.value) if cell.value else ""
            if "CPU" in value.upper():
                print(f"  FOUND: Column {cell.column_letter} = {cell.value}")
    
    except Exception as e:
        print(f"ERROR investigating PLANEJAMENTO line 52: {e}")

def analyze_relationships(wb):
    """Analyze relationships between mystery sheets"""
    print(f"\n{'='*80}")
    print(f"ANALYZING RELATIONSHIPS")
    print(f"{'='*80}\n")
    
    mystery_sheets = ["CPU", "MATERIAIS", "ENCARGOS", "DD - C. EXAMES E EPI", "Transportes"]
    
    print("Checking if mystery sheets reference each other or base data:\n")
    
    for sheet_name in mystery_sheets:
        if sheet_name not in wb.sheetnames:
            print(f"[SKIP] {sheet_name} not in workbook")
            continue
        
        ws = wb[sheet_name]
        print(f"\n{sheet_name}:")
        print(f"  - Rows: {ws.max_row}, Columns: {ws.max_column}")
        
        # Try to detect what this sheet is about
        header_row = []
        for col in range(1, min(10, ws.max_column + 1)):
            header_row.append(str(ws.cell(1, col).value)[:20] if ws.cell(1, col).value else "")
        
        print(f"  - Headers: {', '.join(header_row)}")
        
        # Check for distinctive content
        keywords = {}
        for row in range(2, min(20, ws.max_row + 1)):
            for col in range(1, min(5, ws.max_column + 1)):
                cell = ws.cell(row, col)
                if cell.value and isinstance(cell.value, str):
                    value_lower = cell.value.lower()
                    if any(kw in value_lower for kw in ["preco", "custo", "taxa", "percentual", "encargo", "epi", "transporte"]):
                        keywords[cell.value] = keywords.get(cell.value, 0) + 1
        
        if keywords:
            print(f"  - Key terms found: {dict(sorted(keywords.items(), key=lambda x: -x[1])[:5])}")

def main():
    """Run investigation"""
    wb = copy_and_load_workbook()
    
    if not wb:
        return
    
    # Investigate mystery sheets
    mystery_sheets = ["CPU", "MATERIAIS", "ENCARGOS", "DD - C. EXAMES E EPI", "Transportes"]
    
    for sheet_name in mystery_sheets:
        if sheet_name in wb.sheetnames:
            investigate_sheet(wb, sheet_name, max_rows=10, max_cols=10)
    
    # Investigate PLANEJAMENTO line 52
    investigate_planejamento_linha_52(wb)
    
    # Analyze relationships
    analyze_relationships(wb)
    
    # Summary
    print(f"\n{'='*80}")
    print("INVESTIGATION SUMMARY")
    print(f"{'='*80}\n")
    
    print("Next steps to reconcile findings:")
    print("1. CPU appears to be: [determine from above output]")
    print("2. MATERIAIS appears to be: [determine from above output]")
    print("3. ENCARGOS appears to be: [determine from above output]")
    print("4. DD - EXAMES E EPI appears to be: [determine from above output]")
    print("5. Transportes appears to be: [determine from above output]")
    
    wb.close()

if __name__ == "__main__":
    main()
