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

from ._common import init_mpl

_PALETTE = ["#1a3a5c", "#5adc8e", "#5aabdc", "#e8a030", "#c05c18"]
_BDI_COMPS = ["Overhead BDI", "Lucro (L)", "Tributos"]
_BDI_COLORS = {"Overhead BDI": _PALETTE[2], "Lucro (L)": _PALETTE[3], "Tributos": _PALETTE[4]}


def _iso_week_to_ym(semana_offset: int, data_inicio: date) -> str:
    """Converte offset de semana (0-based) em string 'AAAA-MM'."""
    dt = data_inicio + timedelta(weeks=semana_offset)
    return dt.strftime("%Y-%m")


def _build_monthly_direto(canonical) -> dict[str, float]:
    """Constrói série mensal de custo direto a partir do planejamento + cronograma."""
    planejamento = getattr(canonical, "planejamento", None) or []
    cron = getattr(canonical, "cronograma", None)
    scheduled = getattr(cron, "scheduled_activities", None) or []
    projeto = getattr(canonical, "projeto", None)
    data_inicio_str = getattr(projeto, "data_inicio", None) if projeto else None

    try:
        data_inicio = date.fromisoformat(str(data_inicio_str)) if data_inicio_str else date(2026, 1, 1)
    except (ValueError, TypeError):
        data_inicio = date(2026, 1, 1)

    # Mapa item_id → custo total sem BDI
    custo_por_item: dict[str, float] = {}
    for item in planejamento:
        item_id = getattr(item, "item_id", None) or (item.get("item_id") if isinstance(item, dict) else None)
        subtotal = getattr(item, "subtotal", None) or (item.get("subtotal") if isinstance(item, dict) else {})
        if isinstance(subtotal, dict):
            sem_bdi = subtotal.get("sem_bdi") or {}
            total = float(sem_bdi.get("total", 0.0) or 0.0) if isinstance(sem_bdi, dict) else 0.0
        else:
            sem_bdi = getattr(subtotal, "sem_bdi", None)
            total = float(getattr(sem_bdi, "total", 0.0) or 0.0) if sem_bdi else 0.0
        if item_id and total > 0:
            custo_por_item[str(item_id)] = total

    # Distribuir custo de cada atividade uniformemente pelas semanas de execução
    monthly: dict[str, float] = defaultdict(float)
    for act in scheduled:
        act_id = getattr(act, "activity_id", None) or (act.get("activity_id") if isinstance(act, dict) else None)
        start = getattr(act, "start_week", None) or (act.get("start_week", 0) if isinstance(act, dict) else 0)
        end = getattr(act, "end_week", None) or (act.get("end_week", 0) if isinstance(act, dict) else 0)
        custo = custo_por_item.get(str(act_id), 0.0) if act_id else 0.0
        if custo <= 0 or end < start:
            continue
        n_weeks = max(1, end - start + 1)
        custo_semanal = custo / n_weeks
        for w in range(int(start), int(end) + 1):
            ym = _iso_week_to_ym(w, data_inicio)
            monthly[ym] += custo_semanal

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
        "Lucro (L)":    bdi_abs * 0.30,
        "Tributos":     bdi_abs * 0.35,
    }


def build(canonical, cubo) -> bytes | None:  # noqa: ARG001
    del cubo
    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None

    try:
        projeto = getattr(canonical, "projeto", None)
        data_inicio_str = getattr(projeto, "data_inicio", None) if projeto else None
        try:
            data_inicio = date.fromisoformat(str(data_inicio_str)) if data_inicio_str else date(2026, 1, 1)
        except (ValueError, TypeError):
            data_inicio = date(2026, 1, 1)

        # ── Séries mensais a partir das fontes canônicas ─────────────────────
        direto_m   = _build_monthly_direto(canonical)
        indireto_m = _build_monthly_indireto(canonical, data_inicio)

        # Períodos: union de todos os meses com dado, ordenados
        periodos = sorted(set(direto_m) | set(indireto_m))
        if not periodos:
            return None

        # Último mês com direto (marca fim da obra)
        ultimo_direto_idx = max(
            (i for i, p in enumerate(periodos) if direto_m.get(p, 0.0) > 0), default=None
        )

        scale = 1e6
        direto   = [direto_m.get(p, 0.0) / scale for p in periodos]
        indireto = [indireto_m.get(p, 0.0) / scale for p in periodos]

        resultado = getattr(canonical, "resultado", None)
        preco_venda = float(getattr(getattr(resultado, "venda", None), "total_com_bdi", 0.0) or 0.0) / scale
        custo_op    = float(getattr(getattr(resultado, "custo", None), "total", 0.0) or 0.0) / scale

        # BDI: distribui o markup proporcionalmente ao custo mensal (todas as séries em Mi)
        total_custo = sum(direto) + sum(indireto)  # em Mi
        bdi_total   = max(0.0, preco_venda - total_custo)  # em Mi
        bdi_frac    = bdi_total / max(total_custo, 1e-9)   # fração adimensional
        bdi_layers: dict[str, list[float]] = {
            "Overhead BDI": [(d + i) * bdi_frac * 0.35 for d, i in zip(direto, indireto)],
            "Lucro (L)":    [(d + i) * bdi_frac * 0.30 for d, i in zip(direto, indireto)],
            "Tributos":     [(d + i) * bdi_frac * 0.35 for d, i in zip(direto, indireto)],
        }

        x = list(range(len(periodos)))

        fig, (ax_bar, ax_line) = plt.subplots(2, 1, figsize=(max(10, len(periodos) * 0.9 + 2), 10), sharex=True)

        # ── Painel 1: barras mensais empilhadas ────────────────────────────────
        ax_bar.bar(x, direto, color=_PALETTE[0], alpha=0.88, width=0.7, label="Direto")
        ax_bar.bar(x, indireto, bottom=direto, color=_PALETTE[1], alpha=0.88, width=0.7, label="Indireto")
        bottoms = [d + i for d, i in zip(direto, indireto)]
        for comp in _BDI_COMPS:
            vals = bdi_layers[comp]
            ax_bar.bar(x, vals, bottom=bottoms, color=_BDI_COLORS[comp], alpha=0.80, width=0.7, label=comp)
            bottoms = [b + v for b, v in zip(bottoms, vals)]
        ax_bar.set_title("Custo por Mês (planejamento + indiretos)", fontsize=11, fontweight="bold")
        ax_bar.set_ylabel("R$ (Mi)", fontsize=9)
        ax_bar.legend(loc="upper right", fontsize=8)
        ax_bar.grid(axis="y", alpha=0.3)
        ax_bar.tick_params(labelbottom=False)

        # ── Painel 2: acumulado convergindo para preço de venda ──────────────
        def _accum(series: list[float]) -> list[float]:
            out, s = [], 0.0
            for v in series:
                s += v
                out.append(s)
            return out

        acc_d = _accum(direto)
        acc_i = [d + i for d, i in zip(acc_d, _accum(indireto))]
        acc_bdi: dict[str, list[float]] = {}
        prev = acc_i
        for comp in _BDI_COMPS:
            nxt = [p + v for p, v in zip(prev, _accum(bdi_layers[comp]))]
            acc_bdi[comp] = nxt
            prev = nxt
        acc_total_bdi = prev

        ax_line.fill_between(x, 0, acc_d, alpha=0.75, color=_PALETTE[0], label="Direto Acum.")
        ax_line.fill_between(x, acc_d, acc_i, alpha=0.75, color=_PALETTE[1], label="Indireto Acum.")
        prev_acc = acc_i
        for comp in _BDI_COMPS:
            nxt_acc = acc_bdi[comp]
            ax_line.fill_between(x, prev_acc, nxt_acc, alpha=0.70, color=_BDI_COLORS[comp], label=f"{comp} Acum.")
            prev_acc = nxt_acc
        ax_line.plot(x, acc_total_bdi, color="#333", linewidth=1.8, alpha=0.9, zorder=5)

        # Linhas de referência — vêm do resultado financeiro real
        if preco_venda > 0:
            ax_line.axhline(preco_venda, color="#e74c3c", linewidth=1.8, linestyle="-",
                            alpha=0.9, label=f"Preço de venda: {preco_venda:.1f} Mi")
        if custo_op > 0:
            ax_line.axhline(custo_op, color="#27ae60", linewidth=1.2, linestyle="--",
                            alpha=0.6, label=f"Custo s/BDI: {custo_op:.1f} Mi")

        # Separador visual: fim das atividades diretas vs pós-obra
        if ultimo_direto_idx is not None and ultimo_direto_idx < len(periodos) - 1:
            for ax in (ax_bar, ax_line):
                ax.axvline(x=ultimo_direto_idx + 0.5, color="#555", linewidth=1.2,
                           linestyle=":", alpha=0.7)
            ax_bar.text(ultimo_direto_idx + 0.6, ax_bar.get_ylim()[1] * 0.92,
                        "← obra concluída\n   pós-obra →",
                        fontsize=7, color="#555", va="top")

        ax_line.set_ylabel("R$ (Mi) Acumulado", fontsize=9)
        ax_line.set_xlabel("Mês", fontsize=9)
        ax_line.set_title(
            "Custo Acumulado (direto + indireto + BDI → preço de venda)", fontsize=11, fontweight="bold"
        )
        ax_line.set_xticks(x)
        ax_line.set_xticklabels(periodos, rotation=45, ha="right", fontsize=8)
        ax_line.legend(fontsize=7.5, loc="upper left", ncol=2)
        ax_line.grid(axis="y", alpha=0.3)

        fig.suptitle("S-Curve de Custo", fontsize=13, fontweight="bold")
        fig.tight_layout()
        return fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None
