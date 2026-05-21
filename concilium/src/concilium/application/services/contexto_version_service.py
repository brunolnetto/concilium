"""ADR-062: Serviço genérico de versionamento de entidades de configuração.

Suporta contextos (`config/contextos/`) e perfis (`config/perfis/`) com a mesma
lógica de versionamento:

    config/<entity>/<id>/versions/vN.json   ← conteúdo versionado
    config/<entity>/<id>/current            ← ponteiro para versão ativa
    config/<entity>/<id>/<entity>.json      ← metadados da entidade

Backward compat: se a estrutura versionada não existir, lê o arquivo estático
legado config/<entity>/<id>.json e retorna como v1 implícito.

Aliases de conveniência:
    ContextoVersionService  = ConfigVersionService("contextos")
    PerfilVersionService    = ConfigVersionService("perfis")
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class ConfigVersionService:
    """Serviço genérico de versionamento para qualquer entidade em config/<subdir>/."""

    def __init__(self, config_root: Path, subdir: str) -> None:
        self._root = Path(config_root) / subdir
        self._subdir = subdir

    # ── Resolução ────────────────────────────────────────────────────────────

    def resolve(self, entity_id: str, version: str | None = None) -> dict[str, Any] | None:
        """Retorna o dict da entidade para a versão especificada (ou versão ativa se None)."""
        versioned_dir = self._root / entity_id / "versions"
        current_file = self._root / entity_id / "current"

        if versioned_dir.exists():
            v = version or self._read_current(current_file)
            v_file = versioned_dir / f"{v}.json"
            if v_file.exists():
                return json.loads(v_file.read_text(encoding="utf-8"))
            available = sorted(versioned_dir.glob("v*.json"))
            if available:
                return json.loads(available[-1].read_text(encoding="utf-8"))

        return None

    def current_version(self, entity_id: str) -> str:
        return self._read_current(self._root / entity_id / "current")

    # ── Listagem ─────────────────────────────────────────────────────────────

    def list_entities(self) -> list[dict[str, Any]]:
        """Lista todas as entidades disponíveis com histórico de versões."""
        result: list[dict[str, Any]] = []

        for entity_dir in sorted(self._root.iterdir()):
            if not entity_dir.is_dir():
                continue
            # Find metadata file: <entity>.json or contexto.json or perfil.json
            meta = self._read_meta(entity_dir)
            versions = self._list_versions(entity_dir)
            current = self._read_current(entity_dir / "current")
            result.append(
                {
                    "id": meta.get("id") or entity_dir.name,
                    "nome": meta.get("nome") or entity_dir.name,
                    "descricao": meta.get("descricao") or "",
                    "current_version": current,
                    "versions": versions,
                    **{
                        k: meta[k]
                        for k in meta
                        if k not in ("id", "nome", "descricao", "current_version") and not k.startswith("$")
                    },
                }
            )

        return result

    def list_versions(self, entity_id: str) -> list[dict[str, Any]]:
        entity_dir = self._root / entity_id
        if not entity_dir.is_dir():
            return [{"version": "v1", "motivo": "legado"}]
        return self._list_versions(entity_dir)

    # ── Criação de nova versão ───────────────────────────────────────────────

    def create_version(
        self,
        entity_id: str,
        fields: dict[str, Any],
        motivo: str,
        author: str = "system",
        make_current: bool = True,
    ) -> dict[str, Any]:
        entity_dir = self._root / entity_id
        versions_dir = entity_dir / "versions"
        versions_dir.mkdir(parents=True, exist_ok=True)

        existing = sorted(versions_dir.glob("v*.json"))
        last_n = 0
        for f in existing:
            try:
                last_n = max(last_n, int(f.stem[1:]))
            except ValueError:
                pass
        new_v = f"v{last_n + 1}"

        base: dict[str, Any] = {}
        if existing:
            base = json.loads(existing[-1].read_text(encoding="utf-8"))
            for k in ("version", "created_at", "created_by", "motivo"):
                base.pop(k, None)

        new_entry = {
            "version": new_v,
            "created_at": datetime.now(UTC).isoformat(),
            "created_by": author,
            "motivo": motivo,
            **base,
            **fields,
        }
        (versions_dir / f"{new_v}.json").write_text(
            json.dumps(new_entry, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        if make_current:
            (entity_dir / "current").write_text(new_v, encoding="utf-8")
            meta_file = self._find_meta_file(entity_dir)
            if meta_file and meta_file.exists():
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                meta["current_version"] = new_v
                meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        return new_entry

    # ── Comparação ───────────────────────────────────────────────────────────

    def compare(self, entity_id: str, version_a: str, version_b: str) -> dict[str, Any]:
        a = self.resolve(entity_id, version_a) or {}
        b = self.resolve(entity_id, version_b) or {}

        _skip = {"version", "created_at", "created_by", "motivo", "$comment"}
        all_keys = (set(a) | set(b)) - _skip
        diff: dict[str, Any] = {}
        for k in sorted(all_keys):
            va, vb = a.get(k), b.get(k)
            if va != vb:
                diff[k] = {"de": va, "para": vb}

        return {
            "entity_id": entity_id,
            "subdir": self._subdir,
            "version_a": version_a,
            "version_b": version_b,
            "changed": diff,
            "unchanged": sorted(all_keys - set(diff)),
        }

    # ── Internos ─────────────────────────────────────────────────────────────

    @staticmethod
    def _read_current(current_file: Path) -> str:
        if current_file.exists():
            return current_file.read_text(encoding="utf-8").strip() or "v1"
        return "v1"

    def _read_meta(self, entity_dir: Path) -> dict[str, Any]:
        meta_file = self._find_meta_file(entity_dir)
        if meta_file and meta_file.exists():
            try:
                return json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"id": entity_dir.name}

    def _find_meta_file(self, entity_dir: Path) -> Path | None:
        """Procura arquivo de metadados: contexto.json, perfil.json ou <subdir_singular>.json."""
        for candidate in [
            entity_dir / f"{self._subdir[:-1]}.json",  # contextos→contexto, perfis→perfil
            entity_dir / "contexto.json",
            entity_dir / "perfil.json",
            entity_dir / "meta.json",
        ]:
            if candidate.exists():
                return candidate
        return None

    @staticmethod
    def _list_versions(entity_dir: Path) -> list[dict[str, Any]]:
        versions_dir = entity_dir / "versions"
        if not versions_dir.exists():
            return []
        result = []
        for vf in sorted(versions_dir.glob("v*.json")):
            try:
                data = json.loads(vf.read_text(encoding="utf-8"))
                entry: dict[str, Any] = {
                    "version": data.get("version") or vf.stem,
                    "created_at": data.get("created_at"),
                    "created_by": data.get("created_by"),
                    "motivo": data.get("motivo", ""),
                }
                # Include config-specific fields
                for k in ("catalogo_id", "jurisdicao_id", "perfil_id", "nome"):
                    if k in data:
                        entry[k] = data[k]
                result.append(entry)
            except Exception:
                pass
        return result


# ── Aliases de conveniência ──────────────────────────────────────────────────


class ContextoVersionService(ConfigVersionService):
    """Versiona entidades em config/contextos/."""

    def __init__(self, config_root: Path) -> None:
        super().__init__(config_root, "contextos")

    # Alias methods para backward compat
    def list_contexts(self) -> list[dict[str, Any]]:
        return self.list_entities()


class PerfilVersionService(ConfigVersionService):
    """Versiona entidades em config/perfis/."""

    def __init__(self, config_root: Path) -> None:
        super().__init__(config_root, "perfis")

    def list_perfis(self) -> list[dict[str, Any]]:
        return self.list_entities()


class TemaVersionService(ConfigVersionService):
    """Versiona entidades em config/temas/ (ADR-065)."""

    def __init__(self, config_root: Path) -> None:
        super().__init__(config_root, "temas")

    def list_temas(self) -> list[dict[str, Any]]:
        return self.list_entities()


class JurisdictionVersionService(ConfigVersionService):
    """Versiona overlays de jurisdição em config/jurisdicoes/ (ADR-066)."""

    def __init__(self, config_root: Path) -> None:
        super().__init__(config_root, "jurisdicoes")

    def list_jurisdicoes(self) -> list[dict[str, Any]]:
        return self.list_entities()
