#!/usr/bin/env python3
"""
MATA_DENSA — 3 Versões de Sobreposição via completion_threshold_pct (ADR-081)

Cria um único projeto MATA_DENSA com 3 versões derivadas:
  v1  Sequencial    θ=1.00  FS clássico (baseline)
  v2  Conservador   θ=0.50  SV-002 inicia quando SV-001 atinge 50%  ← forked de v1
  v3  Agressivo     θ=0.33  SV-002 inicia quando SV-001 atinge 33%  ← forked de v2

Entregáveis:
  benchmarks/projetos/MATA_DENSA/
    v1/canonical.json + artifacts/
    v2/canonical.json + artifacts/   (forked_from: v1)
    v3/canonical.json + artifacts/   (forked_from: v2)

Uso:
    python benchmarks/run_mata_densa_sobreposicao.py [--reset]
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_ROOT = Path(__file__).resolve().parent.parent
_SLUG = "MATA_DENSA"

VERSOES = [
    {"version": "v1", "theta": 1.0,  "motivo": "Sequencial — FS clássico (θ=1.0)",         "forked_from": None},
    {"version": "v2", "theta": 0.5,  "motivo": "Conservador — sobreposição 50% (θ=0.50)",  "forked_from": "v1"},
    {"version": "v3", "theta": 0.33, "motivo": "Agressivo — sobreposição 33% (θ=0.33)",    "forked_from": "v2"},
]


def _patch_eap_theta(eap: list[dict], successor_id: str, predecessor_id: str, theta: float) -> list[dict]:
    """Retorna cópia do EAP com completion_threshold_pct alterado para o predecessor especificado."""
    eap = copy.deepcopy(eap)
    for item in eap:
        if item.get("item_id") == successor_id:
            for pred in item.get("predecessores", []):
                if isinstance(pred, dict) and pred.get("item_id") == predecessor_id:
                    pred["completion_threshold_pct"] = theta
    return eap


def _spec_with_theta(ref: dict, ref_path: Path, theta: float) -> "ProjectSpec":
    """Carrega spec completo via load_spec_from_dict e aplica θ no EAP."""
    from concilium.application.benchmarks.spec.spec_loader import load_spec_from_dict

    ref_patched = copy.deepcopy(ref)
    ref_patched["spec"]["eap"] = _patch_eap_theta(
        ref_patched["spec"]["eap"], "SV-SIMPLES-002", "SV-SIMPLES-001", theta
    )
    return load_spec_from_dict(ref_patched, ref_path)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Executa MATA_DENSA com 3 versões de sobreposição (ADR-081)")
    parser.add_argument("--reset", action="store_true", help="Apagar e recriar o projeto do zero")
    args = parser.parse_args()

    os.environ.setdefault("CONCILIUM__CONFIG_ROOT", str(_ROOT / "config"))
    os.environ.setdefault("CONCILIUM__PROJECTS_ROOT", str(_ROOT / "benchmarks" / "projetos"))

    from concilium.application.benchmarks import (
        BenchmarkReportBuilder,
        BenchmarkReportPrinter,
        ProjectSpec,
    )
    from concilium.application.benchmarks.execution.runner import BenchmarkRunner
    from concilium.infrastructure.storage.store_factory import build_local_project_repository

    projects_root = _ROOT / "benchmarks" / "projetos"
    config_root = _ROOT / "config"
    benchmarks_root = _ROOT / "benchmarks" / "data"

    ref_path = benchmarks_root / _SLUG / "referencia.json"
    ref = json.loads(ref_path.read_text(encoding="utf-8"))

    runner = BenchmarkRunner(
        config_root=config_root,
        projects_root=projects_root,
        report_builder=BenchmarkReportBuilder(),
        report_printer=BenchmarkReportPrinter(),
    )
    repo = build_local_project_repository(projects_root)

    W = 90
    print(f"\n{'=' * W}")
    print(f"  MATA_DENSA — 3 VERSÕES DE SOBREPOSIÇÃO (ADR-081 completion_threshold_pct)")
    print(f"{'=' * W}")

    resultados = []

    for i, v in enumerate(VERSOES):
        theta = v["theta"]
        version_label = v["version"]
        motivo = v["motivo"]
        forked_from = v["forked_from"]

        print(f"\n{'─' * W}")
        print(f"  {version_label.upper()}  {motivo}")
        print(f"{'─' * W}")

        spec = _spec_with_theta(ref, ref_path, theta)

        if i == 0:
            # v1: cria/reseta o projeto e executa a pipeline
            report = runner.run(spec, reset=args.reset)
        else:
            # v2/v3: faz fork da versão anterior, depois executa a pipeline
            try:
                store = repo.get_project(_SLUG)
            except FileNotFoundError:
                print(f"  [ERRO] Projeto {_SLUG} não encontrado. Execute com --reset.")
                sys.exit(1)

            new_ver = store.new_version(
                base=forked_from,
                forked_from=forked_from,
                motivo=motivo,
            )
            print(f"  [FORK] {forked_from} → {new_ver}  (θ={theta})")

            # Skill-01 recusa rodar se canonical_in != None.
            # Após fork (copy-on-write), o canonical de new_ver é cópia do predecessor.
            # Deletá-lo força skill-01 a criar o canonical do zero com os novos inputs.
            canonical_blob_path = store._path(f"{new_ver}/{store._CANONICAL_FILE}")
            store._storage.deletar_blob(canonical_blob_path)
            print(f"  [DEL]  canonical de {new_ver} limpo para re-execução com θ={theta}")

            report = runner.run(spec, reset=False)

        # Extrair resultado do canonical diretamente (o relatório de confronto não tem custo)
        canonical_path = projects_root / _SLUG / version_label / "canonical.json"
        # Após fork+run, current_version pode ser v2 ou v3 — precisamos ler o canonical correto
        try:
            store_now = repo.get_project(_SLUG)
            current_ver = store_now.current_version()
        except Exception:
            current_ver = version_label

        # Tentar canonical do version_label primeiro; fallback para current
        for ver_try in [version_label, current_ver]:
            cp = projects_root / _SLUG / ver_try / "canonical.json"
            if cp.exists():
                canonical_path = cp
                break

        canonical = {}
        if canonical_path.exists():
            with open(canonical_path, encoding="utf-8") as f:
                canonical = json.load(f)

        resultado = canonical.get("resultado", {})
        custo = (resultado.get("custo") or {}).get("total", 0) or 0
        venda = (resultado.get("venda") or {}).get("total_com_bdi", 0) or 0
        margem = resultado.get("margem_pct", 0) or 0
        makespan = canonical.get("cronograma", {}).get("makespan_weeks")
        dag_arestas = canonical.get("activity_dag", {}).get("arestas", [])

        # Verificar θ efetivo no activity_dag
        theta_efetivo = next(
            (a.get("completion_threshold_pct", 1.0) for a in dag_arestas),
            1.0,
        )

        acts = canonical.get("cronograma", {}).get("scheduled_activities", [])
        act_str = "  ".join(
            f"{a.get('activity_id', '?')[-3:]}:[{a.get('start_week')}-{a.get('end_week')}]"
            for a in acts
        )

        resultados.append({
            "version": version_label,
            "theta": theta,
            "theta_efetivo": theta_efetivo,
            "makespan": makespan,
            "custo": custo,
            "venda": venda,
            "margem": margem,
            "acts": act_str,
        })

        print(f"  θ especificado: {theta:.2f}  |  θ no DAG: {theta_efetivo:.2f}")
        print(f"  Makespan: {makespan} semanas  |  Custo: R$ {custo:,.0f}  |  Cronograma: {act_str}")

    # Tabela comparativa final
    print(f"\n{'=' * W}")
    print(f"  COMPARATIVO FINAL — projeto: {_SLUG}")
    print(f"{'=' * W}")
    print(f"  {'Versão':<8} | {'θ':>5} | {'Makespan':>10} | {'Custo Total':>15} | {'Delta Custo':>13} | {'Cronograma'}")
    print(f"  {'-'*8}-+-{'-'*5}-+-{'-'*10}-+-{'-'*15}-+-{'-'*13}-+---")

    base_custo = resultados[0]["custo"] if resultados else 0
    base_make = resultados[0]["makespan"] if resultados else None

    for r in resultados:
        dc = r["custo"] - base_custo
        dm_str = f"{r['makespan']:+d}" if (base_make and r["makespan"]) else "N/A"
        dm_str = f"{r['makespan'] - base_make:+d}" if (base_make and r["makespan"] and r != resultados[0]) else (str(r["makespan"]) if r["makespan"] else "?")
        print(
            f"  {r['version']:<8} | {r['theta']:>5.2f} | {str(r['makespan']) + ' sem':>10} | "
            f"R$ {r['custo']:>12,.0f} | {('+' if dc >= 0 else '') + f'R$ {dc:>9,.0f}':>13} | {r['acts']}"
        )

    print(f"{'=' * W}")

    # Verificar meta.json do projeto para confirmar version_history
    meta_path = projects_root / _SLUG / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        print(f"\n  VERSÕES NO PROJETO (meta.json):")
        for ver, info in meta.get("version_history", {}).items():
            forked = info.get("forked_from") or "—"
            motiv = (info.get("motivo") or "")[:50]
            print(f"    {ver}: forked_from={forked:<4}  motivo={motiv}")
        print(f"  current_version: {meta.get('current_version')}")

    print(f"\n  Entregáveis: {projects_root / _SLUG}")
    print(f"    v1/canonical.json  (θ=1.00 — Sequencial)")
    print(f"    v2/canonical.json  (θ=0.50 — Conservador, forked de v1)")
    print(f"    v3/canonical.json  (θ=0.33 — Agressivo, forked de v2)")


if __name__ == "__main__":
    main()
