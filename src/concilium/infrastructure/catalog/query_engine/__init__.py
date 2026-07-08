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

from ._engine import CatalogQueryEngine, is_available
from ._loaders_file import (
    _load_cpu_rows_from_dir,
    _load_cpu_rows_from_file,
    _load_insumo_rows,
    _load_insumo_rows_layout_a,
    _load_insumo_rows_layout_b,
    _load_prod_rows_fallback_file,
    _load_prod_rows_from_dir,
    _load_prod_rows_from_dirs,
)
from ._loaders_session import (
    _build_composicao_rows,
    _build_equipe_rows,
    _create_junction_tables,
    _load_session_cpus,
    _load_session_insumos,
    _load_session_produtividades,
)
from ._rows import _cpu_row, _first_field, _funcao_row, _insumo_row, _prod_row
from ._session import CatalogSession

__all__ = [
    "CatalogQueryEngine",
    "CatalogSession",
    "_build_composicao_rows",
    "_build_equipe_rows",
    "_cpu_row",
    "_create_junction_tables",
    "_first_field",
    "_funcao_row",
    "_insumo_row",
    "_load_cpu_rows_from_dir",
    "_load_cpu_rows_from_file",
    "_load_insumo_rows",
    "_load_insumo_rows_layout_a",
    "_load_insumo_rows_layout_b",
    "_load_prod_rows_fallback_file",
    "_load_prod_rows_from_dir",
    "_load_prod_rows_from_dirs",
    "_load_session_cpus",
    "_load_session_insumos",
    "_load_session_produtividades",
    "_prod_row",
    "is_available",
]
