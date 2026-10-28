"""Camada 4 — Modelo canônico do orçamento (parte extraída de canonical.py)."""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _finite_numeric_equals(value: object, expected: int) -> bool:
    """Compare a pre-coercion JSON quantity without trusting Pydantic defaults."""
    if isinstance(value, bool):
        return False
    try:
        numeric = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return False
    return numeric.is_finite() and numeric == Decimal(expected)

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
    proveniencia: Literal["CONFIGURADO", "DERIVADO_SKILL03", "DERIVADO_SKILL05"] = "CONFIGURADO"


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
    proveniencia: Literal["CONFIGURADO", "DERIVADO_SKILL03", "DERIVADO_SKILL05", "LEGACY_UNVERIFIED"] = "CONFIGURADO"

    @model_validator(mode="before")
    @classmethod
    def _classify_ambiguous_legacy_pool(cls, value):
        """Quarantine a legacy pool that resembles Skill 05's synthetic default.

        Its ID and quantities are not proof of origin: a declared pool can share
        these values. Preserve the record, but do not treat ambiguous legacy
        provenance as physical capacity or delete it as generated state.
        """
        if isinstance(value, dict) and "proveniencia" not in value:
            tipo_id = value.get("tipo_id")
            if (
                isinstance(tipo_id, str)
                and tipo_id.startswith(("FUNC-", "EQUIP-"))
                and _finite_numeric_equals(value.get("quantidade_total"), 1000)
                and _finite_numeric_equals(value.get("quantidade_disponivel"), 1000)
                and _finite_numeric_equals(value.get("custo_aquisicao_total", 0), 0)
            ):
                return {**value, "proveniencia": "LEGACY_UNVERIFIED"}
        return value


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
    # P16-D: source-of-truth from the typed physical profile a_i,g(m_ij).
    # Empty maps mean legacy unverified provenance: never certify pool parity.
    demanda_fisica_semanal: dict[str, int] = Field(default_factory=dict)
    demanda_por_item_semanal: dict[str, dict[str, int]] = Field(default_factory=dict)
    # Exact physical mobilization m_i,j used when evaluating a_i,g(m_i,j).
    # Do not scale this by weather, calendar or effective throughput.
    # Missing provenance is an uncertified legacy contract.
    frentes_por_item_semanal: dict[str, dict[str, int]] = Field(default_factory=dict)
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
    # P13-B: explicit commercial selector; None is legacy/NOT_EVALUATED, never baseline.
    regime_economico_p13: Literal[
        "FULL_RATE_STANDBY", "DISCOUNTED_STANDBY", "EXPLICIT_OFF_HIRE"
    ] | None = None
    origem_regime_p13: str | None = None  # independently declared contract provenance
    moeda_regime_p13: str | None = None  # no implicit BRL/USD fallback
    # ADR-088: sub-decomposição de EQ (locacao | manutencao)
    custo_unit_semanal_locacao: float = 0.0  # taxa aluguel puro (BDI_servicos)
    custo_unit_semanal_manutencao: float = 0.0  # taxa manutenção (BDI_servicos)
    # Invariante: custo_unit_semanal_eq ≈ custo_unit_semanal_locacao + custo_unit_semanal_manutencao
    # ADR-083: partição causal de custo por item (produtivo + ocioso + mob_imputado)
    particao_por_item: list[CustoParticionadoItem] = Field(default_factory=list)
    # ADR-156: composição de funções de MO por trás deste tipo_id — {funcao_id: num_pessoas}
    # por UMA instância de equipe (não multiplicado por quantidade_contratada). Default {}
    # preserva comportamento (nenhum builder do pipeline real popula ainda — wiring futuro).
    composicao_funcoes_mo: dict[str, int] = Field(default_factory=dict)
    # ADR-157: espelho de composicao_funcoes_mo para equipamento — {equip_id: num_unidades}
    # por UMA instância de equipe. Mesma disciplina (default {}, sem wiring ainda).
    composicao_equipamentos_eq: dict[str, int] = Field(default_factory=dict)


# ── ADR-077: Recurso Instancial ───────────────────────────────────────────────


class SegmentoAtividade(BaseModel):
    """Segmento contínuo de alocação de um slot de recurso a uma atividade — ADR-083.

    Captura o intervalo exato [semana_inicio, semana_fim] em que um slot específico
    de um contrato de pool esteve alocado a uma atividade sem interrupção.  Gerado
    por `_build_instancias_recurso` a partir do rastreio semana-a-semana do slot.
    Utilizado por `_enrich_particao_overhead` para calcular `overhead_ocioso` e
    `custo_ocioso_imputado` com base nos gaps reais entre atividades consecutivas.

    ADR-153 F1: `identidade_fisica_id` é um rótulo opcional, declarado externamente
    após o solve — não muda o que o segmento representa (ainda é sobre o slot
    contratual, não sobre identidade física por definição do próprio slot).
    """

    model_config = ConfigDict(extra="ignore")

    activity_id: str  # item_id da atividade coberta
    semana_inicio: str  # primeira semana do segmento (ISO, ex: "2026-W35")
    semana_fim: str  # última semana do segmento (inclusive)
    machine_weeks: int = 0  # quantidade de semanas de trabalho neste segmento
    # ADR-153 F1: rótulo declarativo opcional — qual ativo físico (matrícula/placa)
    # de fato ocupou este segmento. Nunca preenchido pelo solver/atribuição de slots
    # (ADR-077 segue sem noção de identidade física); só por enriquecimento externo
    # via atribuir_identidade_fisica_segmentos (pool_identidade_fisica.py).
    identidade_fisica_id: str | None = None


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
    """Par de atividades paralelizáveis via compartilhamento de recurso — ADR-133.

    Detectado automaticamente pós-RCPSP. O solver serializou (i, j) exclusivamente
    por escassez de pool (pool == 1, demanda == 2). Ambas têm folga CPM positiva,
    portanto a alternativa de paralelo-com-alternância é geometricamente viável.

    O planejador recebe o balanço custo × prazo e decide aceitar ou rejeitar.
    """

    model_config = ConfigDict(extra="ignore")

    atividade_i: str  # item_id — uma das atividades do par
    atividade_j: str  # item_id — outra atividade do par
    tipo_recurso_id: str  # tipo de recurso compartilhável
    recurso_e_gargalo: (
        bool  # True → compartilhar estende duration (limite_producao == "equipamento" e r é equip principal)
    )
    delta_makespan_semanas: int  # semanas adicionais no makespan total (0 se r é suporte)
    delta_custo_frota: float  # R$ economizado em frota (1 unidade poupada) — positivo = economia
    delta_indiretos: float  # R$ adicional em indiretos pelo Δ_makespan — positivo = custo extra
    delta_liquido: float  # delta_custo_frota − delta_indiretos
    economicamente_viavel: bool  # delta_liquido > 0


class RelatorioOportunidades(BaseModel):
    """Artefato de pré-processamento estrutural — ADR-078.

    Produzido pelo _build_pre_processamento_compartilhamento em skill-05 quando
    `rcpsp_spec.resource_costs` está presente. Contém o grafo de oportunidades H
    completo (incluindo arestas inviáveis para auditoria).

    ADR-133: `oportunidades_paralelo` agrega os candidatos a compartilhamento
    paralelo detectados automaticamente pós-RCPSP.
    """

    model_config = ConfigDict(extra="ignore")

    total_oportunidades: int  # |H| total (viáveis + podadas)
    total_economia_pot: float  # Σ delta_c_pot (apenas viáveis)
    oportunidades_podadas: int  # count(economicamente_viavel=False)
    lambda0_total: float  # Σ lambda0 (apenas viáveis)
    oportunidades: list[OportunidadeCompartilhamento] = Field(default_factory=list)
    gap_max_por_tipo: dict[str, int] = Field(default_factory=dict)  # {tipo_id: gap_max}
    # ADR-133: candidatos a paralelo-com-alternância (detecção pós-RCPSP)
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


