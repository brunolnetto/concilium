"""ADR-097 F5 — Cálculos de tributação individual: INSS, IRRF e custo total empregador CLT.

TDD: testes escritos antes da implementação em domain/services/tributacao.py.

Invariantes:
  - calculate_inss_employee(3000.00) ≈ R$ 248,61 (tabela progressiva 2026)
  - salário ≤ 5.000 → IRRF = 0 (isenção efetiva Lei 15.270/2025)
  - calculate_employer_clt(horista).custo_total ≈ salario × 2.777 (ENCARGOS_CLT + 1)
  - soma dos itens de TaxationResult == custo_total - salario_base
"""

from __future__ import annotations

import pytest


def _import():
    from concilium.domain.services.financial.tributacao import (
        TaxationResult,
        calculate_employer_clt,
        calculate_inss_employee,
        calculate_irrf,
    )

    return calculate_inss_employee, calculate_irrf, calculate_employer_clt, TaxationResult


# ── INSS empregado ────────────────────────────────────────────────────────────


class TestCalculateInssEmployee:
    def test_abaixo_primeira_faixa(self):
        ci, *_ = _import()
        # R$ 1.500 → faixa 7,5%: 1500 × 0.075 - 0 = 112.50
        assert ci(1_500.0) == pytest.approx(112.50, abs=0.02)

    def test_referencia_adr097(self):
        ci, *_ = _import()
        # ADR-097 §DoD Fase 3: calculate_inss_employee(3000) ≈ 248.61
        assert ci(3_000.0) == pytest.approx(248.61, abs=0.05)

    def test_faixa_14_pct(self):
        ci, *_ = _import()
        # R$ 5.000 → faixa 14%: 5000 × 0.14 - 198.26 = 501.74
        assert ci(5_000.0) == pytest.approx(501.74, abs=0.02)

    def test_teto_maximo(self):
        ci, *_ = _import()
        # Acima do teto (R$ 8.475,55): INSS máximo = 8475.55 × 0.14 − 198.26 = 988.32
        # (O ADR cita ≈ 988.09 como aproximação; a tabela exata dá 988.32)
        result = ci(20_000.0)
        assert result == pytest.approx(988.32, abs=0.05)
        assert ci(10_000.0) == ci(20_000.0)  # idêntico acima do teto

    def test_resultado_positivo(self):
        ci, *_ = _import()
        assert ci(1_621.0) > 0
        assert ci(0.0) == pytest.approx(0.0, abs=0.01)


# ── IRRF mensal ───────────────────────────────────────────────────────────────


class TestCalculateIrrf:
    def test_isencao_efetiva_abaixo_de_5000(self):
        _, irrf, *_ = _import()
        assert irrf(4_999.99) == pytest.approx(0.0, abs=0.01)
        assert irrf(5_000.0) == pytest.approx(0.0, abs=0.01)

    def test_acima_de_5000_nao_e_zero(self):
        _, irrf, *_ = _import()
        assert irrf(6_000.0) > 0

    def test_abaixo_limite_isento_puro(self):
        _, irrf, *_ = _import()
        # R$ 2.000 → faixa isenta (≤ 2428.80)
        assert irrf(2_000.0) == pytest.approx(0.0, abs=0.01)

    def test_faixa_7_5_pct(self):
        _, irrf, *_ = _import()
        # R$ 2.600: faixa 7.5% → 2600 × 0.075 - 182.16 = 195 - 182.16 = 12.84
        # mas base ≤ 5000 → isenção efetiva → 0
        assert irrf(2_600.0) == pytest.approx(0.0, abs=0.01)

    def test_resultado_nao_negativo(self):
        _, irrf, *_ = _import()
        for base in [0, 1000, 2000, 3000, 4000, 5000, 6000, 8000, 15000]:
            assert irrf(float(base)) >= 0.0


# ── TaxationResult e calculate_employer_clt ───────────────────────────────────


class TestCalculateEmployerClt:
    def test_custo_total_horista_aproxima_fator_2777(self):
        _, _, calc, _ = _import()
        salario = 3_000.0
        result = calc(salario, categoria="horista")
        # custo_total ≈ salario × (1 + 1.777) = salario × 2.777
        esperado = salario * 2.777
        assert abs(result.custo_total - esperado) / esperado < 0.005  # < 0.5% de desvio

    def test_custo_total_mensalista_aproxima_fator_206(self):
        _, _, calc, _ = _import()
        salario = 5_000.0
        result = calc(salario, categoria="mensalista")
        esperado = salario * 2.060
        assert abs(result.custo_total - esperado) / esperado < 0.005

    def test_salario_base_preservado(self):
        _, _, calc, _ = _import()
        result = calc(4_000.0, categoria="horista")
        assert result.salario_base == pytest.approx(4_000.0)

    def test_soma_itens_igual_encargos_totais(self):
        _, _, calc, _ = _import()
        result = calc(3_000.0, categoria="horista")
        soma_itens = sum(item.valor for item in result.itens)
        encargos = result.custo_total - result.salario_base
        assert abs(soma_itens - encargos) < 0.10  # tolerância R$ 0.10

    def test_itens_nao_vazios(self):
        _, _, calc, _ = _import()
        result = calc(3_000.0)
        assert len(result.itens) >= 7  # pelo menos Grupos A-F + Judicial

    def test_grupo_a_presente(self):
        _, _, calc, _ = _import()
        result = calc(3_000.0, categoria="horista")
        nomes = [i.nome for i in result.itens]
        assert any("A" in n or "INSS" in n or "FGTS" in n for n in nomes)

    def test_categoria_default_e_horista(self):
        _, _, calc, _ = _import()
        r_default = calc(3_000.0)
        r_horista = calc(3_000.0, categoria="horista")
        assert r_default.custo_total == pytest.approx(r_horista.custo_total, abs=0.01)

    def test_resultado_auditavel_tem_base_legal(self):
        _, _, calc, _ = _import()
        result = calc(3_000.0)
        itens_com_base = [i for i in result.itens if i.base_legal]
        assert len(itens_com_base) > 0
