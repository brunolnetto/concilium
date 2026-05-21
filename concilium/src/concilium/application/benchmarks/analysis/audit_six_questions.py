"""Auditoria agnÃ³stica de seis perguntas para um benchmark.

ImplementaÃ§Ã£o migrada para cÃ³digo-base e desacoplada de scripts especÃ­ficos.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_DEFAULT_ROOT = Path(__file__).resolve().parents[5]
_TOL = 0.05
_REL_TOL = 0.001  # 0.1%


@dataclass
class Answer:
    pergunta: str
    status: str
    evidencia: dict[str, Any]


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


def _latest_project_by_name(project_name: str, projects_root: Path) -> Path | None:
    target_norm = _normalize_project_token(project_name)
    best: tuple[str, Path] | None = None
    for d in projects_root.iterdir():
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = _load_json(meta_path)
        except Exception:
            continue
        nome_meta = str(meta.get("nome") or "")
        nome_norm = _normalize_project_token(nome_meta)
        if (
            nome_meta != project_name
            and nome_norm != target_norm
            and target_norm not in nome_norm
            and nome_norm not in target_norm
        ):
            continue
        created = str(meta.get("criado_em") or "")
        if best is None or created > best[0]:
            best = (created, d)
    return None if best is None else best[1]


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


def _audit_q1_insumos_equipes(ref: dict[str, Any], cur: dict[str, Any]) -> Answer:
    """Q1: Insumos, CPUs, produtividades e composição de equipes iguais?"""
    ref_eap = ref.get("eap") or (ref.get("cpus") or {}).get("itens_eap") or []
    ref_cpu_map = {str(x.get("item_id")): str(x.get("cpu_id")) for x in ref_eap}
    cur_cpu_map = {str(x.get("item_id")): str(x.get("cpu_id")) for x in cur.get("eap", [])}
    cpus_iguais = ref_cpu_map == cur_cpu_map

    ref_equipes = (
        ref.get("equipes_detalhadas")
        or (ref.get("equipes") or {}).get("detalhes")
        or (ref.get("equipes") or {}).get("equipes")
        or []
    )
    ref_eq_map: dict[str, dict[str, dict[str, int]]] = {}
    for eq in ref_equipes:
        item_id = str(eq.get("item_id") or "")
        if not item_id:
            continue
        ref_eq_map[item_id] = {
            "funcoes": dict(_sum_dict_counter(eq.get("funcoes", []), "funcao_id", "num_pessoas")),
            "equipamentos": dict(_sum_dict_counter(eq.get("equipamentos", []), "equip_id", "num_unidades")),
        }

    cur_eq_map: dict[str, dict[str, dict[str, int]]] = {}
    for eq in cur.get("equipes_diretas", []):
        item_id = str(eq.get("item_id") or "")
        if not item_id:
            continue
        cur_eq_map[item_id] = {
            "funcoes": dict(_sum_dict_counter(eq.get("funcoes", []), "funcao_id", "num_pessoas")),
            "equipamentos": dict(_sum_dict_counter(eq.get("equipamentos", []), "equip_id", "num_unidades")),
        }

    equipes_iguais = ref_eq_map == cur_eq_map
    return Answer(
        pergunta="1) Insumos/CPUs/produtividades/composição de equipes iguais?",
        status="PASSA" if (cpus_iguais and equipes_iguais) else "FALHA",
        evidencia={"cpus_iguais": cpus_iguais, "equipes_iguais": equipes_iguais},
    )


def _resolve_ref_custo_direto(ref_resultado: dict[str, Any], ref_confronto: dict[str, Any]) -> float:
    ref_cd = _norm_float(ref_resultado.get("custo_direto_total"))
    if ref_cd == 0:
        ref_cd = _norm_float((ref_resultado.get("custo") or {}).get("direto_equipes"))
    if ref_cd == 0:
        ref_cd = _norm_float(ref_confronto.get("custo_direto"))
    return ref_cd


def _resolve_cur_custo_direto(cur_res: dict[str, Any]) -> float:
    cur_cd = _norm_float((cur_res.get("custo") or {}).get("direto_catalogo"))
    if cur_cd == 0:
        cur_cd = _norm_float((cur_res.get("custo") or {}).get("direto_equipes"))
    if cur_cd == 0:
        cur_cd = _norm_float(cur_res.get("custo_direto_total_equipes"))
    return cur_cd


def _audit_q2_custo_direto(ref: dict[str, Any], cur: dict[str, Any]) -> Answer:
    """Q2: Custo direto (catálogo vs referência) igual?"""
    ref_resultado = (ref.get("resultado") or {}).get("canonical") or (ref.get("resultado") or {})
    ref_confronto = _get_ref_confronto(ref)
    ref_cd = _resolve_ref_custo_direto(ref_resultado, ref_confronto)
    cur_cd = _resolve_cur_custo_direto(cur.get("resultado") or {})
    delta_cd = round(cur_cd - ref_cd, 2)
    return Answer(
        pergunta="2) Custo direto (catálogo vs referência) igual?",
        status="PASSA" if _is_close(ref_cd, cur_cd) else "FALHA",
        evidencia={"ref": ref_cd, "concilium_catalogo": cur_cd, "delta": delta_cd},
    )


def _extract_ref_item_subtotal(i: dict[str, Any]) -> float:
    subtotal = (i.get("subtotal_com_bdi") or {}).get("total")
    if subtotal is None:
        subtotal = ((i.get("subtotal") or {}).get("com_bdi") or {}).get("total")
    if subtotal is None:
        tp = i.get("total_projeto") or {}
        subtotal = (
            _norm_float(tp.get("servicos"))
            + _norm_float(tp.get("material"))
            + _norm_float(tp.get("diesel"))
            + _norm_float(tp.get("mo"))
        )
        if subtotal == 0:
            subtotal = _norm_float(i.get("custo_unit_sbdi")) * _norm_float(i.get("quantitativo"))
    return _norm_float(subtotal)


def _audit_q3_orcamento(ref: dict[str, Any], cur: dict[str, Any]) -> Answer:
    """Q3: Orçamento de itens calculado corretamente?"""
    ref_planejamento = ref.get("planejamento_detalhado") or (ref.get("planejamento") or {}).get("itens") or []
    if not ref_planejamento:
        ref_planejamento = (ref.get("cpus") or {}).get("itens_eap") or []
    ref_items = {str(i.get("item_id")): _extract_ref_item_subtotal(i) for i in ref_planejamento}
    cur_items = {
        str(i.get("item_id")): _norm_float(((i.get("subtotal") or {}).get("sem_bdi") or {}).get("total"))
        for i in cur.get("planejamento", [])
    }
    item_deltas = {k: round(cur_items.get(k, 0.0) - v, 2) for k, v in ref_items.items()}
    ok_items = (
        all(_is_close(ref_items.get(k, 0.0), cur_items.get(k, 0.0)) for k in item_deltas) if item_deltas else False
    )
    return Answer(
        pergunta="3) Orçamento de itens está correto?",
        status="N/A" if not item_deltas else ("PASSA" if ok_items else "FALHA"),
        evidencia={"itens": item_deltas, "qtd_itens": len(item_deltas)},
    )


def _resolve_ref_indireto(ref_resultado: dict[str, Any], ref_confronto: dict[str, Any]) -> float:
    ref_ind = _norm_float(ref_confronto.get("custo_indireto"))
    if ref_ind == 0:
        ref_ind = _norm_float(ref_resultado.get("custo_indireto_total"))
    if ref_ind == 0:
        ref_ind = _norm_float(
            sum(v for k, v in (ref_resultado.get("custo") or {}).items() if str(k).startswith("indireto_"))
        )
    return ref_ind


def _audit_q4_indiretos(ref: dict[str, Any], cur: dict[str, Any]) -> Answer:
    """Q4: Indiretos aplicados corretamente?"""
    ref_resultado = (ref.get("resultado") or {}).get("canonical") or (ref.get("resultado") or {})
    ref_confronto = _get_ref_confronto(ref)
    ref_ind = _resolve_ref_indireto(ref_resultado, ref_confronto)
    cur_ind = _norm_float((cur.get("resultado") or {}).get("custo_indireto_total"))
    if cur_ind == 0:
        cur_ind = _norm_float(
            sum(
                v
                for k, v in (((cur.get("resultado") or {}).get("custo") or {}).items())
                if str(k).startswith("indireto_")
            )
        )
    delta_ind = round(cur_ind - ref_ind, 2)
    return Answer(
        pergunta="4) Indiretos aplicados corretamente?",
        status="PASSA" if _is_close(ref_ind, cur_ind) else "FALHA",
        evidencia={"ref": ref_ind, "concilium": cur_ind, "delta": delta_ind},
    )


def _build_pe_mismatch(ref_pe: dict, cur_pe: dict) -> dict[str, Any]:
    pe_mismatch: dict[str, Any] = {}
    for item_id in sorted(set(ref_pe) & set(cur_pe)):
        deltas = {}
        for key in ("custo_fixo_equipe", "custo_venda_cpu", "delta"):
            rv = _norm_float(ref_pe[item_id].get(key))
            cv = _norm_float(cur_pe[item_id].get(key))
            d = round(cv - rv, 2)
            if abs(d) > _TOL:
                deltas[key] = d
        if deltas:
            pe_mismatch[item_id] = deltas
    return pe_mismatch


def _audit_q5_ponto_equilibrio(ref: dict[str, Any], cur: dict[str, Any]) -> Answer:
    """Q5: Ponto de equilíbrio por EAP coincide?"""
    ref_pe_src = _extract_ref_ponto_equilibrio(ref)
    ref_pe = {str(i.get("item_id")): i for i in (ref_pe_src or []) if i.get("item_id")}
    cur_pe = {str(i.get("item_id")): i for i in (cur.get("ponto_equilibrio") or []) if i.get("item_id")}
    if not ref_pe:
        return Answer(
            pergunta="5) Ponto de equilíbrio por EAP coincide?",
            status="N/A",
            evidencia={
                "motivo": "Referência não possui dados de ponto_equilibrio (nem C_FIXO) para confronto",
                "ref_count": 0,
                "concilium_count": len(cur_pe),
            },
        )
    missing_ref = sorted(set(ref_pe) - set(cur_pe))
    missing_cur = sorted(set(cur_pe) - set(ref_pe))
    pe_mismatch = _build_pe_mismatch(ref_pe, cur_pe)
    pe_ok = not missing_ref and not missing_cur and not pe_mismatch
    return Answer(
        pergunta="5) Ponto de equilíbrio por EAP coincide?",
        status="PASSA" if pe_ok else "FALHA",
        evidencia={
            "ref_count": len(ref_pe),
            "concilium_count": len(cur_pe),
            "missing_ref": missing_ref,
            "missing_cur": missing_cur,
            "mismatch": pe_mismatch,
        },
    )


def _build_resultado_triples(
    ref_resultado: dict[str, Any], ref_confronto: dict[str, Any], cur_res: dict[str, Any]
) -> dict[str, tuple[float, float]]:
    ref_pv = _norm_float(ref_confronto.get("preco_venda"))
    ref_ct = _norm_float(ref_confronto.get("custo_total"))
    margem_ref_derived = (ref_pv - ref_ct) / ref_pv if ref_pv > 0 else 0.0
    return {
        "preco_venda_total": (
            _norm_float(
                ref_confronto.get("preco_venda")
                or ref_resultado.get("preco_venda_total")
                or (ref_resultado.get("venda") or {}).get("total_com_bdi")
            ),
            _norm_float(
                cur_res.get("preco_venda_total")
                or (cur_res.get("venda") or {}).get("total_custo_plus_catalogo")
                or (cur_res.get("venda") or {}).get("total_com_bdi")
            ),
        ),
        "custo_total": (
            _norm_float(
                ref_confronto.get("custo_total")
                or ref_resultado.get("custo_total")
                or (ref_resultado.get("custo") or {}).get("total")
            ),
            _norm_float(cur_res.get("custo_total") or (cur_res.get("custo") or {}).get("total")),
        ),
        "margem_bruta": (
            _norm_float(ref_resultado.get("margem_bruta") or ref_resultado.get("margem_pct") or margem_ref_derived),
            _norm_float(cur_res.get("margem_bruta") or cur_res.get("margem_pct")),
        ),
    }


def _audit_q6_resultado(ref: dict[str, Any], cur: dict[str, Any]) -> Answer:
    """Q6: Resultado final (venda, custo, margem) coincide?"""
    ref_resultado = (ref.get("resultado") or {}).get("canonical") or (ref.get("resultado") or {})
    ref_confronto = _get_ref_confronto(ref)
    cur_res = cur.get("resultado") or {}
    triples = _build_resultado_triples(ref_resultado, ref_confronto, cur_res)
    deltas_6 = {k: round(cv - rv, 2) for k, (rv, cv) in triples.items()}
    ok_6 = all(_is_close(rv, cv) for rv, cv in triples.values())
    return Answer(
        pergunta="6) Resultado final coincide?",
        status="PASSA" if ok_6 else "FALHA",
        evidencia={"deltas": deltas_6},
    )


def run_audit(slug: str, root: Path | None = None) -> dict[str, Any]:
    """Executa auditoria de 6 perguntas para o slug informado.

    Args:
        slug: identificador do benchmark (ex: CTC)
        root: raiz do repositório
    """
    r = root or _DEFAULT_ROOT
    data_dir = r / "benchmarks" / "data" / slug
    ref = _load_json(data_dir / "referencia.json")
    extr_path = data_dir / "extracao_intermediarios.json"
    extr = _load_json(extr_path) if extr_path.exists() else {}
    canonical_path = _resolve_canonical_path(extr, ref, r)
    cur = _load_json(canonical_path)

    answers = [
        _audit_q1_insumos_equipes(ref, cur),
        _audit_q2_custo_direto(ref, cur),
        _audit_q3_orcamento(ref, cur),
        _audit_q4_indiretos(ref, cur),
        _audit_q5_ponto_equilibrio(ref, cur),
        _audit_q6_resultado(ref, cur),
    ]

    return {
        "slug": slug,
        "resumo": {
            "passa": sum(1 for a in answers if a.status == "PASSA"),
            "falha": sum(1 for a in answers if a.status == "FALHA"),
            "na": sum(1 for a in answers if a.status == "N/A"),
            "total": len(answers),
        },
        "respostas": [{"pergunta": a.pergunta, "status": a.status, "evidencia": a.evidencia} for a in answers],
    }
