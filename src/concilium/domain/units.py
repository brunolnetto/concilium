"""Registro canônico de unidades de medida para o domínio de engenharia civil.

Este módulo é a única fonte de verdade sobre unidades aceitas no catálogo.

Regras
------
1. Cada unidade tem uma forma canônica em minúsculas (ex: "m²", "m³", "unid").
2. ALIAS_UNIDADES mapeia todas as variantes aceitas -> canônica.
   Usado pelo field_validator dos modelos, transparente para quem grava JSON.
3. normalize_unidade() é a função de normalização; lança ValueError para
   unidades desconhecidas.
4. Para adicionar uma nova unidade válida, basta incluí-la em UNIDADES_CANONICAS
   (e aliases em ALIAS_UNIDADES se necessário).

Unidades canônicas
------------------
  Comprimento  : m, km
  Área         : m²
  Volume       : m³
  Tempo (insumo): h, mes
  Massa        : t, kg
  Volume liq.  : l
  Contagem     : unid
  Embalagem    : sc          (saco — ex: cimento)
  Especial CPU : vb          (verba — serviços lump-sum)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Unidades canônicas (forma aceita nos JSONs após normalização)
# ---------------------------------------------------------------------------
UNIDADES_CANONICAS: frozenset[str] = frozenset(
    {
        # comprimento
        "m",
        "km",
        # área
        "m²",
        # volume sólido
        "m³",
        # tempo
        "h",
        "mes",
        # massa
        "t",
        "kg",
        # volume líquido
        "l",
        # contagem
        "unid",
        # embalagem
        "sc",
        # verba (serviço lump-sum, ex: mobilização)
        "vb",
    }
)

# ---------------------------------------------------------------------------
# Mapa de aliases -> canônica
# (todas as variantes que a planilha pode gerar)
# ---------------------------------------------------------------------------
ALIAS_UNIDADES: dict[str, str] = {
    # maiúsculas simples
    "M": "m",
    "KM": "km",
    "M²": "m²",
    "M2": "m²",
    "m2": "m²",
    "M³": "m³",
    "M3": "m³",
    "m3": "m³",
    "H": "h",
    "T": "t",
    "KG": "kg",
    "L": "l",
    "LT": "l",
    "lt": "l",
    "SC": "sc",
    "VB": "vb",
    # variantes de "unidade"
    "UNID": "unid",
    "UND": "unid",
    "und": "unid",
    "UN": "unid",
    "un": "unid",
    "Un": "unid",
    "Unid": "unid",
    # mês
    "MES": "mes",
    "MÊS": "mes",
    "mês": "mes",
    "Mes": "mes",
    # hora
    "hr": "h",
    "HR": "h",
    "hs": "h",
    "HS": "h",
}


# ---------------------------------------------------------------------------
# Função pública
# ---------------------------------------------------------------------------


def normalize_unidade(value: str) -> str:
    """Normaliza uma string de unidade para a forma canônica.

    Já canônica -> retorna como está.
    Alias conhecido -> retorna canônica.
    Desconhecida -> levanta ValueError.

    Examples
    --------
    >>> normalize_unidade("M²")
    'm²'
    >>> normalize_unidade("UNID")
    'unid'
    >>> normalize_unidade("m³")
    'm³'
    >>> normalize_unidade("foobar")
    ValueError: Unidade desconhecida: 'foobar'. ...
    """
    v = value.strip()
    if v in UNIDADES_CANONICAS:
        return v
    if v in ALIAS_UNIDADES:
        return ALIAS_UNIDADES[v]
    raise ValueError(
        f"Unidade desconhecida: {v!r}. Canônicas: {sorted(UNIDADES_CANONICAS)}. Aliases: {sorted(ALIAS_UNIDADES)}."
    )
