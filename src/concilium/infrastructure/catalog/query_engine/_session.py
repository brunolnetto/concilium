"""DuckDB-backed catalog query engine — ADR-100 — CatalogSession (sessão in-memory por execução de pipeline)."""

from __future__ import annotations

import json
import time
from typing import Any

from . import _engine
from ._loaders_session import (
    _build_composicao_rows,
    _build_equipe_rows,
    _create_junction_tables,
    _load_session_cpus,
    _load_session_insumos,
    _load_session_produtividades,
)


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
        if not _engine._AVAILABLE:
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

        cpu_rows = _load_session_cpus(conn, catalogo)
        ins_rows = _load_session_insumos(conn, catalogo)
        prod_rows = _load_session_produtividades(conn, catalogo)

        # ── Junction tables ───────────────────────────────────────────────────
        comp_rows = _build_composicao_rows(cpu_rows)
        fn_rows, eq_rows, mat_rows = _build_equipe_rows(prod_rows)
        _create_junction_tables(conn, comp_rows, fn_rows, eq_rows, mat_rows)

        self._loaded = True
        elapsed = round((time.perf_counter() - t0) * 1000)
        _engine.logger.debug(
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


