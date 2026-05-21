"""Backtracking do PE — soluções inversas com validação de roundtrip (ADR-061)."""

from __future__ import annotations

from dataclasses import dataclass

_PARAM_LABELS: dict[str, str] = {
    "L": "Ajustar margem no orçamento (BDI)",
    "P": "Melhorar produtividade do equipamento",
    "N_MAX": "Aumentar equipes paralelas",
    "T0_RAMP": "Mudar época de início da mobilização",
    "COMBINADA": "Combinação de ajustes",
}

_PARAM_IMPACTO_CLIENTE: dict[str, str] = {
    "L": "Preço de venda aumenta",
    "P": "Sem repasse — requer calibração de CPU",
    "N_MAX": "Sem repasse — requer mais recursos",
    "T0_RAMP": "Sem repasse — requer flexibilidade de cronograma",
    "COMBINADA": "Depende da combinação",
}


@dataclass(frozen=True)
class SolucaoInversa:
    """Uma solução que fecha o gap do PE ajustando um único parâmetro."""

    parametro: str  # "L" | "P" | "N_MAX" | "T0_RAMP" | "COMBINADA"
    valor_atual: float
    valor_requerido: float
    delta_abs: float  # valor_requerido − valor_atual
    delta_pct: float  # variação percentual

    # Consequências para o planejador
    impacto_preco_pct: float  # % de aumento no preço ao cliente (0 = sem repasse)
    impacto_produtividade_pct: float  # esforço de calibração/upgrade
    impacto_recursos_pct: float  # recursos adicionais necessários
    impacto_prazo_semanas: float  # variação em semanas (negativo = comprime)

    # Validação interna
    pe_gap_recalculado: float  # resultado do roundtrip analítico
    roundtrip_valido: bool
    erro_roundtrip: float  # |pe_gap_recalc − alvo|
    confianca: int  # 1–5 (5 = inversa exata)

    @property
    def label(self) -> str:
        return _PARAM_LABELS.get(self.parametro, self.parametro)

    @property
    def impacto_cliente_descricao(self) -> str:
        return _PARAM_IMPACTO_CLIENTE.get(self.parametro, "—")

    @property
    def estrelas(self) -> str:
        return "★" * self.confianca + "☆" * (5 - self.confianca)

    @property
    def descricao_delta(self) -> str:
        if self.parametro == "L":
            return f"De {self.valor_atual * 100:.1f}% para {self.valor_requerido * 100:.1f}% (+{self.delta_abs * 100:.1f}pp)"  # noqa: E501
        if self.parametro == "P":
            return f"De {self.valor_atual:.0f} para {self.valor_requerido:.0f} un/h (+{self.delta_pct:.0f}%)"
        if self.parametro == "N_MAX":
            return f"De {self.valor_atual:.0f} para {self.valor_requerido:.0f} equipes (+{self.delta_abs:.0f})"
        if self.parametro == "T0_RAMP":
            return f"Deslocar início {abs(self.delta_abs):.0f} semanas para a estação seca"
        return f"Δ = {self.delta_abs:+.2f}"


@dataclass(frozen=True)
class BacktrackingPEItem:
    """Soluções inversas para fechar o gap de PE de uma atividade."""

    atividade_id: str
    descricao: str
    pe_gap_atual: float
    pe_gap_alvo: float

    solucoes: tuple[SolucaoInversa, ...]  # ordenadas por confiança desc
    solucao_recomendada: SolucaoInversa | None  # menor Σ impactos nos 3 eixos
    roundtrips_falharam: tuple[str, ...]  # parametros com falha

    @property
    def tem_solucao_sem_repasse(self) -> bool:
        return any(s.roundtrip_valido and s.impacto_preco_pct < 0.5 for s in self.solucoes)


@dataclass(frozen=True)
class BacktrackingPERelatorio:
    """Backtracking completo para todos os itens em déficit."""

    projeto_id: str
    gerado_em: str
    pe_gap_alvo: float
    itens: tuple[BacktrackingPEItem, ...]
    consistencia_global: bool
    n_roundtrips_falharam: int
    # ADR-061: validações emitidas
    validacoes_emitidas: tuple[str, ...] = ()  # ex: ("VAL-INV-ROUNDTRIP-FAIL",)

    @property
    def aviso_consistencia(self) -> str | None:
        if self.n_roundtrips_falharam == 0:
            return None
        return (
            f"{self.n_roundtrips_falharam} sugestão(ões) não foram confirmadas pelo cálculo "
            "e foram removidas das opções."
        )

    def to_dict(self) -> dict:
        import dataclasses

        def _c(o):
            if dataclasses.is_dataclass(o) and not isinstance(o, type):
                return {k: _c(v) for k, v in dataclasses.asdict(o).items()}
            if isinstance(o, (list, tuple)):
                return [_c(v) for v in o]
            return o

        return _c(self)
