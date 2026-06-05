"""ADR-064: Contrato de formulários tipados — elimina edição de JSON bruto na UI.

Todo objeto de domínio editável na UI deve declarar:
  - EDITABLE_FIELDS:  campos que o usuário pode alterar (widget tipado)
  - READONLY_FIELDS:  campos exibidos mas não editáveis
  - INTERNAL_FIELDS:  campos ignorados na UI (hashes, timestamps de audit, etc.)

Uso:
    from concilium.presentation.ui.atoms.form_contracts import (
        FieldSpec, render_typed_form, CPU_EDITABLE_FIELDS, CPU_READONLY_FIELDS
    )
    payload = render_typed_form(cpu_data, CPU_EDITABLE_FIELDS, CPU_READONLY_FIELDS, key="cpu-edit")
    # payload é dict construído programaticamente — nunca json.loads(user_text)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import streamlit as st

WidgetKind = Literal[
    "text_input", "number_input", "selectbox", "multiselect", "checkbox", "text_area_plain", "data_editor", "color_hex"
]


@dataclass
class FieldSpec:
    """Especificação de um campo editável na UI."""

    label: str
    widget: WidgetKind = "text_input"
    min_value: float | int | None = None
    max_value: float | int | None = None
    step: float | int | None = None
    options: list[str] = field(default_factory=list)
    help: str = ""
    placeholder: str = ""
    # For data_editor columns
    columns: list[str] = field(default_factory=list)


# ─── Contratos por entidade de domínio ────────────────────────────────────────

# ADR-064 §D4: campos editáveis de uma CPU de catálogo
CPU_EDITABLE_FIELDS: dict[str, FieldSpec] = {
    "descricao": FieldSpec(
        label="Descrição",
        widget="text_input",
        placeholder="Descrição técnica da CPU",
    ),
    "unidade": FieldSpec(
        label="Unidade",
        widget="selectbox",
        options=["m³", "m²", "m", "un", "h", "t", "kg", "l", "km", "vb"],
        help="Unidade de medida do serviço",
    ),
    "categoria": FieldSpec(
        label="Categoria",
        widget="selectbox",
        options=[
            "TERRAPLENAGEM",
            "PAVIMENTACAO",
            "SANEAMENTO",
            "ESTRUTURAS",
            "DRENAGEM",
            "SINALIZACAO",
            "OBRAS_DE_ARTE",
            "DIVERSOS",
        ],
    ),
    "producao_id_ref": FieldSpec(
        label="ID de Produtividade",
        widget="text_input",
        placeholder="CPU-XXX-PROD-001",
        help="Referência à produtividade horária desta CPU",
    ),
    "composicao_itens": FieldSpec(
        label="Composição (itens de custo)",
        widget="data_editor",
        columns=["insumo_id", "coeficiente", "categoria_custo"],
    ),
}

# Campos exibidos read-only para contexto, sem widget de edição
CPU_READONLY_FIELDS: set[str] = {
    "codigo",
    "origem",
    "data_referencia_preco",
    "fonte_preco",
}

# Campos nunca mostrados na UI (internos / auditados)
CPU_INTERNAL_FIELDS: set[str] = {
    "historico_precos",
    "scd_version",
    "hash",
    "_id",
    "created_at",
    "updated_at",
    "precos_unitarios_sbdi",
}

# Constantes de categoria_custo usadas em composicao_itens
CATEGORIAS_CUSTO = ["MAO_OBRA", "EQUIPAMENTO", "MATERIAL", "DIESEL", "SERVICO"]

# ADR-065: campos editáveis de um TemaVisual
TEMA_EDITABLE_FIELDS: dict[str, FieldSpec] = {
    "empresa": FieldSpec(label="Nome da empresa", widget="text_input", placeholder="Ex: MendesLobo Construtora"),
    "perfil_exibicao": FieldSpec(
        label="Perfil de exibição",
        widget="selectbox",
        options=["EXECUTIVO", "SIMPLES", "TECNICO"],
        help="Controla densidade e nível de detalhe dos artefatos",
    ),
    # ── Cores ─────────────────────────────────────────────────────────────
    "cores.cabecalho_fundo": FieldSpec(label="Cabeçalho — fundo", widget="color_hex"),
    "cores.cabecalho_texto": FieldSpec(label="Cabeçalho — texto", widget="color_hex"),
    "cores.destaque": FieldSpec(label="Destaque", widget="color_hex"),
    "cores.zebra_impar": FieldSpec(label="Zebra — linha ímpar", widget="color_hex"),
    "cores.borda": FieldSpec(label="Bordas", widget="color_hex"),
    # ── Fontes ────────────────────────────────────────────────────────────
    "fontes.cabecalho": FieldSpec(
        label="Fonte cabeçalho",
        widget="selectbox",
        options=["Arial", "Helvetica", "Calibri", "Times New Roman", "Courier"],
    ),
    "fontes.corpo": FieldSpec(
        label="Fonte corpo", widget="selectbox", options=["Arial", "Helvetica", "Calibri", "Times New Roman", "Courier"]
    ),
    "fontes.tamanho_titulo": FieldSpec(
        label="Tamanho título (pt)", widget="number_input", min_value=10, max_value=24, step=1
    ),
    "fontes.tamanho_cabecalho": FieldSpec(
        label="Tamanho cabeçalho (pt)", widget="number_input", min_value=8, max_value=16, step=1
    ),
    "fontes.tamanho_corpo": FieldSpec(
        label="Tamanho corpo (pt)", widget="number_input", min_value=8, max_value=14, step=1
    ),
}

TEMA_READONLY_FIELDS: set[str] = {"id"}


# ─── Renderer genérico ────────────────────────────────────────────────────────


def _get_nested(obj: dict, dotted_key: str) -> Any:
    """Resolve chave dotted ('cores.destaque') em dict aninhado."""
    parts = dotted_key.split(".", 1)
    val = obj.get(parts[0])
    if len(parts) == 1 or not isinstance(val, dict):
        return val
    return _get_nested(val, parts[1])


def _set_nested(result: dict, dotted_key: str, value: Any) -> None:
    """Define valor em dict aninhado via chave dotted."""
    parts = dotted_key.split(".", 1)
    if len(parts) == 1:
        result[parts[0]] = value
    else:
        if parts[0] not in result or not isinstance(result[parts[0]], dict):
            result[parts[0]] = {}
        _set_nested(result[parts[0]], parts[1], value)


def _render_readonly_fields(obj: dict, readonly_fields: set) -> None:
    ro_present = {k: v for k, v in obj.items() if k in readonly_fields and v is not None}
    if not ro_present:
        return
    with st.expander("ℹ️ Campos de referência (read-only)", expanded=False):
        cols = st.columns(min(len(ro_present), 3))
        for i, (k, v) in enumerate(ro_present.items()):
            cols[i % 3].caption(k)
            cols[i % 3].text(str(v) if not isinstance(v, dict) else "…")


def _render_text_input_field(spec: FieldSpec, current_val: Any, fkey: str, result: dict, field_name: str) -> None:
    _set_nested(
        result,
        field_name,
        st.text_input(
            spec.label,
            value=str(current_val or ""),
            key=fkey,
            help=spec.help or None,
            placeholder=spec.placeholder or None,
        ),
    )


def _render_number_input_field(spec: FieldSpec, current_val: Any, fkey: str, result: dict, field_name: str) -> None:
    _set_nested(
        result,
        field_name,
        st.number_input(
            spec.label,
            value=float(current_val or 0.0),
            min_value=float(spec.min_value) if spec.min_value is not None else None,
            max_value=float(spec.max_value) if spec.max_value is not None else None,
            step=float(spec.step) if spec.step is not None else 0.1,
            key=fkey,
            help=spec.help or None,
        ),
    )


def _render_selectbox_field(spec: FieldSpec, current_val: Any, fkey: str, result: dict, field_name: str) -> None:
    options = spec.options or []
    current_str = str(current_val or "")
    idx = options.index(current_str) if current_str in options else 0
    _set_nested(
        result,
        field_name,
        st.selectbox(
            spec.label,
            options=options,
            index=idx,
            key=fkey,
            help=spec.help or None,
        ),
    )


def _render_multiselect_field(spec: FieldSpec, current_val: Any, fkey: str, result: dict, field_name: str) -> None:
    _set_nested(
        result,
        field_name,
        st.multiselect(
            spec.label,
            options=spec.options or [],
            default=current_val if isinstance(current_val, list) else [],
            key=fkey,
            help=spec.help or None,
        ),
    )


def _render_checkbox_field(spec: FieldSpec, current_val: Any, fkey: str, result: dict, field_name: str) -> None:
    _set_nested(
        result,
        field_name,
        st.checkbox(
            spec.label,
            value=bool(current_val),
            key=fkey,
            help=spec.help or None,
        ),
    )


def _render_text_area_field(spec: FieldSpec, current_val: Any, fkey: str, result: dict, field_name: str) -> None:
    _set_nested(
        result,
        field_name,
        st.text_area(
            spec.label,
            value=str(current_val or ""),
            key=fkey,
            help=spec.help or None,
        ),
    )


def _render_data_editor_dispatch(spec: FieldSpec, current_val: Any, fkey: str, result: dict, field_name: str) -> None:
    _render_data_editor_field(field_name, spec, current_val, fkey, result)


def _render_color_hex_field(spec: FieldSpec, current_val: Any, fkey: str, result: dict, field_name: str) -> None:
    current_hex = str(current_val or "FFFFFF").lstrip("#").upper()
    if len(current_hex) != 6:
        current_hex = "FFFFFF"
    picked = st.color_picker(
        spec.label,
        value=f"#{current_hex}",
        key=fkey,
        help=spec.help or "Hex 6 dígitos — ex: #1F4E78",
    )
    _set_nested(result, field_name, picked.lstrip("#").upper())


_FIELD_RENDERERS: dict[str, Any] = {
    "text_input": _render_text_input_field,
    "number_input": _render_number_input_field,
    "selectbox": _render_selectbox_field,
    "multiselect": _render_multiselect_field,
    "checkbox": _render_checkbox_field,
    "text_area_plain": _render_text_area_field,
    "data_editor": _render_data_editor_dispatch,
    "color_hex": _render_color_hex_field,
}


def render_typed_form(
    obj: dict[str, Any],
    editable_fields: dict[str, FieldSpec],
    readonly_fields: set[str] | None = None,
    key: str = "typed-form",
) -> dict[str, Any]:
    """Renderiza formulário tipado para um objeto de domínio.

    Suporta chaves dotted para campos aninhados (ex: 'cores.destaque').

    Returns:
        Dicionário com os valores atuais — construído programaticamente,
        nunca a partir de json.loads(user_text) (ADR-064).
    """
    result: dict[str, Any] = {}
    _render_readonly_fields(obj, readonly_fields or set())
    for field_name, spec in editable_fields.items():
        current_val = _get_nested(obj, field_name)
        fkey = f"{key}-{field_name.replace('.', '-')}"
        renderer = _FIELD_RENDERERS.get(spec.widget)
        if renderer:
            renderer(spec, current_val, fkey, result, field_name)
    return result


def _render_data_editor_field(
    field_name: str,
    spec: FieldSpec,
    current_val: Any,
    fkey: str,
    result: dict[str, Any],
) -> None:
    """Render a data_editor widget for list-of-dict fields."""
    rows = current_val if isinstance(current_val, list) else []
    columns = spec.columns

    st.caption(spec.label)

    # Build column config for composicao_itens
    col_cfg: dict[str, Any] = {}
    for col in columns:
        if col == "coeficiente":
            col_cfg[col] = st.column_config.NumberColumn("Coeficiente", min_value=0.0, step=0.001, format="%.4f")
        elif col == "categoria_custo":
            col_cfg[col] = st.column_config.SelectboxColumn(
                "Categoria de Custo", options=CATEGORIAS_CUSTO, required=True
            )
        else:
            col_cfg[col] = st.column_config.TextColumn(col.replace("_", " ").title())

    edited = st.data_editor(
        rows,
        column_config=col_cfg,
        num_rows="dynamic",
        use_container_width=True,
        key=fkey,
        hide_index=True,
    )
    _set_nested(result, field_name, edited if isinstance(edited, list) else [])
