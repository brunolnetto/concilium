"""Inspeciona estrutura da planilha PADRÃO RFI.xlsm para mapeamento de catálogo."""
import io, sys, json
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    import openpyxl
except ImportError:
    print("openpyxl não instalado — já é dependência do projeto via requirements")
    sys.exit(1)

XLSM = Path(__file__).resolve().parents[1] / "docs/product/3-reference_files/catalogos/PLANILHA PADRÃO RFI.xlsm"
print(f"Arquivo: {XLSM}")
print(f"Existe: {XLSM.exists()}\n")

wb = openpyxl.load_workbook(XLSM, read_only=True, data_only=True)
print(f"Abas ({len(wb.sheetnames)}): {wb.sheetnames}\n")

SAMPLE_ROWS = 6   # header + 5 linhas de amostra
MAX_COLS = 30

for name in wb.sheetnames:
    ws = wb[name]
    print("=" * 70)
    print(f"ABA: {name!r}  (dims: {ws.dimensions})")
    rows = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i >= SAMPLE_ROWS:
            break
        # Trunca colunas longas demais
        cells = [str(c)[:40] if c is not None else "" for c in row[:MAX_COLS]]
        rows.append(cells)

    if not rows:
        print("  (vazia)")
        continue

    # Detecta header (primeira linha com conteúdo)
    headers = rows[0] if rows else []
    print(f"  Colunas detectadas ({len([h for h in headers if h])}):")
    for ci, h in enumerate(headers):
        if h:
            # Mostra header + amostra dos primeiros valores
            samples = [rows[r][ci] for r in range(1, len(rows)) if ci < len(rows[r]) and rows[r][ci]]
            print(f"    [{ci:2d}] {h!r:<35}  ex: {samples[:3]}")
    print()

wb.close()
