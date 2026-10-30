"""Camada 4 — Modelo canônico do orçamento (parte extraída de canonical.py)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ._base import StatusMargem, StatusValidacao, ValidacaoItem


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
    # Issue #132: preço veio da Fonte 2 (composicao_itens × preco_insumo), sem relação
    # com produtividade — não há base bottom-up (NEP-032) para este item.
    precificacao_via_fallback_composicao: bool = False
    # ADR-162 D1: ρ_i — Producao.valor_horario resolvida na Fonte 1 (bottom-up, NEP-032).
    # 0.0 quando não resolvível (Fonte 2/fallback de composição, ou override manual de PU)
    # — γ_i^v/causa_dominante ficam INDETERMINADO nesses casos, nunca um valor inventado.
    produtividade_catalogo: float = 0.0
    # ADR-172: β_i — média de η_p (praticabilidade: clima×calendário×jornada) ponderada por
    # num_equipes sobre o cronograma já construído deste item. Aplicado como produtividade
    # efetiva (ρ_i·β_i) na precificação — nunca sobrescreve produtividade_catalogo (ρ_i puro,
    # referência estrutural do catálogo). 1.0 (sem correção) quando o item não tem cronograma
    # associado ou não há semanas ativas — nunca um valor inventado.
    beta_praticabilidade: float = 1.0


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
    pu_catalogo_unitario: float = 0.0  # PU_sem_bdi por unidade (referência catálogo) = custo_venda_cpu / Q
    # ADR-162: PU operacional real = custo_fixo_equipe / Q (custo_fixo_equipe é o custo
    # operacional agregado real, ver comentário em _build_pe_for_equipe — NÃO usar
    # custo_total_autonomo/Q aqui, esse é pu_operacional_autonomo, grandeza diferente).
    # Comparável diretamente a pu_catalogo_unitario: delta/Q ≈ pu_catalogo_unitario − pu_operacional_unitario.
    pu_operacional_unitario: float = 0.0
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

    # ADR-162 D1: decomposição causal de delta em duas famílias — cronograma (gap de
    # horas reais vs catalogadas) e precificação (gap entre a taxa de venda e a taxa
    # real de execução). Partição simétrica (Shapley/Bennet — ver _pe_causa_dominante em
    # _ponto_equilibrio.py): o termo de interação entre as duas causas é dividido meio a
    # meio, em vez de atribuído inteiro a uma convenção arbitrária. "MISTO" quando nenhuma
    # causa tem participação claramente maior (share < 65%); "INDETERMINADO" quando
    # H_i/γ_i^v/γ_i^o não são resolvíveis (ex.: sem schedule real ainda, ou item sem base
    # bottom-up de produção) — nunca um valor inventado.
    causa_dominante: Literal["CRONOGRAMA", "PRECIFICACAO", "MISTO", "INDETERMINADO"] = "INDETERMINADO"
    t_cronograma: float = 0.0  # (H_cat − H_i) · (γ_i^v + γ_i^o)/2 — partição simétrica, gap de horas
    t_precificacao: float = 0.0  # (γ_i^v − γ_i^o) · (H_cat + H_i)/2 — partição simétrica, gap de taxa

    # ADR-162 D2/D3: teto de competitividade Γ (config/perfis/<id>.json, campo
    # `teto_ponto_equilibrio_rs`, opt-in por perfil — None = desabilitado) e o intervalo de
    # horas reais toleradas que ele implica. Informativo (relatório/Excel), nunca gate de
    # schedule. None quando Γ não configurado, ou γ_i^o não resolvível (mesma condição de D1).
    horas_reais_min: float | None = None  # (custo_venda_total − Γ) / γ_i^o
    horas_reais_max: float | None = None  # custo_venda_total / γ_i^o
    # Seção 28 do formulário: β̄_i(ε_i) = P_i^op/OC_i − 1 (BDI efetivo dado a composição instancial)
    bdi_equivalente: float = 0.0


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
    # Seção 28: β̄_proj = P_dir / C_dir − 1 (média ponderada dos BDIs por fração de custo do projeto)
    bdi_equivalente_proj: float = 0.0
    # Seção 28: pool direto = β̄_dir = P_dir / C_dir − 1 (agrega todas as equipes diretas)
    bdi_equivalente_direto: float = 0.0
    # Seção 28: pool indireto = β̄_ind = P_ind / C_ind − 1 (bottom-up das sub-categorias de indiretos)
    bdi_equivalente_indireto: float = 0.0


class CustoTotal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    direto_equipes: float  # custo real das equipes no campo (MO+EQ×tempo + materiais cat)
    indireto_adm: float = 0
    indireto_top: float = 0
    indireto_lab: float = 0
    indireto_qsms: float = 0
    indireto_mob: float = 0
    # ADR-184 (continuação da ADR-151 D4): custo do déficit de estoque de consumível
    # provisionado externamente (deficit × preço, quando precificado) — já incluído em
    # `total`, exposto à parte para auditoria (mesmo padrão dos `indireto_*`).
    deficit_estoque_externo: float = 0
    total: float


class LimitacaoClimaN4(BaseModel):
    """Issue #124 — visibiliza que o gap climático diagnosticado (N3) nunca é cobrado em N4.

    Na bridge N1→N2→N3→N4 (ADR-039/NEP-042, ``_bridge.py``), ``gap_praticabilidade_abs``
    é o custo que a praticabilidade climática *deveria* causar (entra em N3), mas esse valor
    nunca entra em N4 — o custo operacional real (pool instancial) efetivamente cobrado.

    Isso é uma decisão arquitetural deliberada, não uma lacuna a corrigir: a duração das
    atividades não é estendida por praticabilidade climática, para manter o RCPSP computável
    (ADR-148 D2-bis, precedente ADR-082-cons). A alternativa de recalibrar o catálogo pela
    eficiência (A3) foi explicitamente rejeitada pelo usuário. Este campo só documenta/expõe
    a limitação — não altera nenhum cálculo de custo, duração ou o valor de N4.
    """

    model_config = ConfigDict(extra="ignore")

    gap_praticabilidade_abs: float = 0.0  # mesmo valor agregado que compõe N3 (Σ gap_praticabilidade_abs)
    cobrado_no_custo_operacional: bool = False  # sempre False — nunca entra em N4, por design
    mensagem: str = (
        "Custo climático diagnosticado na bridge (N3), mas NÃO é cobrado no custo "
        "operacional real (N4): a duração das atividades não é estendida por "
        "praticabilidade climática, por decisão arquitetural que mantém o RCPSP "
        "computável (ADR-148 D2-bis / ADR-082-cons). A alternativa de recalibrar o "
        "catálogo pela eficiência (A3) foi explicitamente rejeitada. Ver issue #124."
    )


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


class MetricasRealizadasP11(BaseModel):
    """Exact, explicit P20×Skill04 diagnostic, NEVER a sale/cost authority.

    Monetary and unitless ratios are canonical fraction strings. They are
    independently replayable and cannot silently round to legacy floats.
    """
    model_config = ConfigDict(extra="forbid")

    authority: Literal["P11_B_READ_ONLY_PREVIEW_NOT_PROJECT_GO"]
    contractual_k: str
    physically_purchased_v: str
    indirect: str
    price_once_bdi: str
    effective_bdi: str | None
    activity_efficiencies: dict[str, str | None]
    zeta: str | None
    pi: str | None
    source: Literal["SKILL04_P20_EXCLUSIVE_POSTINGS"] = "SKILL04_P20_EXCLUSIVE_POSTINGS"


class Resultado(BaseModel):
    model_config = ConfigDict(extra="ignore")

    venda: Venda
    custo: CustoTotal
    metricas_realizadas_p11: MetricasRealizadasP11 | None = None
    resultado_financeiro: float
    margem_pct: float
    status_margem: StatusMargem
    validacoes: list[ValidacaoItem]
    balanco_de_controle: "BalancoControle | None" = None  # ADR-028
    balanco_ponto_equilibrio: "BalancoPontoEquilibrio | None" = None
    # Issue #124: limitação conhecida — gap climático diagnosticado na bridge (N3) mas
    # nunca cobrado no custo operacional real (N4). Ver LimitacaoClimaN4.
    limitacao_clima_n4: "LimitacaoClimaN4 | None" = None
    # P21-C: same pricing evidence is serialized by REST/MCP/UI and RFI/RFP paths.
    pricing_diagnostics: dict[str, str | None] = Field(default_factory=dict)
    pricing_gates: dict[str, str | None] = Field(default_factory=dict)
    pricing_authority: str = "P21_C_PRICING_GATES_NOT_EVALUATED"


# ── Fase 2: Resource Binding ──────────────────────────────────────────────

