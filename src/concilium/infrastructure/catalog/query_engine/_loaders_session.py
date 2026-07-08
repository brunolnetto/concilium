"""DuckDB-backed catalog query engine — ADR-100 — carregamento de linhas a partir do catálogo resolvido em memória."""

from __future__ import annotations

import json
from typing import Any

from ._rows import _cpu_row, _first_field, _insumo_row, _prod_row


def _load_session_cpus(conn: Any, catalogo: dict[str, Any]) -> list[tuple]:
    """Cria a tabela `cpus` a partir do catálogo resolvido; retorna as rows inseridas."""
    cpu_rows = [_cpu_row(c) for c in catalogo.get("cpus", []) if isinstance(c, dict)]
    conn.execute("CREATE TABLE cpus (codigo TEXT, descricao TEXT, categoria TEXT, unidade TEXT, raw_json TEXT)")
    if cpu_rows:
        conn.executemany("INSERT INTO cpus VALUES (?,?,?,?,?)", cpu_rows)
    conn.execute("CREATE INDEX idx_cpus_codigo    ON cpus(codigo)")
    conn.execute("CREATE INDEX idx_cpus_categoria ON cpus(categoria)")
    return cpu_rows


def _load_session_insumos(conn: Any, catalogo: dict[str, Any]) -> list[tuple]:
    """Cria as tabelas `insumos` + `insumos_precos` (flatten dict[tipo, list] → tabela flat)."""
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
                ins_rows.append(_insumo_row(i, str(_first_field(i, "tipo", default="outros"))))

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
    return ins_rows


def _load_session_produtividades(conn: Any, catalogo: dict[str, Any]) -> list[tuple]:
    """Cria a tabela `produtividades` a partir do catálogo resolvido; retorna as rows inseridas."""
    prod_rows = [_prod_row(p) for p in catalogo.get("produtividades", []) if isinstance(p, dict)]
    conn.execute("CREATE TABLE produtividades (id TEXT, cpu_id TEXT, raw_json TEXT)")
    if prod_rows:
        conn.executemany("INSERT INTO produtividades VALUES (?,?,?)", prod_rows)
    conn.execute("CREATE INDEX idx_prod_id  ON produtividades(id)")
    conn.execute("CREATE INDEX idx_prod_cpu ON produtividades(cpu_id)")
    return prod_rows


def _build_composicao_rows(cpu_rows: list[tuple]) -> list[tuple]:
    """Expande `composicao_itens` de cada CPU (raw_json) em rows da junction table."""
    comp_rows: list[tuple] = []
    for cpu_row in cpu_rows:
        codigo = cpu_row[0]
        cpu = json.loads(cpu_row[4])
        for seq, item in enumerate(cpu.get("composicao_itens") or []):
            comp_rows.append(
                (
                    codigo,
                    seq,
                    str(_first_field(item, "insumo_id", default="")),
                    float(_first_field(item, "coeficiente", default=0)),
                    str(_first_field(item, "categoria_custo", default="")),
                    str(_first_field(item, "unidade", default="")),
                )
            )
    return comp_rows


def _build_equipe_rows(prod_rows: list[tuple]) -> tuple[list[tuple], list[tuple], list[tuple]]:
    """Expande `composicao_padrao_equipe` de cada produtividade (raw_json) nas 3 junction tables."""
    fn_rows: list[tuple] = []
    eq_rows: list[tuple] = []
    mat_rows: list[tuple] = []
    for prod_row in prod_rows:
        pid = prod_row[0]
        prod = json.loads(prod_row[2])
        equipe = prod.get("composicao_padrao_equipe") or {}
        for fn in equipe.get("funcoes") or []:
            fn_rows.append(
                (
                    pid,
                    str(_first_field(fn, "funcao_id", default="")),
                    float(_first_field(fn, "num_pessoas", default=1)),
                    str(_first_field(fn, "papel", default="direto")),
                )
            )
        for eq in equipe.get("equipamentos") or []:
            eq_rows.append(
                (
                    pid,
                    str(_first_field(eq, "equip_id", "equipamento_id", default="")),
                    float(_first_field(eq, "num_unidades", default=1)),
                    float(_first_field(eq, "consumo_litros_hora", "consumo_litros_hora_estimado", default=0)),
                )
            )
        for mat in equipe.get("materiais") or []:
            mat_rows.append(
                (
                    pid,
                    str(_first_field(mat, "insumo_id", "material_id", default="")),
                    float(_first_field(mat, "consumo_por_hora", default=0)),
                    str(_first_field(mat, "unidade", default="")),
                )
            )
    return fn_rows, eq_rows, mat_rows


def _create_junction_tables(
    conn: Any,
    comp_rows: list[tuple],
    fn_rows: list[tuple],
    eq_rows: list[tuple],
    mat_rows: list[tuple],
) -> None:
    """Cria `composicao_itens` + as 3 tabelas `equipe_*` e insere as rows fornecidas."""
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


