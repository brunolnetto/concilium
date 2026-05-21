"""Camada 4 — Modelo canônico do orçamento (produzido pelo pipeline)."""

from datetime import date, datetime
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from statemachine import State, StateMachine

from concilium.domain.models.analitica import CurvaABCInsumo, SCurve  # ADR-058
from concilium.domain.models.backtracking_pe import BacktrackingPERelatorio  # ADR-061
from concilium.domain.models.bdi import IndiretoComBdi  # ADR-023 §D4
from concilium.domain.models.campanha_equipamento import AnaliseFrequenciaCampanhas  # ADR-059
from concilium.domain.models.catalogo import PapelFuncao
from concilium.domain.models.constraint_violation import ConstraintViolation
from concilium.domain.models.cubo_analitico import CuboAnalitico  # ADR-058 ext.
from concilium.domain.models.decision_variables import DecisionVariables
from concilium.domain.models.diagnostico_pe import DiagnosticoPERelatorio  # ADR-060
from concilium.domain.models.memorial_bdi import MemorialCalculoBDI  # ADR-057
from concilium.domain.models.mobilizacao import CurvaForca, MobilizacaoPolicy  # ADR-054

StatusValidacao = Literal["OK", "AVISO", "ERRO", "INFO"]
StatusMargem = Literal["VERDE", "AMARELO", "VERMELHO"]
StatusProjeto = Literal["RASCUNHO", "EM_VALIDACAO", "APROVADO", "EM_EXECUCAO", "CONCLUIDO"]


class ProjetoStatusMachine(StateMachine):
    """Máquina de estados do ciclo de vida do projeto."""

    rascunho = State("RASCUNHO", value="RASCUNHO", initial=True)
    em_validacao = State("EM_VALIDACAO", value="EM_VALIDACAO")
    aprovado = State("APROVADO", value="APROVADO")
    em_execucao = State("EM_EXECUCAO", value="EM_EXECUCAO")
    concluido = State("CONCLUIDO", value="CONCLUIDO", final=True)

    enviar_validacao = rascunho.to(em_validacao)
    cancelar_validacao = em_validacao.to(rascunho)
    # Compatibilidade com fluxo atual do CLI: aprovar também a partir de RASCUNHO.
    aprovar = rascunho.to(aprovado) | em_validacao.to(aprovado)
    iniciar_execucao = aprovado.to(em_execucao)
    concluir = em_execucao.to(concluido)


def transition_status_projeto(status_atual: StatusProjeto, status_destino: StatusProjeto) -> StatusProjeto:
    """Valida e aplica transição de status via `python-statemachine`."""
    if status_atual == status_destino:
        return status_atual

    machine = ProjetoStatusMachine(start_value=status_atual)
    eventos_por_destino: dict[StatusProjeto, tuple[str, ...]] = {
        "RASCUNHO": ("cancelar_validacao",),
        "EM_VALIDACAO": ("enviar_validacao",),
        "APROVADO": ("aprovar",),
        "EM_EXECUCAO": ("iniciar_execucao",),
        "CONCLUIDO": ("concluir",),
    }

    eventos_disponiveis = {evento.name for evento in machine.allowed_events}
    for nome_evento in eventos_por_destino[status_destino]:
        if nome_evento in eventos_disponiveis:
            getattr(machine, nome_evento)()
            return cast(StatusProjeto, machine.current_state_value)

    raise ValueError(
        f"Transição de status inválida: {status_atual} -> {status_destino}. "
        f"Permitidas a partir de {status_atual}: {sorted(eventos_disponiveis)}"
    )


class ValidacaoItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    codigo: str
    status: StatusValidacao
    mensagem: str | None = None


class Meta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    versao_schema: str = "1.0.0"
    gerado_em: datetime
    framework: Literal["concilium"] = "concilium"
    contexto_id: str
    # ADR-031: escopo e plano que geraram este canônico
    escopo_id: str = "default"
    plano_id: str | None = None


class Coordenadas(BaseModel):
    model_config = ConfigDict(extra="ignore")

    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class RegimeTrabalho(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dias_semana: int = Field(ge=1, le=7)
    horas_dia: int = Field(ge=1, le=24)


class Projeto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID | str
    nome: str
    tipo_obra: Literal["terraplenagem", "pavimentacao", "saneamento"]
    localizacao: str
    coordenadas: Coordenadas
    regime_trabalho: RegimeTrabalho
    data_inicio: date
    data_termino: date
    # ADR-041: data de referência para resolução histórica de preços (SCD Type 2)
    data_base_orcamento: date | None = None
    status: StatusProjeto = "RASCUNHO"
    snapshot_catalogo_id: str
    snapshot_perfil_id: str
    revisao: int = Field(default=1, ge=1)
    # ADR-023: snapshot do PerfilBdiProjeto confirmado em `concilium project create`
    bdi_perfil_id: str | None = None

    def can_transition_to(self, status_destino: StatusProjeto) -> bool:
        try:
            transition_status_projeto(self.status, status_destino)
        except ValueError:
            return False
        return True

    def with_status(self, status_destino: StatusProjeto) -> "Projeto":
        novo_status = transition_status_projeto(self.status, status_destino)
        return self.model_copy(update={"status": novo_status})


class Praticabilidade(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fonte: str
    limiar_inviabilidade_mm: float = Field(ge=0)
    calculada_em: datetime
    # Chave: ISO week "AAAA-Www" (ex. "2026-W23"). Valor: fração produtiva [0,1].
    # Dict vazio = dados não disponíveis (skill 02 fará fallback para percentual_produtivo_mensal)
    percentual_produtivo_semanal: dict[str, float] = Field(default_factory=dict)
    # Chave mensal "MM" (ex. "06") — mantido para retrocompatibilidade e fallback
    percentual_produtivo_mensal: dict[str, float] = Field(default_factory=dict)


class EapItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    item_id: str
    ordem: int = Field(ge=1)
    cpu_id: str
    descricao: str
    unidade: str
    quantitativo: float = Field(gt=0)
    # ADR-063 §D4: predecessor IDs (Finish-to-Start). Empty for hot_project.
    predecessores: list[str] = Field(default_factory=list)


# Eap é apenas alias para list[EapItem] — exposto como nome no canônico
Eap = list[EapItem]


class Atividade(BaseModel):
    model_config = ConfigDict(extra="ignore")

    atividade_id: str
    eap_item_id: str
    descricao: str
    fracao_quantitativo: float = Field(gt=0, le=1)
    quantitativo_atividade: float = Field(gt=0)
    cpu_id: str
    # ADR-054 §7.2: optional embedded mobilization policy.
    # When present, takes precedence over the project-level override file
    # (mobilizacao_policy_override.json). Enables per-Atividade policy embedded
    # in the canonical — useful for scenario branching and full auditability.
    mobilizacao_policy: MobilizacaoPolicy | None = None


class ArestaActivityDag(BaseModel):
    model_config = ConfigDict(extra="ignore")

    de: str
    para: str


class ActivityDag(BaseModel):
    model_config = ConfigDict(extra="ignore")

    nos: list[str]
    arestas: list[ArestaActivityDag]
    ordem_topologica: list[str]
    critical_path: list[str] | None = None
    start_offset_min: dict[str, int] | None = None


class DistribuicaoSemanal(BaseModel):
    """Distribuição de execução por semana ISO ("AAAA-Www")."""

    model_config = ConfigDict(extra="ignore")

    num_equipes: int = Field(ge=0)
    qtd_executada: float = Field(ge=0)
    qtd_acumulada: float = Field(ge=0)
    pct: float = Field(ge=0, le=1)
    # Eficiência da semana — fração produtiva aplicada (derivada da praticabilidade)
    eficiencia: float = Field(default=1.0, ge=0.0, le=1.0)


# Alias retrocompatível
DistribuicaoMensal = DistribuicaoSemanal


class AtividadeIntervalo(BaseModel):
    """Unidade atômica de execução: semana ISO × atividade × composição de equipe.

    Formaliza a atividade como um intervalo particionado por semanas e composto
    por equipes. É a granularidade mínima de planejamento e controle do custo direto.

    Invariante: Σ qtd_planejada de todos os intervalos de uma atividade == quantitativo_atividade.

    Derivado de ScheduledActivityCanonical via `AtividadeIntervalo.from_scheduled_activity()`.
    """

    model_config = ConfigDict(extra="ignore")

    atividade_id: str
    semana_iso: str = Field(
        pattern=r"^\d{4}-W(0[1-9]|[1-4][0-9]|5[0-3])$",
        description="Semana ISO no formato AAAA-Www, ex: 2026-W23",
    )
    num_equipes: int = Field(ge=0)
    qtd_planejada: float = Field(ge=0)
    qtd_acumulada: float = Field(ge=0)
    eficiencia: float = Field(default=1.0, ge=0.0, le=1.0)
    pct_completude: float = Field(default=0.0, ge=0.0, le=1.0)

    @classmethod
    def from_scheduled_activity(cls, sa: "ScheduledActivityCanonical") -> "list[AtividadeIntervalo]":
        """Expande um ScheduledActivityCanonical em lista de AtividadeIntervalo (um por semana)."""
        return [
            cls(
                atividade_id=sa.activity_id,
                semana_iso=semana_iso,
                num_equipes=dist.num_equipes,
                qtd_planejada=dist.qtd_executada,
                qtd_acumulada=dist.qtd_acumulada,
                eficiencia=dist.eficiencia,
                pct_completude=dist.pct,
            )
            for semana_iso, dist in sa.distribuicao_semanal.items()
        ]


class CronogramaItem(BaseModel):
    """Per-item weekly schedule (legacy format — use Cronograma for new code)."""

    model_config = ConfigDict(extra="ignore")

    item_id: str
    dias_trabalhados_semana: int
    # Chave: ISO week "AAAA-Www" (ex. "2026-W23")
    distribuicao_semanal: dict[str, DistribuicaoSemanal] = Field(default_factory=dict)
    # Retrocompat: leitura de dados legados com distribuicao_mensal
    distribuicao_mensal: dict[str, DistribuicaoSemanal] = Field(default_factory=dict)
    pct_completude: float = Field(ge=0, le=1)


class FuncaoEquipeDireta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    funcao_id: str = ""
    descricao: str = ""
    num_pessoas: int = 0
    salario_base: float = 0.0
    percentual_encargos: float = 0.0
    horas_extras_pct: float = 0.0
    custo_mensal_unitario: float = 0.0
    # Papel contabilizável herdado de FuncaoEquipe.papel (propaga do catálogo via skill 03)
    papel: PapelFuncao = "direto"


class EquipamentoEquipeDireta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    equip_id: str = ""
    descricao: str = ""
    num_unidades: int = 0
    custo_mensal: float = 0.0
    consumo_litros_hora: float | None = None
    custo_combustivel_mensal: float = 0.0
    custo_mensal_total: float = 0.0


class EquipeDireta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    equipe_id: str = ""
    item_id: str = ""
    cpu_id: str = ""
    nome: str = ""
    num_equipes_base: int = 1
    funcoes: list[FuncaoEquipeDireta] = Field(default_factory=list)
    equipamentos: list[EquipamentoEquipeDireta] = Field(default_factory=list)
    custo_mao_obra_mensal: float = 0.0
    # ADR-030 D3: custo_equipamentos_mensal exclui combustível (antes era custo_mensal_total)
    custo_equipamentos_mensal: float = 0.0
    custo_combustivel_total_mensal: float = 0.0  # ADR-030 D3: soma de combustível de todos os equipamentos
    custo_material_mensal: float = 0.0  # ADR-030 D2: materiais diretos da equipe
    custo_fixo_mensal: float = 0.0
    permanencia_meses: float = Field(default=0.0, ge=0)
    permanencia_efetiva_meses: float = Field(default=0.0, ge=0)  # Σ(num_equipes_j) / SEMANAS_POR_MES — correto para N>1
    custo_total: float = 0.0
    modo_estimativa: Literal["inicial", "refinado"] = "refinado"  # ADR-030 D4


class CustomTeamComposition(BaseModel):
    """ADR-006: Composição de equipe customizada (fora do padrão do CPU).

    Requer aprovação explícita com justificativa documentada.
    """

    model_config = ConfigDict(extra="ignore")

    activity_id: str
    cpu_id: str

    composition_standard: dict[str, int] = Field(default_factory=dict)
    composition_custom: dict[str, int] = Field(default_factory=dict)

    reason: Literal[
        "insufficient_pool_capacity",
        "learning_curve",
        "site_constraints",
        "economic_optimization",
        "temporary_specialization",
    ]

    approved_by: str
    approved_at: datetime
    approval_note: str


class PrecoUnitarioCategoria(BaseModel):
    model_config = ConfigDict(extra="ignore")

    material: float = 0.0
    diesel: float = 0.0
    mao_obra: float = 0.0
    equipamentos: float = 0.0
    total: float = 0.0


class BdiCategorias(BaseModel):
    model_config = ConfigDict(extra="ignore")

    material: float = 0.0
    diesel: float = 0.0
    mao_obra: float = 0.0
    equipamentos: float = 0.0


class SubtotalCategorias(BaseModel):
    model_config = ConfigDict(extra="ignore")

    material: float = 0.0
    diesel: float = 0.0
    mao_obra: float = 0.0
    equipamentos: float = 0.0
    total: float = 0.0


class SubtotalSemBdiComBdi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sem_bdi: SubtotalCategorias = Field(default_factory=SubtotalCategorias)
    com_bdi: SubtotalCategorias = Field(default_factory=SubtotalCategorias)


class Planejamento(BaseModel):
    model_config = ConfigDict(extra="ignore")

    item_id: str = ""
    cpu_id: str = ""
    quantitativo: float = 0.0
    preco_unitario: PrecoUnitarioCategoria = Field(default_factory=PrecoUnitarioCategoria)
    bdi: BdiCategorias = Field(default_factory=BdiCategorias)
    preco_unitario_com_bdi: PrecoUnitarioCategoria = Field(default_factory=PrecoUnitarioCategoria)
    subtotal: SubtotalSemBdiComBdi | None = None


class Mobilizacao(BaseModel):
    model_config = ConfigDict(extra="ignore")

    descricao: str
    num_unidades: int
    origem: str
    destino: str
    distancia_km: float
    custo_km: float
    custo_total: float


class Indireto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    categoria: Literal["ADM", "TOP", "LAB", "QSMS", "MOB"]
    descricao: str
    funcoes: list[dict] = Field(default_factory=list)
    equipamentos: list[dict] = Field(default_factory=list)
    verbas_mensais: list[dict] = Field(default_factory=list)
    verbas_fixas: list[dict] = Field(default_factory=list)
    mobilizacoes: list[Mobilizacao] = Field(default_factory=list)
    baixadas: list[dict] = Field(default_factory=list)
    permanencia_meses: float | None = None
    custo_total: float = 0.0


class PontoEquilibrio(BaseModel):
    model_config = ConfigDict(extra="ignore")

    item_id: str
    custo_fixo_equipe: float
    custo_venda_cpu: float
    delta: float
    delta_pct: float
    status_validacao: StatusValidacao
    custo_operacional_real: float = 0.0  # Novo: custo_total da equipe (real)
    frentes_equivalentes: float = 1.0  # Novo: razão entre custo_operacional_real e custo_fixo_equipe

    # ADR-051 Link: Rastreio de confiabilidade do PE baseado em validação de PU
    validacao_pu_status: Literal["VERDE", "AMARELO", "VERMELHO"] | None = None
    confianca_pe: Literal["ALTA", "MEDIA", "BAIXA"] | None = None
    diagnostico_pu: str | None = None  # ex: "PU subestimado em 8%, PE pode ser otimista"


class Venda(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Metodologia A (legado): precificação por catálogo (CPU_unit × qty × BDI)
    total_sem_bdi: float  # sum(CPU_unit × qty)  — referência de mercado
    total_com_bdi: float  # sum(CPU_unit × qty × (1+BDI))  — preco_venda catálogo

    # Metodologia B (custo-mais-margem / alinhada com planilhas referência):
    # preco_venda = (custo_direto_real + custo_indireto_real) × (1 + lucro + impostos)
    total_custo_plus: float = 0.0  # preco_venda pelo modelo custo+margem usando custo real da equipe
    total_custo_plus_catalogo: float = 0.0  # preco_venda pelo modelo custo+margem usando direto catálogo
    bdi_lucro_impostos: float = 0.0  # fator aplicado (ex: 0.1433 = lucro 9% + trib 5.33%)


class CustoTotal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    direto_equipes: float  # custo real das equipes no campo (MO+EQ×tempo + materiais cat)
    direto_catalogo: float = 0.0  # custo dir pelo catálogo: sum(CPU_unit × qty) sem BDI
    # = como as referências medem o custo direto
    indireto_adm: float = 0
    indireto_top: float = 0
    indireto_lab: float = 0
    indireto_qsms: float = 0
    indireto_mob: float = 0
    total: float


class BalancoPontoEquilibrio(BaseModel):
    """Visão macro do Custo Fixo Estrutural e Headcount do canteiro."""

    model_config = ConfigDict(extra="ignore")

    total_hc_operacional: int = 0
    total_hc_indireto: int = 0
    total_hc: int = 0
    custo_fixo_mensal: float = 0.0
    custo_fixo_total: float = 0.0
    numero_equipes_diretas: int = 0


# ── ADR-028: Balanço de controle de margem ───────────────────────────────────

ControleVariavel = Literal["TUNAVEL", "SEMI_TUNAVEL", "EXTERNO"]


class BalancoControle(BaseModel):
    """Decompõe o gap de margem em porções fecháveis vs estruturais (ADR-028)."""

    model_config = ConfigDict(extra="ignore")

    gap_total_pp: float  # pontos percentuais: meta - margem_atual
    gap_fechavel_pp: float  # redutível por variáveis TUNAVEL
    gap_semi_tunavel_pp: float  # redutível por SEMI_TUNAVEL (procurement, BDI)
    gap_externo_pp: float  # estrutural — SINAPI, impostos, praticabilidade
    viavel_por_decisao: bool  # gap_fechavel + gap_semi_tunavel >= gap_total
    principais_fatores_externos: list[str] = Field(default_factory=list)
    fonte: Literal["ESTIMADO", "CALCULADO"] = "ESTIMADO"


class Resultado(BaseModel):
    model_config = ConfigDict(extra="ignore")

    venda: Venda
    custo: CustoTotal
    resultado_financeiro: float
    margem_pct: float
    status_margem: StatusMargem
    validacoes: list[ValidacaoItem]
    balanco_de_controle: "BalancoControle | None" = None  # ADR-028
    balanco_ponto_equilibrio: "BalancoPontoEquilibrio | None" = None


# ── Fase 2: Resource Binding ──────────────────────────────────────────────

CategoriaRecurso = Literal["EQUIPAMENTO", "MAQUINARIO", "EQUIPE", "MATERIAL"]
CriticidadeRecurso = Literal["CRITICA", "NORMAL", "OPCIONAL"]
StatusAlocacao = Literal["PLANEJADA", "ATIVA", "COMPLETADA", "CANCELADA"]


class TipoRecurso(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    nome: str
    categoria: CategoriaRecurso
    custo_unitario_dia: float = Field(ge=0)
    especificacoes: dict = Field(default_factory=dict)


class RecursoPool(BaseModel):
    """Pool de recursos disponíveis para o projeto (não double-counted)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    tipo_id: str
    projeto_id: str
    quantidade_total: int = Field(ge=1)
    quantidade_disponivel: int = Field(ge=0)
    data_aquisicao: date | None = None
    custo_aquisicao_total: float = Field(ge=0, default=0.0)


class RequisitoRecurso(BaseModel):
    """Requisito declarativo: atividade X precisa de Y unidades do tipo Z."""

    model_config = ConfigDict(extra="ignore")

    requisito_id: str
    atividade_id: str
    tipo_recurso_id: str
    descricao: str
    quantidade: float = Field(gt=0)
    data_inicio: date
    data_termino: date
    criticidade: CriticidadeRecurso = "NORMAL"


class Alocacao(BaseModel):
    """Alocação concreta: recurso R atribuído à atividade A no período T.

    Invariante: quantidade_alocada <= RecursoPool.quantidade_total no período.
    Garantida pelo skill 03B, nunca contada duas vezes.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    atividade_id: str
    recurso_id: str  # FK -> RecursoPool.id
    quantidade_alocada: float = Field(gt=0)
    data_inicio: date
    data_termino: date
    status: StatusAlocacao = "PLANEJADA"
    # ADR-019 D3: CONSTRANGIDO = pool esgotado após esta alocação (sem margem)
    criticidade_recurso: Literal["LIVRE", "CONSTRANGIDO"] = "LIVRE"


class ConflitoPico(BaseModel):
    """Conflito detectado: demanda ultrapassa capacidade em algum período."""

    model_config = ConfigDict(extra="ignore")

    recurso_id: str
    tipo_nome: str
    periodo_inicio: date
    periodo_termino: date
    quantidade_disponivel: int
    quantidade_necessaria: float
    excedente: float
    atividades_conflitantes: list[str]
    recomendacoes: list[str]


# ── ADR-009: Indirect Costs as First-Class Models ─────────────────────────────


class IndirectoCostComponent(BaseModel):
    """Componente de custo indireto: MÃO_DE_OBRA, EQUIPAMENTOS ou VERBAS."""

    model_config = ConfigDict(extra="ignore")

    nome: str
    custo_fixo_mensal: float = Field(ge=0)
    itens: list[dict] = Field(default_factory=list)


class IndirectoCategoria(BaseModel):
    """Categoria de custo indireto com driver de escalonamento (ADR-009)."""

    model_config = ConfigDict(extra="ignore")

    categoria: Literal["TOP", "ADM", "LAB", "QSMS", "MOB"]
    driver: Literal["permanencia", "one_time"]
    mao_de_obra: IndirectoCostComponent | None = None
    equipamentos: IndirectoCostComponent | None = None
    verbas: IndirectoCostComponent | None = None
    custo_fixo_mensal: float = Field(default=0.0, ge=0)
    custo_fixo_total: float = Field(default=0.0, ge=0)  # apenas para driver="one_time"

    @property
    def custo_semanal(self) -> float:
        """Custo por semana para categorias permanencia. MOB retorna 0 (one_time)."""
        if self.driver == "one_time":
            return 0.0
        from concilium.domain.constants import SEMANAS_POR_MES

        return round(self.custo_fixo_mensal / SEMANAS_POR_MES, 2)

    def custo_total_para_semanas(self, n_semanas: int) -> float:
        """Custo total para uma duração em semanas."""
        if self.driver == "one_time":
            return self.custo_fixo_total
        return round(self.custo_semanal * n_semanas, 2)


class IndiretoSemanal(BaseModel):
    """Breakdown semanal de custo indireto por categoria (ADR-009 §D2)."""

    model_config = ConfigDict(extra="ignore")

    semana: int = Field(ge=0)
    categoria: str
    custo_mao_de_obra: float = Field(default=0.0, ge=0)
    custo_equipamentos: float = Field(default=0.0, ge=0)
    custo_verbas: float = Field(default=0.0, ge=0)
    custo_semanal: float = Field(default=0.0, ge=0)
    ativa: bool = True


# ── ADR-010: Activity Cost Breakdown Models ────────────────────────────────────


class InsumoComponenteAtividade(BaseModel):
    """Componente de custo direto de uma atividade: MO, EQUIPAMENTOS ou MATERIAL."""

    model_config = ConfigDict(extra="ignore")

    nome: str
    itens: list[dict] = Field(default_factory=list)  # legado — sem schema
    # ADR-058 D1: itens tipados com rastreabilidade de insumo individual
    itens_detalhados: list["InsumoDetalheAtvCanonical"] = Field(default_factory=list)
    custo_total: float = Field(ge=0)


class InsumoDetalheAtvCanonical(BaseModel):
    """ADR-058 D1: insumo individual rastreável dentro de uma atividade (versão Pydantic).

    Versão serializável do dataclass InsumoDetalheAtividade em domain/models/analitica.py.
    """

    model_config = ConfigDict(extra="ignore")

    insumo_id: str
    descricao: str
    categoria: str  # "MAO_OBRA" | "EQUIPAMENTO" | "DIESEL" | "MATERIAL"
    num_unidades: float = 0.0
    custo_unitario_mensal: float = 0.0
    permanencia_meses: float = 0.0
    custo_total: float = 0.0


class AtividadeInsumo(BaseModel):
    """Insumo de custo direto de uma atividade (ADR-010 §D1)."""

    model_config = ConfigDict(extra="ignore")

    categoria: str
    mao_de_obra: InsumoComponenteAtividade | None = None
    equipamentos: InsumoComponenteAtividade | None = None
    material: InsumoComponenteAtividade | None = None

    @property
    def custo_total_direto(self) -> float:
        return round(
            (self.mao_de_obra.custo_total if self.mao_de_obra else 0.0)
            + (self.equipamentos.custo_total if self.equipamentos else 0.0)
            + (self.material.custo_total if self.material else 0.0),
            2,
        )


class IndiretoAlocacao(BaseModel):
    """Como uma atividade compartilha os pools de custo indireto (ADR-010 §D2)."""

    model_config = ConfigDict(extra="ignore")

    estrategia: Literal["esforco_mo", "duracao", "fator_explicito"]
    percentual_horas_mo: float | None = Field(default=None, ge=0, le=1)
    semanas_atividade: int | None = Field(default=None, ge=0)
    semanas_projeto: int | None = Field(default=None, ge=0)
    fator_top: float = Field(default=0.0, ge=0, le=1)
    fator_adm: float = Field(default=0.0, ge=0, le=1)
    fator_lab: float = Field(default=0.0, ge=0, le=1)
    fator_qsms: float = Field(default=0.0, ge=0, le=1)


class CustoIndiretoAtividade(BaseModel):
    """Parcela de custo indireto atribuída a uma atividade (ADR-010 §D2)."""

    model_config = ConfigDict(extra="ignore")

    atividade_id: str
    alocacao: IndiretoAlocacao
    custo_top_atribuido: float = Field(default=0.0, ge=0)
    custo_adm_atribuido: float = Field(default=0.0, ge=0)
    custo_lab_atribuido: float = Field(default=0.0, ge=0)
    custo_qsms_atribuido: float = Field(default=0.0, ge=0)

    @property
    def custo_total_indireto(self) -> float:
        return round(
            self.custo_top_atribuido + self.custo_adm_atribuido + self.custo_lab_atribuido + self.custo_qsms_atribuido,
            2,
        )


class MobilizacaoAtividade(BaseModel):
    """Custo de setup/teardown específico de uma atividade (ADR-010 §D3)."""

    model_config = ConfigDict(extra="ignore")

    atividade_id: str
    fase: Literal["setup", "teardown", "both"]
    mao_de_obra: InsumoComponenteAtividade | None = None
    equipamentos: InsumoComponenteAtividade | None = None
    material: InsumoComponenteAtividade | None = None
    alocacao: Literal["semana_inicio", "semana_fim", "ambas"] = "semana_inicio"

    @property
    def custo_total(self) -> float:
        return round(
            (self.mao_de_obra.custo_total if self.mao_de_obra else 0.0)
            + (self.equipamentos.custo_total if self.equipamentos else 0.0)
            + (self.material.custo_total if self.material else 0.0),
            2,
        )

    def alocacao_por_semana(self, semana_inicio: int, semana_fim: int) -> dict[int, float]:
        if self.alocacao == "semana_inicio":
            return {semana_inicio: self.custo_total}
        if self.alocacao == "semana_fim":
            return {semana_fim: self.custo_total}
        metade = round(self.custo_total / 2, 2)
        return {semana_inicio: metade, semana_fim: metade}


class AtividadeCustoCompleto(BaseModel):
    """Breakdown completo de custo de uma atividade (ADR-010 §D4)."""

    model_config = ConfigDict(extra="ignore")

    atividade_id: str
    nome: str = ""
    semana_inicio: int = Field(ge=0)
    semana_fim: int = Field(ge=0)
    custos_diretos: list[AtividadeInsumo] = Field(default_factory=list)
    indireto_alocacao: IndiretoAlocacao | None = None
    custo_indireto_atribuido: float = Field(default=0.0, ge=0)
    mobilizacao: MobilizacaoAtividade | None = None

    @property
    def duracao_semanas(self) -> int:
        return max(1, self.semana_fim - self.semana_inicio + 1)

    @property
    def custo_direto_total(self) -> float:
        return round(sum(i.custo_total_direto for i in self.custos_diretos), 2)

    @property
    def custo_mobilizacao_atividade(self) -> float:
        return self.mobilizacao.custo_total if self.mobilizacao else 0.0

    @property
    def custo_total_atividade(self) -> float:
        return round(
            self.custo_direto_total + self.custo_indireto_atribuido + self.custo_mobilizacao_atividade,
            2,
        )


# ── ADR-004: Weekly schedule canonical models ─────────────────────────────


class ScheduledActivityCanonical(BaseModel):
    """Atividade agendada (semanal) — com detalhe de distribuição de execução.

    Unifica scheduling (semana início/fim, datas) com distribuição de execução (qtd por semana).
    """

    model_config = ConfigDict(extra="ignore")

    activity_id: str
    start_week: int
    end_week: int
    duration_weeks: int
    data_inicio: date | None = None
    data_fim: date | None = None
    assigned_resources: dict[str, int] = Field(default_factory=dict)

    # Distribuição semanal: chave "AAAA-Www" -> {num_equipes, qtd_executada, qtd_acumulada, pct, eficiencia}
    distribuicao_semanal: dict[str, DistribuicaoSemanal] = Field(default_factory=dict)


class ScheduleCandidateCanonical(BaseModel):
    """Candidato de cronograma semanal gerado por uma heurística (v1 — deprecated)."""

    model_config = ConfigDict(extra="ignore")

    heuristic: str
    scheduled_activities: list[ScheduledActivityCanonical] = Field(default_factory=list)
    makespan: int
    quality_score: float
    metrics: dict[str, float] = Field(default_factory=dict)
    relaxed: bool = False


class Cronograma(BaseModel):
    """Cronograma unificado (semanal com agregação mensal).

    Single source of truth para o schedule do projeto (semanal + agregação mensal).
    """

    model_config = ConfigDict(extra="ignore")

    # Scheduling metadata (from AUTO optimization or MANUAL_ALLOCATION)
    algorithm: Literal["manual_allocation", "MINSLK", "LPT", "MAXRES", "ES", "GR", "MILP"] = "manual_allocation"
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    makespan_weeks: int = Field(default=1, ge=1)
    is_feasible: bool = True
    was_relaxed: bool = False

    # Scheduled activities with weekly detail
    scheduled_activities: list[ScheduledActivityCanonical] = Field(default_factory=list)

    # Monthly aggregation (for reporting, backward compatibility)
    # Chave: "2026-03" -> {qtd_total, pct, atividades: [activity_ids]}
    distribuicao_mensal: dict[str, dict] = Field(default_factory=dict)

    # Legacy field (retrocompat if needed)
    pct_completude: float = Field(default=1.0, ge=0.0, le=1.0)


class CanonicalModel(BaseModel):
    """Estado completo do orçamento — produzido incrementalmente pelo pipeline."""

    model_config = ConfigDict(extra="ignore")

    meta: Meta
    projeto: Projeto
    praticabilidade: Praticabilidade | None = None
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
    intervention_assessments: list[dict] | None = None

    # Fase 2 — resource binding
    tipos_recurso: list[TipoRecurso] = Field(default_factory=list)
    recurso_pool: list[RecursoPool] = Field(default_factory=list)
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

    # ADR-059: Campanhas de permanência de equipamentos.
    analise_campanhas: "AnaliseFrequenciaCampanhas | None" = None

    # ADR-057: Memorial de cálculo BDI — artefato de auditoria ponta a ponta.
    # Gerado por Skill 08. Exportado como JSON e aba Excel MEMORIAL.BDI.
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
            scheduled = []
            for item in cron:
                # Accept both raw dicts and already-instantiated CronogramaItem objects
                if isinstance(item, dict):
                    item_data = item
                elif hasattr(item, "model_dump"):
                    item_data = item.model_dump()
                else:
                    continue
                item_id = item_data.get("item_id", "")
                dist_semanal = item_data.get("distribuicao_semanal") or {}
                # Fall back to distribuicao_mensal when semanal is empty
                if not dist_semanal:
                    dist_semanal = item_data.get("distribuicao_mensal") or {}
                # Extract start/end week from distribution keys
                weeks: list[int] = []
                for k in dist_semanal:
                    if "-W" in str(k):
                        try:
                            weeks.append(int(str(k).split("-W")[1]))
                        except (ValueError, IndexError):
                            pass
                start = min(weeks) if weeks else 1
                end = max(weeks) if weeks else 1
                scheduled.append(
                    {
                        "activity_id": item_id,
                        "start_week": start,
                        "end_week": end,
                        "duration_weeks": max(end - start + 1, 1),
                        "distribuicao_semanal": dist_semanal,
                    }
                )
            values["cronograma"] = {
                "algorithm": "manual_allocation",
                "scheduled_activities": scheduled,
            }
        return values


# ── ADR-019: Modelos de reconciliação e re-planejamento ──────────────────────


class ItemCustoAquisicao(BaseModel):
    """Custo de aquisição/contratação derivado de uma recomendação BUY/HIRE de 03C."""

    model_config = ConfigDict(extra="ignore")

    conflito_idx: int
    recurso_id: str
    tipo_recurso_id: str
    tipo_nome: str
    acao: Literal["BUY", "HIRE"]
    quantidade: float
    custo_unitario_dia: float
    dias: int
    custo_total: float
    categoria_bdi: Literal["EQUIPAMENTO", "MAO_OBRA"]


class ResultadoReconciliado(BaseModel):
    """Resultado após aplicar delta de custos de aquisição de recurso (06A)."""

    model_config = ConfigDict(extra="ignore")

    itens_aquisicao: list[ItemCustoAquisicao] = Field(default_factory=list)
    delta_custo_total: float = 0.0
    venda_total_com_bdi: float = 0.0
    custo_total_reconciliado: float = 0.0
    margem_reconciliada_pct: float = 0.0
    status_margem_reconciliado: StatusMargem = "VERDE"
    delta_status: str | None = None


class ReplanSugestao(BaseModel):
    """Sugestão concreta de re-planejamento com checkpoint e parâmetros (13-assessor-replanejamento)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    tipo: Literal["CRONOGRAMA", "EQUIPES", "RECURSOS", "ESCOPO", "BDI"]
    checkpoint_skill: str
    parametros_sugeridos: dict
    delta_margem_estimado: float
    confianca: Literal["ALTA", "MEDIA", "BAIXA"]
    justificativa: str
    restricoes: list[str] = Field(default_factory=list)
    controle: ControleVariavel = "TUNAVEL"  # ADR-028


class ReplanSuggestions(BaseModel):
    """Seção canônica produzida por 13-assessor-replanejamento."""

    model_config = ConfigDict(extra="ignore")

    status_gatilho: StatusMargem
    delta_margem_necessario: float
    sugestoes: list[ReplanSugestao] = Field(default_factory=list)
    sugestao_prioritaria: str | None = None


# ── ADR-020: Criticidade multi-dimensional sem score sintético ───────────────


class DimensaoCriticidade(BaseModel):
    """Raw value + rank para uma única dimensão de criticidade."""

    model_config = ConfigDict(extra="ignore")

    valor_raw: float
    rank: int  # 1 = mais crítico
    percentil: float  # 0.0–1.0, 1.0 = mais crítico


class CriticidadeProfile(BaseModel):
    """Perfil multi-dimensional de uma atividade — sem score agregado."""

    model_config = ConfigDict(extra="ignore")

    atividade_id: str
    custo: DimensaoCriticidade
    duracao: DimensaoCriticidade
    recurso: DimensaoCriticidade
    sensibilidade: DimensaoCriticidade
    pareto_frontier: bool
    rank_lexicografico: int  # 1 = mais crítico
    classe: Literal["A+", "A", "B", "C"]
    interpretacao: str


class CostCriticalityResult(BaseModel):
    """Substitui o dict cost_criticality_report com tipo estruturado (ADR-020)."""

    model_config = ConfigDict(extra="ignore")

    atividades: list[CriticidadeProfile] = Field(default_factory=list)
    n_pareto_frontier: int = 0
    criterio_primario: Literal["custo", "duracao", "recurso"] = "custo"
    n_atividades: int = 0


# ── ADR-021: Espaço combinatorial de planos ──────────────────────────────────


# ── ADR-027: Perfil de exposição a custos por CPU ────────────────────────────


class VetorExposuraCpu(BaseModel):
    """Ponto no simplex de exposição de custo da CPU — ∑ coordenadas = 1,0.

    Cada coordenada é a fração do custo da CPU exposta a um indexador de mercado
    distinto. Preservado sem colapso escalar para permitir clustering por perfil
    de risco de custo (ADR-027).

    Derivação a partir de composicao_itens (categoria_custo):
        equip    ← EQUIPAMENTO + MAQUINARIO + DIESEL + COMBUSTIVEL
        mao_obra ← MAO_OBRA + PESSOAL
        material ← MATERIAL e demais categorias classificadas
        outros   ← residual = 1 – equip – mao_obra – material
    """

    model_config = ConfigDict(extra="ignore")

    equip: float = Field(ge=0.0, le=1.0)  # combustível / aluguel / depreciação de máquinas
    mao_obra: float = Field(ge=0.0, le=1.0)  # SINAPI / dissídio coletivo
    material: float = Field(ge=0.0, le=1.0)  # índices de insumos materiais
    outros: float = Field(ge=0.0, le=1.0)  # residual: mobilização, praticabilidade, outros

    @model_validator(mode="after")
    def _check_simplex(self) -> "VetorExposuraCpu":
        total = round(self.equip + self.mao_obra + self.material + self.outros, 6)
        if abs(total - 1.0) > 1e-4:
            raise ValueError(
                f"VetorExposuraCpu deve somar 1,0; soma={total:.6f} "
                f"(equip={self.equip}, mao_obra={self.mao_obra}, "
                f"material={self.material}, outros={self.outros})"
            )
        return self


class CpuExposurePerfil(BaseModel):
    """Perfil de exposição de custo de uma CPU — ponto no simplex de risco (ADR-027).

    O vetor é preservado sem colapso escalar para clustering.
    O escalar de sensibilidade para a análise Pareto (skill 09) é derivado
    on-the-fly via produto interno com pesos de volatilidade do perfil.
    """

    model_config = ConfigDict(extra="ignore")

    cpu_id: str
    vetor: VetorExposuraCpu  # ponto no simplex — não-colapsado
    fator_praticabilidade: float = Field(ge=0.0, le=1.0)  # multiplicador ortogonal: 0=insensível, 1=altamente sazonal
    fonte: Literal["CATALOGO", "CALCULADO"] = "CALCULADO"


class Lever(BaseModel):
    """Intervenção paramétrica que melhora a margem do plano."""

    model_config = ConfigDict(extra="ignore")

    tipo: Literal["EXPAND_POOL", "REDUCE_DURATION", "ADD_TEAMS", "REVIEW_BDI"]
    checkpoint_skill: str
    parametros: dict = Field(default_factory=dict)
    delta_margem_estimado: float
    custo_aplicacao: float  # custo adicional estimado em R$ para aplicar
    ratio_beneficio: float  # delta_margem / max(custo_aplicacao_norm, 1e-6)
    confianca: Literal["ALTA", "MEDIA", "BAIXA"]
    justificativa: str
    controle: ControleVariavel = "TUNAVEL"  # ADR-028


class RepairStep(BaseModel):
    """Um passo na sequência de repair (AMARELO/VERMELHO -> VERDE)."""

    model_config = ConfigDict(extra="ignore")

    ordem: int
    lever: Lever
    margem_acumulada_apos: float
    status_apos: StatusMargem


class RepairPath(BaseModel):
    """Sequência mínima de intervenções para atingir VERDE."""

    model_config = ConfigDict(extra="ignore")

    viavel: bool  # True se o caminho atinge faixa_alvo.min
    passos: list[RepairStep] = Field(default_factory=list)
    margem_projetada: float
    status_projetado: StatusMargem


class OportunidadeVerde(BaseModel):
    """Oportunidade de aumentar margem num plano já VERDE."""

    model_config = ConfigDict(extra="ignore")

    lever: Lever
    margem_adicional_estimada: float
    risco: Literal["BAIXO", "MEDIO", "ALTO"]


class PlanSpaceResult(BaseModel):
    """Resultado do 14-explorador-cenarios: repair_path e/ou oportunidades."""

    model_config = ConfigDict(extra="ignore")

    status_entrada: StatusMargem
    margem_entrada: float
    repair_path: RepairPath | None = None
    oportunidades: list[OportunidadeVerde] = Field(default_factory=list)


# ── ADR-051: Validação Convergente de Preço Unitário ────────────────────────


class CategoriaConvergencia(BaseModel):
    """Convergência de preço unitário em uma categoria de custo."""

    model_config = ConfigDict(extra="ignore")

    pu_teorico: float  # PU teórico derivado de composição/produção
    pu_planejado: float  # PU calculado pelo pipeline
    desvio_pct: float  # (planejado - teorico) / teorico × 100%
    status: Literal["VERDE", "AMARELO", "VERMELHO"]


class ValidacaoCatalogoPUItem(BaseModel):
    """Validação de PU teórico vs catalogado para CPU isolada (ADR-051 §Camada 1)."""

    model_config = ConfigDict(extra="ignore")

    cpu_id: str
    unidade: str

    producao_horaria: float
    custo_hora_teorico: float  # soma de componentes

    pu_teorico_sem_bdi: float  # = custo_hora / producao_hora
    pu_catalogado_sem_bdi: float | None = None  # precos_unitarios_sbdi.total (se existe)

    desvio_pct: float  # (catalogado - teorico) / teorico × 100% (se catalogado existe)
    status_convergencia: Literal["VERDE", "AMARELO", "VERMELHO"]  # ±5% / ±10% / >10%

    # Por categoria
    detalhes: dict[str, CategoriaConvergencia] = Field(
        default_factory=dict
    )  # {material, diesel, mao_obra, equipamentos}

    validacoes: list[ValidacaoItem] = Field(default_factory=list)


class ValidacaoPUResumida(BaseModel):
    """Resumo consolidado de validações de PU (catálogo) para relatório."""

    model_config = ConfigDict(extra="ignore")

    # Nível catálogo
    validacoes_catalogo: list[ValidacaoCatalogoPUItem] = Field(default_factory=list)

    # Resumo
    num_verde: int = 0
    num_amarelo: int = 0
    num_vermelho: int = 0
    status_geral: Literal["VERDE", "AMARELO", "VERMELHO"] = "VERDE"

    recomendacoes: list[str] = Field(default_factory=list)


# ── Resolução de forward refs cross-module ────────────────────────────────────
# RelatorioCriticidade, RelatorioSensibilidade, RelatorioIntervencao vêm de
# concilium.models.reports (ADR-026). Importamos aqui para que o Pydantic v2
# resolva corretamente as referências por string em CanonicalModel.
from concilium.domain.models.reports import (  # noqa: E402 — necessário após definição das classes
    RelatorioCriticidade,
    RelatorioIntervencao,
    RelatorioSensibilidade,
)

CanonicalModel.model_rebuild()
