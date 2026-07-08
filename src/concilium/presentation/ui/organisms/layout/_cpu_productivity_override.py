"""Camada de apresentação — layout Streamlit (parte extraída de layout.py)."""

from __future__ import annotations

import streamlit as st

from ...infra.api import api_call
from ._mobilizacao_policy import _extract_cpu_id_from_any_item, _load_eap_items_for_planning


def _extract_cpu_ids(reference: dict) -> set[str]:
    cpu_ids: set[str] = set()
    if not isinstance(reference, dict):
        return cpu_ids

    def _add_cpu(value: object) -> None:
        if isinstance(value, str) and value.strip():
            cpu_ids.add(value.strip())

    cpus_block = reference.get("cpus")
    if isinstance(cpus_block, dict):
        for item in cpus_block.get("itens_eap", []):
            if isinstance(item, dict):
                _add_cpu(item.get("cpu_id"))

    return cpu_ids


def _cpu_prod_resolve(cpu: dict, prod_lookup: dict) -> float:
    """Resolves producao_horaria for a CPU."""
    prod_id = cpu.get("producao_id_ref")
    if prod_id and prod_id in prod_lookup:
        return prod_lookup[prod_id]
    return float(cpu.get("producao_horaria") or 0.0)


def _build_cpu_prod_lookup(cat: dict) -> dict[str, float]:
    """Builds producao_id -> valor_horario lookup from catalog."""
    lookup: dict[str, float] = {}
    for _p in cat.get("producoes") or cat.get("produtividades") or []:
        if isinstance(_p, dict):
            pid = _p.get("id") or _p.get("codigo")
            val = _p.get("valor_horario") or _p.get("producao_horaria")
            if pid and val is not None:
                lookup[str(pid)] = float(val)
    return lookup


def _build_resolved_cpus(
    cpu_ids: list | set, catalog_cpus_prod: dict, base_url: str, project_id: str, actor: str
) -> dict[str, dict]:
    """Resolves CPU dicts from snapshot or API fallback."""
    resolved: dict[str, dict] = {}
    for cpu_id in sorted(cpu_ids):
        if cpu_id in catalog_cpus_prod:
            resolved[cpu_id] = dict(catalog_cpus_prod[cpu_id])
        else:
            try:
                resolved[cpu_id] = api_call(
                    method="GET",
                    path=f"/api/projects/{project_id}/catalog/cpus/{cpu_id}",
                    base_url=base_url,
                    actor=actor,
                ) or {"codigo": cpu_id}
            except Exception:
                resolved[cpu_id] = {"codigo": cpu_id}
    return resolved


def _find_changed_cpus(edited_rows: list) -> list[dict]:
    """Returns rows where producao_horaria changed."""
    return [
        r
        for r in edited_rows
        if abs(float(r.get("producao_horaria_nova") or 0.0) - float(r.get("producao_horaria_base") or 0.0)) > 1e-9
    ]


def _save_cpu_productivity(edited_rows: list[dict], base_url: str, project_id: str, actor: str) -> None:
    """Handles saving changed CPU productivity values."""
    changed = _find_changed_cpus(edited_rows)
    if not changed:
        st.info("Nenhuma alteração detectada.")
        return
    errors: list[str] = []
    for row in changed:
        cpu_id = str(row["cpu_id"])
        try:
            api_call(
                method="POST",
                path=f"/api/projects/{project_id}/catalog/cpus/{cpu_id}",
                base_url=base_url,
                payload={"producao_horaria": float(row["producao_horaria_nova"])},
                actor=actor,
            )
        except Exception as exc:
            errors.append(f"{cpu_id}: {exc}")
    if errors:
        st.error(f"Erros ao salvar: {'; '.join(errors)}")
    else:
        st.success(f"Produtividade salva para {len(changed)} CPU(s). Re-execute o pipeline para aplicar.")


def _resolve_cpu_ids_with_fallback(reference: dict, base_url: str, project_id: str, actor: str) -> list:
    """Resolves cpu_ids from reference or EAP fallback."""
    cpu_ids = list(_extract_cpu_ids(reference))
    if not cpu_ids:
        eap_rows = _load_eap_items_for_planning(project_id, base_url, actor)
        cpu_ids = list({_extract_cpu_id_from_any_item(it) for it in eap_rows if _extract_cpu_id_from_any_item(it)})
    return cpu_ids


def _catalog_cpus_by_codigo(cat: dict) -> dict[str, dict]:
    """Returns a codigo->cpu dict from the catalog cpus list."""
    return {str(c.get("codigo") or ""): c for c in (cat.get("cpus") or []) if isinstance(c, dict) and c.get("codigo")}


def _process_comp_row(
    row: dict,
    orig_funcoes: dict,
    orig_equips: dict,
    orig_itens: dict,
    new_funcoes: list,
    new_equipamentos: list,
    new_composicao: list,
) -> None:
    """Classifies one edited composition row and appends to appropriate list."""
    tipo = str(row.get("tipo", ""))
    rid = str(row.get("id", ""))
    qty = float(row.get("quantidade") or 0.0)
    if tipo == "MÃO_OBRA":
        entry = dict(orig_funcoes.get(rid, {"funcao_id": rid}))
        entry["num_pessoas"] = max(0, int(round(qty)))
        new_funcoes.append(entry)
    elif tipo == "EQUIPAMENTO":
        entry = dict(orig_equips.get(rid, {"equip_id": rid}))
        entry["num_unidades"] = max(0, int(round(qty)))
        new_equipamentos.append(entry)
    else:
        entry = dict(orig_itens.get(rid, {"insumo_id": rid, "categoria_custo": tipo}))
        entry["coeficiente"] = qty
        new_composicao.append(entry)


def render_cpu_productivity_override(base_url: str, project_id: str, actor: str) -> None:
    """Override de produtividade das CPUs — edita apenas producao_horaria."""
    st.caption("Edite apenas a produção horária de cada CPU. Demais atributos são somente leitura.")
    try:
        reference = api_call(
            method="GET", path=f"/api/projects/{project_id}/benchmark-reference", base_url=base_url, actor=actor
        )
    except Exception:
        reference = {}
    cpu_ids = _resolve_cpu_ids_with_fallback(reference, base_url, project_id, actor)
    if not cpu_ids:
        st.info("Nenhuma CPU encontrada. Execute o pipeline ou adicione itens à EAP.")
        return
    _cat = reference.get("catalog") or {}
    catalog_cpus_prod = _catalog_cpus_by_codigo(_cat)
    prod_lookup = _build_cpu_prod_lookup(_cat)
    resolved = _build_resolved_cpus(cpu_ids, catalog_cpus_prod, base_url, project_id, actor)
    rows = [
        {
            "cpu_id": cpu_id,
            "descricao": resolved[cpu_id].get("descricao", ""),
            "unidade": resolved[cpu_id].get("unidade", ""),
            "producao_id_ref": resolved[cpu_id].get("producao_id_ref", "—"),
            "producao_horaria_base": _cpu_prod_resolve(resolved[cpu_id], prod_lookup),
            "producao_horaria_nova": _cpu_prod_resolve(resolved[cpu_id], prod_lookup),
        }
        for cpu_id in sorted(resolved)
    ]
    edited = st.data_editor(
        rows,
        width="stretch",
        hide_index=True,
        column_config={
            "cpu_id": st.column_config.TextColumn("CPU", disabled=True, width="medium"),
            "descricao": st.column_config.TextColumn("Descrição", disabled=True, width="large"),
            "unidade": st.column_config.TextColumn("Un.", disabled=True, width="small"),
            "producao_id_ref": st.column_config.TextColumn("Prod. ID", disabled=True, width="medium"),
            "producao_horaria_base": st.column_config.NumberColumn("Base (un/h)", disabled=True, format="%.2f"),
            "producao_horaria_nova": st.column_config.NumberColumn(
                "✏️ Nova prod./hora", format="%.2f", step=0.5, min_value=0.0
            ),
        },
        disabled=["cpu_id", "descricao", "unidade", "producao_id_ref", "producao_horaria_base"],
        key=f"cpu-prod-editor-{project_id}",
    )
    if st.button("Salvar produtividade das CPUs", key=f"save-cpu-prod-{project_id}", type="primary"):
        edited_rows = (
            edited if isinstance(edited, list) else (edited.to_dict("records") if hasattr(edited, "to_dict") else [])
        )  # noqa: E501
        _save_cpu_productivity(edited_rows, base_url, project_id, actor)


