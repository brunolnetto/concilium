"""Curação do catálogo — parte extraída de cure_schema.py (grupo _cure_contextual)."""

from __future__ import annotations

import json
import re
from statistics import median

from ._core import (
    CurationReport,
    _categoria_custo_from_tipo,
    _index_by_str_key,
    _is_valid_insumo_code,
    _normalize_code,
    _robust_bounds,
    _team_is_empty,
)
from ._remap import _apply_insumo_code_remap


def _cure_contextual_inherit_cap_templates(prods: list[dict], report: CurationReport, apply: bool) -> None:
    # 0) Corrigir equipes vazias em produções CAP por mapeamento explícito de template
    prod_by_id = _index_by_str_key(prods, "id")
    cap_team_template_map = {
        "CPU-DREN-BOCA-BDCAP-100-PROD-001": "CPU-DREN-BOCA-BDTC-100-PROD-001",
        "CPU-DREN-BOCA-BSCAP-100-PROD-001": "CPU-DREN-BOCA-BSTC-100-PROD-001",
        "CPU-DREN-BOCA-BTCAP-100-PROD-001": "CPU-DREN-BOCA-BTCC-300X300-PROD-001",
        "CPU-DREN-CORPO-BDCAP-100-PROD-001": "CPU-DREN-CORPO-BDTC-100-PA1-PROD-001",
        "CPU-DREN-CORPO-BSCAP-100-PROD-001": "CPU-DREN-CORPO-BSTC-100-PA1-PROD-001",
        "CPU-DREN-CORPO-BTCAP-100-PROD-001": "CPU-DREN-CORPO-BTCC-100-PROD-001",
    }
    for target_id, source_id in cap_team_template_map.items():
        target = prod_by_id.get(target_id)
        source = prod_by_id.get(source_id)
        if not isinstance(target, dict) or not isinstance(source, dict):
            continue
        target_team = target.get("composicao_padrao_equipe")
        source_team = source.get("composicao_padrao_equipe")
        if not _team_is_empty(target_team) or _team_is_empty(source_team):
            continue
        if apply:
            target["composicao_padrao_equipe"] = json.loads(json.dumps(source_team))
        report.add_fixed(f"PRODUCAO {target_id}: equipe herdada de template {source_id}")


def _cure_contextual_fill_valor_horario_de_prod(
    prod: dict, pid: str, prod_by_id: dict[str, dict], report: CurationReport, apply: bool
) -> None:
    if prod.get("valor_horario") is not None:
        return
    m = re.match(r"^CPU-([A-Z0-9]+)-(.+)-PROD-([0-9]+)$", pid)
    if not m:
        return
    candidate_id = f"PROD-{m.group(2)}-{m.group(3)}"
    candidate = prod_by_id.get(candidate_id)
    candidate_val = (candidate or {}).get("valor_horario") if isinstance(candidate, dict) else None
    if candidate_val is None:
        return
    if apply:
        prod["valor_horario"] = candidate_val
    report.add_fixed(f"PRODUCAO {pid}: valor_horario herdado de {candidate_id}")


def _cure_contextual_fill_valor_horario_equivalente(prods: list[dict], report: CurationReport, apply: bool) -> None:
    # 1) Preencher valor_horario faltante via produção equivalente PROD-*
    prod_by_id = _index_by_str_key(prods, "id")
    for prod in prods:
        if not isinstance(prod, dict):
            continue
        pid = prod.get("id")
        if not isinstance(pid, str):
            continue
        _cure_contextual_fill_valor_horario_de_prod(prod, pid, prod_by_id, report, apply)


def _cure_contextual_dedupe_normalized_code(new_code: str, old_code: str, used_codes: set[str]) -> str:
    if new_code in used_codes and new_code != old_code:
        salt = 1
        base = new_code
        while new_code in used_codes and new_code != old_code:
            suffix = f"-{salt}"
            new_code = (base[: 40 - len(suffix)] + suffix)[:40]
            salt += 1
    return new_code


def _cure_contextual_normalize_insumo_codes(
    cpus: list[dict], prods: list[dict], insumos: list[dict], report: CurationReport, apply: bool
) -> None:
    # 2) Normalizar códigos de insumo inválidos e propagar remapeamento
    remap: dict[str, str] = {}
    used_codes: set[str] = set()
    for ins in insumos:
        if isinstance(ins, dict) and isinstance(ins.get("codigo"), str):
            used_codes.add(ins["codigo"])

    for ins in insumos:
        if not isinstance(ins, dict):
            continue
        old_code = ins.get("codigo")
        if not isinstance(old_code, str) or _is_valid_insumo_code(old_code):
            continue
        new_code = _cure_contextual_dedupe_normalized_code(_normalize_code(old_code), old_code, used_codes)
        remap[old_code] = new_code
        used_codes.add(new_code)
        if apply:
            ins["codigo"] = new_code
        report.add_fixed(f"INSUMO {old_code}: codigo normalizado para {new_code}")

    _apply_insumo_code_remap(cpus, prods, remap)


def _cure_contextual_sintetiza_composicao_via_equipe(
    cpu: dict,
    codigo: str,
    insumo_by_code: dict[str, dict],
    prod_by_id: dict[str, dict],
    report: CurationReport,
    apply: bool,
) -> None:
    """ADR-138: composicao_itens agora é escopo exclusivo de MATERIAL/DIESEL.

    Antes desta ADR, quando não havia candidato MATERIAL único (`MA-{codigo}`),
    esta função sintetizava linhas MAO_OBRA/EQUIPAMENTO em `composicao_itens` a
    partir de `Producao.composicao_padrao_equipe` — exatamente a redundância que
    ADR-138 remove (MAO_OBRA/EQUIPAMENTO agora só têm fonte confiável ali, nunca
    em `composicao_itens`). Não há, hoje, um caminho equivalente de síntese para
    MATERIAL/DIESEL a partir da equipe (`MaterialEquipe` é consumo horário
    operacional, não BOM por unidade de produto — ADR-138 Fase 2 pendente), então
    esta função apenas registra a lacuna para revisão manual/econômica.
    """
    report.add_manual(f"CPU {codigo}: composicao_itens vazia sem candidato único de insumo")
    report.add_skipped(f"CPU {codigo}: composicao_itens vazia (permitido no schema; revisar economicamente depois)")


def _cure_contextual_fill_composicao_itens_vazia(
    cpu: dict,
    codigo: str,
    insumo_by_code: dict[str, dict],
    prod_by_id: dict[str, dict],
    report: CurationReport,
    apply: bool,
) -> None:
    candidates = [f"MA-AGIS-{codigo}", f"MA-{codigo}"]
    found = [c for c in candidates if c in insumo_by_code]
    if len(found) != 1:
        _cure_contextual_sintetiza_composicao_via_equipe(cpu, codigo, insumo_by_code, prod_by_id, report, apply)
        return

    insumo_id = found[0]
    tipo = (insumo_by_code.get(insumo_id) or {}).get("tipo")
    novo_item = {
        "insumo_id": insumo_id,
        "coeficiente": 1.0,
        "categoria_custo": _categoria_custo_from_tipo(tipo if isinstance(tipo, str) else None),
    }
    if apply:
        cpu["composicao_itens"] = [novo_item]
    report.add_fixed(f"CPU {codigo}: composicao_itens preenchida automaticamente com {insumo_id}")


def _cure_contextual_autofill_composicao_itens(
    cpus: list[dict], prods: list[dict], insumos: list[dict], report: CurationReport, apply: bool
) -> None:
    # 3) Auto-preencher composicao_itens vazia quando houver insumo candidato inequívoco
    insumo_by_code = _index_by_str_key(insumos, "codigo")
    prod_by_id = _index_by_str_key(prods, "id")
    for cpu in cpus:
        if not isinstance(cpu, dict):
            continue
        codigo = cpu.get("codigo")
        itens = cpu.get("composicao_itens")
        if not isinstance(codigo, str) or not isinstance(itens, list) or itens:
            continue
        _cure_contextual_fill_composicao_itens_vazia(cpu, codigo, insumo_by_code, prod_by_id, report, apply)


def _cure_contextual_valor_horario_row(cpu: dict, prod_by_id: dict[str, dict]) -> dict | None:
    codigo = cpu.get("codigo")
    if not isinstance(codigo, str):
        return None
    categoria = cpu.get("categoria")
    unidade = cpu.get("unidade")
    prod_ref = cpu.get("producao_id_ref")
    if not isinstance(prod_ref, str) or not prod_ref:
        return None
    prod = prod_by_id.get(prod_ref)
    if not isinstance(prod, dict):
        return None
    raw_valor_horario = prod.get("valor_horario")
    if raw_valor_horario is None:
        return None
    try:
        valor_horario = float(raw_valor_horario)
    except (TypeError, ValueError):
        return None
    if valor_horario <= 0:
        return None
    return {
        "cpu_codigo": codigo,
        "categoria": str(categoria or "SEM_CATEGORIA"),
        "unidade": str(unidade or "SEM_UNIDADE"),
        "producao_id_ref": prod_ref,
        "valor_horario": valor_horario,
    }


def _cure_contextual_build_valor_horario_rows(cpus: list[dict], prods: list[dict]) -> list[dict]:
    prod_by_id = _index_by_str_key(prods, "id")
    rows: list[dict] = []
    for cpu in cpus:
        if not isinstance(cpu, dict):
            continue
        row = _cure_contextual_valor_horario_row(cpu, prod_by_id)
        if row is not None:
            rows.append(row)
    return rows


def _cure_contextual_fix_outlier_group(
    key: tuple[str, str],
    items: list[dict],
    prod_by_id: dict[str, dict],
    report: CurationReport,
    apply: bool,
) -> None:
    values = [float(r["valor_horario"]) for r in items if float(r["valor_horario"]) > 0]
    bounds = _robust_bounds(values, non_negative=True)
    if bounds is None:
        return
    med = float(median(values))
    low, high = bounds

    for item in items:
        current = float(item["valor_horario"])
        if low <= current <= high:
            continue
        # Não há checagem residual `current == med` aqui: `_robust_bounds` garante
        # low <= q10 <= med <= q90 <= high, logo `med` está sempre dentro de
        # [low, high] — se chegamos até aqui é porque `current` já está fora dos
        # limites, então `current == med` é matematicamente impossível.

        # Evita sobrecorreção: atua apenas em desvios realmente extremos.
        # - baixo extremo: abaixo de 50% do limite inferior
        # - alto extremo: acima de 200% do limite superior
        # Nota: `current` é sempre > 0 (filtrado na montagem de `rows` acima) e a
        # checagem em `low <= current <= high` já garante que current está fora dos
        # limites aqui — logo é sempre current < low (o que implica low > 0, já que
        # current > 0) ou current > high, nunca nenhum dos dois. Por isso usamos
        # if/else exaustivo (em vez de if/elif com um terceiro caminho residual
        # inatingível, que seria código morto e nunca coberto por testes).
        if current < low:
            if current >= low * 0.5:
                continue
        else:
            if current <= high * 2.0:
                continue

        prod_ref = item["producao_id_ref"]
        cpu_codigo = item["cpu_codigo"]
        if apply:
            # `item` só entra em `rows`/`items` quando `prod_by_id.get(prod_ref)`
            # já foi validado como dict (linhas acima) — prod_by_id não é mutado
            # entre as duas passagens, então o lookup aqui é sempre um dict.
            prod_by_id[prod_ref]["valor_horario"] = med
        report.add_fixed(
            "PRODUCAO "
            f"{prod_ref}: valor_horario {current:.6f} -> {med:.6f} "
            f"(CPU {cpu_codigo}, grupo {key[0]}/{key[1]}, IQR {low:.6f}..{high:.6f})"
        )


def _cure_contextual_fix_produtividade_outliers(
    cpus: list[dict], prods: list[dict], report: CurationReport, apply: bool
) -> None:
    # 4) Corrigir outliers de produtividade para mediana do grupo (categoria/unidade)
    prod_by_id = _index_by_str_key(prods, "id")
    rows = _cure_contextual_build_valor_horario_rows(cpus, prods)

    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        key = (row["categoria"], row["unidade"])
        grouped.setdefault(key, []).append(row)

    for key, items in grouped.items():
        _cure_contextual_fix_outlier_group(key, items, prod_by_id, report, apply)


def cure_contextual(
    cpus: list[dict], prods: list[dict], insumos: list[dict], report: CurationReport, apply: bool
) -> None:
    _cure_contextual_inherit_cap_templates(prods, report, apply)
    _cure_contextual_fill_valor_horario_equivalente(prods, report, apply)
    _cure_contextual_normalize_insumo_codes(cpus, prods, insumos, report, apply)
    _cure_contextual_autofill_composicao_itens(cpus, prods, insumos, report, apply)
    _cure_contextual_fix_produtividade_outliers(cpus, prods, report, apply)


