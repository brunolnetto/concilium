"""Testes unitários para BridgeAnalyzer (ADR-039 — The Bridge).

Casos cobertos:
  TC1: F_i inteiros (frentes exatas)         — fator_quantizacao = 1.0
  TC2: F_i fracionados < 1                   — fator_quantizacao > 1
  TC3: Praticabilidade 0.83 (regime chuvoso) — N3 > N2
  TC4: Delta real isolado (N4 fornecido)      — status_alerta correto
  TC5: N4 ausente                             — delta_real_abs = None
  TC6: Fator quantizacao médio (lista mista)
  TC7: calcular_necessidade_fracionada helpers
  TC8: Validações de entrada inválida
"""

from __future__ import annotations

import dataclasses

import pytest
from pydantic import ValidationError

from concilium.domain.services.bridge_analyzer import BridgeAnalyzer

# ── TC1: Frentes inteiras — sem overhead de quantização ──────────────────────


def test_fator_quantizacao_frentes_inteiras():
    """F_i inteiros → ceil(F_i)/F_i = 1.0 → fq = 1.0"""
    f_inteiros = [1.0, 2.0, 3.0, 4.0]
    fq = BridgeAnalyzer.fator_quantizacao_medio(f_inteiros)
    assert fq == pytest.approx(1.0, abs=1e-6)


def test_calcular_frentes_inteiras_preserva_nivel_1():
    """Com F_i inteiros e P=1.0: N2 == N1, N3 == N1, delta_estrutural == 0."""
    resultado = BridgeAnalyzer.calcular(
        nivel_1=100_000.0,
        necessidades_fracionadas=[1.0, 2.0, 3.0],
        praticabilidade=1.0,
    )
    assert resultado.fator_quantizacao == pytest.approx(1.0, abs=1e-4)
    assert resultado.nivel_2_catalogo_escalado == pytest.approx(100_000.0, abs=0.5)
    assert resultado.nivel_3_catalogo_normalizado == pytest.approx(100_000.0, abs=0.5)
    assert resultado.delta_estrutural_abs == pytest.approx(0.0, abs=0.1)


# ── TC2: F_i fracionados < 1 — overhead de quantização alto ─────────────────


def test_fator_quantizacao_fracionado_alto():
    """F = 0.5 → ceil(0.5)/0.5 = 1/0.5 = 2.0 → custo duplica."""
    fq = BridgeAnalyzer.fator_quantizacao_medio([0.5])
    assert fq == pytest.approx(2.0, abs=1e-6)


def test_fator_quantizacao_fracionado_lista():
    """F = [0.5, 0.25] → [2.0, 4.0] → média 3.0"""
    fq = BridgeAnalyzer.fator_quantizacao_medio([0.5, 0.25])
    assert fq == pytest.approx(3.0, abs=1e-6)


def test_calcular_com_frentes_fracionadas():
    """F_i = [0.5, 0.75] — nenhuma é inteira, overhead real."""
    resultado = BridgeAnalyzer.calcular(
        nivel_1=50_000.0,
        necessidades_fracionadas=[0.5, 0.75],
        praticabilidade=1.0,
    )
    # fq = (ceil(0.5)/0.5 + ceil(0.75)/0.75) / 2 = (2.0 + 4/3) / 2 ≈ 1.667
    esperado_fq = (2.0 + 4 / 3) / 2
    assert resultado.fator_quantizacao == pytest.approx(esperado_fq, rel=1e-3)
    assert resultado.nivel_2_catalogo_escalado > resultado.nivel_1_catalogo_base
    assert resultado.desvio_escala_abs > 0


# ── TC3: Praticabilidade 0.83 (regime chuvoso) ───────────────────────────────


def test_praticabilidade_083_amplia_nivel_3():
    """P=0.83 → N3 = N2 / 0.83 > N2."""
    resultado = BridgeAnalyzer.calcular(
        nivel_1=100_000.0,
        necessidades_fracionadas=[1.0],
        praticabilidade=0.83,
    )
    assert resultado.fator_praticabilidade == 0.83
    n2 = resultado.nivel_2_catalogo_escalado
    n3 = resultado.nivel_3_catalogo_normalizado
    assert n3 == pytest.approx(n2 / 0.83, abs=0.5)
    assert resultado.desvio_clima_abs == pytest.approx(n3 - n2, abs=0.5)
    assert resultado.desvio_clima_abs > 0


def test_praticabilidade_083_delta_estrutural():
    """Com P=0.83 e F_i inteiros: desvio_escala=0, apenas desvio_clima."""
    resultado = BridgeAnalyzer.calcular(
        nivel_1=100_000.0,
        necessidades_fracionadas=[2.0, 3.0],
        praticabilidade=0.83,
    )
    assert resultado.desvio_escala_abs == pytest.approx(0.0, abs=0.5)
    assert resultado.desvio_clima_abs > 0
    assert resultado.delta_estrutural_abs == pytest.approx(resultado.desvio_clima_abs, abs=0.5)


# ── TC4: Delta real isolado — status_alerta correto ──────────────────────────


def test_delta_real_verde_abaixo_10pct():
    """N4 = N3 × 1.05 → delta_real = 5% → VERDE."""
    n3_estimado = 100_000.0 / 0.83  # ≈ 120_482
    n4 = n3_estimado * 1.05  # 5% acima de N3
    resultado = BridgeAnalyzer.calcular(
        nivel_1=100_000.0,
        necessidades_fracionadas=[1.0],
        praticabilidade=0.83,
        nivel_4=n4,
    )
    assert resultado.status_alerta == "VERDE"
    assert resultado.delta_real_abs is not None
    assert abs(resultado.delta_real_percentual) <= 10.0


def test_delta_real_amarelo_entre_10_e_25pct():
    """N4 = N3 × 1.15 → delta_real ≈ 13% → AMARELO."""
    n1 = 100_000.0
    resultado = BridgeAnalyzer.calcular(
        nivel_1=n1,
        necessidades_fracionadas=[1.0],
        praticabilidade=1.0,
        nivel_4=n1 * 1.15,
    )
    assert resultado.status_alerta == "AMARELO"


def test_delta_real_vermelho_acima_25pct():
    """N4 = N1 × 1.50 → delta_pct = (N4-N3)/N4 = 0.50/1.50 = 33% → VERMELHO.

    Nota: delta_real_pct = (N4-N3)/N4×100, não (N4-N3)/N1×100.
    Para VERMELHO (>25%) com N3=N1 precisa N4 > N1/0.75 ≈ N1×1.333.
    """
    n1 = 100_000.0
    resultado = BridgeAnalyzer.calcular(
        nivel_1=n1,
        necessidades_fracionadas=[1.0],
        praticabilidade=1.0,
        nivel_4=n1 * 1.50,  # delta_pct = 0.50/1.50 × 100 ≈ 33.3%
    )
    assert resultado.status_alerta == "VERMELHO"
    assert resultado.delta_real_percentual is not None
    assert abs(resultado.delta_real_percentual) > 25.0


def test_delta_real_negativo_positivo_gestao():
    """N4 < N3 → gestão superou o catálogo normalizado (eficiência positiva)."""
    resultado = BridgeAnalyzer.calcular(
        nivel_1=100_000.0,
        necessidades_fracionadas=[1.0],
        praticabilidade=0.83,
        nivel_4=100_000.0 * 0.90,  # 10% abaixo de N1
    )
    # N4 < N3 → delta_real_abs < 0 (favorável)
    assert resultado.delta_real_abs < 0


# ── TC5: N4 ausente ───────────────────────────────────────────────────────────


def test_sem_nivel_4_delta_none():
    """Sem N4, delta_real_abs e delta_real_percentual devem ser None."""
    resultado = BridgeAnalyzer.calcular(
        nivel_1=50_000.0,
        necessidades_fracionadas=[0.8, 1.2],
        praticabilidade=0.90,
    )
    assert resultado.nivel_4_operacional is None
    assert resultado.delta_real_abs is None
    assert resultado.delta_real_percentual is None
    assert resultado.status_alerta == "SEM_DADOS"


# ── TC6: Fator quantização lista mista ────────────────────────────────────────


def test_fator_quantizacao_lista_mista():
    """[1.0, 0.5, 0.25, 1.5] → [1.0, 2.0, 4.0, ceil(1.5)/1.5=4/3] → média"""
    frentes = [1.0, 0.5, 0.25, 1.5]
    esperado = (1.0 + 2.0 + 4.0 + (2.0 / 1.5)) / 4
    fq = BridgeAnalyzer.fator_quantizacao_medio(frentes)
    assert fq == pytest.approx(esperado, rel=1e-6)


def test_fator_quantizacao_lista_vazia():
    """Lista vazia → fator 1.0 (sem quantização)."""
    fq = BridgeAnalyzer.fator_quantizacao_medio([])
    assert fq == 1.0


def test_fator_quantizacao_ignora_zeros():
    """Zeros são ignorados (evita divisão por zero)."""
    fq = BridgeAnalyzer.fator_quantizacao_medio([0.0, 0.0, 1.0])
    assert fq == pytest.approx(1.0, abs=1e-6)


# ── TC7: calcular_necessidade_fracionada helpers ──────────────────────────────


def test_necessidade_fracionada_basica():
    """F = Q / (P × T) = 1000 / (50 × 20) = 1.0 exato."""
    f = BridgeAnalyzer.calcular_necessidade_fracionada(quantidade=1000.0, produtividade=50.0, horas_disponiveis=20.0)
    assert f == pytest.approx(1.0, abs=1e-9)


def test_necessidade_fracionada_menor_que_1():
    """Q pequena → F < 1 (frente não precisa de uma equipe inteira)."""
    f = BridgeAnalyzer.calcular_necessidade_fracionada(quantidade=100.0, produtividade=50.0, horas_disponiveis=20.0)
    assert f == pytest.approx(0.1, abs=1e-9)
    assert 0 < f < 1


def test_necessidade_fracionada_resultado_inteiro_exato():
    """Q = P × T × 3 → F = 3.0 exato."""
    f = BridgeAnalyzer.calcular_necessidade_fracionada(quantidade=3000.0, produtividade=100.0, horas_disponiveis=10.0)
    assert f == pytest.approx(3.0, abs=1e-9)


# ── TC8: Validações de entrada inválida ───────────────────────────────────────


def test_calcular_praticabilidade_zero_levanta_valueerror():
    with pytest.raises(ValueError, match="praticabilidade"):
        BridgeAnalyzer.calcular(nivel_1=100_000.0, necessidades_fracionadas=[1.0], praticabilidade=0.0)


def test_calcular_praticabilidade_negativa_levanta_valueerror():
    with pytest.raises(ValueError, match="praticabilidade"):
        BridgeAnalyzer.calcular(nivel_1=100_000.0, necessidades_fracionadas=[1.0], praticabilidade=-0.5)


def test_calcular_praticabilidade_acima_1_levanta_valueerror():
    with pytest.raises(ValueError, match="praticabilidade"):
        BridgeAnalyzer.calcular(nivel_1=100_000.0, necessidades_fracionadas=[1.0], praticabilidade=1.01)


def test_necessidade_fracionada_produtividade_zero_levanta_valueerror():
    with pytest.raises(ValueError, match="produtividade"):
        BridgeAnalyzer.calcular_necessidade_fracionada(1000.0, 0.0, 20.0)


def test_necessidade_fracionada_horas_zero_levanta_valueerror():
    with pytest.raises(ValueError, match="horas_disponiveis"):
        BridgeAnalyzer.calcular_necessidade_fracionada(1000.0, 50.0, 0.0)


# ── TC9: Propriedades derivadas e imutabilidade ───────────────────────────────


def test_bridge_analysis_imutavel():
    """BridgeAnalysis é frozen=True — atribuição deve lançar."""
    resultado = BridgeAnalyzer.calcular(nivel_1=100_000.0, necessidades_fracionadas=[1.0], praticabilidade=1.0)
    with pytest.raises((ValidationError, dataclasses.FrozenInstanceError)):
        resultado.nivel_1_catalogo_base = 999.0  # type: ignore[misc]


def test_delta_estrutural_e_soma_desvios():
    """delta_estrutural_abs deve ser igual a desvio_escala + desvio_clima."""
    resultado = BridgeAnalyzer.calcular(
        nivel_1=100_000.0,
        necessidades_fracionadas=[0.6, 0.8],
        praticabilidade=0.83,
    )
    soma = resultado.desvio_escala_abs + resultado.desvio_clima_abs
    assert resultado.delta_estrutural_abs == pytest.approx(soma, abs=0.5)


def test_nivel_4_como_proxy_custo_direto():
    """Cenário realista: N1=500k, frentes=[0.7, 0.9], P=0.85, N4=650k."""
    resultado = BridgeAnalyzer.calcular(
        nivel_1=500_000.0,
        necessidades_fracionadas=[0.7, 0.9],
        praticabilidade=0.85,
        nivel_4=650_000.0,
    )
    # N4 deve ser preservado
    assert resultado.nivel_4_operacional == pytest.approx(650_000.0, abs=1.0)
    # N3 > N2 > N1 (com frentes fracionadas e P < 1)
    assert resultado.nivel_3_catalogo_normalizado > resultado.nivel_2_catalogo_escalado
    assert resultado.nivel_2_catalogo_escalado > resultado.nivel_1_catalogo_base
    # status deve ser definido
    assert resultado.status_alerta in {"VERDE", "AMARELO", "VERMELHO", "SEM_DADOS"}
