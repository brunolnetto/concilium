"""ADR-124 / NEP-036: Campo de Eficiência — Fase de Planejamento.

ADR-124 reformula a decomposição para separar planejamento de controle:

  Planejamento: η_plan = η_clima · δ  (sempre disponíveis)
  Controle:     η_total = η_s · η_plan · η_w  (S/W/E=None até haver execução real)

  Nível 1 (Global):   η_obra(t) = Σ_i Q[i,t] / Σ_i Q_max[i,t]
  Nível 2 (Causal):   decomposição η_clima / δ ponderada por capacidade
  Nível 3 (Pareto):   perdas físicas ordenadas por atividade
  Nível 4 (Fatorial): Eta_clima[i,j] e Delta[i,j] por atividade+semana

Propriedade log-linear:
  log(Eta_plan_ij) = log(Eta_clima_j) + log(Delta_j)

Estrutura sparse: {item_id: {semana_iso: valor}} — não aloca a matriz densa.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


def _weighted_sum(weights: list[float], values: list[float]) -> float:
    """Σ weights[i] * values[i] — colapsa a soma ponderada em uma única chamada."""
    return sum(a * v for a, v in zip(weights, values, strict=True))


@dataclass
class CampoEficiencia:
    """Campo de eficiência materializado do canônico — fase de planejamento.

    Superfícies de planejamento (sempre disponíveis):
      Eta_clima  — η_clima_j = fator_chuva (praticabilidade climática, estocástica)
      Delta      — δ_j = fator_calendario  (coeficiente calendário, controlável)
      Eta_plan   — η_plan = η_clima · δ    (eficiência agregada do planejamento)

    Superfícies de controle (None no planejamento):
      S  — η_s = n_j / n_max  (alocação; requer execução real)
      W  — η_w residual de gestão (requer produção real vs. planejada)
      E  — η_total = η_s · η_plan · η_w

    Todos os campos são dicts esparsos: {item_id: {semana_iso: float}}.
    """

    # ── Planejamento ────────────────────────────────────────────────────────────
    Eta_clima: dict[str, dict[str, float]] = field(default_factory=dict)
    Delta: dict[str, dict[str, float]] = field(default_factory=dict)
    Eta_plan: dict[str, dict[str, float]] = field(default_factory=dict)
    Q: dict[str, dict[str, float]] = field(default_factory=dict)
    Q_max: dict[str, dict[str, float]] = field(default_factory=dict)

    # ── Controle — None no planejamento ─────────────────────────────────────────
    S: dict[str, dict[str, float]] | None = None  # CONTROLE: η_s = n_j/n_max
    W: dict[str, dict[str, float]] | None = None  # CONTROLE: gestão residual
    E: dict[str, dict[str, float]] | None = None  # CONTROLE: η_total

    # ── Metadados ──────────────────────────────────────────────────────────────
    atividades: list[str] = field(default_factory=list)
    semanas: list[str] = field(default_factory=list)

    # ── Nível 1: série temporal global ────────────────────────────────────────

    def eta_obra(self) -> dict[str, float]:
        """η_obra(t) = Σ_i Q[i,t] / Σ_i Q_max[i,t] — série semanal.

        Em planejamento: Q/Q_max = η_plan por construção.
        Em controle: Q = produção realizada.
        """
        soma_q: dict[str, float] = {}
        soma_qmax: dict[str, float] = {}
        for item_id in self.atividades:
            for sem, q in (self.Q.get(item_id) or {}).items():
                soma_q[sem] = soma_q.get(sem, 0.0) + q
            for sem, qm in (self.Q_max.get(item_id) or {}).items():
                soma_qmax[sem] = soma_qmax.get(sem, 0.0) + qm
        return {sem: soma_q.get(sem, 0.0) / qmax for sem, qmax in soma_qmax.items() if qmax > 0}

    # ── Nível 2: decomposição causal global ───────────────────────────────────

    def _dc_collect_for_item(self, item_id: str) -> tuple[list[float], list[float], list[float], list[float]]:
        """Coleta (q_max, eta_clima, delta, eta_plan) das células válidas (qm > 0) de um item."""
        q_max_list: list[float] = []
        clima_list: list[float] = []
        delta_list: list[float] = []
        plan_list: list[float] = []
        for sem in self.Eta_plan.get(item_id) or {}:
            qm = (self.Q_max.get(item_id) or {}).get(sem, 0.0)
            if qm <= 0:
                continue
            q_max_list.append(qm)
            clima_list.append((self.Eta_clima.get(item_id) or {}).get(sem, 1.0))
            delta_list.append((self.Delta.get(item_id) or {}).get(sem, 1.0))
            plan_list.append((self.Eta_plan.get(item_id) or {}).get(sem, 1.0))
        return q_max_list, clima_list, delta_list, plan_list

    def decomposicao_causal(self) -> dict[str, float]:
        """Contribuição ponderada de η_clima e δ para η_plan global.

        Ponderação por q_max_celula (capacidade), não por número de equipes.
        """
        q_max_list: list[float] = []
        clima_list: list[float] = []
        delta_list: list[float] = []
        plan_list: list[float] = []

        for item_id in self.atividades:
            qm_item, clima_item, delta_item, plan_item = self._dc_collect_for_item(item_id)
            q_max_list += qm_item
            clima_list += clima_item
            delta_list += delta_item
            plan_list += plan_item

        if not q_max_list:
            return {"eta_clima_global": 1.0, "delta_global": 1.0, "eta_plan_global": 1.0}

        Q_total = sum(q_max_list)
        alpha = [qm / Q_total for qm in q_max_list]
        eta_clima_g = _weighted_sum(alpha, clima_list)
        delta_g = _weighted_sum(alpha, delta_list)
        eta_plan_g = _weighted_sum(alpha, plan_list)
        return {
            "eta_clima_global": round(eta_clima_g, 4),
            "delta_global": round(delta_g, 4),
            "eta_plan_global": round(eta_plan_g, 4),
        }

    # ── Nível 2b: perdas físicas ──────────────────────────────────────────────

    def perda_fisica(self) -> dict[str, dict[str, float]]:
        """L[i,t] = Q_max[i,t] - Q[i,t] em unidades físicas (m³, t, km)."""
        result: dict[str, dict[str, float]] = {}
        for item_id in self.atividades:
            q_dict = self.Q.get(item_id) or {}
            qm_dict = self.Q_max.get(item_id) or {}
            perdas = {sem: max(0.0, qm_dict.get(sem, 0.0) - q_dict.get(sem, 0.0)) for sem in qm_dict}
            if any(v > 0 for v in perdas.values()):
                result[item_id] = perdas
        return result

    # ── Nível 3: Pareto de atividades ─────────────────────────────────────────

    def pareto_perdas(self, top_n: int = 10) -> list[dict[str, Any]]:
        """Top-N atividades por perda física total Σ_t L[i,t] (decrescente)."""
        pf = self.perda_fisica()
        perdas_totais = []
        for item_id in self.atividades:
            total_perda = sum((pf.get(item_id) or {}).values())
            total_qmax = sum((self.Q_max.get(item_id) or {}).values())
            total_q = sum((self.Q.get(item_id) or {}).values())
            eta_medio = total_q / total_qmax if total_qmax > 0 else 1.0
            perdas_totais.append(
                {
                    "item_id": item_id,
                    "perda_fisica_total": round(total_perda, 2),
                    "q_executada_total": round(total_q, 2),
                    "q_max_total": round(total_qmax, 2),
                    "eta_medio": round(eta_medio, 4),
                    "pct_perda": round(total_perda / total_qmax * 100, 1) if total_qmax > 0 else 0.0,
                }
            )
        perdas_totais.sort(key=lambda x: x["perda_fisica_total"], reverse=True)
        return perdas_totais[:top_n]

    # ── Log-linear: base para ANOVA e regressão ────────────────────────────────

    def log_linear(self) -> dict[str, dict[str, dict[str, float]]]:
        """log(Eta_plan), log(Eta_clima), log(Delta) para decomposição aditiva.

        Propriedade: log(Eta_plan_ij) = log(Eta_clima_j) + log(Delta_j)
        Células com valor 0 são NaN (log(0) indefinido).
        """

        def _log_field(f: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
            return {
                iid: {sem: math.log(v) if v > 0 else float("nan") for sem, v in sem_dict.items()}
                for iid, sem_dict in f.items()
            }

        return {
            "log_Eta_plan": _log_field(self.Eta_plan),
            "log_Eta_clima": _log_field(self.Eta_clima),
            "log_Delta": _log_field(self.Delta),
        }


class EficienciaFieldBuilder:
    """Constrói CampoEficiencia (fase de planejamento) a partir do canônico.

    Lê fator_clima e fator_calendario de cada DistribuicaoSemanal (ADR-068).
    S, W, E permanecem None — fase de controle não implementada.
    """

    def build(self, canonical: Any) -> CampoEficiencia:
        """Materializa o campo a partir de canonical.cronograma."""
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
            campo.Eta_clima[item_id] = {}
            campo.Delta[item_id] = {}
            campo.Eta_plan[item_id] = {}
            campo.Q[item_id] = {}
            campo.Q_max[item_id] = {}

            for sem, cell in dist.items():
                semanas_set.add(sem)
                eta_clima = float(getattr(cell, "fator_clima", 1.0))
                delta = float(getattr(cell, "fator_calendario", 1.0))
                eta_plan = round(eta_clima * delta, 6)
                q = float(getattr(cell, "qtd_executada", 0.0))
                q_max = float(getattr(cell, "q_max_celula", 0.0))
                campo.Eta_clima[item_id][sem] = round(eta_clima, 6)
                campo.Delta[item_id][sem] = round(delta, 6)
                campo.Eta_plan[item_id][sem] = eta_plan
                campo.Q[item_id][sem] = round(q, 4)
                campo.Q_max[item_id][sem] = round(q_max, 4)

        campo.semanas = sorted(semanas_set)
        return campo
