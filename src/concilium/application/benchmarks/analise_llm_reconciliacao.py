"""Análise de disparidades com LLM (Claude).

Utiliza capacidades de análise de LLM para:
1. Interpretar padrões nas disparidades
2. Identificar anomalias e inconsistências
3. Gerar insights sobre divergências planejamento ↔ canonical
4. Sugerir explicações para os desvios
5. Fornecer recomendações de ação

Ao invés de tentar mapear determinísticamente, deixa o LLM
usar raciocínio e compreensão para identificar insights.
"""

from __future__ import annotations

import anthropic
from dataclasses import dataclass
from typing import Any


@dataclass
class AnaliseLLMReconciliacao:
    """Resultado da análise LLM das disparidades."""

    resumo_executivo: str
    padroes_identificados: list[str]
    anomalias: list[str]
    hipoteses: list[str]
    recomendacoes: list[str]
    analise_detalhada: str


def preparar_contexto_para_llm(dados_planejamento: dict, dados_canonical: dict, disparidades: list) -> str:
    """Prepara contexto estruturado para enviar ao LLM."""
    contexto = """# CONTEXTO: Reconciliação Planejamento.txt ↔ Canonical Model

## 1. DADOS DE PLANEJAMENTO (Original)
Custos curados diretamente do planejamento Excel original:

### Resumo Financeiro
"""

    total_plan_sem_bdi = sum(
        item.get("total_sem_bdi", 0)
        for item in dados_planejamento.values()
        if isinstance(item, dict)
    )
    total_plan_com_bdi = sum(
        item.get("total_com_bdi", 0)
        for item in dados_planejamento.values()
        if isinstance(item, dict)
    )

    contexto += f"""
- Total Direto (s/ BDI): R$ {total_plan_sem_bdi:,.2f}
- Total Direto (c/ BDI): R$ {total_plan_com_bdi:,.2f}
- BDI Aplicado: ~{((total_plan_com_bdi / total_plan_sem_bdi - 1) * 100) if total_plan_sem_bdi > 0 else 0:.1f}%

### Items Principais (Top 10 por valor)
"""

    items_ordenados = sorted(
        [
            (k, v.get("total_com_bdi", 0))
            for k, v in dados_planejamento.items()
            if isinstance(v, dict) and v.get("total_com_bdi", 0) > 0
        ],
        key=lambda x: x[1],
        reverse=True,
    )

    for item_id, valor in items_ordenados[:10]:
        item_data = dados_planejamento[item_id]
        contexto += f"\n- {item_id}: R$ {valor:,.2f} | Desc: {item_data.get('descricao', 'N/A')[:50]}"

    contexto += """

## 2. DADOS DO PIPELINE (Canonical)
Custos calculados pelo motor financeiro após processamento:

### Resumo Financeiro
"""

    total_canon = sum(dados_canonical.values())
    contexto += f"""
- Total Direto: R$ {total_canon:,.2f}

### Items Principais (Top 10 por valor)
"""

    items_canon = sorted(
        [(k, v) for k, v in dados_canonical.items() if v > 0],
        key=lambda x: x[1],
        reverse=True,
    )

    for item_id, valor in items_canon[:10]:
        contexto += f"\n- {item_id}: R$ {valor:,.2f}"

    contexto += """

## 3. DISPARIDADES IDENTIFICADAS
Diferenças entre planejamento e canonical:

### Categorias de Disparidades
"""

    # Contar por tipo
    nao_executados = len([d for d in disparidades if d.get("tipo") == "NAO_EXECUTADO"])
    nao_planejados = len([d for d in disparidades if d.get("tipo") == "NAO_PLANEJADO"])

    contexto += f"""
- Items Planejados mas NÃO EXECUTADOS: {nao_executados}
- Items EXECUTADOS mas NÃO PLANEJADOS: {nao_planejados}

### Top Disparidades (Maior Delta)
"""

    disparidades_top = sorted(disparidades, key=lambda x: abs(x.get("delta", 0)), reverse=True)[:10]

    for disp in disparidades_top:
        contexto += (
            f"\n- {disp['item_id']}: {disp['tipo']} | "
            f"Delta: R$ {disp['delta']:,.2f} ({disp.get('delta_pct', 0):+.1f}%) | "
            f"Plan: R$ {disp.get('planejamento_sem_bdi', 0):,.2f} | "
            f"Canon: R$ {disp.get('canonical', 0):,.2f}"
        )

    contexto += """

## 4. PERGUNTAS PARA ANÁLISE
Com base nos dados acima, analise:

1. **Padrões de Divergência**: Há padrões ou categorias de items que divergem?
2. **Granularidade**: As nomenclaturas sugerem diferenças de granularidade?
3. **Completude**: Há items que deveriam estar mapeados mas não estão?
4. **Metodologia**: As diferenças sugerem mudanças em como custos são calculados?
5. **Validação**: Quais são os sinais de que os dados estão corretos/incorretos?
"""

    return contexto


class AnalisadorLLMReconciliacao:
    """Usa Claude para analisar disparidades de reconciliação."""

    def __init__(self, api_key: str | None = None):
        self.client = anthropic.Anthropic(api_key=api_key)

    def analisar(
        self,
        dados_planejamento: dict,
        dados_canonical: dict,
        disparidades: list,
    ) -> AnaliseLLMReconciliacao:
        """Executa análise LLM das disparidades."""

        contexto = preparar_contexto_para_llm(dados_planejamento, dados_canonical, disparidades)

        # Criar prompt para análise
        prompt = f"""{contexto}

## SOLICITAÇÃO DE ANÁLISE

Por favor, analise estes dados de reconciliação planejamento ↔ canonical e forneça:

1. **Resumo Executivo** (2-3 parágrafos): Visão geral das disparidades e seu significado
2. **Padrões Identificados** (lista): Padrões ou estruturas reconhecíveis nos dados
3. **Anomalias** (lista): Dados inusitados ou inesperados
4. **Hipóteses** (lista): Possíveis explicações para as disparidades
5. **Recomendações** (lista): Ações sugeridas para resolver ou entender as divergências
6. **Análise Detalhada** (1-2 parágrafos): Aprofundamento técnico

Formate a resposta como JSON com as seguintes chaves:
{{
    "resumo_executivo": "...",
    "padroes_identificados": ["padrão 1", "padrão 2", ...],
    "anomalias": ["anomalia 1", ...],
    "hipoteses": ["hipótese 1", ...],
    "recomendacoes": ["recomendação 1", ...],
    "analise_detalhada": "..."
}}
"""

        # Chamar Claude
        message = self.client.messages.create(
            model="claude-opus-4-8",
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )

        # Parse resposta
        response_text = message.content[0].text

        # Tentar extrair JSON da resposta
        import json
        import re

        # Procurar bloco JSON
        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if json_match:
            try:
                resultado = json.loads(json_match.group())
                return AnaliseLLMReconciliacao(
                    resumo_executivo=resultado.get("resumo_executivo", ""),
                    padroes_identificados=resultado.get("padroes_identificados", []),
                    anomalias=resultado.get("anomalias", []),
                    hipoteses=resultado.get("hipoteses", []),
                    recomendacoes=resultado.get("recomendacoes", []),
                    analise_detalhada=resultado.get("analise_detalhada", ""),
                )
            except json.JSONDecodeError:
                pass

        # Fallback: retornar resposta completa como análise detalhada
        return AnaliseLLMReconciliacao(
            resumo_executivo="Veja análise detalhada",
            padroes_identificados=[],
            anomalias=[],
            hipoteses=[],
            recomendacoes=[],
            analise_detalhada=response_text,
        )


def gerar_relatorio_llm(analise: AnaliseLLMReconciliacao) -> str:
    """Gera relatório formatado da análise LLM."""
    linhas = [
        "=" * 100,
        "ANÁLISE LLM: Reconciliação Planejamento.txt ↔ Canonical",
        "=" * 100,
        "",
        "[RESUMO EXECUTIVO]",
    ]

    if analise.resumo_executivo:
        for paragrafo in analise.resumo_executivo.split("\n"):
            if paragrafo.strip():
                linhas.append(f"  {paragrafo.strip()}")
    else:
        linhas.append("  (Análise em progresso)")

    linhas.extend([
        "",
        "[PADRÕES IDENTIFICADOS]",
    ])

    if analise.padroes_identificados:
        for padrao in analise.padroes_identificados:
            linhas.append(f"  • {padrao}")
    else:
        linhas.append("  (Nenhum padrão significativo)")

    linhas.extend([
        "",
        "[ANOMALIAS]",
    ])

    if analise.anomalias:
        for anomalia in analise.anomalias:
            linhas.append(f"  ⚠️  {anomalia}")
    else:
        linhas.append("  (Nenhuma anomalia detectada)")

    linhas.extend([
        "",
        "[HIPÓTESES EXPLICATIVAS]",
    ])

    if analise.hipoteses:
        for i, hipotese in enumerate(analise.hipoteses, 1):
            linhas.append(f"  {i}. {hipotese}")
    else:
        linhas.append("  (Nenhuma hipótese gerada)")

    linhas.extend([
        "",
        "[RECOMENDAÇÕES]",
    ])

    if analise.recomendacoes:
        for i, rec in enumerate(analise.recomendacoes, 1):
            linhas.append(f"  {i}. {rec}")
    else:
        linhas.append("  (Nenhuma recomendação)")

    linhas.extend([
        "",
        "[ANÁLISE DETALHADA]",
    ])

    if analise.analise_detalhada:
        for paragrafo in analise.analise_detalhada.split("\n"):
            if paragrafo.strip():
                linhas.append(f"  {paragrafo.strip()}")

    linhas.extend([
        "",
        "=" * 100,
    ])

    return "\n".join(linhas)
