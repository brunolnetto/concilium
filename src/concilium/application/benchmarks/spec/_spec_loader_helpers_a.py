"""Private helpers for spec_loader — Part A (norm_ref + ebr functions)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


def iso_weeks(start: str, end: str) -> list[str]:
    """Gera lista de chaves ISO-week entre duas datas."""

    current = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    seen: dict[str, None] = {}
    while current <= end_date:
        iso = current.isocalendar()
        seen[f"{iso.year}-W{iso.week:02d}"] = None
        current += timedelta(weeks=1)
    return list(seen.keys())


_EBR_KEY_MAP: dict[str, str] = {
    "materiais": "material",
    "material": "material",
    "diesel": "diesel",
    "mao_obra": "mao_obra",
    "equipamentos": "equipamentos",
    "servicos": "servicos",
    "indireto": "indireto",
}


def _norm_ref_apply_nome(out: dict[str, Any], projeto_block: dict[str, Any]) -> None:
    nome = projeto_block.get("nome") or projeto_block.get("projeto")
    if nome and not isinstance(out.get("projeto"), str):
        out["projeto"] = nome


def _norm_ref_apply_localizacao(out: dict[str, Any], projeto_block: dict[str, Any]) -> None:
    loc = projeto_block.get("localizacao")
    if loc and not out.get("localizacao"):
        out["localizacao"] = loc
    # Se localizacao já é {lat, lng}, propagar como coordenadas também (retrocompat)
    if isinstance(loc, dict) and "lat" in loc and not out.get("coordenadas"):
        out["coordenadas"] = loc
    elif projeto_block.get("coordenadas") and not out.get("coordenadas"):
        out["coordenadas"] = projeto_block.get("coordenadas")


def _norm_ref_projeto_block(out: dict[str, Any], projeto_block: dict[str, Any]) -> None:
    if not projeto_block:
        return
    _norm_ref_apply_nome(out, projeto_block)
    _norm_ref_apply_localizacao(out, projeto_block)


def _norm_ref_datas_block(out: dict[str, Any], datas_block: dict[str, Any]) -> None:
    if not datas_block:
        return
    if datas_block.get("data_inicio") and not out.get("data_inicio"):
        out["data_inicio"] = datas_block.get("data_inicio")
    if datas_block.get("data_termino") and not out.get("data_termino"):
        out["data_termino"] = datas_block.get("data_termino")


def _norm_ref_atividade_item(atividade: Any, idx: int) -> dict[str, Any] | None:
    if not isinstance(atividade, dict):
        return None
    item_id = atividade.get("item_id")
    cpu_id = atividade.get("cpu_id")
    if not item_id or not cpu_id:
        return None
    return {
        "item_id": str(item_id),
        "ordem": int(atividade.get("ordem") or idx),
        "cpu_id": str(cpu_id),
        "descricao": str(atividade.get("descricao") or item_id),
        "unidade": str(atividade.get("unidade") or "un"),
        "quantitativo": float(atividade.get("quantitativo") or 0.0),
    }


def _norm_ref_atividades_to_eap(out: dict[str, Any]) -> None:
    atividades = out.get("atividades")
    if not isinstance(atividades, list) or not atividades:
        return
    if out.get("eap") or (out.get("cpus") or {}).get("itens_eap"):
        return
    eap = [item for item in (_norm_ref_atividade_item(a, i) for i, a in enumerate(atividades, 1)) if item is not None]
    if eap:
        out["eap"] = eap


def _norm_ref_metas_confronto(out: dict[str, Any]) -> None:
    raw_metas = out.get("metas_confronto")
    metas = raw_metas if isinstance(raw_metas, dict) else {}
    if not metas:
        return
    raw_resultado = out.get("resultado")
    resultado: dict[str, Any] = raw_resultado if isinstance(raw_resultado, dict) else {}
    if "benchmark_confronto_referencia" not in resultado:
        resultado["benchmark_confronto_referencia"] = {
            "custo_direto": metas.get("custo_direto"),
            "custo_indireto": metas.get("custo_indireto"),
            "custo_total": metas.get("custo_total"),
            "preco_venda": metas.get("preco_venda"),
        }
    out["resultado"] = resultado


def _norm_ref_parse_atividade_duration(atividade: dict[str, Any], weeks: list[str]) -> int:
    duration = atividade.get("duration_weeks") or atividade.get("duracao_semanas")
    try:
        return int(duration) if duration is not None else max(1, len(weeks))
    except Exception:
        return max(1, len(weeks))


def _norm_ref_add_to_cron_index(cron_index: dict[str, dict], items: Any) -> None:
    for c in items or []:
        if isinstance(c, dict) and c.get("item_id"):
            cron_index[str(c["item_id"])] = c


def _norm_ref_build_cron_index(out: dict[str, Any]) -> dict[str, dict]:
    """Índice spec.cronograma compacto → {item_id: {equipes}}.

    duration_weeks é derivado de Q/P em skill-04 (_enrich_spec_resources_from_catalog)
    e não deve ser armazenado na spec (seria redundante e poderia divergir).
    """
    cron_index: dict[str, dict] = {}
    _norm_ref_add_to_cron_index(cron_index, out.get("cronograma_compacto"))
    # fallback: atividades legadas
    if not cron_index:
        cron_legacy = out.get("cronograma") or {}
        legacy_items = cron_legacy.get("atividades") if isinstance(cron_legacy, dict) else []
        _norm_ref_add_to_cron_index(cron_index, legacy_items)
    return cron_index


def _norm_ref_build_activity_from_eap_item(item: Any, cron_index: dict[str, dict]) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    item_id = item.get("item_id")
    if not item_id:
        return None

    cron_item = cron_index.get(str(item_id), {})

    act: dict[str, Any] = {
        "item_id": str(item_id),
        "descricao": str(item.get("descricao") or item_id),
        # duration_weeks=1 é placeholder; _enrich_spec_resources_from_catalog
        # substitui pelo valor real ceil(Q / (P × n_frentes × h_sem))
        "duration_weeks": 1,
        "required_resources": {},
    }

    # Injetar ramp_params quando spec.cronograma tem equipes compacto
    eq = cron_item.get("equipes")
    if isinstance(eq, dict) and eq.get("n_max", 0) > 0:
        act["ramp_params"] = {
            "n_inicial": eq.get("n_inicial", 1),
            "n_max": eq["n_max"],  # necessário para _compute_ramp_profile
            "taxa_mobilizacao": eq.get("taxa_mobilizacao", float(eq["n_max"])),
            "taxa_desmobilizacao": eq.get("taxa_desmobilizacao", float(eq["n_max"])),
        }

    return act


def _norm_ref_build_activities_from_eap(out: dict[str, Any]) -> list[dict[str, Any]]:
    """Build activities from EAP using spec.cronograma when available."""
    raw_eap = out.get("eap")
    eap = raw_eap if isinstance(raw_eap, list) else []
    cron_index = _norm_ref_build_cron_index(out)

    activities: list[dict[str, Any]] = []
    for item in eap:
        act = _norm_ref_build_activity_from_eap_item(item, cron_index)
        if act is not None:
            activities.append(act)
    return activities


def _norm_ref_build_activity_from_atividade(atividade: Any, weeks: list[str]) -> dict[str, Any] | None:
    if not isinstance(atividade, dict):
        return None
    item_id = atividade.get("item_id")
    if not item_id:
        return None
    required_resources = atividade.get("required_resources")
    if not isinstance(required_resources, dict):
        required_resources = atividade.get("recursos") if isinstance(atividade.get("recursos"), dict) else {}
    return {
        "item_id": str(item_id),
        "descricao": str(atividade.get("descricao") or item_id),
        "duration_weeks": max(1, _norm_ref_parse_atividade_duration(atividade, weeks)),
        "required_resources": required_resources,
    }


def _norm_ref_build_activities_from_atividades(atividades: list[Any], weeks: list[str]) -> list[dict[str, Any]]:
    """Build activities from explicit atividades."""
    activities: list[dict[str, Any]] = []
    for atividade in atividades:
        act = _norm_ref_build_activity_from_atividade(atividade, weeks)
        if act is not None:
            activities.append(act)
    return activities


def _norm_ref_build_rcpsp_activities(out: dict[str, Any], weeks: list[str]) -> list[dict[str, Any]]:
    raw_atividades = out.get("atividades")
    atividades = raw_atividades if isinstance(raw_atividades, list) else []

    # If no atividades but EAP exists, build from EAP using spec.cronograma when available
    if not atividades:
        return _norm_ref_build_activities_from_eap(out)

    # Otherwise build from explicit atividades
    return _norm_ref_build_activities_from_atividades(atividades, weeks)


def _norm_ref_build_default_rcpsp_spec(out: dict[str, Any], rcpsp_block: dict[str, Any]) -> dict[str, Any]:
    data_ini = out.get("data_inicio", "2025-01-01")
    data_fim = out.get("data_termino", "2025-06-30")
    weeks = iso_weeks(data_ini, data_fim)
    activities = _norm_ref_build_rcpsp_activities(out, weeks)
    raw_resource_pool = out.get("resource_pool")
    resource_pool: dict[str, Any] = raw_resource_pool if isinstance(raw_resource_pool, dict) else {}
    if not resource_pool:
        restr = out.get("restricao_equipes")
        if isinstance(restr, dict):
            resource_pool = restr
    spec_out: dict[str, Any] = {
        "deadline_weeks": int(rcpsp_block.get("deadline_weeks") or len(weeks) or 1),
        "activities": activities,
        "resource_pool": resource_pool,
        "precedence": rcpsp_block.get("precedence") or [],
    }
    # ADR-091 Fase 4: objetivo de pool (pool_config) opcional na referência. Quando
    # presente sem resource_pool explícito, dirige a inferência do pool mínimo.
    pool_config = out.get("pool_config")
    if isinstance(pool_config, dict):
        spec_out["pool_config"] = pool_config
    return spec_out


def _norm_ref_ensure_rcpsp_spec(out: dict[str, Any]) -> None:
    if out.get("rcpsp_spec"):
        return
    raw_rcpsp = out.get("rcpsp")
    rcpsp_block: dict[str, Any] = raw_rcpsp if isinstance(raw_rcpsp, dict) else {}
    raw_params = out.get("parametros_simulacao")
    params_block: dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}
    raw_rcpsp_from_params = params_block.get("rcpsp_spec")
    rcpsp_from_params: dict[str, Any] = raw_rcpsp_from_params if isinstance(raw_rcpsp_from_params, dict) else {}
    rcpsp_spec = dict(rcpsp_block or rcpsp_from_params)
    if not rcpsp_spec:
        rcpsp_spec = _norm_ref_build_default_rcpsp_spec(out, rcpsp_block)
    out["rcpsp_spec"] = rcpsp_spec


def _ebr_as_float(v: Any) -> float | None:
    try:
        return None if v is None else float(v)
    except Exception:
        return None


def _ebr_from_stats(stats: Any) -> dict[str, float]:
    if not isinstance(stats, dict):
        return {}
    result: dict[str, float] = {}
    for src_key, dst_key in _EBR_KEY_MAP.items():
        raw = stats.get(src_key)
        if isinstance(raw, dict):
            rate = _ebr_as_float(raw.get("media"))
            if rate is not None:
                result[dst_key] = rate
    return result


def _ebr_from_por_item(bdi_ref: dict[str, Any]) -> dict[str, float]:
    por_item = bdi_ref.get("por_item") or []
    if not (isinstance(por_item, list) and por_item):
        return {}
    sample = por_item[0] if isinstance(por_item[0], dict) else {}
    bdi_item = sample.get("bdi") if isinstance(sample, dict) else {}
    if not isinstance(bdi_item, dict):
        return {}
    result: dict[str, float] = {}
    for src_key, dst_key in _EBR_KEY_MAP.items():
        rate = _ebr_as_float(bdi_item.get(src_key))
        if rate is not None:
            result[dst_key] = rate
    return result


def _ebr_apply_fallbacks(mapped: dict[str, float]) -> None:
    if "servicos" not in mapped and "equipamentos" in mapped:
        mapped["servicos"] = mapped["equipamentos"]
    if "servicos" not in mapped and "mao_obra" in mapped:
        mapped["servicos"] = mapped["mao_obra"]
