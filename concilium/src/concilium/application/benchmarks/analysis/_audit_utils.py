"""Utilitários de auditoria. Extraído de audit_six_questions."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

_DEFAULT_ROOT = Path(__file__).resolve().parents[5]
_TOL = 0.05
_REL_TOL = 0.001


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _norm_float(v: Any) -> float:
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def _normalize_project_token(value: str) -> str:
    raw = str(value or "").upper()
    raw = raw.replace("_", " ")
    raw = re.sub(r"\bCALIBRADO\b", "", raw)
    raw = re.sub(r"[^A-Z0-9]+", " ", raw)
    return " ".join(raw.split())


def _get_ref_confronto(ref: dict[str, Any]) -> dict[str, Any]:
    """Retorna o bloco de confronto de referência quando disponível."""
    return (
        ((ref.get("resultado") or {}).get("benchmark_confronto_referencia") or {})
        if isinstance(ref.get("resultado"), dict)
        else {}
    )


def _is_close(ref_val: float, cur_val: float, abs_tol: float = _TOL, rel_tol: float = _REL_TOL) -> bool:
    delta = abs(cur_val - ref_val)
    limit = max(abs_tol, rel_tol * max(abs(ref_val), abs(cur_val), 1.0))
    return delta <= limit


def _sum_dict_counter(entries: list[dict[str, Any]], key_id: str, key_qty: str) -> Counter:
    out: Counter = Counter()
    for row in entries or []:
        key = str(row.get(key_id) or "")
        if not key:
            continue
        out[key] += int(row.get(key_qty) or 0)
    return out


def _as_float(v: Any) -> float:
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def _row_to_pe_entry(row: dict[str, Any]) -> dict[str, Any] | None:
    item_id = row.get("item_id") or row.get("item") or row.get("eap_item")
    if not item_id:
        return None
    custo_fixo = (
        row.get("custo_fixo_equipe") if row.get("custo_fixo_equipe") is not None else row.get("custo_fixo_total")
    )
    custo_venda = row.get("custo_venda_cpu") if row.get("custo_venda_cpu") is not None else row.get("custo_venda")
    delta = row.get("delta")
    if delta is None and custo_venda is not None and custo_fixo is not None:
        delta = _as_float(custo_venda) - _as_float(custo_fixo)
    return {
        "item_id": str(item_id),
        "custo_fixo_equipe": _as_float(custo_fixo),
        "custo_venda_cpu": _as_float(custo_venda),
        "delta": _as_float(delta),
    }


def _extract_pe_from_list_block(rows: Any) -> list[dict[str, Any]] | None:
    if not isinstance(rows, list) or not rows:
        return None
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        entry = _row_to_pe_entry(row)
        if entry:
            out.append(entry)
    return out if out else None


def _build_c_fixo_candidates(pe_block: Any, ref: dict[str, Any]) -> list:
    candidates: list = []
    if isinstance(pe_block, dict):
        candidates.append(pe_block.get("c_fixo"))
        candidates.append(pe_block.get("benchmark_referencia"))
        candidates.append(pe_block.get("benchmark_referencia_itemizado"))
    candidates.append(ref.get("c_fixo"))
    return candidates


def _extract_ref_ponto_equilibrio(ref: dict[str, Any]) -> list[dict[str, Any]]:
    """Extrai ponto de equilíbrio da referência em formatos alternativos.

    Prioridade:
    1) ponto_equilibrio (lista direta com item_id)
    2) ponto_equilibrio.canonical
    3) ponto_equilibrio.c_fixo / c_fixo
    """
    pe_block = ref.get("ponto_equilibrio")

    if isinstance(pe_block, list) and pe_block:
        result = _extract_pe_from_list_block(pe_block)
        if result:
            return result

    if isinstance(pe_block, dict):
        canonical = pe_block.get("canonical")
        if isinstance(canonical, list) and canonical:
            return canonical

    for candidate in _build_c_fixo_candidates(pe_block, ref):
        result = _extract_pe_from_list_block(candidate)
        if result:
            return result

    return []


def _aq_lp_load_meta(meta_path: Path) -> dict | None:
    try:
        return _load_json(meta_path)
    except Exception:
        return None


def _aq_lp_matches_name(nome_meta: str, nome_norm: str, project_name: str, target_norm: str) -> bool:
    return nome_meta == project_name or nome_norm == target_norm or target_norm in nome_norm or nome_norm in target_norm


def _aq_lp_check_dir(d: Path, project_name: str, target_norm: str) -> tuple | None:
    if not d.is_dir():
        return None
    meta = _aq_lp_load_meta(d / "meta.json")
    if meta is None:
        return None
    nome_meta = str(meta.get("nome") or "")
    nome_norm = _normalize_project_token(nome_meta)
    if not _aq_lp_matches_name(nome_meta, nome_norm, project_name, target_norm):
        return None
    return str(meta.get("criado_em") or ""), d


def _latest_project_by_name(project_name: str, projects_root: Path) -> Path | None:
    target_norm = _normalize_project_token(project_name)
    best: tuple[str, Path] | None = None
    for d in projects_root.iterdir():
        result = _aq_lp_check_dir(d, project_name, target_norm)
        if result is None:
            continue
        created, path = result
        if best is None or created > best[0]:
            best = (created, path)
    return best[1] if best else None


def _resolve_canonical_path(extr: dict[str, Any], ref: dict[str, Any], root: Path) -> Path:
    candidate_raw = str(extr.get("paths", {}).get("canonical", "")).strip()
    candidate = Path(candidate_raw) if candidate_raw else None
    if candidate and candidate.exists():
        return candidate

    project_name = str(ref.get("projeto") or (ref.get("meta") or {}).get("projeto") or "")
    if project_name:
        proj = _latest_project_by_name(project_name, root / "projetos")
        if proj:
            can = proj / "v1" / "canonical.json"
            if can.exists():
                return can

    raise FileNotFoundError("canonical.json nÃ£o encontrado para auditoria")
