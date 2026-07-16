"""ADR-023 — Modelo BDI Diferenciado por Categoria de Custo (re-exports)."""

from ._base import (
    CENARIOS_TRIBUTARIOS,
    CategoriaBdi,
    TaxRegimeVersion,
    TaxSimulationScenario,
)
from ._components import (
    DEFAULT_BDI_TABELA,
    DEFAULT_ENCARGOS,
    ComponentesBdi,
    EncargosRegime,
    TabelaBdi,
    TabelaEncargos,
)
from ._profiles import (
    AplicacaoTributaria,
    BdiPerfilDiff,
    CheckboxTributo,
    DecomposicaoEquipamento,
    IndiretoComBdi,
    PerfilBdiProjeto,
    PerfilLucroProjeto,
    PerfilTributarioProjeto,
    resolve_bdi_tabela,
    resolver_bdi_cbs_ibs,
    resolver_bdi_jurisdicao,
    resolver_componentes_bdi,
)

__all__ = [
    "AplicacaoTributaria",
    "BdiPerfilDiff",
    "CENARIOS_TRIBUTARIOS",
    "CategoriaBdi",
    "CheckboxTributo",
    "ComponentesBdi",
    "DEFAULT_BDI_TABELA",
    "DEFAULT_ENCARGOS",
    "DecomposicaoEquipamento",
    "EncargosRegime",
    "IndiretoComBdi",
    "PerfilBdiProjeto",
    "PerfilLucroProjeto",
    "PerfilTributarioProjeto",
    "TabelaBdi",
    "TabelaEncargos",
    "TaxRegimeVersion",
    "TaxSimulationScenario",
    "resolver_bdi_cbs_ibs",
    "resolver_bdi_jurisdicao",
    "resolver_componentes_bdi",
]
