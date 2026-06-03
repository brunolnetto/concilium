"""Simula o fechamento de levers de equilíbrio sobre o último run do benchmark.

Uso:
    python3 tools/simulate_lever_application.py [SLUG] [lever_id ...] [--json]

Exemplos:
    python3 tools/simulate_lever_application.py AGIS fechar_gap_escala fechar_gap_pool
    python3 tools/simulate_lever_application.py AGIS revisao_bdi_minima --json

Mecanismo:
    Para cada item de PontoEquilibrio, o lever identificado como selecionado
    reduz o custo_fixo_equipe pelo seu delta_margin (excesso eliminável).
    O resultado é comparado com o baseline ao nível do item e no agregado.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

LEVER_DOCS = {
    "fechar_gap_escala": (
        "custo",
        "Executar cada frente com 1 equipe sem compressão de prazo. "
        "Requer ampliação do prazo contratual ou redução de escopo por fase.",
    ),
    "fechar_gap_pool": (
        "custo",
        "Adotar contrato residente — uma mobilização/desmobilização única "
        "para todo o projeto, eliminando ciclos extras entre itens.",
    ),
    "fechar_gap_praticabilidade": (
        "custo",
        "Melhorar praticabilidade operacional: turno noturno, janela seca, "
        "abrigos. Reduz desvio de produtividade em relação ao nominal.",
    ),
    "revisao_bdi_minima": (
        "preco",
        "Revisão do BDI contratual. Requer laudo técnico e aprovação do contratante.",
    ),
}


def _find_agis_canonical(slug: str) -> Path:
    projects_dir = ROOT / "benchmarks" / "projetos"
    if not projects_dir.exists():
        raise FileNotFoundError(f"Diretório de projetos não encontrado: {projects_dir}")

    candidate: Path | None = None
    for project_dir in sorted(projects_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        meta_path = project_dir / "meta.json"
        if not project_dir.is_dir() or not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if slug.upper() in meta.get("nome", "").upper() or slug.upper() in meta.get("slug", "").upper():
            canon = project_dir / "v1" / "canonical.json"
            if canon.exists():
                candidate = canon
                break

    if candidate is None:
        raise FileNotFoundError(
            f"Canonical para slug '{slug}' não encontrado em {projects_dir}. "
            "Execute o benchmark primeiro."
        )
    return candidate


def _load_ponto_equilibrio(canonical_path: Path) -> tuple[list[dict], dict]:
    """Retorna (pe_list, financeiro_resumo) do canonical.json."""
    raw = json.loads(canonical_path.read_text(encoding="utf-8"))
    pe_list = raw.get("ponto_equilibrio") or []
    # Financeiro resumo para contexto de preco_venda/custo_direto
    resultado = raw.get("resultado_financeiro") or raw.get("resultado") or {}
    return pe_list, resultado


def _simulate(
    pe_list: list[dict],
    lever_ids: list[str],
) -> list[dict]:
    """Aplica os levers e retorna lista de itens com campos before/after."""
    rows = []
    for pe in pe_list:
        item_id = pe.get("item_id", "?")
        custo_fixo = float(pe.get("custo_fixo_equipe", 0.0))
        custo_venda = float(pe.get("custo_venda_cpu", 0.0))
        delta_baseline = float(pe.get("delta", custo_venda - custo_fixo))

        levers = pe.get("levers_equilibrio") or []
        applied: list[dict] = []
        total_reducao = 0.0
        for lv in levers:
            if lv.get("id") in lever_ids:
                dm = float(lv.get("delta_margin", 0.0))
                applied.append({"id": lv["id"], "delta_margin": dm})
                total_reducao += dm

        custo_fixo_sim = custo_fixo - total_reducao
        delta_sim = custo_venda - custo_fixo_sim
        status_baseline = "OK" if delta_baseline >= 0 else "ERRO"
        status_sim = "OK" if delta_sim >= 0 else "ERRO"

        rows.append({
            "item_id": item_id,
            "custo_fixo_baseline": round(custo_fixo, 2),
            "custo_fixo_sim": round(custo_fixo_sim, 2),
            "custo_venda": round(custo_venda, 2),
            "delta_baseline": round(delta_baseline, 2),
            "delta_sim": round(delta_sim, 2),
            "reducao_custo": round(total_reducao, 2),
            "status_baseline": status_baseline,
            "status_sim": status_sim,
            "levers_aplicados": applied,
        })
    return rows


def _print_report(
    slug: str,
    lever_ids: list[str],
    rows: list[dict],
    resultado: dict,
    canonical_path: Path,
) -> None:
    def fmt(v: float) -> str:
        return f"R$ {v:>14,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def pct(a: float, b: float) -> str:
        if b == 0:
            return "  —"
        return f"{(a - b) / abs(b) * 100:+.2f}%"

    print()
    print("=" * 72)
    print(f"  SIMULAÇÃO DE FECHAMENTO DE LEVERS — {slug}")
    print("=" * 72)
    print()

    print("  Levers aplicados:")
    for lid in lever_ids:
        tipo, doc = LEVER_DOCS.get(lid, ("?", lid))
        tag = "custo" if tipo == "custo" else "preço"
        print(f"    [{tag}] {lid}")
        print(f"          {doc}")
    print()
    print(f"  Fonte canonical: {canonical_path.relative_to(ROOT)}")
    print()

    # Por item
    print(f"  {'Item':<20} {'Custo (base)':>16} {'Custo (sim)':>14} {'Delta (base)':>14} {'Delta (sim)':>13} {'Chg':>7} {'Status'}")
    print("  " + "-" * 90)
    for r in rows:
        chg = pct(r["delta_sim"], r["delta_baseline"])
        status = f"{r['status_baseline']} → {r['status_sim']}"
        print(
            f"  {r['item_id']:<20} {fmt(r['custo_fixo_baseline'])[3:]:>16} "
            f"{fmt(r['custo_fixo_sim'])[3:]:>14} "
            f"{fmt(r['delta_baseline'])[3:]:>14} "
            f"{fmt(r['delta_sim'])[3:]:>13}  {chg:>7}  {status}"
        )

    # Agregado
    print("  " + "-" * 90)
    total_custo_base = sum(r["custo_fixo_baseline"] for r in rows)
    total_custo_sim = sum(r["custo_fixo_sim"] for r in rows)
    total_delta_base = sum(r["delta_baseline"] for r in rows)
    total_delta_sim = sum(r["delta_sim"] for r in rows)
    total_reducao = sum(r["reducao_custo"] for r in rows)
    itens_ok_base = sum(1 for r in rows if r["status_baseline"] == "OK")
    itens_ok_sim = sum(1 for r in rows if r["status_sim"] == "OK")

    print(
        f"  {'TOTAL':<20} {fmt(total_custo_base)[3:]:>16} "
        f"{fmt(total_custo_sim)[3:]:>14} "
        f"{fmt(total_delta_base)[3:]:>14} "
        f"{fmt(total_delta_sim)[3:]:>13}  {pct(total_delta_sim, total_delta_base):>7}"
    )
    print()
    print(f"  Redução total de custo direto : {fmt(total_reducao)}")
    print(f"  Itens em ERRO → OK            : {itens_ok_base} → {itens_ok_sim} de {len(rows)}")

    # Resultado financeiro do projeto (contexto)
    preco_venda = float(resultado.get("preco_venda", 0.0) or 0.0)
    custo_direto = float(resultado.get("custo_direto", 0.0) or 0.0)
    custo_indireto = float(resultado.get("custo_indireto", 0.0) or 0.0)
    if preco_venda > 0:
        custo_direto_sim = custo_direto - total_reducao
        custo_total_sim = custo_direto_sim + custo_indireto
        margem_base = preco_venda - (custo_direto + custo_indireto)
        margem_sim = preco_venda - custo_total_sim
        print()
        print("  Impacto no resultado consolidado do projeto:")
        print(f"    Preço de venda (fixo)     : {fmt(preco_venda)}")
        print(f"    Custo direto baseline     : {fmt(custo_direto)}")
        print(f"    Custo direto simulado     : {fmt(custo_direto_sim)}  (−{fmt(total_reducao)[3:]})")
        print(f"    Custo indireto (fixo)     : {fmt(custo_indireto)}")
        print(f"    Margem baseline           : {fmt(margem_base)}  ({margem_base / preco_venda * 100:.1f}%)")
        print(f"    Margem simulada           : {fmt(margem_sim)}  ({margem_sim / preco_venda * 100:.1f}%)")

    print()
    print("=" * 72)
    print()


def main(argv: list[str] | None = None) -> int:
    args = (argv or sys.argv[1:]).copy()
    as_json = "--json" in args
    if as_json:
        args.remove("--json")

    slug = args[0].upper() if args else "AGIS"
    lever_ids = args[1:] if len(args) > 1 else ["fechar_gap_escala", "fechar_gap_pool"]

    available = list(LEVER_DOCS.keys())
    invalid = [lid for lid in lever_ids if lid not in available]
    if invalid:
        print(f"[ERRO] Levers desconhecidos: {invalid}")
        print(f"       Disponíveis: {available}")
        return 1

    try:
        canonical_path = _find_agis_canonical(slug)
    except FileNotFoundError as e:
        print(f"[ERRO] {e}")
        return 1

    pe_list, resultado = _load_ponto_equilibrio(canonical_path)
    if not pe_list:
        print(f"[ERRO] Nenhum ponto_equilibrio encontrado em {canonical_path}")
        return 1

    rows = _simulate(pe_list, lever_ids)

    if as_json:
        out = {
            "slug": slug,
            "levers_aplicados": lever_ids,
            "canonical": str(canonical_path.relative_to(ROOT)),
            "itens": rows,
            "agregado": {
                "total_reducao_custo": round(sum(r["reducao_custo"] for r in rows), 2),
                "total_delta_baseline": round(sum(r["delta_baseline"] for r in rows), 2),
                "total_delta_sim": round(sum(r["delta_sim"] for r in rows), 2),
                "itens_ok_baseline": sum(1 for r in rows if r["status_baseline"] == "OK"),
                "itens_ok_sim": sum(1 for r in rows if r["status_sim"] == "OK"),
            },
        }
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    else:
        _print_report(slug, lever_ids, rows, resultado, canonical_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
