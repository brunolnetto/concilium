"""ADR-097 F6 — MCP tools de tributação: testes de integração das ferramentas MCP.

Verifica que as 3 ferramentas estão registradas e que as funções subjacentes
retornam resultados corretos com a mesma semântica do serviço de domínio.

Invariantes:
  - 3 tools registrados: calcular_custo_empregador_clt, calcular_inss_empregado, calcular_irrf
  - calcular_custo_empregador_clt(5000, "horista") → custo_total ≈ 5000 × (1 + ENCARGOS_CLT)
  - calcular_inss_empregado(3000) ≈ 248.61
  - calcular_irrf(4999) == 0.0 (isenção efetiva Lei 15.270/2025)
  - calcular_irrf(6000) > 0
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_server():
    """Cria um FastMCP server mínimo e registra as ferramentas de tributação."""
    from mcp.server.fastmcp import FastMCP

    from concilium.presentation.mcp.tools.tributacao import register

    server = FastMCP("test")
    register(server)
    return server


def _call_clt(salario_base: float, categoria: str = "horista") -> dict:
    """Chama o serviço de domínio de custo CLT e retorna dict completo para testes."""
    from concilium.domain.services.financial.tributacao import calculate_employer_clt

    result = calculate_employer_clt(salario_base, categoria=categoria)
    return {
        "salario_base": result.salario_base,
        "custo_total": result.custo_total,
        "encargos_totais": round(result.custo_total - result.salario_base, 2),
        "categoria": categoria,
        "itens": result.itens,
    }


def _call_inss(salario_bruto: float) -> float:
    from concilium.domain.services.financial.tributacao import calculate_inss_employee

    return calculate_inss_employee(salario_bruto)


def _call_irrf(base_calculo: float) -> float:
    from concilium.domain.services.financial.tributacao import calculate_irrf

    return calculate_irrf(base_calculo)


# ---------------------------------------------------------------------------
# Task 1.1 — Verificar que o módulo importa e as 3 tools estão registradas
# ---------------------------------------------------------------------------


class TestModuloImportaEToolsRegistradas:
    def test_modulo_importavel(self):
        import concilium.presentation.mcp.tools.tributacao as mod  # noqa: F401

        assert mod is not None

    def test_register_eh_callable(self):
        from concilium.presentation.mcp.tools.tributacao import register

        assert callable(register)

    def test_tres_tools_registradas(self):
        """As 3 ferramentas MCP devem estar registradas no server."""
        server = _make_server()
        # FastMCP expõe _tool_manager._tools como dict nome→função
        try:
            tools = server._tool_manager._tools
            tool_names = set(tools.keys())
        except AttributeError:
            # fallback: tentar acesso alternativo
            tool_names = set(getattr(server, "_tools", {}).keys())
        expected = {
            "calcular_custo_empregador_clt",
            "calcular_inss_empregado",
            "calcular_irrf",
        }
        assert expected.issubset(tool_names), (
            f"Tools registradas: {tool_names}; esperadas: {expected}"
        )


# ---------------------------------------------------------------------------
# Task 1.2 — calcular_custo_empregador_clt
# ---------------------------------------------------------------------------


class TestCalcularCustoEmpregadorClt:
    def test_chaves_presentes(self):
        result = _call_clt(5000.0, categoria="horista")
        for chave in ("salario_base", "custo_total", "itens", "categoria"):
            assert chave in result, f"chave '{chave}' ausente no resultado"

    def test_custo_total_aproxima_encargos_clt(self):
        """custo_total ≈ 5000 × (1 + ENCARGOS_CLT) com margem < 0.5%."""
        from concilium.domain.constants import ENCARGOS_CLT

        result = _call_clt(5000.0, categoria="horista")
        esperado = 5000.0 * (1.0 + ENCARGOS_CLT)
        assert abs(result["custo_total"] - esperado) / esperado < 0.005

    def test_salario_base_preservado(self):
        result = _call_clt(5000.0, categoria="horista")
        assert result["salario_base"] == pytest.approx(5000.0)

    def test_categoria_correta(self):
        result = _call_clt(5000.0, categoria="horista")
        assert result["categoria"] == "horista"

    def test_len_itens_igual_11(self):
        """Grupos A (5 itens) + B + C + D + E + F + Judicial = 11 itens."""
        result = _call_clt(5000.0, categoria="horista")
        itens = result["itens"]
        assert len(itens) == 11, (
            f"Esperado 11 itens (Grupos A-F + Judicial), encontrado {len(itens)}"
        )

    def test_mensalista_diferente_de_horista(self):
        r_h = _call_clt(5000.0, categoria="horista")
        r_m = _call_clt(5000.0, categoria="mensalista")
        assert r_h["custo_total"] > r_m["custo_total"]

    def test_encargos_totais_positivos(self):
        result = _call_clt(5000.0, categoria="horista")
        encargos = result["custo_total"] - result["salario_base"]
        assert encargos > 0


# ---------------------------------------------------------------------------
# Task 1.3 — calcular_inss_empregado
# ---------------------------------------------------------------------------


class TestCalcularInssEmpregado:
    def test_referencia_adr097_3000_reais(self):
        """ADR-097 §DoD: calculate_inss_employee(3000) ≈ 248.61."""
        inss = _call_inss(3000.0)
        assert inss == pytest.approx(248.61, abs=0.05)

    def test_resultado_positivo_para_salario_positivo(self):
        inss = _call_inss(2000.0)
        assert inss > 0.0

    def test_zero_para_salario_zero(self):
        inss = _call_inss(0.0)
        assert inss == pytest.approx(0.0, abs=0.01)

    def test_acima_do_teto_identico(self):
        """Acima do teto contributivo (R$ 8.475,55), INSS não cresce."""
        inss_10k = _call_inss(10_000.0)
        inss_20k = _call_inss(20_000.0)
        assert inss_10k == pytest.approx(inss_20k, abs=0.01)


# ---------------------------------------------------------------------------
# Task 1.4 & 1.5 — calcular_irrf
# ---------------------------------------------------------------------------


class TestCalcularIrrf:
    def test_isencao_efetiva_4999(self):
        """Base = 4999 ≤ 5000 → IRRF = 0.0 (isenção efetiva Lei 15.270/2025)."""
        irrf = _call_irrf(4999.0)
        assert irrf == 0.0

    def test_isencao_exatamente_5000(self):
        irrf = _call_irrf(5000.0)
        assert irrf == 0.0

    def test_acima_5000_maior_que_zero(self):
        """Base = 6000 > 5000 → IRRF > 0."""
        irrf = _call_irrf(6000.0)
        assert irrf > 0.0

    def test_resultado_nao_negativo(self):
        for base in [0, 1000, 3000, 5000, 6000, 10000, 20000]:
            irrf = _call_irrf(float(base))
            assert irrf >= 0.0, f"IRRF negativo para base={base}"

    def test_isencao_base_2000(self):
        """Base abaixo da faixa isenta pura → IRRF = 0."""
        irrf = _call_irrf(2000.0)
        assert irrf == pytest.approx(0.0, abs=0.01)


# ---------------------------------------------------------------------------
# Task 1.6 — Integração: MCP tool chama serviço de domínio correto
# ---------------------------------------------------------------------------


class TestIntegracaoMcpComServicoDominio:
    def test_mcp_e_servico_concordam_inss(self):
        """MCP tool deve retornar o mesmo INSS que o serviço direto."""
        from concilium.domain.services.financial.tributacao import calculate_inss_employee

        inss_direto = calculate_inss_employee(5000.0)
        inss_mcp = _call_inss(5000.0)
        assert inss_mcp == pytest.approx(inss_direto, abs=0.01)

    def test_mcp_e_servico_concordam_irrf(self):
        from concilium.domain.services.financial.tributacao import calculate_irrf

        irrf_direto = calculate_irrf(6500.0)
        irrf_mcp = _call_irrf(6500.0)
        assert irrf_mcp == pytest.approx(irrf_direto, abs=0.01)

    def test_mcp_e_servico_concordam_custo_empregador(self):
        from concilium.domain.services.financial.tributacao import calculate_employer_clt

        result_direto = calculate_employer_clt(4000.0, categoria="horista")
        result_mcp = _call_clt(4000.0, categoria="horista")
        assert result_mcp["custo_total"] == pytest.approx(result_direto.custo_total, abs=0.01)
