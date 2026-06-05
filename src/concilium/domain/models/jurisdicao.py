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
    model_config = ConfigDict(extra="forbid")

    versao: str
    percentual_total: float = Field(ge=0, le=2)
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

    codigo: str = Field(pattern=r"^[A-Z]{2,5}$")
    nome: str
    moeda: str = Field(pattern=r"^[A-Z]{3}$")
    regime_trabalhista: Literal["CLT", "OUTRO"]
    provedores_referencia: list[ProvedorReferencia] = Field(min_length=1)
    fonte_climatica: FonteClimatica
    motor_encargos_sociais: MotorEncargosSociais
    # ADR-038 §D3: tributação BDI regional — None se jurisdição não tem override
    motor_tributario_bdi: MotorTributarioBdi | None = None
