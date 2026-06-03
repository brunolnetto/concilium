"""ADR-029 Fase 1 — shim: concilium.domain.repositories.

Re-exporta as implementações concretas do pacote original (concilium.repositories)
e expõe os port interfaces (ABCs) definidos neste pacote.

Port interfaces (ABCs):
    RepositorioInsumoPort  — contrato de acesso a insumos
    ArtifactStorePort      — contrato de persistência de artefatos

Implementações concretas (shims -> concilium.repositories):
    RepositorioInsumo      — implementação filesystem/dict do port de insumos
    RepositorioProducao    — repositório de dados de produção
"""

import importlib
import sys

from concilium.domain.repositories.artifact_port import ArtifactStorePort
from concilium.domain.repositories.insumo_port import RepositorioInsumoPort

_ORIG_PKG = "concilium.infrastructure.repositories"
_THIS_PKG = "concilium.domain.repositories"

_SUBMODULES = ["insumo", "producao"]

for _s in _SUBMODULES:
    _alias = f"{_THIS_PKG}.{_s}"
    if _alias not in sys.modules:
        try:
            sys.modules[_alias] = importlib.import_module(f"{_ORIG_PKG}.{_s}")
        except ImportError:
            pass

_orig = importlib.import_module(_ORIG_PKG)

__all__: list[str] = [
    "RepositorioInsumoPort",
    "ArtifactStorePort",
    *getattr(_orig, "__all__", []),
]


def __getattr__(name: str):  # noqa: N807
    """Delega nomes não declarados localmente ao pacote original."""
    if name in ("RepositorioInsumoPort", "ArtifactStorePort"):
        raise AttributeError(name)  # already imported above
    return getattr(_orig, name)
