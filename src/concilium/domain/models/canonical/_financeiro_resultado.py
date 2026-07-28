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
    # Issue #124: limitação conhecida — gap climático diagnosticado na bridge (N3) mas
    # nunca cobrado no custo operacional real (N4). Ver LimitacaoClimaN4.
    limitacao_clima_n4: "LimitacaoClimaN4 | None" = None


# ── Fase 2: Resource Binding ──────────────────────────────────────────────

