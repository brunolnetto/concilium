#!/usr/bin/env python3
"""
anp_fetch.py — Stage 1c do Pipeline ADR-045

Obtém preço médio estadual do diesel S-10 via API de dados abertos da ANP.
Salva em `config/referencias/ANP/BR-{UF}/diesel.json` (artefato imutável por semana).

Uso:
    python scripts/anp_fetch.py --uf CE --semana latest
    python scripts/anp_fetch.py --uf CE --preco-manual 7.35  # seed manual quando API indisponível
    python scripts/anp_fetch.py --uf all --semana latest
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]

# Preços de seed (fontes web verificadas em 2026-05-14) — fallback quando API indisponível
# Fonte: ANP pesquisa semana 3-9/mai/2026
SEED_PRICES: dict[str, dict] = {
    "CE": {"preco_medio": 7.35, "semana": "2026-W19", "data_referencia": "2026-05-09", "n_postos_estimado": 312},
    "SP": {"preco_medio": 6.74, "semana": "2026-W19", "data_referencia": "2026-05-09", "n_postos_estimado": 1840},
    "GO": {"preco_medio": 6.82, "semana": "2026-W19", "data_referencia": "2026-05-09", "n_postos_estimado": 420},
    "MT": {"preco_medio": 6.95, "semana": "2026-W19", "data_referencia": "2026-05-09", "n_postos_estimado": 280},
    "RJ": {"preco_medio": 6.99, "semana": "2026-W19", "data_referencia": "2026-05-09", "n_postos_estimado": 890},
    "MG": {"preco_medio": 6.88, "semana": "2026-W19", "data_referencia": "2026-05-09", "n_postos_estimado": 1200},
    "BA": {"preco_medio": 7.28, "semana": "2026-W19", "data_referencia": "2026-05-09", "n_postos_estimado": 680},
    "PE": {"preco_medio": 7.31, "semana": "2026-W19", "data_referencia": "2026-05-09", "n_postos_estimado": 520},
    "PA": {"preco_medio": 7.42, "semana": "2026-W19", "data_referencia": "2026-05-09", "n_postos_estimado": 380},
    "AM": {"preco_medio": 7.58, "semana": "2026-W19", "data_referencia": "2026-05-09", "n_postos_estimado": 180},
}

ANP_API_BASE = "https://dados.gov.br/api/action/datastore_search"
ANP_RESOURCE_ID = "f3bcbf16-6b19-4ad5-b53b-2c7b1498ee04"  # série histórica combustíveis


def _fetch_api(uf: str, semana: str) -> dict | None:
    """Tenta buscar preço via API dados.gov.br/ANP."""
    try:
        import urllib.request, urllib.parse
        params = {
            "resource_id": ANP_RESOURCE_ID,
            "filters": json.dumps({"ESTADO": uf, "PRODUTO": "ÓLEO DIESEL S10"}),
            "limit": 500,
        }
        url = f"{ANP_API_BASE}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Concilium/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        records = data.get("result", {}).get("records", [])
        if not records:
            return None
        # Média ponderada por volume
        total_vol, total_preco = 0.0, 0.0
        n_postos = len(records)
        for r in records:
            preco = float(r.get("PREÇO MÉDIO REVENDA") or 0)
            vol   = float(r.get("COEF DE VARIAÇÃO PREÇO REVENDA") or 1)  # proxy de volume
            total_preco += preco * vol
            total_vol   += vol
        media = total_preco / total_vol if total_vol > 0 else 0
        if media <= 0:
            return None
        return {
            "preco_medio_ponderado": round(media, 4),
            "n_postos": n_postos,
            "data_referencia": records[0].get("DATA INICIAL", ""),
        }
    except Exception as e:
        print(f"  [AVISO] API ANP indisponível: {e}", file=sys.stderr)
        return None


def _build_diesel_json(uf: str, preco: float, semana: str, data_ref: str, n_postos: int, fonte: str) -> dict:
    return {
        "$schema": "https://concilium.framework/schemas/v1/tabela_referencia",
        "provedor": "ANP",
        "versao": semana,
        "jurisdicao": f"BR-{uf}",
        "data_vigencia": data_ref,
        "imutavel": True,
        "fonte_coleta": fonte,
        "combustiveis": [
            {
                "produto": "DIESEL_S10",
                "unidade": "l",
                "preco_medio_ponderado": preco,
                "n_postos": n_postos,
            }
        ],
    }


def fetch_uf(uf: str, semana: str, preco_manual: float | None = None) -> dict | None:
    out_dir = ROOT / f"config/referencias/ANP/BR-{uf}"
    out_dir.mkdir(parents=True, exist_ok=True)

    if preco_manual:
        data_ref = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        wk = datetime.now(timezone.utc).strftime("%Y-W%W")
        result = _build_diesel_json(uf, preco_manual, wk, data_ref, 0, "manual")
        msg = f"manual R${preco_manual}/L"
    else:
        api_result = _fetch_api(uf, semana)
        if api_result:
            preco    = api_result["preco_medio_ponderado"]
            data_ref = api_result.get("data_referencia", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            result   = _build_diesel_json(uf, preco, semana, data_ref, api_result["n_postos"], "ANP_API")
            msg = f"API ANP R${preco}/L ({api_result['n_postos']} postos)"
        elif uf in SEED_PRICES:
            seed   = SEED_PRICES[uf]
            preco  = seed["preco_medio"]
            result = _build_diesel_json(uf, preco, seed["semana"], seed["data_referencia"],
                                         seed.get("n_postos_estimado", 0), "ANP_seed_web")
            msg = f"seed R${preco}/L (ANP web {seed['semana']})"
        else:
            print(f"  [SKIP] BR-{uf}: sem preço disponível")
            return None

    out_path = out_dir / f"diesel_{result['versao'].replace(':', '-')}.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  BR-{uf}: {msg} → {out_path.name}")
    return result


def main() -> None:
    p = argparse.ArgumentParser(description="ADR-045 Stage 1c: Fetch diesel ANP")
    p.add_argument("--uf",          required=True, help="UF ou 'all'")
    p.add_argument("--semana",      default="latest", help="Semana ISO ou 'latest'")
    p.add_argument("--preco-manual", type=float, dest="preco_manual",
                   help="Preço manual R$/L (quando API indisponível)")
    args = p.parse_args()

    ufs = list(SEED_PRICES.keys()) if args.uf == "all" else [args.uf.upper()]
    semana = args.semana if args.semana != "latest" else datetime.now(timezone.utc).strftime("%Y-W%W")

    print(f"\n  anp_fetch — {len(ufs)} UF(s) — semana {semana}")
    for uf in ufs:
        fetch_uf(uf, semana, args.preco_manual if args.uf != "all" else None)


if __name__ == "__main__":
    main()
