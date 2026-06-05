"""BenchmarkDiffService — Comparação estruturada de execuções de benchmark."""
from dataclasses import dataclass
from datetime import datetime

from concilium.domain.benchmark.models import BenchmarkExecution


@dataclass
class BenchmarkDiffResult:
    """Resultado da comparação entre duas execuções de benchmark."""

    execution_1_id: str
    execution_2_id: str
    benchmark_id: str
    versao_1: int
    versao_2: int
    delta_custo_direto_percentual: float  # % de mudança no custo
    delta_cronograma_semanas: int  # mudança em semanas
    delta_margem_lucro_percentual: float  # pontos percentuais
    itens_impactados: int = 0
    interpretacao: str = ""
    comparado_em: datetime | None = None

    def to_dict(self) -> dict:
        """Serializa resultado para dicionário."""
        return {
            "execution_1_id": self.execution_1_id,
            "execution_2_id": self.execution_2_id,
            "benchmark_id": self.benchmark_id,
            "versao_1": self.versao_1,
            "versao_2": self.versao_2,
            "delta_custo_direto_percentual": self.delta_custo_direto_percentual,
            "delta_cronograma_semanas": self.delta_cronograma_semanas,
            "delta_margem_lucro_percentual": self.delta_margem_lucro_percentual,
            "itens_impactados": self.itens_impactados,
            "interpretacao": self.interpretacao,
            "comparado_em": self.comparado_em.isoformat() if self.comparado_em else None,
        }


class BenchmarkDiffService:
    """Serviço para comparar execuções de benchmark e gerar diffs estruturados."""

    def compare(
        self, exec_1: BenchmarkExecution, exec_2: BenchmarkExecution
    ) -> BenchmarkDiffResult:
        """Compara duas execuções e retorna diff estruturado.

        Args:
            exec_1: Execução baseline (v1)
            exec_2: Execução nova (v2)

        Returns:
            BenchmarkDiffResult com deltas estruturados.
        """
        if exec_1.benchmark_id != exec_2.benchmark_id:
            raise ValueError(
                f"Execuções de benchmarks diferentes: {exec_1.benchmark_id} vs {exec_2.benchmark_id}"
            )

        # Extrai deltas da discrepancia_sumario se disponível
        discrepancia = exec_2.discrepancia_sumario or {}

        delta_custo = discrepancia.get("delta_custo_direto", 0.0)
        delta_cronograma = discrepancia.get("delta_cronograma", 0)
        delta_margem = discrepancia.get("delta_margem_lucro", 0.0)
        itens_impactados = discrepancia.get("itens_impactados", 0)

        # Gera interpretação
        interpretacao = self._gerar_interpretacao(
            delta_custo, delta_cronograma, delta_margem
        )

        return BenchmarkDiffResult(
            execution_1_id=exec_1.execution_id,
            execution_2_id=exec_2.execution_id,
            benchmark_id=exec_1.benchmark_id,
            versao_1=exec_1.versao,
            versao_2=exec_2.versao,
            delta_custo_direto_percentual=delta_custo,
            delta_cronograma_semanas=delta_cronograma,
            delta_margem_lucro_percentual=delta_margem,
            itens_impactados=itens_impactados,
            interpretacao=interpretacao,
            comparado_em=datetime.now(),
        )

    @staticmethod
    def _gerar_interpretacao(
        delta_custo: float, delta_cronograma: int, delta_margem: float
    ) -> str:
        """Gera interpretação textual dos deltas."""
        signals = []

        if delta_custo < -0.5:
            signals.append(f"Melhoria: custo {abs(delta_custo):.1f}% menor")
        elif delta_custo > 0.5:
            signals.append(f"Regressão: custo {delta_custo:.1f}% maior")

        if delta_cronograma < -1:
            signals.append(f"Cronograma {abs(delta_cronograma)} semanas menor")
        elif delta_cronograma > 1:
            signals.append(f"Cronograma {delta_cronograma} semanas maior")

        if delta_margem > 0.5:
            signals.append(f"Margem melhorou {delta_margem:.1f}pp")
        elif delta_margem < -0.5:
            signals.append(f"Margem piorou {abs(delta_margem):.1f}pp")

        if not signals:
            return "Sem alterações significativas"

        return "; ".join(signals)
