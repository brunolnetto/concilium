#!/usr/bin/env python3
"""ADR-076 Impact Analysis — AGIS Benchmark.

Carrega o canonical v13 do projeto AGIS, re-executa o cálculo de
ponto_equilibrio com os novos campos ADR-076, e decompõe a "lesão de
produtividade" por componente (escala de equipes, clima, pool overhead).

Uso:
    cd concilium
    python -c "import sys; sys.path.insert(0, 'src')" && \
        python benchmarks/analysis/adr076_agis_impact.py
    # ou simplesmente:
    python benchmarks/analysis/adr076_agis_impact.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Garante que o código fonte WSL tem prioridade
_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from concilium.domain.models.canonical import CanonicalModel

def _find_agis_canonical() -> Path:
    """Encontra o canonical.json mais recente do benchmark AGIS base (sem [cenario])."""
    import json as _json
    projetos_dir = _ROOT / "benchmarks" / "projetos"
    if not projetos_dir.exists():
        raise FileNotFoundError(f"Diretório projetos não encontrado: {projetos_dir}")
    candidates = []
    for proj_dir in projetos_dir.iterdir():
        meta_path = proj_dir / "meta.json"
        if not meta_path.exists():
            continue
        meta = _json.loads(meta_path.read_text(encoding="utf-8"))
        nome = meta.get("nome", "")
        if "AGIS" in nome and not nome.endswith("]") and "[" not in nome:
            version = meta.get("current_version", "v1")
            canonical = proj_dir / version / "canonical.json"
            if canonical.exists():
                candidates.append((canonical.stat().st_mtime, canonical))
    if not candidates:
        raise FileNotFoundError("Nenhum canonical AGIS base encontrado em benchmarks/projetos/")
    candidates.sort(reverse=True)
    return candidates[0][1]

CANONICAL_PATH = _find_agis_canonical()

SEMANAS_POR_MES = 4.333333


# ── Carrega canonical ──────────────────────────────────────────────────────

def load_canonical(path: Path) -> CanonicalModel:
    with open(path, encoding="utf-8") as f:
        return CanonicalModel.model_validate(json.load(f))


# ── Fatores de lesão climática da distribuição semanal ────────────────────

def _lesao_semanal(canonical: CanonicalModel) -> dict[str, dict]:
    """Extrai médias ponderadas de fator_clima, fator_calendario, fator_total por item."""
    result: dict[str, dict] = {}
    if not canonical.cronograma:
        return result
    for sa in canonical.cronograma.scheduled_activities:
        dist = sa.distribuicao_semanal or {}
        if not dist:
            continue
        total_equipes = 0
        soma_clima = soma_cal = soma_total = 0.0
        semanas_lesadas_clima = 0
        for d in dist.values():
            ne = d.num_equipes
            total_equipes += ne
            soma_clima  += d.fator_clima     * ne
            soma_cal    += d.fator_calendario * ne
            soma_total  += d.fator_total     * ne
            if d.fator_clima < 0.90:
                semanas_lesadas_clima += 1
        if total_equipes > 0:
            result[sa.activity_id] = {
                "active_weeks": sum(1 for d in dist.values() if d.num_equipes > 0),
                "team_weeks": total_equipes,
                "fator_clima_medio":      round(soma_clima  / total_equipes, 4),
                "fator_calendario_medio": round(soma_cal    / total_equipes, 4),
                "fator_total_medio":      round(soma_total  / total_equipes, 4),
                "semanas_lesadas_clima":  semanas_lesadas_clima,
            }
    return result


# ── Cálculo ADR-076 por equipe ─────────────────────────────────────────────

def _adr076_por_equipe(canonical: CanonicalModel, lesao_semanal: dict) -> list[dict]:
    """Calcula os campos ADR-076 + decomposição de lesão para cada equipe."""
    plan_by_item = {p.item_id: p for p in canonical.planejamento if p.item_id}
    rows = []
    for eq in canonical.equipes_diretas:
        if not eq.item_id:
            continue

        perm_efetiva = float(eq.permanencia_efetiva_meses or 0.0)
        perm_nominal = float(eq.permanencia_meses or 0.0)
        custo_fixo_total = eq.custo_fixo_mensal * perm_efetiva
        if custo_fixo_total <= 0:
            continue

        custo_op_real     = float(eq.custo_total or 0.0)
        custo_autonomo    = float(eq.custo_total_autonomo or 0.0)

        plan = plan_by_item.get(eq.item_id)
        Q            = float(plan.quantitativo) if plan else 0.0
        venda_sem_bdi = float(
            plan.subtotal.sem_bdi.total
            if plan and plan.subtotal and plan.subtotal.sem_bdi
            else 0.0
        )
        venda_com_bdi = float(
            plan.subtotal.com_bdi.total
            if plan and plan.subtotal and plan.subtotal.com_bdi
            else 0.0
        )

        # ADR-076 Opção C
        frentes_nec = (
            round(custo_autonomo / venda_sem_bdi, 4) if venda_sem_bdi > 0 and custo_autonomo > 0
            else round(custo_op_real / venda_com_bdi, 4) if venda_com_bdi > 0 else 1.0
        )
        gap_pool = round(custo_op_real - custo_autonomo, 2)

        # ADR-076 Opção D
        pu_cat = round(venda_sem_bdi / Q, 4)     if Q > 0 else 0.0
        pu_aut = round(custo_autonomo / Q, 4)    if Q > 0 else 0.0
        pu_cal = max(pu_cat, pu_aut)
        ajuste = round((pu_cal - pu_cat) / pu_cat * 100, 2) if pu_cat > 0 else 0.0

        # Lesão por escala de equipes
        # custo_base_catalogo = 1 equipe × custo_fixo_mensal × permanencia_nominal
        custo_base_cat = eq.custo_fixo_mensal * perm_nominal
        gap_escala_abs = round(custo_autonomo - custo_base_cat, 2)  # efeito equipes + praticab.

        # Ratio de escala = custo_autonomo / custo_base_cat (quantas vezes maior)
        ratio_escala = round(custo_autonomo / custo_base_cat, 3) if custo_base_cat > 0 else 1.0

        # Número efetivo de equipes = team_weeks / active_weeks
        les = lesao_semanal.get(eq.item_id, {})
        active_weeks = les.get("active_weeks", 0)
        team_weeks   = les.get("team_weeks",   0)
        n_equipes_efetivo = round(team_weeks / active_weeks, 2) if active_weeks > 0 else 1.0
        fator_clima       = les.get("fator_clima_medio",      1.0)
        fator_calendario  = les.get("fator_calendario_medio", 1.0)
        fator_total       = les.get("fator_total_medio",      1.0)
        semanas_clima     = les.get("semanas_lesadas_clima",  0)

        # Decomposição da lesão sobre custo_autonomo (vs base_catalogo)
        # 1. Lesão de escala pura: N equipes implicam N× mais team-months
        gap_escala_equipes = round(custo_base_cat * (n_equipes_efetivo - 1.0), 2)
        # 2. Lesão de praticabilidade (custo adicional = custo_autonomo - base_cat × N_equipes)
        gap_praticabilidade = round(gap_escala_abs - gap_escala_equipes, 2)

        status_frentes = (
            "OK" if frentes_nec <= 1.25
            else "AVISO" if frentes_nec <= 1.50
            else "CRITICO"
        )

        rows.append({
            "item_id":             eq.item_id,
            "cpu_id":              eq.cpu_id,
            "contrato_tipo_id":    eq.contrato_tipo_id,
            "n_equipes_efetivo":   n_equipes_efetivo,
            "active_weeks":        active_weeks,
            "perm_nominal_m":      round(perm_nominal,  3),
            "perm_efetiva_m":      round(perm_efetiva,  3),
            "custo_base_catalogo": round(custo_base_cat, 2),
            "custo_autonomo":      round(custo_autonomo, 2),
            "custo_op_real":       round(custo_op_real, 2),
            "gap_escala_equipes":  gap_escala_equipes,
            "gap_praticabilidade": gap_praticabilidade,
            "gap_pool":            gap_pool,
            "frentes_nec":         frentes_nec,
            "status_frentes":      status_frentes,
            "pu_cat":              pu_cat,
            "pu_calibrado":        round(pu_cal, 4),
            "ajuste_minimo_pct":   ajuste,
            "fator_clima_medio":   fator_clima,
            "fator_calendario_medio": fator_calendario,
            "fator_total_medio":   fator_total,
            "semanas_lesadas_clima": semanas_clima,
        })
    return rows


# ── Impressão ──────────────────────────────────────────────────────────────

def _brl(v: float) -> str:
    return f"R$ {v:>14,.2f}"

def _pct(v: float) -> str:
    return f"{v:>+7.2f}%"


def print_report(rows: list[dict]) -> None:
    print()
    print("=" * 100, flush=True)
    print("  ADR-076  IMPACTO NO BENCHMARK AGIS — Decomposição de Lesão de Produtividade")
    print("=" * 100, flush=True)

    # ── Tabela de Frentes e PU Calibrado ──────────────────────────────────
    print()
    print("-" * 100)
    print(f"  {'Item':<10} {'CPU':<40} {'Frentes Nec.':>13} {'Status':>8} "
          f"{'PU Cat.':>10} {'PU Calib.':>10} {'Ajuste':>8}")
    print("-" * 100)
    for r in rows:
        print(
            f"  {r['item_id']:<10} {r['cpu_id'][:39]:<40} "
            f"{r['frentes_nec']:>13.4f} {r['status_frentes']:>8} "
            f"{r['pu_cat']:>10.4f} {r['pu_calibrado']:>10.4f} {r['ajuste_minimo_pct']:>+7.1f}%"
        )

    # ── Tabela de Decomposição da Lesão ───────────────────────────────────
    print()
    print("-" * 100)
    print("  Decomposição da Lesão de Custo (vs Base Catálogo 1-equipe × perm.nominal)")
    print("-" * 100)
    print(f"  {'Item':<10} {'Nº Eq':>5} {'Sem.':>5} {'Base Cat.':>16} "
          f"{'Gap Escala':>16} {'Gap Praticab.':>14} {'Gap Pool':>14} {'Total Autônomo':>16}")
    print("-" * 100)
    tot_base = tot_esc = tot_prat = tot_pool = tot_aut = 0.0
    for r in rows:
        tot_base += r["custo_base_catalogo"]
        tot_esc  += r["gap_escala_equipes"]
        tot_prat += r["gap_praticabilidade"]
        tot_pool += r["gap_pool"]
        tot_aut  += r["custo_autonomo"]
        print(
            f"  {r['item_id']:<10} {r['n_equipes_efetivo']:>5.1f} "
            f"{r['active_weeks']:>5} "
            f"{_brl(r['custo_base_catalogo'])} "
            f"{_brl(r['gap_escala_equipes'])} "
            f"{_brl(r['gap_praticabilidade'])} "
            f"{_brl(r['gap_pool'])} "
            f"{_brl(r['custo_autonomo'])}"
        )
    print("-" * 100)
    print(
        f"  {'TOTAL':<10} {'':>5} {'':>5} "
        f"{_brl(tot_base)} "
        f"{_brl(tot_esc)} "
        f"{_brl(tot_prat)} "
        f"{_brl(tot_pool)} "
        f"{_brl(tot_aut)}"
    )
    gap_total = tot_aut - tot_base
    if tot_base > 0:
        print(
            f"\n  Gap total sobre catálogo: {_brl(gap_total)} "
            f"({gap_total/tot_base*100:+.1f}%)"
        )
        print(
            f"  → Lesão por escala de equipes: {_brl(tot_esc)} ({tot_esc/gap_total*100:.1f}% do gap)"
        )
        print(
            f"  → Lesão por praticabilidade:   {_brl(tot_prat)} ({tot_prat/gap_total*100:.1f}% do gap)"
        )
        print(
            f"  → Overhead de pool:            {_brl(tot_pool)} (sobre custo autônomo)"
        )

    # ── Tabela de Fatores Climáticos ──────────────────────────────────────
    print()
    print("-" * 100)
    print("  Fatores de Praticabilidade Climática (médias ponderadas por equipe×semana)")
    print("-" * 100)
    print(f"  {'Item':<10} {'Nº Eq':>5} {'Sem. Ativas':>12} {'Sem. Lesadas':>14} "
          f"{'f_clima':>9} {'f_cal':>9} {'f_total':>9}")
    print("-" * 100)
    for r in rows:
        lesao_clima_pct = (1 - r["fator_clima_medio"]) * 100
        print(
            f"  {r['item_id']:<10} {r['n_equipes_efetivo']:>5.1f} "
            f"{r['active_weeks']:>12} "
            f"{r['semanas_lesadas_clima']:>14} "
            f"  {r['fator_clima_medio']:.4f} "
            f"  {r['fator_calendario_medio']:.4f} "
            f"  {r['fator_total_medio']:.4f}"
            + (f"  ← {lesao_clima_pct:.1f}% lesão" if lesao_clima_pct > 0.5 else "")
        )

    print()
    print("=" * 100, flush=True)


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"Carregando {CANONICAL_PATH} ...")
    canonical = load_canonical(CANONICAL_PATH)
    print(f"OK — {len(canonical.equipes_diretas)} equipes, {len(canonical.planejamento)} itens de planejamento")

    lesao_semanal = _lesao_semanal(canonical)
    rows = _adr076_por_equipe(canonical, lesao_semanal)
    print_report(rows)


if __name__ == "__main__":
    main()
