"""Curação do catálogo — parte extraída de cure_schema.py (grupo _cure_cpu)."""

from __future__ import annotations

from ._core import CurationReport


def _cure_cpu_dmt_fields(changed: dict, codigo: object, report: CurationReport, apply: bool) -> None:
    # Move dmt_referencia_m do root para atributos_categoria (campo mal posicionado)
    dmt_root_fields = {
        k: v for k, v in changed.items() if k in ("dmt_referencia_m", "dmt_min_metros", "dmt_max_metros")
    }
    if not dmt_root_fields:
        return
    if apply:
        attrs_cat = dict(changed.get("atributos_categoria") or {})
        for k, v in dmt_root_fields.items():
            attrs_cat[k] = v
            del changed[k]
        changed["atributos_categoria"] = attrs_cat
    for k in dmt_root_fields:
        report.add_fixed(f"CPU {codigo}: movido '{k}' do root para atributos_categoria")


def cure_cpu(cpu: dict, report: CurationReport, apply: bool) -> dict:
    codigo = cpu.get("codigo", "<sem-codigo>")
    changed = dict(cpu)

    _cure_cpu_dmt_fields(changed, codigo, report, apply)

    # Remove campos deprecated do root de CPU
    for campo in ("fonte_preco", "data_referencia_preco"):
        if campo in changed:
            if apply:
                del changed[campo]
            report.add_fixed(f"CPU {codigo}: removido campo deprecated '{campo}'")

    return changed if apply else cpu


_CPU_ONLY_FIELDS = {
    "atributos_categoria",
    "cpu_referencia_id",
    "producao_id_ref",
    "composicao_itens",
    "custo_direto_unitario_planilha",
    "precos_unitarios_sbdi",
}


