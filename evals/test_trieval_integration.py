#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evals — trieval: Avaliação RAG da Qualidade de Respostas do Agente

A biblioteca `trieval` avalia tripletos (Q, C, A) com 6 métricas:

  C|Q  Context Relevance  — contexto recuperado é relevante à pergunta?
  A|C  Faithfulness       — resposta adere ao contexto? (não alucinação)
  A|Q  Answer Relevance   — resposta resolve a pergunta?
  C|A  Context Support    — contexto suporta completamente a resposta?
  Q|C  Answerability      — a pergunta pode ser respondida com este contexto?
  Q|A  Self-Containment   — a pergunta pode ser entendida pela resposta?

Mapeamento AGIS:
  Q = pergunta sobre planejamento de obras
  C = dados retornados pelas skills (Layer 1–4)
  A = resposta do agente de engenharia

Requer:
  pip install trieval
  Variável de ambiente: OPENAI_API_KEY ou equivalente

Execute:
  pytest evals/test_trieval_integration.py -v -m trieval
  # ou sem LLM (apenas casos de estrutura):
  pytest evals/test_trieval_integration.py -v -m "not requires_llm"
"""

import os
import textwrap
from dataclasses import dataclass
from typing import Optional

import pytest


# ---------------------------------------------------------------------------
# Marcadores
# ---------------------------------------------------------------------------

REQUIRES_LLM = pytest.mark.trieval
# Registre em pytest.ini ou pyproject.toml:
# [tool.pytest.ini_options]
# markers = ["trieval: requer LLM (trieval + OPENAI_API_KEY)"]


# ---------------------------------------------------------------------------
# Casos de avaliação RAG (tripletos Q / C / A)
# ---------------------------------------------------------------------------

@dataclass
class AgisEvalCase:
    """Um caso de avaliação para o agente de engenharia AGIS."""
    id: str
    category: str
    description: str
    question: str    # Q
    context: str     # C — dados retornados pelas skills
    answer: str      # A — resposta esperada do agente
    min_overall_score: float = 0.70  # limiar mínimo de qualidade


# ── Casos definidos manualmente (golden set) ────────────────────────────────

EVAL_CASES: list[AgisEvalCase] = [

    # Layer 2 — ENCARGOS
    AgisEvalCase(
        id="EC-001",
        category="operational-encargos",
        description="Agente deve multiplicar salário por 1.66 para calcular custo real",
        question="Qual é o custo mensal de 1 Operador de Escavadeira considerando encargos?",
        context=textwrap.dedent("""
            [Layer 1 - MÃO DE OBRA]
            Operador de Escavadeira: R$ 6.300,00/mês (salário base)

            [Layer 2 - ENCARGOS]
            Provisão (férias, 13°, FGTS): 31%
            Encargos Sociais (INSS, SESI, SENAI): 30%
            Administrativo: 5%
            TOTAL ENCARGOS: 66%
            Multiplicador: 1.66

            Cálculo:
            Custo c/ Encargos = R$ 6.300 × 1.66 = R$ 10.458,00/mês
        """).strip(),
        answer=textwrap.dedent("""
            [Layer 2 - Cálculo com ENCARGOS]
            MÃO DE OBRA: Operador de Escavadeira = R$ 6.300,00/mês (base)
            ENCARGOS: 66% → Multiplicador 1.66
            Custo Total = R$ 6.300 × 1.66 = R$ 10.458,00/mês

            O custo mensal real do Operador de Escavadeira, incluindo todos os
            encargos trabalhistas e previdenciários, é de R$ 10.458,00/mês.
        """).strip(),
        min_overall_score=0.75,
    ),

    # Layer 3 — BDI e Planejamento
    AgisEvalCase(
        id="EC-002",
        category="planning-bdi",
        description="Agente deve aplicar BDI correto ao custo base do serviço",
        question="Qual o preço de venda de escavação a R$ 18,50/m³ com BDI de 25% em materiais?",
        context=textwrap.dedent("""
            [Layer 1 - CPU]
            ESCAVAÇÃO, CARGA, TRANSPORTE: Custo Unit. s/ BDI = R$ 18,50/m³

            [Layer 1 - BDI]
            Material: 25%
            Mão de Obra: 15%
            Equipamento: 12%
            Diesel: 20%

            [Layer 3 - Fórmula PLANEJAMENTO]
            Preço c/ BDI = Custo s/ BDI × (1 + BDI%)
            Para Material: R$ 18,50 × 1.25 = R$ 23,125/m³
        """).strip(),
        answer=textwrap.dedent("""
            [Layer 3 - PLANEJAMENTO]
            CPU: Escavação = R$ 18,50/m³ (sem BDI)
            BDI Material: 25%
            Preço c/ BDI = R$ 18,50 × 1.25 = R$ 23,13/m³

            O preço de venda da escavação com BDI de materiais é R$ 23,13/m³.
        """).strip(),
        min_overall_score=0.75,
    ),

    # Layer 4 — Viabilidade
    AgisEvalCase(
        id="EC-003",
        category="financial-viability",
        description="Agente deve classificar corretamente uma margem de 7% como inviável",
        question="Um projeto com margem de 7% é financeiramente viável?",
        context=textwrap.dedent("""
            [Layer 4 - RESULTADO]
            Receita Total:   R$ 1.000.000
            Custo Total:     R$ 930.000
            Resultado:       R$ 70.000
            Margem:          7,0%

            [Layer 4 - PONTO DE EQUILIBRIO]
            Meta de Margem: 8% ≤ Margem ≤ 10%
            Status Calculado: UNDERPRICED (margem abaixo do mínimo de 8%)
            Ação Recomendada: Revisar preços ou reduzir custos operacionais
        """).strip(),
        answer=textwrap.dedent("""
            [Layer 4 - Validação Financeira]
            Margem Calculada: 7,0%
            Target: 8% ≤ Margem ≤ 10%
            Status: ⚠️ UNDERPRICED

            NÃO VIÁVEL. A margem de 7% está abaixo do mínimo de 8%. Recomenda-se
            revisar os preços de venda ou reduzir custos de mão de obra e equipamentos.
            Decisão: NOGO
        """).strip(),
        min_overall_score=0.75,
    ),

    # Layer 4 — Ponto de Equilíbrio
    AgisEvalCase(
        id="EC-004",
        category="financial-breakeven",
        description="Agente deve calcular corretamente o ponto de equilíbrio",
        question="Qual o ponto de equilíbrio com custos fixos de R$ 200.000 e margem de contribuição de R$ 10/m³?",
        context=textwrap.dedent("""
            [Layer 4 - PONTO DE EQUILIBRIO]
            Custos Fixos (ADM+TOP+LAB+QSMS): R$ 200.000
            Preço Unitário: R$ 20,00/m³
            Custo Variável Unitário: R$ 10,00/m³
            Margem de Contribuição: R$ 10,00/m³

            Fórmula:
            Break-Even = Custos Fixos / Margem de Contribuição
                       = R$ 200.000 / R$ 10,00
                       = 20.000 m³
        """).strip(),
        answer=textwrap.dedent("""
            [Layer 4 - Cálculo Ponto de Equilíbrio]
            Custos Fixos: R$ 200.000
            Margem de Contribuição: R$ 10,00/m³ (preço R$ 20 - custo variável R$ 10)
            Break-Even = R$ 200.000 / R$ 10 = 20.000 m³

            O projeto precisa executar pelo menos 20.000 m³ para cobrir os custos fixos.
        """).strip(),
        min_overall_score=0.75,
    ),

    # E2E — Resposta sem dados (alucinação)
    AgisEvalCase(
        id="EC-005",
        category="anti-hallucination",
        description="Agente NÃO deve inventar dados quando contexto está vazio/indefinido",
        question="Qual é uma margem típica de lucro em projetos de terraplanagem?",
        context=textwrap.dedent("""
            [Layer 1 - BASE DATA]
            As tabelas MÃO DE OBRA, EQUIPAMENTOS, BDI, PRODUÇÕES foram carregadas.
            
            [Layer 2 - OPERATIONAL CALC]
            Custos de equipe e equipamentos calculados para cenários padrão.
            
            [Layer 4 - FINANCIAL VALIDATION]
            Meta de margem para viabilidade: 8% ≤ Margem ≤ 10%
            
            Nota: NÃO há dados históricos de "margens típicas de mercado" na planilha AGIS.
            A tabela CPU contém preços base, não benchmarks de mercado.
        """).strip(),
        answer=textwrap.dedent("""
            [Layer 4 - Validação Financeira]
            Não posso fornecer uma "margem típica" genérica.
            
            A planilha AGIS não contém dados históricos de margens de mercado.
            O sistema valida projetos contra a meta de 8% ≤ Margem ≤ 10%
            com base em dados específicos do projeto (custos reais + receita).
            
            Para sua análise, execute os 4 layers com os dados do seu projeto
            e use o resultado para validar a viabilidade (Gate 4).
        """).strip(),
        min_overall_score=0.55,  # threshold menor — contexto explicitamente diz "não há dados"
    ),
]


# ---------------------------------------------------------------------------
# Testes de estrutura dos casos (sem LLM)
# ---------------------------------------------------------------------------

class TestEvalCaseStructure:
    """Garante que todos os casos de eval estão bem formados."""

    def test_all_cases_have_unique_ids(self):
        ids = [c.id for c in EVAL_CASES]
        assert len(ids) == len(set(ids)), "IDs duplicados nos casos de eval"

    def test_all_cases_have_non_empty_qca(self):
        for case in EVAL_CASES:
            assert len(case.question) > 10, f"{case.id}: pergunta muito curta"
            assert len(case.context) > 20, f"{case.id}: contexto muito curto"
            assert len(case.answer) > 20, f"{case.id}: resposta muito curta"

    def test_all_cases_have_valid_score_threshold(self):
        for case in EVAL_CASES:
            assert 0.0 < case.min_overall_score <= 1.0, (
                f"{case.id}: limiar de score inválido ({case.min_overall_score})"
            )

    def test_anti_hallucination_case_exists(self):
        categories = {c.category for c in EVAL_CASES}
        assert "anti-hallucination" in categories, (
            "Deve existir ao menos um caso de anti-alucinação"
        )

    def test_all_layers_covered(self):
        categories = {c.category for c in EVAL_CASES}
        for expected in ["operational-encargos", "planning-bdi", "financial-viability"]:
            assert any(expected in cat for cat in categories), (
                f"Categoria '{expected}' não coberta pelos casos de eval"
            )

    @pytest.mark.parametrize("case", EVAL_CASES, ids=[c.id for c in EVAL_CASES])
    def test_context_mentions_layer(self, case: AgisEvalCase):
        """Contexto deve referenciar ao menos um Layer."""
        has_layer = any(
            f"Layer {i}" in case.context or f"layer {i}" in case.context.lower()
            for i in range(1, 5)
        )
        assert has_layer, (
            f"{case.id}: contexto não menciona nenhum Layer — "
            "agente deve rastrear origem dos dados"
        )


# ---------------------------------------------------------------------------
# Testes que requerem LLM via trieval
# ---------------------------------------------------------------------------

@REQUIRES_LLM
class TestTrievalScores:
    """
    Testes com LLM real (requer trieval + OPENAI_API_KEY).

    Execute com:
        pytest evals/test_trieval_integration.py -m trieval -v
    """

    @pytest.fixture(scope="class")
    def evaluator(self):
        """Cria instância do Evaluator trieval."""
        try:
            from trieval import Evaluator  # noqa: PLC0415
        except ImportError:
            pytest.skip("trieval não instalado — execute: pip install trieval")

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY não definida")

        return Evaluator(model="openai:gpt-4o-mini")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("case", EVAL_CASES, ids=[c.id for c in EVAL_CASES])
    async def test_overall_score_above_threshold(
        self, evaluator, case: AgisEvalCase
    ):
        """Overall score deve estar acima do limiar mínimo do caso."""
        result = await evaluator.evaluate(
            question=case.question,
            context=case.context,
            answer=case.answer,
        )
        assert result.overall_score >= case.min_overall_score, (
            f"{case.id} ({case.category}): "
            f"score={result.overall_score:.3f} < limiar={case.min_overall_score}\n"
            f"Diagnóstico: {result.diagnose()}"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("case", EVAL_CASES, ids=[c.id for c in EVAL_CASES])
    async def test_faithfulness_anti_hallucination(
        self, evaluator, case: AgisEvalCase
    ):
        """
        A|C (Faithfulness) deve ser ≥ 0.65 — agente não deve inventar dados
        que não estejam no contexto das skills.
        """
        result = await evaluator.evaluate(
            question=case.question,
            context=case.context,
            answer=case.answer,
        )
        faithfulness = result.generation_score  # média de A|C + A|Q
        assert faithfulness >= 0.65, (
            f"{case.id}: generation_score={faithfulness:.3f} — possível alucinação\n"
            f"Diagnóstico: {result.diagnose()}"
        )

    @pytest.mark.asyncio
    async def test_ec001_encargos_answer_is_faithful(self, evaluator):
        """Caso EC-001 especificamente: resposta com ENCARGOS deve ser fiel ao contexto."""
        case = next(c for c in EVAL_CASES if c.id == "EC-001")
        result = await evaluator.evaluate(
            question=case.question,
            context=case.context,
            answer=case.answer,
        )
        assert result.overall_score >= 0.75, (
            f"EC-001 ENCARGOS: score={result.overall_score:.3f} abaixo de 0.75\n"
            f"Diagnóstico: {result.diagnose()}"
        )

    @pytest.mark.asyncio
    async def test_ec003_nogo_classification_is_relevant(self, evaluator):
        """Caso EC-003: classificação NOGO deve ser relevante para a pergunta."""
        case = next(c for c in EVAL_CASES if c.id == "EC-003")
        result = await evaluator.evaluate(
            question=case.question,
            context=case.context,
            answer=case.answer,
        )
        assert result.overall_score >= 0.75, (
            f"EC-003 NOGO: score={result.overall_score:.3f}\n"
            f"Diagnóstico: {result.diagnose()}"
        )
