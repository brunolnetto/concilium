"""Ferramentas MCP de Tributação Social — ADR-097 F6 / ADR-116 F5.

Tool unificada: calcular_tributos(tipo=) substitui as 3 tools anteriores
(calcular_custo_empregador_clt, calcular_inss_empregado, calcular_irrf).
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from concilium.infrastructure.auth.permission_guard import permission
from concilium.presentation.mcp._context import _wrap_response


def register(server: FastMCP) -> None:
    """Registra a ferramenta unificada de tributação social."""

    @server.tool()
    @permission("catalog:read")
    def calcular_tributos(
        tipo: Literal["clt_empregador", "inss_empregado", "irrf"],
        valor: float,
        categoria: str = "horista",
    ) -> dict[str, Any]:
        """Calcula tributos e encargos trabalhistas (CLT, INSS ou IRRF).

        tipos disponíveis:
        - clt_empregador: custo total do empregador para um funcionário CLT,
          decomposto por Grupo A-F + Judicial. valor = salário base mensal (R$).
          categoria: "horista" (campo/obra) ou "mensalista" (gestão/admin).
        - inss_empregado: INSS descontado do empregado pela tabela progressiva 2026.
          valor = salário bruto mensal (R$).
        - irrf: IRRF mensal com isenção efetiva Lei 15.270/2025.
          valor = base de cálculo após deduções (INSS + dependentes).
          Base <= R$ 5.000 -> IRRF = R$ 0,00.

        Args:
            tipo: Qual tributo calcular (clt_empregador | inss_empregado | irrf).
            valor: Valor base para o cálculo em R$.
            categoria: Categoria do trabalhador — só relevante para clt_empregador.
        """
        try:
            if tipo == "clt_empregador":
                from concilium.domain.services.financial.tributacao import calculate_employer_clt
                result = calculate_employer_clt(valor, categoria=categoria)
                multiplicador = round(result.custo_total / valor, 4) if valor > 0 else 0.0
                return _wrap_response({
                    "tipo": tipo,
                    "salario_base": result.salario_base,
                    "custo_total": result.custo_total,
                    "encargos_totais": round(result.custo_total - result.salario_base, 2),
                    "multiplicador_efetivo": multiplicador,
                    "categoria": categoria,
                    "breakdown": [
                        {"nome": item.nome, "percentual_pct": round(item.percentual * 100, 2),
                         "valor_R$": item.valor, "base_legal": item.base_legal}
                        for item in result.itens
                    ],
                })
            elif tipo == "inss_empregado":
                from concilium.domain.services.financial.tributacao import calculate_inss_employee
                inss = calculate_inss_employee(valor)
                return _wrap_response({
                    "tipo": tipo,
                    "salario_bruto": valor,
                    "inss_empregado": inss,
                    "aliquota_efetiva_pct": round(inss / valor * 100, 2) if valor > 0 else 0,
                    "base_irrf": round(valor - inss, 2),
                    "referencia": "Portaria MPS/MF nº 13/2026",
                })
            elif tipo == "irrf":
                from concilium.domain.services.financial.tributacao import calculate_irrf
                irrf = calculate_irrf(valor)
                return _wrap_response({
                    "tipo": tipo,
                    "base_calculo": valor,
                    "irrf_mensal": irrf,
                    "isento": irrf == 0.0,
                    "aliquota_efetiva_pct": round(irrf / valor * 100, 2) if valor > 0 else 0,
                    "referencia": "RFB 2026 + Lei 15.270/2025 (isencao ate R$ 5.000)",
                })
            else:
                return _wrap_response({"erro": f"tipo '{tipo}' invalido. Use: clt_empregador | inss_empregado | irrf"})
        except Exception as exc:
            return _wrap_response({"erro": str(exc)})
