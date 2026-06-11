"""BDI component models: ComponentesBdi, TabelaBdi, EncargosRegime, default tables."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from concilium.domain.constants import (
    BDI_CSSL,
    BDI_IR,
    BDI_ISS,
)

from ._base import CategoriaBdi


class ComponentesBdi(BaseModel):
    """Decomposição auditável de um BDI por categoria de custo (ADR-023 §D1).

    Fórmula TCU Acórdão 2622/2013 — numerador multiplicativo:
        BDI = [(1+AC) × (1+DF) × (1+R) × (1+CR) × (1+L)] / (1 - T) - 1
    onde T = cofins + iss + pis + cssl + ir.

    O numerador usa produto (não soma) dos fatores de overhead, conforme o
    Acórdão TCU e a planilha de referência. A forma aditiva (1+AC+DF+R+L)
    é uma simplificação que subestima o BDI em ~0,9 pp para os valores típicos
    de terraplenagem.
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
        """BDI calculado pela fórmula TCU multiplicativa. Retorna fração (ex: 0.2997 = 29,97%).

        Numerador: produto dos fatores — (1+AC)(1+DF)(1+R)(1+CR)(1+L)
        Denominador: 1 - T  (tributos sobre o preço de venda)
        """
        numerador = (1 + self.ac) * (1 + self.df) * (1 + self.r) * (1 + self.cr) * (1 + self.l)
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
    """Tabela de BDI para todos os tipos de custo de um projeto (ADR-023 §D1 / ADR-090).

    ADR-090: `diesel` é um alias de `material` (ambos = 4%, fornecimento de mercadoria).
    O campo `diesel` é mantido por retrocompatibilidade de serialização e para rastreamento
    diferenciado de crédito CBS/IBS em `TaxSimulationScenario` (ADR-055).
    """

    model_config = ConfigDict(frozen=True)

    mao_obra: ComponentesBdi
    material: ComponentesBdi
    servicos: ComponentesBdi
    indireto: ComponentesBdi
    # ADR-090: diesel = material (mesma taxa 4%); campo mantido por retrocompat + CBS/IBS
    diesel: ComponentesBdi
    data_vigencia: date

    def para_categoria(self, categoria: CategoriaBdi) -> ComponentesBdi:
        # ADR-090/107: DIESEL e COMBUSTIVEL delegam para material (mesma ComponentesBdi)
        if categoria in ("DIESEL", "COMBUSTIVEL"):
            return self.material
        return getattr(self, categoria.lower())


# Valores calibrados pela planilha AGIS / Ferrovia Nova Transnordestina (2026-03)
# e validados pelo benchmark AGIS (delta preco_venda < 0.1% vs referência).
#
# Tributos: obras de terraplenagem e infraestrutura ferroviária beneficiam-se de
# isenção de COFINS e PIS (regime cumulativo / desoneração). ISS incide sobre
# serviços de MO, serviços e indiretos; NÃO incide sobre fornecimento de material
# e diesel (tratados como venda de mercadoria).
#
# BDI efetivos (fórmula multiplicativa TCU Acórdão 2622/2013):
#   mao_obra  : (1+AC)(1+DF)(1+R)(1+L) / (1-T) - 1  →  BDI ≈ 29,97%
#   material  : (1+L)                                 →  BDI =  4,00%
#   servicos  : igual a mao_obra                      →  BDI ≈ 29,97%
#   indireto  : (1+AC)(1+DF)(1+R)(1+L) / (1-T) - 1  →  BDI ≈ 25,21%
#   diesel    : (1+L)                                 →  BDI =  4,00%
DEFAULT_BDI_TABELA = TabelaBdi(
    mao_obra=ComponentesBdi(
        # AC=5%, DF=1.5%, R=1%, L=9%  |  ISS=5%, CSSL=1.99%, IR=2.74% (COFINS/PIS isentos)
        ac=0.050,
        df=0.015,
        r=0.010,
        cr=0.000,
        l=0.090,
        cofins=0.000,  # isenção COFINS — obras de infraestrutura
        iss=BDI_ISS,  # 5,00%
        pis=0.000,  # isenção PIS — obras de infraestrutura
        cssl=BDI_CSSL,  # 1,99%
        ir=BDI_IR,  # 2,74%
    ),
    material=ComponentesBdi(
        # Fornecimento de material: apenas lucro, sem tributos sobre prestação de serviço
        ac=0.000,
        df=0.000,
        r=0.000,
        cr=0.000,
        l=0.040,  # L=4%
        cofins=0.000,
        iss=0.000,
        pis=0.000,
        cssl=0.000,
        ir=0.000,
    ),
    servicos=ComponentesBdi(
        # Serviços (equipamentos): mesmo tratamento da mão de obra
        ac=0.050,
        df=0.015,
        r=0.010,
        cr=0.000,
        l=0.090,
        cofins=0.000,
        iss=BDI_ISS,
        pis=0.000,
        cssl=BDI_CSSL,
        ir=BDI_IR,
    ),
    indireto=ComponentesBdi(
        # Custos indiretos: AC=5%, DF=1.5%, R=1%, L=5% (lucro menor que diretos)
        ac=0.050,
        df=0.015,
        r=0.010,
        cr=0.000,
        l=0.050,  # L=5% (planilha AGIS)
        cofins=0.000,
        iss=BDI_ISS,
        pis=0.000,
        cssl=BDI_CSSL,
        ir=BDI_IR,
    ),
    diesel=ComponentesBdi(
        # ADR-090: diesel = material (fornecimento de mercadoria consumida no campo).
        # BDI idêntico ao material (4%). Campo mantido por retrocompat + CBS/IBS credit_ratio.
        ac=0.000,
        df=0.000,
        r=0.000,
        cr=0.000,
        l=0.040,  # L=4% — idêntico ao material
        cofins=0.000,
        iss=0.000,
        pis=0.000,
        cssl=0.000,
        ir=0.000,
    ),
    data_vigencia=date(2026, 3, 1),  # calibrado em março/2026 via planilha AGIS
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
