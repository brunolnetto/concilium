"""DuckDB-backed catalog query engine — ADR-100 — CatalogQueryEngine (cache .duckdb persistente)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from ._loaders_file import (
    _load_cpu_rows_from_dir,
    _load_cpu_rows_from_file,
    _load_insumo_rows,
    _load_prod_rows_fallback_file,
    _load_prod_rows_from_dirs,
)
from ._rows import _funcao_row

logger = logging.getLogger(__name__)

# ── Disponibilidade do DuckDB (opcional — sem ele usa JSON puro) ───────────────

try:
    import duckdb as _duckdb  # noqa: F401 — availability probe

    _AVAILABLE = True
except ImportError:  # pragma: no cover
    _AVAILABLE = False


def is_available() -> bool:
    """Retorna True se duckdb está instalado."""
    return _AVAILABLE


class CatalogQueryEngine:
    """Cache DuckDB para catálogo local (ADR-100).

    Uso:
        engine = CatalogQueryEngine(catalog_dir)
        if engine.is_ready():
            cpus = engine.load_cpus()
            insumos = engine.load_insumos()
    """

    DB_FILENAME = "catalog.duckdb"
    TS_FILENAME = "catalog.duckdb.timestamp"
    SCHEMA_VER = "2"  # base tables: cpus, insumos, produtividades, funcoes

    def __init__(self, catalog_dir: Path) -> None:
        self._dir = catalog_dir
        self._db_path = catalog_dir / self.DB_FILENAME
        self._ts_path = catalog_dir / self.TS_FILENAME

    # ── Estado ────────────────────────────────────────────────────────────────

    def is_ready(self) -> bool:
        """True se DuckDB está disponível e o cache está atualizado."""
        if not _AVAILABLE:
            return False
        if self._is_stale():
            try:
                self._rebuild()
            except Exception as exc:
                logger.warning("CatalogQueryEngine rebuild falhou, usando JSON puro: %s", exc)
                return False
        return self._db_path.exists()

    def _is_stale(self) -> bool:
        """True se o cache não existe ou qualquer .json da pasta é mais recente."""
        if not self._db_path.exists() or not self._ts_path.exists():
            return True
        try:
            meta = json.loads(self._ts_path.read_text(encoding="utf-8"))
            if meta.get("schema_ver") != self.SCHEMA_VER:
                return True
            cache_mtime: float = meta["mtime"]
        except Exception:
            return True

        for json_file in self._dir.rglob("*.json"):
            try:
                if json_file.stat().st_mtime > cache_mtime:
                    return True
            except OSError:
                continue
        return False

    # ── Rebuild ───────────────────────────────────────────────────────────────

    def _rebuild(self) -> None:
        """Reconstrói o cache DuckDB a partir dos JSON de origem."""
        t0 = time.perf_counter()
        logger.info("CatalogQueryEngine: iniciando rebuild de '%s'...", self._dir.name)

        import duckdb

        # Remove arquivo corrompido antes de criar novo
        if self._db_path.exists():
            try:
                self._db_path.unlink()
            except OSError:
                pass

        conn = duckdb.connect(str(self._db_path))
        try:
            conn.execute("PRAGMA threads=4")

            self._build_cpus(conn)
            self._build_insumos(conn)
            self._build_produtividades(conn)
            self._build_funcoes(conn)
            # Junction tables são construídas em CatalogSession (in-memory, por execução)
            # — não no cache persistente, para manter rebuild rápido.

            conn.checkpoint()
        finally:
            conn.close()

        elapsed = round((time.perf_counter() - t0) * 1000)
        self._ts_path.write_text(
            json.dumps({"mtime": time.time(), "schema_ver": self.SCHEMA_VER, "rebuild_ms": elapsed}),
            encoding="utf-8",
        )
        logger.info("CatalogQueryEngine: rebuild concluído em %dms.", elapsed)

    def _build_cpus(self, conn: Any) -> None:
        cpus_dir = self._dir / "cpus"
        cpus_file = self._dir / "cpus.json"

        if cpus_dir.exists():
            rows = _load_cpu_rows_from_dir(cpus_dir)
        elif cpus_file.exists():
            rows = _load_cpu_rows_from_file(cpus_file)
        else:
            rows = []

        conn.execute("""
            CREATE TABLE cpus (
                codigo    TEXT,
                descricao TEXT,
                categoria TEXT,
                unidade   TEXT,
                raw_json  TEXT
            )
        """)
        if rows:
            conn.executemany("INSERT INTO cpus VALUES (?, ?, ?, ?, ?)", rows)
        conn.execute("CREATE INDEX idx_cpus_codigo    ON cpus(codigo)")
        conn.execute("CREATE INDEX idx_cpus_categoria ON cpus(categoria)")

    def _build_insumos(self, conn: Any) -> None:
        ins_dir = self._dir / "insumos"
        rows = _load_insumo_rows(ins_dir)

        conn.execute("""
            CREATE TABLE insumos (
                id        TEXT,
                descricao TEXT,
                tipo      TEXT,
                raw_json  TEXT
            )
        """)
        if rows:
            conn.executemany("INSERT INTO insumos VALUES (?, ?, ?, ?)", rows)
        conn.execute("CREATE INDEX idx_insumos_id ON insumos(id)")

    def _build_produtividades(self, conn: Any) -> None:
        rows = _load_prod_rows_from_dirs(self._dir)
        # fallback: arquivo único
        if not rows:
            rows = _load_prod_rows_fallback_file(self._dir / "produtividades.json")

        conn.execute("""
            CREATE TABLE produtividades (
                id       TEXT,
                cpu_id   TEXT,
                raw_json TEXT
            )
        """)
        if rows:
            conn.executemany("INSERT INTO produtividades VALUES (?, ?, ?)", rows)
        conn.execute("CREATE INDEX idx_prod_cpu ON produtividades(cpu_id)")

    def _build_funcoes(self, conn: Any) -> None:
        rows: list[tuple[str, str, str]] = []
        f = self._dir / "funcoes.json"
        if f.exists():
            try:
                payload = json.loads(f.read_text(encoding="utf-8"))
                items = payload.get("funcoes", payload) if isinstance(payload, dict) else payload
                for raw in items or []:
                    if isinstance(raw, dict):
                        rows.append(_funcao_row(raw))
            except Exception:
                pass

        conn.execute("""
            CREATE TABLE funcoes (
                id       TEXT,
                descricao TEXT,
                raw_json TEXT
            )
        """)
        if rows:
            conn.executemany("INSERT INTO funcoes VALUES (?, ?, ?)", rows)

    # ── Leitura ───────────────────────────────────────────────────────────────

    def load_cpus(self) -> list[dict[str, Any]]:
        """Retorna todos os CPUs como list[dict], compatível com _llj_load_cpus."""
        return self._load_table("cpus")

    def load_insumos(self) -> dict[str, list[dict[str, Any]]]:
        """Retorna insumos agrupados por tipo, compatível com _llj_load_insumos."""
        rows = self._load_table("insumos", extra_col="tipo")
        result: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            tipo = row.pop("tipo", "outros")
            result.setdefault(tipo, []).append(row)
        return result

    def load_produtividades(self) -> list[dict[str, Any]]:
        """Retorna produtividades como list[dict]."""
        return self._load_table("produtividades")

    def load_funcoes(self) -> list[dict[str, Any]]:
        """Retorna funções como list[dict]."""
        return self._load_table("funcoes")

    def _load_table(self, table: str, extra_col: str | None = None) -> list[dict[str, Any]]:
        """Abre conexão read-only, lê tabela, reconstrói dicts a partir de raw_json."""
        import duckdb

        conn = duckdb.connect(str(self._db_path), read_only=True)
        try:
            if extra_col:
                rows = conn.execute(f"SELECT {extra_col}, raw_json FROM {table}").fetchall()
                return [{extra_col: r[0], **json.loads(r[1])} for r in rows]
            else:
                rows = conn.execute(f"SELECT raw_json FROM {table}").fetchall()
                return [json.loads(r[0]) for r in rows]
        finally:
            conn.close()


