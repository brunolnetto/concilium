"""Curação do catálogo — parte extraída de cure_schema.py (grupo _cure_insumo)."""

from __future__ import annotations

from ._core import CurationReport, _infer_tipo_contrato
from ._cure_cpu import _CPU_ONLY_FIELDS


def _cure_insumo_fonte_preco(changed: dict, codigo: object, report: CurationReport, apply: bool) -> None:
    if not changed.get("fonte_preco"):
        if apply:
            changed["fonte_preco"] = "catalogo_proprio"
        report.add_fixed(f"INSUMO {codigo}: preenchido fonte_preco='catalogo_proprio'")


def _cure_insumo_cpu_contamination(changed: dict, codigo: object, report: CurationReport, apply: bool) -> None:
    # Remove campos exclusivos de CPU que foram copiados para Insumo por engano
    cpu_contaminados = [k for k in _CPU_ONLY_FIELDS if k in changed]
    if cpu_contaminados:
        if apply:
            for k in cpu_contaminados:
                del changed[k]
        for k in cpu_contaminados:
            report.add_fixed(f"INSUMO {codigo}: removido campo exclusivo de CPU '{k}'")


def _cure_insumo_remove_derived_attrs(
    changed: dict, attrs: dict, keys: tuple[str, ...], codigo: object, report: CurationReport, apply: bool
) -> None:
    derivados = [k for k in keys if k in attrs]
    if derivados and apply:
        for k in derivados:
            del attrs[k]
        changed["atributos_especificos"] = attrs
    for k in derivados:
        report.add_fixed(f"INSUMO {codigo}: removido campo derivado atributos_especificos.{k}")


def _cure_insumo_padroniza_regime(
    attrs: dict, changed: dict, codigo: object, report: CurationReport, apply: bool
) -> None:
    # Padroniza regime de contratação para permitir cálculo consistente de encargos.
    regime = attrs.get("tipo_contrato")
    if regime not in {"CLT", "PJ"}:
        inferred = _infer_tipo_contrato(changed)
        if apply:
            attrs["tipo_contrato"] = inferred
        report.add_fixed(f"INSUMO {codigo}: preenchido tipo_contrato='{inferred}'")


def _cure_insumo_mao_obra(changed: dict, codigo: object, report: CurationReport, apply: bool) -> None:
    attrs = changed.get("atributos_especificos", {})
    if not isinstance(attrs, dict):
        attrs = {}
    _cure_insumo_padroniza_regime(attrs, changed, codigo, report, apply)
    # attrs já é garantidamente dict pela coerção acima (linha 406-407).
    _cure_insumo_remove_derived_attrs(changed, attrs, ("custo_com_encargos",), codigo, report, apply)
    if apply:
        changed["atributos_especificos"] = attrs


def _cure_insumo_remove_decomposicao_custo_hora_total(
    attrs: dict, codigo: object, report: CurationReport, apply: bool
) -> None:
    # Remove custo_hora_total de decomposicao_equip se presente
    decomp = attrs.get("decomposicao_equip")
    if isinstance(decomp, dict) and "custo_hora_total" in decomp:
        if apply:
            del decomp["custo_hora_total"]
        report.add_fixed(f"INSUMO {codigo}: removido decomposicao_equip.custo_hora_total (derivado da soma)")


def _cure_insumo_equipamento(changed: dict, codigo: object, report: CurationReport, apply: bool) -> None:
    attrs = changed.get("atributos_especificos", {})
    if not isinstance(attrs, dict):
        return
    _cure_insumo_remove_derived_attrs(
        changed, attrs, ("custo_manutencao_hora", "custo_produtivo_hora"), codigo, report, apply
    )
    _cure_insumo_remove_decomposicao_custo_hora_total(attrs, codigo, report, apply)


def cure_insumo(ins: dict, report: CurationReport, apply: bool) -> dict:
    codigo = ins.get("codigo", "<sem-codigo>")
    tipo = ins.get("tipo", "")
    changed = dict(ins)

    _cure_insumo_fonte_preco(changed, codigo, report, apply)
    _cure_insumo_cpu_contamination(changed, codigo, report, apply)

    # Remove campos derivados de MAO_OBRA
    if tipo == "MAO_OBRA":
        _cure_insumo_mao_obra(changed, codigo, report, apply)

    # Remove campos derivados de EQUIPAMENTO
    if tipo == "EQUIPAMENTO":
        _cure_insumo_equipamento(changed, codigo, report, apply)

    return changed if apply else ins


