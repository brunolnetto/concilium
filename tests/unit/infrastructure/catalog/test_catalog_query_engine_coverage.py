"""Unit tests para query_engine.py (CC=13B, coverage 37.4%).

Cobre:
  is_available()
  CatalogQueryEngine.is_ready (duckdb unavailable, _is_stale branches)
  _is_stale (schema mismatch, no timestamp, stale json)
  _cpu_row, _insumo_row, _prod_row, _funcao_row (row builders)
  CatalogSession.__init__ raises ImportError sem duckdb
  CatalogSession.from_resolved com catálogo minimal (se duckdb disponível)
  find_cpus_by_categoria, find_cpus_using_insumo
  get_composicao_com_precos, get_equipe_com_precos
  get_price_stats, query, close, __enter__/__exit__
"""

from __future__ import annotations

import json
import time
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------


class TestIsAvailable:
    def test_reflects_duckdb_presence(self):
        import importlib.util

        from concilium.infrastructure.catalog.query_engine import is_available

        duckdb_present = importlib.util.find_spec("duckdb") is not None
        assert is_available() == duckdb_present


# ---------------------------------------------------------------------------
# Row builders (sem DuckDB)
# ---------------------------------------------------------------------------


class TestRowBuilders:
    def test_cpu_row(self):
        from concilium.infrastructure.catalog.query_engine import _cpu_row

        raw = {"codigo": "CPU-01", "descricao": "Escavação", "categoria": "terraplenagem", "unidade": "m3"}
        row = _cpu_row(raw)
        assert row[0] == "CPU-01"
        assert row[1] == "Escavação"
        assert row[2] == "terraplenagem"
        assert json.loads(row[4]) == raw

    def test_cpu_row_fallback_id(self):
        """codigo ausente → usa 'id'."""
        from concilium.infrastructure.catalog.query_engine import _cpu_row

        raw = {"id": "CPU-02", "descricao": "X", "categoria": "c", "unidade": "u"}
        row = _cpu_row(raw)
        assert row[0] == "CPU-02"

    def test_cpu_row_empty_fields(self):
        from concilium.infrastructure.catalog.query_engine import _cpu_row

        row = _cpu_row({})
        assert row[0] == ""
        assert row[1] == ""

    def test_insumo_row(self):
        from concilium.infrastructure.catalog.query_engine import _insumo_row

        raw = {"id": "INS-01", "descricao": "Óleo"}
        row = _insumo_row(raw, "combustivel")
        assert row[0] == "INS-01"
        assert row[2] == "combustivel"
        assert json.loads(row[3]) == raw

    def test_insumo_row_fallback_codigo(self):
        from concilium.infrastructure.catalog.query_engine import _insumo_row

        raw = {"codigo": "INS-02"}
        row = _insumo_row(raw, "mao_obra")
        assert row[0] == "INS-02"

    def test_prod_row(self):
        from concilium.infrastructure.catalog.query_engine import _prod_row

        raw = {"id": "PROD-01", "cpu_id": "CPU-01"}
        row = _prod_row(raw)
        assert row[0] == "PROD-01"
        assert row[1] == "CPU-01"
        assert json.loads(row[2]) == raw

    def test_prod_row_fallback(self):
        from concilium.infrastructure.catalog.query_engine import _prod_row

        raw = {"producao_id": "PROD-02", "codigo_cpu": "CPU-02"}
        row = _prod_row(raw)
        assert row[0] == "PROD-02"
        assert row[1] == "CPU-02"

    def test_funcao_row(self):
        from concilium.infrastructure.catalog.query_engine import _funcao_row

        raw = {"id": "FN-01", "descricao": "Operador"}
        row = _funcao_row(raw)
        assert row[0] == "FN-01"
        assert row[1] == "Operador"
        assert json.loads(row[2]) == raw


# ---------------------------------------------------------------------------
# CatalogQueryEngine (sem DuckDB obrigatório)
# ---------------------------------------------------------------------------


class TestCatalogQueryEngineNoDuckDB:
    def test_is_ready_when_not_available(self, tmp_path):
        """Quando duckdb não disponível → is_ready() == False."""
        from concilium.infrastructure.catalog import query_engine

        with patch.object(query_engine._engine, "_AVAILABLE", False):
            engine = query_engine.CatalogQueryEngine(tmp_path)
            assert engine.is_ready() is False

    def test_is_stale_no_db_file(self, tmp_path):
        """Sem arquivo .duckdb → _is_stale() == True."""
        from concilium.infrastructure.catalog.query_engine import CatalogQueryEngine

        engine = CatalogQueryEngine(tmp_path)
        assert engine._is_stale() is True

    def test_is_stale_no_timestamp_file(self, tmp_path):
        """Sem arquivo .timestamp → _is_stale() == True."""
        from concilium.infrastructure.catalog.query_engine import CatalogQueryEngine

        engine = CatalogQueryEngine(tmp_path)
        (tmp_path / CatalogQueryEngine.DB_FILENAME).touch()
        assert engine._is_stale() is True

    def test_is_stale_schema_mismatch(self, tmp_path):
        """Schema version diferente → _is_stale() == True."""
        from concilium.infrastructure.catalog.query_engine import CatalogQueryEngine

        engine = CatalogQueryEngine(tmp_path)
        (tmp_path / CatalogQueryEngine.DB_FILENAME).touch()
        ts_path = tmp_path / CatalogQueryEngine.TS_FILENAME
        ts_path.write_text(json.dumps({"schema_ver": "0", "mtime": time.time()}))
        assert engine._is_stale() is True

    def test_is_stale_corrupt_timestamp(self, tmp_path):
        """Timestamp malformado → _is_stale() == True."""
        from concilium.infrastructure.catalog.query_engine import CatalogQueryEngine

        engine = CatalogQueryEngine(tmp_path)
        (tmp_path / CatalogQueryEngine.DB_FILENAME).touch()
        (tmp_path / CatalogQueryEngine.TS_FILENAME).write_text("não json {{{")
        assert engine._is_stale() is True

    def test_is_stale_fresh_cache(self, tmp_path):
        """Cache recém-construído sem JSONs mais novos → _is_stale() == False."""
        from concilium.infrastructure.catalog.query_engine import CatalogQueryEngine

        engine = CatalogQueryEngine(tmp_path)
        (tmp_path / CatalogQueryEngine.DB_FILENAME).touch()
        ts_path = tmp_path / CatalogQueryEngine.TS_FILENAME
        ts_path.write_text(json.dumps({"schema_ver": CatalogQueryEngine.SCHEMA_VER, "mtime": time.time() + 100}))
        # Sem arquivos JSON no diretório
        assert engine._is_stale() is False

    def test_is_stale_stale_json(self, tmp_path):
        """JSON mais novo que cache → _is_stale() == True."""
        from concilium.infrastructure.catalog.query_engine import CatalogQueryEngine

        engine = CatalogQueryEngine(tmp_path)
        (tmp_path / CatalogQueryEngine.DB_FILENAME).touch()
        ts_path = tmp_path / CatalogQueryEngine.TS_FILENAME
        old_time = time.time() - 100
        ts_path.write_text(json.dumps({"schema_ver": CatalogQueryEngine.SCHEMA_VER, "mtime": old_time}))
        # Cria JSON mais novo
        json_file = tmp_path / "cpus.json"
        json_file.write_text("[]")
        assert engine._is_stale() is True

    def test_is_ready_rebuild_fails_returns_false(self, tmp_path):
        """Rebuild falha → is_ready() == False sem crash."""
        from concilium.infrastructure.catalog import query_engine

        with patch.object(query_engine._engine, "_AVAILABLE", True):
            engine = query_engine.CatalogQueryEngine(tmp_path)
            with patch.object(engine, "_rebuild", side_effect=RuntimeError("falha de disco")):
                # _is_stale() == True (sem db) → chama _rebuild → falha → False
                result = engine.is_ready()
            assert result is False

    def test_build_insumos_skips_non_dict_entry_and_continues_loop(self, tmp_path):
        """Layout A (insumos/<tipo>/*.json): um arquivo cujo JSON não é dict é
        pulado, mas o loop continua e processa o próximo arquivo normalmente."""
        duckdb = pytest.importorskip("duckdb")
        from concilium.infrastructure.catalog.query_engine import CatalogQueryEngine

        tipo_dir = tmp_path / "insumos" / "mao_obra"
        tipo_dir.mkdir(parents=True)
        (tipo_dir / "a_lista.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        (tipo_dir / "b_dict.json").write_text(json.dumps({"id": "INS-1", "descricao": "Servente"}), encoding="utf-8")
        engine = CatalogQueryEngine(tmp_path)
        conn = duckdb.connect(":memory:")
        try:
            engine._build_insumos(conn)
            rows = conn.execute("SELECT id FROM insumos").fetchall()
        finally:
            conn.close()
        assert rows == [("INS-1",)]

    def test_build_produtividades_skips_non_dict_entry_and_continues_loop(self, tmp_path):
        """produtividades/*.json: um arquivo cujo JSON não é dict é pulado, mas
        o loop continua e processa o próximo arquivo normalmente."""
        duckdb = pytest.importorskip("duckdb")
        from concilium.infrastructure.catalog.query_engine import CatalogQueryEngine

        prod_dir = tmp_path / "produtividades"
        prod_dir.mkdir()
        (prod_dir / "a_lista.json").write_text(json.dumps(["nao", "e", "dict"]), encoding="utf-8")
        (prod_dir / "b_dict.json").write_text(
            json.dumps({"cpu_id": "CPU-1", "producao_horaria": 5.0}), encoding="utf-8"
        )
        engine = CatalogQueryEngine(tmp_path)
        conn = duckdb.connect(":memory:")
        try:
            engine._build_produtividades(conn)
            rows = conn.execute("SELECT * FROM produtividades").fetchall()
        finally:
            conn.close()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# CatalogSession — sem DuckDB
# ---------------------------------------------------------------------------


class TestCatalogSessionNoDuckDB:
    def test_init_raises_import_error_when_not_available(self):
        """CatalogSession.__init__ levanta ImportError quando duckdb ausente."""
        from concilium.infrastructure.catalog import query_engine

        with patch.object(query_engine._engine, "_AVAILABLE", False):
            with pytest.raises(ImportError, match="duckdb"):
                query_engine.CatalogSession()


# ---------------------------------------------------------------------------
# CatalogSession — com DuckDB (skip se não disponível)
# ---------------------------------------------------------------------------

duckdb = pytest.importorskip("duckdb", reason="duckdb não instalado, pulando testes de CatalogSession")


@pytest.fixture
def minimal_catalogo():
    return {
        "cpus": [
            {
                "codigo": "CPU-01",
                "descricao": "Escavação 3ª cat",
                "categoria": "terraplenagem",
                "unidade": "m3",
                "composicao_itens": [
                    {"insumo_id": "EQ-01", "coeficiente": 1.0, "categoria_custo": "equipamento", "unidade": "h"},
                ],
            }
        ],
        "insumos": {
            "equipamento": [
                {"id": "EQ-01", "descricao": "Escavadeira", "preco_unitario": 200.0},
            ],
            "mao_obra": [
                {"id": "MO-01", "descricao": "Operador", "preco_unitario": 80.0},
            ],
        },
        "produtividades": [
            {
                "id": "PROD-01",
                "cpu_id": "CPU-01",
                "composicao_padrao_equipe": {
                    "funcoes": [{"funcao_id": "MO-01", "num_pessoas": 1, "papel": "direto"}],
                    "equipamentos": [{"equip_id": "EQ-01", "num_unidades": 1, "consumo_litros_hora": 15.0}],
                    "materiais": [],
                },
            }
        ],
    }


class TestCatalogSessionWithDuckDB:
    def test_from_resolved_creates_session(self, minimal_catalogo):
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        session = CatalogSession.from_resolved(minimal_catalogo)
        assert session._loaded is True
        session.close()

    def test_find_cpus_by_categoria(self, minimal_catalogo):
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        with CatalogSession.from_resolved(minimal_catalogo) as session:
            cpus = session.find_cpus_by_categoria("terraplenagem")
        assert len(cpus) == 1
        assert cpus[0]["codigo"] == "CPU-01"

    def test_find_cpus_by_categoria_no_match(self, minimal_catalogo):
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        with CatalogSession.from_resolved(minimal_catalogo) as session:
            cpus = session.find_cpus_by_categoria("pavimentacao")
        assert cpus == []

    def test_find_cpus_using_insumo(self, minimal_catalogo):
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        with CatalogSession.from_resolved(minimal_catalogo) as session:
            cpus = session.find_cpus_using_insumo("EQ-01")
        assert "CPU-01" in cpus

    def test_find_cpus_using_insumo_not_found(self, minimal_catalogo):
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        with CatalogSession.from_resolved(minimal_catalogo) as session:
            cpus = session.find_cpus_using_insumo("INS-INEXISTENTE")
        assert cpus == []

    def test_get_composicao_com_precos(self, minimal_catalogo):
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        with CatalogSession.from_resolved(minimal_catalogo) as session:
            items = session.get_composicao_com_precos("CPU-01")
        assert len(items) == 1
        assert items[0]["insumo_id"] == "EQ-01"
        assert items[0]["coeficiente"] == 1.0

    def test_get_composicao_cpu_not_found(self, minimal_catalogo):
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        with CatalogSession.from_resolved(minimal_catalogo) as session:
            items = session.get_composicao_com_precos("CPU-INEXISTENTE")
        assert items == []

    def test_get_equipe_com_precos(self, minimal_catalogo):
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        with CatalogSession.from_resolved(minimal_catalogo) as session:
            equipe = session.get_equipe_com_precos("PROD-01")
        assert "funcoes" in equipe
        assert "equipamentos" in equipe
        assert "materiais" in equipe
        assert len(equipe["funcoes"]) == 1
        assert len(equipe["equipamentos"]) == 1

    def test_get_equipe_not_found(self, minimal_catalogo):
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        with CatalogSession.from_resolved(minimal_catalogo) as session:
            equipe = session.get_equipe_com_precos("PROD-INEXISTENTE")
        assert equipe["funcoes"] == []
        assert equipe["equipamentos"] == []

    def test_load_with_empty_composicao_and_empty_equipe(self):
        """Covers the false branches of `if comp_rows:` / `if rows:` in _load:
        a CPU with no composicao_itens and a produtividade with no
        funcoes/equipamentos/materiais leave those staging lists empty."""
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        catalogo = {
            "cpus": [{"codigo": "CPU-EMPTY", "descricao": "d", "categoria": "c", "unidade": "u"}],
            "insumos": [],
            "produtividades": [{"id": "PROD-EMPTY", "cpu_id": "CPU-EMPTY", "composicao_padrao_equipe": {}}],
        }
        with CatalogSession.from_resolved(catalogo) as session:
            composicao = session.get_composicao_com_precos("CPU-EMPTY")
            equipe = session.get_equipe_com_precos("PROD-EMPTY")
        assert composicao == []
        assert equipe["funcoes"] == []
        assert equipe["equipamentos"] == []
        assert equipe["materiais"] == []

    def test_get_composicao_com_precos_multi_row_with_missing_insumo(self):
        """Covers the loop back-edge and the `if rec["raw_json"]` false branch:
        one item resolves via LEFT JOIN, the other references a nonexistent
        insumo_id so raw_json comes back NULL."""
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        catalogo = {
            "cpus": [
                {
                    "codigo": "CPU-MULTI",
                    "descricao": "d",
                    "categoria": "c",
                    "unidade": "u",
                    "composicao_itens": [
                        {"insumo_id": "EQ-1", "coeficiente": 1.0, "categoria_custo": "equipamento", "unidade": "h"},
                        {
                            "insumo_id": "INSUMO-INEXISTENTE",
                            "coeficiente": 2.0,
                            "categoria_custo": "material",
                            "unidade": "kg",
                        },
                    ],
                }
            ],
            "insumos": {"equipamento": [{"id": "EQ-1", "descricao": "Escavadeira", "preco_unitario": 100.0}]},
            "produtividades": [],
        }
        with CatalogSession.from_resolved(catalogo) as session:
            items = session.get_composicao_com_precos("CPU-MULTI")
        assert len(items) == 2
        by_id = {i["insumo_id"]: i for i in items}
        assert by_id["EQ-1"]["preco_unitario"] == 100.0
        assert by_id["INSUMO-INEXISTENTE"]["preco_unitario"] is None

    def test_get_equipe_com_precos_multi_row_with_missing_insumo(self):
        """Covers the loop back-edge and falsy-raw_json branch in _parse()
        for get_equipe_com_precos (funcoes with 2 entries, one unresolved)."""
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        catalogo = {
            "cpus": [],
            "insumos": {"mao_obra": [{"id": "MO-1", "descricao": "Operador", "preco_unitario": 50.0}]},
            "produtividades": [
                {
                    "id": "PROD-MULTI",
                    "cpu_id": "CPU-X",
                    "composicao_padrao_equipe": {
                        "funcoes": [
                            {"funcao_id": "MO-1", "num_pessoas": 1, "papel": "direto"},
                            {"funcao_id": "MO-INEXISTENTE", "num_pessoas": 2, "papel": "indireto"},
                        ],
                    },
                }
            ],
        }
        with CatalogSession.from_resolved(catalogo) as session:
            equipe = session.get_equipe_com_precos("PROD-MULTI")
        assert len(equipe["funcoes"]) == 2
        by_id = {f["funcao_id"]: f for f in equipe["funcoes"]}
        assert by_id["MO-1"]["preco_unitario"] == 50.0
        assert by_id["MO-INEXISTENTE"]["preco_unitario"] is None

    def test_load_insumos_flat_list_multiple_entries(self):
        """Covers the loop back-edge on the `elif isinstance(raw_insumos, list)` path."""
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        catalogo = {
            "cpus": [],
            "insumos": [
                {"id": "INS-1", "tipo": "mao_obra", "preco_unitario": 50.0},
                {"id": "INS-2", "tipo": "equipamento", "preco_unitario": 200.0},
            ],
            "produtividades": [],
        }
        with CatalogSession.from_resolved(catalogo) as session:
            stats = session.get_price_stats()
        assert len(stats) == 2

    def test_load_insumos_dict_multiple_entries_per_tipo(self):
        """Covers the inner-loop back-edge for dict-shaped insumos when a single
        tipo has 2+ items (`for i in items or []` at line 526)."""
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        catalogo = {
            "cpus": [],
            "insumos": {
                "mao_obra": [
                    {"id": "MO-1", "descricao": "Op1", "preco_unitario": 50.0},
                    {"id": "MO-2", "descricao": "Op2", "preco_unitario": 60.0},
                ]
            },
            "produtividades": [],
        }
        with CatalogSession.from_resolved(catalogo) as session:
            stats = session.get_price_stats(tipo="mao_obra")
        assert len(stats) == 1
        assert stats[0]["maximo"] == 60.0
        assert stats[0]["minimo"] == 50.0

    def test_get_price_stats_all(self, minimal_catalogo):
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        with CatalogSession.from_resolved(minimal_catalogo) as session:
            stats = session.get_price_stats()
        assert len(stats) > 0
        assert "tipo" in stats[0]
        assert "media" in stats[0]

    def test_get_price_stats_by_tipo(self, minimal_catalogo):
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        with CatalogSession.from_resolved(minimal_catalogo) as session:
            stats = session.get_price_stats(tipo="equipamento")
        assert len(stats) == 1
        assert stats[0]["tipo"] == "equipamento"

    def test_query_ad_hoc(self, minimal_catalogo):
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        with CatalogSession.from_resolved(minimal_catalogo) as session:
            rows = session.query("SELECT COUNT(*) FROM cpus")
        assert rows[0][0] == 1

    def test_context_manager(self, minimal_catalogo):
        """__enter__ / __exit__ funcionam corretamente."""
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        with CatalogSession.from_resolved(minimal_catalogo) as session:
            assert session._loaded is True
        # Após __exit__, close() foi chamado — nova query levanta exceção
        with pytest.raises(Exception):  # noqa: B017
            session.query("SELECT 1")

    def test_get_equipe_com_precos_with_materiais(self):
        """Covers materiais loop body (linha 605) — nunca exercido pelas fixtures existentes."""
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        catalogo = {
            "cpus": [],
            "insumos": {"material": [{"id": "MAT-1", "descricao": "Cimento", "preco_unitario": 30.0}]},
            "produtividades": [
                {
                    "id": "PROD-MAT",
                    "cpu_id": "CPU-X",
                    "composicao_padrao_equipe": {
                        "materiais": [{"insumo_id": "MAT-1", "consumo_por_hora": 2.0, "unidade": "kg"}],
                    },
                }
            ],
        }
        with CatalogSession.from_resolved(catalogo) as session:
            equipe = session.get_equipe_com_precos("PROD-MAT")
        assert len(equipe["materiais"]) == 1
        assert equipe["materiais"][0]["insumo_id"] == "MAT-1"
        assert equipe["materiais"][0]["preco_unitario"] == 30.0

    def test_insumos_dict_with_non_dict_item_skipped(self):
        """Covers `if isinstance(i, dict)` false branch inside dict-shaped insumos loop (527->526)."""
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        catalogo = {
            "cpus": [],
            "insumos": {"mao_obra": ["not-a-dict", {"id": "MO-1", "preco_unitario": 50.0}]},
            "produtividades": [],
        }
        with CatalogSession.from_resolved(catalogo) as session:
            stats = session.get_price_stats(tipo="mao_obra")
        assert len(stats) == 1

    def test_insumos_neither_dict_nor_list_skipped(self):
        """Covers `raw_insumos` sendo nem dict nem list — pula ambos os ramos (529->534)."""
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        catalogo = {"cpus": [], "insumos": None, "produtividades": []}
        with CatalogSession.from_resolved(catalogo) as session:
            stats = session.get_price_stats()
        assert stats == []

    def test_insumos_list_with_non_dict_item_skipped(self):
        """Covers `if isinstance(i, dict)` false branch inside list-shaped insumos loop (531->530)."""
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        catalogo = {
            "cpus": [],
            "insumos": ["not-a-dict", {"id": "INS-1", "tipo": "mao_obra", "preco_unitario": 50.0}],
            "produtividades": [],
        }
        with CatalogSession.from_resolved(catalogo) as session:
            stats = session.get_price_stats(tipo="mao_obra")
        assert len(stats) == 1

    def test_insumos_as_flat_list(self):
        """Catálogo com insumos como lista plana (não dict por tipo)."""
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        catalogo = {
            "cpus": [],
            "insumos": [
                {"id": "INS-1", "tipo": "mao_obra", "preco_unitario": 50.0},
            ],
            "produtividades": [],
        }
        with CatalogSession.from_resolved(catalogo) as session:
            stats = session.get_price_stats(tipo="mao_obra")
        assert len(stats) == 1



# ─── catalog query engine (partial) ──────────────────────────────────────────


class TestCatalogQueryEngine:
    def test_query_engine_initializes(self, tmp_path):
        from concilium.infrastructure.catalog.query_engine import CatalogQueryEngine

        engine = CatalogQueryEngine(catalog_dir=tmp_path)
        assert engine is not None

    def test_query_engine_with_bundle(self, tmp_path):
        from concilium.infrastructure.catalog.query_engine import CatalogQueryEngine

        bundle = {"cpus": [{"codigo": "CPU-1", "descricao": "Terraplenagem"}], "insumos": [], "producoes": []}
        (tmp_path / ".catalog_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
        engine = CatalogQueryEngine(catalog_dir=tmp_path)
        # Test that engine initializes without error; search may need DuckDB
        assert engine is not None



import sys  # noqa: E402
from pathlib import Path  # noqa: E402

from concilium.infrastructure.catalog.query_engine import CatalogQueryEngine, CatalogSession  # noqa: E402

# ─── query engine internals (greatest_gaps_batch1) ──────────────────────────

# ---------------------------------------------------------------------------
# Query engine internals
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self):
        self.executed = []
        self.executed_many = []

    def execute(self, sql, *args):
        self.executed.append((sql, args))
        if "SELECT raw_json FROM cpus" in sql:
            cpu = {
                "codigo": "CPU-1",
                "composicao_itens": [
                    {"insumo_id": "I1", "coeficiente": 2.0, "categoria_custo": "mat", "unidade": "kg"}
                ],
            }
            return _FakeResult([(json.dumps(cpu),)])
        if "SELECT raw_json FROM produtividades" in sql:
            prod = {
                "id": "P1",
                "composicao_padrao_equipe": {
                    "funcoes": [{"funcao_id": "MO-1", "num_pessoas": 2, "papel": "direto"}],
                    "equipamentos": [{"equip_id": "EQ-1", "num_unidades": 1, "consumo_litros_hora": 3.0}],
                    "materiais": [{"insumo_id": "MAT-1", "consumo_por_hora": 4.0, "unidade": "kg"}],
                },
            }
            return _FakeResult([(json.dumps(prod),)])
        return _FakeResult([])

    def executemany(self, sql, rows):
        self.executed_many.append((sql, list(rows)))


class _DuckConn:
    def __init__(self, rows):
        self.rows = rows
        self.closed = False

    def execute(self, _sql):
        return _FakeResult(self.rows)

    def close(self):
        self.closed = True


def test_query_engine_build_methods_tolerate_invalid_json(tmp_path):
    engine = CatalogQueryEngine(tmp_path)
    conn = _FakeConn()

    cpus_dir = tmp_path / "cpus"
    cpus_dir.mkdir(parents=True)
    (cpus_dir / "bad.json").write_text("{invalid")
    (cpus_dir / "list.json").write_text("[]")
    engine._build_cpus(conn)  # exception + non-dict branches

    ins_dir = tmp_path / "insumos"
    ins_dir.mkdir(exist_ok=True)
    (ins_dir / "materiais.json").write_text("{invalid")
    engine._build_insumos(conn)

    (tmp_path / "produtividades.json").write_text("{invalid")
    engine._build_produtividades(conn)

    (tmp_path / "funcoes.json").write_text("{invalid")
    engine._build_funcoes(conn)

    assert any("CREATE TABLE cpus" in sql for sql, _ in conn.executed)
    assert any("CREATE TABLE insumos" in sql for sql, _ in conn.executed)
    assert any("CREATE TABLE produtividades" in sql for sql, _ in conn.executed)
    assert any("CREATE TABLE funcoes" in sql for sql, _ in conn.executed)


def test_query_engine_build_methods_skip_non_dict_list_entries(tmp_path):
    """Layouts de arquivo único (cpus.json, insumos/<tipo>.json, produtividades.json,
    funcoes.json) toleram listas com elementos que não são dict — cobre o ramo
    falso de `if isinstance(raw, dict)` em cada _build_* (só percorrido quando
    NÃO existe o diretório correspondente, i.e. layout de arquivo único)."""
    engine = CatalogQueryEngine(tmp_path)
    conn = _FakeConn()

    (tmp_path / "cpus.json").write_text(json.dumps(["not-a-dict", {"codigo": "CPU-1"}]))
    engine._build_cpus(conn)

    ins_dir = tmp_path / "insumos"
    ins_dir.mkdir(parents=True)
    (ins_dir / "material.json").write_text(json.dumps(["not-a-dict", {"id": "INS-1"}]))
    engine._build_insumos(conn)

    (tmp_path / "produtividades.json").write_text(json.dumps(["not-a-dict", {"id": "PROD-1"}]))
    engine._build_produtividades(conn)

    (tmp_path / "funcoes.json").write_text(json.dumps(["not-a-dict", {"id": "FN-1"}]))
    engine._build_funcoes(conn)

    assert any("INSERT INTO cpus" in sql for sql, _ in conn.executed_many)
    assert any("INSERT INTO insumos" in sql for sql, _ in conn.executed_many)
    assert any("INSERT INTO produtividades" in sql for sql, _ in conn.executed_many)
    assert any("INSERT INTO funcoes" in sql for sql, _ in conn.executed_many)


def test_query_engine_load_table_branches(monkeypatch, tmp_path):
    engine = CatalogQueryEngine(tmp_path)

    # extra_col branch
    dc1 = _DuckConn(rows=[("tipo-a", json.dumps({"id": "x"}))])

    class _Duck1:
        @staticmethod
        def connect(_path, read_only=True):
            return dc1

    monkeypatch.setitem(__import__("sys").modules, "duckdb", _Duck1)
    rows = engine._load_table("insumos", extra_col="tipo")
    assert rows[0]["tipo"] == "tipo-a"
    assert dc1.closed is True

    # non-extra_col branch
    dc2 = _DuckConn(rows=[(json.dumps({"codigo": "CPU-1"}),)])

    class _Duck2:
        @staticmethod
        def connect(_path, read_only=True):
            return dc2

    monkeypatch.setitem(__import__("sys").modules, "duckdb", _Duck2)
    rows2 = engine._load_table("cpus")
    assert rows2[0]["codigo"] == "CPU-1"
    assert dc2.closed is True

# ─── query engine internals (greatest_gaps_batch2) ──────────────────────────

class _FakeResult2:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConn2:
    def __init__(self):
        self.executed: list[str] = []
        self.executed_many: list[tuple[str, list[tuple]]] = []
        self.closed = False
        self.checkpoint_called = False

    def execute(self, sql, *args):
        self.executed.append(str(sql))
        return _FakeResult2([])

    def executemany(self, sql, rows):
        self.executed_many.append((str(sql), list(rows)))

    def checkpoint(self):
        self.checkpoint_called = True

    def close(self):
        self.closed = True

def test_query_engine_rebuild_handles_stale_db_and_writes_timestamp(tmp_path, monkeypatch):
    engine = CatalogQueryEngine(tmp_path)
    # Create directory at DB path so unlink raises OSError and exercises the safe fallback.
    engine._db_path.mkdir(parents=True, exist_ok=True)

    conn = _FakeConn2()

    class _Duckdb:
        @staticmethod
        def connect(_path):
            return conn

    monkeypatch.setitem(sys.modules, "duckdb", _Duckdb)
    monkeypatch.setattr(engine, "_build_cpus", lambda c: c.execute("CREATE CPUS"))
    monkeypatch.setattr(engine, "_build_insumos", lambda c: c.execute("CREATE INSUMOS"))
    monkeypatch.setattr(engine, "_build_produtividades", lambda c: c.execute("CREATE PRODS"))
    monkeypatch.setattr(engine, "_build_funcoes", lambda c: c.execute("CREATE FUNCOES"))

    engine._rebuild()

    assert conn.checkpoint_called is True
    assert conn.closed is True
    assert engine._ts_path.exists()
    payload = json.loads(engine._ts_path.read_text(encoding="utf-8"))
    assert payload["schema_ver"] == CatalogQueryEngine.SCHEMA_VER
    assert "rebuild_ms" in payload


def test_query_engine_build_methods_cover_layout_variants(tmp_path):
    engine = CatalogQueryEngine(tmp_path)
    conn = _FakeConn2()

    # cpus.json fallback layout
    (tmp_path / "cpus.json").write_text(
        json.dumps({"cpus": [{"codigo": "CPU-1", "descricao": "d", "categoria": "c", "unidade": "u"}]}),
        encoding="utf-8",
    )

    # insumos/<tipo>/<ID>.json layout with subdirectory
    tipo_dir = tmp_path / "insumos" / "equipamento"
    tipo_dir.mkdir(parents=True)
    (tipo_dir / "EQ-1.json").write_text(json.dumps({"id": "EQ-1", "descricao": "Escavadeira"}), encoding="utf-8")

    # produtividades from alternate folder name "producoes"
    prods_dir = tmp_path / "producoes"
    prods_dir.mkdir(parents=True)
    (prods_dir / "PROD-1.json").write_text(json.dumps({"id": "PROD-1", "cpu_id": "CPU-1"}), encoding="utf-8")

    # funcoes from funcoes.json
    (tmp_path / "funcoes.json").write_text(
        json.dumps({"funcoes": [{"id": "FN-1", "descricao": "Op"}]}), encoding="utf-8"
    )

    engine._build_cpus(conn)
    engine._build_insumos(conn)
    engine._build_produtividades(conn)
    engine._build_funcoes(conn)

    inserts = "\n".join(sql for sql, _ in conn.executed_many)
    assert "INSERT INTO cpus" in inserts
    assert "INSERT INTO insumos" in inserts
    assert "INSERT INTO produtividades" in inserts
    assert "INSERT INTO funcoes" in inserts


def test_query_engine_wrapper_load_methods(tmp_path, monkeypatch):
    engine = CatalogQueryEngine(tmp_path)

    def _fake_load(table, extra_col=None):
        if table == "cpus":
            return [{"codigo": "CPU-1"}]
        if table == "insumos":
            return [{"tipo": "equipamento", "id": "EQ-1"}, {"id": "GEN-1"}]
        if table == "produtividades":
            return [{"id": "PROD-1"}]
        return [{"id": "FN-1"}]

    monkeypatch.setattr(engine, "_load_table", _fake_load)

    assert engine.load_cpus()[0]["codigo"] == "CPU-1"
    grouped = engine.load_insumos()
    assert grouped["equipamento"][0]["id"] == "EQ-1"
    assert grouped["outros"][0]["id"] == "GEN-1"
    assert engine.load_produtividades()[0]["id"] == "PROD-1"
    assert engine.load_funcoes()[0]["id"] == "FN-1"


def test_query_engine_is_ready_returns_false_when_cache_file_missing(tmp_path, monkeypatch):
    from concilium.infrastructure.catalog import query_engine

    engine = CatalogQueryEngine(tmp_path)
    monkeypatch.setattr(engine, "_is_stale", lambda: False)
    monkeypatch.setattr(query_engine._engine, "_AVAILABLE", True)
    assert engine.is_ready() is False


def test_query_engine_is_stale_ignores_oserror_in_json_stat(tmp_path, monkeypatch):
    engine = CatalogQueryEngine(tmp_path)
    engine._db_path.touch()
    engine._ts_path.write_text(
        json.dumps({"schema_ver": CatalogQueryEngine.SCHEMA_VER, "mtime": 1e20}),
        encoding="utf-8",
    )
    noisy_json = tmp_path / "broken.json"
    noisy_json.write_text("{}", encoding="utf-8")

    original_stat = Path.stat

    def _stat(self, *args, **kwargs):
        if self == noisy_json:
            raise OSError("stat fail")
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", _stat)
    assert engine._is_stale() is False


def test_query_engine_build_cpus_invalid_entries_and_bad_payload(tmp_path):
    engine = CatalogQueryEngine(tmp_path)
    conn = _FakeConn2()

    cpus_dir = tmp_path / "cpus"
    cpus_dir.mkdir(parents=True)
    # Valid JSON but not dict -> no append branch.
    (cpus_dir / "arr.json").write_text("[]", encoding="utf-8")
    # Invalid JSON -> exception branch.
    (cpus_dir / "bad.json").write_text("{", encoding="utf-8")

    engine._build_cpus(conn)
    assert any("CREATE TABLE cpus" in sql for sql in conn.executed)

    # Remove dir to exercise cpus.json fallback exception path.
    for f in cpus_dir.glob("*.json"):
        f.unlink()
    cpus_dir.rmdir()
    (tmp_path / "cpus.json").write_text("{", encoding="utf-8")
    engine._build_cpus(conn)
    assert any("CREATE INDEX idx_cpus_codigo" in sql for sql in conn.executed)


def test_query_engine_build_insumos_edge_paths(tmp_path):
    engine = CatalogQueryEngine(tmp_path)
    conn = _FakeConn2()

    # Layout A with one non-directory entry and one bad json file.
    ins = tmp_path / "insumos"
    ins.mkdir(parents=True)
    (ins / "README.txt").write_text("x", encoding="utf-8")
    tipo = ins / "equipamento"
    tipo.mkdir()
    (tipo / "bad.json").write_text("{", encoding="utf-8")
    engine._build_insumos(conn)

    # Layout B with mixed list entries (non-dict + dict).
    for f in tipo.glob("*.json"):
        f.unlink()
    tipo.rmdir()
    (ins / "equipamento.json").write_text(json.dumps({"insumos": ["bad", {"id": "EQ-1"}]}), encoding="utf-8")
    engine._build_insumos(conn)

    assert any("CREATE TABLE insumos" in sql for sql in conn.executed)


def test_query_engine_build_produtividades_edge_paths(tmp_path):
    engine = CatalogQueryEngine(tmp_path)
    conn = _FakeConn2()

    prod_dir = tmp_path / "produtividades"
    prod_dir.mkdir(parents=True)
    (prod_dir / "bad.json").write_text("{", encoding="utf-8")
    engine._build_produtividades(conn)

    # Fallback single-file path with mixed entries.
    (tmp_path / "produtividades.json").write_text(
        json.dumps({"produtividades": ["bad", {"id": "P1", "cpu_id": "CPU-1"}]}),
        encoding="utf-8",
    )
    # No rows from directory branch after removing the folder.
    for f in prod_dir.glob("*.json"):
        f.unlink()
    prod_dir.rmdir()
    engine._build_produtividades(conn)

    assert any("CREATE TABLE produtividades" in sql for sql in conn.executed)


def test_query_engine_build_cpus_neither_dir_nor_file_exists(tmp_path):
    """Neither cpus/ nor cpus.json present: rows stays empty, both branches of
    the if/elif are skipped entirely (line 257->267 arc)."""
    engine = CatalogQueryEngine(tmp_path)
    conn = _FakeConn2()
    engine._build_cpus(conn)
    assert not any("INSERT INTO cpus" in sql for sql, _ in conn.executed_many)
    assert any("CREATE TABLE cpus" in sql for sql in conn.executed)


def test_query_engine_build_cpus_file_fallback_multiple_entries(tmp_path):
    """cpus.json fallback list with 2+ entries exercises the for-loop back-edge."""
    engine = CatalogQueryEngine(tmp_path)
    conn = _FakeConn2()
    (tmp_path / "cpus.json").write_text(
        json.dumps(
            {
                "cpus": [
                    {"codigo": "CPU-1", "descricao": "d1", "categoria": "c1", "unidade": "u1"},
                    {"codigo": "CPU-2", "descricao": "d2", "categoria": "c2", "unidade": "u2"},
                ]
            }
        ),
        encoding="utf-8",
    )
    engine._build_cpus(conn)
    ((_, rows),) = [pair for pair in conn.executed_many if "INSERT INTO cpus" in pair[0]]
    assert len(rows) == 2


def test_query_engine_build_insumos_multiple_files_in_same_tipo_dir(tmp_path):
    """Two JSON files in the same insumos/<tipo>/ dir exercise the glob loop back-edge."""
    engine = CatalogQueryEngine(tmp_path)
    conn = _FakeConn2()
    tipo_dir = tmp_path / "insumos" / "equipamento"
    tipo_dir.mkdir(parents=True)
    (tipo_dir / "EQ-1.json").write_text(json.dumps({"id": "EQ-1", "descricao": "A"}), encoding="utf-8")
    (tipo_dir / "EQ-2.json").write_text(json.dumps({"id": "EQ-2", "descricao": "B"}), encoding="utf-8")
    engine._build_insumos(conn)
    ((_, rows),) = [pair for pair in conn.executed_many if "INSERT INTO insumos" in pair[0]]
    assert len(rows) == 2


def test_query_engine_build_produtividades_multiple_files_in_dir(tmp_path):
    """Two JSON files in produtividades/ exercise the glob loop back-edge."""
    engine = CatalogQueryEngine(tmp_path)
    conn = _FakeConn2()
    prod_dir = tmp_path / "produtividades"
    prod_dir.mkdir(parents=True)
    (prod_dir / "P1.json").write_text(json.dumps({"id": "P1", "cpu_id": "CPU-1"}), encoding="utf-8")
    (prod_dir / "P2.json").write_text(json.dumps({"id": "P2", "cpu_id": "CPU-2"}), encoding="utf-8")
    engine._build_produtividades(conn)
    ((_, rows),) = [pair for pair in conn.executed_many if "INSERT INTO produtividades" in pair[0]]
    assert len(rows) == 2


def test_query_engine_build_funcoes_file_multiple_entries(tmp_path):
    """funcoes.json list with 2+ entries exercises the for-loop back-edge."""
    engine = CatalogQueryEngine(tmp_path)
    conn = _FakeConn2()
    (tmp_path / "funcoes.json").write_text(
        json.dumps({"funcoes": [{"id": "FN-1", "descricao": "A"}, {"id": "FN-2", "descricao": "B"}]}),
        encoding="utf-8",
    )
    engine._build_funcoes(conn)
    ((_, rows),) = [pair for pair in conn.executed_many if "INSERT INTO funcoes" in pair[0]]
    assert len(rows) == 2


def test_catalog_session_load_material_id_fallback_branch():
    catalogo = {
        "cpus": [
            {
                "codigo": "CPU-1",
                "descricao": "Esc",
                "categoria": "terraplenagem",
                "unidade": "m3",
                "composicao_itens": [],
            }
        ],
        "insumos": {"material": [{"id": "MAT-1", "preco_unitario": 5.0}]},
        "produtividades": [
            {
                "id": "PROD-1",
                "cpu_id": "CPU-1",
                "composicao_padrao_equipe": {
                    "funcoes": [],
                    "equipamentos": [],
                    "materiais": [{"material_id": "MAT-1", "consumo_por_hora": 2.0, "unidade": "kg"}],
                },
            }
        ],
    }
    with CatalogSession.from_resolved(catalogo) as session:
        equipe = session.get_equipe_com_precos("PROD-1")
    assert equipe["materiais"][0]["insumo_id"] == "MAT-1"





# ─── infrastructure/catalog/query_engine.py (88 missing) ─────────────────────


class TestQueryEngine:
    def _catalog(self):
        return {
            "cpus": [
                {"codigo": "CPU-ESC", "descricao": "Escavação de solo", "unidade": "m³", "categoria": "TERRA"},
                {"codigo": "CPU-PAV", "descricao": "Pavimentação asfáltica", "unidade": "m²", "categoria": "PAVE"},
            ],
            "insumos": [
                {
                    "codigo": "INS-DIESEL",
                    "descricao": "Diesel",
                    "tipo": "COMBUSTIVEL",
                    "preco_unitario": 6.5,
                    "unidade": "litro",
                }
            ],
            "producoes": [],
            "funcoes": [],
        }

    def test_catalog_session_from_resolved(self):
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        session = CatalogSession.from_resolved(self._catalog())
        assert session is not None

    def test_catalog_session_find_cpu(self):
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        session = CatalogSession.from_resolved(self._catalog())
        result = session.find_cpus_by_categoria("TERRA")
        assert len(result) >= 1
        assert any(c["codigo"] == "CPU-ESC" for c in result)

    def test_catalog_session_get_composicao_empty(self):
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        session = CatalogSession.from_resolved(self._catalog())
        result = session.get_composicao_com_precos("CPU-MISSING")
        assert result == []

    def test_catalog_session_get_equipe_missing(self):
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        session = CatalogSession.from_resolved(self._catalog())
        result = session.get_equipe_com_precos("PROD-MISSING")
        assert isinstance(result, dict)




# ─── infrastructure/catalog/query_engine.py — CatalogSession deeper paths ─────


class TestCatalogSessionDeeper:
    def _make_session(self):
        from concilium.infrastructure.catalog.query_engine import CatalogSession

        catalog = {
            "cpus": [
                {
                    "codigo": "CPU-ESC",
                    "descricao": "Escavacao hidraulica",
                    "unidade": "m3",
                    "categoria": "TERRA",
                    "producao_id_ref": "PROD-ESC",
                    "composicao_itens": [{"insumo_id": "DIESEL", "coeficiente": 2.0}],
                },
            ],
            "insumos": [
                {
                    "codigo": "DIESEL",
                    "descricao": "Diesel S10",
                    "tipo": "COMBUSTIVEL",
                    "preco_unitario": 6.5,
                    "unidade": "litro",
                },
            ],
            "producoes": [
                {
                    "id": "PROD-ESC",
                    "valor_horario": 50.0,
                    "composicao_padrao_equipe": {
                        "funcoes": [{"funcao_id": "OP", "num_pessoas": 1, "salario_mensal": 3000.0}],
                        "equipamentos": [{"equip_id": "ESC-HIDRA", "num_unidades": 1}],
                    },
                },
            ],
            "funcoes": [
                {"funcao_id": "OP", "descricao": "Operador", "salario_base": 3000.0},
            ],
        }
        return CatalogSession.from_resolved(catalog)

    def test_get_composicao_com_precos(self):
        session = self._make_session()
        result = session.get_composicao_com_precos("CPU-ESC")
        assert isinstance(result, list)

    def test_get_equipe_com_precos(self):
        session = self._make_session()
        result = session.get_equipe_com_precos("PROD-ESC")
        assert isinstance(result, dict)

    def test_find_cpus_by_categoria(self):
        session = self._make_session()
        result = session.find_cpus_by_categoria("TERRA")
        assert len(result) >= 1
        assert result[0]["codigo"] == "CPU-ESC"

    def test_find_cpus_by_categoria_no_match(self):
        session = self._make_session()
        result = session.find_cpus_by_categoria("PAVE")
        assert result == []

    def test_find_cpus_using_insumo(self):
        session = self._make_session()
        result = session.find_cpus_using_insumo("DIESEL")
        assert isinstance(result, list)

    def test_catalog_session_query(self):
        session = self._make_session()
        # query method - check it doesn't raise
        result = session.query("SELECT codigo FROM cpus LIMIT 1")
        assert isinstance(result, list)

    def test_catalog_session_get_price_stats(self):
        session = self._make_session()
        result = session.get_price_stats()
        assert isinstance(result, (dict, list))

