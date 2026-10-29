"""Camada 4 — Modelo canônico do orçamento (parte extraída de canonical.py)."""

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from concilium.domain.models.analytics.analitica import CurvaABCInsumo, SCurve
from concilium.domain.models.analytics.cubo_analitico import CuboAnalitico
from concilium.domain.models.analytics.diagnostico_pe import DiagnosticoPERelatorio
from concilium.domain.models.campaign.campanha_equipamento import AnaliseFrequenciaCampanhas
from concilium.domain.models.financial.backtracking_pe import BacktrackingPERelatorio
from concilium.domain.models.financial.bdi import IndiretoComBdi, TabelaBdi
from concilium.domain.models.financial.memorial_bdi import MemorialCalculoBDI
from concilium.domain.models.planning.calendario_operacional import CalendarioOperacionalSemanal
from concilium.domain.models.planning.mobilizacao import CurvaForca
from concilium.domain.models.project.constraint_violation import ConstraintViolation
from concilium.domain.models.project.decision_variables import DecisionVariables

from ._base import Meta, Praticabilidade, Projeto
from ._eap import ActivityDag, Atividade, AtividadeIntervalo, EapItem
from ._equipes_diretas import EquipeDireta
from ._estoque_consumiveis import RecursoConsumivelCanonical, ResumoEstoqueConsumivel
from ._financeiro_resultado import Indireto, Planejamento, PontoEquilibrio, Resultado
from ._indiretos_insumos import AtividadeCustoCompleto, Cronograma, IndiretoSemanal, _migrate_cron_list_to_cronograma
from ._pool_recursos import (
    Alocacao,
    CadeiaPerpetuacao,
    ComposicaoEquipeAtividade,
    ConflitoPico,
    InstanciaRecurso,
    RecursoContrato,
    RecursoPool,
    RelatorioOportunidades,
    RequisitoRecurso,
    ResumoUtilizacaoContrato,
    TipoRecurso,
)
from ._replan_criticidade import (
    CostCriticalityResult,
    CpuExposurePerfil,
    PlanSpaceResult,
    ReplanSuggestions,
    ResultadoReconciliado,
)

if TYPE_CHECKING:
    # ADR-026: resolvidos em tempo de execução via canonical/__init__.py (import
    # tardio + CanonicalModel.model_rebuild()) para evitar import circular com reports.py.
    from concilium.domain.models.reports import (
        RelatorioCriticidade,
        RelatorioIntervencao,
        RelatorioSensibilidade,
    )


class CanonicalModel(BaseModel):
    """Estado completo do orçamento — produzido incrementalmente pelo pipeline."""

    model_config = ConfigDict(extra="ignore")

    meta: Meta
    projeto: Projeto
    praticabilidade: Praticabilidade | None = None
    # ADR-068: artefato semanal consolidado de disponibilidade civil.
    calendario_operacional: list[CalendarioOperacionalSemanal] = Field(default_factory=list)
    fator_calendario_semanal: dict[str, float] = Field(default_factory=dict)
    eap: list[EapItem] = Field(default_factory=list)
    atividades: list[Atividade] | None = None
    intervalos_atividade: list[AtividadeIntervalo] = Field(
        default_factory=list,
        description="Unidades atômicas de execução (semana × atividade × equipe). "
        "Derivado de cronograma.scheduled_activities via AtividadeIntervalo.from_scheduled_activity().",
    )
    activity_dag: ActivityDag | None = None
    cronograma: Cronograma | None = None  # Unified weekly schedule (was: list[Cronograma])
    equipes_diretas: list[EquipeDireta] = Field(default_factory=list)
    planejamento: list[Planejamento] = Field(default_factory=list)
    indiretos: list[Indireto] = Field(default_factory=list)
    indiretos_semanal: list[IndiretoSemanal] = Field(default_factory=list)
    # ADR-023 §D4: custos indiretos com BDI-INDIRETO aplicado (skill 05 -> Phase 3)
    indiretos_com_bdi: list["IndiretoComBdi"] = Field(default_factory=list)
    custos_atividades: list[AtividadeCustoCompleto] = Field(default_factory=list)
    ponto_equilibrio: list[PontoEquilibrio] = Field(default_factory=list)
    resultado: Resultado | None = None

    # Fase 1B — reports analíticos
    criticality_report: dict | None = None
    cost_criticality_report: "CostCriticalityResult | None" = None

    # Fase 2 — resource binding
    tipos_recurso: list[TipoRecurso] = Field(default_factory=list)
    recurso_pool: list[RecursoPool] = Field(default_factory=list)
    # ADR-071: contratos de pool — produzidos pelo skill-05 quando rcpsp_spec presente
    contratos_recurso: list[RecursoContrato] = Field(default_factory=list)
    # ADR-073: cadeias de perpetuação — produzidas junto com contratos_recurso
    cadeias_perpetuacao: list[CadeiaPerpetuacao] = Field(default_factory=list)
    # ADR-077: recurso instancial — mapa de utilização por slot de contrato
    instancias_recurso: list[InstanciaRecurso] = Field(default_factory=list)
    composicao_equipes_atividade: list[ComposicaoEquipeAtividade] = Field(default_factory=list)
    resumo_utilizacao_contratos: list[ResumoUtilizacaoContrato] = Field(default_factory=list)
    # ADR-128 F6: contabilização de consumíveis (paridade com pool) — produzidos por skill-04
    # quando ao menos um ReplenishableResource é construído (opt-in, ver ADR-128 F5).
    recursos_consumiveis: list[RecursoConsumivelCanonical] = Field(default_factory=list)
    resumo_estoque_consumiveis: list[ResumoEstoqueConsumivel] = Field(default_factory=list)
    # ADR-078: pré-processamento estrutural de compartilhamento
    relatorio_oportunidades: RelatorioOportunidades | None = None
    requisitos: list[RequisitoRecurso] = Field(default_factory=list)
    alocacoes: list[Alocacao] = Field(default_factory=list)
    conflitos_pico: list[ConflitoPico] = Field(default_factory=list)

    # Structured constraint violations introduced in v2.5
    constraint_violations: list[ConstraintViolation] = Field(default_factory=list)

    # Decision variables — persisted in canonical for traceability (v2.5)
    decision_variables: DecisionVariables | None = None

    # ADR-003: Weekly progress tracking (append-only per activity_id)
    progresso: dict[str, list] = Field(default_factory=dict)

    # ADR-005: Replanning history (immutable audit trail)
    replanning_history: list[dict] = Field(default_factory=list)

    # ADR-019: Reconciliação de custos de aquisição e sugestões de re-planejamento
    resultado_reconciliado: "ResultadoReconciliado | None" = None
    replan_suggestions: "ReplanSuggestions | None" = None
    # P18-C3: opt-in, read-only physical-consumption preview from Skill04 + the
    # exact Skill05 pool witness. This sidecar never overrides legacy finance
    # or authorizes PROJECT_GO.
    p18_consumption_preview: dict[str, object] | None = None
    # P17-C: exact read-only Skill05 pool vs Skill06 activity-cost reconciliation.
    p17_cost_reconciliation: dict[str, object] | None = None

    # ADR-021: Espaço combinatorial de planos (repair + otimização de VERDE)
    plan_space_result: "PlanSpaceResult | None" = None

    # ADR-026: Relatórios analíticos da fase Saída-Analítica (skills 15/16/17)
    relatorio_criticidade: "RelatorioCriticidade | None" = None
    relatorio_sensibilidade: "RelatorioSensibilidade | None" = None
    relatorio_intervencao: "RelatorioIntervencao | None" = None

    # ADR-022: Wave execution — taint marking para falhas de skills GATE.
    # pipeline_blocked_from: skills GATE que falharam; distingue "campo vazio por falha"
    # de "campo vazio legítimo" (ex: equipes_diretas=[] por ausência de equipes no escopo).
    # pipeline_integridade: CORROMPIDO quando qualquer GATE falhou; PARCIAL quando só
    # ADVISORY falhou; COMPLETO quando todas as GATE executaram com sucesso.
    pipeline_blocked_from: list[str] = Field(default_factory=list)
    pipeline_integridade: Literal["COMPLETO", "PARCIAL", "CORROMPIDO"] | None = None

    # ADR-027: Perfis de exposição a custos por CPU (calculados por skill 09)
    cpu_exposure_perfis: list["CpuExposurePerfil"] = Field(default_factory=list)

    # ADR-039: Análise de compensação de ineficiências estruturais (The Bridge)
    # Calculada pela Skill 06 — dict serializado para manter CanonicalModel estável.
    bridge_analysis: dict | None = None

    # Benchmark-only traceability: preserves raw inputs, calibrated outputs and errors.
    benchmark_alignment: dict | None = None

    # ADR-060/061: Diagnóstico causal do PE e backtracking de soluções inversas.
    diagnostico_pe: "DiagnosticoPERelatorio | None" = None
    backtracking_pe: "BacktrackingPERelatorio | None" = None

    # ADR-058: Artefatos analíticos do espaço ontológico.
    curva_abc_insumo: "CurvaABCInsumo | None" = None
    s_curve: "SCurve | None" = None
    cubo_analitico: "CuboAnalitico | None" = None  # cubo 4D: categoria×atividade×tempo×BDI
    # Tabela BDI efetiva usada para construir cubo_analitico e calcular preços (skill-06).
    # Persistida para garantir que o lazy-build do serviço e o _build_from_pool (ADR-086)
    # usem exatamente a mesma formulação BDI — elimina divergência entre pipeline e on-demand.
    # Usa forward ref para evitar import circular com o módulo bdi.
    tabela_bdi_efetiva: TabelaBdi | None = None

    # ADR-059: Campanhas de permanência de equipamentos.
    analise_campanhas: "AnaliseFrequenciaCampanhas | None" = None

    # ADR-057: Memorial de cálculo BDI — artefato de auditoria ponta a ponta.
    # Gerado pela skill-06. Exportado como JSON e aba Excel MEMORIAL.BDI.
    # Re-derivável de (bdi_tabela, planejamento, resultado) — persistência é cache auditável.
    memorial_calculo_bdi: "MemorialCalculoBDI | None" = None

    # ADR-054: Curvas de força derivadas de políticas de mobilização.
    # Campo opcional — presente apenas quando WMP foi aplicado no run.
    # Re-derivável deterministicamente de (policy, Q, P, regime, prat_semanal).
    # Persiste como artefato de auditoria e entrada para Skill 05 (custo integrado).
    curvas_forca: list["CurvaForca"] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _migrate_cronograma_list(cls, values: dict) -> dict:
        """Backward-compat: convert old list[CronogramaItem] to new unified Cronograma."""
        cron = values.get("cronograma")
        if isinstance(cron, list):
            values["cronograma"] = _migrate_cron_list_to_cronograma(cron)
        return values


# ── ADR-019: Modelos de reconciliação e re-planejamento ──────────────────────
