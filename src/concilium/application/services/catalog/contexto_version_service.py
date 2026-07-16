"""ADR-062: Serviço genérico de versionamento de entidades de configuração.

Suporta contextos (`config/contextos/`) e perfis (`config/perfis/`) com a mesma
lógica de versionamento:

    config/<entity>/<id>/versions/vN.json   ← conteúdo versionado
    config/<entity>/<id>/current            ← ponteiro para versão ativa
    config/<entity>/<id>/<entity>.json      ← metadados da entidade

Se a estrutura versionada não existir, lê o arquivo estático
config/<entity>/<id>.json e retorna como v1 implícito.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class ConfigVersionService:
    """Serviço genérico de versionamento para qualquer entidade em config/<subdir>/."""

    def __init__(self, config_root: Path, subdir: str, *, include_flat_files: bool = False) -> None:
        self._root = Path(config_root) / subdir
        self._subdir = subdir
        self._include_flat_files = include_flat_files

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

        flat_file = self._root / f"{entity_id}.json"
        if flat_file.exists():
            try:
                return json.loads(flat_file.read_text(encoding="utf-8"))
            except Exception:
                return None

        return None

    def current_version(self, entity_id: str) -> str:
        return self._read_current(self._root / entity_id / "current")

    # ── Listagem ─────────────────────────────────────────────────────────────

    def _versioned_entity_item(self, entity_dir: Path) -> dict[str, Any]:
        # Find metadata file: <entity>.json or contexto.json or perfil.json
        meta = self._read_meta(entity_dir)
        versions = self._list_versions(entity_dir)
        current = self._read_current(entity_dir / "current")
        return {
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

    def _versioned_entities(self) -> tuple[list[dict[str, Any]], set[str]]:
        result: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for entity_dir in sorted(self._root.iterdir()):
            if not entity_dir.is_dir():
                continue
            item = self._versioned_entity_item(entity_dir)
            result.append(item)
            seen_ids.add(str(item["id"]))
        return result, seen_ids

    @staticmethod
    def _flat_file_item(flat: Path, flat_id: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(flat.read_text(encoding="utf-8"))
        except Exception:
            return None
        entity_id = str(payload.get("id") or payload.get("codigo") or flat_id)
        return {
            "id": entity_id,
            "nome": payload.get("nome") or entity_id,
            "descricao": payload.get("descricao") or "",
            "current_version": "v1",
            "versions": [
                {
                    "version": "v1",
                    "created_at": payload.get("created_at"),
                    "created_by": payload.get("created_by"),
                    "motivo": payload.get("motivo") or "base_flat_file",
                }
            ],
            **{
                k: payload[k]
                for k in payload
                if k not in ("id", "nome", "descricao", "current_version") and not str(k).startswith("$")
            },
        }

    def _flat_file_entities(self, seen_ids: set[str]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for flat in sorted(self._root.glob("*.json")):
            flat_id = flat.stem
            if flat_id in seen_ids:
                continue
            item = self._flat_file_item(flat, flat_id)
            if item is None:
                continue
            entity_id = str(item["id"])
            if entity_id in seen_ids:
                continue
            result.append(item)
            seen_ids.add(entity_id)
        return result

    def list_entities(self) -> list[dict[str, Any]]:
        """Lista todas as entidades disponíveis com histórico de versões."""
        result, seen_ids = self._versioned_entities()

        if self._include_flat_files:
            result.extend(self._flat_file_entities(seen_ids))

        return result

    def list_versions(self, entity_id: str) -> list[dict[str, Any]]:
        entity_dir = self._root / entity_id
        if not entity_dir.is_dir():
            flat_file = self._root / f"{entity_id}.json"
            if flat_file.exists():
                try:
                    payload = json.loads(flat_file.read_text(encoding="utf-8"))
                except Exception:
                    payload = {}
                return [
                    {
                        "version": "v1",
                        "created_at": payload.get("created_at"),
                        "created_by": payload.get("created_by"),
                        "motivo": payload.get("motivo") or "base_flat_file",
                    }
                ]
            return [{"version": "v1", "motivo": "base"}]
        return self._list_versions(entity_dir)

    # ── Criação de nova versão ───────────────────────────────────────────────

    @staticmethod
    def _next_version_name(existing: list[Path]) -> str:
        last_n = 0
        for f in existing:
            try:
                last_n = max(last_n, int(f.stem[1:]))
            except ValueError:
                pass
        return f"v{last_n + 1}"

    def _base_fields_for_new_version(self, entity_id: str, existing: list[Path]) -> dict[str, Any]:
        if existing:
            base = json.loads(existing[-1].read_text(encoding="utf-8"))
        else:
            flat_file = self._root / f"{entity_id}.json"
            if not flat_file.exists():
                return {}
            try:
                base = json.loads(flat_file.read_text(encoding="utf-8"))
            except Exception:
                base = {}
        for k in ("version", "created_at", "created_by", "motivo"):
            base.pop(k, None)
        return base

    def _sync_current_meta(self, entity_dir: Path, entity_id: str, new_entry: dict[str, Any], new_v: str) -> None:
        meta_file = self._find_meta_file(entity_dir)
        # _find_meta_file() only ever returns a path that already exists() (or None),
        # so "meta_file truthy but not existing" is not a reachable state — the
        # complement of the `if` is simply "meta_file is None".
        if meta_file and meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            meta["current_version"] = new_v
            meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            bootstrap_meta = {
                "id": new_entry.get("id") or entity_id,
                "nome": new_entry.get("nome") or entity_id,
                "descricao": new_entry.get("descricao") or "",
                "current_version": new_v,
            }
            (entity_dir / "meta.json").write_text(
                json.dumps(bootstrap_meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

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
        new_v = self._next_version_name(existing)
        base = self._base_fields_for_new_version(entity_id, existing)

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
            self._sync_current_meta(entity_dir, entity_id, new_entry, new_v)

        return new_entry

    # ── Comparação ───────────────────────────────────────────────────────────

    def compare(self, entity_id: str, version_a: str, version_b: str) -> dict[str, Any]:
        a = self.resolve(entity_id, version_a) or {}
        b = self.resolve(entity_id, version_b) or {}

        _skip = {"version", "created_at", "created_by", "motivo", "$comment"}
        all_keys = (set(a) | set(b)) - _skip
        diff: dict[str, Any] = {}
        for k in sorted(all_keys):
            _diff_values(path=k, left=a.get(k), right=b.get(k), out=diff)

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
                # ADR-141 D2: flags de rascunho/rejeição (ADR-120) — aditivo, só
                # aparece quando o dado existe no arquivo de versão.
                for k in ("_rascunho", "_rascunho_descricao", "_rejeitado", "_motivo_rejeicao", "_rejeitado_por"):
                    if k in data:
                        entry[k] = data[k]
                result.append(entry)
            except Exception:
                pass
        return result


# ── Serviços por entidade ────────────────────────────────────────────────────


class ContextoVersionService(ConfigVersionService):
    """Versiona entidades em config/contextos/."""

    def __init__(self, config_root: Path) -> None:
        super().__init__(config_root, "contextos")

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
        super().__init__(config_root, "jurisdicoes", include_flat_files=True)

    def list_jurisdicoes(self) -> list[dict[str, Any]]:
        return self.list_entities()


def _diff_values(path: str, left: Any, right: Any, out: dict[str, Any]) -> None:
    if left == right:
        return
    if isinstance(left, dict) and isinstance(right, dict):
        keys = sorted(set(left) | set(right))
        for key in keys:
            child = f"{path}.{key}"
            _diff_values(child, left.get(key), right.get(key), out)
        return
    # Nota: não há tratamento especial para listas — `left == right` já foi
    # descartado na guarda acima, então (assim como para qualquer outro tipo)
    # a única possibilidade aqui é reportar a diferença bruta abaixo.
    out[path] = {"de": left, "para": right}
