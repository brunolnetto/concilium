"""CampaignRunStore — store de execuções de campanha versionadas por projeto.

Cada execução de campanha (run) é um artefato de projeto versionado, seguindo
a estrutura medalhão de entregáveis de execução:

    projetos/{slug}/campaigns/runs/
        run-001/
            inputs/
                campaign_config.json  ← cópia da config usada neste run (bronze)
            outputs/
                bundle.json           ← CampaignOutputBundle (intermediário)
                cube.json             ← CampaignBundleCube (intermediário)
                reports/
                    campaign_report.json  ← relatório final (gold)
                    campaign_report.md    ← relatório legível (gold)
                    campaign_report.pdf   ← entregável PDF (gold)
            meta.json                 ← {campaign_version, gerado_em, status, ...}
        run-002/
            ...
        current                       ← nome do run mais recente

A configuração vive com o run que gerou, não no nível do projeto:
isso garante reprodutibilidade — cada run é auto-contido.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from concilium.domain.repositories.blob_storage_port import BlobStoragePort


class CampaignRunStore:
    """Store de execuções de campanha versionadas, backed by BlobStoragePort.

    Cada chamada a `new_run()` cria um slot `run-NNN/` com
    artefatos imutáveis após finalização.

    Construtores:
        CampaignRunStore(storage, prefix)       — nova API via BlobStoragePort
        CampaignRunStore(project_root=<Path>)   — compat legado (wraps LocalBlobStorage)
        CampaignRunStore(<Path>)                — compat legado posicional
        CampaignRunStore.from_project_root(...)  — compat explícita
    """

    # Estrutura medalhão: inputs/ → outputs/reports/
    CONFIG_FILE   = "inputs/campaign_config.json"
    BUNDLE_FILE   = "outputs/bundle.json"
    CUBE_FILE     = "outputs/cube.json"
    REPORT_JSON   = "outputs/reports/campaign_report.json"
    REPORT_MD     = "outputs/reports/campaign_report.md"
    REPORT_PDF    = "outputs/reports/campaign_report.pdf"
    META_FILE     = "meta.json"
    CURRENT_FILE  = "current"

    def __init__(
        self,
        storage_or_project_root: "BlobStoragePort | Path | None" = None,
        prefix: str | None = None,
        *,
        storage: "BlobStoragePort | None" = None,
        project_root: Path | None = None,
    ) -> None:
        """Construtor flexível para compatibilidade com código legado e nova API.

        Formas suportadas:
            CampaignRunStore(storage_obj, "slug/campaigns")  # nova API posicional
            CampaignRunStore(storage=storage_obj, prefix="..")  # nova API keyword
            CampaignRunStore(Path("/..."))                    # legado posicional
            CampaignRunStore(project_root=Path("/..."))       # legado keyword
        """
        # Resolve storage from positional or keyword arg
        _storage = storage or (storage_or_project_root if isinstance(storage_or_project_root, BlobStoragePort) else None)

        if _storage is not None:
            # New API: storage + prefix
            self._storage = _storage
            self._prefix = (prefix or "campaigns").strip("/")
            # For new-API instances, root is None (backend-agnostic)
            self.root = None  # type: ignore[assignment]
        else:
            # Legacy path-based API
            _path = project_root or storage_or_project_root
            if _path is None:
                raise ValueError("Forneça storage+prefix ou project_root como Path.")
            _path = Path(_path)
            from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage
            # _path is the "project root" (e.g. projetos/AGIS).
            # campaigns live at _path/campaigns/runs/
            # We root the storage at _path.parent so that _path.name/campaigns/... works
            self._storage = LocalBlobStorage(root_dir=_path.parent)
            self._prefix = f"{_path.name}/campaigns"
            # Expose self.root as a Path for backward compat (tests access store.root directly)
            self.root = _path / "campaigns" / "runs"
            self.root.mkdir(parents=True, exist_ok=True)

    # ── Backward-compat classmethod ──────────────────────────────────────────

    @classmethod
    def from_project_root(cls, project_root: Path, slug: str | None = None) -> "CampaignRunStore":
        """Cria store usando LocalBlobStorage enraizado em *project_root*.

        Mantém compatibilidade com código que passa um Path diretamente.

        Args:
            project_root: Raiz do projeto (ex: benchmarks/projetos/AGIS) OU
                          raiz acima do projeto se *slug* for fornecido.
            slug: Slug do projeto. Se fornecido, project_root é tratado como
                  o diretório pai e o prefixo será ``{slug}/campaigns``.
        """
        from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

        if slug:
            root = project_root
            storage = LocalBlobStorage(root_dir=root)
            prefix = f"{slug}/campaigns"
        else:
            storage = LocalBlobStorage(root_dir=project_root.parent)
            prefix = f"{project_root.name}/campaigns"
        inst = cls.__new__(cls)
        inst._storage = storage
        inst._prefix = prefix.strip("/")
        inst.root = None  # type: ignore[assignment]
        return inst

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _runs_prefix(self) -> str:
        return f"{self._prefix}/runs"

    def _run_blob(self, run: str, file: str) -> str:
        return f"{self._prefix}/runs/{run}/{file}"

    def _current_blob(self) -> str:
        return f"{self._prefix}/runs/{self.CURRENT_FILE}"

    def _write_json(self, blob_path: str, data: dict) -> None:
        content = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        self._storage.gravar_blob(blob_path, content.encode("utf-8"))

    def _read_json(self, blob_path: str) -> dict | None:
        if not self._storage.blob_existe(blob_path):
            return None
        data = self._storage.ler_blob(blob_path)
        return json.loads(data.decode("utf-8"))

    # ── Versioning ──────────────────────────────────────────────────────────

    def list_runs(self) -> list[str]:
        """Retorna runs existentes em ordem numérica (run-001, run-002, ...)."""
        blobs = self._storage.listar_blobs(self._runs_prefix())
        runs: set[str] = set()
        runs_prefix = self._runs_prefix() + "/"
        for blob in blobs:
            remainder = blob.removeprefix(runs_prefix)
            # remainder is like "run-001/inputs/campaign_config.json"
            # or just "current"
            first_segment = remainder.split("/")[0]
            if first_segment.startswith("run-") and first_segment != self.CURRENT_FILE:
                runs.add(first_segment)
        return sorted(runs, key=lambda r: int(r.split("-")[1]))

    def current_run(self) -> str | None:
        """Retorna o nome do run mais recente, ou None."""
        cur_blob = self._current_blob()
        if self._storage.blob_existe(cur_blob):
            value = self._storage.ler_blob(cur_blob).decode("utf-8").strip()
            return value or None
        runs = self.list_runs()
        return runs[-1] if runs else None

    def run_path(self, run: str) -> Path:
        """Retorna path do run.

        Para backends filesystem (LocalBlobStorage), retorna o Path real.
        Para outros backends, retorna um Path-like string path lógico.
        """
        from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

        if isinstance(self._storage, LocalBlobStorage):
            return self._storage.root_dir / self._prefix / "runs" / run
        # For non-filesystem backends, return a logical path as Path object
        return Path(self._prefix) / "runs" / run

    def new_run(self) -> str:
        """Cria e registra novo run com estrutura medalhão. Retorna run-NNN."""
        existing = self.list_runs()
        next_num = (max((int(r.split("-")[1]) for r in existing), default=0)) + 1
        run_name = f"run-{next_num:03d}"
        # Initialise structure by writing placeholder sentinel blobs
        # (inputs/ and outputs/reports/ dirs are implied by first writes)
        # We write a sentinel to mark the run as created
        sentinel_path = self._run_blob(run_name, "_init")
        self._storage.gravar_blob(sentinel_path, b"")
        # Write current pointer
        self._storage.gravar_blob(self._current_blob(), run_name.encode("utf-8"))

        # For backward compat with tests that check directory structure:
        # if storage is LocalBlobStorage, also create the dirs
        from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

        if isinstance(self._storage, LocalBlobStorage):
            run_dir = self._storage.root_dir / self._prefix / "runs" / run_name
            (run_dir / "inputs").mkdir(parents=True, exist_ok=True)
            (run_dir / "outputs" / "reports").mkdir(parents=True, exist_ok=True)

        return run_name

    # ── Persistência ────────────────────────────────────────────────────────

    def save_config(self, run: str, config: dict) -> None:
        """Persiste cópia da campaign_config usada neste run (inputs/ — bronze)."""
        self._write_json(self._run_blob(run, self.CONFIG_FILE), config)

    def save_bundle(self, run: str, bundle_dict: dict) -> None:
        """Persiste CampaignOutputBundle serializado."""
        self._write_json(self._run_blob(run, self.BUNDLE_FILE), bundle_dict)

    def save_cube(self, run: str, cube_dict: dict) -> None:
        """Persiste CampaignBundleCube serializado."""
        self._write_json(self._run_blob(run, self.CUBE_FILE), cube_dict)

    def save_report(self, run: str, report_json: dict, md: str, pdf: bytes | None = None) -> None:
        """Persiste os três entregáveis do relatório de campanha."""
        self._write_json(self._run_blob(run, self.REPORT_JSON), report_json)
        self._storage.gravar_blob(
            self._run_blob(run, self.REPORT_MD),
            md.encode("utf-8"),
        )
        if pdf:
            self._storage.gravar_blob(self._run_blob(run, self.REPORT_PDF), pdf)

    def save_meta(self, run: str, meta: dict) -> None:
        """Persiste metadados do run (campaign_version, status, n_avaliados, gerado_em)."""
        if "gerado_em" not in meta:
            meta = {**meta, "gerado_em": datetime.now(timezone.utc).isoformat()}
        self._write_json(self._run_blob(run, self.META_FILE), meta)

    # ── Leitura ─────────────────────────────────────────────────────────────

    def load_bundle(self, run: str | None = None) -> dict | None:
        """Carrega bundle do run especificado (ou current)."""
        r = run or self.current_run()
        if not r:
            return None
        return self._read_json(self._run_blob(r, self.BUNDLE_FILE))

    def load_report_json(self, run: str | None = None) -> dict | None:
        r = run or self.current_run()
        if not r:
            return None
        return self._read_json(self._run_blob(r, self.REPORT_JSON))

    def load_meta(self, run: str | None = None) -> dict | None:
        r = run or self.current_run()
        if not r:
            return None
        return self._read_json(self._run_blob(r, self.META_FILE))

    def load_config(self, run: str | None = None) -> dict | None:
        """Carrega a campaign_config do run."""
        r = run or self.current_run()
        if not r:
            return None
        return self._read_json(self._run_blob(r, self.CONFIG_FILE))

    def list_run_files(self, run: str | None = None) -> list[str]:
        """Lista todos os arquivos do run (percorre subdiretórios da estrutura medalhão)."""
        r = run or self.current_run()
        if not r:
            return []
        run_prefix = f"{self._prefix}/runs/{r}"
        blobs = self._storage.listar_blobs(run_prefix)
        run_prefix_strip = run_prefix + "/"
        result = []
        for blob in blobs:
            rel = blob.removeprefix(run_prefix_strip)
            # Exclude the internal sentinel
            if rel and rel != "_init":
                result.append(rel)
        return sorted(result)
