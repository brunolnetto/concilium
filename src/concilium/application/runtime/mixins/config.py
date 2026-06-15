"""Mixin de configuração: carrega temas, contextos, jurisdições, perfis, referências e calendários."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..exceptions import RuntimeDomainError


class ConfigMixin:
    """Mixin com métodos de carregamento de configuração por arquivo JSON."""

    config_root: Path
    _config_cache: dict[str, Any]

    def __init__(self, config_root: Path | str) -> None:
        self.config_root = Path(config_root)
        self._config_cache: dict[str, Any] = {}

    def _load_json_config(self, folder: str, file_id: str, label: str) -> dict[str, Any]:
        path = self.config_root / folder / f"{file_id}.json"
        if not path.exists():
            raise RuntimeDomainError(f"{label} '{file_id}' não encontrado em {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def load_tema(self, tema_id: str | None = None):
        """Carrega TemaVisual pelo ID (ADR-065). None -> fallback 'default'."""
        from concilium.domain.models.catalog.tema import TEMA_DEFAULT, TemaVisual

        tid = tema_id or "default"
        key = f"tema:{tid}"
        if key in self._config_cache:
            return self._config_cache[key]  # type: ignore[return-value]

        path = self.config_root / "temas" / tid / "tema.json"
        if not path.exists():
            self._config_cache[key] = TEMA_DEFAULT
            return TEMA_DEFAULT

        try:
            tema = TemaVisual.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            tema = TEMA_DEFAULT
        self._config_cache[key] = tema
        return tema

    def load_contexto(self, contexto_id: str):
        from concilium.domain.models.catalog.contexto import ContextoObra

        key = f"ctx:{contexto_id}"
        if key not in self._config_cache:
            data = self._load_json_config("contextos", contexto_id, "Contexto")
            self._config_cache[key] = ContextoObra.model_validate(data)
        return self._config_cache[key]

    def load_jurisdicao(self, codigo: str) -> dict[str, Any]:
        data = self._load_json_config("jurisdicoes", codigo, "Jurisdição")
        parent_id = data.get("parent_id")
        if parent_id:
            parent_data = self.load_jurisdicao(parent_id)
            return self._deep_merge(parent_data, data)
        return data

    def _deep_merge(self, base: dict, overlay: dict) -> dict:
        result = dict(base)
        for key, value in overlay.items():
            if isinstance(value, dict) and key in result and isinstance(result[key], dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def load_perfil(self, perfil_id: str) -> dict[str, Any]:
        key = f"perfil:{perfil_id}"
        if key not in self._config_cache:
            self._config_cache[key] = self._load_json_config("perfis", perfil_id, "Perfil")
        return self._config_cache[key]

    def load_referencia(self, ref_id: str) -> dict[str, Any]:
        return self._load_json_config("referencias", ref_id, "Referência")

    def load_calendario_operacional(
        self, jurisdicao_id: str | None = None, project_id: str | None = None
    ) -> dict[str, Any]:
        """ADR-068: carrega calendário operacional com precedência Projeto > Jurisdição > Global."""
        key = f"cal:{jurisdicao_id or '-'}:{project_id or '-'}"
        if key in self._config_cache:
            return self._config_cache[key]

        cal_root = self.config_root / "calendarios"
        by_id: dict[str, dict[str, Any]] = {}

        def _load_optional(path: Path) -> list[dict[str, Any]]:
            if not path.exists():
                return []
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return []
            eventos = data.get("eventos", []) if isinstance(data, dict) else []
            return [e for e in eventos if isinstance(e, dict) and e.get("id")]

        for evt in _load_optional(cal_root / "global.json"):
            by_id[str(evt["id"])] = evt
        if jurisdicao_id:
            for evt in _load_optional(cal_root / "jurisdicao" / f"{jurisdicao_id}.json"):
                by_id[str(evt["id"])] = evt
        if project_id:
            for evt in _load_optional(cal_root / "projeto" / f"{project_id}.json"):
                by_id[str(evt["id"])] = evt

        merged: dict[str, Any] = {"versao": "1", "eventos": list(by_id.values())}
        self._config_cache[key] = merged
        return merged
