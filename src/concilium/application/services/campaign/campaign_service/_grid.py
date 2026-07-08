"""ADR-070 — Campaign service (parte extraída de campaign_service.py)."""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
from typing import Any

from concilium.domain.models.campaign.campaign import GoResearchCampaignBundle

_PER_ITEM_PREFIX = "_per_item_:"
_CPU_ALT_PREFIX = "_cpu_alt_:"


def _expand_sweep_dims(bundle: GoResearchCampaignBundle) -> tuple[list[str], list[list]]:
    """Expande ParametroSweep em (keys, value_lists) prontos para itertools.product.

    - scope="global":         1 dimensão com k valores (comportamento original).
    - scope="per_item":       len(item_ids) dimensões, cada uma com k valores.
                              Chave interna: "_per_item_:{campo}:{item_id}"
    - scope="cpu_alternativo": idem, mas chave interna: "_cpu_alt_:{campo}:{item_id}"
    """
    keys: list[str] = []
    value_lists: list[list] = []

    for s in bundle.sweep:
        if s.scope in ("per_item", "cpu_alternativo") and s.item_ids:
            prefix = _PER_ITEM_PREFIX if s.scope == "per_item" else _CPU_ALT_PREFIX
            for iid in s.item_ids:
                keys.append(f"{prefix}{s.campo}:{iid}")
                value_lists.append(s.valores)
        else:
            # global (e cpu_alternativo sem item_ids — trata como global)
            keys.append(s.campo)
            value_lists.append(s.valores)

    return keys, value_lists


def gerar_grid(bundle: GoResearchCampaignBundle) -> list[tuple[dict, dict]]:
    """Returns list of (spec_variant, parametros_variados). Applies sweep.

    Suporta scope="global" (padrão), "per_item" e "cpu_alternativo".
    Para per_item e cpu_alternativo, cada item_id é uma dimensão independente
    → cardinalidade = k^len(item_ids) para aquele sweep.
    """
    if not bundle.sweep:
        return [(bundle.base_spec, {})]

    keys, value_lists = _expand_sweep_dims(bundle)

    results = []
    for combo in itertools.product(*value_lists):
        variados = dict(zip(keys, combo, strict=False))
        spec_v = _apply_overrides(copy.deepcopy(bundle.base_spec), variados)
        results.append((spec_v, variados))
    return results


def _apply_overrides(spec: dict, overrides: dict) -> dict:
    """Apply dot-path overrides. Supports nested paths with '.'.

    Chaves especiais ignoradas aqui (processadas em outro estágio):
      - "inputs_*"        → pós-carregamento via _apply_post_load_overrides
      - "_per_item_:*"    → pós-carregamento via _apply_post_load_overrides
      - "_cpu_alt_:*"     → pre-load, mas apenas para spec["spec"]["eap"] (ver abaixo)

    "restricoes_mercado" é tratado aqui como campo top-level (merge de dicts).
    "_cpu_alt_:*" modifica spec["spec"]["eap"][item_id].cpu_id diretamente.
    """
    for key_path, value in overrides.items():
        # Campos que começam com "inputs_" são aplicados APÓS o carregamento do spec
        # (via _apply_post_load_overrides). Ignorar aqui.
        if key_path.startswith("inputs_"):
            continue
        # per_item é resolvido no pós-carregamento
        if key_path.startswith(_PER_ITEM_PREFIX):
            continue
        # cpu_alternativo: modifica spec["spec"]["eap"] antes do carregamento
        if key_path.startswith(_CPU_ALT_PREFIX):
            _apply_cpu_alt_override(spec, key_path, value)
            continue

        parts = key_path.split(".")
        d = spec
        for part in parts[:-1]:
            if part not in d:
                d[part] = {}
            elif not isinstance(d[part], dict):
                d[part] = {}
            d = d[part]
        last = parts[-1]
        # Merge dict values instead of replacing (preserva campos existentes)
        if isinstance(value, dict) and isinstance(d.get(last), dict):
            d[last] = {**d[last], **value}
        else:
            d[last] = value
    return spec


def _apply_cpu_alt_override(spec: dict, key_path: str, value: str) -> None:
    """Substitui cpu_id no spec["spec"]["eap"] para o item_id extraído da chave.

    Formato de key_path: "_cpu_alt_:{campo}:{item_id}"
    onde campo pode ser "eap.cpu_id" ou qualquer variante com "cpu_id".
    """
    # Extrai item_id: é o sufixo após o último ":"
    suffix = key_path[len(_CPU_ALT_PREFIX) :]
    # suffix = "{campo}:{item_id}" — item_id não contém ":" por convenção
    last_colon = suffix.rfind(":")
    if last_colon < 0:
        return
    item_id = suffix[last_colon + 1 :]

    # Navega até a lista eap no spec
    eap_list = None
    # Suporta tanto spec dict plano quanto spec com chave "spec" aninhada
    if "spec" in spec and isinstance(spec["spec"], dict):
        eap_list = spec["spec"].get("eap")
    if eap_list is None:
        eap_list = spec.get("eap")
    if not isinstance(eap_list, list):
        return

    for item in eap_list:
        if isinstance(item, dict) and item.get("item_id") == item_id:
            item["cpu_id"] = value
            break


_NO_RESULT = object()


def _apply_scalar(existing: Any, value: Any) -> Any:
    """Aplica valor ou transformação escalar a um campo existente.

    Sintaxe de valor especial:
        {"__scale__": factor}   → multiplica o valor atual por factor (float)
        {"__add__": delta}      → soma delta ao valor atual (int/float)
        {"__frac_of__": "outro_campo", "__value__": frac}
            → não usado aqui; requer contexto adicional

    Qualquer outro dict faz merge; qualquer outro valor substitui.
    """
    if isinstance(value, dict):
        if "__scale__" in value and existing is not None:
            scaled = _apply_scale(existing, value["__scale__"])
            if scaled is not _NO_RESULT:
                return scaled
        if "__add__" in value and existing is not None:
            added = _apply_add(existing, value["__add__"])
            if added is not _NO_RESULT:
                return added
        # merge dict
        if isinstance(existing, dict):
            return {**existing, **value}
    return value


def _apply_scale(existing: Any, factor: Any) -> Any:
    import math as _math

    try:
        raw = float(existing) * float(factor)
        # Preserva tipo int quando o campo original era int
        if isinstance(existing, int):
            return max(1, int(_math.ceil(raw)))
        return round(raw, 4)
    except (TypeError, ValueError):
        return _NO_RESULT


def _apply_add(existing: Any, delta: Any) -> Any:
    try:
        raw = float(existing) + float(delta)
        return type(existing)(raw) if isinstance(existing, int) else round(raw, 4)
    except (TypeError, ValueError):
        return _NO_RESULT


def _set_path(d: Any, parts: list[str], value: Any) -> None:
    """Navega path (suporta [*] para listas) e aplica valor."""
    if not parts:
        return
    part = parts[0]
    rest = parts[1:]

    if part == "[*]":
        # Aplica a todos os itens de uma lista
        if isinstance(d, list):
            for item in d:
                _set_path(item, rest, value)
        return

    if not rest:
        # Folha: aplicar valor
        if isinstance(d, dict):
            d[part] = _apply_scalar(d.get(part), value)
        return

    # Intermediate node
    if isinstance(d, dict):
        if part not in d:
            d[part] = {} if rest[0] != "[*]" else []
        _set_path(d[part], rest, value)


def _apply_post_load_overrides(spec_obj: object, variados: dict) -> None:
    """Aplica overrides diretamente no ProjectSpec carregado.

    Suporta:
      - dot-path simples:    inputs_cronograma.rcpsp_spec.deadline_weeks
      - wildcard de lista:   inputs_cronograma.rcpsp_spec.activities.[*].ramp_params.n_max
      - valores escalares:   {"__scale__": 1.25} ou {"__add__": 2}
      - per_item:            chave "_per_item_:{campo_inputs}:{item_id}"
                             → aplica value apenas à activity com o item_id dado
    """
    for key_path, value in variados.items():
        if key_path.startswith(_PER_ITEM_PREFIX):
            _apply_per_item_post_load(spec_obj, key_path, value)
            continue
        if not key_path.startswith("inputs_"):
            continue
        parts = key_path.split(".")
        attr = parts[0]
        d = getattr(spec_obj, attr, None)
        if d is None:
            continue
        _set_path(d, parts[1:], value)


def _apply_per_item_post_load(spec_obj: object, key_path: str, value: Any) -> None:
    """Aplica override de per_item a uma única activity por item_id.

    Formato de key_path: "_per_item_:{campo_inputs}:{item_id}"
    onde campo_inputs é ex. "inputs_cronograma.rcpsp_spec.activities.[*].ramp_params.n_max"

    A função substitui o segmento "[*]" pelo filtro de item_id antes de navegar.
    Se o campo não contém "[*]", tenta localizar a activity pelo item_id na lista
    de atividades e aplicar o path relativo ao n_max (última parte do campo).
    """
    suffix = key_path[len(_PER_ITEM_PREFIX) :]
    last_colon = suffix.rfind(":")
    if last_colon < 0:
        return
    campo = suffix[:last_colon]
    item_id = suffix[last_colon + 1 :]

    if not campo.startswith("inputs_"):
        return

    parts = campo.split(".")
    attr = parts[0]
    d = getattr(spec_obj, attr, None)
    if d is None:
        return

    # Navega até a lista que contém [*]; quando encontrar, filtra pelo item_id
    # em vez de aplicar a todos os elementos.
    _set_path_per_item(d, parts[1:], value, item_id)


def _set_path_per_item_wildcard(d: Any, rest: list[str], value: Any, item_id: str) -> None:
    """Aplica _set_path apenas ao item de uma lista cujo item_id corresponde."""
    if isinstance(d, list):
        for item in d:
            if isinstance(item, dict) and item.get("item_id") == item_id:
                _set_path(item, rest, value)


def _set_path_per_item_intermediate(d: Any, part: str, rest: list[str], value: Any, item_id: str) -> None:
    """Navega para o próximo nó intermediário, criando-o se necessário."""
    if isinstance(d, dict):
        if part not in d:
            d[part] = {} if rest[0] != "[*]" else []
        _set_path_per_item(d[part], rest, value, item_id)


def _set_path_per_item(d: Any, parts: list[str], value: Any, item_id: str) -> None:
    """Como _set_path, mas quando encontra '[*]' filtra apenas o item com item_id."""
    if not parts:
        return
    part = parts[0]
    rest = parts[1:]

    if part == "[*]":
        _set_path_per_item_wildcard(d, rest, value, item_id)
        return

    if not rest:
        if isinstance(d, dict):
            d[part] = _apply_scalar(d.get(part), value)
        return

    _set_path_per_item_intermediate(d, part, rest, value, item_id)


def cenario_id(variados: dict) -> str:
    return hashlib.sha1(json.dumps(variados, sort_keys=True, default=str).encode()).hexdigest()[:10]


