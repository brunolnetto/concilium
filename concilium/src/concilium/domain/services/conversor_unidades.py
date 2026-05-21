"""Serviço de domínio para conversão e compatibilização de unidades.

Garante que o pipeline de cálculos não sofra anomalias de grandeza quando o
catálogo for alimentado com 't' e a CPU pedir 'kg', ou 'm3' x 'litro'.
"""

from concilium.domain.constants import HORAS_DIA_PADRAO, HORAS_MES_CLT  # ADR-056 §T3


class UnidadeIncompativelError(ValueError):
    """Exceção levantada quando não há caminho de conversão entre unidades."""

    pass


class ConversorUnidades:
    """Motor de conversão de unidades para engenharia de custos."""

    # Mapa de normalização canônica (alias -> unidade base)
    _ALIASES = {
        "un": "unidade",
        "und": "unidade",
        "unid": "unidade",
        "sc": "saco",
        "l": "litro",
        "ton": "t",
        "h": "h",
        "mes": "mes",
        "mês": "mes",
        "dia": "dia",
        "kg": "kg",
        "t": "t",
        "m": "m",
        "m2": "m2",
        "m3": "m3",
        "cm": "cm",
        "km": "km",
        "litro": "litro",
        "saco": "saco",
    }

    # Tabela de conversão (base_origem -> base_destino -> fator)
    _TABELA = {
        # Massa
        "t": {"kg": 1000.0},
        "kg": {"t": 0.001, "g": 1000.0},
        "g": {"kg": 0.001},
        # Volume
        "m3": {"litro": 1000.0},
        "litro": {"m3": 0.001},
        # Comprimento
        "km": {"m": 1000.0},
        "m": {"km": 0.001, "cm": 100.0},
        "cm": {"m": 0.01},
        # Tempo — convenção CLT (ADR-056 §T3: ver domain/constants.HORAS_MES_CLT)
        # Nota: dict literal não pode referenciar módulo-nível no corpo da classe;
        # os valores 220.0 e 8.0 correspondem a HORAS_MES_CLT e HORAS_DIA_PADRAO.
        "mes": {"h": HORAS_MES_CLT},
        "dia": {"h": float(HORAS_DIA_PADRAO)},
        "h": {"mes": 1.0 / HORAS_MES_CLT, "dia": 1.0 / HORAS_DIA_PADRAO},
    }

    @classmethod
    def normalizar(cls, unidade: str) -> str:
        """Padroniza strings para a base canônica (ex: 'un' -> 'unidade')."""
        if not unidade:
            return ""
        u = unidade.strip().lower()
        return cls._ALIASES.get(u, u)

    @staticmethod
    def converter_preco(valor: float, unidade_origem: str, unidade_destino: str) -> float:
        """Converte um PREÇO UNITÁRIO (R$/unidade) entre dimensões.

        Diferente da conversão de quantidades, a conversão de preços é INVERSA.
        Ex: Se 1 mes = 176h, então 100 R$/h = 17600 R$/mes.
        """
        origem = ConversorUnidades.normalizar(unidade_origem)
        destino = ConversorUnidades.normalizar(unidade_destino)

        if origem == destino:
            return valor

        if origem in ConversorUnidades._TABELA and destino in ConversorUnidades._TABELA[origem]:
            fator = ConversorUnidades._TABELA[origem][destino]
            return valor / fator

        raise UnidadeIncompativelError(f"Conversão de preço impossível de '{unidade_origem}' para '{unidade_destino}'.")

    @classmethod
    def eh_unidade_conhecida(cls, unidade: str) -> bool:
        """Verifica se a unidade (ou seu alias) é reconhecida pelo sistema."""
        norm = cls.normalizar(unidade)
        return norm in cls._ALIASES.values()

    @classmethod
    def sao_compativeis(cls, origem: str, destino: str) -> bool:
        """Verifica se existe caminho direto de conversão entre duas unidades."""
        u_origem = cls.normalizar(origem)
        u_destino = cls.normalizar(destino)

        if u_origem == u_destino:
            return True

        return u_destino in cls._TABELA.get(u_origem, {})

    @classmethod
    def converter(cls, quantidade: float, origem: str, destino: str) -> float:
        """Converte uma quantidade entre bases canônicas."""
        u_origem = cls.normalizar(origem)
        u_destino = cls.normalizar(destino)

        if u_origem == u_destino:
            return quantidade

        if u_origem in cls._TABELA and u_destino in cls._TABELA[u_origem]:
            fator = cls._TABELA[u_origem][u_destino]
            return quantidade * fator

        raise UnidadeIncompativelError(
            f"Conversão impossível de '{origem}' ({u_origem}) para '{destino}' ({u_destino})."
        )

    @classmethod
    def resolver_coeficiente_cpu(cls, coeficiente_cpu: float, unidade_cpu: str, unidade_catalogo: str) -> float:
        """Resolve o coeficiente real a ser aplicado no preço."""
        return cls.converter(coeficiente_cpu, unidade_cpu, unidade_catalogo)
