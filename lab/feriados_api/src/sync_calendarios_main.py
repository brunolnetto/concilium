"""Sincroniza feriados NACIONAL/ESTADUAL do warehouse local para
`config/calendarios/` do repositório principal (ADR-068), passando por um SCD2
de dia (`holiday_history`, valid_from/valid_to) que historiza mudanças entre
sincronizações — mesmo padrão de `HistoricoPreco` no repositório principal.

Fluxo completo (rodar após um novo crawl, tipicamente 1x/ano):
    1. `holidays` (tabela crua do último crawl) -> upsert em `holiday_history`
       (fecha registros superados, abre os novos/alterados) — feito por este script.
    2. `holiday_history` (vigente) -> `config/calendarios/global.json` +
       `config/calendarios/jurisdicao/BR-{UF}.json` — feito por este script
       (uso local/dev; escreve direto no repo principal via caminho relativo).
    3. `holiday_history` (histórico completo) -> `holiday_history.json` — feito
       por este script (artefato para publicar remotamente).
    4. Publicar remotamente (no repositório principal, fora deste script):
       `concilium ops blob put-versioned holiday_history.json referencia/feriados --backend sharepoint`
    5. Em outro ambiente/máquina, sem re-crawlar (no repositório principal):
       `concilium configuration calendarios sync referencia/feriados/latest.json --backend sharepoint`
       — baixa do SharePoint e regenera config/calendarios/ sem depender deste
       pipeline nem de duckdb (ver `calendario_sync.py`, sem dependência de duckdb).

fator_operacao de ponto_facultativo NÃO é decidido aqui — o evento sai com
fator_operacao=None. Observar ou não (binário: parada integral vs dia normal,
sem meio-termo) é escolha de configuração de projeto, resolvida em runtime
por skill 04 via `inputs["observar_pontos_facultativos"]`.

Uso:
    uv run python -m src.sync_calendarios_main [--config-root PATH]
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import duckdb

from src.exporters.calendario_operacional import export_calendario_operacional
from src.exporters.holiday_history import export_json, sync_holiday_history

DEFAULT_CONFIG_ROOT = Path(__file__).resolve().parents[3] / "config"


def _read_raw_holidays(database: str | Path) -> list[dict]:
    con = duckdb.connect(str(database), read_only=True)
    try:
        rows = con.execute(
            "SELECT holiday_key, year, name, date, level, uf, ibge, is_facultativo, is_bancario FROM holidays"
        ).fetchall()
        cols = [d[0] for d in con.description]
        return [dict(zip(cols, r, strict=True)) for r in rows]
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="holidays.duckdb")
    parser.add_argument("--config-root", default=str(DEFAULT_CONFIG_ROOT))
    parser.add_argument("--history-json", default="holiday_history.json")
    args = parser.parse_args()

    raw_rows = _read_raw_holidays(args.database)
    stats = sync_holiday_history(raw_rows, args.database, date.today())
    print(f"holiday_history: {stats['novos']} novos, {stats['alterados']} alterados, {stats['inalterados']} inalterados")

    n = export_json(args.database, args.history_json)
    print(f"{args.history_json}: {n} registros (histórico completo)")

    resultado = export_calendario_operacional(args.database, args.config_root)
    for path, n_eventos in sorted(resultado.items()):
        print(f"{path}: {n_eventos} eventos")


if __name__ == "__main__":
    main()
