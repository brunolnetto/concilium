"""ADR-023 — Modelo BDI Diferenciado por Categoria de Custo.

Cinco categorias de BDI auditáveis: MAO_OBRA, MATERIAL, SERVICOS, INDIRETO, DIESEL.
Fórmula TCU (Acórdão 2622/2013): BDI = (1 + AC + DF + R + CR + L) / (1 - T) - 1
Perfil por projeto: snapshot imutável coletado em `concilium project create`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from concilium.domain.constants import (
    BDI_COFINS,
    BDI_CSSL,
    BDI_IR,
    BDI_ISS,
    BDI_PIS,
    BDI_TRIBUTOS_MATERIAL,
)

# ── Literals ──────────────────────────────────────────────────────────────

CategoriaBdi = Literal["MAO_OBRA", "MATERIAL", "SERVICOS", "INDIRETO", "DIESEL"]


# ── ADR-055 — Reforma Tributária CBS/IBS ─────────────────────────────────


class TaxRegimeVersion(StrEnum):
    """Versão do regime tributário vigente (ADR-055 §D1).

    PRE_REFORMA    — regime atual PIS/COFINS/ISS (cumulativo)
    TRANSICAO      — fase 2026–2032: CBS/IBS gradualmente introduzidos
    PLENO_CBS_IBS  — 2033+: regime completo não-cumulativo
    """

    PRE_REFORMA = "pre_reforma"
    TRANSICAO = "transicao"
    PLENO_CBS_IBS = "pleno_cbs_ibs"


@dataclass(frozen=True)
class TaxSimulationScenario:
    """Cenário de tributação CBS/IBS para simulação de BDI (ADR-055 §D4).

    Modela o IMPACTO da reforma no preço de proposta — não realiza apuração real.
    Todos os valores são premissas do planejador, não obrigações fiscais.

    Assumptions documentadas:
    - credit_ratio_mao_obra = 0.0: MO é remuneração, não gera crédito CBS/IBS
    - credit_ratio_{material,servicos,diesel}: premissa de compliance do fornecedor
    - credit_lag_semanas: prazo médio de recuperação do crédito via apuração mensal
    - taxa_financ_anual: custo do capital da construtora (CDI ou WACC)
    - CSSL + IR mantidos; sua base de cálculo pode mudar com CBS/IBS mas o impacto
      na fórmula de BDI é pequeno e modelado de forma conservadora aqui.
    """

    regime_version: TaxRegimeVersion

    # CBS + IBS combinados (incidência sobre preço de venda, bruto)
    # Referência: ~26,5% no regime pleno — varia por jurisdição e tipo de contrato
    cbs_ibs_combined_rate: float = 0.0

    # Frações recuperáveis por categoria de custo
    credit_ratio_mao_obra: float = 0.0  # MO direta: sem crédito CBS/IBS
    credit_ratio_material: float = 0.0  # Materiais: alta recuperabilidade
    credit_ratio_servicos: float = 0.0  # Subcontratados: depende do compliance
    credit_ratio_diesel: float = 0.0  # Combustível: redução prevista

    # Custo de carregamento do crédito
    credit_lag_semanas: int = 0  # Semanas até recuperação (apuração mensal ≈ 4-6 sem.)
    taxa_financ_anual: float = 0.12  # CDI / custo de capital da empresa

    # Split payment: retenção na fonte pelo tomador (obras públicas)
    # Não altera BDI — apenas sinaliza impacto de caixa para informação do planejador
    split_payment: bool = False

    # CSSL + IR — mantidos sem crédito CBS/IBS (ADR-056 §T3: constantes de domain/constants.py)
    cssl_rate: float = BDI_CSSL  # 1,99% efetivo sobre receita (Lucro Presumido)
    ir_rate: float = BDI_IR  # 2,74% efetivo sobre receita (Lucro Presumido)

    def tributos_efetivos_por_categoria(self) -> dict[str, float]:
        """Carga líquida por categoria para uso na fórmula TCU BDI (ADR-055 §D2).

        Retorna T_efetivo por categoria = CBS_IBS×(1-credit_ratio) + CSSL + IR.
        No regime PRE_REFORMA, todos os credit_ratios são 0 e CBS_IBS=0, portanto
        os tributos devem ser obtidos diretamente dos campos legados cofins/iss/pis.
        """

        def net(ratio: float) -> float:
            return round(
                self.cbs_ibs_combined_rate * (1.0 - ratio) + self.cssl_rate + self.ir_rate,
                6,
            )

        return {
            "mao_obra": net(self.credit_ratio_mao_obra),
            "material": net(self.credit_ratio_material),
            "servicos": net(self.credit_ratio_servicos),
            "diesel": net(self.credit_ratio_diesel),
            "indireto": net(self.credit_ratio_servicos),  # indiretos tratados como serviços
        }

    def custo_carregamento_df(self, credit_ratio: float) -> float:
        """Adicional ao componente df pelo lag de recuperação do crédito (ADR-055 §D2).

        df_adicional = CBS_IBS_bruto × credit_ratio × (lag_semanas/52) × taxa_financ
        """
        credito_recuperavel = self.cbs_ibs_combined_rate * credit_ratio
        return round(
            credito_recuperavel * (self.credit_lag_semanas / 52.0) * self.taxa_financ_anual,
            6,
        )

    def to_dict(self) -> dict:
        return {
            "regime_version": self.regime_version.value,
            "cbs_ibs_combined_rate": self.cbs_ibs_combined_rate,
            "credit_ratio_mao_obra": self.credit_ratio_mao_obra,
            "credit_ratio_material": self.credit_ratio_material,
            "credit_ratio_servicos": self.credit_ratio_servicos,
            "credit_ratio_diesel": self.credit_ratio_diesel,
            "credit_lag_semanas": self.credit_lag_semanas,
            "taxa_financ_anual": self.taxa_financ_anual,
            "split_payment": self.split_payment,
            "cssl_rate": self.cssl_rate,
            "ir_rate": self.ir_rate,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TaxSimulationScenario:
        rv = data.get("regime_version", "pre_reforma")
        return cls(
            regime_version=TaxRegimeVersion(rv),
            cbs_ibs_combined_rate=float(data.get("cbs_ibs_combined_rate", 0.0)),
            credit_ratio_mao_obra=float(data.get("credit_ratio_mao_obra", 0.0)),
            credit_ratio_material=float(data.get("credit_ratio_material", 0.0)),
            credit_ratio_servicos=float(data.get("credit_ratio_servicos", 0.0)),
            credit_ratio_diesel=float(data.get("credit_ratio_diesel", 0.0)),
            credit_lag_semanas=int(data.get("credit_lag_semanas", 0)),
            taxa_financ_anual=float(data.get("taxa_financ_anual", 0.12)),
            split_payment=bool(data.get("split_payment", False)),
            cssl_rate=float(data.get("cssl_rate", BDI_CSSL)),
            ir_rate=float(data.get("ir_rate", BDI_IR)),
        )


# Cenários canônicos pré-definidos (ADR-055 §D5)
CENARIOS_TRIBUTARIOS: dict[TaxRegimeVersion, TaxSimulationScenario] = {
    TaxRegimeVersion.PRE_REFORMA: TaxSimulationScenario(
        regime_version=TaxRegimeVersion.PRE_REFORMA,
        cbs_ibs_combined_rate=0.0,  # Tributos modelados via campos legados cofins/iss/pis
        credit_ratio_mao_obra=0.0,
        credit_ratio_material=0.0,
        credit_ratio_servicos=0.0,
        credit_ratio_diesel=0.0,
        credit_lag_semanas=0,
    ),
    TaxRegimeVersion.TRANSICAO: TaxSimulationScenario(
        regime_version=TaxRegimeVersion.TRANSICAO,
        cbs_ibs_combined_rate=0.013,  # ~5% do regime pleno em 2026 (1,7% CBS + 0,1% IBS)
        credit_ratio_mao_obra=0.0,
        credit_ratio_material=0.75,
        credit_ratio_servicos=0.60,
        credit_ratio_diesel=0.65,
        credit_lag_semanas=6,
        split_payment=False,
        cssl_rate=BDI_CSSL,
        ir_rate=BDI_IR,
    ),
    TaxRegimeVersion.PLENO_CBS_IBS: TaxSimulationScenario(
        regime_version=TaxRegimeVersion.PLENO_CBS_IBS,
        cbs_ibs_combined_rate=0.265,  # ~26,5% estimativa base (varia por jurisdição)
        credit_ratio_mao_obra=0.0,  # MO direta: sem crédito
        credit_ratio_material=0.80,
        credit_ratio_servicos=0.70,
        credit_ratio_diesel=0.72,
        credit_lag_semanas=4,
        split_payment=True,  # Obras públicas: retenção obrigatória
        cssl_rate=BDI_CSSL,
        ir_rate=BDI_IR,
    ),
}


# ── D1 — Componentes de BDI auditáveis ───────────────────────────────────


class ComponentesBdi(BaseModel):
    """Decomposição auditável de um BDI por categoria de custo (ADR-023 §D1).

    Fórmula TCU Acórdão 2622/2013:
        BDI = (1 + AC + DF + R + CR + L) / (1 - T) - 1
    onde T = cofins + iss + pis + cssl + ir.
    """

    model_config = ConfigDict(frozen=True)

    # Numerador
    ac: float = Field(ge=0, le=1, description="Administração central")
    df: float = Field(ge=0, le=1, description="Despesas financeiras")
    r: float = Field(ge=0, le=1, description="Garantia / risco / seguro")
    cr: float = Field(ge=0, le=1, description="Contingência de risco")
    l: float = Field(ge=0, le=1, description="Lucro")  # noqa: E741

    # Tributos (denominador)
    cofins: float = Field(ge=0, le=1)
    iss: float = Field(ge=0, le=1)
    pis: float = Field(ge=0, le=1)
    cssl: float = Field(ge=0, le=1)
    ir: float = Field(ge=0, le=1)

    @property
    def tributos(self) -> float:
        return round(self.cofins + self.iss + self.pis + self.cssl + self.ir, 6)

    @property
    def overhead(self) -> float:
        """Soma dos componentes de overhead (AC + DF + R + CR + L)."""
        return round(self.ac + self.df + self.r + self.cr + self.l, 6)

    @property
    def bdi_total(self) -> float:
        """BDI calculado pela fórmula TCU. Retorna fração (ex: 0.3450 = 34,50%)."""
        numerador = 1 + self.overhead
        denominador = 1 - self.tributos
        if denominador <= 0:
            raise ValueError(f"Tributos totais >= 1 ({self.tributos:.4f}); BDI indefinido.")
        return round(numerador / denominador - 1, 6)

    def decomposicao_no_preco(self) -> dict[str, float]:
        """ADR-056: decompõe a influência de cada componente do BDI no preço de venda.

        Para PV = C × (1 + BDI) onde BDI = (1+OH)/(1-T) - 1:

            C/PV       = (1-T)/(1+OH)     ← fração de custo direto no preço
            OHx/PV     = OHx × C/PV       ← overhead proporcionalmente sobre PV
            Tributo/PV = tributo           ← tributos são fração direta do preço

        Invariante: soma de todos os valores = 1.0 (100% do preço de venda).

        Exemplo (mao_obra, BDI=34,50%):
            custo_direto  = 74,35%  ← R$74,35 de cada R$100 cobrados
            overhead_ac   =  3,72%
            overhead_df   =  1,11%
            overhead_r    =  0,74%
            overhead_cr   =  0,00%
            margem_l      =  6,69%  ← margem líquida sobre o preço
            tributo_cofins =  3,00%
            tributo_iss   =  5,00%
            tributo_pis   =  0,65%
            tributo_cssl  =  1,99%
            tributo_ir    =  2,74%
        """
        oh = self.overhead
        t = self.tributos
        c_pv = (1.0 - t) / (1.0 + oh) if (1.0 + oh) > 0 else 0.0

        return {
            "custo_direto": round(c_pv, 6),
            "overhead_ac": round(self.ac * c_pv, 6),
            "overhead_df": round(self.df * c_pv, 6),
            "overhead_r": round(self.r * c_pv, 6),
            "overhead_cr": round(self.cr * c_pv, 6),
            "margem_l": round(self.l * c_pv, 6),
            "tributo_cofins": round(self.cofins, 6),
            "tributo_iss": round(self.iss, 6),
            "tributo_pis": round(self.pis, 6),
            "tributo_cssl": round(self.cssl, 6),
            "tributo_ir": round(self.ir, 6),
        }


class TabelaBdi(BaseModel):
    """Tabela de BDI para todos os cinco tipos de custo de um projeto (ADR-023 §D1).

    Funciona como template-base da construtora. A configuração efetiva por projeto
    é obtida via `resolver_componentes_bdi(base, perfil)` em §D7.
    """

    model_config = ConfigDict(frozen=True)

    mao_obra: ComponentesBdi
    material: ComponentesBdi
    servicos: ComponentesBdi
    indireto: ComponentesBdi
    diesel: ComponentesBdi
    data_vigencia: date

    def para_categoria(self, categoria: CategoriaBdi) -> ComponentesBdi:
        return getattr(self, categoria.lower())


# Valores padrão derivados da planilha rfi_catalog.xlsm (abril/2026).
# Tributos (cofins, iss, pis, cssl, ir) importados de domain/constants.py (ADR-056 §T3).
#
# BDI efetivos calculados pela fórmula TCU = (1+OH)/(1-T) - 1:
#   mao_obra  : OH=16,50%  T=13,38%  →  BDI=34,50%
#   material  : OH= 5,00%  T= 0,00%  →  BDI= 5,00%
#   servicos  : OH=16,50%  T=13,38%  →  BDI=34,50%
#   indireto  : OH= 6,00%  T=13,38%  →  BDI=22,37%
#   diesel    : OH= 9,00%  T=13,38%  →  BDI=25,84%
DEFAULT_BDI_TABELA = TabelaBdi(
    mao_obra=ComponentesBdi(
        ac=0.050,
        df=0.015,
        r=0.010,
        cr=0.000,
        l=0.090,
        cofins=BDI_COFINS,
        iss=BDI_ISS,
        pis=BDI_PIS,
        cssl=BDI_CSSL,
        ir=BDI_IR,
    ),
    material=ComponentesBdi(
        # Material (fornecimento): ISS não incide sobre venda de mercadoria
        ac=0.050,
        df=0.000,
        r=0.000,
        cr=0.000,
        l=0.000,
        cofins=BDI_TRIBUTOS_MATERIAL,
        iss=BDI_TRIBUTOS_MATERIAL,
        pis=BDI_TRIBUTOS_MATERIAL,
        cssl=BDI_TRIBUTOS_MATERIAL,
        ir=BDI_TRIBUTOS_MATERIAL,
    ),
    servicos=ComponentesBdi(
        ac=0.050,
        df=0.015,
        r=0.010,
        cr=0.000,
        l=0.090,
        cofins=BDI_COFINS,
        iss=BDI_ISS,
        pis=BDI_PIS,
        cssl=BDI_CSSL,
        ir=BDI_IR,
    ),
    indireto=ComponentesBdi(
        ac=0.040,
        df=0.000,
        r=0.000,
        cr=0.000,
        l=0.020,
        cofins=BDI_COFINS,
        iss=BDI_ISS,
        pis=BDI_PIS,
        cssl=BDI_CSSL,
        ir=BDI_IR,
    ),
    diesel=ComponentesBdi(
        ac=0.040,
        df=0.000,
        r=0.000,
        cr=0.000,
        l=0.050,
        cofins=BDI_COFINS,
        iss=BDI_ISS,
        pis=BDI_PIS,
        cssl=BDI_CSSL,
        ir=BDI_IR,
    ),
    data_vigencia=date(2026, 4, 1),
)


# ── D2 — Encargos Sociais ─────────────────────────────────────────────────


class EncargosRegime(BaseModel):
    """Encargos sociais para uma categoria de trabalhador (ADR-023 §D2).

    Aplicados sobre o salário base ANTES do BDI.
    Total = a + b + c + d + e + f + judicial
    """

    model_config = ConfigDict(frozen=True)

    a: float = Field(ge=0, description="Básicos: INSS, FGTS, salário educação, etc.")
    b: float = Field(ge=0, description="Com incidência de A (férias, 13º, DSR, etc.)")
    c: float = Field(ge=0, description="Sem incidência de A (aviso prévio, etc.)")
    d: float = Field(ge=0, description="Reincidências de B sobre C")
    e: float = Field(ge=0, description="Seguros e plano de saúde")
    f: float = Field(ge=0, description="Transporte, alimentação (horistas)")
    judicial: float = Field(ge=0, description="Despesas judiciais trabalhistas")

    @property
    def total(self) -> float:
        return round(self.a + self.b + self.c + self.d + self.e + self.f + self.judicial, 6)


class TabelaEncargos(BaseModel):
    """Encargos sociais para os dois regimes (ADR-023 §D2).

    Horistas: 177,70%  |  Mensalistas: 106,00%  (rfi_catalog.xlsm abril/2026)
    """

    model_config = ConfigDict(frozen=True)

    horistas: EncargosRegime
    mensalistas: EncargosRegime
    data_vigencia: date


DEFAULT_ENCARGOS = TabelaEncargos(
    horistas=EncargosRegime(
        a=0.3780,
        b=0.4784,
        c=0.4053,
        d=0.1907,
        e=0.1022,
        f=0.1924,
        judicial=0.0300,
    ),
    mensalistas=EncargosRegime(
        a=0.3780,
        b=0.0994,
        c=0.4030,
        d=0.0474,
        e=0.1022,
        f=0.0000,
        judicial=0.0300,
    ),
    data_vigencia=date(2026, 4, 1),
)


# ── D4 — Custo Indireto com BDI ───────────────────────────────────────────


class IndiretoComBdi(BaseModel):
    """Custo indireto com BDI-INDIRETO aplicado (ADR-023 §D4)."""

    model_config = ConfigDict(extra="ignore")

    categoria: Literal["TOP", "ADM", "LAB", "QSMS", "MOB"]
    custo_sem_bdi: float = Field(ge=0)
    bdi_aplicado: float = Field(ge=0, description="BDI-INDIRETO efetivo do projeto")
    custo_com_bdi: float = Field(ge=0)

    @model_validator(mode="after")
    def _check_custo_com_bdi(self) -> IndiretoComBdi:
        expected = round(self.custo_sem_bdi * (1 + self.bdi_aplicado), 2)
        if abs(self.custo_com_bdi - expected) > 0.02:
            raise ValueError(
                f"custo_com_bdi={self.custo_com_bdi} diverge do esperado {expected} "
                f"(sem_bdi={self.custo_sem_bdi}, bdi={self.bdi_aplicado})"
            )
        return self


# ── D3 — Decomposição de Custo de Equipamento ────────────────────────────


class DecomposicaoEquipamento(BaseModel):
    """Decomposição de custo de equipamento em sub-categorias para BDI correto (ADR-023 §D3).

    Permite aplicar o BDI correto por sub-componente:
      custo_mao_obra_h + custo_capital_h  -> BDI MAO_OBRA
      custo_diesel_h                      -> BDI DIESEL
      custo_material_h                    -> BDI MATERIAL

    Registrada em AtributosInsumo para enriquecer o catálogo.
    Usada por skill 06-precificacao-unitaria em vez da ponderação 70%/30%.
    """

    model_config = ConfigDict(frozen=True)

    equip_id: str
    custo_hora_total: float = Field(gt=0, description="Custo operacional total por hora (R$/h)")
    custo_mao_obra_h: float = Field(ge=0, description="Operador + manutenção -> BDI MAO_OBRA")
    custo_diesel_h: float = Field(ge=0, description="consumo_litros_hora × preco_diesel -> BDI DIESEL")
    custo_material_h: float = Field(ge=0, description="Lubrificantes, pneus, peças -> BDI MATERIAL")
    custo_capital_h: float = Field(ge=0, description="Depreciação + remuneração capital -> BDI MAO_OBRA")

    @model_validator(mode="after")
    def _check_components_sum(self) -> DecomposicaoEquipamento:
        total_comp = self.custo_mao_obra_h + self.custo_diesel_h + self.custo_material_h + self.custo_capital_h
        if abs(total_comp - self.custo_hora_total) > 0.01:
            raise ValueError(
                f"Soma dos componentes ({total_comp:.4f}) difere de "
                f"custo_hora_total ({self.custo_hora_total:.4f}) em mais de R$ 0.01."
            )
        return self

    @property
    def fracao_mao_obra(self) -> float:
        """Fração do custo total que vai para BDI MAO_OBRA (mão de obra + capital)."""
        return round((self.custo_mao_obra_h + self.custo_capital_h) / self.custo_hora_total, 6)

    @property
    def fracao_diesel(self) -> float:
        return round(self.custo_diesel_h / self.custo_hora_total, 6)

    @property
    def fracao_material(self) -> float:
        return round(self.custo_material_h / self.custo_hora_total, 6)


# ── D6/D7 — Perfil BDI por Projeto (snapshot versionado) ─────────────────


class CheckboxTributo(BaseModel):
    """Aplicabilidade + alíquota efetiva de um tributo para uma categoria BDI."""

    model_config = ConfigDict(frozen=True)

    aplicavel: bool
    aliquota: float = Field(ge=0, le=1, description="Ignorada se aplicavel=False")


class AplicacaoTributaria(BaseModel):
    """Incidência tributária para uma categoria de BDI (ADR-023 §D6)."""

    model_config = ConfigDict(frozen=True)

    iss: CheckboxTributo
    cofins: CheckboxTributo
    pis: CheckboxTributo
    cssl: CheckboxTributo
    ir: CheckboxTributo


class PerfilTributarioProjeto(BaseModel):
    """Configuração tributária por categoria BDI — confirmada via HiL na criação do projeto."""

    model_config = ConfigDict(frozen=True)

    regime: Literal["lucro_presumido", "simples_nacional", "lucro_real"]
    municipio: str
    iss_aliquota_municipal: float = Field(ge=0, le=0.05, description="ISS local; max legal 5%")

    mao_obra: AplicacaoTributaria
    material: AplicacaoTributaria
    servicos: AplicacaoTributaria
    indireto: AplicacaoTributaria
    diesel: AplicacaoTributaria

    observacoes: str | None = None


class PerfilLucroProjeto(BaseModel):
    """Margem de lucro por categoria BDI — negociável dentro dos pisos da construtora (ADR-023 §D7)."""

    model_config = ConfigDict(frozen=True)

    mao_obra: float = Field(ge=0, le=1)
    material: float = Field(ge=0, le=1)
    servicos: float = Field(ge=0, le=1)
    indireto: float = Field(ge=0, le=1)
    diesel: float = Field(ge=0, le=1)


class PerfilBdiProjeto(BaseModel):
    """Snapshot imutável do perfil BDI de um projeto (ADR-023 §D6, ADR-055 §D3).

    Coletado em `concilium project create`. Versionado por content_hash.
    Cada artefato gerado pelo pipeline registra `bdi_perfil_id` em ArtifactMeta.

    ADR-055: campo `regime_version` indica o regime tributário aplicável.
    Quando regime_version != PRE_REFORMA, o BDI efetivo é derivado via
    `resolver_bdi_cbs_ibs()` em vez de `resolver_componentes_bdi()`.
    """

    model_config = ConfigDict(frozen=True)

    perfil_id: str = Field(default_factory=lambda: str(uuid4()))
    projeto_id: str
    versao: int = Field(ge=1, default=1)
    content_hash: str  # SHA-256 do payload normalizado
    confirmado_em: datetime
    confirmado_por: str

    tributario: PerfilTributarioProjeto
    lucro: PerfilLucroProjeto

    # ADR-055 §D3: versão do regime tributário; default PRE_REFORMA = backward compat
    regime_version: TaxRegimeVersion = TaxRegimeVersion.PRE_REFORMA


class BdiPerfilDiff(BaseModel):
    """Diff entre duas versões do PerfilBdiProjeto (ADR-023 §D6).

    Emitido como artefato quando `concilium bdi-update` ou `update_tax_profile` altera o perfil.
    """

    model_config = ConfigDict(frozen=True)

    diff_id: str = Field(default_factory=lambda: str(uuid4()))
    projeto_id: str
    versao_anterior: int
    versao_nova: int
    perfil_anterior_id: str
    perfil_novo_id: str
    gerado_em: datetime = Field(default_factory=lambda: datetime.now(UTC))
    motivo: str
    campos_alterados: list[str]  # caminhos JSON dot-notation (ex: "tributario.mao_obra.iss.aliquota")
    resumo: str


# ── D7 — Resolver componentes efetivos ───────────────────────────────────


def resolver_componentes_bdi(
    base: TabelaBdi,
    perfil: PerfilBdiProjeto,
) -> TabelaBdi:
    """Aplica o PerfilBdiProjeto sobre a TabelaBdi de referência, retornando a tabela efetiva.

    Substitui alíquotas de tributos e lucro conforme o perfil do projeto.
    Campos ausentes (aplicavel=False) são zerados.
    """

    def _aplicar(comp: ComponentesBdi, aplic: AplicacaoTributaria, lucro: float) -> ComponentesBdi:
        return ComponentesBdi(
            ac=comp.ac,
            df=comp.df,
            r=comp.r,
            cr=comp.cr,
            l=lucro,
            cofins=aplic.cofins.aliquota if aplic.cofins.aplicavel else 0.0,
            iss=aplic.iss.aliquota if aplic.iss.aplicavel else 0.0,
            pis=aplic.pis.aliquota if aplic.pis.aplicavel else 0.0,
            cssl=aplic.cssl.aliquota if aplic.cssl.aplicavel else 0.0,
            ir=aplic.ir.aliquota if aplic.ir.aplicavel else 0.0,
        )

    trib = perfil.tributario
    lucro = perfil.lucro

    return TabelaBdi(
        mao_obra=_aplicar(base.mao_obra, trib.mao_obra, lucro.mao_obra),
        material=_aplicar(base.material, trib.material, lucro.material),
        servicos=_aplicar(base.servicos, trib.servicos, lucro.servicos),
        indireto=_aplicar(base.indireto, trib.indireto, lucro.indireto),
        diesel=_aplicar(base.diesel, trib.diesel, lucro.diesel),
        data_vigencia=base.data_vigencia,
    )


def resolver_bdi_cbs_ibs(
    base: TabelaBdi,
    scenario: TaxSimulationScenario,
) -> TabelaBdi:
    """ADR-055 §D2/D3: Deriva TabelaBdi com tributos CBS/IBS efetivos (líquidos após crédito).

    Para cada categoria de custo:
    - Mantém overhead (ac, r, cr, l) da tabela base
    - Substitui tributos por T_efetivo = CBS_IBS×(1-credit_ratio) + CSSL + IR
    - Acrescenta custo de carregamento do crédito ao componente df

    Compatibilidade: cofins armazena CBS+IBS líquido; iss=pis=0.
    O campo `cofins` passa a representar "tributos indiretos líquidos" neste regime.
    A fórmula TCU (numerador/denominador) continua válida.

    Para PRE_REFORMA, retorna a tabela base inalterada (noop).
    """
    if scenario.regime_version == TaxRegimeVersion.PRE_REFORMA:
        return base

    credit_ratios: dict[str, float] = {
        "mao_obra": scenario.credit_ratio_mao_obra,
        "material": scenario.credit_ratio_material,
        "servicos": scenario.credit_ratio_servicos,
        "diesel": scenario.credit_ratio_diesel,
        "indireto": scenario.credit_ratio_servicos,
    }

    def _substituir(comp: ComponentesBdi, categoria: str) -> ComponentesBdi:
        ratio = credit_ratios[categoria]
        cbs_ibs_liquido = round(scenario.cbs_ibs_combined_rate * (1.0 - ratio), 6)
        df_carregamento = scenario.custo_carregamento_df(ratio)
        return ComponentesBdi(
            ac=comp.ac,
            df=min(0.99, round(comp.df + df_carregamento, 6)),
            r=comp.r,
            cr=comp.cr,
            l=comp.l,
            # CBS+IBS líquido packed in cofins; iss/pis zeroed (substituídos)
            cofins=cbs_ibs_liquido,
            iss=0.0,
            pis=0.0,
            cssl=scenario.cssl_rate,
            ir=scenario.ir_rate,
        )

    return TabelaBdi(
        mao_obra=_substituir(base.mao_obra, "mao_obra"),
        material=_substituir(base.material, "material"),
        servicos=_substituir(base.servicos, "servicos"),
        indireto=_substituir(base.indireto, "indireto"),
        diesel=_substituir(base.diesel, "diesel"),
        data_vigencia=base.data_vigencia,
    )
