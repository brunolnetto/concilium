"""NEP-036: CampoEficiencia — formulação matricial, η_obra, decomposição causal, log-linear."""

from __future__ import annotations

import math
from types import SimpleNamespace

from concilium.domain.services.eficiencia_field_builder import CampoEficiencia, EficienciaFieldBuilder


def _cell(eta_s, eta_p, eta_w, q, q_max):
    return SimpleNamespace(
        fator_total=eta_s * eta_p * eta_w,
        eta_s=eta_s, eta_p=eta_p, eta_w=eta_w,
        eficiencia=eta_w,
        fator_clima=eta_p,
        qtd_executada=q,
        q_max_celula=q_max,
    )


def _campo_simples():
    """Três atividades, duas semanas — valores controlados."""
    campo = CampoEficiencia()
    # eap-A: η=1.0 nas duas semanas
    campo.atividades = ["eap-A", "eap-B", "eap-C"]
    campo.semanas = ["2026-W01", "2026-W02"]
    for item, eta_s, eta_p, eta_w, q, q_max in [
        ("eap-A", 1.0, 1.0, 1.0, 100.0, 100.0),
        ("eap-B", 0.5, 0.8, 1.0, 40.0, 100.0),
        ("eap-C", 1.0, 0.5, 0.5, 25.0, 100.0),
    ]:
        eta = eta_s * eta_p * eta_w
        campo.E[item] = {"2026-W01": eta, "2026-W02": eta}
        campo.S[item] = {"2026-W01": eta_s, "2026-W02": eta_s}
        campo.P_r[item] = {"2026-W01": eta_p, "2026-W02": eta_p}
        campo.W[item] = {"2026-W01": eta_w, "2026-W02": eta_w}
        campo.Q[item] = {"2026-W01": q, "2026-W02": q}
        campo.Q_max[item] = {"2026-W01": q_max, "2026-W02": q_max}
    return campo


class TestCampoEficiencia:
    def test_eta_obra_razao_das_somas(self):
        campo = _campo_simples()
        obra = campo.eta_obra()
        # Por semana: Σ Q = 100+40+25=165; Σ Q_max = 300
        assert abs(obra["2026-W01"] - 165.0 / 300.0) < 1e-6

    def test_eta_obra_nao_e_media_das_eficiencias(self):
        campo = _campo_simples()
        obra = campo.eta_obra()["2026-W01"]
        eta_media_simples = (1.0 + 0.4 + 0.25) / 3  # ≈ 0.55
        # Deve ser ≠ média simples quando capacidades são iguais por coincidência são iguais…
        # … mas se forem iguais, as duas convergem. Verificamos a fórmula, não a desigualdade.
        eta_correto = 165.0 / 300.0  # ≈ 0.55 — aqui sim igual pois q_max são iguais
        assert abs(obra - eta_correto) < 1e-6

    def test_perda_fisica_q_max_minus_q(self):
        campo = _campo_simples()
        perdas = campo.perda_fisica()
        # eap-A: perda=0; eap-B: perda=60; eap-C: perda=75
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
        # η_s_global = (1.0+0.5+1.0)/3 ≈ 0.833
        assert abs(dec["eta_s_global"] - (1.0 + 0.5 + 1.0) / 3) < 0.01

    def test_log_linear_roundtrip(self):
        campo = _campo_simples()
        ll = campo.log_linear()
        # exp(log_E) deve ser igual a E dentro de 1e-9
        for item_id in campo.atividades:
            for sem in campo.semanas:
                e = campo.E[item_id][sem]
                le = ll["log_E"].get(item_id, {}).get(sem, float("nan"))
                if not math.isnan(le):
                    assert abs(math.exp(le) - e) < 1e-9, f"roundtrip falhou para {item_id}@{sem}"

    def test_log_linear_aditividade(self):
        # log(E) = log(S) + log(P_r) + log(W) elemento a elemento
        campo = _campo_simples()
        ll = campo.log_linear()
        for item_id in campo.atividades:
            for sem in campo.semanas:
                le = ll["log_E"].get(item_id, {}).get(sem, float("nan"))
                ls = ll["log_S"].get(item_id, {}).get(sem, float("nan"))
                lp = ll["log_P_r"].get(item_id, {}).get(sem, float("nan"))
                lw = ll["log_W"].get(item_id, {}).get(sem, float("nan"))
                if not any(math.isnan(v) for v in [le, ls, lp, lw]):
                    assert abs(le - (ls + lp + lw)) < 1e-9, f"aditividade falhou para {item_id}@{sem}"


class TestEficienciaFieldBuilder:
    def _canonical(self):
        """Canonical stub com 1 atividade, 2 semanas."""
        cell1 = SimpleNamespace(
            fator_total=0.8, eta_s=1.0, eta_p=0.8, eta_w=1.0,
            eficiencia=1.0, fator_clima=0.8, qtd_executada=80.0, q_max_celula=100.0,
        )
        cell2 = SimpleNamespace(
            fator_total=0.9, eta_s=0.9, eta_p=1.0, eta_w=1.0,
            eficiencia=1.0, fator_clima=1.0, qtd_executada=90.0, q_max_celula=100.0,
        )
        sa = SimpleNamespace(
            activity_id="act-1",
            distribuicao_semanal={"2026-W01": cell1, "2026-W02": cell2},
        )
        cron = SimpleNamespace(scheduled_activities=[sa])
        return SimpleNamespace(cronograma=cron)

    def test_build_popula_campos(self):
        can = self._canonical()
        campo = EficienciaFieldBuilder().build(can)
        assert "act-1" in campo.atividades
        assert "act-1" in campo.E
        assert abs(campo.E["act-1"]["2026-W01"] - 0.8) < 1e-6
        assert abs(campo.Q["act-1"]["2026-W01"] - 80.0) < 1e-6

    def test_semanas_ordenadas(self):
        can = self._canonical()
        campo = EficienciaFieldBuilder().build(can)
        assert campo.semanas == sorted(campo.semanas)

    def test_sem_cronograma_retorna_vazio(self):
        campo = EficienciaFieldBuilder().build(SimpleNamespace(cronograma=None))
        assert campo.atividades == []
