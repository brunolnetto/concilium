"""BDI profile/resolver models: IndiretoComBdi, Decomposicao, Perfil*, resolver functions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._base import TaxRegimeVersion, TaxSimulationScenario
from ._components import ComponentesBdi, TabelaBdi


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
