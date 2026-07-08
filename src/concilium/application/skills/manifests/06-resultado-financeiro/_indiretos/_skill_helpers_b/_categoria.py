"""Skill 05 — Indiretos (ADR-009, ADR-023 §D4).

Normalização de categoria e construção a partir de dict (composição, MO, encargos).
"""

from __future__ import annotations

from typing import Any, Literal

from concilium.domain.constants import SEMANAS_POR_MES as _SEMANAS_POR_MES  # ADR-056 §T3
from concilium.domain.models.canonical import IndirectoCategoria
from concilium.infrastructure.repositories.insumo import RepositorioInsumo

try:
    # Hyphenated manifest dir: only loaded at runtime via a synthetic package
    # (see concilium/application/skills/__init__.py); ty cannot resolve this
    # statically.
    from .._skill_helpers_a import (  # ty: ignore[unresolved-import]
        _bcfd_enrich_mo_itens,
        _parse_component,
    )
except ImportError:
    import importlib.util
    from pathlib import Path

    _here = Path(__file__).resolve().parent.parent
    _path_a = _here / "_skill_helpers_a.py"
    _spec_a = importlib.util.spec_from_file_location("skill07_helpers_a_for_b_categoria", _path_a)
    if _spec_a is None or _spec_a.loader is None:
        raise ImportError(f"Não foi possível carregar spec para: {_path_a}") from None
    _mod_a = importlib.util.module_from_spec(_spec_a)
    _spec_a.loader.exec_module(_mod_a)
    _bcfd_enrich_mo_itens = _mod_a._bcfd_enrich_mo_itens
    _parse_component = _mod_a._parse_component


def _as_categoria_indireto(codigo: str) -> Literal["ADM", "TOP", "LAB", "QSMS", "MOB"]:
    """Valida e estreita ``codigo`` (str vindo de config/perfil) para o Literal do domínio.

    ``codigo`` chega como ``str`` porque é lido de dicts de configuração
    (``perfil["categorias_indireto"]``, ``categorias_config``) sem tipagem estática.
    Falha explicitamente para categorias desconhecidas em vez de deixar o
    pydantic rejeitar silenciosamente mais adiante na construção do modelo.
    """
    if codigo == "ADM":
        return "ADM"
    if codigo == "TOP":
        return "TOP"
    if codigo == "LAB":
        return "LAB"
    if codigo == "QSMS":
        return "QSMS"
    if codigo == "MOB":
        return "MOB"
    raise ValueError(f"Categoria de indireto desconhecida: {codigo!r}")


def _build_categoria_from_dict(
    codigo: str,
    comp_dict: dict,
    n_semanas: int,
    repo: RepositorioInsumo | None = None,
    data_base=None,
    overrides: dict[str, Any] | None = None,
    jurisdicao_id: str | None = None,
) -> IndirectoCategoria:
    """Constrói IndirectoCategoria a partir de dict de composição (ADR-009 driver=permanencia)."""
    _bcfd_enrich_mo_itens(comp_dict, repo, jurisdicao_id, overrides, data_base)
    mo = _parse_component(comp_dict.get("mao_de_obra"))
    eq = _parse_component(comp_dict.get("equipamentos"))
    vb = _parse_component(comp_dict.get("verbas"))
    custo_mensal = (
        (mo.custo_fixo_mensal if mo else 0.0)
        + (eq.custo_fixo_mensal if eq else 0.0)
        + (vb.custo_fixo_mensal if vb else 0.0)
    )
    custo_total = round(custo_mensal * (n_semanas / _SEMANAS_POR_MES), 2)
    return IndirectoCategoria(
        categoria=_as_categoria_indireto(codigo),
        driver="permanencia",
        mao_de_obra=mo,
        equipamentos=eq,
        verbas=vb,
        custo_fixo_mensal=custo_mensal,
        custo_fixo_total=custo_total,
    )


