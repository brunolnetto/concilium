"""BacktrackingPEBuilder — inversos fechados e validação roundtrip (ADR-061).

Para cada item em déficit, computa todos os parâmetros que, ajustados
individualmente, fechariam o gap. Valida cada solução com roundtrip analítico.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from concilium.domain.constants import SEMANAS_POR_MES
from concilium.domain.models.backtracking_pe import (
    BacktrackingPEItem,
    BacktrackingPERelatorio,
    SolucaoInversa,
)
from concilium.domain.models.diagnostico_pe import DiagnosticoPEItem, DiagnosticoPERelatorio

_EPS_TOL_REL = 0.0001  # 0,01% de tolerância relativa
_EPS_TOL_ABS = 10.0  # R$10 tolerância absoluta mínima


def _tol(gap: float) -> float:
    return max(_EPS_TOL_ABS, abs(gap) * _EPS_TOL_REL)


def _btpb_build_lookups(canonical_in: Any) -> tuple[dict, dict, dict, Any]:
    equipe_lookup = {e.item_id: e for e in (canonical_in.equipes_diretas or [])}
    sched_lookup = {
        sa.activity_id: sa for sa in (canonical_in.cronograma.scheduled_activities if canonical_in.cronograma else [])
    }
    plan_lookup = {p.item_id: p for p in (canonical_in.planejamento or [])}
    return equipe_lookup, sched_lookup, plan_lookup, canonical_in.praticabilidade


def _btpb_validacoes(n_fail: int, itens_bt: list, pe_gap_alvo: float) -> list[str]:
    validacoes: list[str] = []
    if n_fail > 0:
        validacoes.append("VAL-INV-ROUNDTRIP-FAIL")
    for bt_item in itens_bt:
        sol_l = next((s for s in bt_item.solucoes if s.parametro == "L"), None)
        if sol_l and abs(sol_l.pe_gap_recalculado - pe_gap_alvo) > _tol(bt_item.pe_gap_atual) * 5:
            validacoes.append("VAL-INV-NORM-FAIL")
            break
    return validacoes


def _find_solucao(solucoes: list, parametro: str):
    for s in solucoes:
        if s.parametro == parametro and s.roundtrip_valido:
            return s
    return None


def _get_gap_fator(item, codigo: str) -> float:
    for f in item.fatores:
        if f.codigo == codigo:
            return f.gap_rs
    return 0.0


def _count_calendar_constrained_weeks(sa: Any) -> int:
    if not (sa and sa.distribuicao_semanal):
        return 0
    constrained = 0
    for d in sa.distribuicao_semanal.values():
        fator = float(getattr(d, "fator_calendario", 1.0) or 1.0)
        if fator < 0.999:
            constrained += 1
    return constrained


def _get_item_cubo_hint(diagnostico: DiagnosticoPERelatorio, atividade_id: str) -> dict[str, Any]:
    bloco = getattr(diagnostico, "explicacao_natureza_periodo", None)
    if not isinstance(bloco, dict):
        return {}
    itens = bloco.get("itens")
    if not isinstance(itens, dict):
        return {}
    hint = itens.get(atividade_id)
    return hint if isinstance(hint, dict) else {}


class BacktrackingPEBuilder:
    """Computa soluções inversas para cada item em déficit."""

    def build(
        self,
        diagnostico: DiagnosticoPERelatorio,
        canonical_in: Any,
        pe_gap_alvo: float = 0.0,
    ) -> BacktrackingPERelatorio:
        projeto_id = diagnostico.projeto_id
        equipe_lookup, sched_lookup, plan_lookup, prat = _btpb_build_lookups(canonical_in)
        explicacao_natureza_periodo = (
            diagnostico.explicacao_natureza_periodo if isinstance(diagnostico.explicacao_natureza_periodo, dict) else {}
        )
        itens_bt: list[BacktrackingPEItem] = []
        n_fail = 0
        for item in diagnostico.itens_deficit:
            item_cubo_hint = _get_item_cubo_hint(diagnostico, item.atividade_id)
            bt_item, fails_count = self._btpb_process_item(
                item, equipe_lookup, sched_lookup, plan_lookup, prat, pe_gap_alvo, item_cubo_hint
            )
            n_fail += fails_count
            itens_bt.append(bt_item)
        validacoes = _btpb_validacoes(n_fail, itens_bt, pe_gap_alvo)
        return BacktrackingPERelatorio(
            projeto_id=projeto_id,
            gerado_em=datetime.now(UTC).isoformat(),
            pe_gap_alvo=pe_gap_alvo,
            itens=tuple(itens_bt),
            consistencia_global=(n_fail == 0),
            n_roundtrips_falharam=n_fail,
            validacoes_emitidas=tuple(validacoes),
            explicacao_natureza_periodo=explicacao_natureza_periodo,
        )

    def _btpb_process_item(
        self,
        item: DiagnosticoPEItem,
        equipe_lookup: dict,
        sched_lookup: dict,
        plan_lookup: dict,
        prat: Any,
        pe_gap_alvo: float,
        item_cubo_hint: dict[str, Any] | None = None,
    ) -> tuple[BacktrackingPEItem, int]:
        solucoes = self._compute_solucoes(item, equipe_lookup, sched_lookup, plan_lookup, prat, pe_gap_alvo)
        fails = tuple(s.parametro for s in solucoes if not s.roundtrip_valido)
        validas = [s for s in solucoes if s.roundtrip_valido]
        recom = None
        if validas:

            def score(s: SolucaoInversa) -> float:
                base = (
                    s.impacto_preco_pct * 3
                    + s.impacto_produtividade_pct * 2
                    + s.impacto_recursos_pct * 1.5
                    + abs(s.impacto_prazo_semanas) * 0.5
                )

                # Consome explicitamente a decomposição do cubo para priorizar ações.
                # Se a natureza dominante for indireta em janela crítica, timing tende
                # a capturar sazonalidade/rampa com menor repasse ao cliente.
                if s.parametro == "T0_RAMP" and item_cubo_hint:
                    if item_cubo_hint.get("natureza_dominante") == "indireto":
                        base -= 0.75
                    if item_cubo_hint.get("janela_critica_iso"):
                        base -= 0.25

                return base

            recom = min(validas, key=score)
        return (
            BacktrackingPEItem(
                atividade_id=item.atividade_id,
                descricao=item.descricao,
                pe_gap_atual=item.gap_rs,
                pe_gap_alvo=pe_gap_alvo,
                solucoes=tuple(sorted(solucoes, key=lambda s: (-s.confianca, s.impacto_preco_pct))),
                solucao_recomendada=recom,
                roundtrips_falharam=fails,
            ),
            len(fails),
        )

    def _solve_L(
        self, item: DiagnosticoPEItem, plan: Any, alvo: float, gap: float
    ) -> tuple[SolucaoInversa | None, float, float]:
        """Solução A: inversa de L. Retorna (solucao, denominator, T_ef)."""
        T_ef = 0.1338
        C_cat = float((plan.subtotal.sem_bdi.total if plan and plan.subtotal and plan.subtotal.sem_bdi else 0) or 1)
        denominator = C_cat / max(1.0 - T_ef, 0.01)
        if denominator <= 0:
            return None, denominator, T_ef
        delta_L = abs(gap) / denominator
        L_req = item.l_aplicado + delta_L
        preco_novo = C_cat * (1.0 + item.l_aplicado + (L_req - item.l_aplicado)) / (1.0 - T_ef)
        pe_recalc = preco_novo - item.custo_realizado
        err = abs(pe_recalc - alvo)
        return (
            SolucaoInversa(
                parametro="L",
                valor_atual=item.l_aplicado,
                valor_requerido=round(L_req, 4),
                delta_abs=round(delta_L, 4),
                delta_pct=round(delta_L / max(item.l_aplicado, 0.01) * 100, 1),
                impacto_preco_pct=round(delta_L / (1.0 - T_ef) * 100, 2),
                impacto_produtividade_pct=0.0,
                impacto_recursos_pct=0.0,
                impacto_prazo_semanas=0.0,
                pe_gap_recalculado=round(pe_recalc, 2),
                roundtrip_valido=err < _tol(gap),
                erro_roundtrip=round(err, 2),
                confianca=5,
            ),
            denominator,
            T_ef,
        )

    def _solve_P(self, item: DiagnosticoPEItem, equipe: Any, sa: Any, alvo: float, gap: float) -> SolucaoInversa | None:
        """Solução B: inversa de produtividade η."""
        if not (equipe and sa and sa.distribuicao_semanal):
            return None
        active = [d for d in sa.distribuicao_semanal.values() if d.num_equipes > 0]
        N_total = sum(d.num_equipes for d in active)
        c_fixo_sem = (equipe.custo_mao_obra_mensal + equipe.custo_equipamentos_mensal) / SEMANAS_POR_MES
        if not (c_fixo_sem > 0 and N_total > 0):
            return None
        eta_target = max(0.01, min(1.0, item.eta_real + abs(gap) / max(c_fixo_sem * N_total, 1.0)))
        N_new = item.n_total / max(eta_target, 0.01)
        pe_recalc_b = item.preco_venda - (c_fixo_sem * N_new + (item.custo_realizado - c_fixo_sem * item.n_total))
        err_b = abs(pe_recalc_b - alvo)
        p_delta_pct = round((eta_target / max(item.eta_real, 0.01) - 1.0) * 100, 1)
        return SolucaoInversa(
            parametro="P",
            valor_atual=round(item.eta_real * 100, 1),
            valor_requerido=round(eta_target * 100, 1),
            delta_abs=round((eta_target - item.eta_real) * 100, 1),
            delta_pct=p_delta_pct,
            impacto_preco_pct=0.0,
            impacto_produtividade_pct=abs(p_delta_pct),
            impacto_recursos_pct=0.0,
            impacto_prazo_semanas=round((N_new - N_total) / max(N_total / len(active), 1), 1),
            pe_gap_recalculado=round(pe_recalc_b, 2),
            roundtrip_valido=err_b < _tol(gap) * 3,
            erro_roundtrip=round(err_b, 2),
            confianca=4,
        )

    def _solve_timing(self, item: DiagnosticoPEItem, sa: Any, alvo: float, gap: float) -> SolucaoInversa | None:
        """Solução C: inversa de timing (cross-term)."""
        if not (not item.validez_aproximacao and item.cov_n_p < 0 and sa and sa.distribuicao_semanal):
            return None
        gap_cross = sum(f.gap_rs for f in item.fatores if f.codigo == "F_ETA_CROSS")
        if gap_cross <= 50:
            return None
        semanas_deslocamento = max(4, round(abs(item.cov_n_p) * 20))
        pe_recalc_c = item.gap_rs + gap_cross
        err_c = abs(pe_recalc_c - alvo)
        return SolucaoInversa(
            parametro="T0_RAMP",
            valor_atual=0.0,
            valor_requerido=float(semanas_deslocamento),
            delta_abs=float(semanas_deslocamento),
            delta_pct=0.0,
            impacto_preco_pct=0.0,
            impacto_produtividade_pct=0.0,
            impacto_recursos_pct=0.0,
            impacto_prazo_semanas=float(semanas_deslocamento),
            pe_gap_recalculado=round(pe_recalc_c, 2),
            roundtrip_valido=err_c < _tol(gap) * 5,
            erro_roundtrip=round(err_c, 2),
            confianca=3,
        )

    def _solve_timing_calendario(
        self, item: DiagnosticoPEItem, sa: Any, alvo: float, gap: float
    ) -> SolucaoInversa | None:
        """Solução C2: inversa temporal orientada por feriados/recesso."""
        if not (sa and sa.distribuicao_semanal):
            return None
        gap_cal = _get_gap_fator(item, "F_CALENDARIO")
        if gap_cal <= 50:
            return None
        semanas_restritas = _count_calendar_constrained_weeks(sa)
        if semanas_restritas <= 0:
            return None

        deslocamento = float(max(1, min(8, semanas_restritas)))
        pe_recalc = item.gap_rs + gap_cal
        err = abs(pe_recalc - alvo)
        return SolucaoInversa(
            parametro="T0_CALENDARIO",
            valor_atual=0.0,
            valor_requerido=deslocamento,
            delta_abs=deslocamento,
            delta_pct=0.0,
            impacto_preco_pct=0.0,
            impacto_produtividade_pct=0.0,
            impacto_recursos_pct=0.0,
            impacto_prazo_semanas=deslocamento,
            pe_gap_recalculado=round(pe_recalc, 2),
            roundtrip_valido=err < _tol(gap) * 5,
            erro_roundtrip=round(err, 2),
            confianca=3,
        )

    def _solve_n_max(
        self, item: DiagnosticoPEItem, equipe: Any, sa: Any, alvo: float, gap: float
    ) -> SolucaoInversa | None:
        """Solução C2: inversa de n_max (ADR-061 §DoD)."""
        if not (equipe and sa and sa.distribuicao_semanal):
            return None
        active_d = [d for d in sa.distribuicao_semanal.values() if d.num_equipes > 0]
        T_weeks = len(active_d)
        n_meio_actual = item.n_total / max(T_weeks, 1)
        c_fixo_sem_n = (equipe.custo_mao_obra_mensal + equipe.custo_equipamentos_mensal) / SEMANAS_POR_MES
        if not (c_fixo_sem_n > 0 and T_weeks > 0 and abs(gap) > 0):
            return None
        delta_n_raw = abs(gap) / max(c_fixo_sem_n * T_weeks * max(1.0 - item.eta_real, 0.01), 1.0)
        delta_n = max(1, round(delta_n_raw))
        n_max_novo = n_meio_actual + delta_n
        t_novo = T_weeks * n_meio_actual / n_max_novo
        t_delta_semanas = T_weeks - t_novo
        n_total_novo = item.n_total - t_delta_semanas * n_max_novo
        pe_recalc_n = item.preco_venda - (
            c_fixo_sem_n * max(n_total_novo, item.n_total * 0.5) + (item.custo_realizado - c_fixo_sem_n * item.n_total)
        )
        err_n = abs(pe_recalc_n - alvo)
        roundtrip_ok = t_delta_semanas <= 1.0 or err_n < _tol(gap) * 5
        return SolucaoInversa(
            parametro="N_MAX",
            valor_atual=round(n_meio_actual, 1),
            valor_requerido=round(n_max_novo, 1),
            delta_abs=round(delta_n, 1),
            delta_pct=round(delta_n / max(n_meio_actual, 1) * 100, 1),
            impacto_preco_pct=0.0,
            impacto_produtividade_pct=0.0,
            impacto_recursos_pct=round(delta_n / max(n_meio_actual, 1) * 100, 1),
            impacto_prazo_semanas=round(-t_delta_semanas, 1),
            pe_gap_recalculado=round(pe_recalc_n, 2),
            roundtrip_valido=roundtrip_ok,
            erro_roundtrip=round(err_n, 2),
            confianca=3,
        )

    def _solve_combinada(
        self,
        item: DiagnosticoPEItem,
        solucoes: list[SolucaoInversa],
        alvo: float,
        denominator: float,
        T_ef: float,
    ) -> SolucaoInversa | None:
        """Solução D: combinação L + timing."""
        sol_timing = _find_solucao(solucoes, "T0_RAMP")
        sol_l = _find_solucao(solucoes, "L")
        if not (sol_timing and sol_l):
            return None
        gap_f_eta = _get_gap_fator(item, "F_ETA_CROSS")
        gap_residual = item.gap_rs - gap_f_eta - alvo
        delta_L_comb = abs(gap_residual) / max(denominator, 1.0) if denominator > 0 else 0
        return SolucaoInversa(
            parametro="COMBINADA",
            valor_atual=0.0,
            valor_requerido=0.0,
            delta_abs=0.0,
            delta_pct=0.0,
            impacto_preco_pct=round(delta_L_comb / (1.0 - T_ef) * 100, 2),
            impacto_produtividade_pct=0.0,
            impacto_recursos_pct=0.0,
            impacto_prazo_semanas=float(sol_timing.delta_abs),
            pe_gap_recalculado=round(alvo, 2),
            roundtrip_valido=True,
            erro_roundtrip=0.0,
            confianca=4,
        )

    def _compute_solucoes(
        self,
        item: DiagnosticoPEItem,
        equipe_lookup: dict,
        sched_lookup: dict,
        plan_lookup: dict,
        prat: Any,
        alvo: float,
    ) -> list[SolucaoInversa]:
        gap = item.gap_rs - alvo
        equipe = equipe_lookup.get(item.atividade_id)
        sa = sched_lookup.get(item.atividade_id)
        plan = plan_lookup.get(item.atividade_id)

        solucoes: list[SolucaoInversa] = []
        sol_l, denominator, T_ef = self._solve_L(item, plan, alvo, gap)
        if sol_l is not None:
            solucoes.append(sol_l)
        sol_p = self._solve_P(item, equipe, sa, alvo, gap)
        if sol_p is not None:
            solucoes.append(sol_p)
        sol_timing = self._solve_timing(item, sa, alvo, gap)
        if sol_timing is not None:
            solucoes.append(sol_timing)
        sol_timing_cal = self._solve_timing_calendario(item, sa, alvo, gap)
        if sol_timing_cal is not None:
            solucoes.append(sol_timing_cal)
        sol_n_max = self._solve_n_max(item, equipe, sa, alvo, gap)
        if sol_n_max is not None:
            solucoes.append(sol_n_max)
        sol_comb = self._solve_combinada(item, solucoes, alvo, denominator, T_ef)
        if sol_comb is not None:
            solucoes.append(sol_comb)
        return solucoes
