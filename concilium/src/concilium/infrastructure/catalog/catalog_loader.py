"""ADR-024 — CatalogLoader: carregamento de catálogo com cache local e detecção de mudanças.

Dois backends:
  LOCAL_JSON    — lê arquivos JSON em config/catalogos/<id>/ (comportamento atual).
  GOOGLE_SHEETS — lê de uma planilha Google Sheets via API (requer credenciais OAuth2/SA).

Política de cache (backend LOCAL_JSON):
  - Cache em .concilium/catalog_cache/{catalog_name}/latest.json
  - TTL configurável via concilium.yaml (catalog.remote_ttl_minutes, padrão 60)
  - Invalidação por SHA-256 do conteúdo normalizado (CatalogSnapshot.compute_hash)
  - --offline: usa cache mesmo com TTL expirado; falha se cache ausente

Integração com pipeline:
  - Pré-00-escopo: CatalogLoader.load() retorna (CatalogSnapshot, CatalogDiff | None)
  - Diff é emitido como ArtifactKind.CATALOG_DIFF quando o hash muda entre runs

Ver ADR-024 para política completa de TTL, flags e estrutura de diretório.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from concilium.domain.models.catalog_snapshot import (
    CatalogDiff,
    CatalogSnapshot,
    CatalogSnapshotMeta,
    compute_catalog_diff,
)


class CatalogBackend(StrEnum):
    """Backend de carregamento de catálogo (ADR-024 §D6, ADR-047 §D5)."""

    LOCAL_JSON = "local_json"  # comportamento atual — padrão
    GOOGLE_SHEETS = "google_sheets"  # requer credenciais SA
    SHAREPOINT = "sharepoint"  # ADR-047: SharePoint / OneDrive via Graph API


# ── Cache ────────────────────────────────────────────────────────────────────

_DEFAULT_TTL_MINUTES = 60
_CACHE_SUBDIR = ".concilium/catalog_cache"


def _cache_dir(project_root: Path, catalog_name: str) -> Path:
    return project_root / _CACHE_SUBDIR / catalog_name


def _read_cache(project_root: Path, catalog_name: str) -> CatalogSnapshot | None:
    """Lê snapshot do cache local. Retorna None se ausente ou corrompido."""
    cache_file = _cache_dir(project_root, catalog_name) / "latest.json"
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        return CatalogSnapshot.model_validate(data)
    except Exception:
        return None


def _write_cache(project_root: Path, catalog_name: str, snapshot: CatalogSnapshot) -> None:
    """Persiste snapshot no cache local."""
    cache_path = _cache_dir(project_root, catalog_name)
    cache_path.mkdir(parents=True, exist_ok=True)
    (cache_path / "latest.json").write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    # Metadados separados para checagem rápida de hash sem carregar payload completo
    (cache_path / "latest_meta.json").write_text(snapshot.meta.model_dump_json(indent=2), encoding="utf-8")


def _cache_is_fresh(snapshot: CatalogSnapshot, ttl_minutes: int) -> bool:
    """Verifica se o cache está dentro do TTL."""
    age = datetime.now(UTC) - snapshot.meta.created_at
    return age < timedelta(minutes=ttl_minutes)


# ── Local JSON loader ─────────────────────────────────────────────────────────


def _load_local_json(
    config_root: Path,
    catalog_name: str,
) -> tuple[list[dict], dict[str, list[dict]], list[dict], list[dict]]:
    """Carrega CPUs, insumos, produtividades e funções de config/catalogos/<catalog_name>/."""
    cat_dir = config_root / "catalogos" / catalog_name
    if not cat_dir.exists():
        raise FileNotFoundError(f"Catálogo '{catalog_name}' não encontrado em {cat_dir}")

    # CPUs
    cpus: list[dict] = []
    cpus_path = cat_dir / "cpus.json"
    cpus_dir = cat_dir / "cpus"
    if cpus_dir.exists():
        for cpu_file in sorted(cpus_dir.glob("*.json")):
            raw = json.loads(cpu_file.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cpus.append(raw)
    elif cpus_path.exists():
        raw = json.loads(cpus_path.read_text(encoding="utf-8"))
        cpus = raw.get("cpus", raw) if isinstance(raw, dict) else raw

    # Insumos separados por tipo
    insumos: dict[str, list[dict]] = {}
    ins_dir = cat_dir / "insumos"
    if ins_dir.exists():
        for tipo_file in ins_dir.glob("*.json"):
            tipo_key = tipo_file.stem  # ex: "mao_obra"
            raw = json.loads(tipo_file.read_text(encoding="utf-8"))
            items = raw.get("insumos", raw) if isinstance(raw, dict) else raw
            insumos[tipo_key] = items

    # Produtividades
    produtividades: list[dict] = []
    prod_path = cat_dir / "produtividades.json"
    prod_dir = cat_dir / "producoes"
    if prod_dir.exists():
        for prod_file in sorted(prod_dir.glob("*.json")):
            raw = json.loads(prod_file.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                produtividades.append(raw)
    elif prod_path.exists():
        raw = json.loads(prod_path.read_text(encoding="utf-8"))
        produtividades = raw.get("produtividades", raw) if isinstance(raw, dict) else raw

    # Funções — mapeamento canônico funcao_id -> insumo_id (opcional)
    funcoes: list[dict] = []
    func_path = cat_dir / "funcoes.json"
    if func_path.exists():
        raw = json.loads(func_path.read_text(encoding="utf-8"))
        funcoes = raw.get("funcoes", raw) if isinstance(raw, dict) else raw

    return cpus, insumos, produtividades, funcoes


# ── SharePoint backend (ADR-047 §D5) ─────────────────────────────────────────


def _load_sharepoint(
    storage: Any,  # SharePointBlobStorage
    catalog_name: str,
) -> tuple[list[dict], dict[str, list[dict]], list[dict], list[dict]]:
    """Carrega catálogo do SharePoint espelhando a estrutura _load_local_json (ADR-047 §D6)."""
    base = f"config/catalogos/{catalog_name}"

    cpus: list[dict] = []
    cpus_blobs = storage.listar_blobs(f"{base}/cpus")
    if cpus_blobs:
        for blob_path in sorted(cpus_blobs):
            if blob_path.endswith(".json"):
                raw = json.loads(storage.ler_blob(blob_path).decode("utf-8"))
                if isinstance(raw, dict):
                    cpus.append(raw)
    else:
        try:
            raw = json.loads(storage.ler_blob(f"{base}/cpus.json").decode("utf-8"))
            cpus = raw.get("cpus", raw) if isinstance(raw, dict) else raw
        except FileNotFoundError:
            pass

    insumos: dict[str, list[dict]] = {}
    ins_blobs = storage.listar_blobs(f"{base}/insumos")
    for blob_path in ins_blobs:
        if blob_path.endswith(".json"):
            tipo_key = blob_path.rsplit("/", 1)[-1].replace(".json", "")
            raw = json.loads(storage.ler_blob(blob_path).decode("utf-8"))
            items = raw.get("insumos", raw) if isinstance(raw, dict) else raw
            insumos[tipo_key] = items

    produtividades: list[dict] = []
    prod_blobs = storage.listar_blobs(f"{base}/produtividades")
    if prod_blobs:
        for blob_path in sorted(prod_blobs):
            if blob_path.endswith(".json"):
                raw = json.loads(storage.ler_blob(blob_path).decode("utf-8"))
                if isinstance(raw, dict):
                    produtividades.append(raw)
    else:
        try:
            raw = json.loads(storage.ler_blob(f"{base}/produtividades.json").decode("utf-8"))
            produtividades = raw.get("produtividades", raw) if isinstance(raw, dict) else raw
        except FileNotFoundError:
            pass

    funcoes: list[dict] = []
    try:
        raw = json.loads(storage.ler_blob(f"{base}/funcoes.json").decode("utf-8"))
        funcoes = raw.get("funcoes", raw) if isinstance(raw, dict) else raw
    except FileNotFoundError:
        pass

    return cpus, insumos, produtividades, funcoes


# ── Google Sheets backend (stub — implementação futura) ───────────────────────


def _load_google_sheets(
    catalog_name: str,
    spreadsheet_id: str,
    credentials_path: str,
) -> tuple[list[dict], dict[str, list[dict]], list[dict]]:  # pragma: no cover
    """Carrega catálogo de uma planilha Google Sheets (ADR-024 §D1).

    Requer:
        google-auth, google-auth-httplib2, google-auth-oauthlib, google-api-python-client
    Credenciais: arquivo JSON de Service Account em `credentials_path`.
    """
    raise NotImplementedError(
        "Backend GOOGLE_SHEETS não implementado nesta versão. Configure catalog.backend: local_json no concilium.yaml."
    )


# ── CatalogLoader ─────────────────────────────────────────────────────────────


class CatalogLoader:
    """Carrega, cacheia e detecta mudanças no catálogo (ADR-024).

    Uso:
        loader = CatalogLoader(config_root=Path("./config"), project_root=Path("."))
        snapshot, diff = loader.load("mendeslobo", project_id="P-001")
        # diff é None se o catálogo não mudou; CatalogDiff se mudou

    Args:
        config_root:   Raiz das configurações (ex: ./config).
        project_root:  Raiz do projeto — usado para cache local em .concilium/.
        backend:       LOCAL_JSON (padrão) ou GOOGLE_SHEETS.
        ttl_minutes:   TTL do cache em minutos (padrão 60).
        offline:       Se True, usa cache mesmo com TTL expirado; falha se ausente.
        force_refresh: Se True, ignora cache e recarrega sempre.
    """

    def __init__(
        self,
        config_root: Path | str,
        project_root: Path | str | None = None,
        backend: CatalogBackend | str = CatalogBackend.LOCAL_JSON,
        ttl_minutes: int = _DEFAULT_TTL_MINUTES,
        offline: bool = False,
        force_refresh: bool = False,
        sharepoint_storage: Any = None,  # SharePointBlobStorage — injetado quando backend=SHAREPOINT
    ) -> None:
        self.config_root = Path(config_root)
        self.project_root = Path(project_root) if project_root else Path(".")
        self.backend = CatalogBackend(backend)
        self.ttl_minutes = ttl_minutes
        self.offline = offline
        self.force_refresh = force_refresh
        self._sharepoint_storage = sharepoint_storage  # ADR-047 §D5

    @classmethod
    def from_config(
        cls,
        config_root: Path | str,
        project_root: Path | str | None = None,
        offline: bool = False,
        force_refresh: bool = False,
    ) -> CatalogLoader:
        """Constrói CatalogLoader a partir de concilium.yaml (ADR-024 §D4)."""
        import yaml  # lazy — evita cold import desnecessário  # type: ignore[import-untyped]

        yaml_path = Path(config_root) / "concilium.yaml"
        catalog_cfg: dict[str, Any] = {}
        if yaml_path.exists():
            raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            catalog_cfg = raw.get("catalog", {})

        return cls(
            config_root=config_root,
            project_root=project_root,
            backend=CatalogBackend(catalog_cfg.get("backend", "local_json")),
            ttl_minutes=int(catalog_cfg.get("remote_ttl_minutes", _DEFAULT_TTL_MINUTES)),
            offline=offline or bool(catalog_cfg.get("offline_fallback", False)),
            force_refresh=force_refresh,
        )

    def load(
        self,
        catalog_name: str,
        project_id: str | None = None,
        previous_snapshot: CatalogSnapshot | None = None,
    ) -> tuple[CatalogSnapshot, CatalogDiff | None]:
        """Carrega o catálogo, gerenzia cache e computa diff se houver mudança.

        Args:
            catalog_name:      ID do catálogo (ex: "mendeslobo").
            project_id:        ID do projeto (para registrar no meta.project_ids).
            previous_snapshot: Snapshot anterior do mesmo projeto (para diff).

        Returns:
            (CatalogSnapshot, CatalogDiff | None)
            - CatalogDiff é None se o catálogo não mudou ou não há snapshot anterior.
        """
        cached = _read_cache(self.project_root, catalog_name)

        # Decide se precisa buscar dados frescos
        needs_fetch = (
            self.force_refresh or cached is None or (not self.offline and not _cache_is_fresh(cached, self.ttl_minutes))
        )

        if self.offline and cached is None:
            raise FileNotFoundError(
                f"Modo offline: cache ausente para catálogo '{catalog_name}'. "
                f"Execute sem --offline para popular o cache."
            )

        if needs_fetch:
            snapshot = self._fetch_fresh(catalog_name, project_id)
            _write_cache(self.project_root, catalog_name, snapshot)
        else:
            snapshot = cached  # type: ignore[assignment]
            # Adiciona project_id ao snapshot em memória (sem reescrever se já presente)
            if project_id and project_id not in snapshot.meta.project_ids:
                updated_meta = CatalogSnapshotMeta.model_validate(
                    {**snapshot.meta.model_dump(), "project_ids": snapshot.meta.project_ids + [project_id]}
                )
                snapshot = CatalogSnapshot.model_validate({**snapshot.model_dump(), "meta": updated_meta.model_dump()})

        # Diff contra snapshot anterior
        diff: CatalogDiff | None = None
        if previous_snapshot is not None:
            if previous_snapshot.meta.version_hash != snapshot.meta.version_hash:
                diff = compute_catalog_diff(previous_snapshot, snapshot)

        return snapshot, diff

    def _fetch_fresh(self, catalog_name: str, project_id: str | None) -> CatalogSnapshot:
        """Busca dados frescos do backend configurado."""
        funcoes: list[dict] = []
        if self.backend == CatalogBackend.LOCAL_JSON:
            cpus, insumos, produtividades, funcoes = _load_local_json(self.config_root, catalog_name)
        elif self.backend == CatalogBackend.SHAREPOINT:
            if self._sharepoint_storage is None:
                raise ValueError(
                    "CatalogBackend.SHAREPOINT requer sharepoint_storage injetado no CatalogLoader. "
                    "Use CatalogLoader(backend='sharepoint', sharepoint_storage=SharePointBlobStorage.from_env())"
                )
            cpus, insumos, produtividades, funcoes = _load_sharepoint(self._sharepoint_storage, catalog_name)
        elif self.backend == CatalogBackend.GOOGLE_SHEETS:
            import os  # noqa: PLC0415

            creds_path = os.environ.get("CONCILIUM_GOOGLE_CREDENTIALS", "")
            spreadsheet_id = ""  # lido do config yaml
            cpus, insumos, produtividades, _ = _load_google_sheets(catalog_name, spreadsheet_id, creds_path)  # type: ignore[misc]
            funcoes = []
        else:
            raise ValueError(f"Backend desconhecido: {self.backend}")

        return CatalogSnapshot.create(
            catalog_name=catalog_name,
            cpus=cpus,
            insumos=insumos,
            produtividades=produtividades,
            funcoes=funcoes,
            created_by=f"catalog_loader:{self.backend.value}",
            project_id=project_id,
        )
