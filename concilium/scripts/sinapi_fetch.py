#!/usr/bin/env python3
"""
sinapi_fetch.py — Stage 1a do Pipeline ADR-045

Baixa e parseia tabelas SINAPI (Caixa Econômica Federal) de insumos por UF/mês.
Salva em `config/referencias/SINAPI/BR-{UF}/insumos_{AAAA-MM}.json`.

URL padrão CEF (NãoDesonerado):
  https://www.caixa.gov.br/Downloads/sinapi-custo-ref-insumos-{uf_lower}/{ANO}/{MES}/
    SINAPI_ref_insumos_{UF}_{AAAA}{MM}_NaoDesonerado.xlsx

Uso:
    python scripts/sinapi_fetch.py --uf CE --mes 2026-01
    python scripts/sinapi_fetch.py --uf CE --arquivo /caminho/local/sinapi.xlsx
    python scripts/sinapi_fetch.py --uf all --mes 2026-01
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]

SINAPI_URL_TEMPLATE = (
    "https://www.caixa.gov.br/Downloads/sinapi-custo-ref-insumos-{uf_lower}/{ano}/{mes_pad}/"
    "SINAPI_ref_insumos_{UF}_{ano}{mes_pad}_NaoDesonerado.xlsx"
)

TIPO_MAP = {
    "material": "MATERIAL",
    "equipamento": "EQUIPAMENTO",
    "mao de obra": "MAO_OBRA",
    "mão de obra": "MAO_OBRA",
    "servico": "TERCEIRIZADO",
    "serviço": "TERCEIRIZADO",
}


def _parse_sinapi_xlsx(path: Path) -> list[dict]:
    """Parseia planilha SINAPI NãoDesonerado e retorna lista de insumos."""
    try:
        import openpyxl
    except ImportError:
        print("openpyxl necessário: uv add openpyxl", file=sys.stderr)
        sys.exit(2)

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    insumos: list[dict] = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        # Detecta tipo pela aba
        tipo_aba = TIPO_MAP.get(sheet_name.lower().strip(), None)

        header_row = None
        for ri, row in enumerate(ws.iter_rows(values_only=True)):
            non_null = [c for c in row if c is not None]
            if not non_null:
                continue
            first = str(non_null[0]).strip().lower()
            # Header detectado quando tem "código" ou "descrição"
            if any(k in first for k in ("código", "codigo", "code", "descrição")):
                header_row = ri
                header = [str(c).strip() if c else f"_col{i}" for i, c in enumerate(row)]
                break

        if header_row is None:
            continue

        col_codigo = next((i for i, h in enumerate(header) if "dig" in h.lower() or "cod" in h.lower()), 0)
        col_desc   = next((i for i, h in enumerate(header) if "descri" in h.lower()), 1)
        col_unid   = next((i for i, h in enumerate(header) if "unid" in h.lower()), 2)
        col_preco  = next((i for i, h in enumerate(header) if "preço" in h.lower() or "preco" in h.lower() or "r$" in h.lower()), 3)
        col_tipo   = next((i for i, h in enumerate(header) if "classe" in h.lower() or "tipo" in h.lower() or "grupo" in h.lower()), None)

        rows_read = 0
        for row in ws.iter_rows(min_row=header_row + 2, values_only=True):
            if all(c is None for c in row):
                continue
            codigo = str(row[col_codigo] or "").strip() if col_codigo < len(row) else ""
            if not codigo or not re.match(r"\d{5}", codigo):
                continue
            desc   = str(row[col_desc]  or "").strip() if col_desc  < len(row) else ""
            unid   = str(row[col_unid]  or "UN").strip() if col_unid  < len(row) else "UN"
            try:
                preco = float(row[col_preco] or 0) if col_preco < len(row) else 0
            except (TypeError, ValueError):
                preco = 0

            tipo = tipo_aba or "MATERIAL"
            if col_tipo is not None and col_tipo < len(row) and row[col_tipo]:
                raw_tipo = str(row[col_tipo]).strip().lower()
                tipo = TIPO_MAP.get(raw_tipo, tipo)

            insumos.append({
                "codigo_referencia": codigo,
                "descricao":         desc,
                "tipo":              tipo,
                "unidade":           unid,
                "preco_publicado":   preco,
                "origem":            "SINAPI",
            })
            rows_read += 1

    wb.close()
    return insumos


def _download(uf: str, ano: str, mes: str) -> Path | None:
    """Baixa xlsx do portal CEF. Retorna path local ou None se falhar."""
    mes_pad = mes.zfill(2)
    url = SINAPI_URL_TEMPLATE.format(uf_lower=uf.lower(), UF=uf.upper(), ano=ano, mes_pad=mes_pad)
    out_dir = ROOT / f"config/referencias/SINAPI/BR-{uf.upper()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"SINAPI_{uf.upper()}_{ano}{mes_pad}_NaoDesonerado.xlsx"

    if out_path.exists():
        print(f"  [CACHE] {out_path.name}")
        return out_path

    try:
        import urllib.request
        print(f"  Baixando {url} ...")
        req = urllib.request.Request(url, headers={"User-Agent": "Concilium/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            out_path.write_bytes(resp.read())
        print(f"  Salvo em: {out_path}")
        return out_path
    except Exception as e:
        print(f"  [ERRO] Download falhou: {e}", file=sys.stderr)
        return None


def fetch_uf(uf: str, mes_ref: str, arquivo_local: str | None = None) -> list[dict]:
    ano, mes = mes_ref.split("-")
    out_dir  = ROOT / f"config/referencias/SINAPI/BR-{uf.upper()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / f"insumos_{mes_ref}.json"

    if out_json.exists():
        print(f"  [CACHE] {out_json}")
        return json.loads(out_json.read_text(encoding="utf-8")).get("insumos", [])

    if arquivo_local:
        xlsx_path = Path(arquivo_local)
    else:
        xlsx_path = _download(uf, ano, mes)

    if xlsx_path is None or not xlsx_path.exists():
        print(f"  [SKIP] BR-{uf}: xlsx não disponível")
        return []

    print(f"  Parseando {xlsx_path.name} ...")
    insumos = _parse_sinapi_xlsx(xlsx_path)
    print(f"  {len(insumos)} insumos extraídos")

    result = {
        "$schema": "https://concilium.framework/schemas/v1/tabela_referencia",
        "provedor": "SINAPI",
        "versao": mes_ref,
        "jurisdicao": f"BR-{uf.upper()}",
        "data_vigencia": f"{mes_ref}-01",
        "url_fonte": SINAPI_URL_TEMPLATE.format(
            uf_lower=uf.lower(), UF=uf.upper(), ano=ano, mes_pad=mes.zfill(2)
        ),
        "imutavel": True,
        "insumos": insumos,
    }
    out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Salvo: {out_json}")
    return insumos


def main() -> None:
    p = argparse.ArgumentParser(description="ADR-045 Stage 1a: Fetch SINAPI/CEF")
    p.add_argument("--uf",      required=True, help="UF (ex: CE) ou 'all'")
    p.add_argument("--mes",     default="2026-01", help="AAAA-MM")
    p.add_argument("--arquivo", default=None, help="Arquivo xlsx local (opcional)")
    args = p.parse_args()

    ufs = ["CE","SP","RJ","MG","GO","MT","BA","PE","PA","AM","RS","PR","SC","ES","DF",
           "MS","RO","AC","RR","AP","TO","MA","PI","RN","PB","AL","SE"] \
          if args.uf == "all" else [args.uf.upper()]

    for uf in ufs:
        print(f"\n  SINAPI BR-{uf} {args.mes}")
        fetch_uf(uf, args.mes, args.arquivo if args.uf != "all" else None)


if __name__ == "__main__":
    main()
