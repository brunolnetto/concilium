"""Camada 4 — Modelo canônico do orçamento (parte extraída de canonical.py)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from concilium.domain.models.catalog.catalogo import PapelFuncao


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
    tipo_combustivel: str | None = None
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
    #   abs(custo_inst_mo + custo_inst_eq + custo_inst_comb + custo_inst_mat
    #       + custo_inst_mob_demob - custo_total) < 0.05
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


