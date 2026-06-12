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
import shutil
from datetime import datetime, timezone
from pathlib import Path


class CampaignRunStore:
    """Store de execuções de campanha versionadas.

    Cada chamada a `new_run()` cria um diretório `run-NNN/` com
    artefatos imutáveis após `finalize()`.
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

    def __init__(self, project_root: Path) -> None:
        """
        Args:
            project_root: raiz do projeto (ex: benchmarks/projetos/AGIS).
        """
        self.root = project_root / "campaigns" / "runs"
        self.root.mkdir(parents=True, exist_ok=True)

    # ── Versioning ──────────────────────────────────────────────────────────

    def list_runs(self) -> list[str]:
        """Retorna runs existentes em ordem numérica (run-001, run-002, ...)."""
        return sorted(
            (p.name for p in self.root.iterdir() if p.is_dir() and p.name.startswith("run-")),
            key=lambda r: int(r.split("-")[1]),
        )

    def current_run(self) -> str | None:
        """Retorna o nome do run mais recente, ou None."""
        cur = self.root / self.CURRENT_FILE
        if cur.exists():
            return cur.read_text(encoding="utf-8").strip() or None
        runs = self.list_runs()
        return runs[-1] if runs else None

    def run_path(self, run: str) -> Path:
        return self.root / run

    def new_run(self) -> str:
        """Cria e registra novo run com estrutura medalhão. Retorna run-NNN."""
        existing = self.list_runs()
        next_num = (max((int(r.split("-")[1]) for r in existing), default=0)) + 1
        run_name = f"run-{next_num:03d}"
        run_dir = self.root / run_name
        (run_dir / "inputs").mkdir(parents=True)
        (run_dir / "outputs" / "reports").mkdir(parents=True)
        (self.root / self.CURRENT_FILE).write_text(run_name, encoding="utf-8")
        return run_name

    # ── Persistência ────────────────────────────────────────────────────────

    def save_config(self, run: str, config: dict) -> None:
        """Persiste cópia da campaign_config usada neste run (inputs/ — bronze)."""
        path = self.run_path(run) / self.CONFIG_FILE
        path.write_text(json.dumps(config, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    def save_bundle(self, run: str, bundle_dict: dict) -> None:
        """Persiste CampaignOutputBundle serializado."""
        path = self.run_path(run) / self.BUNDLE_FILE
        path.write_text(json.dumps(bundle_dict, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    def save_cube(self, run: str, cube_dict: dict) -> None:
        """Persiste CampaignBundleCube serializado."""
        path = self.run_path(run) / self.CUBE_FILE
        path.write_text(json.dumps(cube_dict, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    def save_report(self, run: str, report_json: dict, md: str, pdf: bytes | None = None) -> None:
        """Persiste os três entregáveis do relatório de campanha."""
        rdir = self.run_path(run)
        (rdir / self.REPORT_JSON).write_text(
            json.dumps(report_json, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )
        (rdir / self.REPORT_MD).write_text(md, encoding="utf-8")
        if pdf:
            (rdir / self.REPORT_PDF).write_bytes(pdf)

    def save_meta(self, run: str, meta: dict) -> None:
        """Persiste metadados do run (campaign_version, status, n_avaliados, gerado_em)."""
        path = self.run_path(run) / self.META_FILE
        if "gerado_em" not in meta:
            meta = {**meta, "gerado_em": datetime.now(timezone.utc).isoformat()}
        path.write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    # ── Leitura ─────────────────────────────────────────────────────────────

    def load_bundle(self, run: str | None = None) -> dict | None:
        """Carrega bundle do run especificado (ou current)."""
        r = run or self.current_run()
        if not r:
            return None
        p = self.run_path(r) / self.BUNDLE_FILE
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def load_report_json(self, run: str | None = None) -> dict | None:
        r = run or self.current_run()
        if not r:
            return None
        p = self.run_path(r) / self.REPORT_JSON
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def load_meta(self, run: str | None = None) -> dict | None:
        r = run or self.current_run()
        if not r:
            return None
        p = self.run_path(r) / self.META_FILE
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def load_config(self, run: str | None = None) -> dict | None:
        """Carrega a campaign_config do run."""
        r = run or self.current_run()
        if not r:
            return None
        p = self.run_path(r) / self.CONFIG_FILE
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def list_run_files(self, run: str | None = None) -> list[str]:
        """Lista todos os arquivos do run (percorre subdiretórios da estrutura medalhão)."""
        r = run or self.current_run()
        if not r:
            return []
        base = self.run_path(r)
        return sorted(
            str(p.relative_to(base))
            for p in base.rglob("*")
            if p.is_file()
        )
