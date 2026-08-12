"""Modelos Pydantic v2 para todas as camadas do Concilium.

Lazy-loaded via __getattr__ so that importing any single model does not
trigger a full cascade of all submodule imports at startup.

ADR-029 Fase 2: arquivos movidos de concilium.models -> concilium.domain.models.
O pacote concilium.models mantém uma camada temporária de retrocompatibilidade.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # static analysis & IDEs only — never runs at startup
    from concilium.domain.models.canonical import (
        CanonicalModel,
        Cronograma,
        DistribuicaoMensal,
        DistribuicaoSemanal,
        Eap,
        EapItem,
        EquipeDireta,
        Indireto,
        Meta,
        Planejamento,
        PontoEquilibrio,
        Praticabilidade,
        Projeto,
        Resultado,
        StatusValidacao,
        ValidacaoItem,
    )
    from concilium.domain.models.catalog.catalogo import CPU, Insumo, TemplateObra, TipoInsumo
    from concilium.domain.models.catalog.contexto import ContextoObra
    from concilium.domain.models.catalog.jurisdicao import Jurisdicao
    from concilium.domain.models.catalog.referencia import TabelaReferencia
    from concilium.domain.models.project.constraint_violation import ConstraintViolation
    from concilium.domain.models.project.decision_variables import DecisionVariables
    from concilium.domain.models.project.perfil import PerfilConstrutora

# name -> (module_path, attribute)
_LAZY_MAP: dict[str, tuple[str, str]] = {
    # canonical
    "CanonicalModel": ("concilium.domain.models.canonical", "CanonicalModel"),
    "Cronograma": ("concilium.domain.models.canonical", "Cronograma"),
    "DistribuicaoMensal": ("concilium.domain.models.canonical", "DistribuicaoMensal"),
    "DistribuicaoSemanal": ("concilium.domain.models.canonical", "DistribuicaoSemanal"),
    "Eap": ("concilium.domain.models.canonical", "Eap"),
    "EapItem": ("concilium.domain.models.canonical", "EapItem"),
    "EquipeDireta": ("concilium.domain.models.canonical", "EquipeDireta"),
    "Indireto": ("concilium.domain.models.canonical", "Indireto"),
    "Meta": ("concilium.domain.models.canonical", "Meta"),
    "Planejamento": ("concilium.domain.models.canonical", "Planejamento"),
    "PontoEquilibrio": ("concilium.domain.models.canonical", "PontoEquilibrio"),
    "Praticabilidade": ("concilium.domain.models.canonical", "Praticabilidade"),
    "Projeto": ("concilium.domain.models.canonical", "Projeto"),
    "Resultado": ("concilium.domain.models.canonical", "Resultado"),
    "StatusValidacao": ("concilium.domain.models.canonical", "StatusValidacao"),
    "ValidacaoItem": ("concilium.domain.models.canonical", "ValidacaoItem"),
    # catalogo
    "CPU": ("concilium.domain.models.catalog.catalogo", "CPU"),
    "Insumo": ("concilium.domain.models.catalog.catalogo", "Insumo"),
    "TemplateObra": ("concilium.domain.models.catalog.catalogo", "TemplateObra"),
    "TipoInsumo": ("concilium.domain.models.catalog.catalogo", "TipoInsumo"),
    # contexto
    "ContextoObra": ("concilium.domain.models.catalog.contexto", "ContextoObra"),
    # jurisdicao
    "Jurisdicao": ("concilium.domain.models.catalog.jurisdicao", "Jurisdicao"),
    # perfil
    "PerfilConstrutora": ("concilium.domain.models.project.perfil", "PerfilConstrutora"),
    # referencia
    "TabelaReferencia": ("concilium.domain.models.catalog.referencia", "TabelaReferencia"),
    # outros
    "DecisionVariables": ("concilium.domain.models.project.decision_variables", "DecisionVariables"),
    "ConstraintViolation": ("concilium.domain.models.project.constraint_violation", "ConstraintViolation"),
    # ADR-054: workforce mobilization policy
    "WorkforcePolicy": ("concilium.domain.models.planning.mobilizacao", "WorkforcePolicy"),
    "CurvaForca": ("concilium.domain.models.planning.mobilizacao", "CurvaForca"),
    "CurvaForcaSemanal": ("concilium.domain.models.planning.mobilizacao", "CurvaForcaSemanal"),
}

__all__ = list(_LAZY_MAP)


def __getattr__(name: str):  # noqa: N807
    """Resolve attribute lazily on first access; cache in module globals."""
    if name in _LAZY_MAP:
        module_path, attr = _LAZY_MAP[name]
        mod = importlib.import_module(module_path)
        val = getattr(mod, attr)
        # Cache so subsequent accesses are O(1) dict lookups, not importlib calls
        globals()[name] = val
        return val
    raise AttributeError(f"module 'concilium.domain.models' has no attribute {name!r}")
