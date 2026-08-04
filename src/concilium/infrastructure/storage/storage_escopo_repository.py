"""EscopoHandle/PlanoHandle via BlobStoragePort (ADR-047 — porta EscopoStore/PlanoStore).

Convenção de path, espelhando o que `StorageProjectHandle.create_escopo` já escreve:
    {project_id}/escopos/{escopo_id}/meta.json
    {project_id}/escopos/{escopo_id}/planos/_index.json                 ("plano_ids": [...])
    {project_id}/escopos/{escopo_id}/planos/{plano_id}/plano.json
    {project_id}/escopos/{escopo_id}/planos/{plano_id}/canonical.json
    {project_id}/escopos/{escopo_id}/planos/{plano_id}/canonical.meta.json
    {project_id}/escopos/{escopo_id}/planos/{plano_id}/invocations.log
    {project_id}/escopos/{escopo_id}/planos/{plano_id}/premissas_efetivas.json
    {project_id}/escopos/{escopo_id}/planos/{plano_id}/premissas_por_skill.json
    {project_id}/escopos/{escopo_id}/planos/{plano_id}/outputs/{visualizations,reports}/{filename}

BlobStoragePort não tem listagem de diretório com metadados nem transação
atômica — por isso `list_plans()` lê `_index.json` (mesmo padrão já usado por
`projetos/_index.json` e `escopos/_index.json`) em vez de derivar de
`listar_blobs()`, e `log_invocation`/`_upsert_roster_item` fazem
leitura-então-escrita (sem operação atômica de append/merge nativa).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from concilium.domain.models.canonical import CanonicalModel
from concilium.domain.models.project.escopo import Escopo
from concilium.domain.repositories.blob_storage_port import BlobStoragePort

from ._bdi_perfil_freeze import (
    bdi_perfil_versao_filename,
    bdi_perfil_versoes_referenciadas,
    extract_bdi_perfil_versao,
)


class StoragePlanoHandle:
    """PlanoHandle backed by BlobStoragePort — porta `PlanoStore` (escopo_store.py)."""

    CANONICAL_FILE = "canonical.json"
    INVOCATIONS_LOG = "invocations.log"
    PLANO_FILE = "plano.json"
    PREMISSAS_EFETIVAS_FILE = "premissas_efetivas.json"
    PREMISSAS_POR_SKILL_FILE = "premissas_por_skill.json"

    def __init__(
        self,
        storage: BlobStoragePort,
        project_id: str,
        escopo_id: str,
        plano_id: str,
        escopo_store: StorageEscopoHandle | None = None,
    ) -> None:
        self._storage = storage
        self._project_id = project_id
        self._escopo_id = escopo_id
        self._plano_id = plano_id
        self.escopo_store = escopo_store

    def _path(self, relative: str) -> str:
        return f"{self._project_id}/escopos/{self._escopo_id}/planos/{self._plano_id}/{relative.lstrip('/')}"

    @staticmethod
    def _get_output_subdir(filename: str) -> str:
        ext = Path(filename).suffix.lower()
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"):
            return "visualizations"
        if ext in (".pdf", ".xlsx", ".xls", ".csv"):
            return "reports"
        return "reports"  # fallback

    def _read_json(self, relative: str, default: Any) -> Any:
        try:
            return json.loads(self._storage.ler_blob(self._path(relative)).decode("utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    def _write_json(self, relative: str, payload: Any) -> None:
        content = json.dumps(payload, indent=2, ensure_ascii=False, default=str).encode("utf-8")
        self._storage.gravar_blob(self._path(relative), content)

    # ── Metadados do plano ──────────────────────────────────────────────

    @property
    def plano_id(self) -> str:
        return self._plano_id

    @property
    def meta(self) -> dict[str, Any]:
        return self._read_json(self.PLANO_FILE, {"plano_id": self._plano_id, "status": "RASCUNHO"})

    def _update_meta(self, **changes: Any) -> None:
        m = self.meta
        m.update(changes)
        self._write_json(self.PLANO_FILE, m)

    @property
    def status(self) -> str:
        return self.meta.get("status", "RASCUNHO")

    def _is_readonly(self) -> bool:
        """Equivalente ao chmod 444 do `PlanoStore` local: em BlobStoragePort não há
        bit de permissão a checar, então o status "APROVADO" (a mesma fonte de
        verdade que `approve()` grava) já basta como sinal de imutabilidade."""
        return self.status == "APROVADO"

    # ── Canonical ──────────────────────────────────────────────────────

    def load_canonical(self) -> CanonicalModel | None:
        try:
            data = self._storage.ler_blob(self._path(self.CANONICAL_FILE))
        except FileNotFoundError:
            return None
        return CanonicalModel.model_validate_json(data.decode("utf-8"))

    def save_canonical(
        self,
        model: CanonicalModel,
        trace_id: str | None = None,
        created_by: str = "runtime",
        parent_refs: list | None = None,
    ) -> None:
        if self._is_readonly():
            raise PermissionError(
                f"Plano '{self._plano_id}' está APROVADO (read-only). Crie uma nova iteração antes de modificar."
            )
        payload_json = model.model_dump_json(indent=2)
        self._storage.gravar_blob(self._path(self.CANONICAL_FILE), payload_json.encode("utf-8"))
        self._write_canonical_meta_sidecar(
            payload_json, trace_id=trace_id, created_by=created_by, parent_refs=parent_refs
        )

    def _write_canonical_meta_sidecar(
        self, payload_json: str, *, trace_id: str | None, created_by: str, parent_refs: list | None
    ) -> None:
        """ADR-018 §D2: sidecar de proveniência — best-effort, nunca falha o save."""
        try:
            from hashlib import sha256

            from concilium.domain.models.artifact import ArtifactKind, ArtifactMeta

            meta = ArtifactMeta(
                kind=ArtifactKind.CANONICAL,
                schema_name="CanonicalModel",
                schema_version="2026-05-05",
                created_by=created_by,
                trace_id=trace_id,
                parent_refs=parent_refs or [],
                content_hash=sha256(payload_json.encode()).hexdigest(),
                version=self._plano_id,
            )
            self._write_json("canonical.meta.json", meta.model_dump(mode="json"))
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning("Sidecar write falhou (best-effort, canonical preservado): %s", exc)

    def write_canonical_raw(self, content: dict) -> None:
        if self._is_readonly():
            raise PermissionError(f"Plano '{self._plano_id}' é read-only (APROVADO).")
        self._write_json(self.CANONICAL_FILE, content)

    # ── Invocations log ────────────────────────────────────────────────

    def log_invocation(self, entry: dict) -> None:
        line = json.dumps(entry, default=str) + "\n"
        existing = b""
        try:
            existing = self._storage.ler_blob(self._path(self.INVOCATIONS_LOG))
        except FileNotFoundError:
            pass
        self._storage.gravar_blob(self._path(self.INVOCATIONS_LOG), existing + line.encode("utf-8"))

    def read_invocations(self) -> list[dict]:
        try:
            data = self._storage.ler_blob(self._path(self.INVOCATIONS_LOG))
        except FileNotFoundError:
            return []
        out: list[dict] = []
        for raw_line in data.decode("utf-8").splitlines():
            raw_line = raw_line.strip()
            if raw_line:
                try:
                    out.append(json.loads(raw_line))
                except json.JSONDecodeError:
                    pass
        return out

    # ── Premissas efetivas (issue #121/#123) ────────────────────────────

    def write_premissas_efetivas(
        self, skill_id: str, normalized_inputs: dict[str, Any], escopo_meta: dict[str, Any]
    ) -> None:
        if self._is_readonly():
            return
        from hashlib import sha256

        payload = json.dumps(normalized_inputs, sort_keys=True, default=str)
        content_hash = sha256(payload.encode()).hexdigest()
        escopo_hash = sha256(json.dumps(escopo_meta, sort_keys=True, default=str).encode()).hexdigest()
        ts = datetime.now(UTC).isoformat()

        self._write_json(
            self.PREMISSAS_EFETIVAS_FILE,
            {"skill_id": skill_id, "hash": content_hash, "ts": ts, "inputs": normalized_inputs},
        )

        por_skill = self.read_premissas_por_skill()
        registro: dict[str, Any] = {"hash": content_hash, "escopo_hash": escopo_hash, "ts": ts}
        bdi_perfil_versao = extract_bdi_perfil_versao(normalized_inputs)
        if bdi_perfil_versao is not None:
            registro["bdi_perfil_versao"] = bdi_perfil_versao
        por_skill[skill_id] = registro
        self._write_json(self.PREMISSAS_POR_SKILL_FILE, por_skill)

    def read_premissas_por_skill(self) -> dict[str, dict[str, Any]]:
        result = self._read_json(self.PREMISSAS_POR_SKILL_FILE, {})
        return result if isinstance(result, dict) else {}

    # ── Outputs ────────────────────────────────────────────────────────

    def save_output_file(self, data: bytes, filename: str = "resultado.xlsx") -> Path:
        subdir = self._get_output_subdir(filename)
        relative = f"outputs/{subdir}/{filename}"
        self._storage.gravar_blob(self._path(relative), data)
        return Path(self._project_id) / "escopos" / self._escopo_id / "planos" / self._plano_id / relative

    def load_output_file(self, filename: str = "resultado.xlsx") -> bytes | None:
        subdir = self._get_output_subdir(filename)
        try:
            return self._storage.ler_blob(self._path(f"outputs/{subdir}/{filename}"))
        except FileNotFoundError:
            pass
        fallback_subdir = "reports" if subdir == "visualizations" else "visualizations"
        try:
            return self._storage.ler_blob(self._path(f"outputs/{fallback_subdir}/{filename}"))
        except FileNotFoundError:
            return None

    def list_output_files(self) -> list[str]:
        prefix = self._path("outputs")
        blobs = self._storage.listar_blobs(prefix)
        return sorted({b.rsplit("/", 1)[-1] for b in blobs if not b.endswith("/")})

    # ── Ciclo de vida ─────────────────────────────────────────────────

    def approve(self) -> None:
        """Marca plano como APROVADO: `aprovar_versao` em canonical + invocations + premissas
        (Local=chmod 444, SharePoint=checkin — mesma semântica de `StorageProjectHandle.approve`)."""
        for fname in (
            self.CANONICAL_FILE,
            self.INVOCATIONS_LOG,
            self.PREMISSAS_EFETIVAS_FILE,
            self.PREMISSAS_POR_SKILL_FILE,
        ):
            path = self._path(fname)
            if self._storage.blob_existe(path):
                self._storage.aprovar_versao(path)
        self._protect_bdi_perfil_versoes()
        self._update_meta(status="APROVADO", aprovado_em=datetime.now(UTC).isoformat())

    def _protect_bdi_perfil_versoes(self) -> None:
        """Protege (aprovar_versao) os snapshots de perfil BDI referenciados pelas
        skills deste plano (issue #123) — mesma lógica de
        `StorageProjectHandle._protect_bdi_perfil_versoes`, mas para o modelo
        escopo/plano em vez de vN flat."""
        versoes = bdi_perfil_versoes_referenciadas(self.read_premissas_por_skill())
        for versao in versoes:
            relative = f"bdi/{bdi_perfil_versao_filename(versao)}"
            path = f"{self._project_id}/{relative}"
            if self._storage.blob_existe(path):
                self._storage.aprovar_versao(path)

    def archive(self) -> None:
        self._update_meta(status="ARQUIVADO", arquivado_em=datetime.now(UTC).isoformat())

    def set_em_analise(self) -> None:
        self._update_meta(status="EM_ANALISE")

    def new_iteration(self, base_plano: StoragePlanoHandle | None = None) -> StoragePlanoHandle:
        """Cria nova iteração (copy-on-write) dentro do mesmo escopo.

        Diferente do `PlanoStore` local (onde a existência do diretório já
        implica listagem), aqui é preciso um `escopo_store` válido para
        manter `planos/_index.json` consistente — sem índice, `list_plans()`
        nunca veria a nova iteração.
        """
        if self.escopo_store is None:
            raise RuntimeError(
                f"Plano '{self._plano_id}' não tem escopo_store associado — "
                "new_iteration() precisa dele para atualizar o índice de planos."
            )
        new_id = str(uuid.uuid4())
        new_handle = StoragePlanoHandle(
            self._storage, self._project_id, self._escopo_id, new_id, escopo_store=self.escopo_store
        )

        src = base_plano or self
        try:
            canon_bytes = self._storage.ler_blob(src._path(self.CANONICAL_FILE))
            self._storage.gravar_blob(new_handle._path(self.CANONICAL_FILE), canon_bytes)
        except FileNotFoundError:
            pass

        parent_meta = src.meta
        new_meta = {
            "plano_id": new_id,
            "escopo_id": parent_meta.get("escopo_id", self._escopo_id),
            "projeto_id": parent_meta.get("projeto_id", ""),
            "nome": parent_meta.get("nome", ""),
            "hipotese": parent_meta.get("hipotese"),
            "status": "RASCUNHO",
            "versao_iteracao": parent_meta.get("versao_iteracao", 1) + 1,
            "criado_em": datetime.now(UTC).isoformat(),
        }
        new_handle._write_json(self.PLANO_FILE, new_meta)
        self.escopo_store._add_plano_to_index(new_id)
        return new_handle


class StorageEscopoHandle:
    """EscopoHandle backed by BlobStoragePort — porta `EscopoStore` (escopo_store.py)."""

    META_FILE = "meta.json"
    _PLANOS_INDEX = "planos/_index.json"

    def __init__(self, storage: BlobStoragePort, project_id: str, escopo_id: str) -> None:
        self._storage = storage
        self._project_id = project_id
        self._escopo_id = escopo_id

    def _path(self, relative: str) -> str:
        return f"{self._project_id}/escopos/{self._escopo_id}/{relative.lstrip('/')}"

    @property
    def escopo_id(self) -> str:
        return self._escopo_id

    @property
    def meta(self) -> dict[str, Any]:
        try:
            return json.loads(self._storage.ler_blob(self._path(self.META_FILE)).decode("utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {"escopo_id": self._escopo_id}

    def update_meta(self, **changes: Any) -> None:
        m = self.meta
        m.update(changes)
        content = json.dumps(m, indent=2, ensure_ascii=False, default=str).encode("utf-8")
        self._storage.gravar_blob(self._path(self.META_FILE), content)

    def to_escopo(self) -> Escopo | None:
        try:
            return Escopo.model_validate(self.meta)
        except Exception:
            return None

    def _upsert_roster_item(self, campo: str, chave: str, item: dict[str, Any]) -> None:
        """Merge raso por `chave` dentro da lista `campo`. Nunca remove um registro
        já presente — mesma semântica de `EscopoStore._upsert_roster_item`."""
        valor_chave = item.get(chave)
        if not valor_chave:
            raise ValueError(f"item.{chave} é obrigatório")
        roster = list(self.meta.get(campo) or [])
        for i, m in enumerate(roster):
            if m.get(chave) == valor_chave:
                roster[i] = {**m, **item}
                break
        else:
            roster.append(item)
        self.update_meta(**{campo: roster})

    def upsert_roster_mo_membro(self, membro: dict[str, Any]) -> None:
        self._upsert_roster_item("roster_mo", "individuo_id", membro)

    def upsert_roster_eq_ativo(self, ativo: dict[str, Any]) -> None:
        self._upsert_roster_item("roster_eq", "ativo_id", ativo)

    # ── Planos ─────────────────────────────────────────────────────────

    def list_plans(self) -> list[str]:
        index = self._read_planos_index()
        return sorted(index["plano_ids"])

    def _read_planos_index(self) -> dict[str, list[str]]:
        try:
            data = json.loads(self._storage.ler_blob(self._path(self._PLANOS_INDEX)).decode("utf-8"))
            if isinstance(data, dict) and isinstance(data.get("plano_ids"), list):
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return {"plano_ids": []}

    def _add_plano_to_index(self, plano_id: str) -> None:
        index = self._read_planos_index()
        if plano_id not in index["plano_ids"]:
            index["plano_ids"].append(plano_id)
        content = json.dumps(index, indent=2).encode("utf-8")
        self._storage.gravar_blob(self._path(self._PLANOS_INDEX), content)

    def plan(self, plano_id: str) -> StoragePlanoHandle:
        return StoragePlanoHandle(self._storage, self._project_id, self._escopo_id, plano_id, escopo_store=self)

    def create_plan(
        self, nome: str, hipotese: str | None = None, plano_id: str | None = None
    ) -> StoragePlanoHandle:
        """Cria novo PlanoTrabalho dentro deste escopo."""
        pid = plano_id or str(uuid.uuid4())
        handle = StoragePlanoHandle(self._storage, self._project_id, self._escopo_id, pid, escopo_store=self)

        escopo_meta = self.meta
        meta = {
            "plano_id": pid,
            "escopo_id": self._escopo_id,
            "projeto_id": escopo_meta.get("projeto_id", ""),
            "nome": nome,
            "hipotese": hipotese,
            "status": "RASCUNHO",
            "versao_iteracao": 1,
            "criado_em": datetime.now(UTC).isoformat(),
        }
        handle._write_json(StoragePlanoHandle.PLANO_FILE, meta)
        self._add_plano_to_index(pid)
        return handle

    def approved_plan(self) -> StoragePlanoHandle | None:
        """Retorna o plano APROVADO deste escopo (no máximo um), ou None."""
        for pid in self.list_plans():
            ps = self.plan(pid)
            if ps.status == "APROVADO":
                return ps
        return None

    def active_plan(self) -> StoragePlanoHandle | None:
        """Retorna plano APROVADO ou, na ausência, o RASCUNHO/EM_ANALISE mais recente."""
        ap = self.approved_plan()
        if ap:
            return ap
        candidates = [
            self.plan(pid) for pid in self.list_plans() if self.plan(pid).status in ("RASCUNHO", "EM_ANALISE")
        ]
        return candidates[-1] if candidates else None

    def approve_plan(self, plano_id: str) -> list[str]:
        """Aprova o plano indicado e arquiva os demais EM_ANALISE/RASCUNHO.

        Retorna lista de plano_ids arquivados automaticamente.
        """
        arquivados: list[str] = []
        for pid in self.list_plans():
            ps = self.plan(pid)
            if pid == plano_id:
                ps.approve()
            elif ps.status in ("RASCUNHO", "EM_ANALISE"):
                ps.archive()
                arquivados.append(pid)
        return arquivados


class StorageSnapshotStore:
    """Snapshots imutáveis via BlobStoragePort — porta só o lado de escrita de
    `SnapshotStore` (snapshot.py): `.load()` não tem nenhum chamador confirmado
    no código real (só o hash de retorno de `.store()` é usado, nunca o
    conteúdo lido de volta), então não foi portado — ver achado da investigação
    da issue #146."""

    def __init__(self, storage: BlobStoragePort, project_id: str) -> None:
        self._storage = storage
        self._project_id = project_id

    @staticmethod
    def compute_hash(content: dict | list) -> str:
        from hashlib import sha256

        serialized = json.dumps(content, sort_keys=True, default=str).encode()
        return sha256(serialized).hexdigest()

    def store(self, kind: str, content: dict | list) -> str:
        """Persiste snapshot, retorna o hash curto. Reusa blob existente se hash coincide."""
        h = self.compute_hash(content)
        short = h[:7]
        path = f"{self._project_id}/snapshots/{kind}-{short}.json"
        if not self._storage.blob_existe(path):
            payload = json.dumps(content, indent=2, default=str, ensure_ascii=False).encode("utf-8")
            self._storage.gravar_blob(path, payload)
        return short
