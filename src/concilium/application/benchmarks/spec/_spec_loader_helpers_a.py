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


def _norm_ref_projeto_block(out: dict[str, Any], projeto_block: dict[str, Any]) -> None:
    if not projeto_block:
        return
    nome = projeto_block.get("nome") or projeto_block.get("projeto")
    if nome and not isinstance(out.get("projeto"), str):
        out["projeto"] = nome
    loc = projeto_block.get("localizacao")
    if loc and not out.get("localizacao"):
        out["localizacao"] = loc
    # Se localizacao já é {lat, lng}, propagar como coordenadas também (retrocompat)
    if isinstance(loc, dict) and "lat" in loc and not out.get("coordenadas"):
        out["coordenadas"] = loc
    elif projeto_block.get("coordenadas") and not out.get("coordenadas"):
        out["coordenadas"] = projeto_block.get("coordenadas")


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
    metas = out.get("metas_confronto") if isinstance(out.get("metas_confronto"), dict) else {}
    if not metas:
        return
    resultado = out.get("resultado") if isinstance(out.get("resultado"), dict) else {}
    if "benchmark_confronto_referencia" not in resultado:  # type: ignore[operator]
        resultado["benchmark_confronto_referencia"] = {  # type: ignore[index]
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


def _norm_ref_build_rcpsp_activities(out: dict[str, Any], weeks: list[str]) -> list[dict[str, Any]]:
    atividades = out.get("atividades") if isinstance(out.get("atividades"), list) else []

    # If no atividades but EAP exists, build from EAP using spec.cronograma when available
    if not atividades:
        eap = out.get("eap") if isinstance(out.get("eap"), list) else []

        # Índice spec.cronograma compacto → {item_id: {equipes}}
        # duration_weeks é derivado de Q/P em skill-04 (_enrich_spec_resources_from_catalog)
        # e não deve ser armazenado na spec (seria redundante e poderia divergir).
        cron_index: dict[str, dict] = {}
        for c in out.get("cronograma_compacto") or []:
            if isinstance(c, dict) and c.get("item_id"):
                cron_index[str(c["item_id"])] = c
        # fallback: atividades legadas
        if not cron_index:
            cron_legacy = out.get("cronograma") or {}
            for c in (cron_legacy.get("atividades") if isinstance(cron_legacy, dict) else []) or []:
                if isinstance(c, dict) and c.get("item_id"):
                    cron_index[str(c["item_id"])] = c

        activities: list[dict[str, Any]] = []
        for item in eap:
            if not isinstance(item, dict):
                continue
            item_id = item.get("item_id")
            if not item_id:
                continue

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

            activities.append(act)
        return activities

    # Otherwise build from explicit atividades
    activities: list[dict[str, Any]] = []
    for atividade in atividades:  # type: ignore[union-attr]
        if not isinstance(atividade, dict):
            continue
        item_id = atividade.get("item_id")
        if not item_id:
            continue
        required_resources = atividade.get("required_resources")
        if not isinstance(required_resources, dict):
            required_resources = atividade.get("recursos") if isinstance(atividade.get("recursos"), dict) else {}
        activities.append(
            {
                "item_id": str(item_id),
                "descricao": str(atividade.get("descricao") or item_id),
                "duration_weeks": max(1, _norm_ref_parse_atividade_duration(atividade, weeks)),
                "required_resources": required_resources,
            }
        )
    return activities


def _norm_ref_build_default_rcpsp_spec(out: dict[str, Any], rcpsp_block: dict[str, Any]) -> dict[str, Any]:
    data_ini = out.get("data_inicio", "2025-01-01")
    data_fim = out.get("data_termino", "2025-06-30")
    weeks = iso_weeks(data_ini, data_fim)
    activities = _norm_ref_build_rcpsp_activities(out, weeks)
    resource_pool: dict[str, Any] = out.get("resource_pool") if isinstance(out.get("resource_pool"), dict) else {}  # type: ignore[assignment]
    if not resource_pool:
        restr = out.get("restricao_equipes")
        if isinstance(restr, dict):
            resource_pool = restr
    spec_out: dict[str, Any] = {
        "deadline_weeks": int(rcpsp_block.get("deadline_weeks") or len(weeks) or 1),  # type: ignore[union-attr]
        "activities": activities,
        "resource_pool": resource_pool,
        "precedence": rcpsp_block.get("precedence") or [],  # type: ignore[union-attr]
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
    rcpsp_block = out.get("rcpsp") if isinstance(out.get("rcpsp"), dict) else {}
    params_block = out.get("parametros_simulacao") if isinstance(out.get("parametros_simulacao"), dict) else {}
    rcpsp_from_params = (
        params_block.get("rcpsp_spec") if isinstance(params_block.get("rcpsp_spec"), dict) else {}  # type: ignore[union-attr]
    )
    rcpsp_spec = dict(rcpsp_block or rcpsp_from_params)  # type: ignore[arg-type]
    if not rcpsp_spec:
        rcpsp_spec = _norm_ref_build_default_rcpsp_spec(out, rcpsp_block)  # type: ignore[arg-type]
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
