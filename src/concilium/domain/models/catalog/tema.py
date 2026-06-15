"""ADR-065: TemaVisual — entidade de primeira classe para identidade visual.

Separada de ContextoObra (que responde "qual catálogo/jurisdição") e de
PerfilBdi (que responde "quais parâmetros financeiros").

Validações de domínio:
- Cores: hex de 6 dígitos sem '#' (regex ^[0-9A-Fa-f]{6}$)
- Fontes: Literal — conjunto restrito suportado por openpyxl e fpdf2
- Tamanhos: Field(ge=N, le=M) — bounds explícitos por nível tipográfico
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_HEX_RE = re.compile(r"^[0-9A-Fa-f]{6}$")

FonteSuportada = Literal["Arial", "Helvetica", "Calibri", "Times New Roman", "Courier"]

FONTES_SUPORTADAS: list[str] = ["Arial", "Helvetica", "Calibri", "Times New Roman", "Courier"]


class CoresTema(BaseModel):
    """Paleta cromática — hex de 6 dígitos sem '#' (ex: '1F4E78')."""

    model_config = ConfigDict(extra="ignore")

    cabecalho_fundo: str = "1F4E78"
    cabecalho_texto: str = "FFFFFF"
    zebra_par: str = "FFFFFF"
    zebra_impar: str = "F2F2F2"
    borda: str = "D9D9D9"
    destaque: str = "FFC000"

    @field_validator(
        "cabecalho_fundo", "cabecalho_texto", "zebra_par", "zebra_impar", "borda", "destaque", mode="before"
    )
    @classmethod
    def validate_hex(cls, v: object) -> str:
        s = str(v).lstrip("#")  # aceita com ou sem '#' na entrada, normaliza sem
        if not _HEX_RE.match(s):
            raise ValueError(f"Cor inválida '{v}' — esperado hex de 6 dígitos (ex: '1F4E78')")
        return s.upper()


class FontesTema(BaseModel):
    """Tipografia — fontes do conjunto suportado, tamanhos com bounds explícitos."""

    model_config = ConfigDict(extra="ignore")

    cabecalho: FonteSuportada = "Arial"
    corpo: FonteSuportada = "Calibri"
    tamanho_titulo: int = Field(default=14, ge=10, le=24)
    tamanho_cabecalho: int = Field(default=11, ge=8, le=16)
    tamanho_corpo: int = Field(default=10, ge=8, le=14)


class TemaVisual(BaseModel):
    """Identidade visual de uma empresa/cliente (ADR-065).

    Armazenado em config/temas/{id}/tema.json.
    Referenciado por ContextoObra.tema_id.
    Injetado pelo Runtime como catalogo["identidade_visual"] para backward-compat.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    empresa: str = "Concilium"
    perfil_exibicao: Literal["EXECUTIVO", "SIMPLES", "TECNICO"] = "EXECUTIVO"
    cores: CoresTema = Field(default_factory=CoresTema)
    fontes: FontesTema = Field(default_factory=FontesTema)

    def to_catalogo_dict(self) -> dict:
        """Serializa no formato legado esperado pelos exportadores (backward-compat)."""
        return {
            "empresa": self.empresa,
            "perfil": self.perfil_exibicao,
            "cores": self.cores.model_dump(),
            "fontes": self.fontes.model_dump(),
        }


# Tema neutro usado como fallback quando nenhum tema_id está configurado
TEMA_DEFAULT = TemaVisual(
    id="default",
    empresa="Concilium",
    perfil_exibicao="SIMPLES",
)
