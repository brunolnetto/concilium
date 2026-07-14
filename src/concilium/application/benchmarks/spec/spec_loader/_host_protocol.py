"""Protocol descrevendo a superfície cruzada entre mixins de BenchmarkSpecLoader.

BenchmarkSpecLoader é composto por múltiplos mixins (_ResolveMixin, _InputsMixin,
_LoadDictMixin, _NormalizeMixin) que se chamam entre si via `self`. Cada mixin
isolado não enxerga os atributos/métodos dos outros — este Protocol existe só
para checagem de tipos (TYPE_CHECKING), permitindo que cada mixin declare
`self` com essa forma sem introduzir uma dependência real em tempo de execução.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from concilium.application.benchmarks.input_derivation import BenchmarkInputDeriver

from ._project_spec import ProjectSpec


class BenchmarkSpecLoaderHost(Protocol):
    """Superfície do BenchmarkSpecLoader composto, do ponto de vista de um mixin individual."""

    _config_root: Path
    _project_root: Path
    _input_deriver: BenchmarkInputDeriver

    def resolve_contexto(self, contexto_id: str, version: str | None = None) -> dict[str, Any] | None: ...
    def load_from_dict(self, ref: dict[str, Any], path: Path | str) -> ProjectSpec: ...
    def _normalize_reference_schema(self, ref: dict[str, Any]) -> dict[str, Any]: ...
    def _lfd_resolve_context(self, ref: dict[str, Any], contexto_id: str) -> tuple: ...
    def _lfd_build_bdi_section(self, extra_inputs: dict, ref: dict[str, Any], bdi_ref: dict) -> dict: ...
    def _lfd_build_ind_ref(self, ref: dict[str, Any], weeks: list) -> dict: ...
    def _lfd_resolve_projeto_nome(self, ref: dict[str, Any], projeto_block: dict, path: Path) -> str: ...
    @staticmethod
    def _lfd_resolve_contexto_id(ref: dict[str, Any], meta_block: dict) -> str: ...
    @staticmethod
    def _lfd_resolve_datas(ref: dict[str, Any], projeto_block: dict) -> tuple[str, str]: ...
    @staticmethod
    def _lfd_resolve_localizacao_regime(ref: dict[str, Any], projeto_block: dict) -> tuple[Any, dict]: ...
    @staticmethod
    def _lfd_build_inputs_escopo(
        projeto_nome: str, localizacao: Any, regime_trabalho: dict, data_ini: str, data_fim: str, eap: list, ref: dict
    ) -> dict: ...
    @staticmethod
    def _infer_slug_from_path(path: Path) -> str: ...
    @staticmethod
    def _extract_eap(ref: dict[str, Any]) -> list[dict[str, Any]]: ...
    @staticmethod
    def _extract_bdi_rates(ref: dict[str, Any]) -> dict[str, float]: ...
    def _enrich_eap_with_cpu_ids(
        self, eap: list[dict[str, Any]], contexto_id: str = "mendeslobo"
    ) -> list[dict[str, Any]]: ...
    @staticmethod
    def _build_inputs_indiretos(
        ind_ref: dict, weeks: list, referencia_indireto_total: Any, equipes_indiretas: list
    ) -> dict: ...
