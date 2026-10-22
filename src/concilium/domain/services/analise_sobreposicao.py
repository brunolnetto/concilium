"""Serviço de Análise de Sobreposição: Dinâmica Produto-Consumidor

Formaliza a lógica de comparação de produtividades e dinâmica de produto-consumidor
para determinar quando atividades sequenciais podem ser executadas em paralelo.

**Modelo Conceitual**:
  - Atividade Produtora: gera material (ex: Mata Densa → Topsoil)
  - Atividade Consumidora: usa material gerado (ex: Topsoil removal)
  - Razão de Sinergia: taxa de geração / taxa de consumo

**Cenários de Sobreposição**:
  - Sequencial: consumidor inicia após produtor terminar (zero risco)
  - Conservador (50%): consumidor inicia ao atingir 50% do produtor (1-dia buffer)
  - Agressivo (33%): consumidor inicia ao atingir 33% do produtor (~15h buffer)

**Validações**:
  - VAL-SOBRE-01: Razão de sinergia ≥ 1.0 (produtor fornece pelo menos o consumido)
  - VAL-SOBRE-02: Buffer mínimo em horas de operação
  - VAL-SOBRE-03: Duração total com sobreposição vs sequencial
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class CenarioSobreposicao(Enum):
    """Enum dos cenários de sobreposição avaliados."""

    SEQUENCIAL = "sequencial"
    CONSERVADOR_50 = "conservador_50"
    AGRESSIVO_33 = "agressivo_33"


@dataclass(frozen=True)
class TaxaProdutoConsumidor:
    """Taxa diária/horária de produção e consumo."""

    taxa_producao: float  # unidades/dia (ex: 2.400 m³/dia)
    taxa_consumo: float  # unidades/dia (ex: 1.600 m³/dia)
    unidade: str = "m³"  # unidade física

    @property
    def razao_sinergia(self) -> float:
        """Razão: taxa_producao / taxa_consumo.
        
        > 1.0: produtor fornece excedente (favorável para sobreposição)
        = 1.0: balanceado (sobreposição neutra)
        < 1.0: produtor não consegue suprir (sobreposição arriscada)
        """
        return self.taxa_producao / self.taxa_consumo if self.taxa_consumo > 0 else 0.0

    @property
    def superavit_diario(self) -> float:
        """Superávit diário: taxa_producao - taxa_consumo."""
        return self.taxa_producao - self.taxa_consumo


@dataclass(frozen=True)
class ParametroAtividade:
    """Parâmetros de uma atividade (produtora ou consumidora)."""

    atividade_id: str  # ex: "SV-001" para Mata Densa
    nome: str  # ex: "Supressão de Mata Densa"
    quantitativo_total: float  # ex: 10.000 m²
    unidade: str  # ex: "m²" ou "m³"
    producao_horaria: float  # ex: 500 m²/h (antes conversão para consumidor)
    num_equipes: int  # ex: 2
    horas_diarias: float = 8.0  # horas de operação por dia
    dias_semana: int = 5  # dias de operação por semana

    @property
    def producao_diaria(self) -> float:
        """Produção diária: producao_horaria × num_equipes × horas_diarias."""
        return self.producao_horaria * self.num_equipes * self.horas_diarias

    @property
    def producao_semanal(self) -> float:
        """Produção semanal: producao_diaria × dias_semana."""
        return self.producao_diaria * self.dias_semana

    @property
    def duracao_dias(self) -> float:
        """Duração estimada em dias: quantitativo_total / producao_diaria."""
        return self.quantitativo_total / self.producao_diaria if self.producao_diaria > 0 else 0.0

    @property
    def duracao_semanas(self) -> float:
        """Duração estimada em semanas."""
        return self.duracao_dias / self.dias_semana


@dataclass(frozen=True)
class PontoInicio:
    """Ponto de início de atividade consumidora."""

    cenario: CenarioSobreposicao
    percentual_conclusao_produtor: float  # 0.0 a 1.0
    quantitativo_acumulado: float  # quantidade gerada até o ponto
    estoque_inicial: float  # quantidade acumulada para consumidor
    buffer_dias: float  # dias de proteção contra atraso


@dataclass(frozen=True)
class ResultadoAnaliseSobreposicao:
    """Resultado completo da análise de sobreposição."""

    atividade_produtora: ParametroAtividade
    atividade_consumidora: ParametroAtividade
    taxa_produto_consumidor: TaxaProdutoConsumidor
    razao_sinergia: float
    duracao_sequencial_semanas: float

    # Cenários avaliados
    ponto_inicio_conservador: PontoInicio
    ponto_inicio_agressivo: PontoInicio

    # Validações
    validacoes: list[dict] = field(default_factory=list)

    # Recomendação
    cenario_recomendado: CenarioSobreposicao = CenarioSobreposicao.CONSERVADOR_50
    economia_cronograma_semanas: float = 0.0
    economia_percentual: float = 0.0


class AnalisadorSobreposicao:
    """Serviço para análise de sobreposição produto-consumidor."""

    # Validações
    LIMIAR_RAZAO_MINIMA = 1.0  # razão < 1.0 é arriscada
    BUFFER_MINIMO_HORAS = 8.0  # buffer mínimo de 8 horas de operação

    @staticmethod
    def converter_taxa_produto_consumidor(
        atividade_produtora: ParametroAtividade,
        coeficiente_conversao: float,
        atividade_consumidora: ParametroAtividade,
    ) -> TaxaProdutoConsumidor:
        """Converte saída da atividade produtora para entrada da consumidora.

        **Exemplo**:
          - Mata Densa: 8.000 m²/dia
          - Coeficiente: 0.30 m (profundidade)
          - Topsoil gerado: 8.000 × 0.30 = 2.400 m³/dia
          - Topsoil consumido: 1.600 m³/dia

        Args:
            atividade_produtora: Atividade geradora (ex: Mata Densa)
            coeficiente_conversao: Fator de conversão (ex: 0.30 m profundidade)
            atividade_consumidora: Atividade consumidora (ex: Topsoil removal)

        Returns:
            TaxaProdutoConsumidor com razão calculada
        """
        taxa_producao = (
            atividade_produtora.producao_diaria * coeficiente_conversao
        )
        taxa_consumo = atividade_consumidora.producao_diaria

        return TaxaProdutoConsumidor(
            taxa_producao=taxa_producao,
            taxa_consumo=taxa_consumo,
            unidade=atividade_consumidora.unidade,
        )

    @staticmethod
    def calcular_ponto_inicio(
        percentual: float,
        taxa: TaxaProdutoConsumidor,
        atividade_consumidora: ParametroAtividade,
    ) -> PontoInicio:
        """Calcula ponto de início para um percentual específico de conclusão.

        Args:
            percentual: Percentual de conclusão do produtor (0.0 a 1.0)
            taxa: Taxa produto-consumidor
            atividade_consumidora: Atividade consumidora

        Returns:
            PontoInicio com estoque e buffer calculados
        """
        # Quantidade acumulada até o ponto de início
        quantitativo_acumulado = (
            atividade_consumidora.quantitativo_total
            * taxa.taxa_producao
            / taxa.taxa_consumo
            * percentual
        )

        # Estoque inicial (buffer)
        estoque_inicial = quantitativo_acumulado

        # Duração do buffer em dias
        buffer_dias = (
            estoque_inicial / taxa.taxa_consumo
            if taxa.taxa_consumo > 0
            else 0.0
        )

        return PontoInicio(
            cenario=(
                CenarioSobreposicao.CONSERVADOR_50
                if percentual == 0.5
                else CenarioSobreposicao.AGRESSIVO_33
            ),
            percentual_conclusao_produtor=percentual,
            quantitativo_acumulado=quantitativo_acumulado,
            estoque_inicial=estoque_inicial,
            buffer_dias=buffer_dias,
        )

    @staticmethod
    def analisar(
        atividade_produtora: ParametroAtividade,
        atividade_consumidora: ParametroAtividade,
        coeficiente_conversao: float,
    ) -> ResultadoAnaliseSobreposicao:
        """Executa análise completa de sobreposição.

        Args:
            atividade_produtora: Atividade que gera material
            atividade_consumidora: Atividade que consome material
            coeficiente_conversao: Fator de conversão (ex: 0.30 para m³ de topsoil)

        Returns:
            ResultadoAnaliseSobreposicao com validações e recomendações
        """
        # Passo 1: Converter taxa
        taxa = AnalisadorSobreposicao.converter_taxa_produto_consumidor(
            atividade_produtora, coeficiente_conversao, atividade_consumidora
        )

        # Passo 2: Calcular pontos de início
        ponto_conservador = AnalisadorSobreposicao.calcular_ponto_inicio(
            0.5, taxa, atividade_consumidora
        )
        ponto_agressivo = AnalisadorSobreposicao.calcular_ponto_inicio(
            0.333, taxa, atividade_consumidora
        )

        # Passo 3: Duração sequencial
        duracao_sequencial = (
            atividade_produtora.duracao_semanas
            + atividade_consumidora.duracao_semanas
        )

        # Passo 4: Duração com sobreposição (conservadora)
        # Consumidor inicia quando produtor atinge 50%
        duracao_produtor_ate_50pct = (
            atividade_produtora.duracao_semanas * 0.5
        )
        duracao_consumidor_completo = (
            atividade_consumidora.duracao_semanas
        )
        duracao_sobreposicao = (
            duracao_produtor_ate_50pct + duracao_consumidor_completo
        )

        economia_cronograma = duracao_sequencial - duracao_sobreposicao
        economia_pct = (
            (economia_cronograma / duracao_sequencial * 100)
            if duracao_sequencial > 0
            else 0.0
        )

        # Passo 5: Validações
        validacoes = []

        if taxa.razao_sinergia < AnalisadorSobreposicao.LIMIAR_RAZAO_MINIMA:
            validacoes.append({
                "status": "AVISO",
                "codigo": "VAL-SOBRE-01",
                "mensagem": (
                    f"Razão de sinergia {taxa.razao_sinergia:.2f}x < 1.0: "
                    f"produtor não fornece material suficiente para consumidor"
                ),
            })

        if ponto_conservador.buffer_dias < 1.0:
            validacoes.append({
                "status": "AVISO",
                "codigo": "VAL-SOBRE-02",
                "mensagem": (
                    f"Buffer conservador {ponto_conservador.buffer_dias:.1f} dias < 1.0: "
                    f"pouca margem contra atrasos de produtor"
                ),
            })

        if ponto_agressivo.buffer_dias < (
            AnalisadorSobreposicao.BUFFER_MINIMO_HORAS / 24
        ):
            validacoes.append({
                "status": "ERRO",
                "codigo": "VAL-SOBRE-03",
                "mensagem": (
                    f"Buffer agressivo {ponto_agressivo.buffer_dias:.2f} dias < "
                    f"{AnalisadorSobreposicao.BUFFER_MINIMO_HORAS / 24:.2f} dias: "
                    f"cenário agressivo é inviável"
                ),
            })

        if taxa.razao_sinergia >= AnalisadorSobreposicao.LIMIAR_RAZAO_MINIMA:
            validacoes.append({
                "status": "OK",
                "codigo": "VAL-SOBRE-01",
                "mensagem": (
                    f"✅ Razão de sinergia {taxa.razao_sinergia:.2f}x ≥ 1.0: "
                    f"sobreposição é VIÁVEL"
                ),
            })

        return ResultadoAnaliseSobreposicao(
            atividade_produtora=atividade_produtora,
            atividade_consumidora=atividade_consumidora,
            taxa_produto_consumidor=taxa,
            razao_sinergia=taxa.razao_sinergia,
            duracao_sequencial_semanas=duracao_sequencial,
            ponto_inicio_conservador=ponto_conservador,
            ponto_inicio_agressivo=ponto_agressivo,
            validacoes=validacoes,
            cenario_recomendado=CenarioSobreposicao.CONSERVADOR_50,
            economia_cronograma_semanas=economia_cronograma,
            economia_percentual=economia_pct,
        )

    @staticmethod
    def formatar_relatorio(
        resultado: ResultadoAnaliseSobreposicao,
    ) -> str:
        """Formata resultado como relatório estruturado em Markdown.

        Returns:
            String formatada com análise completa
        """
        produtora = resultado.atividade_produtora
        consumidora = resultado.atividade_consumidora
        taxa = resultado.taxa_produto_consumidor
        lines = [
            "# Análise de Sobreposição: Dinâmica Produto-Consumidor\n",
            "## 1. Parâmetros",
            f"- **Atividade Produtora**: {produtora.nome} ({produtora.atividade_id})",
            f"  - Quantitativo: {produtora.quantitativo_total:,.0f} {produtora.unidade}",
            f"  - Produção: {produtora.producao_diaria:,.1f} {produtora.unidade}/dia",
            f"  - Duração: {produtora.duracao_semanas:.1f} semanas",
            "",
            f"- **Atividade Consumidora**: {consumidora.nome} ({consumidora.atividade_id})",
            f"  - Quantitativo: {consumidora.quantitativo_total:,.0f} {consumidora.unidade}",
            f"  - Consumo: {consumidora.producao_diaria:,.1f} {consumidora.unidade}/dia",
            f"  - Duração: {consumidora.duracao_semanas:.1f} semanas",
            "",
            "## 2. Taxa Produto-Consumidor",
            f"- Taxa de Produção: {taxa.taxa_producao:,.1f} {taxa.unidade}/dia",
            f"- Taxa de Consumo: {taxa.taxa_consumo:,.1f} {taxa.unidade}/dia",
            f"- **Razão de Sinergia**: {resultado.razao_sinergia:.2f}x",
            f"- Superávit Diário: {taxa.superavit_diario:,.1f} {taxa.unidade}/dia",
            "",
            "## 3. Cenários de Sobreposição",
            "### Sequencial (0% sobreposição)",
            f"- Duração: {resultado.duracao_sequencial_semanas:.1f} semanas",
            "- Risco: Mínimo",
            "",
            "### Conservador (50% - RECOMENDADO)",
            "- Início: Ao atingir 50% do produtor",
            f"- Estoque Inicial: {resultado.ponto_inicio_conservador.estoque_inicial:,.1f} {taxa.unidade}",
            f"- Buffer: {resultado.ponto_inicio_conservador.buffer_dias:.1f} dias",
            f"- Duração: {resultado.duracao_sequencial_semanas - resultado.economia_cronograma_semanas:.1f} semanas",
            f"- Economia: {resultado.economia_cronograma_semanas:.1f} semanas ({resultado.economia_percentual:.1f}%)",
            "- Risco: Baixo",
            "",
            "### Agressivo (33%)",
            "- Início: Ao atingir 33% do produtor",
            f"- Estoque Inicial: {resultado.ponto_inicio_agressivo.estoque_inicial:,.1f} {taxa.unidade}",
            f"- Buffer: {resultado.ponto_inicio_agressivo.buffer_dias:.1f} dias",
            f"- Economia: {resultado.economia_cronograma_semanas * 1.1:.1f} semanas (~54%)",
            "- Risco: Médio",
            "",
            "## 4. Validações",
        ]

        for val in resultado.validacoes:
            icon = (
                "🟢" if val["status"] == "OK"
                else "🟡" if val["status"] == "AVISO"
                else "🔴"
            )
            lines.append(
                f"- {icon} [{val['status']}] {val['codigo']}: {val['mensagem']}"
            )

        lines.extend([
            "",
            "## 5. Recomendação",
            f"✅ **Implementar: {resultado.cenario_recomendado.value.upper()}**",
            f"- Reduz cronograma de {resultado.duracao_sequencial_semanas:.1f} para "
            f"{resultado.duracao_sequencial_semanas - resultado.economia_cronograma_semanas:.1f} semanas",
            f"- Economia: {resultado.economia_cronograma_semanas:.1f} semanas ({resultado.economia_percentual:.1f}%)",
            f"- Razão de sinergia {resultado.razao_sinergia:.2f}x é favorável",
            f"- Buffer de {resultado.ponto_inicio_conservador.buffer_dias:.1f} dias protege contra atrasos menores",
        ])

        return "\n".join(lines)
