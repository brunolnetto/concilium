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


def _llj_load_cpus(cat_dir) -> list:
    cpus: list = []
    cpus_dir = cat_dir / "cpus"
    cpus_path = cat_dir / "cpus.json"
    if cpus_dir.exists():
        for cpu_file in sorted(cpus_dir.glob("*.json")):
            raw = json.loads(cpu_file.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cpus.append(raw)
    elif cpus_path.exists():
        raw = json.loads(cpus_path.read_text(encoding="utf-8"))
        cpus = raw.get("cpus", raw) if isinstance(raw, dict) else raw
    return cpus


def _llj_load_insumos(cat_dir) -> dict:
    insumos: dict = {}
    ins_dir = cat_dir / "insumos"
    if ins_dir.exists():
        for tipo_file in ins_dir.glob("*.json"):
            tipo_key = tipo_file.stem
            raw = json.loads(tipo_file.read_text(encoding="utf-8"))
            items = raw.get("insumos", raw) if isinstance(raw, dict) else raw
            insumos[tipo_key] = items
    return insumos


def _llj_load_produtividades(cat_dir) -> list:
    """Carrega arquivos de produtividade/produção do catálogo.

    Ordem de preferência dos layouts de diretório:
      1. produtividades/  — layout novo (CPU-*-PROD-001.json individuais)
      2. producoes/       — layout legado (PROD-*.json individuais)
      3. produtividades.json — arquivo único (fallback)
    """
    for dir_name in ("produtividades", "producoes"):
        prod_dir = cat_dir / dir_name
        if prod_dir.exists():
            produtividades: list = []
            for prod_file in sorted(prod_dir.glob("*.json")):
                raw = json.loads(prod_file.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    produtividades.append(raw)
            return produtividades
    prod_path = cat_dir / "produtividades.json"
    if prod_path.exists():
        raw = json.loads(prod_path.read_text(encoding="utf-8"))
        return raw.get("produtividades", raw) if isinstance(raw, dict) else raw
    return []


def _llj_load_funcoes(cat_dir) -> list:
    funcoes: list = []
    func_path = cat_dir / "funcoes.json"
    if func_path.exists():
        raw = json.loads(func_path.read_text(encoding="utf-8"))
        funcoes = raw.get("funcoes", raw) if isinstance(raw, dict) else raw
    return funcoes


def _load_local_json(
    config_root: Path,
    catalog_name: str,
) -> tuple[list[dict], dict[str, list[dict]], list[dict], list[dict]]:
    """Carrega CPUs, insumos, produtividades e funções.

    Tenta DuckDB primeiro (ADR-100) — 10-700× mais rápido no warm start.
    Recai em leitura JSON pura se DuckDB não estiver disponível ou falhar.
    """
    cat_dir = config_root / "catalogos" / catalog_name
    if not cat_dir.exists():
        raise FileNotFoundError(f"Catálogo '{catalog_name}' não encontrado em {cat_dir}")

    # ── Fast path: DuckDB (ADR-100) ──────────────────────────────────────────
    try:
        from concilium.infrastructure.catalog.query_engine import CatalogQueryEngine
        engine = CatalogQueryEngine(cat_dir)
        if engine.is_ready():
            return (
                engine.load_cpus(),
                engine.load_insumos(),
                engine.load_produtividades(),
                engine.load_funcoes(),
            )
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).debug("DuckDB path falhou, usando JSON puro: %s", _exc)

    # ── Fallback: JSON puro (comportamento original) ─────────────────────────
    cpus = _llj_load_cpus(cat_dir)
    insumos = _llj_load_insumos(cat_dir)
    produtividades = _llj_load_produtividades(cat_dir)
    funcoes = _llj_load_funcoes(cat_dir)
    return cpus, insumos, produtividades, funcoes
def _lsp_load_cpus(storage, base: str) -> list:
    cpus: list = []
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
    return cpus


def _lsp_load_insumos(storage, base: str) -> dict:
    insumos: dict = {}
    ins_blobs = storage.listar_blobs(f"{base}/insumos")
    for blob_path in ins_blobs:
        if blob_path.endswith(".json"):
            tipo_key = blob_path.rsplit("/", 1)[-1].replace(".json", "")
            raw = json.loads(storage.ler_blob(blob_path).decode("utf-8"))
            items = raw.get("insumos", raw) if isinstance(raw, dict) else raw
            insumos[tipo_key] = items
    return insumos


def _lsp_load_produtividades(storage, base: str) -> list:
    produtividades: list = []
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
    return produtividades


def _lsp_load_funcoes(storage, base: str) -> list:
    funcoes: list = []
    try:
        raw = json.loads(storage.ler_blob(f"{base}/funcoes.json").decode("utf-8"))
        funcoes = raw.get("funcoes", raw) if isinstance(raw, dict) else raw
    except FileNotFoundError:
        pass
    return funcoes


def _load_sharepoint(
    storage: Any,  # SharePointBlobStorage
    catalog_name: str,
) -> tuple[list[dict], dict[str, list[dict]], list[dict], list[dict]]:
    """Carrega catálogo do SharePoint espelhando a estrutura _load_local_json (ADR-047 §D6)."""
    base = f"config/catalogos/{catalog_name}"

    cpus = _lsp_load_cpus(storage, base)
    insumos = _lsp_load_insumos(storage, base)
    produtividades = _lsp_load_produtividades(storage, base)
    funcoes = _lsp_load_funcoes(storage, base)
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


def _add_project_id(snapshot: CatalogSnapshot, project_id: str | None) -> CatalogSnapshot:
    if project_id and project_id not in snapshot.meta.project_ids:
        updated_meta = CatalogSnapshotMeta.model_validate(
            {**snapshot.meta.model_dump(), "project_ids": snapshot.meta.project_ids + [project_id]}
        )
        return CatalogSnapshot.model_validate({**snapshot.model_dump(), "meta": updated_meta.model_dump()})
    return snapshot


def _compute_diff_if_changed(previous: CatalogSnapshot | None, current: CatalogSnapshot) -> CatalogDiff | None:
    if previous is None:
        return None
    if previous.meta.version_hash != current.meta.version_hash:
        return compute_catalog_diff(previous, current)
    return None


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
        snapshot = self._resolve_snapshot(catalog_name, project_id, cached)
        diff = _compute_diff_if_changed(previous_snapshot, snapshot)
        return snapshot, diff

    def _resolve_snapshot(
        self, catalog_name: str, project_id: str | None, cached: CatalogSnapshot | None
    ) -> CatalogSnapshot:
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
            return snapshot
        snapshot = cached  # type: ignore[assignment]
        return _add_project_id(snapshot, project_id)

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
            from concilium.infrastructure.settings import get_storage

            creds_path = get_storage().gdrive.google_credentials_path
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
