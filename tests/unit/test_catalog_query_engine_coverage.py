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

        with patch.object(query_engine, "_AVAILABLE", False):
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

        with patch.object(query_engine, "_AVAILABLE", True):
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

        with patch.object(query_engine, "_AVAILABLE", False):
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
