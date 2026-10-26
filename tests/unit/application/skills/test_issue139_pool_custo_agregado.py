"""Testes issue #139 — custo_unit_semanal do pool subestimado em itens multi-frente.

Parte 1: `_add_tipo_item_demand`/`_compute_custo_unit_fracs` dividiam `eq.custo_total`
(sempre "1 frente" por convenção ADR-091/ADR-162 D4) por `machine_weeks` (agregado — soma
`num_equipes` real por semana, todas as frentes). Verificado numericamente antes do fix:
item sozinho no pool com num_equipes=3 constante devolvia o valor de 1 frente inalterado
(1/3 do custo real). Corrigido via `_eq_custo_total_agregado` (skill 05, usa
`EquipeDireta.custo_operacional_agregado`, ADR-172 — integral semana a semana, já na mesma
base agregada de `machine_weeks`).

Parte 2: o mesmo tipo de mismatch (custo_total "1 frente" tratado como agregado) também
existia em skill 06 (`_consolidacao`) — `_br_build_venda_custo`, `_cat_accumulate_equipes_
sem_particao` e o próprio `_build_pe_for_equipe` (D6 do ADR-172) somavam/comparavam
`eq.custo_total` diretamente, sem diferenciar itens cobertos por pool (onde `custo_total`
pós-sobrescrita já É agregado, corrigido na parte 1) de itens sem pool (onde `custo_total`
continua "1 frente"). Corrigido via `_resolve_custo_equipe_agregado` (skill 06,
`_categorial.py`) — helper único, pool-aware, usado nos três pontos.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_MANIFESTS = Path(__file__).resolve().parents[4] / "src" / "concilium" / "application" / "skills" / "manifests"


def _load_skill05():
    p = _MANIFESTS / "05-equipes-e-alocacao" / "_skill_helpers" / "__init__.py"
    spec = importlib.util.spec_from_file_location("_issue139_skill05_helpers", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_issue139_skill05_helpers"] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_consolidacao():
    p = _MANIFESTS / "06-resultado-financeiro" / "_consolidacao" / "_skill_helpers" / "__init__.py"
    spec = importlib.util.spec_from_file_location("_issue139_consolidacao_helpers", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_issue139_consolidacao_helpers"] = mod
    spec.loader.exec_module(mod)
    return mod


MOD = _load_skill05()
CONSOLID = _load_consolidacao()


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


def _mk_equipe_consolid(
    item_id: str,
    custo_total: float,
    custo_operacional_agregado: float = 0.0,
    num_equipes_base: int = 1,
    contrato_tipo_id: str = "",
):
    return SimpleNamespace(
        item_id=item_id,
        custo_total=custo_total,
        custo_operacional_agregado=custo_operacional_agregado,
        num_equipes_base=num_equipes_base,
        contrato_tipo_id=contrato_tipo_id,
    )


class TestResolveCustoEquipeAgregado:
    """Issue #139 parte 2: `_resolve_custo_equipe_agregado` (skill 06, `_categorial.py`) —
    pool-aware, usado consistentemente em `_build_pe_for_equipe`, `_br_build_venda_custo`
    e `_cat_accumulate_equipes_sem_particao`."""

    def test_coberta_por_pool_usa_custo_total_direto(self):
        """contrato_tipo_id preenchido -> custo_total já é o agregado real ajustado pelo
        contrato (issue #139 parte 1) — não deve ser multiplicado nem substituído."""
        eq = _mk_equipe_consolid(
            "eap-A",
            custo_total=6_000.0,
            custo_operacional_agregado=12_000.0,  # autônomo, deliberadamente diferente
            num_equipes_base=3,
            contrato_tipo_id="ESC",
        )
        assert CONSOLID._resolve_custo_equipe_agregado(eq) == pytest.approx(6_000.0)

    def test_sem_pool_usa_custo_operacional_agregado(self):
        eq = _mk_equipe_consolid(
            "eap-A", custo_total=1_000.0, custo_operacional_agregado=12_000.0, num_equipes_base=3
        )
        assert CONSOLID._resolve_custo_equipe_agregado(eq) == pytest.approx(12_000.0)

    def test_sem_pool_sem_campo_novo_cai_para_nominal(self):
        eq = _mk_equipe_consolid(
            "eap-A", custo_total=1_000.0, custo_operacional_agregado=0.0, num_equipes_base=3
        )
        assert CONSOLID._resolve_custo_equipe_agregado(eq) == pytest.approx(3_000.0)

    def test_sem_pool_sem_frentes_base_default_1(self):
        eq = _mk_equipe_consolid("eap-A", custo_total=1_000.0, custo_operacional_agregado=0.0)
        assert CONSOLID._resolve_custo_equipe_agregado(eq) == pytest.approx(1_000.0)


class TestBrBuildVendaCustoPoolAware:
    def test_soma_mistura_pool_e_nao_pool_corretamente(self):
        """1 equipe com pool (custo_total já agregado) + 1 sem pool (custo_total 1 frente,
        precisa de custo_operacional_agregado) — soma deve refletir os dois corretamente,
        não tratar ambos como já agregados nem multiplicar a coberta por pool de novo."""
        eq_pool = _mk_equipe_consolid(
            "eap-A",
            custo_total=6_000.0,
            custo_operacional_agregado=12_000.0,
            num_equipes_base=3,
            contrato_tipo_id="ESC",
        )
        eq_sem_pool = _mk_equipe_consolid(
            "eap-B", custo_total=1_000.0, custo_operacional_agregado=4_000.0, num_equipes_base=1
        )
        canonical_in = SimpleNamespace(
            planejamento=[],
            equipes_diretas=[eq_pool, eq_sem_pool],
        )
        _venda_sem_bdi, _venda_com_bdi, custo_direto_equipe, _mat, custo_direto_pool = (
            CONSOLID._br_build_venda_custo(canonical_in)
        )
        assert custo_direto_equipe == pytest.approx(6_000.0 + 4_000.0)
        assert custo_direto_pool == pytest.approx(custo_direto_equipe)


class TestAplicarReconciliacaoPlanejamentoSincronizaAgregado:
    """Issue #139 parte 3: `_aplicar_reconciliacao_planejamento` (ADR-107, skill 05) é uma
    TERCEIRA via que sobrescreve `custo_total` para um valor "fonte de verdade" (agregado,
    de `plan.subtotal.sem_bdi.total` — mesma escala de `custo_venda_total`, todas as
    frentes), independente de contrato de pool. Sem sincronizar `custo_operacional_agregado`
    também, `_resolve_custo_equipe_agregado` (skill 06) usaria o valor stale (pré-
    reconciliação, calculado em skill-05 antes desta função rodar) — achado ao investigar
    uma regressão real no benchmark GOLDEN (margem caindo para -97%% após corrigir a issue
    #139 partes 1/2, porque `custo_operacional_agregado` de GOLDEN nunca era reconciliado
    e ficava ~3x maior que o `custo_total` já correto)."""

    def _mk_eq(self, item_id: str, custo_total: float, custo_operacional_agregado: float):
        return SimpleNamespace(
            item_id=item_id, custo_total=custo_total, custo_operacional_agregado=custo_operacional_agregado
        )

    def test_reconciliacao_sincroniza_custo_operacional_agregado(self):
        plan = SimpleNamespace(custo_sem_bdi=246_000.0, subtotal=None)
        eq = self._mk_eq("eap-01", custo_total=747_891.22, custo_operacional_agregado=747_891.22)
        validacoes: list = []
        MOD._aplicar_reconciliacao_planejamento(
            [eq], planejamento_map={"eap-01": plan}, planejamento_ref_map={}, validacoes=validacoes
        )
        assert eq.custo_total == pytest.approx(246_000.0)
        assert eq.custo_operacional_agregado == pytest.approx(246_000.0)
        assert eq.custo_reconciliado_planejamento is True
        assert any(v.codigo == "VAL-PLANEJAMENTO-OVERRIDE" for v in validacoes)


    def test_provenance_survives_canonical_json_roundtrip(self):
        """Persist explicit aggregate evidence between Skill05 and Skill06."""
        from concilium.domain.models.canonical import EquipeDireta

        plan = SimpleNamespace(custo_sem_bdi=400.0, subtotal=None)
        eq = EquipeDireta(
            item_id="eap-01",
            custo_total=200.0,
            custo_operacional_agregado=400.0,
        )
        MOD._aplicar_reconciliacao_planejamento(
            [eq], planejamento_map={"eap-01": plan},
            planejamento_ref_map={}, validacoes=[],
        )
        restored = EquipeDireta.model_validate_json(eq.model_dump_json(warnings="error"))
        assert restored.custo_reconciliado_planejamento is True
        assert restored.custo_total == pytest.approx(400.0)
        assert restored.custo_operacional_agregado == pytest.approx(400.0)

    def test_sem_desvio_significativo_nao_altera_nada(self):
        plan = SimpleNamespace(custo_sem_bdi=246_000.0, subtotal=None)
        eq = self._mk_eq("eap-01", custo_total=246_000.5, custo_operacional_agregado=246_000.5)
        validacoes: list = []
        MOD._aplicar_reconciliacao_planejamento(
            [eq], planejamento_map={"eap-01": plan}, planejamento_ref_map={}, validacoes=validacoes
        )
        assert eq.custo_total == pytest.approx(246_000.5)
        assert eq.custo_operacional_agregado == pytest.approx(246_000.5)
        assert not getattr(eq, "custo_reconciliado_planejamento", False)
        assert validacoes == []
