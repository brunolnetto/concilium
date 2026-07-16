"""Camada 0 — Jurisdição."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProvedorReferencia(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str
    nome: str
    mantenedor: str
    cadencia_atualizacao: Literal["mensal", "trimestral", "anual", "irregular"]
    uso_tipico: str


class FonteClimatica(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provedor: str
    url_base: str | None = None
    metodo_consulta: str
    granularidade: Literal["diaria", "mensal", "horaria"] = "mensal"


class ComponenteEncargo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str
    percentual: float = Field(ge=0, le=2)


class MotorEncargosSociais(BaseModel):
    """Motor de encargos sociais por jurisdição (ADR-097 §D1/D2/D4).

    percentual_horista  → aplica-se a horistas CLT de campo/obra (default: ENCARGOS_CLT).
    percentual_mensalista → aplica-se a mensalistas (gestão/admin) (default: ENCARGOS_MENSALISTA).
    percentual_pj       → aplica-se a prestadores PJ (default: ENCARGOS_PJ).
    percentual_total    → mantido para retrocompatibilidade; usado quando os campos
                          específicos não estão preenchidos.
    componentes         → detalhamento auditável por Grupo A–F+Judicial.
    tax_regime          → regime tributário da empresa (afeta Grupo A — INSS patronal).
    """

    model_config = ConfigDict(extra="forbid")

    versao: str
    percentual_total: float = Field(ge=0, le=2)
    percentual_horista: float | None = Field(default=None, ge=0, le=2)
    percentual_mensalista: float | None = Field(default=None, ge=0, le=2)
    percentual_pj: float | None = Field(default=None, ge=0, le=1)
    tax_regime: str | None = None  # TaxRegime string; None = LUCRO_PRESUMIDO
    componentes: list[ComponenteEncargo] = Field(default_factory=list)


class AliquotasBdi(BaseModel):
    """Alíquotas tributárias usadas no cálculo do BDI por jurisdição (ADR-038 §D3)."""

    model_config = ConfigDict(extra="ignore")  # ignora $comment nos JSONs

    ISS: float = Field(ge=0, le=0.20, description="ISS — varia por município (2% a 5%)")
    PIS: float = Field(ge=0, le=0.10, description="PIS — regime tributário")
    COFINS: float = Field(ge=0, le=0.10, description="COFINS — regime tributário")
    CPRB: float = Field(ge=0, le=0.10, description="CPRB — desoneração da folha (setorial)")


class MotorTributarioBdi(BaseModel):
    """Motor de tributação para composição do BDI por jurisdição (ADR-038 §D3)."""

    model_config = ConfigDict(extra="ignore")  # ignora $comment nos JSONs

    versao: str = Field(description="Ex.: '2024.1'")
    aliquotas: AliquotasBdi

    @property
    def total(self) -> float:
        """Soma de todas as alíquotas (fator tributário total)."""
        a = self.aliquotas
        return round(a.ISS + a.PIS + a.COFINS + a.CPRB, 6)


class Jurisdicao(BaseModel):
    """Camada 0 — contexto regulatório e geográfico."""

    model_config = ConfigDict(extra="ignore")  # ignora $comment, $schema, parent_id

    # Aceita "BR" e "BR-UF" (ex.: "BR-CE", "BR-SP") — o formato realmente usado em
    # config/jurisdicoes/*.json. O pattern anterior (^[A-Z]{2,5}$) rejeitava qualquer
    # código com hífen, incompatível com todos os 27 arquivos de UF já existentes.
    codigo: str = Field(pattern=r"^[A-Z]{2}(-[A-Z]{2})?$")
    nome: str
    moeda: str = Field(pattern=r"^[A-Z]{3}$")
    regime_trabalhista: Literal["CLT", "OUTRO"]
    provedores_referencia: list[ProvedorReferencia] = Field(min_length=1)
    fonte_climatica: FonteClimatica
    motor_encargos_sociais: MotorEncargosSociais
    # ADR-038 §D3: tributação BDI regional — None se jurisdição não tem override
    motor_tributario_bdi: MotorTributarioBdi | None = None
