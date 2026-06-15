"""Modelos de Permanência de Recursos sem Dismissal (ADR-059).

Modela a continuidade de uso de equipamentos entre atividades consecutivas,
eliminando custos desnecessários de desmobilização e remobilização.

Conceito central: CampanhaEquipamento — período contínuo em que um equipamento
(identificado logicamente por tipo + índice) permanece no canteiro, servindo
a uma ou mais atividades sem retornar ao fornecedor/depósito entre elas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RegimePermanencia:
    """Parâmetros econômicos de mobilização e permanência de um tipo de equipamento.

    Define o threshold de decisão:
        Se gap_idle ≤ threshold_dismissal → manter em standby (campanha compartilhada)
        Se gap_idle > threshold_dismissal → devolver e remobilizar

    threshold_dismissal = (custo_mob + custo_demob) / custo_standby_semanal
    """

    tipo_id: str  # equip_id do catálogo (ex: "ESCAV-HID-38T")
    custo_mob: float  # R$ para trazer ao canteiro (transporte + setup)
    custo_demob: float  # R$ para remover do canteiro (desmonte + transporte)
    custo_standby_semanal: float  # R$ por semana idle no canteiro (manutenção mínima)
    modalidade: Literal["aluguel", "proprio"] = "aluguel"

    @property
    def threshold_dismissal(self) -> float:
        """Número de semanas idle a partir do qual é mais barato devolver e remobilizar."""
        if self.custo_standby_semanal <= 0:
            return float("inf")
        return (self.custo_mob + self.custo_demob) / self.custo_standby_semanal

    @classmethod
    def estimado(cls, tipo_id: str, custo_mensal_ativo: float) -> RegimePermanencia:
        """Estima regime a partir do custo mensal ativo.

        Convenções (referência de mercado, construção civil brasileira):
        - MOB ≈ 20% do custo mensal (transporte + setup)
        - DEMOB ≈ 15% do custo mensal
        - Standby semanal ≈ 100% do custo semanal ativo (NEP-031 L2: aluguel integral)
        """
        from concilium.domain.constants import SEMANAS_POR_MES

        custo_semanal = custo_mensal_ativo / SEMANAS_POR_MES
        return cls(
            tipo_id=tipo_id,
            custo_mob=round(custo_mensal_ativo * 0.20, 2),
            custo_demob=round(custo_mensal_ativo * 0.15, 2),
            custo_standby_semanal=round(custo_semanal * 1.0, 2),  # NEP-031 L2,
        )


@dataclass(frozen=True)
class InstanciaEquipamento:
    """Identidade lógica de uma unidade específica de equipamento no canteiro.

    Não representa identidade física real (placa, número de série) — é uma
    abstração para rastreamento de custo e permanência dentro do planejamento.

    Exemplo: "ESCAV-HID-38T#1", "ESCAV-HID-38T#2" para dois exemplares do tipo.
    """

    instancia_id: str  # "{tipo_id}#{numero}", ex: "ESCAV-HID-38T#1"
    tipo_id: str  # equip_id do catálogo
    numero: int  # índice dentro do projeto (1, 2, 3, ...)
    regime: RegimePermanencia


@dataclass(frozen=True)
class AlocacaoInstancia:
    """Período em que uma instância de equipamento está alocada a uma atividade."""

    instancia_id: str
    atividade_id: str
    semana_inicio: int
    semana_fim: int
    num_unidades: int  # sempre 1 para instâncias — aqui para compatibilidade


@dataclass(frozen=True)
class CampanhaEquipamento:
    """Período contínuo de presença de um equipamento no canteiro (ADR-059 D2).

    Agrupa atividades consecutivas (gap ≤ threshold_dismissal) que usam o mesmo
    tipo de equipamento, eliminando custos repetidos de mobilização.

    Invariante:
        custo_campanha ≤ sum(custo_mob + custo_demob para cada atividade isolada)
    """

    instancia_id: str
    tipo_id: str
    semana_entrada: int  # Semana ISO offset em que o equip chega ao canteiro
    semana_saida: int  # Semana ISO offset em que o equip sai do canteiro
    atividades: tuple[str, ...]  # activity_ids ordenadas por start_week
    semanas_ativas: int  # semanas com trabalho efetivo (qtd_executada > 0)
    semanas_standby: int  # semanas idle dentro da campanha
    custo_mob: float  # R$ (pago uma vez no início)
    custo_demob: float  # R$ (pago uma vez no fim)
    custo_standby_total: float  # = standby_semanal × semanas_standby
    custo_campanha: float  # = mob + demob + standby_total
    economia_vs_dismissal: float  # = custo_sem_campanha - custo_campanha

    @property
    def duracao_semanas(self) -> int:
        return max(1, self.semana_saida - self.semana_entrada + 1)

    @property
    def taxa_utilizacao(self) -> float:
        """Fração do tempo da campanha com trabalho efetivo."""
        return round(self.semanas_ativas / self.duracao_semanas, 4) if self.duracao_semanas > 0 else 0.0


@dataclass(frozen=True)
class AnaliseFrequenciaCampanhas:
    """Resumo das campanhas identificadas para todo o projeto (ADR-059)."""

    projeto_id: str
    gerado_em: str
    n_campanhas: int
    n_instancias: int
    economia_total: float  # R$ economizados vs. dismissal em cada atividade
    custo_standby_total: float  # R$ de standby idle gerado pelas campanhas
    economia_liquida: float  # = economia_total - custo_standby_total
    campanhas: tuple[CampanhaEquipamento, ...]
    alertas_custo_duplicado: tuple[str, ...]  # VAL-CAMP-01 — campanhas não detectadas

    def to_dict(self) -> dict:
        import dataclasses

        def _conv(obj):
            if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
                return {k: _conv(v) for k, v in dataclasses.asdict(obj).items()}
            if isinstance(obj, (list, tuple)):
                return [_conv(v) for v in obj]
            return obj

        return _conv(self)
