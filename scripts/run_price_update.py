#!/usr/bin/env python3
"""
run_price_update.py — Orquestrador completo do Pipeline ADR-045

Executa em sequência: anp_fetch → price_resolver → generate_pesquisa
Projetado para execução mensal via Task Scheduler / GitHub Actions.

Uso:
    python scripts/run_price_update.py --uf CE
    python scripts/run_price_update.py --uf CE --fontes sicro anp --apply
    python scripts/run_price_update.py --uf all --fontes all --apply
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT    = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PYTHON  = sys.executable

UFS_BRASIL = ["AC","AL","AM","AP","BA","CE","DF","ES","GO","MA","MG","MS",
               "MT","PA","PB","PE","PI","PR","RJ","RN","RO","RR","RS","SC","SE","SP","TO"]


def _run(cmd: list[str], label: str) -> int:
    print(f"\n  [{label}] {' '.join(cmd[1:])}")
    result = subprocess.run(cmd, capture_output=False, text=True)
    if result.returncode != 0:
        print(f"  [ERRO] {label} falhou (rc={result.returncode})", file=sys.stderr)
    return result.returncode


def run_pipeline(
    ufs: list[str],
    fontes: list[str],
    contexto: str,
    mes: str,
    apply: bool,
    auto_map: bool,
) -> dict:
    started = datetime.now(timezone.utc).isoformat()
    erros: list[str] = []
    resultados: dict[str, dict] = {}

    for uf in ufs:
        print(f"\n{'='*55}")
        print(f"  Pipeline BR-{uf} — {mes}")
        print(f"{'='*55}")
        uf_result: dict = {"uf": uf, "etapas": {}}

        # Stage 1c: ANP diesel
        if "anp" in fontes or "all" in fontes:
            rc = _run([PYTHON, str(SCRIPTS / "anp_fetch.py"), "--uf", uf, "--semana", "latest"], f"ANP BR-{uf}")
            uf_result["etapas"]["anp"] = "ok" if rc == 0 else "erro"
            if rc != 0:
                erros.append(f"anp BR-{uf}")

        # Stage 1a: SINAPI
        if "sinapi" in fontes or "all" in fontes:
            rc = _run([PYTHON, str(SCRIPTS / "sinapi_fetch.py"), "--uf", uf, "--mes", mes], f"SINAPI BR-{uf}")
            uf_result["etapas"]["sinapi"] = "ok" if rc == 0 else "erro"
            if rc != 0:
                erros.append(f"sinapi BR-{uf}")

        # Stage 2: price_resolver
        if "sicro" in fontes or "all" in fontes:
            cmd = [PYTHON, str(SCRIPTS / "price_resolver.py"), "--uf", uf, "--contexto", contexto]
            if apply:
                cmd.append("--apply")
            if auto_map:
                cmd.append("--auto-map")
            rc = _run(cmd, f"resolver BR-{uf}")
            uf_result["etapas"]["resolver"] = "ok" if rc == 0 else "erro"
            if rc != 0:
                erros.append(f"resolver BR-{uf}")

        # Stage 3: generate_pesquisa
        cmd_g = [PYTHON, str(SCRIPTS / "generate_pesquisa.py"), "--uf", uf, "--mes", mes, "--contexto", contexto]
        rc = _run(cmd_g, f"pesquisa BR-{uf}")
        uf_result["etapas"]["pesquisa"] = "ok" if rc == 0 else "erro"
        if rc != 0:
            erros.append(f"pesquisa BR-{uf}")

        resultados[uf] = uf_result

    finished = datetime.now(timezone.utc).isoformat()
    summary = {
        "iniciado_em": started,
        "concluido_em": finished,
        "ufs_processadas": len(ufs),
        "erros": erros,
        "ok": len(erros) == 0,
        "resultados": resultados,
    }

    log_dir = ROOT / "config/referencias/pesquisas/logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"pipeline_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.json"
    log_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Log salvo: {log_path}")

    return summary


def main() -> None:
    p = argparse.ArgumentParser(description="ADR-045: Pipeline completo de atualização de preços")
    p.add_argument("--uf",       required=True, help="UF (ex: CE) ou 'all'")
    p.add_argument("--fontes",   nargs="+", default=["sicro", "anp"],
                   choices=["sinapi", "sicro", "anp", "all"], help="Fontes a usar")
    p.add_argument("--mes",      default="2026-01", help="AAAA-MM de referência")
    p.add_argument("--contexto", default="mendeslobo")
    p.add_argument("--apply",    action="store_true", help="Aplica mudanças no catálogo")
    p.add_argument("--auto-map", action="store_true", dest="auto_map",
                   help="Gera mapeamento automático por descrição (SICRO)")
    args = p.parse_args()

    ufs = UFS_BRASIL if args.uf == "all" else [args.uf.upper()]
    mode = "APPLY" if args.apply else "DRY-RUN"

    print(f"\n{'='*55}")
    print(f"  run_price_update [{mode}]")
    print(f"  UFs: {', '.join(ufs)}")
    print(f"  Fontes: {', '.join(args.fontes)}")
    print(f"  Mês: {args.mes}")
    print(f"{'='*55}")

    summary = run_pipeline(ufs, args.fontes, args.contexto, args.mes, args.apply, args.auto_map)

    print(f"\n{'='*55}")
    print(f"  Concluído: {len(ufs)} UF(s)")
    print(f"  Status: {'OK' if summary['ok'] else 'ERROS'}")
    if summary["erros"]:
        print(f"  Erros: {summary['erros']}")
    print(f"{'='*55}")

    sys.exit(0 if summary["ok"] else 1)


if __name__ == "__main__":
    main()
