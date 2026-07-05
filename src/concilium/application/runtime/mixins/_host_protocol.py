"""Protocol descrevendo a superfície cruzada entre mixins do Runtime.

Runtime (application/runtime/__init__.py) é composto por múltiplos mixins
(ConfigMixin, CatalogMixin, InputsMixin, ExecutionMixin) que se chamam entre
si via `self`. Cada mixin isolado não enxerga os métodos dos outros — este
Protocol existe só para checagem de tipos (TYPE_CHECKING), permitindo que
cada mixin declare `self` com essa forma sem introduzir uma dependência real
em tempo de execução.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from ..contracts import SkillExecutionContract


class RuntimeHost(Protocol):
    """Superfície do Runtime composto, do ponto de vista de um mixin individual."""

    config_root: Path
    _config_cache: dict[str, Any]

    def load_tema(self, tema_id: str | None = None) -> Any: ...
    def load_contexto(self, contexto_id: str) -> Any: ...
    def load_jurisdicao(self, codigo: str) -> dict[str, Any]: ...
    def load_perfil(self, perfil_id: str) -> dict[str, Any]: ...
    def load_calendario_operacional(
        self, jurisdicao_id: str | None = None, project_id: str | None = None
    ) -> dict[str, Any]: ...
    def load_catalogo(self, catalogo_id: str) -> dict[str, Any]: ...
    def _load_resolved_catalogo(
        self,
        catalogo_id: str,
        jurisdicao_id: str | None,
        project: Any,
        version: str | None = None,
    ) -> dict[str, Any]: ...
    def _apply_runtime_defaults(
        self, skill_id: str, project: Any, contexto: Any, inputs: dict[str, Any]
    ) -> dict[str, Any]: ...
    def _build_skill_kwargs(
        self,
        contract: Any,
        *,
        canonical_in: Any,
        inputs: dict[str, Any],
        catalogo: dict[str, Any],
        perfil: dict[str, Any],
        contexto: Any,
        project: Any,
        version: str,
    ) -> dict[str, Any]: ...
    def get_skill_contract(self, skill_id: str) -> SkillExecutionContract: ...
    def check_manifest_deps(self, skill_id: str, project: Any, version: str) -> list[str]: ...
    def create_snapshots(self, project: Any) -> dict[str, str]: ...
