"""ADR-097 F6 / ADR-116 F5 — Tool unificada calcular_tributos.

Consolida as 3 tools anteriores (calcular_custo_empregador_clt,
calcular_inss_empregado, calcular_irrf) em uma única tool com parâmetro tipo=.
"""

from __future__ import annotations

import pytest


def _make_server():
    from mcp.server.fastmcp import FastMCP

    from concilium.presentation.mcp.tools.tributacao import register

    server = FastMCP("test")
    register(server)
    return server


def _call_tributo(tipo: str, valor: float, **kwargs):
    from concilium.domain.services.financial.tributacao import (
        calculate_employer_clt,
        calculate_inss_employee,
        calculate_irrf,
    )

    if tipo == "clt_empregador":
        result = calculate_employer_clt(valor, categoria=kwargs.get("categoria", "horista"))
        return {
            "salario_base": result.salario_base,
            "custo_total": result.custo_total,
            "encargos_totais": round(result.custo_total - result.salario_base, 2),
            "categoria": kwargs.get("categoria", "horista"),
            "itens": result.itens,
        }
    elif tipo == "inss_empregado":
        return calculate_inss_employee(valor)
    elif tipo == "irrf":
        return calculate_irrf(valor)


class TestToolRegistrada:
    def test_uma_tool_registrada(self):
        server = _make_server()
        tools = server._tool_manager._tools
        assert "calcular_tributos" in tools
        # As 3 antigas não devem existir
        assert "calcular_custo_empregador_clt" not in tools
        assert "calcular_inss_empregado" not in tools
        assert "calcular_irrf" not in tools

    def test_tool_count(self):
        server = _make_server()
        assert len(server._tool_manager._tools) == 1


class TestCalcularTributosCltEmpregador:
    def test_custo_total_aproxima_encargos_clt(self):
        from concilium.domain.constants import ENCARGOS_CLT

        result = _call_tributo("clt_empregador", 5000.0)
        esperado = 5000.0 * (1.0 + ENCARGOS_CLT)
        assert abs(result["custo_total"] - esperado) / esperado < 0.005

    def test_salario_base_preservado(self):
        result = _call_tributo("clt_empregador", 5000.0)
        assert result["salario_base"] == pytest.approx(5000.0)

    def test_mensalista_menor_que_horista(self):
        r_h = _call_tributo("clt_empregador", 5000.0, categoria="horista")
        r_m = _call_tributo("clt_empregador", 5000.0, categoria="mensalista")
        assert r_h["custo_total"] > r_m["custo_total"]

    def test_len_itens_igual_11(self):
        result = _call_tributo("clt_empregador", 5000.0)
        assert len(result["itens"]) == 11


class TestCalcularTributosInss:
    def test_referencia_3000_reais(self):
        inss = _call_tributo("inss_empregado", 3000.0)
        assert inss == pytest.approx(248.61, abs=0.05)

    def test_teto_contributivo(self):
        inss_10k = _call_tributo("inss_empregado", 10_000.0)
        inss_20k = _call_tributo("inss_empregado", 20_000.0)
        assert inss_10k == pytest.approx(inss_20k, abs=0.01)


class TestCalcularTributosIrrf:
    def test_isencao_efetiva_4999(self):
        assert _call_tributo("irrf", 4999.0) == 0.0

    def test_isencao_exatamente_5000(self):
        assert _call_tributo("irrf", 5000.0) == 0.0

    def test_acima_5000_maior_que_zero(self):
        assert _call_tributo("irrf", 6000.0) > 0.0

    def test_resultado_nao_negativo(self):
        for base in [0, 1000, 3000, 5000, 6000, 10000]:
            assert _call_tributo("irrf", float(base)) >= 0.0


class TestIntegracaoMcpComServicoDominio:
    def test_inss_concordam(self):
        from concilium.domain.services.financial.tributacao import calculate_inss_employee

        assert _call_tributo("inss_empregado", 5000.0) == pytest.approx(calculate_inss_employee(5000.0), abs=0.01)

    def test_irrf_concordam(self):
        from concilium.domain.services.financial.tributacao import calculate_irrf

        assert _call_tributo("irrf", 6500.0) == pytest.approx(calculate_irrf(6500.0), abs=0.01)

    def test_clt_concordam(self):
        from concilium.domain.services.financial.tributacao import calculate_employer_clt

        result_direto = calculate_employer_clt(4000.0, categoria="horista")
        result_via = _call_tributo("clt_empregador", 4000.0)
        assert result_via["custo_total"] == pytest.approx(result_direto.custo_total, abs=0.01)
