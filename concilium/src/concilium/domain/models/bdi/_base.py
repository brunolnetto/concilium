"""BDI base types: CategoriaBdi, tax regime version, simulation scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from concilium.domain.constants import (
    BDI_CSSL,
    BDI_IR,
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
