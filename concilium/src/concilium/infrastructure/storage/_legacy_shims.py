"""Shims de retrocompatibilidade ADR-031 §D9. Extraído de escopo_store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from concilium.domain.models.canonical import CanonicalModel
from concilium.domain.models.escopo import StatusPlano

from .escopo_store import EscopoStore, PlanoStore

# ── Shim de retrocompatibilidade (ADR-031 §D9) ──────────────────────────────


class _LegacyPlanoShim(PlanoStore):
    """Adapta uma versão legada (vN/) para a interface PlanoStore.

    Não move arquivos — apenas abstrai a estrutura antiga.
    Somente-leitura para o novo modelo: não é possível criar escopos/planos
    com a estrutura legada (operações de escrita requerem migração explícita).
    """

    def __init__(self, project_store: Any, version: str, escopo_shim: _LegacyEscopoShim | None = None) -> None:
        self._project_store = project_store
        self._version = version
        # root aponta para vN/ dentro do projeto
        super().__init__(project_store.root / version, escopo_store=escopo_shim)

    @property
    def plano_id(self) -> str:  # type: ignore[override]
        return self._version

    @property
    def meta(self) -> dict[str, Any]:
        return {
            "plano_id": self._version,
            "escopo_id": "default",
            "projeto_id": self._project_store.meta.get("id", ""),
            "nome": f"Versão legada {self._version}",
            "status": self._legacy_status(),
            "versao_iteracao": int(self._version[1:]) if self._version[1:].isdigit() else 1,
        }

    def _legacy_status(self) -> StatusPlano:
        approved = self._project_store.meta.get("approved_versions", [])
        if self._version in approved:
            return "APROVADO"
        return "RASCUNHO"

    def load_canonical(self) -> CanonicalModel | None:
        return self._project_store.load_canonical(self._version)

    def save_canonical(self, model: CanonicalModel, **_: Any) -> None:  # type: ignore[override]
        self._project_store.save_canonical(model, self._version)

    def write_canonical_raw(self, content: dict) -> None:
        self._project_store.write_canonical_raw(content, self._version)

    def log_invocation(self, entry: dict) -> None:
        self._project_store.log_invocation(self._version, entry)

    def read_invocations(self) -> list[dict]:
        log_path = self.root / self._project_store.INVOCATIONS_LOG
        if not log_path.exists():
            return []
        out: list[dict] = []
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return out

    def approve(self) -> None:
        self._project_store.approve(self._version)

    def archive(self) -> None:
        pass  # Legado não tem semântica de archival — no-op

    def save_output_file(self, data: bytes, filename: str = "resultado.xlsx") -> Path:
        return self._project_store.save_output_file(data, self._version, filename)

    def load_output_file(self, filename: str = "resultado.xlsx") -> bytes | None:
        return self._project_store.load_output_file(self._version, filename)

    def list_output_files(self) -> list[str]:
        return self._project_store.list_output_files(self._version)


class _LegacyEscopoShim(EscopoStore):
    """Adapta estrutura vN/ de um ProjectStore como se fosse EscopoStore 'default'.

    Expõe as versões legadas (v1, v2, ...) como planos do escopo 'default'.
    Somente-leitura para novas operações de escopo/plano.
    """

    def __init__(self, project_store: Any) -> None:
        self._project_store = project_store
        super().__init__(project_store.root)

    @property
    def escopo_id(self) -> str:  # type: ignore[override]
        return "default"

    @property
    def meta(self) -> dict[str, Any]:
        pm = self._project_store.meta
        return {
            "escopo_id": "default",
            "projeto_id": pm.get("id", ""),
            "nome": pm.get("nome", "Escopo padrão"),
            "status": "RASCUNHO",
        }

    def update_meta(self, **_: Any) -> None:
        pass  # Legado — no-op

    def list_plans(self) -> list[str]:
        return self._project_store.list_versions()

    def plan(self, plano_id: str) -> _LegacyPlanoShim:  # type: ignore[override]
        return _LegacyPlanoShim(self._project_store, plano_id, escopo_shim=self)

    def create_plan(self, nome: str, **_: Any) -> _LegacyPlanoShim:  # type: ignore[override]
        """Em projetos legados, cria nova versão usando a interface existente."""
        v = self._project_store.new_version()
        return _LegacyPlanoShim(self._project_store, v, escopo_shim=self)

    def approved_plan(self) -> _LegacyPlanoShim | None:  # type: ignore[override]
        cv = self._project_store.current_version()
        if cv is None:
            return None
        approved = self._project_store.meta.get("approved_versions", [])
        if cv in approved:
            return _LegacyPlanoShim(self._project_store, cv)
        return None

    def active_plan(self) -> _LegacyPlanoShim | None:  # type: ignore[override]
        cv = self._project_store.current_version()
        if cv is None:
            return None
        return _LegacyPlanoShim(self._project_store, cv, escopo_shim=self)

    def approve_plan(self, plano_id: str) -> list[str]:
        self._project_store.approve(plano_id)
        return []
