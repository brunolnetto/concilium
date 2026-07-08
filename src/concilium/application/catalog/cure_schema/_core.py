"""Curação do catálogo — parte extraída de cure_schema.py (grupo _core)."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# RefResolver emite deprecation warning no import em jsonschema>=4.18.
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*RefResolver is deprecated.*")

try:
    from jsonschema import Draft202012Validator, RefResolver
except ImportError as _e:
    raise ImportError("Instale jsonschema: uv add jsonschema") from _e

ROOT = Path(__file__).resolve().parents[5]
SCHEMA_ROOT = ROOT / "config" / "schemas" / "catalog"


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))


_SCHEMA_STORE: dict[str, dict] | None = None


def _schema_store() -> dict[str, dict]:
    global _SCHEMA_STORE
    if _SCHEMA_STORE is None:
        _SCHEMA_STORE = {}
        for f in SCHEMA_ROOT.glob("*.schema.json"):
            s = json.loads(f.read_text(encoding="utf-8"))
            if "$id" in s:
                _SCHEMA_STORE[s["$id"]] = s
    return _SCHEMA_STORE


def _make_validator(schema: dict) -> Any:
    # jsonschema não é um pacote PEP 561 tipado — Draft202012Validator é criado
    # dinamicamente via factory em tempo de execução, sem forma estática real.
    base_uri = SCHEMA_ROOT.as_uri() + "/"
    return Draft202012Validator(
        schema,
        resolver=RefResolver(base_uri=base_uri, referrer=schema, store=_schema_store()),
    )


def _validate_all(entities: list[dict], validator: Any, label: str) -> list[str]:
    erros = []
    for ent in entities:
        eid = ent.get("codigo") or ent.get("id") or "<sem-id>"
        for err in validator.iter_errors(ent):
            path = ".".join(str(x) for x in err.absolute_path)
            erros.append(f"{label} {eid}: {path or '<root>'} → {err.message}")
    return erros


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_code(code: str) -> str:
    ascii_code = unicodedata.normalize("NFKD", code).encode("ascii", "ignore").decode("ascii")
    clean = re.sub(r"[^A-Z0-9-]", "-", ascii_code.upper())
    clean = re.sub(r"-+", "-", clean).strip("-")
    if not clean:
        clean = "INSUMO"
    if len(clean) <= 40:
        return clean
    digest = hashlib.sha1(clean.encode("utf-8")).hexdigest()[:6].upper()
    return f"{clean[:33]}-{digest}"[:40]


def _is_valid_insumo_code(code: str) -> bool:
    return bool(re.match(r"^[A-Z0-9-]{3,40}$", code))


def _categoria_custo_from_tipo(tipo: str | None) -> str:
    if tipo == "MAO_OBRA":
        return "MAO_OBRA"
    if tipo == "EQUIPAMENTO":
        return "EQUIPAMENTO"
    if tipo == "TERCEIRIZADO":
        return "MATERIAL"
    return "MATERIAL"


def _team_is_empty(equipe: dict | None) -> bool:
    if not isinstance(equipe, dict):
        return True
    raw_funcoes = equipe.get("funcoes")
    raw_equipamentos = equipe.get("equipamentos")
    funcoes = raw_funcoes if isinstance(raw_funcoes, list) else []
    equipamentos = raw_equipamentos if isinstance(raw_equipamentos, list) else []
    return len(funcoes) == 0 and len(equipamentos) == 0


def _infer_tipo_contrato(insumo: dict) -> str:
    codigo = str(insumo.get("codigo") or "").upper()
    descricao = str(insumo.get("descricao") or "").upper()
    if "-PJ" in codigo or " PJ" in descricao:
        return "PJ"
    return "CLT"


def _q(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    pos = (len(ordered) - 1) * p
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    frac = pos - low
    return ordered[low] * (1 - frac) + ordered[high] * frac


def _iqr_bounds(values: list[float], *, non_negative: bool = False) -> tuple[float, float] | None:
    if len(values) < 8:
        return None
    q1 = _q(values, 0.25)
    q3 = _q(values, 0.75)
    iqr = q3 - q1
    if iqr <= 0:
        return None
    low = q1 - 1.5 * iqr
    high = q3 + 1.5 * iqr
    if non_negative:
        low = max(0.0, low)
        high = max(0.0, high)
    return low, high


def _robust_bounds(values: list[float], *, non_negative: bool = False) -> tuple[float, float] | None:
    if len(values) < 8:
        return None
    ordered = sorted(values)
    q10 = _q(ordered, 0.10)
    q90 = _q(ordered, 0.90)
    iqr = _iqr_bounds(ordered, non_negative=non_negative)
    if iqr is None:
        low, high = q10, q90
    else:
        low, high = iqr
        low = min(low, q10)
        high = max(high, q90)
    if non_negative:
        low = max(0.0, low)
        high = max(0.0, high)
    return low, high


class CurationReport:
    def __init__(self) -> None:
        self.fixed: list[str] = []
        self.manual: list[str] = []
        self.skipped: list[str] = []

    def add_fixed(self, msg: str) -> None:
        self.fixed.append(msg)

    def add_manual(self, msg: str) -> None:
        self.manual.append(msg)

    def add_skipped(self, msg: str) -> None:
        self.skipped.append(msg)


def _index_by_str_key(entities: list[dict], key: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for e in entities:
        if not isinstance(e, dict):
            continue
        e_key = e.get(key)
        if isinstance(e_key, str):
            result[e_key] = e
    return result


def _dedupe_team_items(items: list[dict], id_key: str, qty_key: str) -> list[dict]:
    by_id: dict[str, dict] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item_id = raw.get(id_key)
        if not isinstance(item_id, str) or not item_id:
            continue
        qty = raw.get(qty_key)
        try:
            qty_i = int(qty) if qty is not None else 0
        except Exception:
            qty_i = 0
        if qty_i <= 0:
            continue
        if item_id in by_id:
            by_id[item_id][qty_key] = int(by_id[item_id].get(qty_key) or 0) + qty_i
        else:
            clean = dict(raw)
            clean[qty_key] = qty_i
            by_id[item_id] = clean
    return list(by_id.values())


def _normalize_team(equipe: dict) -> dict:
    normalized = dict(equipe)
    raw_funcoes = equipe.get("funcoes")
    raw_equipamentos = equipe.get("equipamentos")
    funcoes = raw_funcoes if isinstance(raw_funcoes, list) else []
    equipamentos = raw_equipamentos if isinstance(raw_equipamentos, list) else []
    normalized["funcoes"] = _dedupe_team_items(funcoes, "funcao_id", "num_pessoas")
    normalized["equipamentos"] = _dedupe_team_items(equipamentos, "equip_id", "num_unidades")
    return normalized


