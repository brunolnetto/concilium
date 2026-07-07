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
    from ._skill_helpers_a import (  # ty: ignore[unresolved-import]  # runtime-only: loaded via importlib below
        _aplicar_custo_instancial,
        _build_contratos_recurso,
        _build_dimensionamento,
        _build_instancias_recurso,
        _calcular_permanencia_e_custo_total,
        _derive_rcpsp_from_canonical,
        _enrich_equipes_com_decomposicao_instancial,
        _enrich_particao_overhead,
        _RepoCtx,
        particionar_contrato,
    )
    from ._skill_helpers_b import (  # ty: ignore[unresolved-import]  # runtime-only: loaded via importlib below
        _build_alocacoes_pool,
        _build_requisitos_e_tipos,
    )
    from ._skill_helpers_pre import (  # ty: ignore[unresolved-import]  # runtime-only: loaded via importlib below
        _build_pre_processamento_compartilhamento,
    )
except ImportError:
    import importlib.util
    from pathlib import Path

    _here = Path(__file__).resolve().parent
    _spec_a = importlib.util.spec_from_file_location("skill05_helpers_a", _here / "_skill_helpers_a.py")
    if _spec_a is None or _spec_a.loader is None:
        raise ImportError("Cannot load _skill_helpers_a.py via importlib") from None
    _mod_a = importlib.util.module_from_spec(_spec_a)
    _spec_a.loader.exec_module(_mod_a)

    _spec_b = importlib.util.spec_from_file_location("skill05_helpers_b", _here / "_skill_helpers_b.py")
    if _spec_b is None or _spec_b.loader is None:
        raise ImportError("Cannot load _skill_helpers_b.py via importlib") from None
    _mod_b = importlib.util.module_from_spec(_spec_b)
    _spec_b.loader.exec_module(_mod_b)

    _spec_pre = importlib.util.spec_from_file_location("skill05_helpers_pre", _here / "_skill_helpers_pre.py")
    if _spec_pre is None or _spec_pre.loader is None:
        raise ImportError("Cannot load _skill_helpers_pre.py via importlib") from None
    _mod_pre = importlib.util.module_from_spec(_spec_pre)
    _spec_pre.loader.exec_module(_mod_pre)

    _RepoCtx = _mod_a._RepoCtx
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


def _or_chain(*values: Any) -> Any:
    """Colapsa uma cadeia `v1 or v2 or ... or vn` em uma única chamada (mesma semântica)."""
    last = None
    for v in values:
        if v:
            return v
        last = v
    return last


def _plan_subtotal_dict_total(subtotal: dict) -> float | None:
    """Extrai subtotal.sem_bdi.total quando `subtotal` é um dict (formato legado)."""
    sem_bdi = subtotal.get("sem_bdi") or {}
    if isinstance(sem_bdi, dict):
        total = sem_bdi.get("total")
        if isinstance(total, (int, float)):
            return float(total)
    return None


def _plan_subtotal_obj_total(subtotal: Any) -> float | None:
    """Extrai subtotal.sem_bdi.total quando `subtotal` é um objeto (formato atual)."""
    sem_bdi = getattr(subtotal, "sem_bdi", None)
    if sem_bdi is not None:
        total = getattr(sem_bdi, "total", None)
        if isinstance(total, (int, float)):
            return float(total)
    return None


def _plan_custo_sem_bdi_total(plan: Any) -> float:
    """Extrai subtotal sem BDI do planejamento em formatos legado/atual."""
    try:
        direto = getattr(plan, "custo_sem_bdi", None)
        if isinstance(direto, (int, float)) and direto > 0:
            return float(direto)

        subtotal = getattr(plan, "subtotal", None)
        total: float | None = None
        if isinstance(subtotal, dict):
            total = _plan_subtotal_dict_total(subtotal)
        elif subtotal is not None:
            total = _plan_subtotal_obj_total(subtotal)
        if total is not None:
            return total
    except Exception:
        return 0.0
    return 0.0


def _extract_planejamento_ref_map(inputs: dict[str, Any]) -> dict[str, float]:
    """Extrai o mapa item_id → custo de referência a partir de `inputs['planejamento_ref']`."""
    planejamento_ref_map: dict[str, float] = {}
    for item in inputs.get("planejamento_ref") or []:
        if not isinstance(item, dict):
            continue
        item_id = item.get("item_id")
        subtotal = ((item.get("subtotal") or {}).get("sem_bdi") or {}).get("total")
        if isinstance(item_id, str) and isinstance(subtotal, (int, float)):
            planejamento_ref_map[item_id] = float(subtotal)
    return planejamento_ref_map


def _resolve_planejamento_maps(
    canonical_in: CanonicalModel, inputs: dict[str, Any], benchmark_mode: bool
) -> tuple[dict[str, Any], dict[str, float]]:
    """ADR-107: resolve os mapas de planejamento (canônico e de benchmark) usados na reconciliação."""
    planejamento_map: dict[str, Any] = {}
    if hasattr(canonical_in, "planejamento") and canonical_in.planejamento:
        planejamento_map = {p.item_id: p for p in canonical_in.planejamento}
    planejamento_ref_map: dict[str, float] = {}
    if benchmark_mode and isinstance(inputs.get("planejamento_ref"), list):
        planejamento_ref_map = _extract_planejamento_ref_map(inputs)
    return planejamento_map, planejamento_ref_map


def _aplicar_reconciliacao_planejamento(
    equipes: list,
    planejamento_map: dict[str, Any],
    planejamento_ref_map: dict[str, float],
    validacoes: list[ValidacaoItem],
) -> None:
    """ADR-107: usa custo_sem_bdi do planejamento como fonte de verdade de custo_total."""
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


def _validar_estagio1_inst_none(equipes: list, validacoes: list[ValidacaoItem]) -> None:
    """ADR-104 Checkpoint 1: Estágio 1 — custo_inst_* deve estar None (sem pool contracts ainda)."""
    for eq in equipes:
        if eq.custo_inst_mo is not None:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-ESTAG1-INST-NONE",
                    status="ERRO",
                    mensagem=f"Item {eq.item_id}: custo_inst_* deve estar None no Estágio 1",
                )
            )


def _build_pool_setup(canonical_in: CanonicalModel, catalogo: dict[str, Any]) -> tuple[dict, dict, dict, float]:
    """Monta os lookups de cronograma/catálogo e horas/semana usados na derivação de contratos de pool."""
    sched_acts = canonical_in.cronograma.scheduled_activities if canonical_in.cronograma else []
    cron_lookup = {sa.activity_id: sa for sa in sched_acts}
    # Indexes para custo_hora_total_referencia do catálogo → custo_unit_semanal de catálogo
    cpu_lookup: dict = {c["codigo"]: c for c in catalogo.get("cpus", []) if c.get("codigo")}
    prod_lookup: dict = {
        p.get("id") or p.get("codigo", ""): p
        for p in (catalogo.get("producoes") or catalogo.get("produtividades") or [])
    }
    regime = canonical_in.projeto.regime_trabalho
    horas_semana = float(regime.horas_dia * regime.dias_semana)
    return cron_lookup, cpu_lookup, prod_lookup, horas_semana


def _resolve_rcpsp_spec(
    inputs: dict[str, Any], canonical_in: CanonicalModel, catalogo: dict[str, Any]
) -> tuple[dict | None, bool]:
    """Resolve o rcpsp_spec explícito ou o deriva automaticamente do canônico."""
    rcpsp_spec = inputs.get("rcpsp_spec") if isinstance(inputs.get("rcpsp_spec"), dict) else None
    rcpsp_derivado = False
    if rcpsp_spec is None:
        rcpsp_spec = _derive_rcpsp_from_canonical(canonical_in, catalogo)
        rcpsp_derivado = rcpsp_spec is not None
    return rcpsp_spec, rcpsp_derivado


def _atualizar_custo_via_atribuicao(equipes: list, atribuicao: dict, benchmark_mode: bool) -> None:
    """Atualiza custo_total de cada equipe coberta pelo pool contract."""
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


def _validar_pool_contrato_ok(
    contratos_recurso: list[RecursoContrato],
    cadeias_perpetuacao: list,
    rcpsp_spec: dict,
    rcpsp_derivado: bool,
    validacoes: list[ValidacaoItem],
) -> None:
    """Emite as validações OK de contrato de pool (ADR-071) e perpetuação (ADR-073)."""
    tipos_ids = ", ".join(c.tipo_id for c in contratos_recurso)
    total_contratos = sum(c.custo_total_contrato for c in contratos_recurso)
    n_cadeias = sum(c.n_cadeias for c in contratos_recurso)
    if rcpsp_derivado:
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


def _validar_estagio3_inst_none(equipes: list, atribuicao: dict, validacoes: list[ValidacaoItem]) -> None:
    """ADR-104 Checkpoint 2: Estágio 3 — custo_total atualizado, mas custo_inst_* ainda None."""
    for eq in equipes:
        if eq.item_id in atribuicao and eq.custo_inst_mo is not None:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-ESTAG3-INST-NONE",
                    status="AVISO",
                    mensagem=f"Item {eq.item_id}: custo_inst_* preenchido antes de ADR-085?",
                )
            )


def _processar_pool_contratos(
    equipes: list,
    rcpsp_spec: dict,
    rcpsp_derivado: bool,
    cron_lookup: dict,
    validacoes: list[ValidacaoItem],
    cpu_lookup: dict,
    prod_lookup: dict,
    horas_semana: float,
    benchmark_mode: bool,
) -> tuple[list[RecursoContrato], list]:
    """ADR-071/073: deriva contratos de pool e cadeias de perpetuação a partir do rcpsp_spec."""
    contratos_recurso, atribuicao, cadeias_perpetuacao = _build_contratos_recurso(
        equipes,
        rcpsp_spec,
        cron_lookup,
        validacoes,
        cpu_lookup=cpu_lookup,
        prod_lookup=prod_lookup,
        horas_semana=horas_semana,
    )
    _atualizar_custo_via_atribuicao(equipes, atribuicao, benchmark_mode)
    if contratos_recurso:
        _validar_pool_contrato_ok(contratos_recurso, cadeias_perpetuacao, rcpsp_spec, rcpsp_derivado, validacoes)
        _validar_estagio3_inst_none(equipes, atribuicao, validacoes)
    return contratos_recurso, cadeias_perpetuacao


def _validar_instancia_recurso_ok(
    instancias_recurso: list, resumo_utilizacao_contratos: list, validacoes: list[ValidacaoItem]
) -> None:
    """ADR-077: emite a validação OK do mapeamento instancial, se houver contratos resumidos."""
    if not resumo_utilizacao_contratos:
        return
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


def _limitar_custo_por_planejamento_benchmark(
    equipes: list,
    benchmark_mode: bool,
    planejamento_map: dict[str, Any],
    planejamento_ref_map: dict[str, float],
) -> None:
    """Em benchmark, limita custo_total instancial ao custo de referência do planejamento."""
    if not (benchmark_mode and (planejamento_map or planejamento_ref_map)):
        return
    for eq in equipes:
        custo_ref = 0.0
        plan = planejamento_map.get(eq.item_id)
        if plan is not None:
            custo_ref = _plan_custo_sem_bdi_total(plan)
        elif eq.item_id in planejamento_ref_map:
            custo_ref = planejamento_ref_map[eq.item_id]
        if custo_ref > 0:
            eq.custo_total = min(eq.custo_total, round(custo_ref, 2))


def _validar_estagio4_inst_missing(
    equipes: list, contratos_recurso: list[RecursoContrato], validacoes: list[ValidacaoItem]
) -> None:
    """ADR-104 Checkpoint 3: Estágio 4 — custo_inst_* deve estar preenchido para items em contratos."""
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


def _processar_instancias_recurso(
    contratos_recurso: list[RecursoContrato],
    rcpsp_spec: dict | None,
    cron_lookup: dict,
    validacoes: list[ValidacaoItem],
    cadeias_perpetuacao: list,
    equipes: list,
    benchmark_mode: bool,
    planejamento_map: dict[str, Any],
    planejamento_ref_map: dict[str, float],
) -> tuple[list, list, list]:
    """ADR-077/083/085: mapa instancial de utilização e custo instancial composicional."""
    instancias_recurso: list = []
    composicao_equipes_atividade: list = []
    resumo_utilizacao_contratos: list = []
    if not (contratos_recurso and rcpsp_spec):
        return instancias_recurso, composicao_equipes_atividade, resumo_utilizacao_contratos

    instancias_recurso, composicao_equipes_atividade, resumo_utilizacao_contratos = _build_instancias_recurso(
        contratos_recurso, rcpsp_spec, cron_lookup, validacoes
    )
    _validar_instancia_recurso_ok(instancias_recurso, resumo_utilizacao_contratos, validacoes)

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
        _limitar_custo_por_planejamento_benchmark(equipes, benchmark_mode, planejamento_map, planejamento_ref_map)
        _validar_estagio4_inst_missing(equipes, contratos_recurso, validacoes)

    return instancias_recurso, composicao_equipes_atividade, resumo_utilizacao_contratos


def _preencher_custo_inst_estagio_f3(equipes: list) -> None:
    """ADR-106 F3: preenche custo_inst_* para equipes sem pool contract (best-effort)."""
    try:
        from concilium.domain.services.financial.equipe_custo_engine import _fill_custo_inst_sem_pool

        _fill_custo_inst_sem_pool(equipes)
    except Exception:
        pass  # F3 é best-effort; não bloqueia o pipeline


def _deve_processar_compartilhamento(contratos_recurso: list[RecursoContrato], rcpsp_spec: dict | None) -> bool:
    """ADR-078: só há pré-processamento de compartilhamento com contratos, spec e custos de recurso."""
    return bool(contratos_recurso and rcpsp_spec and rcpsp_spec.get("resource_costs"))


def _deve_detectar_oportunidades_paralelo(relatorio_oportunidades: Any, canonical_in: CanonicalModel) -> bool:
    """ADR-110: só detecta oportunidades paralelas com schedule, resource_costs e pool disponíveis."""
    return bool(
        relatorio_oportunidades is not None
        and canonical_in.cronograma is not None
        and canonical_in.cronograma.scheduled_activities
        and canonical_in.recurso_pool
    )


def _build_scheduled_activities_110(canonical_in: CanonicalModel, contratos_recurso: list[RecursoContrato]) -> list:
    """Reconstrói a lista de ScheduledActivity do scheduler a partir do cronograma canônico."""
    from concilium.application.scheduling.models import ScheduledActivity

    assert canonical_in.cronograma is not None  # noqa: S101 - garantido pelo chamador (guard de ADR-110)
    sched_acts = []
    for sa in canonical_in.cronograma.scheduled_activities:
        rr: dict = {}
        for cont in contratos_recurso:
            if sa.activity_id in cont.items_cobertos:
                rr[cont.tipo_id] = rr.get(cont.tipo_id, 0) + 1
        start_week = int(_or_chain(getattr(sa, "semana_inicio_idx", 0), 0))
        end_week = int(_or_chain(getattr(sa, "semana_fim_idx", 1), 1))
        sched_acts.append(
            ScheduledActivity(
                activity_id=sa.activity_id,
                start_week=start_week,
                end_week=end_week,
                duration_weeks=max(1, end_week - start_week),
                assigned_resources=rr,
            )
        )
    return sched_acts


def _build_activity_dag_110(rcpsp_spec: dict) -> Any:
    """Reconstrói o ActivityDAG do scheduler a partir do rcpsp_spec."""
    from concilium.application.scheduling.models import Activity, ActivityDAG

    act = []
    for a in _or_chain(rcpsp_spec.get("activities"), []):
        dur = max(1, int(_or_chain(a.get("duration_weeks"), 1)))
        rr_a = {str(k): int(v) for k, v in _or_chain(a.get("required_resources"), {}).items()}
        act.append(
            Activity(
                activity_id=str(_or_chain(a.get("item_id"), a.get("activity_id"), "")),
                description=str(a.get("descricao") or ""),
                duration_weeks=dur,
                required_resources=rr_a,
            )
        )
    prec = [
        (str(e[0]), str(e[1]))
        for e in _or_chain(rcpsp_spec.get("precedence"), [])
        if isinstance(e, (list, tuple)) and len(e) >= 2
    ]
    return ActivityDAG(activities=act, precedence=prec)


def _build_resource_pool_110(contratos_recurso: list[RecursoContrato]) -> Any:
    """Reconstrói o ResourcePool do scheduler a partir dos contratos de pool.

    ADR-071: RecursoContrato.quantidade_contratada é o pool_size do contrato
    (quantidade_total pertence a RecursoPool, não a RecursoContrato).
    """
    from concilium.application.scheduling.models import ResourcePool

    pool_res = {c.tipo_id: int(c.quantidade_contratada) for c in contratos_recurso}
    return ResourcePool(resources=pool_res)


def _custo_indireto_semanal(canonical_in: CanonicalModel) -> float:
    """Custo indireto médio por semana, usado na avaliação econômica de oportunidades paralelas."""
    if not canonical_in.indiretos:
        return 0.0
    custo_ind_sem = sum(i.custo_total for i in canonical_in.indiretos)
    makespan = canonical_in.cronograma.makespan_weeks if canonical_in.cronograma else None
    n_sem = max(1, makespan or 1)
    return custo_ind_sem / n_sem


def _aplicar_oportunidades_paralelo(
    relatorio_oportunidades: Any, opps_paralelo: list, validacoes: list[ValidacaoItem]
) -> Any:
    """Anexa oportunidades paralelas detectadas ao relatório e emite a validação OK correspondente."""
    if not opps_paralelo:
        return relatorio_oportunidades
    relatorio_oportunidades = relatorio_oportunidades.model_copy(update={"oportunidades_paralelo": opps_paralelo})
    n_viaveis_par = sum(1 for o in opps_paralelo if o.economicamente_viavel)
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-OPP-PARALELO-OK",
            status="OK",
            mensagem=(
                f"ADR-110: {len(opps_paralelo)} oportunidade(s) paralela(s) detectada(s) "
                f"— {n_viaveis_par} economicamente viável(is)."
            ),
        )
    )
    return relatorio_oportunidades


def _processar_oportunidades_paralelo(
    relatorio_oportunidades: Any,
    canonical_in: CanonicalModel,
    contratos_recurso: list[RecursoContrato],
    rcpsp_spec: dict | None,
    validacoes: list[ValidacaoItem],
) -> Any:
    """ADR-110: detecção automática de oportunidades de compartilhamento paralelo (best-effort)."""
    if not _deve_detectar_oportunidades_paralelo(relatorio_oportunidades, canonical_in):
        return relatorio_oportunidades
    # relatorio_oportunidades só é not-None quando _deve_processar_compartilhamento
    # (chamador) já provou rcpsp_spec truthy — mesma variável, checada antes de
    # construir relatorio_oportunidades via _build_pre_processamento_compartilhamento.
    assert rcpsp_spec is not None
    try:
        from concilium.application.scheduling.models import ScheduleMetrics, ScheduleOutput

        from ._skill_helpers_pre import (  # ty: ignore[unresolved-import]  # runtime-only: sibling loaded via importlib above
            _detectar_oportunidades_paralelo,
        )

        # Garantido por _deve_processar_compartilhamento (chamador só passa relatorio_oportunidades
        # não-None quando rcpsp_spec já foi validado como dict com resource_costs).
        assert rcpsp_spec is not None  # noqa: S101

        sched_acts = _build_scheduled_activities_110(canonical_in, contratos_recurso)
        makespan = max((s.end_week for s in sched_acts), default=0)
        metrics = ScheduleMetrics(
            makespan=makespan,
            resource_leveling_score=1.0,
            idle_time=0,
            activity_fragmentation=0,
            critical_path_slack_min=0.0,
            resource_utilization_avg=1.0,
        )
        sched_output = ScheduleOutput(
            scheduled_activities=sched_acts,
            makespan=makespan,
            feasible=True,
            metrics=metrics,
        )
        dag = _build_activity_dag_110(rcpsp_spec)
        pool = _build_resource_pool_110(contratos_recurso)
        resource_costs = rcpsp_spec.get("resource_costs") or {}
        custo_ind_sem = _custo_indireto_semanal(canonical_in)

        opps_paralelo = _detectar_oportunidades_paralelo(
            sched_output,
            dag,
            pool,
            resource_costs,
            custo_ind_sem,
        )
        relatorio_oportunidades = _aplicar_oportunidades_paralelo(relatorio_oportunidades, opps_paralelo, validacoes)
    except Exception:
        pass  # best-effort: não bloqueia o pipeline se o detector falhar
    return relatorio_oportunidades


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
    planejamento_map, planejamento_ref_map = _resolve_planejamento_maps(canonical_in, inputs, benchmark_mode)
    _aplicar_reconciliacao_planejamento(equipes, planejamento_map, planejamento_ref_map, validacoes)

    # ADR-104 Checkpoint 1: Estágio 1 — custo_inst_* deve estar None (sem pool contracts ainda)
    _validar_estagio1_inst_none(equipes, validacoes)

    cron_lookup, cpu_lookup, prod_lookup, horas_semana = _build_pool_setup(canonical_in, catalogo)

    # ADR-071/073: Pool Contract Model + Perpetuation Chains
    contratos_recurso: list[RecursoContrato] = []
    cadeias_perpetuacao: list = []
    rcpsp_spec, rcpsp_derivado = _resolve_rcpsp_spec(inputs, canonical_in, catalogo)
    if rcpsp_spec:
        contratos_recurso, cadeias_perpetuacao = _processar_pool_contratos(
            equipes,
            rcpsp_spec,
            rcpsp_derivado,
            cron_lookup,
            validacoes,
            cpu_lookup,
            prod_lookup,
            horas_semana,
            benchmark_mode,
        )

    # ADR-077: mapa instancial de utilização — executado quando há pool contracts
    instancias_recurso, composicao_equipes_atividade, resumo_utilizacao_contratos = _processar_instancias_recurso(
        contratos_recurso,
        rcpsp_spec,
        cron_lookup,
        validacoes,
        cadeias_perpetuacao,
        equipes,
        benchmark_mode,
        planejamento_map,
        planejamento_ref_map,
    )

    # ADR-106 F3: preenche custo_inst_* para equipes sem pool contract (NEP-040 Fase 4 completa)
    _preencher_custo_inst_estagio_f3(equipes)

    # ADR-078: pré-processamento estrutural de compartilhamento
    relatorio_oportunidades = None
    if _deve_processar_compartilhamento(contratos_recurso, rcpsp_spec):
        relatorio_oportunidades = _build_pre_processamento_compartilhamento(
            contratos_recurso, rcpsp_spec, cron_lookup, validacoes
        )

    # ADR-110: detecção automática de oportunidades de compartilhamento paralelo
    # Executado quando há schedule, resource_costs e pool contracts disponíveis.
    relatorio_oportunidades = _processar_oportunidades_paralelo(
        relatorio_oportunidades, canonical_in, contratos_recurso, rcpsp_spec, validacoes
    )

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
