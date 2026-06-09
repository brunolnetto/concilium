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
        _aplicar_custo_instancial_adr085,
        _build_contratos_recurso,
        _build_dimensionamento,
        _build_instancias_recurso,
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
    _aplicar_custo_instancial_adr085 = _mod_a._aplicar_custo_instancial_adr085
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

    for eq in equipes:
        if eq.item_id in planejamento_map:
            plan = planejamento_map[eq.item_id]
            custo_ref = float(getattr(plan, "custo_sem_bdi", None) or 0.0)
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
    if rcpsp_spec:
        contratos_recurso, atribuicao, cadeias_perpetuacao = _build_contratos_recurso(
            equipes, rcpsp_spec, cron_lookup, validacoes,
            cpu_lookup=_cpu_lookup, prod_lookup=_prod_lookup, horas_semana=_horas_semana,
        )
        # Atualiza custo_total de cada equipe coberta pelo pool contract
        for eq in equipes:
            if eq.item_id in atribuicao:
                custo_attr, tipo_id, frac = atribuicao[eq.item_id]
                eq.custo_total_autonomo = eq.custo_total
                eq.custo_total = custo_attr
                eq.contrato_tipo_id = tipo_id
                eq.fracao_atribuicao = frac
        if contratos_recurso:
            tipos_ids = ", ".join(c.tipo_id for c in contratos_recurso)
            total_contratos = sum(c.custo_total_contrato for c in contratos_recurso)
            n_cadeias = sum(c.n_cadeias for c in contratos_recurso)
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
            _aplicar_custo_instancial_adr085(contratos_recurso, instancias_recurso, equipes, validacoes)
            _enrich_equipes_com_decomposicao_instancial(equipes, contratos_recurso, validacoes)

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

    # ADR-078: pré-processamento estrutural de compartilhamento
    relatorio_oportunidades = None
    if contratos_recurso and rcpsp_spec and rcpsp_spec.get("resource_costs"):
        relatorio_oportunidades = _build_pre_processamento_compartilhamento(
            contratos_recurso, rcpsp_spec, cron_lookup, validacoes
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


class _RepoCtx:
    """Contexto para lookups rápidos durante dimensionamento."""

    def __init__(self, repo, jurisdicao_id, overrides, data_base):
        self.repo = repo
        self.jurisdicao_id = jurisdicao_id
        self.overrides = overrides or {}
        self.data_base = data_base
