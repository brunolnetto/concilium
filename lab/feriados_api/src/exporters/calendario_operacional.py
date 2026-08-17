"""Exporta feriados NACIONAL/ESTADUAL do warehouse local para `config/calendarios/`
do repositório principal (ADR-068), no formato consumido por
`ConfigMixin.load_calendario_operacional` (ver
`src/concilium/application/runtime/mixins/config.py`).

MUNICIPAL é intencionalmente ignorado: o crawler só cobre as 27 capitais
(`src/crawler/capitals.py`), então feriados municipais não têm cobertura
representativa para projetos fora de capital — incluí-los criaria um
fator_calendario correto só por acaso, dependendo do município do projeto.

Regra de negócio (fator_operacao):
    is_facultativo=False -> tipo="feriado", fator_operacao=0.0
        (feriado formal, não é um risco variável — dia integralmente parado)
    is_facultativo=True  -> tipo="ponto_facultativo", fator_operacao=None
        (observar ou não é uma escolha binária de configuração do projeto —
        não um fato do warehouse. Sem meio-termo: ou vira parada integral
        (observado, igual a um feriado) ou dia normal (não observado). Feita
        na criação da primeira versão e ajustável entre versões para comparar
        o efeito; resolvida em runtime por skill 04, não aqui — ver
        `inputs["observar_pontos_facultativos"]` em
        `04-cronograma/_skill_helpers/_calendario.py`)

Cada evento recebe recorrencia="unica" com inicio=fim=data: as datas já vêm
resolvidas por ano (inclusive feriados móveis, ex. Sexta-feira Santa), então
"anual" por mês/dia quebraria para esses casos. Re-rodar este exportador para
anos futuros é o mecanismo de atualização — não há regra evergreen aqui.
"""

from __future__ import annotations

import json
from pathlib import Path

from .holiday_history import current_rows

NIVEIS_EXPORTADOS = ("NACIONAL", "ESTADUAL")


def _evento_id(holiday_key: str, year: int) -> str:
    return f"{holiday_key}-{year}"


def _row_to_evento(row: dict) -> dict:
    is_facultativo = bool(row["is_facultativo"])
    data_iso = row["date"].isoformat()
    evento = {
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


def _read_holidays(database: str | Path) -> list[dict]:
    """Lê a view *vigente* do SCD2 (`holiday_history`, valid_to IS NULL) —
    não a tabela `holidays` crua, que é sobrescrita a cada crawl e não tem
    conceito de vigência."""
    return [row for row in current_rows(database) if row["level"] in NIVEIS_EXPORTADOS]


def _merge_eventos(existentes: list[dict], novos: list[dict]) -> list[dict]:
    """Upsert por id — preserva eventos de anos já exportados que não estão neste lote."""
    by_id = {e["id"]: e for e in existentes if isinstance(e, dict) and e.get("id")}
    for evento in novos:
        by_id[evento["id"]] = evento
    return sorted(by_id.values(), key=lambda e: (e["inicio"], e["id"]))


def _write_eventos(path: Path, eventos: list[dict]) -> None:
    existente = {"versao": "1", "eventos": []}
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


def export_calendario_operacional(
    database: str | Path,
    config_root: str | Path,
) -> dict[str, int]:
    """Lê `holidays` (NACIONAL/ESTADUAL) do warehouse local e sincroniza
    `config_root/calendarios/global.json` + `config_root/calendarios/jurisdicao/BR-{UF}.json`.

    Retorna contagem de eventos escritos por arquivo (chave = caminho relativo),
    para o chamador reportar o que foi sincronizado.
    """
    config_root = Path(config_root)
    cal_root = config_root / "calendarios"

    por_uf: dict[str, list[dict]] = {}
    nacionais: list[dict] = []

    for row in _read_holidays(database):
        evento = _row_to_evento(row)
        if row["level"] == "NACIONAL":
            nacionais.append(evento)
        else:
            por_uf.setdefault(row["uf"], []).append(evento)

    resultado: dict[str, int] = {}

    if nacionais:
        path = cal_root / "global.json"
        _write_eventos(path, nacionais)
        resultado[str(path)] = len(json.loads(path.read_text(encoding="utf-8"))["eventos"])

    for uf, eventos in por_uf.items():
        path = cal_root / "jurisdicao" / f"BR-{uf}.json"
        _write_eventos(path, eventos)
        resultado[str(path)] = len(json.loads(path.read_text(encoding="utf-8"))["eventos"])

    return resultado
