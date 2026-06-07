"""Auditoria de seis perguntas para um benchmark."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._audit_utils import (
    _DEFAULT_ROOT,
    _TOL,
    _extract_ref_ponto_equilibrio,
    _get_ref_confronto,
    _is_close,
    _load_json,
    _norm_float,
    _resolve_canonical_path,
    _sum_dict_counter,
)


@dataclass
class Answer:
    pergunta: str
    status: str
    evidencia: dict


def _aq1_resolve_ref_equipes(ref: dict) -> list:
    """Resolve lista de equipes de referencia em formato historico ou atual."""
    return (
        ref.get("equipes_detalhadas")
        or (ref.get("equipes") or {}).get("detalhes")
        or (ref.get("equipes") or {}).get("equipes")
        or []
    )


def _aq1_build_eq_map(equipes: list) -> dict:
    """Constroi mapa item_id -> {funcoes, equipamentos} a partir de lista de equipes."""
    eq_map: dict = {}
    for eq in equipes:
        item_id = str(eq.get("item_id") or "")
        if not item_id:
            continue
        eq_map[item_id] = {
            "funcoes": dict(_sum_dict_counter(eq.get("funcoes", []), "funcao_id", "num_pessoas")),
            "equipamentos": dict(_sum_dict_counter(eq.get("equipamentos", []), "equip_id", "num_unidades")),
        }
    return eq_map


def _audit_q1_insumos_equipes(ref: dict[str, Any], cur: dict[str, Any]) -> Answer:
    """Q1: Insumos, CPUs, produtividades e composicao de equipes iguais?"""
    ref_eap = ref.get("eap") or (ref.get("cpus") or {}).get("itens_eap") or []
    ref_cpu_map = {str(x.get("item_id")): str(x.get("cpu_id")) for x in ref_eap}
    cur_cpu_map = {str(x.get("item_id")): str(x.get("cpu_id")) for x in cur.get("eap", [])}
    cpus_iguais = ref_cpu_map == cur_cpu_map
    ref_eq_map = _aq1_build_eq_map(_aq1_resolve_ref_equipes(ref))
    cur_eq_map = _aq1_build_eq_map(cur.get("equipes_diretas", []))
    equipes_iguais = ref_eq_map == cur_eq_map
    return Answer(
        pergunta="1) Insumos/CPUs/produtividades/composicao de equipes iguais?",
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
    custo = cur_res.get("custo") or {}
    cur_cd = _norm_float(custo.get("direto_equipes"))
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


def _aq3_resolve_ref_planejamento(ref: dict) -> list:
    """Resolve lista de itens de planejamento em diferentes formatos de referencia."""
    result = ref.get("planejamento_detalhado") or (ref.get("planejamento") or {}).get("itens") or []
    if not result:
        result = (ref.get("cpus") or {}).get("itens_eap") or []
    return result


def _aq3_build_cur_items(cur: dict) -> dict:
    """Constroi mapa item_id -> subtotal_sem_bdi a partir do canonical atual."""
    return {
        str(i.get("item_id")): _norm_float(((i.get("subtotal") or {}).get("sem_bdi") or {}).get("total"))
        for i in cur.get("planejamento", [])
    }


def _audit_q3_orcamento(ref: dict[str, Any], cur: dict[str, Any]) -> Answer:
    """Q3: Orcamento de itens calculado corretamente?"""
    ref_planejamento = _aq3_resolve_ref_planejamento(ref)
    ref_items = {str(i.get("item_id")): _extract_ref_item_subtotal(i) for i in ref_planejamento}
    cur_items = _aq3_build_cur_items(cur)
    item_deltas = {k: round(cur_items.get(k, 0.0) - v, 2) for k, v in ref_items.items()}
    ok_items = (
        all(_is_close(ref_items.get(k, 0.0), cur_items.get(k, 0.0)) for k in item_deltas) if item_deltas else False
    )
    return Answer(
        pergunta="3) Orcamento de itens esta correto?",
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


def _aq4_resolve_ref_resultado(ref: dict) -> dict:
    """Resolve resultado canonico de referencia (formato novo ou legado)."""
    return (ref.get("resultado") or {}).get("canonical") or (ref.get("resultado") or {})


def _aq4_indireto_fallback(cur: dict) -> float:
    """Soma indiretos por prefixo de chave quando campo direto nao existe."""
    return _norm_float(
        sum(v for k, v in ((cur.get("resultado") or {}).get("custo") or {}).items() if str(k).startswith("indireto_"))
    )


def _audit_q4_indiretos(ref: dict[str, Any], cur: dict[str, Any]) -> Answer:
    """Q4: Indiretos aplicados corretamente?"""
    ref_resultado = _aq4_resolve_ref_resultado(ref)
    ref_confronto = _get_ref_confronto(ref)
    ref_ind = _resolve_ref_indireto(ref_resultado, ref_confronto)
    cur_ind = _norm_float((cur.get("resultado") or {}).get("custo_indireto_total"))
    if cur_ind == 0:
        cur_ind = _aq4_indireto_fallback(cur)
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


def _aq5_build_pe_map(items: list | None) -> dict:
    """Constroi mapa item_id -> item para ponto de equilibrio."""
    return {str(i.get("item_id")): i for i in (items or []) if i.get("item_id")}


def _audit_q5_ponto_equilibrio(ref: dict[str, Any], cur: dict[str, Any]) -> Answer:
    """Q5: Ponto de equilibrio por EAP coincide?"""
    ref_pe_src = _extract_ref_ponto_equilibrio(ref)
    ref_pe = _aq5_build_pe_map(ref_pe_src)
    cur_pe = _aq5_build_pe_map(cur.get("ponto_equilibrio"))
    if not ref_pe:
        return Answer(
            pergunta="5) Ponto de equilibrio por EAP coincide?",
            status="N/A",
            evidencia={
                "motivo": "Referencia nao possui dados de ponto_equilibrio (nem C_FIXO) para confronto",
                "ref_count": 0,
                "concilium_count": len(cur_pe),
            },
        )
    missing_ref = sorted(set(ref_pe) - set(cur_pe))
    missing_cur = sorted(set(cur_pe) - set(ref_pe))
    pe_mismatch = _build_pe_mismatch(ref_pe, cur_pe)
    pe_ok = not missing_ref and not missing_cur and not pe_mismatch
    return Answer(
        pergunta="5) Ponto de equilibrio por EAP coincide?",
        status="PASSA" if pe_ok else "FALHA",
        evidencia={
            "ref_count": len(ref_pe),
            "concilium_count": len(cur_pe),
            "missing_ref": missing_ref,
            "missing_cur": missing_cur,
            "mismatch": pe_mismatch,
        },
    )


def _brt_preco_venda_triple(ref_resultado: dict, ref_confronto: dict, cur_res: dict) -> tuple:
    """Resolve (ref_preco_venda, cur_preco_venda) de fontes alternativas."""
    ref_pv = _norm_float(
        ref_confronto.get("preco_venda")
        or ref_resultado.get("preco_venda_total")
        or (ref_resultado.get("venda") or {}).get("total_com_bdi")
    )
    cur_pv = _norm_float(
        cur_res.get("preco_venda_total")
        or (cur_res.get("venda") or {}).get("total_custo_plus_catalogo")
        or (cur_res.get("venda") or {}).get("total_com_bdi")
    )
    return ref_pv, cur_pv


def _brt_custo_triple(ref_resultado: dict, ref_confronto: dict, cur_res: dict) -> tuple:
    """Resolve (ref_custo_total, cur_custo_total) de fontes alternativas."""
    ref_ct = _norm_float(
        ref_confronto.get("custo_total")
        or ref_resultado.get("custo_total")
        or (ref_resultado.get("custo") or {}).get("total")
    )
    cur_ct = _norm_float(cur_res.get("custo_total") or (cur_res.get("custo") or {}).get("total"))
    return ref_ct, cur_ct


def _build_resultado_triples(
    ref_resultado: dict[str, Any], ref_confronto: dict[str, Any], cur_res: dict[str, Any]
) -> dict[str, tuple[float, float]]:
    ref_pv = _norm_float(ref_confronto.get("preco_venda"))
    ref_ct = _norm_float(ref_confronto.get("custo_total"))
    margem_ref_derived = (ref_pv - ref_ct) / ref_pv if ref_pv > 0 else 0.0
    return {
        "preco_venda_total": _brt_preco_venda_triple(ref_resultado, ref_confronto, cur_res),
        "custo_total": _brt_custo_triple(ref_resultado, ref_confronto, cur_res),
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
    ref_path = None
    for p in (data_dir / "artifacts" / "inputs" / "referencia.json", data_dir / "referencia.json"):
        if p.exists():
            ref_path = p
            break
    if ref_path is None:
        raise FileNotFoundError(f"referencia.json não encontrado para slug={slug}")
    ref = _load_json(ref_path)
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
