"""Helpers for catalogo_master_page (extracted)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

try:
    from ..atoms.form_contracts import CPU_EDITABLE_FIELDS, CPU_READONLY_FIELDS, render_typed_form
    from ..config import DEFAULT_ACTOR
    from ..infra.api import api_call
except ImportError:
    src_root = Path(__file__).resolve().parents[4]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from concilium.presentation.ui.atoms.form_contracts import (
        CPU_EDITABLE_FIELDS,
        CPU_READONLY_FIELDS,
        render_typed_form,
    )
    from concilium.presentation.ui.config import DEFAULT_ACTOR
    from concilium.presentation.ui.infra.api import api_call


def _cmb_workspace_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _cmb_catalog_root(catalog_id: str) -> Path:
    return _cmb_workspace_root() / "config" / "catalogos" / catalog_id


def _cmb_load_produtividades_index(catalog_id: str) -> dict[str, dict]:
    cache_key = f"master-produtividades-index-{catalog_id}"
    cached = st.session_state.get(cache_key)
    if isinstance(cached, dict):
        return cached

    index: dict[str, dict] = {}
    prod_dir = _cmb_catalog_root(catalog_id) / "produtividades"
    if prod_dir.exists():
        for prod_file in sorted(prod_dir.glob("*.json")):
            try:
                data = json.loads(prod_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            prod_id = str(data.get("id") or prod_file.stem).strip()
            if prod_id:
                index[prod_id] = data
            stem_id = prod_file.stem.strip()
            if stem_id:
                index.setdefault(stem_id, data)

    st.session_state[cache_key] = index
    return index


def _cmb_parse_insumo_file(insumo_file: Path) -> list:
    """Parse one insumo JSON file into a list of item dicts (empty on any mismatch)."""
    try:
        data = json.loads(insumo_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def _cmb_merge_insumo_items(index: dict[str, dict], items: list) -> None:
    """Merge parsed insumo items into ``index`` keyed by their ``codigo``."""
    for item in items:
        if not isinstance(item, dict):
            continue
        codigo = str(item.get("codigo") or "").strip()
        if codigo:
            index[codigo] = item


def _cmb_load_insumos_index(catalog_id: str) -> dict[str, dict]:
    cache_key = f"master-insumos-index-{catalog_id}"
    cached = st.session_state.get(cache_key)
    if isinstance(cached, dict):
        return cached

    index: dict[str, dict] = {}
    insumos_root = _cmb_catalog_root(catalog_id) / "insumos"
    if insumos_root.exists():
        for insumo_file in sorted(insumos_root.rglob("*.json")):
            _cmb_merge_insumo_items(index, _cmb_parse_insumo_file(insumo_file))

    st.session_state[cache_key] = index
    return index


def _cmb_regime_label(insumo: dict) -> str:
    categoria = str((insumo.get("atributos_especificos") or {}).get("categoria_sindical") or "").lower()
    if categoria.startswith("horista"):
        return "Horista"
    if categoria.startswith("mensalista"):
        return "Mensalista"
    return "—"


def _cmb_format_money(value: object) -> str:
    if not isinstance(value, (int, float, str)):
        return "—"
    try:
        return f"R$ {float(value):,.2f}"
    except Exception:
        return "—"


def _cmb_equipment_monthly_cost(insumo: dict) -> object:
    attrs = insumo.get("atributos_especificos") or {}
    for key in ("valor_locacao_mensal", "custo_mensal"):
        value = attrs.get(key)
        if value is not None:
            return value
    value = insumo.get("custo_mensal")
    if value is not None:
        return value
    preco = insumo.get("preco_unitario")
    horas_mes = attrs.get("horas_mes")
    try:
        if preco is not None and horas_mes is not None:
            return float(preco) * float(horas_mes)
    except Exception:
        pass
    return None


def _cmb_first_truthy(*values: object, default: object = "") -> object:
    """Return the first truthy value in ``values``, or ``default``.

    Colapsa cadeias `a or b or c or default` em uma única chamada.
    """
    for value in values:
        if value:
            return value
    return default


def _cmb_enrich_funcao_item(funcao: dict, insumo: dict, funcao_id: str) -> dict:
    descricao = _cmb_first_truthy(funcao.get("descricao"), insumo.get("descricao"), funcao.get("funcao"), funcao_id)
    return {
        **funcao,
        "descricao": descricao,
        "regime": funcao.get("regime") or _cmb_regime_label(insumo),
        "salario_base": funcao.get("salario_base") or insumo.get("preco_unitario"),
    }


def _cmb_enrich_funcoes(funcoes: list, catalog_id: str) -> list[dict]:
    insumos_index = _cmb_load_insumos_index(catalog_id)
    enriched: list[dict] = []
    for funcao in funcoes:
        if not isinstance(funcao, dict):
            continue
        funcao_id = str(funcao.get("funcao_id") or "").strip()
        insumo = insumos_index.get(funcao_id) or {}
        enriched.append(_cmb_enrich_funcao_item(funcao, insumo, funcao_id))
    return enriched


def _cmb_enrich_composicao_item(item: dict, insumo: dict) -> dict:
    attrs = insumo.get("atributos_especificos") or {}
    return {
        **item,
        "descricao": _cmb_first_truthy(item.get("descricao"), insumo.get("descricao")),
        "unidade": _cmb_first_truthy(item.get("unidade"), insumo.get("unidade")),
        "custo_mensal": item.get("custo_mensal") or attrs.get("valor_locacao_mensal") or insumo.get("custo_mensal"),
    }


def _cmb_enrich_composicao_itens(composicao: list, catalog_id: str) -> list[dict]:
    insumos_index = _cmb_load_insumos_index(catalog_id)
    enriched: list[dict] = []
    for item in composicao:
        if not isinstance(item, dict):
            continue
        insumo_id = str(item.get("insumo_id") or "").strip()
        insumo = insumos_index.get(insumo_id) or {}
        enriched.append(_cmb_enrich_composicao_item(item, insumo))
    return enriched


def _cmb_enrich_equipamentos(equipamentos: list, catalog_id: str) -> list[dict]:
    insumos_index = _cmb_load_insumos_index(catalog_id)
    enriched: list[dict] = []
    for equipamento in equipamentos:
        if not isinstance(equipamento, dict):
            continue
        equip_id = str(equipamento.get("equip_id") or "").strip()
        insumo = insumos_index.get(equip_id) or {}
        enriched.append(
            {
                **equipamento,
                "descricao": equipamento.get("descricao") or insumo.get("descricao") or "",
                "unidade": equipamento.get("unidade") or insumo.get("unidade") or "",
                "custo_mensal": equipamento.get("custo_mensal") or _cmb_equipment_monthly_cost(insumo),
            }
        )
    return enriched


def _cmb_resolve_equipe(cpu: dict, catalog_id: str) -> dict:
    equipe = cpu.get("equipe") or {}
    if equipe:
        return {
            **equipe,
            "funcoes": _cmb_enrich_funcoes(equipe.get("funcoes") or [], catalog_id),
        }
    prod_id_ref = str(cpu.get("producao_id_ref") or "").strip()
    if not prod_id_ref:
        return {}
    prod = _cmb_load_produtividades_index(catalog_id).get(prod_id_ref) or {}
    equipe_prod = prod.get("composicao_padrao_equipe") or {}
    return {
        **equipe_prod,
        "funcoes": _cmb_enrich_funcoes(equipe_prod.get("funcoes") or [], catalog_id),
    }


def _cmb_comp_badge(cpu: dict, catalog_id: str) -> str:
    """Build a short composition badge string (e.g. 'MO + EQ + MAT')."""
    parts: list[str] = []
    equipe = _cmb_resolve_equipe(cpu, catalog_id)
    if equipe.get("funcoes"):
        parts.append("MO")
    if equipe.get("equipamentos"):
        parts.append("EQ")
    abbr = {"MAO_OBRA": "MO", "EQUIPAMENTO": "EQ", "MATERIAL": "MAT", "DIESEL": "DIESEL", "SERVICO": "SERV"}
    for it in cpu.get("composicao_itens") or []:
        if isinstance(it, dict):
            mapped = abbr.get(it.get("categoria_custo", ""), "")
            if mapped and mapped not in parts:
                parts.append(mapped)
    return " + ".join(parts) if parts else "(sem composição)"


def _cmb_get_categorias(all_cpus: list) -> list:
    """Return sorted list of distinct non-empty categoria values."""
    return sorted({str(c.get("categoria") or "") for c in all_cpus if c.get("categoria")})


def _cmb_filter_cpus(all_cpus: list, q: str, sel_cats: list) -> list:
    """Filter CPUs by free-text q and selected categories."""
    filtered = all_cpus
    if q:
        q_lower = q.lower()
        filtered = [
            c
            for c in filtered
            if q_lower in (c.get("codigo") or "").lower() or q_lower in (c.get("descricao") or "").lower()
        ]
    if sel_cats:
        filtered = [c for c in filtered if c.get("categoria") in sel_cats]
    return filtered


def _cmb_build_cpu_rows(page_cpus: list, catalog_id: str) -> list:
    """Build the list-of-dicts used in the CPU dataframe."""
    return [
        {
            "Código": c.get("codigo", ""),
            "Descrição": (c.get("descricao") or "")[:55],
            "Unidade": c.get("unidade", ""),
            "Categoria": c.get("categoria", ""),
            "Prod. Hor.": c.get("producao_horaria") or "—",
            "Composição": _cmb_comp_badge(c, catalog_id),
        }
        for c in page_cpus
    ]


def _cmb_render_cpu_nav(page: int, n_pages: int, page_key: str, total: int, catalog_id: str) -> None:
    """Render centred pagination nav for the CPU browser."""
    info_html = (
        "<div style='text-align:center;padding:0.35rem 0;font-size:0.85rem;'>"
        f"<strong>{total}</strong> CPUs &nbsp;·&nbsp; página {page + 1}/{n_pages}"
        "</div>"
    )
    col_prev, col_info, col_next = st.columns([1, 5, 1])
    with col_prev:
        if page > 0 and st.button("←", key=f"master-cpu-prev-{catalog_id}", type="secondary", use_container_width=True):
            st.session_state[page_key] = page - 1
            st.rerun()
    col_info.markdown(info_html, unsafe_allow_html=True)
    with col_next:
        if page < n_pages - 1 and st.button(
            "→", key=f"master-cpu-next-{catalog_id}", type="secondary", use_container_width=True
        ):
            st.session_state[page_key] = page + 1
            st.rerun()


def _cmb_handle_cpu_selection(sel: list, page_cpus: list, base_url: str, actor: str, catalog_id: str) -> None:
    """Handle CPU row selection: show detail, edit button, composition dialog."""
    if sel:
        cpu = dict(page_cpus[sel[0]])
        cpu["equipe"] = _cmb_resolve_equipe(cpu, catalog_id)
        st.divider()
        _render_cpu_detail(base_url, actor, catalog_id, cpu)
        if st.button("✏️ Editar composição", key=f"open-comp-dialog-{cpu.get('codigo')}", type="secondary"):
            st.session_state[f"comp-dialog-cpu-{catalog_id}"] = cpu
        if st.session_state.get(f"comp-dialog-cpu-{catalog_id}", {}).get("codigo") == cpu.get("codigo"):
            _render_composition_dialog(base_url, actor, catalog_id, cpu)


def _cmb_render_equipe_expander(funcoes: list, equipamentos: list) -> None:
    """Render the team composition expander for a CPU."""
    if funcoes or equipamentos:
        with st.expander("⚙️ Composição de Equipe", expanded=True):
            if funcoes:
                st.caption("**Mão de obra**")
                funcoes_rows = list(funcoes)
                st.dataframe(
                    [
                        {
                            "Função": f.get("funcao_id", ""),
                            "Descrição": f.get("descricao", ""),
                            "Qtd": f.get("num_pessoas", 1),
                            "Reg.": f.get("regime", "—"),
                            "Salário base": _cmb_format_money(f.get("salario_base")),
                        }
                        for f in funcoes_rows
                        if isinstance(f, dict)
                    ],
                    hide_index=True,
                    use_container_width=True,
                )
            if equipamentos:
                st.caption("**Equipamentos**")
                equipamentos_rows = list(equipamentos)
                st.dataframe(
                    [
                        {
                            "Equipamento": e.get("equip_id", ""),
                            "Descrição": e.get("descricao", ""),
                            "Qtd": e.get("num_unidades", 1),
                            "Unid.": e.get("unidade", ""),
                            "Custo mensal": _cmb_format_money(e.get("custo_mensal")),
                        }
                        for e in equipamentos_rows
                        if isinstance(e, dict)
                    ],
                    hide_index=True,
                    use_container_width=True,
                )


def _cmb_render_composicao_expander(composicao: list) -> None:
    """Render the direct inputs expander for a CPU."""
    if composicao:
        with st.expander("🧱 Insumos Diretos", expanded=True):
            # Guia de categorias de custo como legenda estática (ADR-023)
            _cat_guide = " · ".join(f"**{k}** {v}" for k, v in _CAT_LABELS.items())
            st.caption(
                f"Categorias BDI: {_cat_guide}  \n"
                "A categoria define qual alíquota de BDI é aplicada; MO e EQ têm alíquotas diferentes."
            )
            composicao_rows = list(composicao)
            comp_rows = [
                {
                    "Insumo": it.get("insumo_id", ""),
                    "Descrição": it.get("descricao", ""),
                    "Coeficiente": it.get("coeficiente", 0),
                    "Unidade": it.get("unidade", ""),
                    "Categoria custo": it.get("categoria_custo", ""),
                }
                for it in composicao_rows
                if isinstance(it, dict)
            ]
            st.caption(f"{len(composicao_rows)} item(s)")
            st.dataframe(comp_rows, use_container_width=True, hide_index=True)


def _cmb_clear_catalog_cache(catalog_id: str) -> None:
    st.session_state.pop(f"master-produtividades-index-{catalog_id}", None)
    st.session_state.pop(f"master-insumos-index-{catalog_id}", None)


def _cmb_render_edit_expander(base_url: str, catalog_id: str, cpu: dict, codigo: str) -> None:
    """Render the master-catalog edit form expander for a CPU."""
    with st.expander("📝 Propriedades da CPU", expanded=False):
        edited = render_typed_form(cpu, CPU_EDITABLE_FIELDS, CPU_READONLY_FIELDS, key=f"master-cpu-edit-{codigo}")
        motivo = st.text_input("Motivo *", placeholder="Ex: Atualização pós-medição", key=f"master-cpu-motivo-{codigo}")
        col_save, col_hint = st.columns([2, 3])
        if col_save.button(
            "💾 Salvar no mestre", type="primary", key=f"master-cpu-save-{codigo}", disabled=not motivo.strip()
        ):
            payload = {**cpu, **edited}
            try:
                result = api_call(
                    "PUT",
                    f"/api/catalogs/{catalog_id}/cpus/{codigo}",
                    payload={"cpu_data": payload, "motivo": motivo},
                    base_url=base_url,
                    actor=DEFAULT_ACTOR,
                )
                st.success(f"✅ `{codigo}` salva. Bundle invalidado: {result.get('bundle_invalidated')}")
                st.session_state.pop(f"master-cpus-all-{catalog_id}", None)
                st.rerun()
            except Exception as exc:
                st.error(f"Erro: {exc}")
        col_hint.caption("Salva em `cpus/{codigo}.json` e invalida o bundle cache.")


def _cmb_filter_insumos(all_insumos: list, q: str) -> list:
    """Filter insumos by free-text query on codigo/descricao."""
    if not q:
        return all_insumos
    q_lower = q.lower()
    return [
        i
        for i in all_insumos
        if q_lower in (i.get("codigo") or "").lower() or q_lower in (i.get("descricao") or "").lower()
    ]


def _cmb_build_insumo_rows(page_items: list) -> list:
    """Build the list-of-dicts used in the insumo dataframe."""
    return [
        {
            "Código": ins.get("codigo") or ins.get("id", ""),
            "Descrição": (ins.get("descricao") or "")[:55],
            "Unidade": ins.get("unidade", ""),
            "Preço unit.": ins.get("preco_unitario") or "—",
            "Data ref.": (ins.get("data_referencia_preco") or "")[:10],
        }
        for ins in page_items
        if isinstance(ins, dict)
    ]


def _rcd_empty_editor(catalog_id: str, codigo: str):
    st.info("Nenhum insumo cadastrado. Use o botão abaixo para adicionar o primeiro item.")
    return st.data_editor(
        [{"insumo_id": "", "coeficiente": 1.0, "categoria_custo": "MATERIAL"}],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "insumo_id": st.column_config.TextColumn("ID do Insumo", width="large"),
            "coeficiente": st.column_config.NumberColumn(
                "Coeficiente", min_value=0.0, step=0.001, format="%.4f", width="medium"
            ),
            "categoria_custo": st.column_config.SelectboxColumn("Categoria", options=_CAT_OPTIONS, width="large"),
        },
        key=f"comp-editor-new-{catalog_id}-{codigo}",
    )


def _rcd_do_save(base_url: str, actor: str, catalog_id: str, codigo: str, cpu: dict, edited, motivo: str) -> None:
    new_items = edited.to_dict("records") if hasattr(edited, "to_dict") else list(edited or [])
    new_items = [it for it in new_items if it.get("insumo_id", "").strip()]
    updated_cpu = {**cpu, "composicao_itens": new_items}
    try:
        result = api_call(
            "PUT",
            f"/api/catalogs/{catalog_id}/cpus/{codigo}",
            payload={"cpu_data": updated_cpu, "motivo": motivo},
            base_url=base_url,
            actor=actor,
        )
        st.success(
            f"✅ Composição de `{codigo}` salva — {len(new_items)} item(s). "
            f"Bundle invalidado: {result.get('bundle_invalidated', True)}"
        )
        for k in list(st.session_state.keys()):
            if isinstance(k, str) and k.startswith("master-cpus-all-"):
                del st.session_state[k]
        st.session_state.pop(f"comp-dialog-cpu-{catalog_id}", None)
        st.rerun()
    except Exception as exc:
        st.error(f"Erro ao salvar: {exc}")


def _render_cpu_detail(base_url: str, actor: str, catalog_id: str, cpu: dict) -> None:
    codigo = cpu.get("codigo", "")
    st.subheader(f"`{codigo}` — {cpu.get('descricao', '')}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Unidade", cpu.get("unidade") or "—")
    col2.metric("Categoria", cpu.get("categoria") or "—")
    col3.metric("Produção horária", cpu.get("producao_horaria") or "—")
    col4.metric("Origem", cpu.get("origem") or "—")

    equipe = cpu.get("equipe") or _cmb_resolve_equipe(cpu, catalog_id)
    funcoes = equipe.get("funcoes") or []
    equipamentos = _cmb_enrich_equipamentos(equipe.get("equipamentos") or [], catalog_id)
    _cmb_render_equipe_expander(funcoes, equipamentos)

    composicao = _cmb_enrich_composicao_itens(cpu.get("composicao_itens") or [], catalog_id)
    _cmb_render_composicao_expander(composicao)

    _cmb_render_edit_expander(base_url, catalog_id, cpu, codigo)


_CAT_OPTIONS = ["MAO_OBRA", "EQUIPAMENTO", "MATERIAL", "DIESEL", "SERVICO"]


def _render_composition_dialog(base_url: str, actor: str, catalog_id: str, cpu: dict) -> None:
    """Editor detalhado de composicao_itens para uma CPU do catalogo mestre (ADR-064/067)."""
    codigo = cpu.get("codigo", "")
    composicao = list(cpu.get("composicao_itens") or [])

    st.markdown(
        f"### ✏️ Composição: `{codigo}`    <br><small>{cpu.get('descricao', '')[:80]}</small>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Edite os insumos que compõem esta CPU. O **coeficiente** representa a quantidade "
        "por unidade de serviço (ex: 1.0 L de emulsão por m²). "
        "Salvar grava em `config/catalogos/…` e invalida o bundle cache."
    )
    st.divider()

    # ── Tabela editável de composição ─────────────────────────────────────
    if composicao:
        st.caption(f"**{len(composicao)} item(s) na composição atual**")
        edited = st.data_editor(
            composicao,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "insumo_id": st.column_config.TextColumn(
                    "ID do Insumo",
                    help="Código do insumo (ex: MA-EMULSAO-RR-2C-IMPRIMACAO)",
                    width="large",
                ),
                "coeficiente": st.column_config.NumberColumn(
                    "Coeficiente",
                    help="Quantidade por unidade de serviço",
                    min_value=0.0,
                    step=0.001,
                    format="%.4f",
                    width="medium",
                ),
                "categoria_custo": st.column_config.SelectboxColumn(
                    "Categoria",
                    options=_CAT_OPTIONS,
                    help="Classificação do custo para BDI",
                    width="large",
                ),
            },
            key=f"comp-editor-{catalog_id}-{codigo}",
        )
    else:
        edited = _rcd_empty_editor(catalog_id, codigo)

    st.divider()
    motivo = st.text_input(
        "Motivo da alteração *",
        placeholder="Ex: Adição de emulsão pós-revisão de projeto",
        key=f"comp-motivo-{catalog_id}-{codigo}",
    )

    col_save, col_cancel = st.columns(2)
    if col_save.button(
        "💾 Salvar composição", type="primary", key=f"comp-save-{catalog_id}-{codigo}", disabled=not motivo.strip()
    ):
        _rcd_do_save(base_url, actor, catalog_id, codigo, cpu, edited, motivo)

    if col_cancel.button("Cancelar", type="secondary", key=f"comp-cancel-{catalog_id}-{codigo}"):
        st.session_state.pop(f"comp-dialog-cpu-{catalog_id}", None)
        st.rerun()


_CAT_LABELS = {
    "MAO_OBRA": "🧑‍🔧 Mão de Obra",
    "EQUIPAMENTO": "⚙️ Equipamento",
    "MATERIAL": "🧱 Material",
    "DIESEL": "⛽ Diesel / Combustível",
    "SERVICO": "📋 Serviço",
}
