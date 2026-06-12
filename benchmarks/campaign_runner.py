#!/usr/bin/env python3
"""ADR-070 campaign runner — standalone script.

Usage (from project root):
    python3 benchmarks/campaign_runner.py

Reads:
  benchmarks/data/AGIS/referencia.json    — base_spec
  benchmarks/data/AGIS/campaign_v1.json   — sweep config

Runs executar_campanha and prints a formatted summary table.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Make sure src/ is importable
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from concilium.application.services.campaign_service import executar_campanha
from concilium.domain.models.campaign import (
    CampaignOutputBundle,
    CenarioAvaliado,
    GoResearchCampaignBundle,
    ParametroSweep,
    PerfilExpectativas,
)

BENCHMARKS_DIR = _ROOT / "benchmarks"
DATA_DIR = BENCHMARKS_DIR / "data" / "AGIS"
CONFIG_ROOT = _ROOT / "config"
PROJECTS_ROOT = BENCHMARKS_DIR / "projetos"


def _load_campaign_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_bundle(base_spec: dict, cfg: dict) -> GoResearchCampaignBundle:
    perf_raw = cfg.get("perfil_expectativas") or {}
    perfil = PerfilExpectativas(
        meta_margem_pct=perf_raw.get("meta_margem_pct", 0.10),
        tolerancia_margem=perf_raw.get("tolerancia_margem", 0.03),
        prazo_contratual_semanas=perf_raw.get("prazo_contratual_semanas"),
    )

    sweep = []
    for s in cfg.get("sweep") or []:
        sweep.append(ParametroSweep(campo=s["campo"], valores=s["valores"]))

    return GoResearchCampaignBundle(
        base_spec=base_spec,
        sweep=sweep,
        perfil_expectativas=perfil,
        top_k=cfg.get("top_k", 5),
        campaign_version=cfg.get("campaign_version", "v1"),
    )


def _objetivo_label(c: CenarioAvaliado) -> str:
    """Extract objetivo from parametros_variados (handles dict or simple values)."""
    for val in c.parametros_variados.values():
        if isinstance(val, dict) and "objetivo" in val:
            return val["objetivo"]
        if isinstance(val, str):
            return val
    return str(list(c.parametros_variados.values())[0]) if c.parametros_variados else "-"


def _fmt_pct(v: float | None) -> str:
    return f"{v * 100:.1f}%" if v is not None else "-"


def _fmt_semanas(v: int | float | None, suffix: str = "s") -> str:
    return f"{v}{suffix}" if v is not None else "-"


def _fmt_fe(v: float | None) -> str:
    return f"{v:.3f}" if v is not None else "-"


def _pareto_mark(flag: bool) -> str:
    return "✓" if flag else " "


def _status_mark(viabilidade: str) -> str:
    return "✅" if viabilidade in {"APROVADO", "APROVADO_COM_RESSALVAS"} else "❌"


def print_summary(result: CampaignOutputBundle) -> None:
    n = result.n_cenarios_avaliados
    print(f"\n=== AGIS Campaign {result.campaign_version} — {n} cenário(s) ===")
    print()

    # Header
    col_w = [12, 20, 8, 8, 8, 6, 10, 10]
    headers = ["ID", "Objetivo Pool", "Prazo", "fe_nec", "Margem", "Status", "Pareto-O", "Pareto-EF"]

    def _row(*cells):
        parts = []
        for cell, w in zip(cells, col_w):
            parts.append(str(cell).ljust(w))
        print("| " + " | ".join(parts) + " |")

    sep = "+-" + "-+-".join("-" * w for w in col_w) + "-+"
    print(sep)
    _row(*headers)
    print(sep)

    sorted_cenarios = sorted(
        result.cenarios,
        key=lambda c: (c.rank_final or 9999, c.cenario_id),
    )

    for c in sorted_cenarios:
        _row(
            c.cenario_id[:12],
            _objetivo_label(c)[:20],
            _fmt_semanas(c.vetor_O.prazo_semanas),
            _fmt_fe(c.vetor_O.fe_nec_medio),
            _fmt_pct(c.vetor_EF.margem_pct),
            _status_mark(c.viabilidade),
            _pareto_mark(c.pareto_O),
            _pareto_mark(c.pareto_EF),
        )
        if c.erro:
            print(f"|   ERRO: {c.erro[:70]}")

    print(sep)
    print()

    if result.shortlist:
        print(f"=== Shortlist Top-{len(result.shortlist)} ===")
        for ranked in result.shortlist:
            c = ranked.cenario
            j = ranked.justificativa
            destaque_O = " · ".join(j.destaques_O[:2]) if j.destaques_O else ""
            destaque_EF = " · ".join(j.destaques_EF[:1]) if j.destaques_EF else ""
            all_destaques = " · ".join(filter(None, [destaque_EF, destaque_O]))
            alertas = f"  [ALERTA: {'; '.join(j.alertas)}]" if j.alertas else ""
            print(f"#{ranked.rank} {c.cenario_id} ({j.motivo_inclusao}): {all_destaques}{alertas}")
        print()

    print(f"Bundle status: {result.status}")
    print(
        f"Avaliados: {result.n_cenarios_avaliados} | "
        f"Viaveis: {result.n_cenarios_viaveis} | "
        f"Falhas: {result.n_falhas}"
    )


def main() -> None:
    ref_path = DATA_DIR / "referencia.json"
    cfg_path = DATA_DIR / "campaign_v1.json"

    if not ref_path.exists():
        print(f"ERRO: referencia.json nao encontrado em {ref_path}", file=sys.stderr)
        sys.exit(1)
    if not cfg_path.exists():
        print(f"ERRO: campaign_v1.json nao encontrado em {cfg_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Carregando referencia: {ref_path}")
    base_spec = json.loads(ref_path.read_text(encoding="utf-8"))

    print(f"[INFO] Carregando config: {cfg_path}")
    cfg = _load_campaign_config(cfg_path)
    print(f"[INFO] Descricao: {cfg.get('descricao', '-')}")

    bundle = _build_bundle(base_spec, cfg)
    print(f"[INFO] Campaign ID: {bundle.campaign_id}")
    print(f"[INFO] Grid: {sum(len(s.valores) for s in bundle.sweep)} variantes (produto cartesiano)")
    print(f"[INFO] Iniciando campanha com {len(bundle.sweep)} parametro(s) de sweep...")
    print()

    result = executar_campanha(
        bundle,
        config_root=CONFIG_ROOT,
        projects_root=PROJECTS_ROOT,
        num_workers=3,
        reset=False,  # use existing canonical if available
    )

    print_summary(result)


if __name__ == "__main__":
    main()
