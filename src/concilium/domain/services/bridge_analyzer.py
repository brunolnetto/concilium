"""ADR-039 — Compensação de Ineficiências Estruturais ("The Bridge").

Separa o confronto entre Custo Direto de Catálogo (Metodologia B) e Custo
Operacional de Equipes (Metodologia A) em fatores isoláveis e mensuráveis:

  Nível 1 — Catálogo Base (puro, linear)
  Nível 2 — Catálogo Escalado (+ quantização de frentes)
  Nível 3 — Catálogo Normalizado (+ fator de praticabilidade climática)
  Nível 4 — Custo Operacional de Equipes (realidade medida)

O delta real auditável é (N4 - N3), expurgando os fatores estruturais não
controláveis pelo orçamentista.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from math import ceil


@dataclass(frozen=True)
class BridgeAnalysis:
    """Resultado completo da análise de compensação estrutural (ADR-039 §D1)."""

    # ── Os 4 níveis ────────────────────────────────────────────────────────
    nivel_1_catalogo_base: float
    """Custo direto de catálogo puro: Σ(Q_i × PU_i)."""

    nivel_2_catalogo_escalado: float
    """Catálogo após majoração pela quantização inteira de frentes."""

    nivel_3_catalogo_normalizado: float
    """Catálogo escalado dividido pelo fator de praticabilidade climática."""

    nivel_4_operacional: float | None
    """Custo operacional real de equipes (Metodologia A). None quando não disponível."""

    # ── Fatores isolados ──────────────────────────────────────────────────
    fator_quantizacao: float
    """Razão N2/N1 — custo adicional por arredondamento de frentes (sempre >= 1.0)."""

    fator_praticabilidade: float
    """Fração produtiva P do regime pluviométrico (0 < P <= 1)."""

    # ── Desvios por responsabilidade ──────────────────────────────────────
    desvio_escala_abs: float
    """N2 - N1: custo morto de ociosidade forçada por escala de prazo."""

    desvio_clima_abs: float
    """N3 - N2: custo de oportunidade de frentes paradas aguardando condições."""

    delta_real_abs: float | None
    """N4 - N3: desvio genuíno de gestão operacional. None se N4 não disponível."""

    delta_real_percentual: float | None
    """(N4 - N3) / N4 × 100. None se N4 não disponível."""

    # ── Metadados ─────────────────────────────────────────────────────────
    necessidades_fracionadas: list[float] = field(default_factory=list)
    """F_i de cada atividade: Q_i / (P_i × T_i). Usado para auditoria."""

    @property
    def delta_estrutural_abs(self) -> float:
        """N3 - N1: soma dos desvios estruturais (escala + clima)."""
        return round(self.nivel_3_catalogo_normalizado - self.nivel_1_catalogo_base, 2)

    @property
    def delta_estrutural_percentual(self) -> float | None:
        """Percentual dos fatores estruturais sobre N4 (quando disponível)."""
        if self.nivel_4_operacional and self.nivel_4_operacional > 0:
            return round(self.delta_estrutural_abs / self.nivel_4_operacional * 100, 2)
        return None

    @property
    def status_alerta(self) -> str:
        """Classificação qualitativa do delta real.

        VERDE  : <= 10 %
        AMARELO: 10 % < delta <= 25 %
        VERMELHO: > 25 %
        """
        pct = self.delta_real_percentual
        if pct is None:
            return "SEM_DADOS"
        abs_pct = abs(pct)
        if abs_pct <= 10.0:
            return "VERDE"
        if abs_pct <= 25.0:
            return "AMARELO"
        return "VERMELHO"


class BridgeAnalyzer:
    """Calcula a análise de compensação estrutural (The Bridge — ADR-039)."""

    # ── Funções estáticas utilitárias ─────────────────────────────────────

    @staticmethod
    def calcular_necessidade_fracionada(
        quantidade: float,
        produtividade: float,
        horas_disponiveis: float,
    ) -> float:
        """F_i = Q / (P × T) — frentes técnicas ideais (pode ser fracionário).

        Args:
            quantidade:        Quantitativo da atividade (ex.: m³, m, t).
            produtividade:     Produção da equipe (unidade / hora).
            horas_disponiveis: Total de horas no período de execução.

        Returns:
            Número de frentes tecnicamente necessárias.

        Raises:
            ValueError: Se produtividade ou horas_disponiveis forem <= 0.
        """
        if produtividade <= 0:
            raise ValueError(f"produtividade deve ser > 0, recebido: {produtividade}")
        if horas_disponiveis <= 0:
            raise ValueError(f"horas_disponiveis deve ser > 0, recebido: {horas_disponiveis}")
        return quantidade / (produtividade * horas_disponiveis)

    @staticmethod
    def fator_quantizacao_medio(necessidades_fracionadas: Sequence[float]) -> float:
        """Calcula o fator médio de quantização sobre todas as atividades.

        Fórmula: média(ceil(F_i) / F_i) para cada F_i > 0.

        Args:
            necessidades_fracionadas: Lista de F_i de cada atividade.

        Returns:
            Fator médio (>= 1.0). Retorna 1.0 se a lista estiver vazia.
        """
        frentes_validas = [f for f in necessidades_fracionadas if f > 0]
        if not frentes_validas:
            return 1.0
        return sum(ceil(f) / f for f in frentes_validas) / len(frentes_validas)

    # ── Método principal ──────────────────────────────────────────────────

    @classmethod
    def calcular(
        cls,
        nivel_1: float,
        necessidades_fracionadas: Sequence[float],
        praticabilidade: float,
        nivel_4: float | None = None,
    ) -> BridgeAnalysis:
        """Calcula a análise completa The Bridge.

        Args:
            nivel_1:                   Custo direto de catálogo puro (R$).
            necessidades_fracionadas:  F_i de cada atividade (list[float]).
            praticabilidade:           Fração produtiva P ∈ (0, 1]. Ex.: 0.83.
            nivel_4:                   Custo operacional real (R$). None = N/A.

        Returns:
            BridgeAnalysis com todos os níveis e desvios calculados.

        Raises:
            ValueError: Se praticabilidade estiver fora do intervalo (0, 1].
        """
        if not (0 < praticabilidade <= 1.0):
            raise ValueError(f"praticabilidade deve estar em (0, 1], recebido: {praticabilidade}")

        # Nível 2: catálogo escalado
        fq = cls.fator_quantizacao_medio(necessidades_fracionadas)
        nivel_2 = round(nivel_1 * fq, 2)

        # Nível 3: catálogo normalizado (dividido pela praticabilidade)
        nivel_3 = round(nivel_2 / praticabilidade, 2)

        # Desvios isolados
        desvio_escala = round(nivel_2 - nivel_1, 2)
        desvio_clima = round(nivel_3 - nivel_2, 2)

        # Delta real
        delta_real_abs: float | None = None
        delta_real_pct: float | None = None
        if nivel_4 is not None and nivel_4 > 0:
            delta_real_abs = round(nivel_4 - nivel_3, 2)
            delta_real_pct = round(delta_real_abs / nivel_4 * 100, 2)

        return BridgeAnalysis(
            nivel_1_catalogo_base=round(nivel_1, 2),
            nivel_2_catalogo_escalado=nivel_2,
            nivel_3_catalogo_normalizado=nivel_3,
            nivel_4_operacional=round(nivel_4, 2) if nivel_4 is not None else None,
            fator_quantizacao=round(fq, 4),
            fator_praticabilidade=praticabilidade,
            desvio_escala_abs=desvio_escala,
            desvio_clima_abs=desvio_clima,
            delta_real_abs=delta_real_abs,
            delta_real_percentual=delta_real_pct,
            necessidades_fracionadas=list(necessidades_fracionadas),
        )
