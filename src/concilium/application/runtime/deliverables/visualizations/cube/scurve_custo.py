"""scurve_custo.png — S-Curve de custo + camadas BDI convergindo para o preço de venda.

Painel superior (barras mensais):
  Direto | Indireto | Overhead BDI | Lucro (L) | Tributos

Painel inferior (acumulado):
  Áreas empilhadas das mesmas 5 camadas → curva converge para o preço de venda.

Fonte de dados: planejamento + indiretos_semanal (não o cubo analítico, que só captura
a fração rastreada pelo pool e subestima o direto).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from ._common import build_payload, init_mpl

_PALETTE = ["#1a3a5c", "#5adc8e", "#5aabdc", "#e8a030", "#c05c18"]
_BDI_COMPS = ["Overhead BDI", "Lucro (L)", "Tributos"]
_BDI_COLORS = {"Overhead BDI": _PALETTE[2], "Lucro (L)": _PALETTE[3], "Tributos": _PALETTE[4]}
_SCURVE_SCALE = 1e6


def _iso_week_to_ym(semana_offset: int, data_inicio: date) -> str:
    """Converte offset de semana (0-based) em string 'AAAA-MM'."""
    dt = data_inicio + timedelta(weeks=semana_offset)
    return dt.strftime("%Y-%m")


def _resolve_data_inicio(canonical) -> date:
    """Resolve a data de início do projeto a partir do canônico, com fallback seguro."""
    projeto = getattr(canonical, "projeto", None)
    data_inicio_str = getattr(projeto, "data_inicio", None) if projeto else None
    try:
        return date.fromisoformat(str(data_inicio_str)) if data_inicio_str else date(2026, 1, 1)
    except (ValueError, TypeError):
        return date(2026, 1, 1)


def _item_custo_sem_bdi(item) -> float:
    """Extrai o custo total sem BDI de um item de planejamento (dict ou objeto)."""
    subtotal = getattr(item, "subtotal", None) or (item.get("subtotal") if isinstance(item, dict) else {})
    if isinstance(subtotal, dict):
        sem_bdi = subtotal.get("sem_bdi") or {}
        return float(sem_bdi.get("total", 0.0) or 0.0) if isinstance(sem_bdi, dict) else 0.0
    sem_bdi = getattr(subtotal, "sem_bdi", None)
    return float(getattr(sem_bdi, "total", 0.0) or 0.0) if sem_bdi else 0.0


def _build_custo_por_item(planejamento) -> dict[str, float]:
    """Mapa item_id → custo total sem BDI, a partir do planejamento."""
    custo_por_item: dict[str, float] = {}
    for item in planejamento:
        item_id = getattr(item, "item_id", None) or (item.get("item_id") if isinstance(item, dict) else None)
        total = _item_custo_sem_bdi(item)
        if item_id and total > 0:
            custo_por_item[str(item_id)] = total
    return custo_por_item


def _activity_id_start_end(act):
    """Extrai (activity_id, start_week, end_week) de uma atividade agendada (dict ou objeto)."""
    act_id = getattr(act, "activity_id", None) or (act.get("activity_id") if isinstance(act, dict) else None)
    start = getattr(act, "start_week", None) or (act.get("start_week", 0) if isinstance(act, dict) else 0)
    end = getattr(act, "end_week", None) or (act.get("end_week", 0) if isinstance(act, dict) else 0)
    return act_id, start, end


def _distribute_activity_cost_by_week(
    act, custo_por_item: dict[str, float], data_inicio: date, monthly: dict[str, float]
) -> None:
    """Distribui o custo de uma atividade uniformemente pelas semanas de execução (atualiza `monthly` in-place)."""
    act_id, start, end = _activity_id_start_end(act)
    custo = custo_por_item.get(str(act_id), 0.0) if act_id else 0.0
    if custo <= 0 or end < start:
        return
    n_weeks = max(1, end - start + 1)
    custo_semanal = custo / n_weeks
    for w in range(int(start), int(end) + 1):
        ym = _iso_week_to_ym(w, data_inicio)
        monthly[ym] += custo_semanal


def _build_monthly_direto(canonical) -> dict[str, float]:
    """Constrói série mensal de custo direto a partir do planejamento + cronograma."""
    planejamento = getattr(canonical, "planejamento", None) or []
    cron = getattr(canonical, "cronograma", None)
    scheduled = getattr(cron, "scheduled_activities", None) or []
    data_inicio = _resolve_data_inicio(canonical)

    # Mapa item_id → custo total sem BDI
    custo_por_item = _build_custo_por_item(planejamento)

    # Distribuir custo de cada atividade uniformemente pelas semanas de execução
    monthly: dict[str, float] = defaultdict(float)
    for act in scheduled:
        _distribute_activity_cost_by_week(act, custo_por_item, data_inicio, monthly)

    return dict(monthly)


def _build_monthly_indireto(canonical, data_inicio: date) -> dict[str, float]:
    """Constrói série mensal de custo indireto a partir de indiretos_semanal."""
    ind_sem = getattr(canonical, "indiretos_semanal", None) or []
    monthly: dict[str, float] = defaultdict(float)
    for item in ind_sem:
        # Nota: usar sentinel explícito para distinguir semana=0 (válida) de semana=None
        if isinstance(item, dict):
            semana = item.get("semana")
            custo = float(item.get("custo_semanal", 0.0) or 0.0)
        else:
            _s = getattr(item, "semana", None)
            semana = _s  # preserva 0 sem colapsar para None via `or`
            custo = float(getattr(item, "custo_semanal", 0.0) or 0.0)
        if semana is None:
            continue
        ym = _iso_week_to_ym(int(semana), data_inicio)
        monthly[ym] += custo
    return dict(monthly)


def _bdi_decomp(resultado) -> dict[str, float]:
    """Extrai componentes de BDI: overhead, lucro, tributos."""
    tabela = getattr(canonical_g, "tabela_bdi_efetiva", None) if False else None  # noqa (not used)
    venda = getattr(resultado, "venda", None) if resultado else None
    custo = getattr(resultado, "custo", None) if resultado else None
    if not venda or not custo:
        return {"Overhead BDI": 0.0, "Lucro (L)": 0.0, "Tributos": 0.0}

    preco = float(getattr(venda, "total_com_bdi", 0.0) or 0.0)
    custo_total = float(getattr(custo, "total", 0.0) or 0.0)
    bdi_abs = max(0.0, preco - custo_total)

    # Proporções típicas dentro do BDI (AC+DF+R = overhead, L = lucro, T = tributos)
    # Usar as taxas do perfil se disponíveis; caso contrário, proporção padrão TCU
    bdi_lucro = float(getattr(getattr(venda, "bdi_lucro_impostos", None) or 0.0, "__float__", lambda: 0.0)())  # noqa
    # bdi_lucro_impostos é a TAXA total; recalcular a partir dos valores absolutos
    # Proporção padrão: overhead ~35%, lucro ~30%, tributos ~35%
    return {
        "Overhead BDI": bdi_abs * 0.35,
        "Lucro (L)": bdi_abs * 0.30,
        "Tributos": bdi_abs * 0.35,
    }


def _fetch_scurve_nat_rows(canonical, cubo_analitico) -> list | None:
    """Busca as rows da face tempo_natureza para o S-curve."""
    nat_payload = build_payload("tempo_natureza", "mes", 220, canonical, cubo_analitico)
    return nat_payload.get("rows") if nat_payload else None


def _fetch_scurve_comp_rows(canonical, cubo_analitico) -> list:
    """Busca as rows da face tempo_componente para o S-curve."""
    comp_payload = build_payload("tempo_componente", "mes", 220, canonical, cubo_analitico)
    return (comp_payload.get("rows") if comp_payload else None) or []


def _build_direto_indireto_monthly(rows_nat: list) -> tuple[dict[str, float], dict[str, float]]:
    """Agrega, por período, o custo direto e indireto a partir das rows da face tempo_natureza."""
    direto_m: dict[str, float] = {}
    indireto_m: dict[str, float] = {}
    for r in rows_nat:
        p = str(r.get("periodo", ""))
        v = float(r.get("valor_rs", 0.0))
        nat = str(r.get("natureza", ""))
        if nat == "direto":
            direto_m[p] = direto_m.get(p, 0.0) + v
        elif nat == "indireto":
            indireto_m[p] = indireto_m.get(p, 0.0) + v
    return direto_m, indireto_m


def _build_bdi_by_period(rows_comp: list) -> dict[str, dict[str, float]]:
    """Agrega, por período, os componentes de BDI de interesse (`_BDI_COMPS`)."""
    bdi_by_period: dict[str, dict[str, float]] = {}
    for r in rows_comp:
        comp = str(r.get("componente_bdi", ""))
        if comp not in _BDI_COMPS:
            continue
        p = str(r.get("periodo", ""))
        v = float(r.get("valor_rs", 0.0))
        if p not in bdi_by_period:
            bdi_by_period[p] = {c: 0.0 for c in _BDI_COMPS}
        bdi_by_period[p][comp] = bdi_by_period[p].get(comp, 0.0) + v
    return bdi_by_period


def _scale_scurve_series(
    direto_m: dict[str, float],
    indireto_m: dict[str, float],
    bdi_by_period: dict[str, dict[str, float]],
    periodos: list[str],
) -> tuple[list[float], list[float], dict[str, list[float]]]:
    """Escala as séries mensais de direto/indireto/BDI para o fator `_SCURVE_SCALE` (R$ Mi)."""
    direto = [direto_m.get(p, 0.0) / _SCURVE_SCALE for p in periodos]
    indireto = [indireto_m.get(p, 0.0) / _SCURVE_SCALE for p in periodos]
    bdi_layers = {
        comp: [bdi_by_period.get(p, {}).get(comp, 0.0) / _SCURVE_SCALE for p in periodos] for comp in _BDI_COMPS
    }
    return direto, indireto, bdi_layers


def _render_scurve_bar_panel(
    ax_bar, x: list[int], direto: list[float], indireto: list[float], bdi_layers: dict[str, list[float]]
) -> None:
    """Renderiza o painel superior: barras mensais empilhadas (direto/indireto/BDI)."""
    ax_bar.bar(x, direto, color=_PALETTE[0], alpha=0.88, width=0.7, label="Direto")
    ax_bar.bar(x, indireto, bottom=direto, color=_PALETTE[1], alpha=0.88, width=0.7, label="Indireto")
    bottoms = [d + i for d, i in zip(direto, indireto, strict=False)]
    for comp in _BDI_COMPS:
        vals = bdi_layers[comp]
        ax_bar.bar(x, vals, bottom=bottoms, color=_BDI_COLORS[comp], alpha=0.80, width=0.7, label=comp)
        bottoms = [b + v for b, v in zip(bottoms, vals, strict=False)]
    ax_bar.set_title("Custo por Mês (planejamento + indiretos)", fontsize=11, fontweight="bold")
    ax_bar.set_ylabel("R$ (Mi)", fontsize=9)
    ax_bar.legend(loc="upper right", fontsize=8)
    ax_bar.grid(axis="y", alpha=0.3)
    ax_bar.tick_params(labelbottom=False)


def _accum(series: list[float]) -> list[float]:
    """Soma cumulativa de uma série."""
    out, s = [], 0.0
    for v in series:
        s += v
        out.append(s)
    return out


def _accumulate_scurve_layers(
    direto: list[float], indireto: list[float], bdi_layers: dict[str, list[float]]
) -> tuple[list[float], list[float], dict[str, list[float]], list[float]]:
    """Calcula as camadas acumuladas (direto, indireto e cada componente de BDI) empilhadas."""
    acc_d = _accum(direto)
    acc_i = [d + i for d, i in zip(acc_d, _accum(indireto), strict=False)]
    acc_bdi: dict[str, list[float]] = {}
    prev = acc_i
    for comp in _BDI_COMPS:
        nxt = [p + v for p, v in zip(prev, _accum(bdi_layers[comp]), strict=False)]
        acc_bdi[comp] = nxt
        prev = nxt
    acc_total_bdi = prev
    return acc_d, acc_i, acc_bdi, acc_total_bdi


def _render_scurve_line_panel(
    ax_line,
    x: list[int],
    acc_d: list[float],
    acc_i: list[float],
    acc_bdi: dict[str, list[float]],
    acc_total_bdi: list[float],
    custo_op: float,
) -> None:
    """Renderiza o painel inferior: áreas empilhadas acumuladas e linhas de referência."""
    ax_line.fill_between(x, 0, acc_d, alpha=0.75, color=_PALETTE[0], label="Direto Acum.")
    ax_line.fill_between(x, acc_d, acc_i, alpha=0.75, color=_PALETTE[1], label="Indireto Acum.")
    prev_acc = acc_i
    for comp in _BDI_COMPS:
        nxt_acc = acc_bdi[comp]
        ax_line.fill_between(x, prev_acc, nxt_acc, alpha=0.70, color=_BDI_COLORS[comp], label=f"{comp} Acum.")
        prev_acc = nxt_acc
    ax_line.plot(x, acc_total_bdi, color="#333", linewidth=1.8, alpha=0.9, zorder=5)

    # Linhas de referência
    # preco_pool_bdi = topo das barras acumuladas (direto+indireto+BDI do gráfico)
    preco_pool_bdi = acc_total_bdi[-1] if acc_total_bdi else 0.0
    if preco_pool_bdi > 0:
        ax_line.axhline(
            preco_pool_bdi,
            color="#e74c3c",
            linewidth=1.8,
            linestyle="-",
            alpha=0.9,
            label=f"Preço de venda: {preco_pool_bdi:.1f} Mi",
        )
    if custo_op > 0:
        ax_line.axhline(
            custo_op,
            color="#27ae60",
            linewidth=1.2,
            linestyle="--",
            alpha=0.6,
            label=f"Custo s/BDI: {custo_op:.1f} Mi",
        )


def _render_scurve_separator(ax_bar, ax_line, ultimo_direto_idx: int | None, periodos: list[str]) -> None:
    """Renderiza o separador visual entre atividades diretas e período pós-obra, quando aplicável."""
    if ultimo_direto_idx is not None and ultimo_direto_idx < len(periodos) - 1:
        for ax in (ax_bar, ax_line):
            ax.axvline(x=ultimo_direto_idx + 0.5, color="#555", linewidth=1.2, linestyle=":", alpha=0.7)
        ax_bar.text(
            ultimo_direto_idx + 0.6,
            ax_bar.get_ylim()[1] * 0.92,
            "← obra concluída\n   pós-obra →",
            fontsize=7,
            color="#555",
            va="top",
        )


def _finalize_scurve_line_axis(ax_line, x: list[int], periodos: list[str]) -> None:
    """Configura eixos, título, ticks, legenda e grade do painel inferior."""
    ax_line.set_ylabel("R$ (Mi) Acumulado", fontsize=9)
    ax_line.set_xlabel("Mês", fontsize=9)
    ax_line.set_title("Custo Acumulado (direto + indireto + BDI → preço de venda)", fontsize=11, fontweight="bold")
    ax_line.set_xticks(x)
    ax_line.set_xticklabels(periodos, rotation=45, ha="right", fontsize=8)
    ax_line.legend(fontsize=7.5, loc="upper left", ncol=2)
    ax_line.grid(axis="y", alpha=0.3)


def build(canonical, cubo) -> bytes | None:  # noqa: ARG001
    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None

    cubo_analitico = getattr(canonical, "cubo_analitico", None)
    try:
        rows_nat = _fetch_scurve_nat_rows(canonical, cubo_analitico)
        if not rows_nat:
            return None

        rows_comp = _fetch_scurve_comp_rows(canonical, cubo_analitico)

        # Build direto/indireto monthly series from nat rows
        direto_m, indireto_m = _build_direto_indireto_monthly(rows_nat)

        # BDI layers from comp rows (only _BDI_COMPS are used)
        bdi_by_period = _build_bdi_by_period(rows_comp)

        periodos = sorted(set(direto_m) | set(indireto_m) | set(bdi_by_period))
        if not periodos:
            return None

        # Último mês com direto (marca fim da obra)
        ultimo_direto_idx = max((i for i, p in enumerate(periodos) if direto_m.get(p, 0.0) > 0), default=None)

        direto, indireto, bdi_layers = _scale_scurve_series(direto_m, indireto_m, bdi_by_period, periodos)

        # Custo operacional real = direto + indireto, derivado do cubo (não de custo.total
        # que pode refletir custo de pool ≠ PU×Q quando n_frentes > 1).
        custo_op = (sum(direto_m.values()) + sum(indireto_m.values())) / _SCURVE_SCALE

        x = list(range(len(periodos)))

        fig, (ax_bar, ax_line) = plt.subplots(2, 1, figsize=(max(10, len(periodos) * 0.9 + 2), 10), sharex=True)

        # ── Painel 1: barras mensais empilhadas ────────────────────────────────
        _render_scurve_bar_panel(ax_bar, x, direto, indireto, bdi_layers)

        # ── Painel 2: acumulado convergindo para preço de venda ──────────────
        acc_d, acc_i, acc_bdi, acc_total_bdi = _accumulate_scurve_layers(direto, indireto, bdi_layers)
        _render_scurve_line_panel(ax_line, x, acc_d, acc_i, acc_bdi, acc_total_bdi, custo_op)

        # Separador visual: fim das atividades diretas vs pós-obra
        _render_scurve_separator(ax_bar, ax_line, ultimo_direto_idx, periodos)

        _finalize_scurve_line_axis(ax_line, x, periodos)

        fig.suptitle("S-Curve de Custo", fontsize=13, fontweight="bold")
        fig.tight_layout()
        return fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None
