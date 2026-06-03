"""NEP-036: Campo de Eficiência E ∈ ℝ^{I×T} — Formulação Matricial.

O campo de eficiência materializa a estrutura atividade × semana do modelo
de produção, permitindo análise em múltiplos níveis (NEP-035, Seção 9–11):

  Nível 1 (Global):   η_obra(t) = Σ_i Q[i,t] / Σ_i Q_max[i,t]
  Nível 2 (Causal):   decomposição η_s / η_p / η_w + termo cruzado eps_cross
  Nível 3 (Pareto):   perdas físicas ordenadas por atividade
  Nível 4 (Fatorial): E[i,j], S[i,j], P_r[i,j], W[i,j] por atividade+semana

Propriedade log-linear (Seção 22):
  log(E) = log(S) + log(P_r) + log(W)  (aditivo: base para ANOVA e regressão)

Estrutura sparse: {item_id: {semana_iso: valor}} — não aloca a matriz densa
quando atividades têm janelas disjuntas (typical para obras grandes).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CampoEficiencia:
    """Campo de eficiência E ∈ ℝ^{I×T} materializado do canônico.

    Todos os campos são dicts esparsos: {item_id: {semana_iso: float}}.
    Semanas fora da janela de uma atividade simplesmente não têm entrada.
    """

    E: dict[str, dict[str, float]] = field(default_factory=dict)     # η total = η_s·η_p·η_w
    S: dict[str, dict[str, float]] = field(default_factory=dict)     # η_s (alocação)
    P_r: dict[str, dict[str, float]] = field(default_factory=dict)   # η_p (praticabilidade)
    W: dict[str, dict[str, float]] = field(default_factory=dict)     # η_w (gestão)
    Q: dict[str, dict[str, float]] = field(default_factory=dict)     # produção realizada q_ij
    Q_max: dict[str, dict[str, float]] = field(default_factory=dict) # capacidade máxima q_max_ij

    # metadados
    atividades: list[str] = field(default_factory=list)   # I atividades
    semanas: list[str] = field(default_factory=list)      # T semanas da obra (ordenadas)

    # ── Nível 1: série temporal global ────────────────────────────────────────

    def eta_obra(self) -> dict[str, float]:
        """η_obra(t) = Σ_i Q[i,t] / Σ_i Q_max[i,t] para cada semana t.

        Métrica executiva global (Nível 1 da hierarquia). Não confundir com a
        média simples de eficiências: é a razão das somas, ponderada pela
        capacidade de cada atividade.
        """
        soma_q: dict[str, float] = {}
        soma_qmax: dict[str, float] = {}
        for item_id in self.atividades:
            for sem, q in (self.Q.get(item_id) or {}).items():
                soma_q[sem] = soma_q.get(sem, 0.0) + q
            for sem, qm in (self.Q_max.get(item_id) or {}).items():
                soma_qmax[sem] = soma_qmax.get(sem, 0.0) + qm
        return {
            sem: soma_q.get(sem, 0.0) / soma_qmax[sem]
            for sem, qmax in soma_qmax.items()
            if qmax > 0
        }

    # ── Nível 2: decomposição causal global ───────────────────────────────────

    def decomposicao_causal(self) -> dict[str, float]:
        """Contribuição ponderada de cada fator para η_global.

        Retorna η_s_global, η_p_global, η_w_global e eps_cross (termo de
        acoplamento). |eps_cross| > 0.05 indica que os fatores não são
        separáveis no agregado — a decomposição é diagnóstica por semana,
        não por média global (Seção 5 do modelo).
        """
        q_max_list: list[float] = []
        eta_s_list: list[float] = []
        eta_p_list: list[float] = []
        eta_w_list: list[float] = []
        eta_list: list[float] = []
        for item_id in self.atividades:
            for sem in (self.E.get(item_id) or {}):
                qm = (self.Q_max.get(item_id) or {}).get(sem, 0.0)
                if qm <= 0:
                    continue
                q_max_list.append(qm)
                eta_s_list.append((self.S.get(item_id) or {}).get(sem, 1.0))
                eta_p_list.append((self.P_r.get(item_id) or {}).get(sem, 1.0))
                eta_w_list.append((self.W.get(item_id) or {}).get(sem, 1.0))
                eta_list.append((self.E.get(item_id) or {}).get(sem, 1.0))

        if not q_max_list:
            return {"eta_s_global": 1.0, "eta_p_global": 1.0, "eta_w_global": 1.0,
                    "eta_global": 1.0, "eps_cross": 0.0}

        Q_total = sum(q_max_list)
        alpha = [qm / Q_total for qm in q_max_list]
        eta_s_g = sum(a * e for a, e in zip(alpha, eta_s_list, strict=True))
        eta_p_g = sum(a * e for a, e in zip(alpha, eta_p_list, strict=True))
        eta_w_g = sum(a * e for a, e in zip(alpha, eta_w_list, strict=True))
        eta_g = sum(a * e for a, e in zip(alpha, eta_list, strict=True))
        eps_cross = eta_g - eta_s_g * eta_p_g * eta_w_g
        return {
            "eta_s_global": round(eta_s_g, 4),
            "eta_p_global": round(eta_p_g, 4),
            "eta_w_global": round(eta_w_g, 4),
            "eta_global": round(eta_g, 4),
            "eps_cross": round(eps_cross, 4),
            "acoplamento_material": abs(eps_cross) > 0.05,
        }

    # ── Nível 2b: perdas físicas e custo ─────────────────────────────────────

    def perda_fisica(self) -> dict[str, dict[str, float]]:
        """L[i,t] = Q_max[i,t] - Q[i,t] em unidades físicas (m³, t, km)."""
        result: dict[str, dict[str, float]] = {}
        for item_id in self.atividades:
            q_dict = self.Q.get(item_id) or {}
            qm_dict = self.Q_max.get(item_id) or {}
            perdas = {
                sem: max(0.0, qm_dict.get(sem, 0.0) - q_dict.get(sem, 0.0))
                for sem in qm_dict
            }
            if any(v > 0 for v in perdas.values()):
                result[item_id] = perdas
        return result

    # ── Nível 3: Pareto de atividades ─────────────────────────────────────────

    def pareto_perdas(self, top_n: int = 10) -> list[dict[str, Any]]:
        """Top-N atividades por perda física total Σ_t L[i,t] (decrescente).

        Permite drill-down: "eap-1_7 perdeu 3.500 m³ na janela de execução".
        O top_n evita o heatmap de 16.000 células (Seção 9 do modelo).
        """
        perdas_totais = []
        pf = self.perda_fisica()
        for item_id in self.atividades:
            total_perda = sum((pf.get(item_id) or {}).values())
            total_qmax = sum((self.Q_max.get(item_id) or {}).values())
            total_q = sum((self.Q.get(item_id) or {}).values())
            eta_medio = total_q / total_qmax if total_qmax > 0 else 1.0
            perdas_totais.append({
                "item_id": item_id,
                "perda_fisica_total": round(total_perda, 2),
                "q_executada_total": round(total_q, 2),
                "q_max_total": round(total_qmax, 2),
                "eta_medio": round(eta_medio, 4),
                "pct_perda": round(total_perda / total_qmax * 100, 1) if total_qmax > 0 else 0.0,
            })
        perdas_totais.sort(key=lambda x: x["perda_fisica_total"], reverse=True)
        return perdas_totais[:top_n]

    # ── Log-linear: base para ANOVA e regressão ────────────────────────────────

    def log_linear(self) -> dict[str, dict[str, dict[str, float]]]:
        """log(E), log(S), log(P_r), log(W) para decomposição aditiva.

        Propriedade: log(E_ij) = log(S_ij) + log(P_r_ij) + log(W_ij)
        Células com valor 0 são representadas como NaN (log(0) indefinido).
        """

        def _log_field(f: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
            return {
                iid: {
                    sem: math.log(v) if v > 0 else float("nan")
                    for sem, v in sem_dict.items()
                }
                for iid, sem_dict in f.items()
            }

        return {
            "log_E": _log_field(self.E),
            "log_S": _log_field(self.S),
            "log_P_r": _log_field(self.P_r),
            "log_W": _log_field(self.W),
        }


class EficienciaFieldBuilder:
    """Constrói CampoEficiencia a partir do canônico do projeto.

    Requer que as células de DistribuicaoSemanal tenham sido populadas pela
    NEP-035 (campos eta_s, eta_p, eta_w, q_max_celula). Se ausentes, usa
    fator_total como η e N_equipes × producao_base como q_max (compatibilidade).
    """

    def build(self, canonical: Any) -> CampoEficiencia:
        """Materializa o campo E a partir de canonical.cronograma."""
        cronograma = getattr(canonical, "cronograma", None)
        if cronograma is None:
            return CampoEficiencia()

        scheduled = getattr(cronograma, "scheduled_activities", None) or []
        campo = CampoEficiencia()
        semanas_set: set[str] = set()

        for sa in scheduled:
            item_id = getattr(sa, "activity_id", None) or getattr(sa, "item_id", None)
            if not item_id:
                continue
            dist = getattr(sa, "distribuicao_semanal", None)
            if not dist or not isinstance(dist, dict):
                continue

            campo.atividades.append(item_id)
            campo.E[item_id] = {}
            campo.S[item_id] = {}
            campo.P_r[item_id] = {}
            campo.W[item_id] = {}
            campo.Q[item_id] = {}
            campo.Q_max[item_id] = {}

            for sem, cell in dist.items():
                semanas_set.add(sem)
                eta = float(getattr(cell, "fator_total", getattr(cell, "eficiencia", 1.0)))
                eta_s = float(getattr(cell, "eta_s", 1.0))
                eta_p = float(getattr(cell, "eta_p", float(getattr(cell, "fator_clima", 1.0))))
                eta_w = float(getattr(cell, "eta_w", float(getattr(cell, "eficiencia", 1.0))))
                q = float(getattr(cell, "qtd_executada", 0.0))
                q_max = float(getattr(cell, "q_max_celula", 0.0))
                campo.E[item_id][sem] = round(eta, 6)
                campo.S[item_id][sem] = round(eta_s, 6)
                campo.P_r[item_id][sem] = round(eta_p, 6)
                campo.W[item_id][sem] = round(eta_w, 6)
                campo.Q[item_id][sem] = round(q, 4)
                campo.Q_max[item_id][sem] = round(q_max, 4)

        # Semanas ordenadas cronologicamente
        campo.semanas = sorted(semanas_set)
        return campo
