"""Camada de apresentação — layout Streamlit (parte extraída de layout.py)."""

from __future__ import annotations

from typing import Any

import streamlit as st

from ...helpers.helpers import extract_eap_items_for_policy
from ...infra.api import api_call


def _build_mob_policy_rows(eap_items: list, saved_policies: dict, ramp_up_enabled: bool) -> list[dict]:
    """Builds the policy rows from EAP items and saved policies."""
    rows: list[dict] = []
    for item in eap_items:
        item_id = str(item.get("item_id") or item.get("activity_id") or "")
        saved = saved_policies.get(item_id, {})
        n_max_saved = int(saved.get("n_maximo") or 1)
        n_ini_saved = int(saved.get("n_inicial") or 1) if ramp_up_enabled else n_max_saved
        rows.append(
            {
                "item_id": item_id,
                "descricao": str(item.get("descricao", ""))[:60],
                "cpu_id": str(item.get("cpu_id", "")),
                "quantitativo": float(item.get("quantitativo") or 0),
                "n_maximo": n_max_saved,
                "n_inicial": n_ini_saved,
                "taxa_mobilizacao": float(saved.get("taxa_mobilizacao") or 1.0),
                "_taxa_desmobilizacao": float(saved.get("taxa_desmobilizacao") or 0.0),
                "_semanas_plateau": saved.get("semanas_plateau"),
            }
        )
    return rows


def _extract_cpu_id_from_any_item(item: dict) -> str:
    """Extract cpu_id from canonical EAP contract."""
    if not isinstance(item, dict):
        return ""
    cpu_direct = item.get("cpu_id")
    if isinstance(cpu_direct, str):
        return cpu_direct.strip()
    return ""


def _load_eap_items_for_planning(project_id: str, base_url: str, actor: str) -> list[dict]:
    """Loads EAP items from project endpoint and normalizes cpu_id for planning UIs."""
    try:
        eap_resp = api_call(method="GET", path=f"/api/projects/{project_id}/eap", base_url=base_url, actor=actor)
    except Exception:
        return []
    rows: list[dict] = []
    for item in eap_resp.get("items") or []:
        if not isinstance(item, dict):
            continue
        cpu_id = _extract_cpu_id_from_any_item(item)
        if not cpu_id:
            continue
        normalized = dict(item)
        normalized["cpu_id"] = cpu_id
        rows.append(normalized)
    return rows


def _build_eap_items_from_saved_policies(saved_policies: dict) -> list[dict]:
    """Builds minimal EAP-like rows from saved mobilization policies when EAP is unavailable."""
    items: list[dict] = []
    for item_id in sorted(saved_policies.keys()):
        items.append(
            {
                "item_id": str(item_id),
                "descricao": "(item sem referência de EAP)",
                "cpu_id": "",
                "quantitativo": 0.0,
            }
        )
    return items


def _render_mob_rampdown_expander(rows: list[dict], project_id: str) -> None:
    """Renders the ramp-down controls expander and mutates rows in-place."""
    with st.expander("⚙️ Controles de desmobilização (ramp-down)", expanded=False):
        st.caption("Taxa de saída de equipes após o plateau e duração do plateau antes do ramp-down.")
        for i, row in enumerate(rows):
            adv_col1, adv_col2, adv_label = st.columns([2, 2, 4])
            adv_label.caption(f"{row['item_id']} — {row['descricao'][:40]}")
            rows[i]["_taxa_desmobilizacao"] = adv_col1.number_input(
                "Desmob./sem.",
                min_value=0.0,
                step=0.5,
                value=float(row["_taxa_desmobilizacao"]),
                key=f"desmob-{project_id}-{row['item_id']}",
            )
            plateau_val = adv_col2.number_input(
                "Plateau (sem.)",
                min_value=0,
                step=1,
                value=int(row["_semanas_plateau"] or 0),
                key=f"plateau-{project_id}-{row['item_id']}",
            )
            rows[i]["_semanas_plateau"] = int(plateau_val) if plateau_val > 0 else None


def _display_mob_validate_status(items: list, status_global: str) -> None:
    """Shows validate result status message."""
    if status_global == "OK":
        st.success("✅ Políticas válidas.")
    elif status_global == "AVISO":
        count = sum(1 for i in items if i.get("status") == "AVISO")
        st.warning(f"⚠️ {count} aviso(s).")
    else:
        count = sum(1 for i in items if i.get("status") == "ERRO")
        st.error(f"❌ {count} erro(s).")


def _build_mob_validate_table(items: list) -> list[dict]:
    """Builds the validation result table rows."""
    return [
        {
            "Código": i.get("codigo", ""),
            "Status": i.get("status", ""),
            "Mensagem": i.get("mensagem", ""),
            "Semanas est.": i.get("duration_weeks", "-"),
            "Pico equipes": i.get("peak_teams", "-"),
            "Completa": "✅" if i.get("is_complete") else ("⚠️" if i.get("is_complete") is False else "-"),
        }
        for i in items
    ]


def _handle_mob_validate(base_url: str, project_id: str, actor: str) -> None:
    """Handles the validate policies button logic."""
    try:
        result = api_call(
            method="POST",
            path=f"/api/projects/{project_id}/mobilizacao-policies/validate",
            base_url=base_url,
            actor=actor,
        )
        items = result.get("items", [])
        _display_mob_validate_status(items, result.get("status", "OK"))
        if items:
            st.dataframe(_build_mob_validate_table(items), width="stretch", hide_index=True)
    except Exception as exc:
        st.error(f"Erro na validação: {exc}")


def _build_mob_policy_item(er: dict, adv: dict, ramp_up_enabled: bool, ramp_down_enabled: bool) -> dict:
    """Builds policy_data dict for one mobilizacao item."""
    n_max = max(1, int(er.get("n_maximo") or 1))
    n_ini = min(max(1, int(er.get("n_inicial") or n_max)) if ramp_up_enabled else n_max, n_max)
    taxa_mob = max(0.1, float(er.get("taxa_mobilizacao") or 1.0)) if ramp_up_enabled else float(n_max)
    taxa_desmob = float(adv.get("_taxa_desmobilizacao") or 0.0) if ramp_down_enabled else 0.0
    semanas_plateau = adv.get("_semanas_plateau") if ramp_down_enabled else None
    return {
        "n_inicial": n_ini,
        "n_maximo": n_max,
        "taxa_mobilizacao": taxa_mob,
        "taxa_desmobilizacao": taxa_desmob,
        "semanas_plateau": semanas_plateau,
    }


def _process_mob_save_rows(
    edited_list: list,
    rows: list[dict],
    ramp_up_enabled: bool,
    ramp_down_enabled: bool,
    base_url: str,
    project_id: str,
    actor: str,
) -> tuple[int, list[str]]:
    """Processes all edited rows, POSTing each policy. Returns (count, errors)."""
    errors: list[str] = []
    count = 0
    for i, er in enumerate(edited_list):
        item_id = str(er.get("item_id") or "").strip()
        if not item_id:
            continue
        adv = rows[i] if i < len(rows) else {}
        policy_data = _build_mob_policy_item(er, adv, ramp_up_enabled, ramp_down_enabled)
        try:
            api_call(
                method="POST",
                path=f"/api/projects/{project_id}/mobilizacao-policies",
                base_url=base_url,
                payload={"item_id": item_id, "policy": policy_data},
                actor=actor,
            )
            count += 1
        except Exception as exc:
            errors.append(f"{item_id}: {exc}")
    return count, errors


def _handle_mob_save(
    edited_list: list[dict],
    rows: list[dict],
    ramp_up_enabled: bool,
    ramp_down_enabled: bool,
    base_url: str,
    project_id: str,
    actor: str,
) -> None:
    """Handles the save policies button logic."""
    count, errors = _process_mob_save_rows(
        edited_list, rows, ramp_up_enabled, ramp_down_enabled, base_url, project_id, actor
    )
    if errors:
        st.error(f"Erros ao salvar: {'; '.join(errors)}")
    else:
        st.success(f"✅ {count} política(s) salva(s). Clique em 🚀 Replanejar para aplicar.")


def _build_mob_policy_vis_rows(rows: list[dict], ramp_up_enabled: bool) -> tuple[dict, list[dict]]:
    """Builds column config and visible rows for the mob policy editor."""
    col_cfg: dict = {
        "item_id": st.column_config.TextColumn("Item ID", disabled=True, width="small"),
        "descricao": st.column_config.TextColumn("Descrição", disabled=True, width="large"),
        "cpu_id": st.column_config.TextColumn("CPU", disabled=True, width="small"),
        "quantitativo": st.column_config.NumberColumn("Qtd.", disabled=True, format="%.0f", width="small"),
        "n_maximo": st.column_config.NumberColumn("✏️ Máx. equipes", min_value=1, step=1, format="%.0f", width="small"),
    }
    if ramp_up_enabled:
        col_cfg["n_inicial"] = st.column_config.NumberColumn(
            "✏️ Inicial", min_value=1, step=1, format="%.0f", width="small"
        )
        col_cfg["taxa_mobilizacao"] = st.column_config.NumberColumn(
            "✏️ Mob./sem.", min_value=0.1, step=0.5, format="%.1f", width="small"
        )
    vis_keys = ["item_id", "descricao", "cpu_id", "quantitativo", "n_maximo"] + (
        ["n_inicial", "taxa_mobilizacao"] if ramp_up_enabled else []
    )
    main_rows = [{k: r[k] for k in vis_keys if k in r} for r in rows]
    return col_cfg, main_rows


def _fetch_mob_saved_policies(base_url: str, project_id: str, actor: str) -> dict:
    """Busca as políticas de mobilização salvas, com fallback vazio em caso de erro."""
    try:
        return api_call(
            method="GET",
            path=f"/api/projects/{project_id}/mobilizacao-policies",
            base_url=base_url,
            actor=actor,
        ).get("items", {})
    except Exception:
        return {}


def _resolve_mob_eap_items(reference: dict, saved_policies: dict, project_id: str, base_url: str, actor: str) -> list:
    """Resolve os itens de EAP para políticas de mobilização, com fallbacks sucessivos."""
    eap_items = extract_eap_items_for_policy(reference)
    if not eap_items:
        eap_items = _load_eap_items_for_planning(project_id, base_url, actor)
    if not eap_items and saved_policies:
        eap_items = _build_eap_items_from_saved_policies(saved_policies)
    return eap_items


def _render_mob_ramp_toggles(project_id: str) -> tuple[bool, bool]:
    """Renderiza os checkboxes de ramp-up/ramp-down e retorna seus estados."""
    ramp_col1, ramp_col2, _ = st.columns([2, 2, 4])
    ramp_up_enabled = ramp_col1.checkbox(
        "Ramp-up progressivo",
        value=True,
        key=f"ramp-up-{project_id}",
        help="Mobilização gradual: a equipe aumenta até o máximo ao ritmo definido. "
        "Desabilitado → todas as equipes implantadas na semana 0.",
    )
    ramp_down_enabled = ramp_col2.checkbox(
        "Ramp-down após plateau",
        value=False,
        key=f"ramp-dn-{project_id}",
        help="Desmobilização forçada após o plateau. "
        "Só necessário quando o equipamento/contrato tem data de saída obrigatória.",
    )
    return ramp_up_enabled, ramp_down_enabled


def _render_mob_policy_action_buttons(
    edited: Any,
    rows: list,
    ramp_up_enabled: bool,
    ramp_down_enabled: bool,
    base_url: str,
    project_id: str,
    actor: str,
    base_version: str | None,
) -> None:
    """Renderiza e trata os botões de validar/salvar/replanejar políticas de mobilização."""
    col_save, col_validate, col_replan = st.columns([2, 2, 1])
    if col_validate.button("🔍 Validar políticas", key=f"validate-policies-{project_id}"):
        _handle_mob_validate(base_url, project_id, actor)
    if col_save.button("💾 Salvar políticas", key=f"save-policies-{project_id}"):
        edited_list = (
            edited if isinstance(edited, list) else (edited.to_dict("records") if hasattr(edited, "to_dict") else [])
        )  # noqa: E501
        _handle_mob_save(edited_list, rows, ramp_up_enabled, ramp_down_enabled, base_url, project_id, actor)
    col_replan.write("")
    if col_replan.button("🚀 Replanejar", key=f"replan-wmp-{project_id}"):
        result = api_call(
            method="POST",
            path=f"/api/projects/{project_id}/runs/start",
            base_url=base_url,
            payload={"base_version": base_version, "fork_version": True, "use_saved_overrides": True},
            actor=actor,
        )
        st.success(f"✨ Replanejamento iniciado: {result.get('run_id')}")


def render_mobilizacao_policy_editor(
    base_url: str,
    project_id: str,
    actor: str,
    reference: dict,
    base_version: str | None,
) -> None:
    """Editor de políticas de mobilização (ADR-054)."""
    st.caption(
        "Defina a intenção operacional por atividade. O sistema simula a curva de equipes e "
        "deriva o horizonte de execução — não é necessário atingir o máximo se a produção acumulada "
        "cobrir o quantitativo antes."
    )
    saved_policies = _fetch_mob_saved_policies(base_url, project_id, actor)
    eap_items = _resolve_mob_eap_items(reference, saved_policies, project_id, base_url, actor)
    if not eap_items:
        st.info("Nenhum item de EAP com CPU encontrado na referência para configurar políticas.")
        return
    ramp_up_enabled, ramp_down_enabled = _render_mob_ramp_toggles(project_id)
    rows = _build_mob_policy_rows(eap_items, saved_policies, ramp_up_enabled)
    col_cfg, main_rows = _build_mob_policy_vis_rows(rows, ramp_up_enabled)
    edited = st.data_editor(
        main_rows,
        width="stretch",
        hide_index=True,
        column_config=col_cfg,
        disabled=["item_id", "descricao", "cpu_id", "quantitativo"],
        key=f"mob-policy-editor-{project_id}",
    )
    if ramp_down_enabled:
        _render_mob_rampdown_expander(rows, project_id)
    _render_mob_policy_action_buttons(
        edited, rows, ramp_up_enabled, ramp_down_enabled, base_url, project_id, actor, base_version
    )


