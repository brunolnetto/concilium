"""Camada 4 — Modelo canônico do orçamento (produzido pelo pipeline)."""

from datetime import date, datetime
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from statemachine import State, StateMachine

from concilium.domain.models.analytics.analitica import CurvaABCInsumo, SCurve  # ADR-058
from concilium.domain.models.financial.backtracking_pe import BacktrackingPERelatorio  # ADR-061
from concilium.domain.models.financial.bdi import IndiretoComBdi, TabelaBdi  # ADR-023 §D4
from concilium.domain.models.planning.calendario_operacional import CalendarioOperacionalSemanal
from concilium.domain.models.campaign.campanha_equipamento import AnaliseFrequenciaCampanhas  # ADR-059
from concilium.domain.models.catalog.catalogo import PapelFuncao
from concilium.domain.models.project.constraint_violation import ConstraintViolation
from concilium.domain.models.analytics.cubo_analitico import CuboAnalitico  # ADR-058 ext.
from concilium.domain.models.project.decision_variables import DecisionVariables
from concilium.domain.models.analytics.diagnostico_pe import DiagnosticoPERelatorio  # ADR-060
from concilium.domain.models.financial.memorial_bdi import MemorialCalculoBDI  # ADR-057
from concilium.domain.models.planning.mobilizacao import CurvaForca, MobilizacaoPolicy  # ADR-054

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
    # NEP-039: Proveniência de benchmark — rastreamento de origem
    derivado_de_benchmark: str | None = None  # "AGIS_2025_Q1"
    benchmark_versao: int | None = None  # 1, 2, ... (auto-incrementado)
    benchmark_execution_id: str | None = None  # UUID da execução


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
    # localizacao aceita string legada ("Brasil") ou Coordenadas {lat, lng} (normalizado)
    localizacao: str | Coordenadas
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


class PrecedenciaItem(BaseModel):
    """NEP-031 L4: relação de precedência tipada entre itens da EAP (§4 do enunciado).

    Tipos suportados:
      FS (Finish-to-Start, default): B começa após A terminar + lag semanas.
      SS (Start-to-Start):           B começa lag semanas após A iniciar.
      FF (Finish-to-Finish):         B termina lag semanas após A terminar (parcial).

    ADR-081: ``completion_threshold_pct`` (θ ∈ [0,1]) define a fração do quantitativo
    do predecessor concluída antes do sucessor poder iniciar (apenas FS).
    θ=1.0 (default) → FS clássico 100%.  θ=0.20 → B pode iniciar quando A está 20% feita.
    Fórmula: start_B ≥ start_A + ceil(θ × duration_A) + lag
    """

    model_config = ConfigDict(extra="ignore")

    item_id: str
    tipo: Literal["FS", "SS", "FF"] = "FS"
    lag: int = Field(default=0, ge=0, description="Lag em semanas")
    # ADR-081: completion threshold ∈ [0,1]. 1.0 = FS clássico (default sem quebra retroativa).
    completion_threshold_pct: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description=(
            "Fração do quantitativo do predecessor concluída antes do início do "
            "sucessor (apenas FS). θ=1.0 = FS estrito; θ=0.0 = equivale a SS."
        ),
    )


class EapItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    item_id: str
    ordem: int | None = Field(default=None, ge=1)  # Opcional — inferido do catálogo se não fornecido
    cpu_id: str
    descricao: str | None = None  # Opcional — inferido do catálogo se não fornecido
    unidade: str | None = None  # Opcional — inferido do catálogo se não fornecido
    quantitativo: float = Field(gt=0)
    # NEP-031 L4: predecessores com tipo de relação (FS/SS/FF) e lag.
    # Aceita str (legado, tratado como FS lag=0) ou PrecedenciaItem.
    predecessores: list[str | PrecedenciaItem] = Field(default_factory=list)

    def predecessores_tipados(self) -> list[PrecedenciaItem]:
        """Normaliza predecessores para PrecedenciaItem (converte str legados)."""
        result = []
        for p in self.predecessores:
            if isinstance(p, str):
                result.append(PrecedenciaItem(item_id=p, tipo="FS", lag=0))
            else:
                result.append(p)
        return result


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
    """NEP-031 L4: aresta do DAG com tipo de relação, lag e threshold de conclusão.

    ADR-081: ``completion_threshold_pct`` (θ) tem a mesma semântica de PrecedenciaItem.
    """

    model_config = ConfigDict(extra="ignore")

    de: str
    para: str
    tipo: Literal["FS", "SS", "FF"] = "FS"
    lag: int = Field(default=0, ge=0)
    # ADR-081: idêntico a PrecedenciaItem.completion_threshold_pct
    completion_threshold_pct: float = Field(default=1.0, ge=0.0, le=1.0)


class ActivityDag(BaseModel):
    model_config = ConfigDict(extra="ignore")

    nos: list[str]
    arestas: list[ArestaActivityDag]
    ordem_topologica: list[str]
    critical_path: list[str] | None = None
    start_offset_min: dict[str, int] | None = None


class DistribuicaoSemanal(BaseModel):
    """Distribuição de execução por semana ISO ("AAAA-Www").

    NEP-035 — Decomposição causal da eficiência η = η_s · η_p · η_w:
      η_s  = n_j / n_max          (alocação: fração da força máxima fielded)
      η_p  = fator_clima × fator_calendario  (praticabilidade)
      η_w  = m_ij / M_max = eficiencia      (gestão; M_max=1.0 até calibração histórica)
      η    = fator_total = η_s · η_p · η_w  (eficiência total observada)

    q_max_celula = P_i · h · n_max · M_max  (capacidade teórica da semana)
    perda_fisica = q_max_celula · η_s - q_executada  (produção perdida na semana, unidades físicas)

    Agregação multi-semanal correta (Seção 5 do modelo):
      η_agg = Σ_j(η_j · q_max_celula_j) / Σ_j(q_max_celula_j)  [ponderado por capacidade]
      ≠ produto de médias por fator (os fatores acoplam via pesos de capacidade).
    """

    model_config = ConfigDict(extra="ignore")

    num_equipes: int = Field(ge=0)
    qtd_executada: float = Field(ge=0)
    qtd_acumulada: float = Field(ge=0)
    pct: float = Field(ge=0, le=1)
    # ADR-082-cons: eficiencia = utilização m_ij (≠ praticabilidade; ver fator_total)
    eficiencia: float = Field(default=1.0, ge=0.0, le=1.0)
    # ADR-068: separacao explícita entre clima e calendario operacional.
    fator_clima: float = Field(default=1.0, ge=0.0, le=1.0)
    fator_calendario: float = Field(default=1.0, ge=0.0, le=1.0)
    fator_total: float = Field(default=1.0, ge=0.0, le=1.0)
    # NEP-035: decomposição causal η_s · η_p · η_w
    eta_s: float = Field(default=1.0, ge=0.0, le=1.0)
    eta_p: float = Field(default=1.0, ge=0.0, le=1.0)
    eta_w: float = Field(default=1.0, ge=0.0, le=1.0)
    q_max_celula: float = Field(default=0.0, ge=0.0)
    perda_fisica: float = Field(default=0.0, ge=0.0)


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
    """Per-item weekly schedule (historical format — use Cronograma for new code)."""

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
    # NEP-037 D1: encargos separados do salário base para reconciliar com PU_sbdi
    # custo_mensal_unitario = salario_base × (1 + percentual_encargos) × (1 + horas_extras_pct)
    # custo_encargos_mensal_unitario = salario_base × percentual_encargos × num_pessoas
    custo_encargos_mensal_unitario: float = 0.0
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
    # NEP-031 L1: modo de cobrança de aluguel (§8.2 da formalização — u_q)
    rental_unit: str = "hora_produtiva"  # "hora_produtiva" | "dia_calendario" | "mes"
    # NEP-031 L5: taxa de manutenção por hora produtiva (§8.2 da formalização — μ_q)
    # Custo de manutenção ativo incorrido somente quando σ = prod (não idle/demob).
    custo_manutencao_hora: float = 0.0
    # NEP-031 L2: custo de mob/desmob por evento (§8.3 da formalização — c_r^mob / c_r^demob)
    custo_mobilizacao: float = 0.0
    custo_desmobilizacao: float = 0.0
    # ADR-088: sub-decomposição (aluguel | combustivel | manutencao) por equipamento.
    # custo_mensal = custo_locacao_mensal + custo_manutencao_mensal (sem combustivel)
    # custo_mensal_total = custo_mensal + custo_combustivel_mensal
    custo_locacao_mensal: float = 0.0  # aluguel puro (BDI_servicos ≈ 30%)
    custo_manutencao_mensal: float = 0.0  # manutenção ativa (BDI_servicos)
    custo_locacao_idle_mensal: float = 0.0  # aluguel em standby (integral; = custo_locacao em geral)
    custo_manutencao_idle_mensal: float = 0.0  # manutenção em standby (zero em geral)


class EquipeDireta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    equipe_id: str = ""
    item_id: str = ""
    cpu_id: str = ""
    nome: str = ""
    num_equipes_base: int = 1
    funcoes: list[FuncaoEquipeDireta] = Field(default_factory=list)
    equipamentos: list[EquipamentoEquipeDireta] = Field(default_factory=list)
    custo_mao_obra_mensal: float = 0.0  # salário base × num_pessoas (sem encargos)
    # NEP-037 D1: encargos sociais separados do salário base para reconciliar fe_nec com PU_sbdi.
    # Invariante: custo_total inclui encargos (= custo_mao_obra_mensal + custo_encargos_mensal + ...)
    # fe_nec = (custo_mao_obra_mensal + custo_equip + diesel) / (PU_sbdi × Q) → 1/η_p
    custo_encargos_mensal: float = 0.0  # Σ salario_base × percentual_encargos × num_pessoas
    # ADR-030 D3 / ADR-088: separação aluguel | combustivel | manutencao
    custo_equipamentos_mensal: float = 0.0  # aluguel + manutencao (sem combustivel)
    custo_combustivel_total_mensal: float = 0.0  # combustivel total da equipe
    custo_material_mensal: float = 0.0
    custo_fixo_mensal: float = 0.0
    # ADR-088: sub-campos de equipamento agregados da equipe
    custo_locacao_mensal: float = 0.0  # Σ equipamentos.custo_locacao_mensal × num_unidades
    custo_manutencao_mensal: float = 0.0  # Σ equipamentos.custo_manutencao_mensal × num_unidades
    # Invariante: custo_equipamentos_mensal ≈ custo_locacao_mensal + custo_manutencao_mensal
    permanencia_meses: float = Field(default=0.0, ge=0)
    permanencia_efetiva_meses: float = Field(default=0.0, ge=0)  # Σ(num_equipes_j) / SEMANAS_POR_MES — correto para N>1
    custo_total: float = 0.0
    modo_estimativa: Literal["inicial", "refinado"] = "refinado"  # ADR-030 D4
    # NEP-031 L2: custo de aluguel de equipamentos ociosos dentro da janela de mobilização (§6.3)
    custo_ocioso_equipamentos: float = 0.0
    # NEP-031 L3: custo total de mobilização/desmobilização por eventos detectados (§8)
    custo_mob_desmob: float = 0.0
    # ADR-105 F1-F3: desdobramento de custo_mob_desmob em fases (preparatório para ADR-106).
    # Invariante quando preenchido: custo_mobilizacao_mensal + custo_desmobilizacao_mensal ≈ custo_mob_desmob.
    # custo_operacao_mensal captura custos recorrentes de canteiro (veículos de suporte, geradores, etc.)
    # — independente de mob/demob, extraído de indiretos.adm em sprint S3.
    custo_mobilizacao_mensal: float = 0.0  # custo de transporte + montagem na chegada
    custo_operacao_mensal: float = 0.0  # custos fixos recorrentes de canteiro (≠ mob/demob)
    custo_desmobilizacao_mensal: float = 0.0  # custo de desmontagem + transporte de retorno
    # ADR-071: campos de pool contract — preenchidos quando rcpsp_spec presente em skill-05
    custo_total_autonomo: float = 0.0  # custo disjunto original (diagnóstico/comparação)
    contrato_tipo_id: str = ""  # tipo_id do RecursoContrato atribuído; "" = sem pool
    fracao_atribuicao: float = 0.0  # fração do custo_contrato atribuída a este item

    # ADR-104: Decomposição Instancial de Custos (Estágio 4 — preenchido após ADR-085)
    # Invariante: se custo_inst_mo is not None, então
    #   abs(custo_inst_mo + custo_inst_eq + custo_inst_comb + custo_inst_mat + custo_inst_mob_demob - custo_total) < 0.05
    custo_inst_mo: float | None = None  # Mão de obra instancial (Estágio 4). None = Estágio 1/3
    custo_inst_eq: float | None = None  # Equipamentos instancial (Estágio 4). None = Estágio 1/3
    custo_inst_comb: float | None = None  # Combustível/diesel instancial (Estágio 4). None = Estágio 1/3
    custo_inst_mat: float | None = None  # Materiais instancial (Estágio 4). None = Estágio 1/3
    custo_inst_mob_demob: float | None = None  # Mob + Demob instancial (Estágio 4). None = Estágio 1/3


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
    # ADR-090: sub-custos por categoria_insumo — calculados por skill-07.
    # Permite BDI diferenciado por natureza (MO ≈ 30%, EQ ≈ 30%, material/comb = 4%, verba ≈ 25%).
    # Invariante: custo_total ≈ custo_mao_obra + custo_equipamentos + custo_combustivel
    #                          + custo_verba + custo_mobilizacao
    custo_mao_obra: float = 0.0  # funcoes base (sem encargos) — BDI_mao_obra
    # NEP-037 D4: encargos sociais separados do salário base, mesmo para indiretos.
    custo_encargos: float = 0.0  # encargos sobre MO indireta — BDI_mao_obra (mesmo rate)
    custo_equipamentos: float = 0.0  # equipamentos (aluguel+manut, sem comb) — BDI_servicos
    custo_combustivel: float = 0.0  # combustivel de equipamentos indiretos — BDI_material
    custo_verba: float = 0.0  # verbas_mensais + verbas_fixas — BDI_indireto
    custo_mobilizacao: float = 0.0  # mobilizacoes (overhead admin) — BDI_indireto


class LeverEquilibrio(BaseModel):
    """ADR-082: Ação operacional/contratual que fecha parcialmente o gap do ponto de equilíbrio."""

    model_config = ConfigDict(extra="ignore")

    id: str  # "fechar_gap_escala" | "fechar_gap_praticabilidade" | "fechar_gap_pool" | "revisao_bdi_minima"
    tipo: Literal["custo", "preco"]
    descricao: str
    delta_margin: float  # R$ — positivo = melhoria de margem
    delta_margin_pct: float  # fração de custo_venda_cpu
    viavel: bool  # False quando o gap já é ≤ 0 (lever sem efeito)
    restricoes: list[str] = Field(default_factory=list)  # caveats / condições de aplicação


class PontoEquilibrio(BaseModel):
    model_config = ConfigDict(extra="ignore")

    item_id: str
    custo_fixo_equipe: float
    custo_venda_cpu: float
    delta: float
    delta_pct: float
    status_validacao: StatusValidacao
    custo_operacional_real: float = 0.0  # custo_total da equipe (real, inclui pool overhead)
    frentes_equivalentes: float = 1.0  # custo_operacional_real / custo_fixo_equipe

    # ADR-051 Link: Rastreio de confiabilidade do PE baseado em validação de PU
    validacao_pu_status: Literal["VERDE", "AMARELO", "VERMELHO"] | None = None
    confianca_pe: Literal["ALTA", "MEDIA", "BAIXA"] | None = None
    diagnostico_pu: str | None = None  # ex: "PU subestimado em 8%, PE pode ser otimista"

    # ADR-076 Opção C: diagnóstico quantitativo de viabilidade
    # frentes_equivalentes_necessarias = custo_total_autonomo / (PU_sem_bdi × Q)
    # Responde: "quantas vezes o preço de catálogo seria necessário para cobrir a execução autônoma?"
    frentes_equivalentes_necessarias: float = 1.0
    gap_pool_overhead: float = 0.0  # custo_operacional_real − custo_total_autonomo (signed: <0 = pool economiza)
    status_frentes: Literal["OK", "AVISO", "CRITICO"] | None = None  # OK≤1.25, AVISO≤1.5, CRITICO>1.5

    # ADR-076 Opção D: calibração de PU — ajuste mínimo para margem zero
    pu_catalogo_unitario: float = 0.0  # PU_sem_bdi por unidade (referência catálogo)
    pu_calibrado_unitario: float = 0.0  # max(pu_catalogo, custo_total_autonomo / Q)
    ajuste_minimo_pct: float = 0.0  # (pu_calibrado − pu_catalogo) / pu_catalogo × 100
    gap_praticabilidade_abs: float = 0.0  # RESIDUAL pós-escala: custo_total_autonomo − (custo_base × N_equipes)
    # ≈ 0 para execução puramente proporcional; >0 indica desvio real de produtividade
    # (ex: extensão de prazo por clima além da compressão de N equipes, maior consumo de combustível)
    # NOTA: ≠ custo_total_autonomo − custo_base (esse seria gap_escala, não praticabilidade)
    gap_pool_abs: float = 0.0  # alias de economia_pool_abs com sinal invertido (>0 = pool onerou)

    # ADR-076 Justificativa de Lesão de Produtividade Horária
    # Campos derivados de distribuicao_semanal — rastreiam a origem do desvio por componente
    n_equipes_efetivo: float = 1.0  # team_weeks / active_weeks (número médio real de equipes)
    semanas_ativas: int = 0  # semanas com num_equipes > 0
    fator_clima_medio: float = 1.0  # média ponderada de fator_clima por equipe×semana
    fator_calendario_medio: float = 1.0  # média ponderada de fator_calendario por equipe×semana
    semanas_lesadas_clima: int = 0  # semanas com fator_clima < 0.90
    gap_escala_abs: float = 0.0  # custo_base_catalogo × (N_equipes − 1): custo por compressão de prazo
    diagnostico_lesao: str | None = None  # texto gerado: fonte dominante do desvio

    # ADR-082: Levers de ação para fechar o gap do ponto de equilíbrio
    levers_equilibrio: list[LeverEquilibrio] = Field(default_factory=list)

    # NEP-042: Modelo de três camadas — materialização explícita (D1 + D2 + D3)
    # Camada 2: PU operacional autônomo
    pu_operacional_autonomo: float = 0.0  # custo_total_autonomo / Q_i — sempre exposto
    machine_weeks_brutas: float = 0.0  # MW_i = Σ_j m_{ij} (equipes × semanas ativas)
    machine_weeks_efetivas: float = 0.0  # eMW_i = Σ_j (m_{ij} × η_j) (ponderado por eficiência)
    eta_real: float = 1.0  # η_real = eMW_i / MW_i (eficiência média ponderada)
    # Camada 3: PU pool instancial
    custo_pool_total: float = 0.0  # Σ_r custo_total_particionado_r para esta atividade
    custo_pool_por_unidade: float = 0.0  # custo_pool_total / Q_i — razão comparativa, não preço
    economia_pool_abs: float = 0.0  # custo_total_autonomo − custo_pool_total (>0 = pool economiza)


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


class CustoParticionadoItem(BaseModel):
    """Partição causal de custo de pool por item — ADR-083/084.

    Decompõe o custo atribuído em componentes causais via diagrama de Euler
    sobre IntervalSet (eule[interval]) — ADR-084 D2.

    Campos Fase 2 (já implementados via _compute_particao_por_tipo):
      custo_produtivo, custo_mob_imputado, custo_ocioso_imputado,
      custo_total_particionado, economia_mob, overhead_ocioso

    Campos Fase 3 (implementados via particionar_contrato() com euler()):
      custo_produtivo_exclusivo, custo_produtivo_compartilhado,
      custo_demob_imputado, custo_total_autonomo, economia_vs_autonomo,
      predecessor_critico_id, overlap_semanas
    """

    model_config = ConfigDict(extra="ignore")

    item_id: str

    # ── Fase 2 — implementado ────────────────────────────────────────────────
    custo_produtivo: float = 0.0  # machine_weeks × custo_unit (produção direta)
    custo_mob_imputado: float = 0.0  # fração de mob/demob atribuída (Shapley igual por cadeia)
    custo_ocioso_imputado: float = 0.0  # custo de idle gap imputado ao item como sucessor causal
    custo_total_particionado: float = 0.0  # = custo_atribuido_i (autoridade via ADR-071 D3)
    economia_mob: float = 0.0  # mob_standalone − mob_imputado (>0 = economia)
    overhead_ocioso: float = 0.0  # = custo_ocioso_imputado (custo de gap imputado)

    # ── Fase 3 — ADR-084 D2, via euler() ────────────────────────────────────
    custo_produtivo_exclusivo: float = 0.0  # custo em regiões onde só esta atividade está ativa
    custo_produtivo_compartilhado: float = 0.0  # custo em regiões de sobreposição atribuídas a esta
    custo_demob_imputado: float = 0.0  # C_demob / n (separado de mob)
    custo_total_autonomo: float = 0.0  # custo se item contratasse sozinho (baseline)
    economia_vs_autonomo: float = 0.0  # custo_total_autonomo − custo_total_particionado
    predecessor_critico_id: str | None = None  # predecessor que determina T_start na DAG
    overlap_semanas: float = 0.0  # semanas ativas em sobreposição com outra atividade

    # ── ADR-085 D4: decomposição categorial do custo instancial particionado ──
    # Base bottom-up para BDI diferenciado por categoria (ADR-023).
    # Invariante: custo_inst_mo + custo_inst_eq + custo_inst_comb + custo_inst_mat
    #             == custo_total_particionado (±0,01) — validado por VAL-INST-CAT-SOMA.
    custo_inst_mo: float = 0.0  # mão-de-obra (salário + encargos), inclui MO ociosa (CLT integral)
    custo_inst_eq: float = 0.0  # aluguel de equipamento (ativo + ocioso à taxa reduzida)
    custo_inst_comb: float = 0.0  # combustível (apenas produtivo)
    custo_inst_mat: float = 0.0  # material (apenas produtivo)


class CadeiaPerpetuacao(BaseModel):
    """Cadeia de perpetuação de instâncias de recurso — ADR-073.

    Agrupa atividades consecutivas que usam o mesmo tipo de recurso com gap ≤ δ,
    mantendo a frota mobilizada entre atividades para evitar mob/demob intermediários.

    Uma cadeia gera exatamente 1 mobilização e 1 desmobilização, independentemente
    do número de atividades cobertas.
    """

    model_config = ConfigDict(extra="ignore")

    cadeia_id: str  # ex: "cadeia-desmat-1"
    tipo_id: str  # ex: "DESMAT"
    item_ids: list[str] = Field(default_factory=list)  # atividades em ordem de início
    semana_inicio: str = ""  # primeira semana ativa do primeiro item
    semana_fim: str = ""  # última semana ativa do último item
    semanas_ativas: int = 0  # soma de active_weeks de todos os itens
    semanas_ociosas: int = 0  # soma dos gaps dentro da cadeia
    n_mobilizacoes: int = 1  # sempre 1 por cadeia
    n_desmobilizacoes: int = 1  # sempre 1 por cadeia
    custo_standby: float = 0.0  # custo de manutenção durante gaps
    machine_weeks_ativas: int = 0  # Σ required_i × active_weeks_i (ramp-adjusted)
    delta_aplicado_semanas: int = 2  # threshold de gap efetivo usado


class RecursoContrato(BaseModel):
    """Contrato de pool de recursos — ADR-071.

    Representa o custo real do contrato de um tipo de recurso compartilhado.
    Em vez de cobrar cada atividade pelo tempo que o recurso fica alocado de
    forma independente (modelo disjunto), o contrato cobre:

        pool_size × custo_unit_semanal × semanas_contrato

    O custo por item é uma atribuição proporcional ao uso (machine-weeks).

    ADR-073: campos de perpetuação (n_cadeias, custo_mob_desmob_contrato,
    custo_standby_total, r_naive) enriquecidos pelo skill-05 quando disponível.
    """

    model_config = ConfigDict(extra="ignore")

    contrato_id: str  # ex: "contrato-esc-3cat"
    tipo_id: str  # ex: "ESC-3CAT"
    quantidade_contratada: int  # pool_size do rcpsp_spec
    semana_inicio: str  # primeira semana ativa (ex: "S001")
    semana_fim: str  # última semana ativa
    semanas_contrato: int  # span total (semana_fim_idx - semana_inicio_idx + 1)
    custo_unit_semanal: float  # custo médio por unidade × semana (média ponderada)
    custo_total_contrato: float  # quantidade × custo_unit × semanas
    items_cobertos: list[str] = Field(default_factory=list)  # item_ids que usam este tipo
    # ADR-080: semana de mobilização por instância (número → semana ISO).
    # {} = todas as instâncias são mobilizadas desde semana_inicio (comportamento legado).
    mobilizacao_por_instancia: dict[int, str] = Field(default_factory=dict)
    # ADR-073: diagnóstico de perpetuação
    n_cadeias: int = 0  # número de cadeias (= número de mob/demob do tipo)
    custo_mob_desmob_contrato: float = 0.0  # n_cadeias × (custo_mob + custo_demob) × pool
    custo_standby_total: float = 0.0  # custo standby dentro dos gaps entre cadeias
    r_naive: int = 0  # R_r^naive = Σ e_{i,r} (upper bound disjunto)
    # ADR-078: custos de mob/demob/idle por unidade — opcionais (backward-compatible)
    custo_mob_unit: float = 0.0  # R$/unidade — mobilização
    custo_demob_unit: float = 0.0  # R$/unidade — desmobilização
    custo_idle_semanal_unit: float = 0.0  # R$/unidade/semana — standby contínuo
    unidade_faturamento: str = "hora_prod"  # "hora_prod" | "dia_cal" | "mes"
    gap_max_economico: int = 9999  # calculado em skill-05 pelo _build_pre_processamento
    # ADR-085 D2 / ADR-088: decomposição da taxa semanal unitária por componente.
    # Σ(custo_unit_semanal_*) ≈ custo_unit_semanal.
    custo_unit_semanal_mo: float = 0.0  # taxa MO por unidade×semana (ativa = ociosa, CLT)
    custo_unit_semanal_eq: float = 0.0  # taxa aluguel+manut por unidade×semana (ativa)
    custo_unit_semanal_comb: float = 0.0  # taxa combustível por unidade×semana (apenas ativa)
    custo_unit_semanal_mat: float = 0.0  # taxa material por unidade×semana (apenas ativa)
    rho_idle_eq: float = 1.0  # fração da taxa EQ cobrada em standby (idle/ativa)
    # ADR-088: sub-decomposição de EQ (locacao | manutencao)
    custo_unit_semanal_locacao: float = 0.0  # taxa aluguel puro (BDI_servicos)
    custo_unit_semanal_manutencao: float = 0.0  # taxa manutenção (BDI_servicos)
    # Invariante: custo_unit_semanal_eq ≈ custo_unit_semanal_locacao + custo_unit_semanal_manutencao
    # ADR-083: partição causal de custo por item (produtivo + ocioso + mob_imputado)
    particao_por_item: list[CustoParticionadoItem] = Field(default_factory=list)


# ── ADR-077: Recurso Instancial ───────────────────────────────────────────────


class SegmentoAtividade(BaseModel):
    """Segmento contínuo de alocação de um slot de recurso a uma atividade — ADR-083.

    Captura o intervalo exato [semana_inicio, semana_fim] em que um slot específico
    de um contrato de pool esteve alocado a uma atividade sem interrupção.  Gerado
    por `_build_instancias_recurso` a partir do rastreio semana-a-semana do slot.
    Utilizado por `_enrich_particao_overhead` para calcular `overhead_ocioso` e
    `custo_ocioso_imputado` com base nos gaps reais entre atividades consecutivas.
    """

    model_config = ConfigDict(extra="ignore")

    activity_id: str  # item_id da atividade coberta
    semana_inicio: str  # primeira semana do segmento (ISO, ex: "2026-W35")
    semana_fim: str  # última semana do segmento (inclusive)
    machine_weeks: int = 0  # quantidade de semanas de trabalho neste segmento


class InstanciaRecurso(BaseModel):
    """Slot instancial de um contrato de pool — ADR-077.

    Representa uma posição contratual numerada dentro do pool (ex: "ESC-3CAT-03"),
    com rastreio de utilização ao longo do projeto.

    Não representa um ativo físico específico — o contrato compra capacidade (slots),
    e o ativo físico que ocupa um slot pode variar por substituição ou manutenção.
    """

    model_config = ConfigDict(extra="ignore")

    instancia_id: str  # ex: "ESC-3CAT-03"
    contrato_id: str  # FK → RecursoContrato.contrato_id
    tipo_id: str  # ex: "ESC-3CAT"
    numero: int  # 1-based: posição no pool
    semana_entrada: str  # primeira semana do contrato
    semana_saida: str  # última semana do contrato
    semanas_ativas: int = 0  # semanas com atividade atribuída
    semanas_standby: int = 0  # semanas contratadas sem atividade
    taxa_utilizacao_pct: float = 100.0  # semanas_ativas / (ativas + standby) × 100
    custo_standby: float = 0.0  # c_idle × semanas_standby (ADR-079) ou custo_unit_semanal (fallback)
    atividades_cobertas: list[str] = Field(default_factory=list)  # activity_ids
    # ADR-079: Desmobilização Antecipada (diagnóstico)
    semana_ultima_atividade: str = ""  # última semana com atividade atribuída
    semanas_antecipacao_possivel: int = 0  # trailing standby evitáveis por desmob antecipada
    economia_desmobilizacao_antecipada: float = 0.0  # R$ economizáveis: max(0, c_idle×trailing - c_demob)
    # ADR-080: desmob antecipada efetiva (True quando economia foi aplicada ao custo_total_contrato)
    desmob_antecipada_aplicada: bool = False
    # ADR-083: linha do tempo de alocação por atividade — segmentos contínuos por slot
    segmentos_atividade: list[SegmentoAtividade] = Field(default_factory=list)

    # ── ADR-085 D1/D3: ciclo de vida e custo instancial composicional ─────────
    # Linha do tempo σ_k(j) ∈ {prod, idle, off}. mob = 1ª semana ativa (mob tardia);
    # demob = última semana coberta (após desmob antecipada efetiva). off = fora do ciclo (custo 0).
    semana_mobilizacao: str = ""  # 1ª semana ativa (late mob); "" = span do contrato (legado)
    semana_desmobilizacao: str = ""  # última semana coberta após desmob efetiva; "" = span do contrato
    semanas_off: int = 0  # semanas do span do contrato fora de [mob, demob] (custo zero)
    # Custo instancial por componente (D2/D3) — soma = custo_instancia_total
    custo_ativo_mo: float = 0.0  # MO em semanas produtivas
    custo_ativo_eq: float = 0.0  # aluguel EQ em semanas produtivas
    custo_ativo_comb: float = 0.0  # combustível em semanas produtivas
    custo_ativo_mat: float = 0.0  # material em semanas produtivas
    custo_idle_mo: float = 0.0  # MO em standby (integral — CLT)
    custo_idle_eq: float = 0.0  # aluguel EQ em standby (taxa reduzida ρ·c_eq)
    custo_mob_instancia: float = 0.0  # custo de mobilização imputado a esta instância
    custo_demob_instancia: float = 0.0  # custo de desmobilização (efetivo quando desmob antecipada)
    custo_instancia_total: float = 0.0  # Σ de todos os termos acima (ADR-085 D3)
    # ADR-086: gaps-ponte mantidos ociosos (idle) deste slot — activity_id="__idle__".
    # Registrados por _build_instancias_recurso onde a classificação idle/off já ocorre,
    # para o CuboPoolInstancial reconstruir o estado semana a semana sem recomputar (ADR-086 R3).
    segmentos_idle: list[SegmentoAtividade] = Field(default_factory=list)


class ComposicaoEquipeAtividade(BaseModel):
    """Composição instancial da equipe de uma atividade — ADR-077.

    Liga uma atividade às instâncias do pool que a alimentaram, com rastreabilidade
    dos slots utilizados e do volume de machine-weeks gerado.
    """

    model_config = ConfigDict(extra="ignore")

    activity_id: str  # item_id (EAP)
    tipo_id: str  # tipo do recurso (ex: "ESC-3CAT")
    contrato_id: str  # FK → RecursoContrato.contrato_id
    pool_size: int  # quantidade_contratada do contrato
    n_instancias: int  # nº de slots atribuídos a esta atividade
    required: int  # required_resources[tipo_id] do rcpsp_spec
    instancias_numeros: list[int] = Field(default_factory=list)  # números dos slots usados
    semana_inicio: str = ""  # primeira semana ativa da atividade
    semana_fim: str = ""  # última semana ativa da atividade
    machine_weeks: int = 0  # total machine-weeks (required × active_weeks)


class ResumoUtilizacaoContrato(BaseModel):
    """Resumo agregado de utilização por contrato de pool — ADR-077.

    Agrega métricas de OEE simplificado (sem qualidade, foco em disponibilidade × uso)
    para um tipo de recurso ao longo do projeto.
    """

    model_config = ConfigDict(extra="ignore")

    contrato_id: str
    tipo_id: str
    quantidade_contratada: int
    semanas_contrato: int
    machine_weeks_disponiveis: int  # quantidade_contratada × semanas_contrato
    machine_weeks_usados: int  # Σ semanas_ativas de todas as instâncias
    machine_weeks_standby: int  # Σ semanas_standby de todas as instâncias
    taxa_utilizacao_pct: float  # machine_weeks_usados / disponiveis × 100
    custo_standby_total: float  # custo_unit_semanal × machine_weeks_standby
    instancias_standby_alto: list[str] = Field(default_factory=list)  # IDs com utilização < 65%
    # OK ≥ 65%, AVISO 35–65%, CRITICO < 35%
    status_utilizacao: Literal["OK", "AVISO", "CRITICO"] = "OK"


# ── ADR-078: Pré-processamento Estrutural de Compartilhamento ────────────────


class OportunidadeCompartilhamento(BaseModel):
    """Par de atividades com potencial de economia via serialização — ADR-078.

    Cada instância representa uma aresta `(i, j, r)` do grafo de oportunidades H:
    atividade `i` termina antes de `j`, ambas usam o tipo `r`, e perpetuar `r`
    entre elas tem economia potencial `delta_c_pot` descontada pela eficiência `eta`.
    """

    model_config = ConfigDict(extra="ignore")

    atividade_i: str  # item_id da atividade anterior
    atividade_j: str  # item_id da atividade posterior
    tipo_id: str  # tipo de recurso compartilhado
    gap_semanas: int  # semanas entre fim(i) e início(j)
    gap_max_semanas: int  # gap_r^max — limite de viabilidade
    eta: float  # η ∈ [0,1] — eficiência com desconto idle
    omega_bundle: float  # Ω ∈ [0,1] — fração econômica do bundle
    delta_c_pot: float  # R$ — economia potencial máxima
    lambda0: float  # δC × Ω — penalidade inicial Scheduling Modo B
    recursos_compartilhaveis: dict[str, int] = Field(default_factory=dict)  # ov_vector
    economicamente_viavel: bool = True  # gap <= gap_max


class OportunidadeCompartilhamentoParalelo(BaseModel):
    """Par de atividades paralelizáveis via compartilhamento de recurso — ADR-110.

    Detectado automaticamente pós-RCPSP. O solver serializou (i, j) exclusivamente
    por escassez de pool (pool == 1, demanda == 2). Ambas têm folga CPM positiva,
    portanto a alternativa de paralelo-com-alternância é geometricamente viável.

    O planejador recebe o balanço custo × prazo e decide aceitar ou rejeitar.
    """

    model_config = ConfigDict(extra="ignore")

    atividade_i: str          # item_id — uma das atividades do par
    atividade_j: str          # item_id — outra atividade do par
    tipo_recurso_id: str      # tipo de recurso compartilhável
    recurso_e_gargalo: bool   # True → compartilhar estende duration (limite_producao == "equipamento" e r é equip principal)
    delta_makespan_semanas: int  # semanas adicionais no makespan total (0 se r é suporte)
    delta_custo_frota: float  # R$ economizado em frota (1 unidade poupada) — positivo = economia
    delta_indiretos: float    # R$ adicional em indiretos pelo Δ_makespan — positivo = custo extra
    delta_liquido: float      # delta_custo_frota − delta_indiretos
    economicamente_viavel: bool  # delta_liquido > 0


class RelatorioOportunidades(BaseModel):
    """Artefato de pré-processamento estrutural — ADR-078.

    Produzido pelo _build_pre_processamento_compartilhamento em skill-05 quando
    `rcpsp_spec.resource_costs` está presente. Contém o grafo de oportunidades H
    completo (incluindo arestas inviáveis para auditoria).

    ADR-110: `oportunidades_paralelo` agrega os candidatos a compartilhamento
    paralelo detectados automaticamente pós-RCPSP.
    """

    model_config = ConfigDict(extra="ignore")

    total_oportunidades: int  # |H| total (viáveis + podadas)
    total_economia_pot: float  # Σ delta_c_pot (apenas viáveis)
    oportunidades_podadas: int  # count(economicamente_viavel=False)
    lambda0_total: float  # Σ lambda0 (apenas viáveis)
    oportunidades: list[OportunidadeCompartilhamento] = Field(default_factory=list)
    gap_max_por_tipo: dict[str, int] = Field(default_factory=dict)  # {tipo_id: gap_max}
    # ADR-110: candidatos a paralelo-com-alternância (detecção pós-RCPSP)
    oportunidades_paralelo: list[OportunidadeCompartilhamentoParalelo] = Field(default_factory=list)


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
    # ADR-074: normalized ramp profile propagated from Activity; None = flat demand
    ramp_profile: list[float] | None = None

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
    algorithm: Literal["manual_allocation", "MINSLK", "LPT", "MAXRES", "ES", "GR", "MILP", "CP-SAT", "LNS"] = (
        "manual_allocation"
    )
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


def _migrate_cron_item_to_dict(item) -> dict | None:
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump()
    return None


def _extract_weeks_from_dist(dist_semanal: dict) -> list:
    weeks = []
    for k in dist_semanal:
        if "-W" in str(k):
            try:
                weeks.append(int(str(k).split("-W")[1]))
            except (ValueError, IndexError):
                pass
    return weeks


def _migrate_cron_list_to_cronograma(cron: list) -> dict:
    scheduled = []
    for item in cron:
        item_data = _migrate_cron_item_to_dict(item)
        if item_data is None:
            continue
        item_id = item_data.get("item_id", "")
        dist_semanal = item_data.get("distribuicao_semanal") or {}
        if not dist_semanal:
            dist_semanal = item_data.get("distribuicao_mensal") or {}
        weeks = _extract_weeks_from_dist(dist_semanal)
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
    return {"algorithm": "manual_allocation", "scheduled_activities": scheduled}


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
    intervention_assessments: list[dict] | None = None

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
    # Tabela BDI efetiva usada para construir cubo_analitico e calcular preços (Skill-08).
    # Persistida para garantir que o lazy-build do serviço e o _build_from_pool (ADR-086)
    # usem exatamente a mesma formulação BDI — elimina divergência entre pipeline e on-demand.
    # Usa forward ref para evitar import circular com o módulo bdi.
    tabela_bdi_efetiva: TabelaBdi | None = None

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
            values["cronograma"] = _migrate_cron_list_to_cronograma(cron)
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
    """LEGADO — resultado após delta de aquisição de recurso (skill 06A, removida).

    Todos os campos são populados com zeros pela skill-08 atual. Mantido apenas para
    retrocompatibilidade de serialização e fixtures de testes. Não usar em código novo.
    Candidato a remoção quando os fixtures de teste forem migrados.
    """

    model_config = ConfigDict(extra="ignore")

    itens_aquisicao: list[ItemCustoAquisicao] = Field(default_factory=list)
    delta_custo_total: float = 0.0
    venda_total_com_bdi: float = 0.0
    custo_total_reconciliado: float = 0.0
    margem_reconciliada_pct: float = 0.0
    status_margem_reconciliado: StatusMargem = "VERDE"
    delta_status: str | None = None


class ReplanSugestao(BaseModel):
    """Sugestão concreta de re-planejamento com checkpoint e parâmetros (13-replanejamento-e-cenarios)."""

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
    """Seção canônica produzida por 13-replanejamento-e-cenarios."""

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

    tipo: Literal[
        # Legado (ADR-021)
        "EXPAND_POOL",
        "REDUCE_DURATION",
        "ADD_TEAMS",
        "REVIEW_BDI",
        # Baseados em LeverEquilibrio real (ADR-082) — pool-aware
        "SERIALIZAR_CRONOGRAMA",  # fechar_gap_escala: serializar equipes, estender prazo
        "MELHORAR_PRATICABILIDADE",  # fechar_gap_praticabilidade: reordenar por época climática
        "OTIMIZAR_POOL",  # fechar_gap_pool: reduzir overhead mob/demob/ociosidade
        "RECALIBRAR_PU",  # revisao_bdi_minima: recalibrar PU para cobrir custo real
    ]
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
    """Resultado do 13-replanejamento-e-cenarios (estágio explorador): repair_path e/ou oportunidades."""

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
