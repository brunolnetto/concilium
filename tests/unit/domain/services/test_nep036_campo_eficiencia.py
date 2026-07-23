"""ADR-124 / NEP-036: CampoEficiencia — planejamento η_plan = η_clima · δ."""

from __future__ import annotations

import math
from types import SimpleNamespace

from concilium.domain.services.analytics.eficiencia_field_builder import CampoEficiencia, EficienciaFieldBuilder


def _cell(fator_clima: float, fator_calendario: float, q: float, q_max: float) -> SimpleNamespace:
    return SimpleNamespace(
        fator_clima=fator_clima,
        fator_calendario=fator_calendario,
        qtd_executada=q,
        q_max_celula=q_max,
    )


def _campo_simples() -> CampoEficiencia:
    """Três atividades, duas semanas — valores controlados (planejamento)."""
    campo = CampoEficiencia()
    campo.atividades = ["eap-A", "eap-B", "eap-C"]
    campo.semanas = ["2026-W01", "2026-W02"]
    # (eta_clima, delta) → eta_plan = eta_clima * delta
    for item, eta_clima, delta, q, q_max in [
        ("eap-A", 1.0, 1.0, 100.0, 100.0),  # eta_plan = 1.00
        ("eap-B", 0.8, 0.5, 40.0, 100.0),  # eta_plan = 0.40
        ("eap-C", 0.5, 0.5, 25.0, 100.0),  # eta_plan = 0.25
    ]:
        eta_plan = eta_clima * delta
        campo.Eta_clima[item] = {"2026-W01": eta_clima, "2026-W02": eta_clima}
        campo.Delta[item] = {"2026-W01": delta, "2026-W02": delta}
        campo.Eta_plan[item] = {"2026-W01": eta_plan, "2026-W02": eta_plan}
        campo.Q[item] = {"2026-W01": q, "2026-W02": q}
        campo.Q_max[item] = {"2026-W01": q_max, "2026-W02": q_max}
    # S, W, E permanecem None (fase de controle)
    return campo


class TestCampoEficiencia:
    def test_eta_obra_razao_das_somas(self):
        campo = _campo_simples()
        obra = campo.eta_obra()
        # Σ Q = 100+40+25 = 165; Σ Q_max = 300
        assert abs(obra["2026-W01"] - 165.0 / 300.0) < 1e-6

    def test_eta_obra_nao_e_media_das_eficiencias(self):
        campo = _campo_simples()
        obra = campo.eta_obra()["2026-W01"]
        eta_correto = 165.0 / 300.0
        assert abs(obra - eta_correto) < 1e-6

    def test_perda_fisica_q_max_minus_q(self):
        campo = _campo_simples()
        perdas = campo.perda_fisica()
        assert "eap-A" not in perdas  # sem perda
        assert abs(perdas["eap-B"]["2026-W01"] - 60.0) < 1e-6
        assert abs(perdas["eap-C"]["2026-W01"] - 75.0) < 1e-6

    def test_pareto_ordenado_por_perda_total(self):
        campo = _campo_simples()
        pareto = campo.pareto_perdas(top_n=5)
        assert pareto[0]["item_id"] == "eap-C"  # maior perda (75 × 2 = 150)
        assert pareto[1]["item_id"] == "eap-B"  # segunda maior (60 × 2 = 120)

    def test_decomposicao_causal_ponderada(self):
        campo = _campo_simples()
        dec = campo.decomposicao_causal()
        # Todas q_max iguais (100) → pesos iguais → média aritmética
        # eta_clima_global = (1.0 + 0.8 + 0.5) / 3
        assert abs(dec["eta_clima_global"] - (1.0 + 0.8 + 0.5) / 3) < 0.01
        # delta_global = (1.0 + 0.5 + 0.5) / 3
        assert abs(dec["delta_global"] - (1.0 + 0.5 + 0.5) / 3) < 0.01

    def test_controle_fields_none_no_planejamento(self):
        campo = _campo_simples()
        assert campo.S is None
        assert campo.W is None
        assert campo.E is None

    def test_log_linear_roundtrip(self):
        campo = _campo_simples()
        ll = campo.log_linear()
        for item_id in campo.atividades:
            for sem in campo.semanas:
                ep = campo.Eta_plan[item_id][sem]
                le = ll["log_Eta_plan"].get(item_id, {}).get(sem, float("nan"))
                if not math.isnan(le):
                    assert abs(math.exp(le) - ep) < 1e-9, f"roundtrip falhou para {item_id}@{sem}"

    def test_log_linear_aditividade(self):
        # log(Eta_plan) = log(Eta_clima) + log(Delta) célula a célula
        campo = _campo_simples()
        ll = campo.log_linear()
        for item_id in campo.atividades:
            for sem in campo.semanas:
                lp = ll["log_Eta_plan"].get(item_id, {}).get(sem, float("nan"))
                lc = ll["log_Eta_clima"].get(item_id, {}).get(sem, float("nan"))
                ld = ll["log_Delta"].get(item_id, {}).get(sem, float("nan"))
                if not any(math.isnan(v) for v in [lp, lc, ld]):
                    assert abs(lp - (lc + ld)) < 1e-9, f"aditividade falhou para {item_id}@{sem}"


class TestEficienciaFieldBuilder:
    def _canonical(self):
        """Canonical stub com 1 atividade, 2 semanas."""
        cell1 = _cell(fator_clima=0.8, fator_calendario=1.0, q=80.0, q_max=100.0)
        cell2 = _cell(fator_clima=1.0, fator_calendario=0.9, q=90.0, q_max=100.0)
        sa = SimpleNamespace(
            activity_id="act-1",
            distribuicao_semanal={"2026-W01": cell1, "2026-W02": cell2},
        )
        return SimpleNamespace(cronograma=SimpleNamespace(scheduled_activities=[sa]))

    def test_build_popula_campos_de_planejamento(self):
        campo = EficienciaFieldBuilder().build(self._canonical())
        assert "act-1" in campo.atividades
        assert abs(campo.Eta_clima["act-1"]["2026-W01"] - 0.8) < 1e-6
        assert abs(campo.Delta["act-1"]["2026-W01"] - 1.0) < 1e-6
        assert abs(campo.Eta_plan["act-1"]["2026-W01"] - 0.8) < 1e-6  # 0.8 × 1.0
        assert abs(campo.Eta_plan["act-1"]["2026-W02"] - 0.9) < 1e-6  # 1.0 × 0.9
        assert abs(campo.Q["act-1"]["2026-W01"] - 80.0) < 1e-6

    def test_controle_fields_none_apos_build(self):
        campo = EficienciaFieldBuilder().build(self._canonical())
        assert campo.S is None
        assert campo.W is None
        assert campo.E is None

    def test_semanas_ordenadas(self):
        campo = EficienciaFieldBuilder().build(self._canonical())
        assert campo.semanas == sorted(campo.semanas)

    def test_sem_cronograma_retorna_vazio(self):
        campo = EficienciaFieldBuilder().build(SimpleNamespace(cronograma=None))
        assert campo.atividades == []
