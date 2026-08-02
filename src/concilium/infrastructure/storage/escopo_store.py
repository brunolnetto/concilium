"""Storage de escopos e planos de trabalho (ADR-031 §D3).

EscopoStore — gerencia o diretório de um escopo dentro de um projeto.
PlanoStore  — gerencia o diretório de um plano dentro de um escopo.

Estrutura de filesystem:
    projetos/{projeto_id}/
    ├── meta.json
    ├── snapshots/
    └── escopos/
        └── {escopo_id}/
            ├── escopo.json
            └── planos/
                └── {plano_id}/
                    ├── plano.json
                    ├── canonical.json
                    ├── invocations.log
                    └── outputs/
"""

from __future__ import annotations

import json
import os
import shutil
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from concilium.domain.models.canonical import CanonicalModel
from concilium.domain.models.project.escopo import Escopo, StatusPlano

from ._bdi_perfil_freeze import (
    bdi_perfil_versao_filename,
    bdi_perfil_versoes_referenciadas,
    extract_bdi_perfil_versao,
)


class PlanoStore:
    """Gerencia o diretório de um PlanoTrabalho (ADR-031 §D2, §D3)."""

    CANONICAL_FILE = "canonical.json"
    INVOCATIONS_LOG = "invocations.log"
    PLANO_FILE = "plano.json"
    PREMISSAS_EFETIVAS_FILE = "premissas_efetivas.json"
    PREMISSAS_POR_SKILL_FILE = "premissas_por_skill.json"

    def __init__(self, root: Path, escopo_store: EscopoStore | None = None) -> None:
        self.root = root
        self.escopo_store = escopo_store

    @staticmethod
    def _get_output_subdir(filename: str) -> str:
        """Determina o subdiretório baseado na extensão do arquivo.

        returns: "visualizations" para imagens, "reports" para PDFs/XLSXs
        """
        ext = Path(filename).suffix.lower()
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"):
            return "visualizations"
        if ext in (".pdf", ".xlsx", ".xls", ".csv"):
            return "reports"
        return "reports"  # fallback

    # ── Metadados do plano ──────────────────────────────────────────────

    @property
    def plano_id(self) -> str:
        return self.root.name

    @property
    def meta(self) -> dict[str, Any]:
        pf = self.root / self.PLANO_FILE
        if pf.exists():
            return json.loads(pf.read_text(encoding="utf-8"))
        return {"plano_id": self.plano_id, "status": "RASCUNHO"}

    def _update_meta(self, **changes: Any) -> None:
        m = self.meta
        m.update(changes)
        (self.root / self.PLANO_FILE).write_text(json.dumps(m, indent=2, default=str), encoding="utf-8")

    @property
    def status(self) -> StatusPlano:
        return self.meta.get("status", "RASCUNHO")  # type: ignore[return-value]

    # ── Canonical ──────────────────────────────────────────────────────

    def _is_readonly(self) -> bool:
        cf = self.root / self.CANONICAL_FILE
        return cf.exists() and not bool(cf.stat().st_mode & stat.S_IWUSR)

    def load_canonical(self) -> CanonicalModel | None:
        path = self.root / self.CANONICAL_FILE
        if not path.exists():
            return None
        return CanonicalModel.model_validate_json(path.read_text(encoding="utf-8"))

    def save_canonical(
        self,
        model: CanonicalModel,
        trace_id: str | None = None,
        created_by: str = "runtime",
        parent_refs: list | None = None,
    ) -> None:
        """Persiste canonical + sidecar (ADR-018). Falha se APROVADO."""
        if self._is_readonly():
            raise PermissionError(
                f"Plano '{self.plano_id}' está APROVADO (read-only). Crie uma nova iteração antes de modificar."
            )
        path = self.root / self.CANONICAL_FILE
        payload_json = model.model_dump_json(indent=2)
        path.write_text(payload_json, encoding="utf-8")

        try:
            from hashlib import sha256

            from concilium.domain.models.artifact import ArtifactKind, ArtifactMeta
            from concilium.infrastructure.storage.artifact_store import FileSystemArtifactStore

            content_hash = sha256(payload_json.encode()).hexdigest()
            meta = ArtifactMeta(
                kind=ArtifactKind.CANONICAL,
                schema_name="CanonicalModel",
                schema_version="2026-05-05",
                created_by=created_by,
                trace_id=trace_id,
                parent_refs=parent_refs or [],
                content_hash=content_hash,
                version=self.plano_id,
            )
            FileSystemArtifactStore(self.root).save_meta_sidecar(path, meta)
        except Exception:  # pragma: no cover
            pass  # sidecar é best-effort

    def write_canonical_raw(self, content: dict) -> None:
        if self._is_readonly():
            raise PermissionError(f"Plano '{self.plano_id}' é read-only (APROVADO).")
        path = self.root / self.CANONICAL_FILE
        path.write_text(json.dumps(content, indent=2, default=str), encoding="utf-8")

    # ── Invocations log ────────────────────────────────────────────────

    def log_invocation(self, entry: dict) -> None:
        log = self.root / self.INVOCATIONS_LOG
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def read_invocations(self) -> list[dict]:
        log = self.root / self.INVOCATIONS_LOG
        if not log.exists():
            return []
        out: list[dict] = []
        for line in log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return out

    # ── Premissas efetivas (issue #121 — congelamento junto com o resultado) ──

    def write_premissas_efetivas(
        self, skill_id: str, normalized_inputs: dict[str, Any], escopo_meta: dict[str, Any]
    ) -> None:
        """Congela os inputs efetivamente usados por uma skill para o canônico atual.

        `premissas_efetivas.json` guarda sempre o último snapshot completo (o que
        gerou o canônico corrente, para auditoria/reprodutibilidade).

        `premissas_por_skill.json` guarda, por skill, o hash de `escopo_meta`
        (não de `normalized_inputs` inteiro — cada skill tem inputs próprios por
        contrato, comparar o dict inteiro entre skills diferentes sempre daria
        divergente). `escopo_meta` é a superfície de premissas compartilhada por
        todas as skills do plano (catálogo/jurisdição/perfil do escopo) — é o que
        `_process_staleness_check` compara para detectar reexecução parcial com
        premissas divergentes entre skills dependentes.
        """
        if self._is_readonly():
            return
        from hashlib import sha256

        payload = json.dumps(normalized_inputs, sort_keys=True, default=str)
        content_hash = sha256(payload.encode()).hexdigest()
        escopo_hash = sha256(json.dumps(escopo_meta, sort_keys=True, default=str).encode()).hexdigest()
        ts = datetime.now(UTC).isoformat()

        (self.root / self.PREMISSAS_EFETIVAS_FILE).write_text(
            json.dumps(
                {"skill_id": skill_id, "hash": content_hash, "ts": ts, "inputs": normalized_inputs},
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        por_skill = self.read_premissas_por_skill()
        registro: dict[str, Any] = {"hash": content_hash, "escopo_hash": escopo_hash, "ts": ts}
        bdi_perfil_versao = extract_bdi_perfil_versao(normalized_inputs)
        if bdi_perfil_versao is not None:
            registro["bdi_perfil_versao"] = bdi_perfil_versao
        por_skill[skill_id] = registro
        (self.root / self.PREMISSAS_POR_SKILL_FILE).write_text(
            json.dumps(por_skill, indent=2, default=str), encoding="utf-8"
        )

    def read_premissas_por_skill(self) -> dict[str, dict[str, Any]]:
        f = self.root / self.PREMISSAS_POR_SKILL_FILE
        if not f.exists():
            return {}
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    # ── Outputs ────────────────────────────────────────────────────────

    def save_output_file(self, data: bytes, filename: str = "resultado.xlsx") -> Path:
        """Salva arquivo em outputs/{subdir}/{filename}.

        Imagens → outputs/visualizations/
        PDFs e planilhas → outputs/reports/
        """
        subdir = self._get_output_subdir(filename)
        outputs = self.root / "outputs" / subdir
        outputs.mkdir(parents=True, exist_ok=True)
        p = outputs / filename
        p.write_bytes(data)
        return p

    def load_output_file(self, filename: str = "resultado.xlsx") -> bytes | None:
        """Carrega arquivo de outputs/{subdir}/{filename}.

        Procura em visualizations ou reports conforme extensão.
        Retorna None se inexistente.
        """
        subdir = self._get_output_subdir(filename)
        p = self.root / "outputs" / subdir / filename
        if p.exists():
            return p.read_bytes()

        # Fallback: tentar no outro diretório (compatibilidade)
        fallback_subdir = "reports" if subdir == "visualizations" else "visualizations"
        fallback_path = self.root / "outputs" / fallback_subdir / filename
        if fallback_path.exists():
            return fallback_path.read_bytes()

        return None

    def list_output_files(self) -> list[str]:
        """Lista nomes de arquivos em outputs/, recursivamente em subdiretórios."""
        d = self.root / "outputs"
        if not d.exists():
            return []

        files = []
        for subdir_path in d.iterdir():
            if subdir_path.is_dir():
                for f in subdir_path.iterdir():
                    if f.is_file():
                        files.append(f.name)
        return sorted(files)

    # ── Ciclo de vida ─────────────────────────────────────────────────

    def approve(self) -> None:
        """Marca plano como APROVADO: chmod 444 em canonical + invocations + premissas.

        As premissas efetivas (issue #121) são congeladas junto com o resultado —
        antes desta correção, só canonical/invocations ficavam read-only, enquanto
        overrides e inputs de skill continuavam editáveis por baixo da versão aprovada.
        """
        for fname in (
            self.CANONICAL_FILE,
            self.INVOCATIONS_LOG,
            self.PREMISSAS_EFETIVAS_FILE,
            self.PREMISSAS_POR_SKILL_FILE,
        ):
            f = self.root / fname
            if f.exists():
                os.chmod(f, 0o444)
        self._protect_bdi_perfil_versoes()
        self._update_meta(
            status="APROVADO",
            aprovado_em=datetime.now(UTC).isoformat(),
        )

    def _projeto_root(self) -> Path:
        """Raiz do projeto — várias camadas acima do diretório do plano.

        Preferencialmente via `escopo_store.root` (projetos/{pid}/escopos/{eid}/);
        fallback pela estrutura fixa do próprio diretório quando não há referência
        ao EscopoStore (ex.: PlanoStore construído solto em teste).
        """
        if self.escopo_store is not None:
            return self.escopo_store.root.parents[1]
        return self.root.parents[3]

    def _protect_bdi_perfil_versoes(self) -> None:
        """Protege (chmod 444) os snapshots de perfil BDI usados pelas skills deste plano (issue #123).

        `bdi/perfil_bdi.json` (cabeça) NÃO é protegido — deve continuar editável
        para futuras versões/planos. Só os snapshots `perfil_bdi_v{NNN}.json`
        efetivamente referenciados em `premissas_por_skill.json` são congelados.
        """
        versoes = bdi_perfil_versoes_referenciadas(self.read_premissas_por_skill())
        if not versoes:
            return
        bdi_dir = self._projeto_root() / "bdi"
        for versao in versoes:
            f = bdi_dir / bdi_perfil_versao_filename(versao)
            if f.exists():
                os.chmod(f, 0o444)

    def archive(self) -> None:
        self._update_meta(status="ARQUIVADO", arquivado_em=datetime.now(UTC).isoformat())

    def set_em_analise(self) -> None:
        self._update_meta(status="EM_ANALISE")

    def new_iteration(self, base_plano: PlanoStore | None = None) -> PlanoStore:
        """Cria nova iteração (copy-on-write) dentro do mesmo escopo. Retorna o novo PlanoStore."""
        escopo_dir = self.root.parent
        planos_dir = escopo_dir
        new_id = str(uuid4())
        new_root = planos_dir / new_id
        new_root.mkdir(parents=True, exist_ok=True)
        (new_root / "outputs").mkdir()
        (new_root / self.INVOCATIONS_LOG).touch()

        src = base_plano or self
        src_canonical = src.root / self.CANONICAL_FILE
        if src_canonical.exists():
            shutil.copy(src_canonical, new_root / self.CANONICAL_FILE)

        parent_meta = src.meta
        new_meta = {
            "plano_id": new_id,
            "escopo_id": parent_meta.get("escopo_id", ""),
            "projeto_id": parent_meta.get("projeto_id", ""),
            "nome": parent_meta.get("nome", ""),
            "hipotese": parent_meta.get("hipotese"),
            "status": "RASCUNHO",
            "versao_iteracao": parent_meta.get("versao_iteracao", 1) + 1,
            "criado_em": datetime.now(UTC).isoformat(),
        }
        (new_root / self.PLANO_FILE).write_text(json.dumps(new_meta, indent=2), encoding="utf-8")
        return PlanoStore(new_root)


class EscopoStore:
    """Gerencia o diretório de um Escopo (ADR-031 §D3)."""

    ESCOPO_FILE = "escopo.json"

    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def escopo_id(self) -> str:
        return self.root.name

    @property
    def meta(self) -> dict[str, Any]:
        ef = self.root / self.ESCOPO_FILE
        if ef.exists():
            return json.loads(ef.read_text(encoding="utf-8"))
        return {"escopo_id": self.escopo_id}

    def update_meta(self, **changes: Any) -> None:
        m = self.meta
        m.update(changes)
        (self.root / self.ESCOPO_FILE).write_text(json.dumps(m, indent=2, default=str), encoding="utf-8")

    def to_escopo(self) -> Escopo | None:
        m = self.meta
        try:
            return Escopo.model_validate(m)
        except Exception:
            return None

    def upsert_roster_mo_membro(self, membro: dict[str, Any]) -> None:
        """ADR-173 D5: adiciona ou edita um membro de `roster_mo` por `individuo_id`.

        Merge raso — campos ausentes em `membro` preservam o valor já persistido
        (ex.: "desligar" só precisa enviar `individuo_id` + `data_desligamento`).
        Nunca remove um registro já presente na lista.
        """
        individuo_id = membro.get("individuo_id")
        if not individuo_id:
            raise ValueError("membro.individuo_id é obrigatório")
        roster = list(self.meta.get("roster_mo") or [])
        for i, m in enumerate(roster):
            if m.get("individuo_id") == individuo_id:
                roster[i] = {**m, **membro}
                break
        else:
            roster.append(membro)
        self.update_meta(roster_mo=roster)

    # ── Planos ─────────────────────────────────────────────────────────

    @property
    def _planos_dir(self) -> Path:
        return self.root / "planos"

    def list_plans(self) -> list[str]:
        d = self._planos_dir
        if not d.exists():
            return []
        return sorted(p.name for p in d.iterdir() if p.is_dir())

    def plan(self, plano_id: str) -> PlanoStore:
        return PlanoStore(self._planos_dir / plano_id, escopo_store=self)

    def create_plan(
        self,
        nome: str,
        hipotese: str | None = None,
        plano_id: str | None = None,
    ) -> PlanoStore:
        """Cria novo PlanoTrabalho dentro deste escopo."""
        pid = plano_id or str(uuid4())
        plan_root = self._planos_dir / pid
        plan_root.mkdir(parents=True, exist_ok=True)
        (plan_root / "outputs").mkdir()
        (plan_root / PlanoStore.INVOCATIONS_LOG).touch()

        escopo_meta = self.meta
        meta = {
            "plano_id": pid,
            "escopo_id": self.escopo_id,
            "projeto_id": escopo_meta.get("projeto_id", ""),
            "nome": nome,
            "hipotese": hipotese,
            "status": "RASCUNHO",
            "versao_iteracao": 1,
            "criado_em": datetime.now(UTC).isoformat(),
        }
        (plan_root / PlanoStore.PLANO_FILE).write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return PlanoStore(plan_root, escopo_store=self)

    def approved_plan(self) -> PlanoStore | None:
        """Retorna o plano APROVADO deste escopo (no máximo um), ou None."""
        for pid in self.list_plans():
            ps = self.plan(pid)
            if ps.status == "APROVADO":
                return ps
        return None

    def active_plan(self) -> PlanoStore | None:
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
