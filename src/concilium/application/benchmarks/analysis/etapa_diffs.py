"""Gerador de diffs por etapa (Skills 03-06): canonical vs. extracted_references."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

_DEFAULT_ROOT = Path(__file__).resolve().parents[5]


def _ces03_cost_severidade(can_cost: float, ref_cost: float, pct_diff: float) -> str:
    """Classifica severidade para diferenca de custo_total em equipes."""
    if can_cost == 0 and ref_cost > 0:
        return "CRITICA"
    return "ALTA" if pct_diff > 10 else "MEDIA"


def _ces03_compare_item(item_id: str, can_eq: dict, ref_eq: dict) -> list:
    """Compara uma equipe individual e retorna lista de discrepancias."""
    diffs = []
    can_func_count = len(can_eq.get("funcoes", []))
    ref_func_count = len(ref_eq.get("funcoes", []))
    if can_func_count != ref_func_count:
        diffs.append(
            {
                "item_id": item_id,
                "campo": "funcoes_count",
                "canonical": can_func_count,
                "referencia": ref_func_count,
                "delta": can_func_count - ref_func_count,
                "severidade": "CRITICA" if can_func_count == 0 and ref_func_count > 0 else "MEDIA",
            }
        )
    can_eq_count = len(can_eq.get("equipamentos", []))
    ref_eq_count = len(ref_eq.get("equipamentos", []))
    if can_eq_count != ref_eq_count:
        diffs.append(
            {
                "item_id": item_id,
                "campo": "equipamentos_count",
                "canonical": can_eq_count,
                "referencia": ref_eq_count,
                "delta": can_eq_count - ref_eq_count,
                "severidade": "CRITICA" if can_eq_count == 0 and ref_eq_count > 0 else "MEDIA",
            }
        )
    can_cost = can_eq.get("custo_total", 0.0)
    ref_cost = ref_eq.get("custo_total", 0.0)
    if abs(can_cost - ref_cost) > 0.01:
        pct_diff = abs((can_cost - ref_cost) / (ref_cost + 0.01)) * 100
        diffs.append(
            {
                "item_id": item_id,
                "campo": "custo_total",
                "canonical": can_cost,
                "referencia": ref_cost,
                "delta": can_cost - ref_cost,
                "pct_diff": round(pct_diff, 2),
                "severidade": _ces03_cost_severidade(can_cost, ref_cost, pct_diff),
            }
        )
    return diffs


def compare_equipes_skill03(canonical_equipes: list, ref_equipes: list) -> list[dict[str, Any]]:
    can_dict = {eq["item_id"]: eq for eq in canonical_equipes if eq.get("item_id")}
    ref_dict = {eq.get("item_id"): eq for eq in ref_equipes if eq.get("item_id")}
    discrepancias: list[dict[str, Any]] = []
    for item_id, can_eq in can_dict.items():
        if item_id not in ref_dict:
            continue
        discrepancias.extend(_ces03_compare_item(item_id, can_eq, ref_dict[item_id]))
    return discrepancias


def _normalize_ref_equipes(ref_equipes_raw: Any) -> list[dict[str, Any]]:
    """Aceita formatos antigo/novo de iteracao_referencias e normaliza equipes."""
    if isinstance(ref_equipes_raw, list):
        return ref_equipes_raw
    if not isinstance(ref_equipes_raw, dict):
        return []

    if isinstance(ref_equipes_raw.get("equipes"), list):
        return ref_equipes_raw["equipes"]

    detalhes = ref_equipes_raw.get("detalhes")
    if not isinstance(detalhes, list):
        return []

    normalizadas: list[dict[str, Any]] = []
    for eq in detalhes:
        custos = eq.get("custos") or {}
        normalizadas.append(
            {
                "item_id": eq.get("item_id"),
                "funcoes": eq.get("funcoes") or [],
                "equipamentos": eq.get("equipamentos") or [],
                "custo_total": custos.get("total", 0.0),
            }
        )
    return normalizadas


def compare_planejamento_skill04(canonical_plan: list, ref_plan: list) -> list[dict[str, Any]]:
    discrepancias: list[dict[str, Any]] = []
    can_dict = {item["item_id"]: item for item in canonical_plan if item.get("item_id")}
    ref_dict = {item.get("item_id"): item for item in ref_plan if item.get("item_id")}

    for item_id, can_item in can_dict.items():
        if item_id not in ref_dict:
            continue
        ref_item = ref_dict[item_id]
        can_st = can_item.get("subtotal", {}).get("sem_bdi", {}).get("total", 0.0)
        ref_st = ref_item.get("subtotal_com_bdi", {}).get("total", 0.0)
        if abs(can_st - ref_st) > 0.01:
            pct_diff = abs((can_st - ref_st) / (ref_st + 0.01)) * 100
            discrepancias.append(
                {
                    "item_id": item_id,
                    "campo": "subtotal_sem_bdi",
                    "canonical": can_st,
                    "referencia": ref_st,
                    "delta": can_st - ref_st,
                    "pct_diff": round(pct_diff, 2),
                    "severidade": "ALTA" if pct_diff > 20 else "MÃ‰DIA" if pct_diff > 5 else "BAIXA",
                }
            )
    return discrepancias


def _normalize_ref_planejamento(ref_plan_raw: Any) -> list[dict[str, Any]]:
    """Aceita formatos antigo/novo de iteracao_referencias e normaliza planejamento."""
    if isinstance(ref_plan_raw, list):
        return ref_plan_raw
    if not isinstance(ref_plan_raw, dict):
        return []

    if isinstance(ref_plan_raw.get("itens_com_precos"), list):
        return ref_plan_raw["itens_com_precos"]

    itens = ref_plan_raw.get("itens")
    if not isinstance(itens, list):
        return []

    normalizados: list[dict[str, Any]] = []
    for item in itens:
        subtotal = (item.get("subtotal") or {}).get("sem_bdi") or {}
        normalizados.append(
            {
                "item_id": item.get("item_id"),
                "subtotal_com_bdi": {"total": subtotal.get("total", 0.0)},
            }
        )
    return normalizados


def compare_indiretos_skill05(canonical_indir: list, ref_indir: dict) -> list[dict[str, Any]]:
    discrepancias: list[dict[str, Any]] = []
    for cat in ("ADM", "TOP", "LAB", "QSMS", "MOB"):
        can_val = sum(i.get("custo_total", 0.0) for i in canonical_indir if i.get("categoria") == cat)
        ref_val = ref_indir.get(cat, {}).get("custo_com_bdi", 0.0)
        if abs(can_val - ref_val) > 0.01:
            pct_diff = abs((can_val - ref_val) / (ref_val + 0.01)) * 100 if ref_val > 0 else 0
            discrepancias.append(
                {
                    "categoria": cat,
                    "campo": "custo_total",
                    "canonical": can_val,
                    "referencia": ref_val,
                    "delta": can_val - ref_val,
                    "pct_diff": round(pct_diff, 2),
                    "severidade": "CRÃTICA" if can_val == 0 and ref_val > 0 else "ALTA" if pct_diff > 15 else "MÃ‰DIA",
                }
            )
    return discrepancias


def _normalize_ref_indiretos(ref_indir_raw: Any) -> dict[str, dict[str, float]]:
    """Aceita formatos antigo/novo de iteracao_referencias e normaliza indiretos por categoria."""
    if not isinstance(ref_indir_raw, dict):
        return {}

    if all(k in ref_indir_raw for k in ("ADM", "TOP", "LAB", "QSMS", "MOB")):
        return ref_indir_raw

    out: dict[str, dict[str, float]] = {cat: {"custo_com_bdi": 0.0} for cat in ("ADM", "TOP", "LAB", "QSMS", "MOB")}
    raw_list = ref_indir_raw.get("raw_indiretos")
    value_key = "custo_total"
    if not isinstance(raw_list, list):
        raw_list = ref_indir_raw.get("raw_indiretos_com_bdi")
        value_key = "custo_com_bdi"
    if isinstance(raw_list, list):
        for row in raw_list:
            cat = row.get("categoria")
            if cat in out:
                out[cat]["custo_com_bdi"] = float(row.get(value_key) or 0.0)
    return out


def compare_resultado_skill06(canonical_result: dict, ref_result: dict) -> list[dict[str, Any]]:
    discrepancias: list[dict[str, Any]] = []
    for campo, can_val, ref_val in _normalize_resultado_pairs(canonical_result, ref_result):
        if abs(can_val - ref_val) > 0.01:
            pct_diff = abs((can_val - ref_val) / (ref_val + 0.01)) * 100
            discrepancias.append(
                {
                    "campo": campo,
                    "canonical": can_val,
                    "referencia": ref_val,
                    "delta": can_val - ref_val,
                    "pct_diff": round(pct_diff, 2),
                    "severidade": "CRÃTICA" if campo in ("venda", "custo") else "ALTA",
                }
            )
    return discrepancias


def _to_float(val: Any, keys: tuple[str, ...] = ()) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict):
        for k in keys:
            v = val.get(k)
            if isinstance(v, (int, float)):
                return float(v)
    return 0.0


def _normalize_resultado_pairs(canonical_result: dict | None, ref_result: dict | None) -> list[tuple[str, float, float]]:
    """Normaliza campos de resultado em formatos antigo/novo para comparação numérica."""
    canonical_result = canonical_result or {}
    ref_result = ref_result or {}
    can_venda = _to_float(canonical_result.get("venda"), ("total_custo_plus", "total_com_bdi", "total"))
    can_custo = _to_float(canonical_result.get("custo"), ("total",))
    can_margem = _to_float(canonical_result.get("margem_pct")) or _to_float(canonical_result.get("margem"))

    ref_venda = _to_float(ref_result.get("venda"), ("total_custo_plus", "total_com_bdi", "total"))
    ref_custo = _to_float(ref_result.get("custo"), ("total",))
    ref_margem = _to_float(ref_result.get("margem_pct")) or _to_float(ref_result.get("margem"))

    # Formato rico de iteracao_referencias (CTC): usar confronto da ferramenta
    # para comparar canonical vs. saída do engine na mesma base.
    if isinstance(ref_result.get("benchmark_confronto_ferramenta"), dict):
        confronto_ref = ref_result["benchmark_confronto_ferramenta"]
        ref_venda = _to_float(confronto_ref.get("preco_venda"))
        ref_custo = _to_float(confronto_ref.get("custo_indireto")) + _to_float(confronto_ref.get("custo_direto"))
        ref_margem = (ref_venda - ref_custo) / ref_venda if ref_venda > 0 else 0.0
    elif isinstance(ref_result.get("benchmark_confronto_referencia"), dict):
        confronto_ref = ref_result["benchmark_confronto_referencia"]
        ref_venda = _to_float(confronto_ref.get("preco_venda"))
        ref_custo = _to_float(confronto_ref.get("custo_total"))
        ref_margem = (ref_venda - ref_custo) / ref_venda if ref_venda > 0 else 0.0

    return [
        ("venda", can_venda, ref_venda),
        ("custo", can_custo, ref_custo),
        ("margem", can_margem, ref_margem),
    ]


def _summarize(diffs: list[dict], *, label_key: str = "campo") -> str:
    crit = sum(1 for d in diffs if d.get("severidade") == "CRÃTICA")
    alta = sum(1 for d in diffs if d.get("severidade") == "ALTA")
    media = sum(1 for d in diffs if d.get("severidade") == "MEDIA")
    return f"{crit} CRITICA, {alta} ALTA, {media} MEDIA"


def _find_benchmark_report(slug: str, root: Path) -> Path | None:
    """Localiza benchmark_report.json: caminho organizado primeiro, fallback legacy."""
    candidates = [
        root / "benchmarks" / "data" / slug.upper() / "artifacts" / "outputs" / "benchmark_report.json",
        root / "benchmarks" / "data" / slug.upper() / "outputs" / "benchmark_report.json",
        root / "benchmarks" / "data" / slug.upper() / "audit" / "benchmark_report.json",
    ]
    for organized in candidates:
        if organized.exists():
            return organized
    for p in [root / f"benchmark_{slug.lower()}.json"] + list(root.glob(f"benchmark_{slug.lower()}*.json")):
        if p.exists():
            return p
    return None


def _find_reference_payload(slug: str, root: Path) -> Path | None:
    """Localiza payload de referência em formato legado ou atual (artifacts/inputs)."""
    slug_u = slug.upper()
    slug_l = slug.lower()
    candidates = [
        root / "benchmarks" / "data" / slug_u / f"iteracao_referencias_{slug_l}.json",
        root / "benchmarks" / "extracted_references" / f"iteracao_referencias_{slug_l}.json",
        root / "benchmarks" / "data" / slug_u / "artifacts" / "inputs" / "referencia.json",
        root / "benchmarks" / "data" / slug_u / "referencia.json",
    ]
    return next((p for p in candidates if p.exists()), None)


def _gdfb_load_canonical(bench: dict, r: Path) -> dict:
    """Carrega canonical.json do projeto associado ao benchmark."""
    projeto_nome = bench.get("projeto") or bench.get("slug", "")
    roots = [r / "benchmarks" / "projetos", r / "projetos"]
    for projects_root in roots:
        if not projects_root.exists() or not projects_root.is_dir():
            continue
        for d in projects_root.iterdir():
            if not d.is_dir():
                continue
            meta_path = d / "meta.json"
            if not meta_path.exists():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            nome = str(meta.get("nome") or "")
            if projeto_nome and projeto_nome not in {nome, str(meta.get("id") or "")}:
                continue
            # Prioriza versao ativa; fallback para v1.
            current_version = str(meta.get("current_version") or "v1")
            can_candidates = [
                d / current_version / "canonical.json",
                d / "v1" / "canonical.json",
            ]
            for can_path in can_candidates:
                if can_path.exists():
                    return json.loads(can_path.read_text(encoding="utf-8"))
    return {}


def _normalize_reference_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normaliza payload de referência para o contrato esperado pelos comparadores de etapa."""
    if not isinstance(payload, dict):
        return {}
    if any(k in payload for k in ("equipes", "planejamento", "indiretos")):
        return payload

    normalized: dict[str, Any] = {
        "equipes": {"equipes": payload.get("equipes_detalhadas") or []},
        "planejamento": {"itens": payload.get("planejamento_detalhado") or []},
        "indiretos": {},
        "resultado": payload.get("resultado") or {},
    }

    # Estrutura AGIS atual: categorias no topo com custos mensais/fixos.
    cats = ("ADM", "TOP", "LAB", "QSMS", "MOB")
    if all(cat in payload for cat in cats):
        indiretos_out: dict[str, dict[str, float]] = {}
        semanas = float((payload.get("rcpsp_spec") or {}).get("deadline_weeks") or 0.0)
        # Evita hardcode de constante externa e mantém aproximação estável para benchmark.
        semanas_por_mes = 4.34524
        meses_estimados = semanas / semanas_por_mes if semanas > 0 else 0.0
        for cat in cats:
            row = payload.get(cat) or {}
            mensal = float(row.get("custo_fixo_mensal_total") or 0.0)
            one_time = float(row.get("custo_fixo_total") or 0.0)
            total = one_time + (mensal * meses_estimados)
            indiretos_out[cat] = {"custo_com_bdi": round(total, 2)}
        normalized["indiretos"] = indiretos_out

    return normalized


def generate_diffs_for_benchmark(slug: str, root: Path | None = None) -> dict[str, Any] | None:
    """Gera diffs por etapa (03-06) para um slug de benchmark."""
    r = root or _DEFAULT_ROOT
    extracted_ref_path = _find_reference_payload(slug, r)

    if extracted_ref_path is None:
        return None

    bench_path = _find_benchmark_report(slug, r)
    if bench_path is None:
        return None

    with open(extracted_ref_path, encoding="utf-8") as f:
        extracted_raw = json.load(f)
    extracted = _normalize_reference_payload(extracted_raw)
    with open(bench_path, encoding="utf-8") as f:
        bench = json.load(f)

    canonical = _gdfb_load_canonical(bench, r)

    diffs_result: dict[str, Any] = {
        "slug": slug,
        "gerado_em": datetime.now().isoformat(),
        "por_etapa": {},
    }

    d03 = compare_equipes_skill03(
        canonical.get("equipes_diretas", []),
        _normalize_ref_equipes(extracted.get("equipes", {})),
    )
    diffs_result["por_etapa"]["05-equipes-e-alocacao"] = {
        "total_discrepancias": len(d03),
        "discrepancias": d03,
        "resumo": _summarize(d03),
    }

    d04 = compare_planejamento_skill04(
        canonical.get("planejamento", []),
        _normalize_ref_planejamento(extracted.get("planejamento", {})),
    )
    diffs_result["por_etapa"]["04-planejamento-e-insumos"] = {
        "total_discrepancias": len(d04),
        "discrepancias": d04,
        "resumo": _summarize(d04),
    }

    d05 = compare_indiretos_skill05(
        canonical.get("indiretos", []),
        _normalize_ref_indiretos(extracted.get("indiretos", {})),
    )
    diffs_result["por_etapa"]["07-custos-indiretos-e-contingencia"] = {
        "total_discrepancias": len(d05),
        "discrepancias": d05,
        "resumo": _summarize(d05),
    }

    d06 = compare_resultado_skill06(
        canonical.get("resultado") or {},
        extracted.get("resultado") or {},
    )
    diffs_result["por_etapa"]["06-consolidacao-resultado"] = {
        "total_discrepancias": len(d06),
        "discrepancias": d06,
        "resumo": _summarize(d06),
    }

    return diffs_result
