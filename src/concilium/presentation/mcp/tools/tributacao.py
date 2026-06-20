"""Ferramentas MCP de Tributação Social — ADR-097 F6.

Expõe as funções de simulação de custo de empregador CLT, INSS e IRRF
para uso em contextos de People & Finance pelo agente.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.presentation.mcp._context import _wrap_response
from concilium.infrastructure.auth.permission_guard import permission


def register(server: FastMCP) -> None:
    """Registra as ferramentas de tributação social."""

    @server.tool()
    @permission("catalog:read")
    def calcular_custo_empregador_clt(
        salario_base: float,
        categoria: str = "horista",
    ) -> dict[str, Any]:
        """Calcula o custo total do empregador para um funcionário CLT, decomposto por Grupo A–F + Judicial.

        Use para simular o custo real de contratação e comparar com tabelas de mercado.
        Categorias disponíveis: "horista" (campo/obra, 177,7%) ou "mensalista" (gestão/admin, 106%).

        Args:
            salario_base: Salário base mensal puro (sem encargos) em R$.
            categoria: "horista" (padrão) ou "mensalista".

        Returns:
            custo_total, salario_base, multiplicador efetivo e breakdown por grupo.
        """
        from concilium.domain.services.financial.tributacao import calculate_employer_clt

        try:
            result = calculate_employer_clt(salario_base, categoria=categoria)
            multiplicador = round(result.custo_total / salario_base, 4) if salario_base > 0 else 0.0
            return _wrap_response(
                {
                    "salario_base": result.salario_base,
                    "custo_total": result.custo_total,
                    "encargos_totais": round(result.custo_total - result.salario_base, 2),
                    "multiplicador_efetivo": multiplicador,
                    "categoria": categoria,
                    "breakdown": [
                        {
                            "nome": item.nome,
                            "percentual_pct": round(item.percentual * 100, 2),
                            "valor_R$": item.valor,
                            "base_legal": item.base_legal,
                        }
                        for item in result.itens
                    ],
                }
            )
        except Exception as exc:
            return _wrap_response({"erro": str(exc)})

    @server.tool()
    @permission("catalog:read")
    def calcular_inss_empregado(salario_bruto: float) -> dict[str, Any]:
        """Calcula o INSS descontado do empregado pela tabela progressiva 2026.

        Útil para simular o custo líquido para o trabalhador e comparar com regras de desoneração.
        O cálculo é progressivo (método dedutivo), com teto em R$ 8.475,55 → máx ≈ R$ 988,32.

        Args:
            salario_bruto: Salário bruto mensal em R$.
        """
        from concilium.domain.services.financial.tributacao import calculate_inss_employee

        try:
            inss = calculate_inss_employee(salario_bruto)
            salario_liquido_antes_irrf = round(salario_bruto - inss, 2)
            return _wrap_response(
                {
                    "salario_bruto": salario_bruto,
                    "inss_empregado": inss,
                    "aliquota_efetiva_pct": round(inss / salario_bruto * 100, 2) if salario_bruto > 0 else 0,
                    "base_irrf": salario_liquido_antes_irrf,
                    "referencia": "Portaria MPS/MF nº 13/2026",
                }
            )
        except Exception as exc:
            return _wrap_response({"erro": str(exc)})

    @server.tool()
    @permission("catalog:read")
    def calcular_irrf(base_calculo: float) -> dict[str, Any]:
        """Calcula o IRRF mensal com isenção efetiva Lei 15.270/2025.

        Base de cálculo = salário bruto − INSS empregado − R$ 189,59 × nº dependentes.
        Isenção efetiva: base ≤ R$ 5.000 → IRRF = R$ 0,00.

        Args:
            base_calculo: Base de cálculo do IRRF após deduções (INSS + dependentes).
        """
        from concilium.domain.services.financial.tributacao import calculate_irrf

        try:
            irrf = calculate_irrf(base_calculo)
            return _wrap_response(
                {
                    "base_calculo": base_calculo,
                    "irrf_mensal": irrf,
                    "isento": irrf == 0.0,
                    "aliquota_efetiva_pct": round(irrf / base_calculo * 100, 2) if base_calculo > 0 else 0,
                    "referencia": "RFB 2026 + Lei 15.270/2025 (isenção até R$ 5.000)",
                }
            )
        except Exception as exc:
            return _wrap_response({"erro": str(exc)})
