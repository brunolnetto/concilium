"""Resolução centralizada de taxa de encargo social para insumos de MO.

Usada por skill-05 (MO direta) e skill-07 (MO indireta) para garantir
que a mesma lógica de precedência seja aplicada consistentemente.

Precedência (ADR-097 §D1/D2):
  1. encargo_override explícito (parâmetro)
  2. percentual_encargos_local no insumo (override item-level no catálogo)
  3. enc_horista / enc_mensalista conforme categoria_sindical
"""

from __future__ import annotations

from concilium.domain.constants import ENCARGOS_CLT, ENCARGOS_MENSALISTA


def resolver_encargo(
    atrib: dict,
    enc_horista: float = ENCARGOS_CLT,
    enc_mensalista: float = ENCARGOS_MENSALISTA,
    encargo_override=None,
) -> float:
    """Resolve taxa de encargo social para um atributo de insumo de MO.

    Retorna o multiplicador (ex: 1.777 para CLT horista). A aplicação
    sobre o salário-base (`salario * (1 + taxa)`) fica a cargo do caller.

    Args:
        atrib: dicionário `atributos_especificos` do insumo.
        enc_horista: taxa para horistas CLT (default: ENCARGOS_CLT).
        enc_mensalista: taxa para mensalistas (default: ENCARGOS_MENSALISTA).
        encargo_override: taxa explícita; se fornecida, ignora demais.
    """
    if encargo_override is not None:
        return float(encargo_override)
    enc_local = atrib.get("percentual_encargos_local")
    if enc_local is not None:
        return float(enc_local)
    categoria = (atrib.get("categoria_sindical") or "").lower()
    return enc_horista if categoria.startswith("horista") else (enc_mensalista or enc_horista)


def custo_ja_inclui_encargos(atrib: dict) -> bool:
    """Retorna True se `preco_unitario` do insumo já é all-in (ADR-097 D1).

    Fonte única de verdade: campo estruturado `metodo_custo_total` no catálogo.
    Substitui os mecanismos ad-hoc anteriores — texto livre em `nota`/`nota_encargos`
    (`"inclui encargos"`, replicado de forma divergente em 3 módulos) e a heurística
    implícita "unidade == 'h' → all-in" — por um único sinal explícito e auditável
    pelo JSON Schema (`insumo.schema.json#/$defs/atributosMaoObra`).

    Quando True, o caller deve usar o `preco_unitario` diretamente (multiplicador
    de encargo = 1.0) — aplicar `resolver_encargo()`/`alpha` por cima seria dupla
    contagem.
    """
    return atrib.get("metodo_custo_total") == "custo_total_ja_incluido"
