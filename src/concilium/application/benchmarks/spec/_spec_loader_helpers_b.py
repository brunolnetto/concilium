"""Private helpers for spec_loader — Part B (lfd/eei/bii/ea functions + lfd_build_bdi_section)."""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from concilium.application.benchmarks.spec.spec_loader._host_protocol import BenchmarkSpecLoaderHost


def _lfd_to_bdi_comp(
    raw: dict,
    flat_rate,
    default_vals: dict,
) -> dict:
    """Converte entrada BDI bruta para componentes normalizados."""
    if raw:
        return {
            "ac": raw.get("ac", default_vals["ac"]),
            "df": raw.get("df", default_vals["df"]),
            "r": raw.get("r", default_vals["r"]),
            "cr": raw.get("cr", default_vals["cr"]),
            "l": raw.get("lucro", default_vals["l"]),
            "cofins": raw.get("cofins", default_vals["cofins"]),
            "iss": raw.get("iss", default_vals["iss"]),
            "pis": raw.get("pis", default_vals["pis"]),
            "cssl": raw.get("cssl", default_vals["cssl"]),
            "ir": raw.get("ir", default_vals["ir"]),
        }
    if flat_rate is not None:
        return {
            "ac": float(flat_rate),
            "df": 0.0,
            "r": 0.0,
            "cr": 0.0,
            "l": 0.0,
            "cofins": 0.0,
            "iss": 0.0,
            "pis": 0.0,
            "cssl": 0.0,
            "ir": 0.0,
        }
    return {k: default_vals[k] for k in ("ac", "df", "r", "cr", "l", "cofins", "iss", "pis", "cssl", "ir")}


def _lfd_parse_raw_row(row: Any, fallback_meses: float):
    """Parseia linha de raw_indiretos; retorna (cat, custo_total, permanencia) ou None."""
    if not isinstance(row, dict):
        return None
    cat = str(row.get("categoria") or "").strip().upper()
    if not cat:
        return None
    try:
        custo_total = float(row.get("custo_total") or 0)
    except Exception:
        return None
    try:
        permanencia = float(row.get("permanencia_meses") or fallback_meses)
    except Exception:
        permanencia = fallback_meses
    if permanencia <= 0:
        permanencia = fallback_meses
    return cat, custo_total, permanencia


def _eei_normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return value.strip()


def _eei_normalize_unit(value: str) -> str:
    normalized = _eei_normalize_text(value).replace(" ", "")
    normalized = normalized.replace("metros", "m").replace("metro", "m")
    normalized = normalized.replace("quadrados", "2").replace("quadrado", "2")
    normalized = normalized.replace("cubicos", "3").replace("cubico", "3")
    return normalized


def _eei_unit_score_delta(item_unit: str, cpu_unit: str) -> float:
    if not item_unit or not cpu_unit:
        return 0.0
    return 0.35 if item_unit == cpu_unit else -0.25


def _eei_keyword_boost(item_desc: str, cpu_desc: str) -> float:
    bonus = 0.0
    if "dmt" in item_desc and "dmt" in cpu_desc:
        bonus += 0.25
    if "regulariz" in item_desc and "subleito" in item_desc and "subleito" in cpu_desc:
        bonus += 0.2
    return bonus


def _eei_score_cpu_match(
    item_desc: str,
    item_unit: str,
    item_tokens: set,
    cpu_desc: str,
    cpu_unit: str,
):
    cpu_tokens = set(cpu_desc.split())
    common = len(item_tokens & cpu_tokens)
    if common == 0:
        return None
    score = common / max(1, len(item_tokens))
    score += _eei_unit_score_delta(item_unit, cpu_unit)
    score += _eei_keyword_boost(item_desc, cpu_desc)
    return score


def _eei_best_cpu_in_catalog(
    item_desc: str,
    item_unit: str,
    item_tokens: set,
    cpus: list,
):
    best_cpu, best_score = None, -1.0
    for cpu in cpus:
        cpu_codigo = cpu.get("codigo")
        cpu_desc = _eei_normalize_text(str(cpu.get("descricao", "")))
        if not cpu_codigo or not cpu_desc:
            continue
        cpu_unit = _eei_normalize_unit(str(cpu.get("unidade", "")))
        score = _eei_score_cpu_match(item_desc, item_unit, item_tokens, cpu_desc, cpu_unit)
        if score is not None and score > best_score:
            best_score, best_cpu = score, cpu_codigo
    return best_cpu if best_score >= 0.45 else None


def _eei_find_best_match(item: dict, cpus: list, cpu_by_codigo: dict) -> None:
    cpu_id = item.get("cpu_id")
    if cpu_id and cpu_id in cpu_by_codigo:
        return
    item_desc = _eei_normalize_text(str(item.get("descricao", "")))
    item_unit = _eei_normalize_unit(str(item.get("unidade", "")))
    if not item_desc:
        return
    item_tokens = set(item_desc.split())
    best = _eei_best_cpu_in_catalog(item_desc, item_unit, item_tokens, cpus)
    if best:
        item["cpu_id"] = best


def _bii_build_detalhe_por_cat(equipes_indiretas: list) -> dict:
    result: dict = {}
    for eq in equipes_indiretas:
        cat_key = str(eq.get("categoria") or "").upper()
        if cat_key:
            result[cat_key] = eq
    return result


def _bii_build_mao_obra(cat: str, eq_detail: dict) -> dict | None:
    """Build mao_de_obra sub-entry from equipe detail; returns None if no data."""
    if not eq_detail or not eq_detail.get("mao_obra"):
        return None
    itens = [
        {
            "funcao": p.get("funcao", ""),
            "quantidade": int(p.get("quantidade", 1)),
            "custo_mensal": float(p.get("custo_unitario", 0) * int(p.get("quantidade", 1))),
            "salario_base": float(p.get("salario_base", 0)),
            "tipo_contratacao": p.get("tipo_contratacao", ""),
        }
        for p in eq_detail["mao_obra"]
        if p.get("funcao") or p.get("codigo")
    ]
    return {
        "nome": f"MO {cat}",
        "custo_fixo_mensal": round(sum(i["custo_mensal"] for i in itens), 2),
        "itens": itens,
    }


def _bii_add_equipamentos_e_verbas(entry: dict, cat: str, detalhe: dict) -> None:
    """Anexa sub-categorias de equipamentos e verbas vindas da planilha, se houver.

    Auditoria AGIS 2026-06-11: componentes de equipamentos (locação+combustível de
    veículos de apoio) e verbas vindos da planilha — habilitam BDI por sub-categoria
    (equip → taxa de material/4%, fiel à coluna DIESEL da planilha; verbas → indireto).
    """
    eq_total = detalhe.get("equipamentos_mensal_total")
    if isinstance(eq_total, (int, float)) and eq_total > 0:
        entry["equipamentos"] = {"nome": f"EQUIP {cat}", "custo_fixo_mensal": round(float(eq_total), 2), "itens": []}
    vb_total = detalhe.get("verbas_mensal_total")
    if isinstance(vb_total, (int, float)) and vb_total > 0:
        entry["verbas"] = {"nome": f"VERBAS {cat}", "custo_fixo_mensal": round(float(vb_total), 2), "itens": []}


def _bii_build_entry(cat: str, data: dict, detalhe_por_cat: dict) -> dict:
    if cat == "MOB":
        custo_total_mob = data.get("custo_fixo_total") or data.get("custo_fixo_mensal_total", 0)
        return {"categoria": cat, "driver": "one_time", "custo_fixo_total": float(custo_total_mob or 0)}
    custo_mensal = data.get("custo_fixo_mensal_total") or data.get("mao_de_obra_mensal", 0)
    entry: dict = {"categoria": cat, "driver": "permanencia", "custo_fixo_mensal": float(custo_mensal or 0)}
    detalhe = detalhe_por_cat.get(cat) or {}
    mo = _bii_build_mao_obra(cat, detalhe)
    if mo:
        entry["mao_de_obra"] = mo
    _bii_add_equipamentos_e_verbas(entry, cat, detalhe)
    return entry


def _bii_scale_categories(
    categorias_config: list,
    referencia_indireto_total,
    permanencia_meses: float,
) -> None:
    if not (
        isinstance(referencia_indireto_total, (int, float)) and referencia_indireto_total > 0 and permanencia_meses > 0
    ):
        return
    total_atual = sum(c.get("custo_fixo_mensal", 0) * permanencia_meses for c in categorias_config)
    if total_atual > 0:
        fator = float(referencia_indireto_total) / total_atual
        if abs(fator - 1.0) > 0.1:
            for categoria in categorias_config:
                categoria["custo_fixo_mensal"] *= fator


def _ea_normalize_itens_eap(itens_eap: list) -> list[dict]:
    """Normaliza itens de itens_eap para formato canonico de EAP."""
    normalized: list = []
    for i, item in enumerate(itens_eap, start=1):
        if not isinstance(item, dict):
            continue
        item_id = item.get("item_id")
        cpu_id = item.get("cpu_id")
        desc = item.get("descricao")
        unidade = item.get("unidade")
        quantitativo = item.get("quantitativo")
        if not all([item_id, cpu_id, desc, unidade, quantitativo]):
            continue
        ordem_raw = item.get("ordem")
        ordem = int(ordem_raw) if isinstance(ordem_raw, (int, float)) else i
        normalized.append(
            {
                "item_id": str(item_id),
                "ordem": ordem,
                "cpu_id": str(cpu_id),
                "descricao": str(desc),
                "unidade": str(unidade),
                "quantitativo": float(quantitativo),
            }
        )
    return normalized


def _bs_lfd_build_bdi_section(
    svc: BenchmarkSpecLoaderHost, extra_inputs: dict, ref: dict[str, Any], bdi_ref: dict
) -> dict:
    """Builds and injects BDI tabela into pricing/consolidation benchmark inputs."""
    ref_bdi_rates = svc._extract_bdi_rates(ref)
    default_vals = {
        "ac": 0.05,
        "df": 0.015,
        "r": 0.01,
        "cr": 0.0,
        "l": 0.09,
        "cofins": 0.03,
        "iss": 0.05,
        "pis": 0.0065,
        "cssl": 0.0199,
        "ir": 0.0274,
    }
    mat_defaults = {
        "ac": 0.05,
        "df": 0.0,
        "r": 0.0,
        "cr": 0.0,
        "l": 0.0,
        "cofins": 0.0,
        "iss": 0.0,
        "pis": 0.0,
        "cssl": 0.0,
        "ir": 0.0,
    }
    tabela_bdi = {
        "mao_obra": _lfd_to_bdi_comp(bdi_ref.get("mao_obra", {}), ref_bdi_rates.get("mao_obra"), default_vals),
        "material": _lfd_to_bdi_comp(bdi_ref.get("material", {}), ref_bdi_rates.get("material"), mat_defaults),
        "servicos": _lfd_to_bdi_comp(bdi_ref.get("servicos", {}), ref_bdi_rates.get("servicos"), default_vals),
        "indireto": _lfd_to_bdi_comp(bdi_ref.get("indireto", {}), ref_bdi_rates.get("indireto"), default_vals),
        "diesel": _lfd_to_bdi_comp(bdi_ref.get("diesel", {}), ref_bdi_rates.get("diesel"), default_vals),
        "data_vigencia": "2026-04-01",
    }
    for skill_id in ("06-resultado-financeiro",):  # NEP-041 F4: chave unificada
        section = extra_inputs.get(skill_id, {})
        section["tabela_bdi"] = tabela_bdi
        extra_inputs[skill_id] = section
    return extra_inputs
