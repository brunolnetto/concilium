"""SCD Type-2 (por dia) para o warehouse local de feriados.

Espelha o padrão já usado em `insumo.py::atualizar_preco()` do repositório
principal (`HistoricoPreco.data_inicio_vigencia`/`data_fim_vigencia`, granularidade
dia) em vez do padrão mensal de `ADR-032`/`versioned.py` — uma correção de feriado
é um evento pontual, não um ciclo mensal.

Chave natural do registro: (holiday_key, year, level, uf, ibge) — holiday_key
por si só NÃO é único por ano: feriados regionais de data fixa (ex. Corpus
Christi) recebem o mesmo slug em ~22 UFs diferentes no mesmo ano, sem sufixo
de desambiguação (o dedup do crawler só distingue por nome, não por UF).
Conteúdo versionado: name, date, is_facultativo, is_bancario. A cada sync:
    - conteúdo igual ao registro aberto (valid_to IS NULL) -> no-op
    - conteúdo diferente (ou chave nova) -> fecha o registro aberto anterior
      (valid_to = hoje) e abre um novo (valid_from = hoje, valid_to = NULL)

Não detecta remoção (chave que existia e não aparece mais no lote atual) —
limitação conhecida: só versiona valores de chaves efetivamente re-crawladas.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

_CONTENT_COLS = ("name", "date", "is_facultativo", "is_bancario")


def _natural_key(row: dict) -> tuple:
    return (row["holiday_key"], row["year"], row["level"], row["uf"], row["ibge"])


def _ensure_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS holiday_history (
            holiday_key VARCHAR,
            year INTEGER,
            name VARCHAR,
            date DATE,
            level VARCHAR,
            uf VARCHAR,
            ibge BIGINT,
            is_facultativo BOOLEAN,
            is_bancario BOOLEAN,
            valid_from DATE,
            valid_to DATE
        )
        """
    )


def _current_by_key(con: duckdb.DuckDBPyConnection) -> dict[tuple, dict]:
    rows = con.execute(
        "SELECT holiday_key, year, name, date, level, uf, ibge, is_facultativo, is_bancario "
        "FROM holiday_history WHERE valid_to IS NULL"
    ).fetchall()
    cols = ["holiday_key", "year", "name", "date", "level", "uf", "ibge", "is_facultativo", "is_bancario"]
    result: dict[tuple, dict] = {}
    for r in rows:
        rec = dict(zip(cols, r, strict=True))
        result[_natural_key(rec)] = rec
    return result


def _content_changed(old: dict, new: dict) -> bool:
    return any(old.get(c) != new.get(c) for c in _CONTENT_COLS)


def _dedupe_incoming(rows: list[dict]) -> list[dict]:
    """Colapsa múltiplas linhas cruas com a mesma chave natural em uma só.

    O crawl bruto tem duplicatas de dado, não de identidade: o mesmo feriado
    NACIONAL às vezes chega com variações de grafia do nome (ex.
    "Quarta-feira de Cinzas" vs "Quarta Feira de Cinzas", uma por capital
    consultada) — sem isso, cada re-sync alternaria qual variante está
    "vigente" e geraria churn de valid_from/valid_to sem nenhuma mudança real.
    Escolhe a grafia menor em ordem alfabética, deterministicamente.
    """
    by_key: dict[tuple, dict] = {}
    for row in rows:
        key = _natural_key(row)
        atual = by_key.get(key)
        if atual is None or row["name"] < atual["name"]:
            by_key[key] = row
    return list(by_key.values())


def sync_holiday_history(
    rows: list[dict],
    database: str | Path,
    today: date,
) -> dict[str, int]:
    """Aplica SCD2 sobre `holiday_history` a partir de `rows` (linhas cruas do
    crawl, mesmas colunas de `holidays`: holiday_key/year/name/date/level/uf/ibge/
    is_facultativo/is_bancario).

    Retorna contagem de {"novos": N, "alterados": N, "inalterados": N}.
    """
    con = duckdb.connect(str(database))
    try:
        _ensure_table(con)
        atuais = _current_by_key(con)

        novos = alterados = inalterados = 0
        fechar: list[tuple] = []
        abrir: list[dict] = []

        for row in _dedupe_incoming(rows):
            key = _natural_key(row)
            atual = atuais.get(key)
            if atual is None:
                novos += 1
                abrir.append(row)
            elif _content_changed(atual, row):
                alterados += 1
                fechar.append(key)
                abrir.append(row)
            else:
                inalterados += 1

        for holiday_key, year, level, uf, ibge in fechar:
            con.execute(
                "UPDATE holiday_history SET valid_to = ? "
                "WHERE holiday_key = ? AND year = ? AND level = ? "
                "AND uf IS NOT DISTINCT FROM ? AND ibge IS NOT DISTINCT FROM ? "
                "AND valid_to IS NULL",
                [today, holiday_key, year, level, uf, ibge],
            )

        if abrir:
            con.executemany(
                "INSERT INTO holiday_history "
                "(holiday_key, year, name, date, level, uf, ibge, is_facultativo, is_bancario, valid_from, valid_to) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                [
                    (
                        r["holiday_key"],
                        r["year"],
                        r["name"],
                        r["date"],
                        r["level"],
                        r["uf"],
                        r["ibge"],
                        r["is_facultativo"],
                        r["is_bancario"],
                        today,
                    )
                    for r in abrir
                ],
            )
        return {"novos": novos, "alterados": alterados, "inalterados": inalterados}
    finally:
        con.close()


def current_rows(database: str | Path) -> list[dict]:
    """Linhas atualmente vigentes (valid_to IS NULL) de `holiday_history`."""
    con = duckdb.connect(str(database), read_only=True)
    try:
        rows = con.execute(
            "SELECT holiday_key, year, name, date, level, uf, ibge, is_facultativo, is_bancario "
            "FROM holiday_history WHERE valid_to IS NULL"
        ).fetchall()
        cols = [d[0] for d in con.description]
        return [dict(zip(cols, r, strict=True)) for r in rows]
    finally:
        con.close()


def export_json(database: str | Path, path: str | Path, *, only_current: bool = False) -> int:
    """Exporta `holiday_history` para JSON (datas como ISO string).

    `only_current=False` (default) exporta o histórico completo, incluindo
    registros fechados — é o artefato publicado remotamente, para auditoria.
    """
    import json

    con = duckdb.connect(str(database), read_only=True)
    try:
        query = "SELECT * FROM holiday_history"
        if only_current:
            query += " WHERE valid_to IS NULL"
        rows = con.execute(query).fetchall()
        cols = [d[0] for d in con.description]
    finally:
        con.close()

    records = []
    for r in rows:
        rec = dict(zip(cols, r, strict=True))
        for date_col in ("date", "valid_from", "valid_to"):
            if rec.get(date_col) is not None:
                rec[date_col] = rec[date_col].isoformat()
        records.append(rec)

    Path(path).write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(records)
