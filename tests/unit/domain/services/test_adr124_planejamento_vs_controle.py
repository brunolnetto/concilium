"""ADR-124 — Separação Planejamento vs. Controle.

Testes de contrato/regressão que travam as decisões D1..D5 do ADR-124:

- D1/D3: η_plan = η_clima · δ; eta_obra() = Σ Q / Σ Q_max agregado.
- D5:     η_s e η_w (superfícies S e W) são None no modo planejamento.
- Regressão: η_plan reproduz numericamente o antigo P_r / η_p combinado
  (η_clima · δ) — só o nome/estrutura mudou, não o valor.
"""

from __future__ import annotations

from types import SimpleNamespace

from concilium.domain.services.analytics.eficiencia_field_builder import (
    CampoEficiencia,
    EficienciaFieldBuilder,
)


def _cell(fator_clima: float, fator_calendario: float, q: float, q_max: float) -> SimpleNamespace:
    return SimpleNamespace(
        fator_clima=fator_clima,
        fator_calendario=fator_calendario,
        qtd_executada=q,
        q_max_celula=q_max,
    )


def _canonical() -> SimpleNamespace:
    cells = {
        "2026-W01": _cell(0.80, 1.00, 80.0, 100.0),  # η_plan = 0.80
        "2026-W02": _cell(1.00, 0.90, 90.0, 100.0),  # η_plan = 0.90
        "2026-W03": _cell(0.75, 0.85, 60.0, 100.0),  # η_plan = 0.6375
    }
    sa = SimpleNamespace(activity_id="act-1", distribuicao_semanal=cells)
    return SimpleNamespace(cronograma=SimpleNamespace(scheduled_activities=[sa]))


class TestModeloPlanejamento:
    """D1/D3 — modelo de planejamento η_plan = η_clima · δ."""

    def test_eta_plan_e_produto_clima_delta(self):
        campo = EficienciaFieldBuilder().build(_canonical())
        for sem, clima, delta in [("2026-W01", 0.80, 1.00), ("2026-W02", 1.00, 0.90), ("2026-W03", 0.75, 0.85)]:
            assert abs(campo.Eta_clima["act-1"][sem] - clima) < 1e-9
            assert abs(campo.Delta["act-1"][sem] - delta) < 1e-9
            assert abs(campo.Eta_plan["act-1"][sem] - clima * delta) < 1e-6

    def test_eta_obra_agregado_por_capacidade(self):
        campo = EficienciaFieldBuilder().build(_canonical())
        obra = campo.eta_obra()
        # Só uma atividade → Σ Q / Σ Q_max = q / q_max por semana.
        assert abs(obra["2026-W01"] - 80.0 / 100.0) < 1e-9
        assert abs(obra["2026-W02"] - 90.0 / 100.0) < 1e-9


class TestControleNoneNoPlanejamento:
    """D5 — η_s e η_w (S/W) e η_total (E) são None enquanto não há execução real."""

    def test_builder_deixa_S_W_E_none(self):
        campo = EficienciaFieldBuilder().build(_canonical())
        # S = η_s (alocação n_j/n_max) — CONTROLE, não populado no planejamento.
        assert campo.S is None
        # W = η_w (gestão residual) — CONTROLE, não populado no planejamento.
        assert campo.W is None
        # E = η_total = η_s · η_plan · η_w — só existe em controle.
        assert campo.E is None

    def test_campo_default_tem_controle_none(self):
        campo = CampoEficiencia()
        assert campo.S is None and campo.W is None and campo.E is None
        # Superfícies de planejamento sempre existem (dict vazio, nunca None).
        assert campo.Eta_clima == {} and campo.Delta == {} and campo.Eta_plan == {}


class TestRegressaoPrEtaPlan:
    """Regressão D1/D2 — η_plan reproduz o antigo P_r / η_p combinado (η_clima · δ).

    Antes do ADR-124, a praticabilidade era exposta como `P_r = η_p = fator_clima ·
    fator_calendario`. O renomeio para `Eta_plan` NÃO altera o valor numérico:
    η_plan == η_p_legado == P_r_legado. Este teste trava essa equivalência.
    """

    def test_eta_plan_igual_ao_p_r_legado(self):
        canonical = _canonical()
        campo = EficienciaFieldBuilder().build(canonical)
        cells = canonical.cronograma.scheduled_activities[0].distribuicao_semanal
        for sem, cell in cells.items():
            # Fórmula legada de η_p / P_r == η_plan atual.
            p_r_legado = cell.fator_clima * cell.fator_calendario
            assert abs(campo.Eta_plan["act-1"][sem] - p_r_legado) < 1e-6
