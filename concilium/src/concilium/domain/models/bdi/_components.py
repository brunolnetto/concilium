"""BDI component models: ComponentesBdi, TabelaBdi, EncargosRegime, default tables."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from concilium.domain.constants import (
    BDI_COFINS,
    BDI_CSSL,
    BDI_IR,
    BDI_ISS,
    BDI_PIS,
    BDI_TRIBUTOS_MATERIAL,
)

from ._base import CategoriaBdi


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
