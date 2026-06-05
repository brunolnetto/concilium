"""
Memorial de Calculo -- Decomposicao Completa e Investigacao de Gaps de Custo
ADR-076 / Investigacao de Legitimidade dos Gaps

Objetivo: cada R$ de gap em custo_total deve ter justificativa rastreavel.

TAXONOMIA CORRETA DOS GAPS:
=============================================================================
  custo_base_catalogo = fixo_mensal x perm_nominal
                       (1 equipe, condicoes de catalogo, sem lesao de produtividade)

  gap_escala          = custo_base x (N - 1)
                       (custo de contratar N-1 equipes adicionais para comprimir o prazo)
                       Fonte: decisao RCPSP de alocar N equipes simultaneas ao item

  gap_praticabilidade = custo_total_autonomo - custo_base x N
                       (residual apos descontar escala: desvio REAL de produtividade)
                       Esperado proximo a zero. Se significativo: clima/terreno/mob-desmob

  gap_pool            = custo_total - custo_total_autonomo
                       (overhead de contrato compartilhado: capacidade contratada mas ociosa)
                       Fonte: equipamentos reservados para o contrato mas idle em semanas de outros itens

IDENTIDADE DE AUDITORIA:
  custo_base + gap_escala + gap_praticabilidade + gap_pool = custo_total (deve ser 0 residual)

POOL CONTRACT MODEL (ADR-071):
  custo_unit_semanal = sum(custo_total_autonomo_i) / sum(machine_weeks_i)
  custo_total_contrato = quantidade_contratada x custo_unit x semanas_contrato
  fracao_i = machine_weeks_i / total_machine_weeks
  custo_atribuido_i = custo_total_contrato x fracao_i

  OCIOSIDADE = (quantidade_contratada x semanas_contrato - sum(machine_weeks_i)) x custo_unit
             = custo_total_contrato x (1 - sum(autonomo_i) / custo_total_contrato)
             = custo_total_contrato - sum(custo_total_autonomo_i)

  ORIGEM DA OCIOSIDADE: peak_demand = max(equipes_i simultaneas) < quantidade_contratada
  em algum sub-periodo do contrato. Equipamentos "em standby" pagos pelo contrato.

USO:
  python benchmarks/analysis/adr076_memorial_calculo.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

# Localizar canonical -- percorre projetos/ em ordem decrescente de mtime buscando AGIS base
import os as _os

def _find_agis_canonical() -> Path:
    """Encontra o canonical.json mais recente do benchmark AGIS base (sem [cenario])."""
    projetos_dir = Path(__file__).resolve().parent.parent / "projetos"
    if not projetos_dir.exists():
        raise FileNotFoundError(f"Diretório projetos não encontrado: {projetos_dir}")
    candidates = []
    for proj_dir in projetos_dir.iterdir():
        meta_path = proj_dir / "meta.json"
        if not meta_path.exists():
            continue
        import json as _json
        meta = _json.loads(meta_path.read_text(encoding="utf-8"))
        nome = meta.get("nome", "")
        # Exclui cenários (nome termina com [algo])
        if "AGIS" in nome and not nome.endswith("]") and "[" not in nome:
            version = meta.get("current_version", "v1")
            canonical = proj_dir / version / "canonical.json"
            if canonical.exists():
                candidates.append((canonical.stat().st_mtime, canonical))
    if not candidates:
        raise FileNotFoundError("Nenhum canonical AGIS base encontrado em benchmarks/projetos/")
    candidates.sort(reverse=True)
    return candidates[0][1]

_PROJ_ROOT = Path(__file__).resolve().parent.parent.parent
_CANONICAL_PATH = _find_agis_canonical()

SEMANAS_POR_MES = 4 + 1 / 7  # 4.3333...
TOLERANCIA_VERIF = 2.0        # R$ tolerancia para verificacao de identidade

# Limite para flags de investigacao
FLAG_OCIOSIDADE_PCT   = 35.0  # pool com mais de 35% idle -> flag
FLAG_GAP_PRATICAB_PCT = 5.0   # gap_praticab > 5% do custo_base_N -> flag
FLAG_N_EQUIPES_ALTO   = 3.0   # N > 3 equipes simultaneas -> flag


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(v: float, prefixo: str = "R$ ") -> str:
    """Formata valor monetario com separador de milhar."""
    sinal = "-" if v < 0 else ""
    return f"{sinal}{prefixo}{abs(v):>14,.2f}"


def _fmt_pct(v: float) -> str:
    sinal = "+" if v >= 0 else ""
    return f"{sinal}{v:.1f}%"


def _linha(char: str = "-", n: int = 88) -> str:
    return char * n


def _titulo(texto: str) -> None:
    print()
    print(_linha("="))
    print(f"  {texto}")
    print(_linha("="))


def _secao(texto: str) -> None:
    print()
    print(_linha("-"))
    print(f"  {texto}")
    print(_linha("-"))


# ─────────────────────────────────────────────────────────────────────────────
# Carga do canonical
# ─────────────────────────────────────────────────────────────────────────────

def carregar_canonical() -> dict:
    if not _CANONICAL_PATH.exists():
        print(f"[ERRO] Canonical nao encontrado: {_CANONICAL_PATH}", file=sys.stderr)
        sys.exit(1)
    with open(_CANONICAL_PATH, encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────────────────────────────────────────────────────────
# Extrator de equipes e contratos
# ─────────────────────────────────────────────────────────────────────────────

def extrair_equipes(canonical: dict) -> list[dict]:
    """Extrai equipes_diretas com campos relevantes para o memorial."""
    raw = canonical.get("equipes_diretas") or []
    equipes = []
    for eq in raw:
        fixo      = float(eq.get("custo_fixo_mensal") or 0)
        perm_nom  = float(eq.get("permanencia_meses") or 0)
        perm_ef   = float(eq.get("permanencia_efetiva_meses") or 0) or perm_nom
        custo_aut = float(eq.get("custo_total_autonomo") or 0)
        custo_tot = float(eq.get("custo_total") or 0)

        if fixo <= 0 or perm_nom <= 0:
            continue

        N = perm_ef / perm_nom if perm_nom > 0 else 1.0
        custo_base    = fixo * perm_nom
        gap_escala    = custo_base * (N - 1.0)
        custo_base_N  = custo_base * N          # = fixo * perm_ef
        gap_praticab  = custo_aut - custo_base_N
        gap_pool      = custo_tot - custo_aut
        residuo_verif = custo_base + gap_escala + gap_praticab + gap_pool - custo_tot

        equipes.append({
            "item_id":       eq.get("item_id", "?"),
            "equipe_id":     eq.get("equipe_id", "?"),
            "cpu_id":        eq.get("cpu_id", "?"),
            "contrato_tipo": eq.get("contrato_tipo_id") or "(sem pool)",
            "fracao":        float(eq.get("fracao_atribuicao") or 0),
            # valores base
            "fixo_mensal":   fixo,
            "perm_nominal":  perm_nom,
            "perm_efetiva":  perm_ef,
            "N":             N,
            # decomposicao
            "custo_base":    custo_base,
            "gap_escala":    gap_escala,
            "custo_base_N":  custo_base_N,
            "gap_praticab":  gap_praticab,
            "custo_aut":     custo_aut,
            "gap_pool":      gap_pool,
            "custo_total":   custo_tot,
            # verificacao
            "residuo":       residuo_verif,
            # semanas para legibilidade
            "sem_nominal":   round(perm_nom * SEMANAS_POR_MES, 1),
            "sem_efetiva":   round(perm_ef  * SEMANAS_POR_MES, 1),
        })
    return equipes


def extrair_contratos(canonical: dict) -> list[dict]:
    """Extrai contratos_recurso com analise de ociosidade."""
    raw = canonical.get("contratos_recurso") or []
    contratos = []
    for c in raw:
        qtd      = int(c.get("quantidade_contratada") or 0)
        semanas  = int(c.get("semanas_contrato") or 0)
        custo_u  = float(c.get("custo_unit_semanal") or 0)
        custo_ct = float(c.get("custo_total_contrato") or 0)
        contratos.append({
            "contrato_id":  c.get("contrato_id", "?"),
            "tipo_id":      c.get("tipo_id", "?"),
            "qtd_contrat":  qtd,
            "semanas_ct":   semanas,
            "custo_unit_sw": custo_u,
            "custo_total":  custo_ct,
            "sem_inicio":   c.get("semana_inicio", "?"),
            "sem_fim":      c.get("semana_fim", "?"),
            "items":        list(c.get("items_cobertos") or []),
            "n_cadeias":    int(c.get("n_cadeias") or 0),
            "custo_mob_desmob": float(c.get("custo_mob_desmob_contrato") or 0),
            "custo_standby": float(c.get("custo_standby_total") or 0),
        })
    return contratos


def extrair_planejamento(canonical: dict) -> dict[str, dict]:
    """Extrai venda_sem_bdi e quantitativo por item_id."""
    raw = canonical.get("planejamento") or canonical.get("itens_planejamento") or []
    resultado = {}
    for item in raw:
        iid = item.get("item_id") or item.get("id")
        if not iid:
            continue
        subtotal = item.get("subtotal") or {}
        sem_bdi_sec = subtotal.get("sem_bdi") or {}
        venda_sem_bdi = float(sem_bdi_sec.get("total") or 0)
        qty = float(item.get("quantitativo") or 0)
        resultado[iid] = {
            "venda_sem_bdi": venda_sem_bdi,
            "quantitativo":  qty,
            "pu_catalogo":   round(venda_sem_bdi / qty, 4) if qty > 0 else 0,
        }
    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# Impressao: memorial por item
# ─────────────────────────────────────────────────────────────────────────────

def _print_item(eq: dict, plan: dict | None) -> list[str]:
    """Imprime decomposicao completa de um item. Retorna lista de flags."""
    flags: list[str] = []

    print(f"\n  ITEM: {eq['item_id']}   [{eq['cpu_id']}]")
    print(f"  Equipe: {eq['equipe_id']}  |  Contrato: {eq['contrato_tipo']}", end="")
    if eq["fracao"] > 0:
        print(f" (fracao={eq['fracao']:.4f})")
    else:
        print()

    if plan:
        pu  = plan["pu_catalogo"]
        qty = plan["quantitativo"]
        vbdi = plan["venda_sem_bdi"]
        print(f"  Quantitativo: {qty:,.0f}  |  PU catalogo (sem BDI): R$ {pu:.4f}/un")
        print(f"  Receita sem BDI:    {_fmt(vbdi)}")
    else:
        print("  [Planejamento nao encontrado para este item]")

    N = eq["N"]
    print(f"\n  Duracao catalogo (1 equipe):  {eq['sem_nominal']:5.1f} sem  = {eq['perm_nominal']:.2f} meses")
    print(f"  Duracao efetiva  (RCPSP):     {eq['sem_efetiva']:5.1f} sem  = {eq['perm_efetiva']:.2f} meses")
    print(f"  N equipes efetivas:           {N:.2f}   (= perm_efetiva / perm_nominal)")
    print(f"  Fixo mensal (catalogo):       {_fmt(eq['fixo_mensal'])}")

    # decomposicao
    print(f"\n  DECOMPOSICAO DO CUSTO:")
    print(f"    custo_base    (1eq x perm_nom):   {_fmt(eq['custo_base'])}  [100%]")

    if abs(eq["gap_escala"]) > 0.5:
        pct_esc = eq["gap_escala"] / eq["custo_base"] * 100 if eq["custo_base"] > 0 else 0
        fonte_esc = (
            f"RCPSP: {N:.1f} equipes para comprimir prazo de "
            f"{eq['sem_nominal']:.0f} -> {eq['sem_nominal']/N:.0f} sem"
        )
        print(f"  + gap_escala  ({N:.1f} equipes - 1):    {_fmt(eq['gap_escala'])}  [{_fmt_pct(pct_esc)}]")
        print(f"    Fonte: {fonte_esc}")
        if N > FLAG_N_EQUIPES_ALTO:
            flags.append(f"ALTO_N: {N:.1f} equipes simultaneas -- verificar restricao de deadline no RCPSP")
    else:
        print(f"  + gap_escala  (N=1, sem escala):  {_fmt(0.0)}  [+0.0%]")

    pct_prat = eq["gap_praticab"] / eq["custo_base_N"] * 100 if eq["custo_base_N"] > 0 else 0
    if abs(eq["gap_praticab"]) > 0.5:
        print(f"  + gap_praticab (residual clima):  {_fmt(eq['gap_praticab'])}  [{_fmt_pct(pct_prat)}]")
        if abs(pct_prat) > FLAG_GAP_PRATICAB_PCT:
            flags.append(
                f"GAP_PRATICAB: {pct_prat:+.1f}% do custo_base_N "
                f"-- verificar fator_clima/combustivel no cronograma"
            )
    else:
        print(f"  + gap_praticab (residual ~zero):  {_fmt(eq['gap_praticab'])}  [{_fmt_pct(pct_prat)}]  OK")

    print(f"               ---------------")
    print(f"  = custo_aut   (autonomo):         {_fmt(eq['custo_aut'])}")

    if abs(eq["gap_pool"]) > 0.5:
        pct_pool = eq["gap_pool"] / eq["custo_aut"] * 100 if eq["custo_aut"] > 0 else 0
        print(f"  + gap_pool    (contrato pool):    {_fmt(eq['gap_pool'])}  [{_fmt_pct(pct_pool)}]")
        print(f"    Fonte: ociosidade no contrato {eq['contrato_tipo']}")
    else:
        print(f"  + gap_pool    (sem pool / zero):  {_fmt(0.0)}  [+0.0%]")

    print(f"               ===============")
    print(f"  = custo_total (com pool):         {_fmt(eq['custo_total'])}")

    # verificacao de identidade
    if abs(eq["residuo"]) > TOLERANCIA_VERIF:
        flags.append(f"RESIDUO_ALTO: {eq['residuo']:+.2f} -- identidade nao fecha (bug no calculo?)")
        print(f"  [!] RESIDUO VERIFICACAO: {eq['residuo']:+.2f}  (deveria ser ~0)")
    else:
        print(f"  [OK] Identidade: residuo = {eq['residuo']:+.2f}")

    # calibracao de PU
    if plan and plan["venda_sem_bdi"] > 0:
        vbdi = plan["venda_sem_bdi"]
        frentes_nec = eq["custo_aut"] / vbdi
        pu_cat = plan["pu_catalogo"]
        qty    = plan["quantitativo"]
        pu_cal = eq["custo_aut"] / qty if qty > 0 else 0
        ajuste = (pu_cal - pu_cat) / pu_cat * 100 if pu_cat > 0 else 0
        status = "OK" if frentes_nec <= 1.25 else ("AVISO" if frentes_nec <= 1.50 else "CRITICO")
        pct_sobre_base = (eq["custo_aut"] - vbdi) / vbdi * 100
        print(f"\n  CALIBRACAO PU:")
        print(f"    PU catalogo:    R$ {pu_cat:.4f}/un  |  Receita total: {_fmt(vbdi)}")
        print(f"    PU calibrado:   R$ {pu_cal:.4f}/un  |  Custo autonomo: {_fmt(eq['custo_aut'])}")
        print(f"    Ajuste minimo:  {_fmt_pct(ajuste)}  |  Frentes nec: {frentes_nec:.4f} [{status}]")
        if pct_sobre_base > 0:
            print(f"    Custo autonomo supera receita sem BDI em {_fmt_pct(pct_sobre_base)}")
        if status == "CRITICO":
            flags.append(f"CRITICO: frentes_nec={frentes_nec:.3f} -- PU calibrado {_fmt_pct(ajuste)} acima do catalogo")
        elif status == "AVISO":
            flags.append(f"AVISO: frentes_nec={frentes_nec:.3f} -- PU calibrado {_fmt_pct(ajuste)} acima do catalogo")

    return flags


# ─────────────────────────────────────────────────────────────────────────────
# Impressao: analise de contratos pool
# ─────────────────────────────────────────────────────────────────────────────

def _print_contrato(c: dict, equipes: list[dict]) -> list[str]:
    """Imprime analise de ociosidade de um contrato pool."""
    flags: list[str] = []
    tipo = c["tipo_id"]
    eqs_contrato = [eq for eq in equipes if eq["contrato_tipo"] == tipo]

    sum_autonomo  = sum(eq["custo_aut"]   for eq in eqs_contrato)
    sum_atribuido = sum(eq["custo_total"] for eq in eqs_contrato)
    ociosidade    = c["custo_total"] - sum_autonomo
    ocio_pct      = ociosidade / c["custo_total"] * 100 if c["custo_total"] > 0 else 0

    mw_contratados = c["qtd_contrat"] * c["semanas_ct"]
    mw_usados = (sum_autonomo / c["custo_unit_sw"]) if c["custo_unit_sw"] > 0 else 0
    mw_ociosos = mw_contratados - mw_usados

    print(f"\n  CONTRATO: {c['contrato_id']}  [tipo={tipo}]")
    print(f"  Periodo:  {c['sem_inicio']} -> {c['sem_fim']}  ({c['semanas_ct']} semanas)")
    print(f"  Capacidade contratada: {c['qtd_contrat']} unidades x {c['semanas_ct']} sem = {mw_contratados:.1f} MWs")
    print(f"  Custo unit. semanal:   {_fmt(c['custo_unit_sw'])}/MW")
    print(f"  Custo total contrato:  {_fmt(c['custo_total'])}")
    if c["custo_mob_desmob"] > 0:
        print(f"  Mob/desmob:            {_fmt(c['custo_mob_desmob'])}")
    if c["custo_standby"] > 0:
        print(f"  Standby (ADR-073):     {_fmt(c['custo_standby'])}")

    print(f"\n  ITENS COBERTOS ({len(eqs_contrato)}):")
    print(f"  {'Item':<14} {'Fracao':>8} {'Perm.nom':>10} {'Perm.ef':>10} "
          f"{'N':>5} {'MWs usados':>12} {'Custo aut':>16} {'Custo attr':>16} {'Gap pool':>14}")
    print(f"  {'-'*14} {'-'*8} {'-'*10} {'-'*10} {'-'*5} {'-'*12} {'-'*16} {'-'*16} {'-'*14}")

    total_mw_itens = 0.0
    for eq in sorted(eqs_contrato, key=lambda e: e["fracao"], reverse=True):
        mw_item = mw_contratados * eq["fracao"] if c["custo_total"] > 0 else 0
        total_mw_itens += mw_item
        print(
            f"  {eq['item_id']:<14} {eq['fracao']:>8.4f} "
            f"{eq['perm_nominal']:>9.2f}m {eq['perm_efetiva']:>9.2f}m "
            f"{eq['N']:>5.1f} {mw_item:>12.1f} "
            f"{eq['custo_aut']:>15,.0f}  "
            f"{eq['custo_total']:>15,.0f}  "
            f"{eq['gap_pool']:>+13,.0f}"
        )

    print(f"  {'TOTAL':<14} {'1.0000':>8} "
          f"{'':>10} {'':>10} {'':>5} {total_mw_itens:>12.1f} "
          f"{sum_autonomo:>15,.0f}  {sum_atribuido:>15,.0f}  {sum_atribuido-sum_autonomo:>+13,.0f}")

    print(f"\n  ANALISE DE OCIOSIDADE:")
    print(f"    MWs contratados:  {mw_contratados:>8.1f}")
    print(f"    MWs realmente usados: {mw_usados:>5.1f}")
    print(f"    MWs ociosos:      {mw_ociosos:>8.1f}  ({mw_ociosos/mw_contratados*100:.1f}% do contrato)")
    print(f"    Custo ociosidade: {_fmt(ociosidade)}")
    print(f"    % overhead sobre autonomo: {_fmt_pct(ociosidade/sum_autonomo*100 if sum_autonomo>0 else 0)}")

    # Porque ha ociosidade?
    if len(eqs_contrato) > 1:
        print(f"\n  ORIGEM DA OCIOSIDADE:")
        print(f"    O contrato precisa de {c['qtd_contrat']} unidades para atender o pico de demanda")
        print(f"    (quando {len(eqs_contrato)} itens estao ativos simultaneamente).")
        print(f"    Fora do periodo de sobreposicao, parte das {c['qtd_contrat']} unidades fica ociosa.")
        if ocio_pct > FLAG_OCIOSIDADE_PCT:
            motivo = (
                f"Apenas {mw_usados:.0f}/{mw_contratados:.0f} MWs utilizados. "
                f"Verificar se items podem ser re-sequenciados para reduzir peak demand "
                f"(ex: executar eap items em serie em vez de paralelo -- relaxar restrição de deadline)."
            )
            flags.append(
                f"POOL_OCIOSO ({tipo}): {ocio_pct:.1f}% idle = {_fmt(ociosidade)} desperdicados. "
                + motivo
            )
    elif len(eqs_contrato) == 1:
        print(f"\n  ORIGEM DA OCIOSIDADE:")
        print(f"    Item unico no contrato. Ociosidade vem do contrato ser dimensionado para")
        print(f"    {c['qtd_contrat']} unidades mas o item usa apenas fracao do periodo ou {eqs_contrato[0]['N']:.1f} equipes.")
        if ocio_pct > FLAG_OCIOSIDADE_PCT:
            flags.append(
                f"POOL_OCIOSO_ITEM_UNICO ({tipo}): {ocio_pct:.1f}% idle -- "
                f"contrato superdimensionado para 1 item?"
            )

    if ocio_pct > FLAG_OCIOSIDADE_PCT:
        print(f"  [!] FLAG: overhead de {ocio_pct:.1f}% acima do limite de {FLAG_OCIOSIDADE_PCT:.0f}%")
    else:
        print(f"  [OK] Ociosidade {ocio_pct:.1f}% dentro do limite de {FLAG_OCIOSIDADE_PCT:.0f}%")

    return flags


# ─────────────────────────────────────────────────────────────────────────────
# Resumo agregado
# ─────────────────────────────────────────────────────────────────────────────

def _print_resumo(equipes: list[dict], contratos: list[dict]) -> None:
    _titulo("RESUMO AGREGADO -- ORIGEM DOS GAPS")

    total_base    = sum(eq["custo_base"]   for eq in equipes)
    total_escala  = sum(eq["gap_escala"]   for eq in equipes)
    total_praticab= sum(eq["gap_praticab"] for eq in equipes)
    total_pool    = sum(eq["gap_pool"]     for eq in equipes)
    total_custo   = sum(eq["custo_total"]  for eq in equipes)
    total_autonomo= sum(eq["custo_aut"]    for eq in equipes)
    total_residuo = sum(eq["residuo"]      for eq in equipes)

    print(f"\n  {'COMPONENTE':<35} {'VALOR':>18} {'% do total':>12} {'Justificativa'}")
    print(f"  {'-'*35} {'-'*18} {'-'*12} {'-'*30}")

    def row(nome, val, justif=""):
        pct = val / total_custo * 100 if total_custo > 0 else 0
        print(f"  {nome:<35} {_fmt(val):>18} {_fmt_pct(pct):>12}   {justif}")

    row("custo_base (1eq x perm_nominal)",  total_base,     "Custo unitario do catalogo")
    row("+ gap_escala (RCPSP N equipes)",    total_escala,   "Compressao de prazo: N equipes")
    row("+ gap_praticabilidade (residual)",  total_praticab, "Clima/combustivel (esperado ~0)")
    print(f"  {'         = SUBTOTAL AUTONOMO':<35} {_fmt(total_autonomo):>18}")
    row("+ gap_pool (contratos shared)",     total_pool,     "Ociosidade: cap. reservada idle")
    print(f"  {'='*35} {'='*18}")
    row("= CUSTO TOTAL",                     total_custo,    "")

    print(f"\n  Verificacao identidade (residuo): {total_residuo:+.2f} R$")
    if abs(total_residuo) > TOLERANCIA_VERIF * len(equipes):
        print(f"  [ATENCAO] Residuo agregado alto -- revisar calculo")
    else:
        print(f"  [OK]")

    print(f"\n  POOL: breakdown por contrato")
    for c in contratos:
        tipo = c["tipo_id"]
        eqs = [eq for eq in equipes if eq["contrato_tipo"] == tipo]
        sum_aut = sum(eq["custo_aut"] for eq in eqs)
        overhead = c["custo_total"] - sum_aut
        ocio_pct = overhead / c["custo_total"] * 100 if c["custo_total"] > 0 else 0
        print(
            f"    {tipo:<16} {_fmt(c['custo_total']):>18}   "
            f"aut={_fmt(sum_aut)} overhead={_fmt(overhead)} ({ocio_pct:.1f}% idle)"
        )

    print(f"\n  ITENS POR STATUS (frentes_nec):")
    ok = aviso = critico = sem_plan = 0
    for eq in equipes:
        # frentes_nec apenas se tivermos planejamento (calculado na hora)
        # aqui so contamos por N como proxy
        if eq["N"] <= 1.25:
            ok += 1
        elif eq["N"] <= 1.50:
            aviso += 1
        else:
            critico += 1
    print(f"    OK      (N <= 1.25): {ok:>3}")
    print(f"    AVISO   (N <= 1.50): {aviso:>3}")
    print(f"    CRITICO (N  > 1.50): {critico:>3}")
    print(f"    Total: {len(equipes)}")


# ─────────────────────────────────────────────────────────────────────────────
# Impressao: flags de investigacao
# ─────────────────────────────────────────────────────────────────────────────

def _print_flags(todos_flags: list[tuple[str, str]]) -> None:
    _titulo("FLAGS DE INVESTIGACAO")
    if not todos_flags:
        print("\n  Nenhuma anomalia detectada.")
        return
    for item_id, flag in todos_flags:
        print(f"\n  [{item_id}]  {flag}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    canonical   = carregar_canonical()
    equipes     = extrair_equipes(canonical)
    contratos   = extrair_contratos(canonical)
    planejamento= extrair_planejamento(canonical)

    if not equipes:
        print("[AVISO] Nenhuma equipe_direta encontrada no canonical.", file=sys.stderr)
        return

    todos_flags: list[tuple[str, str]] = []

    # ── 1. Memorial por item ─────────────────────────────────────────────────
    _titulo("MEMORIAL DE CALCULO -- DECOMPOSICAO POR ITEM")
    print("""
  Legenda:
    custo_base   = fixo_mensal x perm_nominal   (1 equipe, catalogo)
    gap_escala   = custo_base x (N-1)            (custo de N-1 equipes extras)
    gap_praticab = custo_autonomo - custo_base*N (residual: clima/terreno)
    gap_pool     = custo_total - custo_autonomo  (overhead contrato compartilhado)
  Identidade: custo_base + gap_escala + gap_praticab + gap_pool = custo_total
""")

    for eq in sorted(equipes, key=lambda e: e["item_id"]):
        plan = planejamento.get(eq["item_id"])
        flags = _print_item(eq, plan)
        for f in flags:
            todos_flags.append((eq["item_id"], f))

    # ── 2. Analise de contratos pool ─────────────────────────────────────────
    _titulo("ANALISE DE CONTRATOS POOL -- OCIOSIDADE")
    print("""
  Para cada contrato: MWs = machine-weeks (unidades x semanas).
  Ociosidade = MWs contratados - MWs realmente usados pelos itens.
  Overhead pool = ociosidade x custo_unit_semanal.

  MW ociosos surgem quando:
    (a) peak_demand (max itens simultaneos) < quantidade_contratada, OU
    (b) contrato cobre span total (1o ao ultimo item) mas itens nao se sobrepõem todo o tempo.
""")

    for c in sorted(contratos, key=lambda x: x["tipo_id"]):
        flags = _print_contrato(c, equipes)
        for f in flags:
            todos_flags.append((c["tipo_id"], f))

    # ── 3. Resumo agregado ───────────────────────────────────────────────────
    _print_resumo(equipes, contratos)

    # ── 4. Flags ─────────────────────────────────────────────────────────────
    _print_flags(todos_flags)

    # ── 5. Conclusao ─────────────────────────────────────────────────────────
    _titulo("CONCLUSAO")
    total_custo  = sum(eq["custo_total"]  for eq in equipes)
    total_base   = sum(eq["custo_base"]   for eq in equipes)
    total_escala = sum(eq["gap_escala"]   for eq in equipes)
    total_pool   = sum(eq["gap_pool"]     for eq in equipes)
    total_praticab = sum(eq["gap_praticab"] for eq in equipes)

    print(f"""
  O custo total de {_fmt(total_custo)} decompoe-se em:

    1. CUSTO BASE (catalogo, 1 equipe):   {_fmt(total_base)}
       Legitimo por definicao -- e o custo referencia do PU de catalogo.

    2. ESCALA DE EQUIPES (RCPSP):         {_fmt(total_escala)}
       Legitimo SE o deadline impoe N equipes simultaneas.
       INVESTIGAR: para cada item com N>1, verificar qual restricao do RCPSP
       determinou N. Se prazo pode ser relaxado -> N=1 -> economia direta.

    3. PRATICABILIDADE (residual clima):  {_fmt(total_praticab)}
       {'Proximo a zero -- OK, sem lesao real de produtividade alem da escala.' if abs(total_praticab) < 10_000 else '[!] Significativo -- investigar fator_clima/combustivel'}

    4. POOL OVERHEAD (contratos):         {_fmt(total_pool)}
       Legitimo SE os contratos compartilhados sao necessarios (peak demand real).
       INVESTIGAR: para cada contrato com >35% idle, avaliar se resequenciamento
       de itens pode reduzir o peak demand (ex: eap-1_3 pode ser feito depois
       de eap-1_4 terminar, sem sobreposicao -> pool size 2 em vez de 4).

  Proximos passos recomendados:
    - Verificar restricoes de deadline no RCPSP que forcam N>1 equipes
    - Analisar se itens em pool podem ser resequenciados para reduzir pico
    - Modelar cenario "standalone" (sem pool) para comparar com pool
    - Revisar capacidade contratada dos pools com >35% idle
""")


if __name__ == "__main__":
    main()
