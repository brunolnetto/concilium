"""Testes issue #139 — custo_unit_semanal do pool subestimado em itens multi-frente.

`_add_tipo_item_demand`/`_compute_custo_unit_fracs` dividiam `eq.custo_total` (sempre "1
frente" por convenção ADR-091/ADR-162 D4) por `machine_weeks` (agregado — soma `num_equipes`
real por semana, todas as frentes). Verificado numericamente antes do fix: item sozinho no
pool com num_equipes=3 constante devolvia o valor de 1 frente inalterado (1/3 do custo real).

Corrigido via `_eq_custo_total_agregado` (usa `EquipeDireta.custo_operacional_agregado`,
ADR-172 — integral semana a semana, já na mesma base agregada de `machine_weeks`).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MANIFESTS = Path(__file__).resolve().parents[4] / "src" / "concilium" / "application" / "skills" / "manifests"


def _load_skill05():
    p = _MANIFESTS / "05-equipes-e-alocacao" / "_skill_helpers" / "__init__.py"
    spec = importlib.util.spec_from_file_location("_issue139_skill05_helpers", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_issue139_skill05_helpers"] = mod
    spec.loader.exec_module(mod)
    return mod


MOD = _load_skill05()


def _mk_sched(item_id: str, weeks: list[str], num_equipes: int):
    from concilium.domain.models.canonical import DistribuicaoSemanal, ScheduledActivityCanonical

    dist = {
        w: DistribuicaoSemanal(
            num_equipes=num_equipes,
            qtd_executada=10.0,
            qtd_acumulada=10.0,
            pct=1.0,
            eficiencia=1.0,
            fator_clima=1.0,
            fator_calendario=1.0,
        )
        for w in weeks
    }
    return ScheduledActivityCanonical(
        activity_id=item_id,
        start_week=0,
        end_week=len(weeks),
        duration_weeks=len(weeks),
        distribuicao_semanal=dist,
    )


def _mk_equipe(item_id: str, custo_total_1frente: float, custo_operacional_agregado: float, num_equipes_base: int):
    from concilium.domain.models.canonical import EquipeDireta

    return EquipeDireta(
        equipe_id=f"eq-{item_id}",
        item_id=item_id,
        cpu_id="CPU-X",
        custo_mao_obra_mensal=custo_total_1frente * 0.6,
        custo_equipamentos_mensal=custo_total_1frente * 0.3,
        custo_combustivel_total_mensal=custo_total_1frente * 0.1,
        custo_fixo_mensal=custo_total_1frente,
        custo_total=custo_total_1frente,
        custo_operacional_agregado=custo_operacional_agregado,
        num_equipes_base=num_equipes_base,
    )


class TestEqCustoTotalAgregado:
    """`_eq_custo_total_agregado`: prefere o campo agregado real; cai para o nominal
    (custo_total × num_equipes_base) só quando o campo novo não está disponível."""

    def test_usa_custo_operacional_agregado_quando_disponivel(self):
        eq = _mk_equipe("eap-A", custo_total_1frente=1000.0, custo_operacional_agregado=12000.0, num_equipes_base=3)
        assert MOD._eq_custo_total_agregado(eq) == pytest.approx(12000.0)

    def test_fallback_nominal_quando_campo_novo_zero(self):
        eq = _mk_equipe("eap-A", custo_total_1frente=1000.0, custo_operacional_agregado=0.0, num_equipes_base=3)
        assert MOD._eq_custo_total_agregado(eq) == pytest.approx(3000.0)


class TestPoolCustoUnitSemanalMultiFrente:
    """Reproduz os dois cenários sintéticos da investigação da issue #139, via o pipeline
    real (_build_contratos_recurso), não cálculo manual."""

    def _run(self, equipes, sched_lookup, resource_pool_size, activities):
        rcpsp_spec = {
            "resource_pool": {"ESC": resource_pool_size},
            "activities": activities,
            "resource_costs": {},
        }
        validacoes: list = []
        contratos, atribuicao, _cadeias = MOD._build_contratos_recurso(equipes, rcpsp_spec, sched_lookup, validacoes)
        return contratos, atribuicao

    def test_item_sozinho_no_pool_num_equipes_3_custo_unit_bate_com_real(self):
        """Caso A da investigação: 1 item, num_equipes=3 constante, 4 semanas, taxa real
        1 frente = 1000/semana -> custo agregado real = 12_000. Antes do fix,
        custo_unit_semanal saía como se fosse 1 frente (333,33/semana, custo_total_contrato
        = 4_000) — o valor pós-pool ficava idêntico ao de 1 frente, inalterado."""
        weeks = [f"S{n:03d}" for n in range(1, 5)]
        eq = _mk_equipe("eap-A", custo_total_1frente=1000.0, custo_operacional_agregado=12_000.0, num_equipes_base=3)
        sched_lookup = {"eap-A": _mk_sched("eap-A", weeks, num_equipes=3)}
        activities = [{"item_id": "eap-A", "required_resources": {"ESC": 3}}]
        contratos, atribuicao = self._run([eq], sched_lookup, resource_pool_size=3, activities=activities)

        assert len(contratos) == 1
        c = contratos[0]
        # custo_unit_semanal deve refletir a taxa REAL por máquina-semana (1000), não a
        # taxa de 1 frente dividida por machine_weeks agregado (333,33)
        assert c.custo_unit_semanal == pytest.approx(1000.0, rel=1e-3)
        assert "eap-A" in atribuicao
        custo_atribuido = atribuicao["eap-A"][0]
        assert custo_atribuido == pytest.approx(12_000.0, rel=1e-2)
        # antes do fix, isso teria batido com o valor de 1 frente (1000/semana × 4 semanas)
        assert custo_atribuido != pytest.approx(4_000.0, rel=1e-2)

    def test_dois_itens_compartilhando_pool_ne_diferentes(self):
        """Caso B da investigação: eap-A (num_equipes=3) e eap-B (num_equipes=1)
        compartilhando o mesmo pool, mesmas 4 semanas, mesma taxa real 1 frente = 1000/semana.
        Real agregado: A=12_000, B=4_000 (soma=16_000). Antes do fix, a média ponderada
        misturava numeradores de 1 frente com machine_weeks agregado, subestimando ambos
        de forma não-uniforme (dependente da composição do pool)."""
        weeks = [f"S{n:03d}" for n in range(1, 5)]
        eq_a = _mk_equipe("eap-A", custo_total_1frente=1000.0, custo_operacional_agregado=12_000.0, num_equipes_base=3)
        eq_b = _mk_equipe("eap-B", custo_total_1frente=1000.0, custo_operacional_agregado=4_000.0, num_equipes_base=1)
        sched_lookup = {
            "eap-A": _mk_sched("eap-A", weeks, num_equipes=3),
            "eap-B": _mk_sched("eap-B", weeks, num_equipes=1),
        }
        activities = [
            {"item_id": "eap-A", "required_resources": {"ESC": 3}},
            {"item_id": "eap-B", "required_resources": {"ESC": 1}},
        ]
        contratos, atribuicao = self._run(
            [eq_a, eq_b], sched_lookup, resource_pool_size=4, activities=activities
        )

        assert len(contratos) == 1
        c = contratos[0]
        assert c.custo_unit_semanal == pytest.approx(1000.0, rel=1e-3)
        # soma das atribuições deve reconciliar com o custo real agregado total (16_000),
        # não com a soma subestimada que o bug produzia
        soma_atribuida = atribuicao["eap-A"][0] + atribuicao["eap-B"][0]
        assert soma_atribuida == pytest.approx(16_000.0, rel=1e-2)
