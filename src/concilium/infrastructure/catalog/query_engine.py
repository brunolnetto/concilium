"""DuckDB-backed catalog query engine — ADR-100.

Duas classes distintas, dois propósitos:

  CatalogQueryEngine  — file-based, persistente entre execuções.
    Cache .duckdb com junction tables indexadas. Schema v3.
    Responsável pelo fast loading (50-70s → 22ms warm start).

  CatalogSession      — in-memory, por execução de pipeline.
    Recebe o catálogo JÁ RESOLVIDO (com overlays ADR-066 aplicados).
    Expõe SQL joins vetorizados substituindo Python loops em pu_calculator.
    Configura drive-spill via CONCILIUM__DUCKDB_MEMORY / CONCILIUM__DUCKDB_SPILL_DIR
    para catálogos que excedem RAM.

Schema (persistente + in-memory):
  cpus(codigo, descricao, categoria, unidade, producao_id_ref, raw_json)
  insumos(id, descricao, tipo, preco_unitario, raw_json)
  produtividades(id, cpu_id, valor_horario, raw_json)
  funcoes(id, descricao, raw_json)

  -- Junction tables (denormalizadas para JOINs sem parse JSON)
  composicao_itens(cpu_codigo, seq, insumo_id, coeficiente, categoria_custo, unidade)
  equipe_funcoes(prod_id, funcao_id, num_pessoas, papel)
  equipe_equipamentos(prod_id, equip_id, num_unidades, consumo_litros_hora)
  equipe_materiais(prod_id, insumo_id, consumo_por_hora, unidade)
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

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


# ── CatalogQueryEngine ────────────────────────────────────────────────────────


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
        rows: list[tuple[str, str, str, str, str]] = []

        if cpus_dir.exists():
            for f in sorted(cpus_dir.glob("*.json")):
                try:
                    raw = json.loads(f.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        rows.append(_cpu_row(raw))
                except Exception:
                    continue
        elif cpus_file.exists():
            try:
                payload = json.loads(cpus_file.read_text(encoding="utf-8"))
                cpus = payload.get("cpus", payload) if isinstance(payload, dict) else payload
                for raw in cpus or []:
                    if isinstance(raw, dict):
                        rows.append(_cpu_row(raw))
            except Exception:
                pass

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
        rows: list[tuple[str, str, str, str]] = []

        if ins_dir.exists():
            # Layout A: insumos/<tipo>/<ID>.json — cada arquivo é um insumo individual
            has_subdirs = any(d.is_dir() for d in ins_dir.iterdir()) if ins_dir.exists() else False
            if has_subdirs:
                for tipo_dir in sorted(ins_dir.iterdir()):
                    if not tipo_dir.is_dir():
                        continue
                    tipo = tipo_dir.name
                    for f in sorted(tipo_dir.glob("*.json")):
                        try:
                            raw = json.loads(f.read_text(encoding="utf-8"))
                            if isinstance(raw, dict):
                                rows.append(_insumo_row(raw, tipo))
                        except Exception:
                            continue
            else:
                # Layout B: insumos/<tipo>.json — cada arquivo é uma lista por tipo
                for f in sorted(ins_dir.glob("*.json")):
                    tipo = f.stem
                    try:
                        payload = json.loads(f.read_text(encoding="utf-8"))
                        items = payload.get("insumos", payload) if isinstance(payload, dict) else payload
                        for raw in items or []:
                            if isinstance(raw, dict):
                                rows.append(_insumo_row(raw, tipo))
                    except Exception:
                        continue

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
        rows: list[tuple[str, str, str]] = []
        for dir_name in ("produtividades", "producoes"):
            prod_dir = self._dir / dir_name
            if prod_dir.exists():
                for f in sorted(prod_dir.glob("*.json")):
                    try:
                        raw = json.loads(f.read_text(encoding="utf-8"))
                        if isinstance(raw, dict):
                            rows.append(_prod_row(raw))
                    except Exception:
                        continue
                break
        # fallback: arquivo único
        if not rows:
            p = self._dir / "produtividades.json"
            if p.exists():
                try:
                    payload = json.loads(p.read_text(encoding="utf-8"))
                    items = payload.get("produtividades", payload) if isinstance(payload, dict) else payload
                    for raw in items or []:
                        if isinstance(raw, dict):
                            rows.append(_prod_row(raw))
                except Exception:
                    pass

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


# ── Row builders ──────────────────────────────────────────────────────────────


def _cpu_row(raw: dict) -> tuple[str, str, str, str, str]:
    return (
        str(raw.get("codigo") or raw.get("id") or raw.get("cpu_id") or ""),
        str(raw.get("descricao") or ""),
        str(raw.get("categoria") or ""),
        str(raw.get("unidade") or ""),
        json.dumps(raw, ensure_ascii=False),
    )


def _insumo_row(raw: dict, tipo: str) -> tuple[str, str, str, str]:
    return (
        str(raw.get("id") or raw.get("codigo") or ""),
        str(raw.get("descricao") or ""),
        tipo,
        json.dumps(raw, ensure_ascii=False),
    )


def _prod_row(raw: dict) -> tuple[str, str, str]:
    return (
        str(raw.get("id") or raw.get("producao_id") or ""),
        str(raw.get("cpu_id") or raw.get("codigo_cpu") or ""),
        json.dumps(raw, ensure_ascii=False),
    )


def _funcao_row(raw: dict) -> tuple[str, str, str]:
    return (
        str(raw.get("id") or ""),
        str(raw.get("descricao") or ""),
        json.dumps(raw, ensure_ascii=False),
    )


# ── CatalogSession ────────────────────────────────────────────────────────────


class CatalogSession:
    """Sessão DuckDB in-memory para o catálogo resolvido (com overlays ADR-066).

    Uma instância por execução de pipeline. Recebe o dict resolvido de
    _load_resolved_catalogo() e constrói junction tables para substituir
    Python loops por SQL vectorizado.

    Drive-spill automático quando dados excedem CONCILIUM__DUCKDB_MEMORY:
      Datasets maiores que RAM são automaticamente derramados em
      CONCILIUM__DUCKDB_SPILL_DIR (default: tempdir do OS).

    Uso:
        session = CatalogSession.from_resolved(catalogo)
        # substitui loops Python em pu_calculator:
        insumos = session.get_composicao_com_precos("CPU-TERRA-ESC-3CAT")
        equipe  = session.get_equipe_com_precos("PROD-123")
        cpus    = session.find_cpus_by_categoria("terraplenagem")
    """

    def __init__(self) -> None:
        if not _AVAILABLE:
            raise ImportError("duckdb não está instalado. pip install duckdb>=1.0.0")
        import duckdb

        from concilium.infrastructure.settings import get_runtime

        runtime = get_runtime()
        self._conn = duckdb.connect(":memory:")
        # ── Drive-spill config ───────────────────────────────────────────────
        mem_limit = runtime.duckdb_memory
        spill_dir = runtime.duckdb_spill_dir
        self._conn.execute(f"SET memory_limit='{mem_limit}'")
        self._conn.execute(f"SET temp_directory='{spill_dir}'")
        self._conn.execute("SET threads=4")
        self._loaded = False

    @classmethod
    def from_resolved(cls, catalogo: dict[str, Any]) -> CatalogSession:
        """Cria sessão a partir do catálogo resolvido (com overlays aplicados)."""
        session = cls()
        session._load(catalogo)
        return session

    def _load(self, catalogo: dict[str, Any]) -> None:
        """Carrega o catálogo resolvido em tabelas DuckDB in-memory."""
        t0 = time.perf_counter()
        conn = self._conn

        # ── CPUs ──────────────────────────────────────────────────────────────
        cpu_rows = [_cpu_row(c) for c in catalogo.get("cpus", []) if isinstance(c, dict)]
        conn.execute("CREATE TABLE cpus (codigo TEXT, descricao TEXT, categoria TEXT, unidade TEXT, raw_json TEXT)")
        if cpu_rows:
            conn.executemany("INSERT INTO cpus VALUES (?,?,?,?,?)", cpu_rows)
        conn.execute("CREATE INDEX idx_cpus_codigo    ON cpus(codigo)")
        conn.execute("CREATE INDEX idx_cpus_categoria ON cpus(categoria)")

        # ── Insumos (flatten dict[tipo, list] → tabela flat) ──────────────────
        ins_rows: list[tuple] = []
        raw_insumos = catalogo.get("insumos", {})
        if isinstance(raw_insumos, dict):
            for tipo, items in raw_insumos.items():
                for i in items or []:
                    if isinstance(i, dict):
                        ins_rows.append(_insumo_row(i, tipo))
        elif isinstance(raw_insumos, list):
            for i in raw_insumos:
                if isinstance(i, dict):
                    ins_rows.append(_insumo_row(i, str(i.get("tipo") or "outros")))

        conn.execute("CREATE TABLE insumos (id TEXT, descricao TEXT, tipo TEXT, raw_json TEXT)")
        if ins_rows:
            conn.executemany("INSERT INTO insumos VALUES (?,?,?,?)", ins_rows)
        conn.execute("CREATE INDEX idx_ins_id   ON insumos(id)")
        conn.execute("CREATE INDEX idx_ins_tipo ON insumos(tipo)")

        # preco_unitario denormalizado — hot path sem json_extract
        conn.execute("""
            CREATE TABLE insumos_precos AS
            SELECT
                id,
                tipo,
                TRY_CAST(json_extract_string(raw_json, '$.preco_unitario') AS FLOAT)    AS preco_unitario,
                TRY_CAST(json_extract_string(raw_json, '$.atributos_especificos.consumo_litros_hora') AS FLOAT)
                    AS consumo_litros_hora
            FROM insumos
        """)
        conn.execute("CREATE INDEX idx_ip_id ON insumos_precos(id)")

        # ── Produtividades ────────────────────────────────────────────────────
        prod_rows = [_prod_row(p) for p in catalogo.get("produtividades", []) if isinstance(p, dict)]
        conn.execute("CREATE TABLE produtividades (id TEXT, cpu_id TEXT, raw_json TEXT)")
        if prod_rows:
            conn.executemany("INSERT INTO produtividades VALUES (?,?,?)", prod_rows)
        conn.execute("CREATE INDEX idx_prod_id  ON produtividades(id)")
        conn.execute("CREATE INDEX idx_prod_cpu ON produtividades(cpu_id)")

        # ── Junction tables ───────────────────────────────────────────────────
        comp_rows: list[tuple] = []
        fn_rows: list[tuple] = []
        eq_rows: list[tuple] = []
        mat_rows: list[tuple] = []

        for cpu_row in cpu_rows:
            codigo = cpu_row[0]
            cpu = json.loads(cpu_row[4])
            for seq, item in enumerate(cpu.get("composicao_itens") or []):
                comp_rows.append(
                    (
                        codigo,
                        seq,
                        str(item.get("insumo_id") or ""),
                        float(item.get("coeficiente") or 0),
                        str(item.get("categoria_custo") or ""),
                        str(item.get("unidade") or ""),
                    )
                )

        for prod_row in prod_rows:
            pid = prod_row[0]
            prod = json.loads(prod_row[2])
            equipe = prod.get("composicao_padrao_equipe") or {}
            for fn in equipe.get("funcoes") or []:
                fn_rows.append(
                    (
                        pid,
                        str(fn.get("funcao_id") or ""),
                        float(fn.get("num_pessoas") or 1),
                        str(fn.get("papel") or "direto"),
                    )
                )
            for eq in equipe.get("equipamentos") or []:
                eq_rows.append(
                    (
                        pid,
                        str(eq.get("equip_id") or eq.get("equipamento_id") or ""),
                        float(eq.get("num_unidades") or 1),
                        float(eq.get("consumo_litros_hora") or eq.get("consumo_litros_hora_estimado") or 0),
                    )
                )
            for mat in equipe.get("materiais") or []:
                mat_rows.append(
                    (
                        pid,
                        str(mat.get("insumo_id") or mat.get("material_id") or ""),
                        float(mat.get("consumo_por_hora") or 0),
                        str(mat.get("unidade") or ""),
                    )
                )

        conn.execute("""CREATE TABLE composicao_itens
            (cpu_codigo TEXT, seq INT, insumo_id TEXT, coeficiente FLOAT, categoria_custo TEXT, unidade TEXT)""")
        if comp_rows:
            conn.executemany("INSERT INTO composicao_itens VALUES (?,?,?,?,?,?)", comp_rows)
        conn.execute("CREATE INDEX idx_ci_cpu ON composicao_itens(cpu_codigo)")
        conn.execute("CREATE INDEX idx_ci_ins ON composicao_itens(insumo_id)")

        for tbl, cols, rows in [
            ("equipe_funcoes", "prod_id TEXT, funcao_id TEXT, num_pessoas FLOAT, papel TEXT", fn_rows),
            (
                "equipe_equipamentos",
                "prod_id TEXT, equip_id TEXT, num_unidades FLOAT, consumo_litros_hora FLOAT",
                eq_rows,
            ),
            ("equipe_materiais", "prod_id TEXT, insumo_id TEXT, consumo_por_hora FLOAT, unidade TEXT", mat_rows),
        ]:
            conn.execute(f"CREATE TABLE {tbl} ({cols})")
            if rows:
                ph = ",".join(["?"] * len(rows[0]))
                conn.executemany(f"INSERT INTO {tbl} VALUES ({ph})", rows)
            _abbrev = "".join(w[0] for w in tbl.split("_"))  # ef, ee, em — único
            conn.execute(f"CREATE INDEX idx_{_abbrev}_p ON {tbl}(prod_id)")

        self._loaded = True
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.debug(
            "CatalogSession loaded in %dms (%d CPUs, %d insumos, %d prods)",
            elapsed,
            len(cpu_rows),
            len(ins_rows),
            len(prod_rows),
        )

    # ── Queries SQL vectorizadas ──────────────────────────────────────────────

    def get_composicao_com_precos(self, cpu_codigo: str) -> list[dict[str, Any]]:
        """Retorna composicao_itens de uma CPU com preço de cada insumo.

        Substitui o loop Python em pu_calculator.py:121-163.
        """
        rows = self._conn.execute(
            """
            SELECT
                ci.insumo_id,
                ci.coeficiente,
                ci.categoria_custo,
                ci.unidade         AS ci_unidade,
                ip.preco_unitario,
                ip.tipo            AS insumo_tipo,
                i.raw_json
            FROM composicao_itens ci
            LEFT JOIN insumos_precos ip ON ip.id = ci.insumo_id
            LEFT JOIN insumos       i  ON i.id  = ci.insumo_id
            WHERE ci.cpu_codigo = ?
            ORDER BY ci.seq
        """,
            [cpu_codigo],
        ).fetchall()
        cols = [
            "insumo_id",
            "coeficiente",
            "categoria_custo",
            "ci_unidade",
            "preco_unitario",
            "insumo_tipo",
            "raw_json",
        ]
        result = []
        for r in rows:
            rec = dict(zip(cols, r, strict=False))
            if rec["raw_json"]:
                rec.update(json.loads(rec.pop("raw_json")))
            result.append(rec)
        return result

    def get_equipe_com_precos(self, prod_id: str) -> dict[str, Any]:
        """Retorna equipe completa (funcoes + equipamentos + materiais) com preços.

        Substitui os 3 loops Python em pu_calculator.py:166-231.
        """
        funcoes = self._conn.execute(
            """
            SELECT ef.funcao_id, ef.num_pessoas, ef.papel, ip.preco_unitario, i.raw_json
            FROM equipe_funcoes ef
            LEFT JOIN insumos_precos ip ON ip.id = ef.funcao_id
            LEFT JOIN insumos       i  ON i.id  = ef.funcao_id
            WHERE ef.prod_id = ?
        """,
            [prod_id],
        ).fetchall()

        equipamentos = self._conn.execute(
            """
            SELECT ee.equip_id, ee.num_unidades, ee.consumo_litros_hora,
                   ip.preco_unitario,
                   COALESCE(ee.consumo_litros_hora, ip.consumo_litros_hora) AS consumo_efetivo,
                   i.raw_json
            FROM equipe_equipamentos ee
            LEFT JOIN insumos_precos ip ON ip.id = ee.equip_id
            LEFT JOIN insumos       i  ON i.id  = ee.equip_id
            WHERE ee.prod_id = ?
        """,
            [prod_id],
        ).fetchall()

        materiais = self._conn.execute(
            """
            SELECT em.insumo_id, em.consumo_por_hora, em.unidade, ip.preco_unitario, i.raw_json
            FROM equipe_materiais em
            LEFT JOIN insumos_precos ip ON ip.id = em.insumo_id
            LEFT JOIN insumos       i  ON i.id  = em.insumo_id
            WHERE em.prod_id = ?
        """,
            [prod_id],
        ).fetchall()

        def _parse(rows, cols):
            result = []
            for r in rows:
                rec = dict(zip(cols, r, strict=False))
                if rec.get("raw_json"):
                    rec.update(json.loads(rec.pop("raw_json")))
                result.append(rec)
            return result

        return {
            "funcoes": _parse(funcoes, ["funcao_id", "num_pessoas", "papel", "preco_unitario", "raw_json"]),
            "equipamentos": _parse(
                equipamentos,
                ["equip_id", "num_unidades", "consumo_litros_hora", "preco_unitario", "consumo_efetivo", "raw_json"],
            ),
            "materiais": _parse(materiais, ["insumo_id", "consumo_por_hora", "unidade", "preco_unitario", "raw_json"]),
        }

    def find_cpus_by_categoria(self, categoria: str) -> list[dict[str, Any]]:
        """Filter O(log n) via índice em vez de O(n) scan Python."""
        rows = self._conn.execute("SELECT raw_json FROM cpus WHERE categoria = ?", [categoria]).fetchall()
        return [json.loads(r[0]) for r in rows]

    def find_cpus_using_insumo(self, insumo_id: str) -> list[str]:
        """Índice reverso O(log n): quais CPUs usam este insumo."""
        rows = self._conn.execute(
            "SELECT DISTINCT cpu_codigo FROM composicao_itens WHERE insumo_id = ?", [insumo_id]
        ).fetchall()
        return [r[0] for r in rows]

    def get_price_stats(self, tipo: str | None = None) -> list[dict[str, Any]]:
        """Estatísticas de preço por tipo — substitui Python aggregations em plausibility."""
        where = "AND tipo = ?" if tipo else ""
        params = [tipo] if tipo else []
        rows = self._conn.execute(
            f"""
            SELECT
                tipo,
                COUNT(*)                                    AS n,
                AVG(preco_unitario)                         AS media,
                STDDEV_POP(preco_unitario)                  AS desvio,
                MIN(preco_unitario)                         AS minimo,
                MAX(preco_unitario)                         AS maximo,
                PERCENTILE_CONT(0.5) WITHIN GROUP
                    (ORDER BY preco_unitario)               AS mediana
            FROM insumos_precos
            WHERE preco_unitario > 0
            {where}
            GROUP BY tipo
            ORDER BY tipo
        """,
            params,
        ).fetchall()
        cols = ["tipo", "n", "media", "desvio", "minimo", "maximo", "mediana"]
        return [dict(zip(cols, r, strict=False)) for r in rows]

    def query(self, sql: str, params: list | None = None) -> list[tuple]:
        """Acesso direto para queries ad-hoc (skills avançadas, analytics)."""
        return self._conn.execute(sql, params or []).fetchall()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> CatalogSession:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
