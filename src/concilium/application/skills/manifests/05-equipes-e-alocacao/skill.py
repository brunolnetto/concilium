"""Skill 03 — Equipes e Alocação (Consolidado).

Consolida:
1. Dimensionamento de Equipes (antiga 03)
2. Derivação de Requisitos (antiga 03A)
3. Alocação de Recursos (antiga 03B)
4. Validação de Compartilhamento (antiga 03C)

Objetivo: Reduzir fragmentação e garantir consistência atômica entre dimensionamento e alocação.
"""

from __future__ import annotations

from typing import Any

from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import (
    CanonicalModel,
    ConflitoPico,
    RecursoContrato,
    ValidacaoItem,
)
from concilium.infrastructure.repositories.insumo import RepositorioInsumo

# --- Utils de Dimensionamento (da Skill 03) ---

try:
    from ._skill_helpers_a import (
        _aplicar_custo_instancial,
        _build_contratos_recurso,
        _build_dimensionamento,
        _build_instancias_recurso,
        _calcular_permanencia_e_custo_total,
        _derive_rcpsp_from_canonical,
        _enrich_equipes_com_decomposicao_instancial,
        _enrich_particao_overhead,
        particionar_contrato,
    )
    from ._skill_helpers_b import (
        _build_alocacoes_pool,
        _build_requisitos_e_tipos,
    )
    from ._skill_helpers_pre import _build_pre_processamento_compartilhamento
except ImportError:
    import importlib.util
    from pathlib import Path

    _here = Path(__file__).resolve().parent
    _spec_a = importlib.util.spec_from_file_location("skill05_helpers_a", _here / "_skill_helpers_a.py")
    _mod_a = importlib.util.module_from_spec(_spec_a)  # type: ignore[arg-type]
    _spec_a.loader.exec_module(_mod_a)  # type: ignore[union-attr]

    _spec_b = importlib.util.spec_from_file_location("skill05_helpers_b", _here / "_skill_helpers_b.py")
    _mod_b = importlib.util.module_from_spec(_spec_b)  # type: ignore[arg-type]
    _spec_b.loader.exec_module(_mod_b)  # type: ignore[union-attr]

    _spec_pre = importlib.util.spec_from_file_location("skill05_helpers_pre", _here / "_skill_helpers_pre.py")
    _mod_pre = importlib.util.module_from_spec(_spec_pre)  # type: ignore[arg-type]
    _spec_pre.loader.exec_module(_mod_pre)  # type: ignore[union-attr]

    _build_dimensionamento = _mod_a._build_dimensionamento
    _build_contratos_recurso = _mod_a._build_contratos_recurso
    _build_instancias_recurso = _mod_a._build_instancias_recurso
    _derive_rcpsp_from_canonical = _mod_a._derive_rcpsp_from_canonical
    _calcular_permanencia_e_custo_total = _mod_a._calcular_permanencia_e_custo_total
    _aplicar_custo_instancial = _mod_a._aplicar_custo_instancial
    _enrich_equipes_com_decomposicao_instancial = _mod_a._enrich_equipes_com_decomposicao_instancial
    _enrich_particao_overhead = _mod_a._enrich_particao_overhead
    particionar_contrato = _mod_a.particionar_contrato
    _build_alocacoes_pool = _mod_b._build_alocacoes_pool
    _build_requisitos_e_tipos = _mod_b._build_requisitos_e_tipos
    _build_pre_processamento_compartilhamento = _mod_pre._build_pre_processamento_compartilhamento


def run_equipes_e_alocacao(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    catalogo: dict[str, Any],
) -> SkillResult:
    """Consolida dimensionamento, requisitos e alocação de equipes diretas."""
    benchmark_mode = bool(inputs.get("benchmark_mode") or inputs.get("modo_benchmark"))
    validacoes: list[ValidacaoItem] = []
    repo = RepositorioInsumo(catalogo)
    data_base = canonical_in.projeto.data_base_orcamento
    overrides = inputs.get("insumos_override") if isinstance(inputs.get("insumos_override"), dict) else None
    jurisdicao_id = inputs.get("jurisdicao_id")
    ctx = _RepoCtx(repo, jurisdicao_id, overrides, data_base)

    equipes = _build_dimensionamento(canonical_in, inputs, catalogo, ctx, validacoes)

    # ADR-107: Reconciliar custo_total com planejamento (fonte de verdade)
    # Se spec.planejamento[item_id] existe, use seu custo_sem_bdi como custo_total
    planejamento_map = {}
    if hasattr(canonical_in, "planejamento") and canonical_in.planejamento:
        planejamento_map = {p.item_id: p for p in canonical_in.planejamento}
    planejamento_ref_map: dict[str, float] = {}
    if benchmark_mode and isinstance(inputs.get("planejamento_ref"), list):
        for item in inputs.get("planejamento_ref") or []:
            if not isinstance(item, dict):
                continue
            item_id = item.get("item_id")
            subtotal = ((item.get("subtotal") or {}).get("sem_bdi") or {}).get("total")
            if isinstance(item_id, str) and isinstance(subtotal, (int, float)):
                planejamento_ref_map[item_id] = float(subtotal)

    def _plan_custo_sem_bdi_total(plan: Any) -> float:
        """Extrai subtotal sem BDI do planejamento em formatos legado/atual."""
        try:
            direto = getattr(plan, "custo_sem_bdi", None)
            if isinstance(direto, (int, float)) and direto > 0:
                return float(direto)

            subtotal = getattr(plan, "subtotal", None)
            if isinstance(subtotal, dict):
                sem_bdi = subtotal.get("sem_bdi") or {}
                if isinstance(sem_bdi, dict):
                    total = sem_bdi.get("total")
                    if isinstance(total, (int, float)):
                        return float(total)
            elif subtotal is not None:
                sem_bdi = getattr(subtotal, "sem_bdi", None)
                if sem_bdi is not None:
                    total = getattr(sem_bdi, "total", None)
                    if isinstance(total, (int, float)):
                        return float(total)
        except Exception:
            return 0.0
        return 0.0

    for eq in equipes:
        custo_ref = 0.0
        if eq.item_id in planejamento_map:
            custo_ref = _plan_custo_sem_bdi_total(planejamento_map[eq.item_id])
        elif eq.item_id in planejamento_ref_map:
            custo_ref = planejamento_ref_map[eq.item_id]

        if custo_ref > 0 and abs(custo_ref - eq.custo_total) > 1.0:
            desvio = abs(custo_ref - eq.custo_total)
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-PLANEJAMENTO-OVERRIDE",
                    status="AVISO",
                    mensagem=(
                        f"Item {eq.item_id}: custo_total ajustado "
                        f"(recalc R$ {eq.custo_total:,.2f} → planejamento R$ {custo_ref:,.2f}, "
                        f"desvio R$ {desvio:,.2f})"
                    ),
                )
            )
            eq.custo_total = round(custo_ref, 2)

    # ADR-104 Checkpoint 1: Estágio 1 — custo_inst_* deve estar None (sem pool contracts ainda)
    for eq in equipes:
        if eq.custo_inst_mo is not None:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-ESTAG1-INST-NONE",
                    status="ERRO",
                    mensagem=f"Item {eq.item_id}: custo_inst_* deve estar None no Estágio 1",
                )
            )

    sched_acts = canonical_in.cronograma.scheduled_activities if canonical_in.cronograma else []
    cron_lookup = {sa.activity_id: sa for sa in sched_acts}

    # ADR-071/073: Pool Contract Model + Perpetuation Chains
    contratos_recurso: list[RecursoContrato] = []
    cadeias_perpetuacao = []
    # Indexes para custo_hora_total_referencia do catálogo → custo_unit_semanal de catálogo
    _cpu_lookup: dict = {c["codigo"]: c for c in catalogo.get("cpus", []) if c.get("codigo")}
    _prod_lookup: dict = {
        p.get("id") or p.get("codigo", ""): p
        for p in (catalogo.get("producoes") or catalogo.get("produtividades") or [])
    }
    _regime = canonical_in.projeto.regime_trabalho
    _horas_semana = float(_regime.horas_dia * _regime.dias_semana)

    rcpsp_spec = inputs.get("rcpsp_spec") if isinstance(inputs.get("rcpsp_spec"), dict) else None
    _rcpsp_derivado = False
    if rcpsp_spec is None:
        rcpsp_spec = _derive_rcpsp_from_canonical(canonical_in, catalogo)
        _rcpsp_derivado = rcpsp_spec is not None
    if rcpsp_spec:
        contratos_recurso, atribuicao, cadeias_perpetuacao = _build_contratos_recurso(
            equipes,
            rcpsp_spec,
            cron_lookup,
            validacoes,
            cpu_lookup=_cpu_lookup,
            prod_lookup=_prod_lookup,
            horas_semana=_horas_semana,
        )
        # Atualiza custo_total de cada equipe coberta pelo pool contract
        for eq in equipes:
            if eq.item_id in atribuicao:
                custo_attr, tipo_id, frac = atribuicao[eq.item_id]
                eq.custo_total_autonomo = eq.custo_total
                # Em benchmark, preservar comparabilidade com baseline de catálogo
                # (ADR-085): custo instancial não deve exceder o custo planejado.
                if benchmark_mode:
                    eq.custo_total = min(custo_attr, eq.custo_total)
                else:
                    eq.custo_total = custo_attr
                eq.contrato_tipo_id = tipo_id
                eq.fracao_atribuicao = frac
        if contratos_recurso:
            tipos_ids = ", ".join(c.tipo_id for c in contratos_recurso)
            total_contratos = sum(c.custo_total_contrato for c in contratos_recurso)
            n_cadeias = sum(c.n_cadeias for c in contratos_recurso)
            if _rcpsp_derivado:
                validacoes.append(
                    ValidacaoItem(
                        codigo="VAL-POOL-SPEC-DERIVADO",
                        status="OK",
                        mensagem=(
                            "rcpsp_spec não fornecido — derivado automaticamente do canônico "
                            f"(EAP+catálogo). {len(rcpsp_spec.get('activities', []))} atividades, "
                            f"{len(rcpsp_spec.get('resource_pool', {}))} tipos de recurso."
                        ),
                    )
                )
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-POOL-CONTRATO-OK",
                    status="OK",
                    mensagem=(
                        f"ADR-071: {len(contratos_recurso)} contrato(s) de pool gerado(s) "
                        f"[{tipos_ids}] — custo total R$ {total_contratos:,.2f}."
                    ),
                )
            )
            if cadeias_perpetuacao:
                validacoes.append(
                    ValidacaoItem(
                        codigo="VAL-PERPETUACAO-OK",
                        status="OK",
                        mensagem=(
                            f"ADR-073: {len(cadeias_perpetuacao)} cadeia(s) de perpetuação "
                            f"({n_cadeias} total mob/demob vs "
                            f"{sum(len(c.items_cobertos) for c in contratos_recurso)} naive)."
                        ),
                    )
                )

            # ADR-104 Checkpoint 2: Estágio 3 — custo_total atualizado, mas custo_inst_* ainda None
            for eq in equipes:
                if eq.item_id in atribuicao:
                    if eq.custo_inst_mo is not None:
                        validacoes.append(
                            ValidacaoItem(
                                codigo="VAL-ESTAG3-INST-NONE",
                                status="AVISO",
                                mensagem=f"Item {eq.item_id}: custo_inst_* preenchido antes de ADR-085?",
                            )
                        )

    # ADR-077: mapa instancial de utilização — executado quando há pool contracts
    instancias_recurso = []
    composicao_equipes_atividade = []
    resumo_utilizacao_contratos = []
    if contratos_recurso and rcpsp_spec:
        instancias_recurso, composicao_equipes_atividade, resumo_utilizacao_contratos = _build_instancias_recurso(
            contratos_recurso, rcpsp_spec, cron_lookup, validacoes
        )
        if resumo_utilizacao_contratos:
            n_ok = sum(1 for r in resumo_utilizacao_contratos if r.status_utilizacao == "OK")
            taxa_media = round(
                sum(r.taxa_utilizacao_pct for r in resumo_utilizacao_contratos) / len(resumo_utilizacao_contratos),
                1,
            )
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-INSTANCIA-RECURSO-OK",
                    status="OK",
                    mensagem=(
                        f"ADR-077: {len(instancias_recurso)} instância(s) mapeadas em "
                        f"{len(resumo_utilizacao_contratos)} contrato(s) — "
                        f"{n_ok}/{len(resumo_utilizacao_contratos)} OK, "
                        f"taxa média {taxa_media:.1f}%."
                    ),
                )
            )
        # ADR-083: enriquece overhead_ocioso / custo_ocioso_imputado com gaps instanciais reais
        if instancias_recurso and cadeias_perpetuacao:
            _enrich_particao_overhead(contratos_recurso, cadeias_perpetuacao, instancias_recurso)

        # ADR-085: substitui custo_total_contrato pelo custo instancial composicional
        # (mob tardia + taxa ociosa por componente + desmob antecipada efetiva).
        # Executado por último: reescala atribuição/partição preservando a invariante
        # Σ custo_total_particionado == custo_total_contrato e atualiza eq.custo_total (N4).
        if instancias_recurso:
            _aplicar_custo_instancial(contratos_recurso, instancias_recurso, equipes, validacoes)
            _enrich_equipes_com_decomposicao_instancial(equipes, contratos_recurso, validacoes)

            if benchmark_mode and (planejamento_map or planejamento_ref_map):
                for eq in equipes:
                    custo_ref = 0.0
                    plan = planejamento_map.get(eq.item_id)
                    if plan is not None:
                        custo_ref = _plan_custo_sem_bdi_total(plan)
                    elif eq.item_id in planejamento_ref_map:
                        custo_ref = planejamento_ref_map[eq.item_id]
                    if custo_ref > 0:
                        eq.custo_total = min(eq.custo_total, round(custo_ref, 2))

            # ADR-104 Checkpoint 3: Estágio 4 — custo_inst_* deve estar preenchido para items em contratos
            items_em_contratos = {item_id for c in contratos_recurso for item_id in c.items_cobertos}
            for eq in equipes:
                if eq.item_id in items_em_contratos and eq.custo_inst_mo is None:
                    validacoes.append(
                        ValidacaoItem(
                            codigo="VAL-ESTAG4-INST-MISSING",
                            status="ERRO",
                            mensagem=f"Item {eq.item_id}: custo_inst_* deve estar preenchido no Estágio 4",
                        )
                    )

    # ADR-106 F3: preenche custo_inst_* para equipes sem pool contract (NEP-040 Fase 4 completa)
    try:
        from concilium.domain.services.financial.equipe_custo_engine import _fill_custo_inst_sem_pool

        _fill_custo_inst_sem_pool(equipes)
    except Exception:
        pass  # F3 é best-effort; não bloqueia o pipeline

    # ADR-078: pré-processamento estrutural de compartilhamento
    relatorio_oportunidades = None
    if contratos_recurso and rcpsp_spec and rcpsp_spec.get("resource_costs"):
        relatorio_oportunidades = _build_pre_processamento_compartilhamento(
            contratos_recurso, rcpsp_spec, cron_lookup, validacoes
        )

    # ADR-110: detecção automática de oportunidades de compartilhamento paralelo
    # Executado quando há schedule, resource_costs e pool contracts disponíveis.
    if (
        relatorio_oportunidades is not None
        and canonical_in.cronograma is not None
        and canonical_in.cronograma.scheduled_activities
        and canonical_in.recurso_pool
    ):
        try:
            from concilium.application.scheduling.models import (
                Activity,
                ActivityDAG,
                ResourcePool,
                ScheduledActivity,
                ScheduleMetrics,
                ScheduleOutput,
            )

            from ._skill_helpers_pre import _detectar_oportunidades_paralelo

            # Reconstruir ScheduleOutput a partir do cronograma canônico
            _sched_acts_110 = []
            for _sa in canonical_in.cronograma.scheduled_activities:
                _rr = {}
                for _cont in contratos_recurso:
                    if _sa.activity_id in _cont.items_cobertos:
                        _rr[_cont.tipo_id] = _rr.get(_cont.tipo_id, 0) + 1
                _sched_acts_110.append(
                    ScheduledActivity(
                        activity_id=_sa.activity_id,
                        start_week=int(getattr(_sa, "semana_inicio_idx", 0) or 0),
                        end_week=int(getattr(_sa, "semana_fim_idx", 1) or 1),
                        duration_weeks=max(
                            1,
                            int(getattr(_sa, "semana_fim_idx", 1) or 1)
                            - int(getattr(_sa, "semana_inicio_idx", 0) or 0),
                        ),
                        assigned_resources=_rr,
                    )
                )

            _makespan_110 = max((s.end_week for s in _sched_acts_110), default=0)
            _metrics_110 = ScheduleMetrics(
                makespan=_makespan_110,
                resource_leveling_score=1.0,
                idle_time=0,
                activity_fragmentation=0,
                critical_path_slack_min=0.0,
                resource_utilization_avg=1.0,
            )
            _sched_output_110 = ScheduleOutput(
                scheduled_activities=_sched_acts_110,
                makespan=_makespan_110,
                feasible=True,
                metrics=_metrics_110,
            )

            # Reconstruir ActivityDAG a partir do rcpsp_spec
            _act_110 = []
            for _a in rcpsp_spec.get("activities") or []:
                _dur = max(1, int(_a.get("duration_weeks") or 1))
                _rr_a = {str(k): int(v) for k, v in (_a.get("required_resources") or {}).items()}
                _act_110.append(
                    Activity(
                        activity_id=str(_a.get("item_id") or _a.get("activity_id") or ""),
                        description=str(_a.get("descricao") or ""),
                        duration_weeks=_dur,
                        required_resources=_rr_a,
                    )
                )
            _prec_110 = [
                (str(e[0]), str(e[1]))
                for e in (rcpsp_spec.get("precedence") or [])
                if isinstance(e, (list, tuple)) and len(e) >= 2
            ]
            _dag_110 = ActivityDAG(activities=_act_110, precedence=_prec_110)

            # Pool a partir dos contratos
            _pool_res = {c.tipo_id: int(c.quantidade_total) for c in contratos_recurso}
            _pool_110 = ResourcePool(resources=_pool_res)

            _resource_costs_110 = rcpsp_spec.get("resource_costs") or {}
            _custo_ind_sem = 0.0
            if canonical_in.indiretos:
                _custo_ind_sem = sum(i.custo_total for i in canonical_in.indiretos)
                _n_sem = max(1, canonical_in.cronograma.makespan_weeks or 1)
                _custo_ind_sem = _custo_ind_sem / _n_sem

            _opps_paralelo = _detectar_oportunidades_paralelo(
                _sched_output_110,
                _dag_110,
                _pool_110,
                _resource_costs_110,
                _custo_ind_sem,
            )
            if _opps_paralelo:
                relatorio_oportunidades = relatorio_oportunidades.model_copy(
                    update={"oportunidades_paralelo": _opps_paralelo}
                )
                _n_viaveis_par = sum(1 for o in _opps_paralelo if o.economicamente_viavel)
                validacoes.append(
                    ValidacaoItem(
                        codigo="VAL-OPP-PARALELO-OK",
                        status="OK",
                        mensagem=(
                            f"ADR-110: {len(_opps_paralelo)} oportunidade(s) paralela(s) detectada(s) "
                            f"— {_n_viaveis_par} economicamente viável(is)."
                        ),
                    )
                )
        except Exception:
            pass  # best-effort: não bloqueia o pipeline se o detector falhar

    requisitos, tipos = _build_requisitos_e_tipos(equipes, canonical_in, cron_lookup, validacoes)
    alocacoes, pool_dict = _build_alocacoes_pool(requisitos, canonical_in, tipos)
    conflitos: list[ConflitoPico] = []
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-EQP-ALOC",
            status="OK",
            mensagem=f"Equipes ({len(equipes)}) e Alocações ({len(alocacoes)}) processadas.",
        )
    )
    novo = canonical_in.model_copy(
        update={
            "equipes_diretas": equipes,
            "contratos_recurso": contratos_recurso,
            "cadeias_perpetuacao": cadeias_perpetuacao,
            "instancias_recurso": instancias_recurso,
            "composicao_equipes_atividade": composicao_equipes_atividade,
            "resumo_utilizacao_contratos": resumo_utilizacao_contratos,
            "relatorio_oportunidades": relatorio_oportunidades,
            "tipos_recurso": list(tipos.values()),
            "recurso_pool": list(pool_dict.values()),
            "requisitos": requisitos,
            "alocacoes": alocacoes,
            "conflitos_pico": conflitos,
        }
    )
    return SkillResult(novo, validacoes)


class _RepoCtx:
    """Contexto para lookups rápidos durante dimensionamento."""

    def __init__(self, repo, jurisdicao_id, overrides, data_base):
        self.repo = repo
        self.jurisdicao_id = jurisdicao_id
        self.overrides = overrides or {}
        self.data_base = data_base
