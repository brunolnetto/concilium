"""Sincroniza `config/calendarios/` (ADR-068) a partir do histórico de
feriados (SCD2 por dia) produzido pelo pipeline `lab/feriados_api`.

Consome o artefato `holiday_history.json` (exportado por
`lab/feriados_api/src/exporters/holiday_history.py::export_json`) — local ou
baixado de blob storage remoto (ex.: SharePoint) — e regenera
`config/calendarios/global.json` (feriados NACIONAL, sempre aplicados) e
`config/calendarios/jurisdicao/BR-{UF}.json` (feriados ESTADUAL, aplicados
apenas a projetos naquela UF). MUNICIPAL é ignorado — o crawler só cobre as
27 capitais, cobertura não-representativa para projetos fora de capital.

fator_operacao de ponto_facultativo NÃO é decidido aqui: sai `None` do
histórico e é resolvido em runtime por skill 04 via
`inputs["observar_pontos_facultativos"]` — binário (parada integral vs dia
normal, sem meio-termo), escolha de configuração de projeto (feita ao gerar
a primeira versão, ajustável entre versões para comparar o efeito), não um
fato do warehouse.

Não depende de duckdb: o artefato de entrada já é JSON puro.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

NIVEIS_CONSUMIDOS = ("NACIONAL", "ESTADUAL")


def _vigente(row: dict[str, Any]) -> bool:
    return row.get("valid_to") in (None, "")


def _evento_id(holiday_key: str, year: int) -> str:
    return f"{holiday_key}-{year}"


def _row_to_evento(row: dict[str, Any]) -> dict[str, Any]:
    is_facultativo = bool(row["is_facultativo"])
    data_iso = row["date"]
    evento: dict[str, Any] = {
        "id": _evento_id(row["holiday_key"], row["year"]),
        "nome": row["name"],
        "tipo": "ponto_facultativo" if is_facultativo else "feriado",
        "inicio": data_iso,
        "fim": data_iso,
        "recorrencia": "unica",
        "fator_operacao": None if is_facultativo else 0.0,
    }
    if row["level"] == "NACIONAL":
        evento["escopo"] = "global"
        evento["jurisdicao_id"] = None
    else:
        evento["escopo"] = "jurisdicao"
        evento["jurisdicao_id"] = f"BR-{row['uf']}"
    return evento


def eventos_por_escopo(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """Filtra para vigentes + NACIONAL/ESTADUAL e agrupa em (nacionais, {uf: eventos})."""
    nacionais: list[dict[str, Any]] = []
    por_uf: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not _vigente(row) or row["level"] not in NIVEIS_CONSUMIDOS:
            continue
        evento = _row_to_evento(row)
        if row["level"] == "NACIONAL":
            nacionais.append(evento)
        else:
            por_uf.setdefault(row["uf"], []).append(evento)
    return nacionais, por_uf


def _merge_eventos(existentes: list[dict[str, Any]], novos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {e["id"]: e for e in existentes if isinstance(e, dict) and e.get("id")}
    for evento in novos:
        by_id[evento["id"]] = evento
    return sorted(by_id.values(), key=lambda e: (e["inicio"], e["id"]))


def _write_eventos(path: Path, eventos: list[dict[str, Any]]) -> int:
    existente: dict[str, Any] = {"versao": "1", "eventos": []}
    if path.exists():
        try:
            carregado = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(carregado, dict):
                existente = carregado
        except Exception:
            pass
    mesclados = _merge_eventos(existente.get("eventos", []), eventos)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"versao": "1", "eventos": mesclados}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(mesclados)


def sync_calendarios_config(
    rows: list[dict[str, Any]],
    config_root: str | Path,
) -> dict[str, int]:
    """Regenera `config/calendarios/` a partir de linhas de `holiday_history.json`.

    Retorna contagem de eventos por arquivo escrito.
    """
    cal_root = Path(config_root) / "calendarios"
    nacionais, por_uf = eventos_por_escopo(rows)

    resultado: dict[str, int] = {}
    if nacionais:
        path = cal_root / "global.json"
        resultado[str(path)] = _write_eventos(path, nacionais)

    for uf, eventos in por_uf.items():
        path = cal_root / "jurisdicao" / f"BR-{uf}.json"
        resultado[str(path)] = _write_eventos(path, eventos)

    return resultado
