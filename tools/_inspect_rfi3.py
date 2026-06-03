"""Lê estrutura real das abas BD_* da planilha RFI (sem read_only para merged cells)."""
import io, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import openpyxl

XLSM = Path(__file__).resolve().parents[1] / "docs/product/3-reference_files/catalogos/PLANILHA PADRÃO RFI.xlsm"
wb = openpyxl.load_workbook(XLSM, data_only=True, keep_vba=False)

TARGET = ["BD_MÃO_DE_OBRA", "BD_EQUIPAMENTOS", "BD_MATERIAIS", "BD_PRODUTIVIDADES", "SERVIÇOS TERCEIRIZADOS"]

HEADER_KEYWORDS = {"código", "code", "cod", "codigo", "descrição", "descricao", "description"}

def find_header_row(ws, max_scan=20):
    """Retorna índice da linha que contém o header real."""
    for ri, row in enumerate(ws.iter_rows(max_row=max_scan, values_only=True)):
        non_null = [c for c in row if c is not None]
        if len(non_null) >= 2:
            first = str(non_null[0]).strip().lower()
            if any(k in first for k in HEADER_KEYWORDS):
                return ri
        # Também aceita linha com muitos valores não-nulos
        if len(non_null) >= 4:
            return ri
    return 0

for name in TARGET:
    if name not in wb.sheetnames:
        print(f"\n[AUSENTE] {name}")
        continue
    ws = wb[name]
    print(f"\n{'='*65}")
    print(f"ABA: {name}  (max_row={ws.max_row}, max_col={ws.max_column})")

    hr = find_header_row(ws)
    print(f"  Header detectado na linha {hr+1}")

    # Lê header + 6 linhas de dados
    all_rows = list(ws.iter_rows(min_row=hr+1, max_row=hr+10, values_only=True))
    if not all_rows:
        print("  (vazio)")
        continue

    header = all_rows[0]
    data_rows = all_rows[1:]

    # Filtra colunas com header não-nulo
    active_cols = [(ci, h) for ci, h in enumerate(header) if h is not None]
    print(f"  {len(active_cols)} colunas com header:")
    for ci, h in active_cols:
        samples = []
        for row in data_rows:
            if ci < len(row) and row[ci] is not None:
                samples.append(str(row[ci])[:45])
        print(f"    [{ci:2d}] {str(h):<40}  ex: {' | '.join(samples[:4])}")

wb.close()
