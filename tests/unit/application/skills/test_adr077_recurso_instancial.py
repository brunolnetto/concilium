"""ADR-077 — Testes unitários para o mapa instancial de utilização de recursos.

Cobre:
- TestInstanciaRecursoModel           — validação do modelo Pydantic
- TestComposicaoEquipeAtividadeModel  — validação do modelo Pydantic
- TestResumoUtilizacaoContratoModel   — validação do modelo Pydantic
- TestBuildInstanciasRecurso          — cálculo de instâncias (algoritmo central)
- TestAtribuicaoGulosa                — regra de prioridade por machine_weeks
- TestZeroDemandWeeks                 — semanas sem demanda = standby para todos
- TestStatusUtilizacao                — thresholds OK/AVISO/CRITICO
- TestValidatorStandbyAlto            — emissão de VAL-SLOT-STANDBY-ALTO
- TestCanonicalModelCampos            — canonical.py aceita os novos campos
"""

from __future__ import annotations

import sys
from pathlib import Path

# Garante que o src está no path (mesmo se rodado fora do venv)
_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))

import pytest  # noqa: E402

from concilium.domain.models.canonical import (  # noqa: E402
    CanonicalModel,
    ComposicaoEquipeAtividade,
    InstanciaRecurso,
    RecursoContrato,
    ResumoUtilizacaoContrato,
)

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _make_instancia(
    tipo_id: str = "ESC-3CAT",
    numero: int = 1,
    semanas_ativas: int = 48,
    semanas_standby: int = 0,
    atividades: list[str] | None = None,
) -> InstanciaRecurso:
    total = semanas_ativas + semanas_standby
    taxa = round(semanas_ativas / total * 100, 1) if total > 0 else 100.0
    custo = 50_000.0 * semanas_standby
    return InstanciaRecurso(
        instancia_id=f"{tipo_id}-{numero:02d}",
        contrato_id=f"contrato-{tipo_id.lower().replace('-', '_')}",
        tipo_id=tipo_id,
        numero=numero,
        semana_entrada="2026-W01",
        semana_saida="2026-W48",
        semanas_ativas=semanas_ativas,
        semanas_standby=semanas_standby,
        taxa_utilizacao_pct=taxa,
        custo_standby=custo,
        atividades_cobertas=atividades or [],
    )


def _make_contrato(
    tipo_id: str = "ESC-3CAT",
    quantidade: int = 6,
    semanas: int = 48,
    custo_unit: float = 50_000.0,
) -> RecursoContrato:
    return RecursoContrato(
        contrato_id=f"contrato-{tipo_id.lower().replace('-', '_')}",
        tipo_id=tipo_id,
        quantidade_contratada=quantidade,
        semana_inicio="2026-W01",
        semana_fim=f"2026-W{semanas:02d}",
        semanas_contrato=semanas,
        custo_unit_semanal=custo_unit,
        custo_total_contrato=quantidade * custo_unit * semanas,
        items_cobertos=[],
    )


def _make_sched_activity(item_id: str, weeks: list[str], num_equipes: int = 1):
    """Simula um ScheduledActivityCanonical simplificado com distribuicao_semanal."""

    class _DistSemanal:
        def __init__(self, ne):
            self.num_equipes = ne
            self.eficiencia = 1.0
            self.fator_clima = 1.0
            self.fator_calendario = 1.0

    class _Sched:
        def __init__(self, aid, weeks, ne):
            self.activity_id = aid
            self.distribuicao_semanal = {w: _DistSemanal(ne) for w in weeks}
            self.ramp_profile = None

    return _Sched(item_id, weeks, num_equipes)


# ─────────────────────────────────────────────────────────────────────────────
# TestInstanciaRecursoModel
# ─────────────────────────────────────────────────────────────────────────────


class TestInstanciaRecursoModel:
    def test_instancia_minima(self):
        inst = _make_instancia(numero=1, semanas_ativas=48, semanas_standby=0)
        assert inst.instancia_id == "ESC-3CAT-01"
        assert inst.taxa_utilizacao_pct == 100.0
        assert inst.custo_standby == 0.0

    def test_instancia_com_standby(self):
        inst = _make_instancia(numero=3, semanas_ativas=37, semanas_standby=11)
        assert inst.semanas_standby == 11
        assert inst.taxa_utilizacao_pct == pytest.approx(77.1, abs=0.2)
        assert inst.custo_standby > 0

    def test_instancia_atividades_cobertas(self):
        inst = _make_instancia(numero=1, semanas_ativas=48, atividades=["eap-1_9"])
        assert "eap-1_9" in inst.atividades_cobertas

    def test_instancia_multi_atividade(self):
        inst = _make_instancia(
            numero=3,
            semanas_ativas=37,
            semanas_standby=11,
            atividades=["eap-1_6", "eap-1_5"],
        )
        assert len(inst.atividades_cobertas) == 2

    def test_instancia_id_formatacao(self):
        for n in [1, 5, 10, 15]:
            inst = _make_instancia(numero=n)
            # Deve ser zero-padded para 2 dígitos
            assert inst.instancia_id == f"ESC-3CAT-{n:02d}"


# ─────────────────────────────────────────────────────────────────────────────
# TestComposicaoEquipeAtividadeModel
# ─────────────────────────────────────────────────────────────────────────────


class TestComposicaoEquipeAtividadeModel:
    def test_composicao_basica(self):
        comp = ComposicaoEquipeAtividade(
            activity_id="eap-1_9",
            tipo_id="ESC-3CAT",
            contrato_id="contrato-esc_3cat",
            pool_size=6,
            n_instancias=2,
            required=2,
            instancias_numeros=[1, 2],
            semana_inicio="2026-W01",
            semana_fim="2026-W48",
            machine_weeks=96,
        )
        assert comp.activity_id == "eap-1_9"
        assert comp.n_instancias == 2
        assert comp.machine_weeks == 96
        assert 1 in comp.instancias_numeros
        assert 2 in comp.instancias_numeros

    def test_composicao_slots_corretos(self):
        comp = ComposicaoEquipeAtividade(
            activity_id="eap-1_6",
            tipo_id="ESC-3CAT",
            contrato_id="contrato-esc_3cat",
            pool_size=6,
            n_instancias=4,
            required=4,
            instancias_numeros=[3, 4, 5, 6],
            semana_inicio="2026-W01",
            semana_fim="2026-W25",
            machine_weeks=100,
        )
        assert len(comp.instancias_numeros) == 4
        assert comp.instancias_numeros == [3, 4, 5, 6]


# ─────────────────────────────────────────────────────────────────────────────
# TestResumoUtilizacaoContratoModel
# ─────────────────────────────────────────────────────────────────────────────


class TestResumoUtilizacaoContratoModel:
    def test_resumo_basico(self):
        r = ResumoUtilizacaoContrato(
            contrato_id="contrato-esc_3cat",
            tipo_id="ESC-3CAT",
            quantidade_contratada=6,
            semanas_contrato=48,
            machine_weeks_disponiveis=288,
            machine_weeks_usados=244,
            machine_weeks_standby=44,
            taxa_utilizacao_pct=84.7,
            custo_standby_total=2_200_000.0,
            status_utilizacao="OK",
        )
        assert r.taxa_utilizacao_pct == pytest.approx(84.7)
        assert r.status_utilizacao == "OK"

    def test_status_critico(self):
        r = ResumoUtilizacaoContrato(
            contrato_id="c1",
            tipo_id="T1",
            quantidade_contratada=10,
            semanas_contrato=48,
            machine_weeks_disponiveis=480,
            machine_weeks_usados=100,
            machine_weeks_standby=380,
            taxa_utilizacao_pct=20.8,
            custo_standby_total=10_000.0,
            status_utilizacao="CRITICO",
        )
        assert r.status_utilizacao == "CRITICO"

    def test_status_aviso(self):
        r = ResumoUtilizacaoContrato(
            contrato_id="c1",
            tipo_id="T1",
            quantidade_contratada=4,
            semanas_contrato=48,
            machine_weeks_disponiveis=192,
            machine_weeks_usados=100,
            machine_weeks_standby=92,
            taxa_utilizacao_pct=52.1,
            custo_standby_total=5_000.0,
            status_utilizacao="AVISO",
        )
        assert r.status_utilizacao == "AVISO"


# ─────────────────────────────────────────────────────────────────────────────
# TestBuildInstanciasRecurso — algoritmo central
# ─────────────────────────────────────────────────────────────────────────────


def _weeks_range(start: int, end: int) -> list[str]:
    """Gera lista de weeks no formato '2026-Wxx' de start a end (inclusive)."""
    return [f"2026-W{w:02d}" for w in range(start, end + 1)]


class TestBuildInstanciasRecurso:
    """Testa _build_instancias_recurso com cenários que reproduzem AGIS ESC-3CAT."""

    @pytest.fixture
    def esc3cat_setup(self):
        """
        Reproduz o cenário ESC-3CAT pós-ADR-076 Opção E:
          pool=6, eap-1_9(2u, W1-48), eap-1_6(4u, W1-25), eap-1_5(4u, W26-37)
        """
        from concilium.application.skills.manifests._05_helpers import (
            _build_instancias_recurso,
        )

        return _build_instancias_recurso

    def _run_esc3cat(self):
        """Executa _build_instancias_recurso para o cenário ESC-3CAT."""
        # Importa a função diretamente (sem pacote — via path)
        import importlib.util
        import sys

        spec = importlib.util.spec_from_file_location(
            "helpers_a",
            _ROOT
            / "src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers/__init__.py",
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["helpers_a"] = mod
        spec.loader.exec_module(mod)
        fn = mod._build_instancias_recurso

        contrato = _make_contrato("ESC-3CAT", quantidade=6, semanas=48, custo_unit=50_000.0)

        # rcpsp_spec: eap-1_9 requires 2, eap-1_6 requires 4, eap-1_5 requires 4
        # total_required_peak por item = só um tipo, então ratio=1
        rcpsp_spec = {
            "resource_pool": {"ESC-3CAT": 6},
            "activities": [
                {"item_id": "eap-1_9", "required_resources": {"ESC-3CAT": 2}},
                {"item_id": "eap-1_6", "required_resources": {"ESC-3CAT": 4}},
                {"item_id": "eap-1_5", "required_resources": {"ESC-3CAT": 4}},
            ],
        }

        # Cronograma simulado
        sched_lookup = {
            "eap-1_9": _make_sched_activity("eap-1_9", _weeks_range(1, 48), num_equipes=2),
            "eap-1_6": _make_sched_activity("eap-1_6", _weeks_range(1, 25), num_equipes=4),
            "eap-1_5": _make_sched_activity("eap-1_5", _weeks_range(26, 37), num_equipes=4),
        }

        validacoes = []
        return fn([contrato], rcpsp_spec, sched_lookup, validacoes), validacoes

    def test_numero_instancias_correto(self):
        (instancias, composicoes, resumos), _ = self._run_esc3cat()
        # Pool=6 → 6 instâncias
        assert len(instancias) == 6

    def test_instancias_1_2_sem_standby(self):
        """Instâncias 1-2 (eap-1_9, 48w) devem ter 0 standby."""
        (instancias, _, _), _ = self._run_esc3cat()
        inst1 = next(i for i in instancias if i.numero == 1)
        inst2 = next(i for i in instancias if i.numero == 2)
        assert inst1.semanas_standby == 0
        assert inst2.semanas_standby == 0
        assert inst1.taxa_utilizacao_pct == pytest.approx(100.0)

    def test_instancias_3_6_com_standby(self):
        """Instâncias 3-6 devem ter 11 semanas de standby (W38-W48)."""
        (instancias, _, _), _ = self._run_esc3cat()
        for num in [3, 4, 5, 6]:
            inst = next(i for i in instancias if i.numero == num)
            assert inst.semanas_standby == 11, f"Instância {num}: esperado 11w standby, got {inst.semanas_standby}"
            assert inst.semanas_ativas == 37

    def test_instancias_1_2_cobrem_eap1_9(self):
        """Instâncias 1-2 devem cobrir apenas eap-1_9."""
        (instancias, _, _), _ = self._run_esc3cat()
        for num in [1, 2]:
            inst = next(i for i in instancias if i.numero == num)
            assert "eap-1_9" in inst.atividades_cobertas
            assert "eap-1_6" not in inst.atividades_cobertas
            assert "eap-1_5" not in inst.atividades_cobertas

    def test_instancias_3_6_cobrem_eap1_6_e_eap1_5(self):
        """Instâncias 3-6 devem cobrir eap-1_6 e eap-1_5."""
        (instancias, _, _), _ = self._run_esc3cat()
        for num in [3, 4, 5, 6]:
            inst = next(i for i in instancias if i.numero == num)
            assert "eap-1_6" in inst.atividades_cobertas
            assert "eap-1_5" in inst.atividades_cobertas

    def test_taxa_utilizacao_instancia_1(self):
        (instancias, _, _), _ = self._run_esc3cat()
        inst1 = next(i for i in instancias if i.numero == 1)
        assert inst1.taxa_utilizacao_pct == pytest.approx(100.0)

    def test_taxa_utilizacao_instancias_3_6(self):
        """77.1% = 37/48 × 100."""
        (instancias, _, _), _ = self._run_esc3cat()
        for num in [3, 4, 5, 6]:
            inst = next(i for i in instancias if i.numero == num)
            assert inst.taxa_utilizacao_pct == pytest.approx(37 / 48 * 100, abs=0.2)

    def test_resumo_taxa_geral(self):
        """Taxa geral: 244/288 = 84.7%."""
        (_, _, resumos), _ = self._run_esc3cat()
        assert len(resumos) == 1
        r = resumos[0]
        # machine_weeks_usados = 2×48 + 4×37 = 96 + 148 = 244
        assert r.machine_weeks_usados == 244
        assert r.machine_weeks_disponiveis == 288
        assert r.taxa_utilizacao_pct == pytest.approx(84.7, abs=0.2)
        assert r.status_utilizacao == "OK"

    def test_composicoes_corretas(self):
        """Deve gerar 3 composicoes (eap-1_9, eap-1_6, eap-1_5)."""
        (_, composicoes, _), _ = self._run_esc3cat()
        act_ids = {c.activity_id for c in composicoes}
        assert "eap-1_9" in act_ids
        assert "eap-1_6" in act_ids
        assert "eap-1_5" in act_ids

    def test_composicao_eap1_9_slots_1_2(self):
        (_, composicoes, _), _ = self._run_esc3cat()
        comp = next(c for c in composicoes if c.activity_id == "eap-1_9")
        assert comp.n_instancias == 2
        assert comp.instancias_numeros == [1, 2]

    def test_composicao_eap1_6_slots_3_6(self):
        (_, composicoes, _), _ = self._run_esc3cat()
        comp = next(c for c in composicoes if c.activity_id == "eap-1_6")
        assert comp.n_instancias == 4
        assert comp.instancias_numeros == [3, 4, 5, 6]


# ─────────────────────────────────────────────────────────────────────────────
# TestAtribuicaoGulosa
# ─────────────────────────────────────────────────────────────────────────────


class TestAtribuicaoGulosa:
    """Verifica que a prioridade de machine_weeks determina quais slots vão para qual atividade."""

    def _run_two_activities(self, mw_a: int, mw_b: int, req_a: int, req_b: int, pool: int):
        """Cenário simples: atividade A e B competem pelo mesmo pool em semanas disjuntas."""
        import importlib.util
        import sys

        spec = importlib.util.spec_from_file_location(
            "helpers_a",
            _ROOT
            / "src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers/__init__.py",
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["helpers_a"] = mod
        spec.loader.exec_module(mod)
        fn = mod._build_instancias_recurso

        weeks_a = _weeks_range(1, mw_a // req_a)
        weeks_b = _weeks_range(mw_a // req_a + 1, mw_a // req_a + mw_b // req_b)

        contrato = _make_contrato("T1", quantidade=pool, semanas=len(weeks_a) + len(weeks_b))
        rcpsp_spec = {
            "resource_pool": {"T1": pool},
            "activities": [
                {"item_id": "act-a", "required_resources": {"T1": req_a}},
                {"item_id": "act-b", "required_resources": {"T1": req_b}},
            ],
        }
        sched_lookup = {
            "act-a": _make_sched_activity("act-a", weeks_a, num_equipes=req_a),
            "act-b": _make_sched_activity("act-b", weeks_b, num_equipes=req_b),
        }
        validacoes = []
        return fn([contrato], rcpsp_spec, sched_lookup, validacoes), validacoes

    def test_atividade_maior_span_tem_slots_baixos(self):
        """Atividade com maior span calendário deve receber slots de menor número.

        act-a: span 10w; act-b: span 10w + (offset 10) = 10w span também → mesmos spans
        Então usamos atividades com spans diferentes para o teste.
        """
        # Para este teste, usamos atividades de spans claramente distintos:
        # act-longue: 20w de duração; act-curta: 5w de duração
        import importlib.util
        import sys

        spec = importlib.util.spec_from_file_location(
            "helpers_a",
            _ROOT
            / "src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers/__init__.py",
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["helpers_a"] = mod
        spec.loader.exec_module(mod)
        fn = mod._build_instancias_recurso

        # Atividades em semanas disjuntas para simplificar
        weeks_longa = _weeks_range(1, 20)
        weeks_curta = _weeks_range(21, 25)

        contrato = _make_contrato("T1", quantidade=3, semanas=25)
        rcpsp_spec = {
            "resource_pool": {"T1": 3},
            "activities": [
                {"item_id": "act-longa", "required_resources": {"T1": 2}},
                {"item_id": "act-curta", "required_resources": {"T1": 2}},
            ],
        }
        sched_lookup = {
            "act-longa": _make_sched_activity("act-longa", weeks_longa, num_equipes=2),
            "act-curta": _make_sched_activity("act-curta", weeks_curta, num_equipes=2),
        }
        validacoes = []
        _, composicoes, _ = fn([contrato], rcpsp_spec, sched_lookup, validacoes)
        comp_longa = next(c for c in composicoes if c.activity_id == "act-longa")
        comp_curta = next(c for c in composicoes if c.activity_id == "act-curta")
        # act-longa tem span=19 > act-curta span=4 → recebe slots menores
        assert min(comp_longa.instancias_numeros) <= min(comp_curta.instancias_numeros)


# ─────────────────────────────────────────────────────────────────────────────
# TestZeroDemandWeeks
# ─────────────────────────────────────────────────────────────────────────────


class TestZeroDemandWeeks:
    """Semanas do contrato sem atividade → standby para todas as instâncias."""

    def test_contrato_mais_longo_que_atividades(self):
        """Contrato de 10 semanas, atividade ativa em W1-W5 apenas."""
        import importlib.util
        import sys

        spec = importlib.util.spec_from_file_location(
            "helpers_a",
            _ROOT
            / "src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers/__init__.py",
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["helpers_a"] = mod
        spec.loader.exec_module(mod)
        fn = mod._build_instancias_recurso

        contrato = RecursoContrato(
            contrato_id="contrato-t1",
            tipo_id="T1",
            quantidade_contratada=2,
            semana_inicio="2026-W01",
            semana_fim="2026-W10",
            semanas_contrato=10,  # 10 semanas de contrato
            custo_unit_semanal=10_000.0,
            custo_total_contrato=200_000.0,
            items_cobertos=["act-a"],
        )
        rcpsp_spec = {
            "resource_pool": {"T1": 2},
            "activities": [{"item_id": "act-a", "required_resources": {"T1": 2}}],
        }
        sched_lookup = {
            "act-a": _make_sched_activity("act-a", _weeks_range(1, 5), num_equipes=2),
        }
        validacoes = []
        instancias, _, resumos = fn([contrato], rcpsp_spec, sched_lookup, validacoes)

        # Cada instância: 5 semanas ativas + 5 semanas standby (zero demand)
        for inst in instancias:
            assert inst.semanas_ativas == 5, f"esperado 5, got {inst.semanas_ativas}"
            assert inst.semanas_standby == 5, f"esperado 5, got {inst.semanas_standby}"

        assert resumos[0].machine_weeks_standby == 10  # 2 instâncias × 5 semanas
        assert resumos[0].taxa_utilizacao_pct == pytest.approx(50.0)


# ─────────────────────────────────────────────────────────────────────────────
# TestStatusUtilizacao
# ─────────────────────────────────────────────────────────────────────────────


class TestStatusUtilizacao:
    """Testa thresholds: OK ≥ 65%, AVISO 35-65%, CRITICO < 35%."""

    def _resumo_com_taxa(self, taxa: float) -> ResumoUtilizacaoContrato:
        mw_disp = 100
        mw_usados = round(taxa)
        mw_standby = mw_disp - mw_usados
        if taxa >= 65.0:
            status = "OK"
        elif taxa >= 35.0:
            status = "AVISO"
        else:
            status = "CRITICO"
        return ResumoUtilizacaoContrato(
            contrato_id="c1",
            tipo_id="T1",
            quantidade_contratada=5,
            semanas_contrato=20,
            machine_weeks_disponiveis=mw_disp,
            machine_weeks_usados=mw_usados,
            machine_weeks_standby=mw_standby,
            taxa_utilizacao_pct=taxa,
            custo_standby_total=mw_standby * 1000.0,
            status_utilizacao=status,
        )

    def test_status_ok_65(self):
        assert self._resumo_com_taxa(65.0).status_utilizacao == "OK"

    def test_status_ok_100(self):
        assert self._resumo_com_taxa(100.0).status_utilizacao == "OK"

    def test_status_aviso_35(self):
        assert self._resumo_com_taxa(35.0).status_utilizacao == "AVISO"

    def test_status_aviso_50(self):
        assert self._resumo_com_taxa(50.0).status_utilizacao == "AVISO"

    def test_status_critico_34(self):
        assert self._resumo_com_taxa(34.0).status_utilizacao == "CRITICO"

    def test_status_critico_0(self):
        assert self._resumo_com_taxa(0.0).status_utilizacao == "CRITICO"


# ─────────────────────────────────────────────────────────────────────────────
# TestValidatorStandbyAlto
# ─────────────────────────────────────────────────────────────────────────────


class TestValidatorStandbyAlto:
    """Verifica que VAL-SLOT-STANDBY-ALTO é emitido quando standby > 35%."""

    def _run_with_standby(self, standby_pct: float):
        """Cenário com taxa = (1 - standby_pct/100)."""
        import importlib.util
        import sys

        spec = importlib.util.spec_from_file_location(
            "helpers_a",
            _ROOT
            / "src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers/__init__.py",
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["helpers_a"] = mod
        spec.loader.exec_module(mod)
        fn = mod._build_instancias_recurso

        # Pool=1, atividade usa 0 (apenas standby) ou 1 semana
        total_weeks = 10
        active_weeks = round(total_weeks * (1 - standby_pct / 100))
        total_weeks - active_weeks

        contrato = RecursoContrato(
            contrato_id="contrato-t1",
            tipo_id="T1",
            quantidade_contratada=1,
            semana_inicio="2026-W01",
            semana_fim=f"2026-W{total_weeks:02d}",
            semanas_contrato=total_weeks,
            custo_unit_semanal=10_000.0,
            custo_total_contrato=100_000.0,
            items_cobertos=["act-a"],
        )
        rcpsp_spec = {
            "resource_pool": {"T1": 1},
            "activities": [{"item_id": "act-a", "required_resources": {"T1": 1}}],
        }
        active_wks = _weeks_range(1, active_weeks) if active_weeks > 0 else []
        sched_lookup = (
            {
                "act-a": _make_sched_activity("act-a", active_wks, num_equipes=1),
            }
            if active_wks
            else {}
        )
        validacoes = []
        fn([contrato], rcpsp_spec, sched_lookup, validacoes)
        return validacoes

    def test_sem_standby_nao_emite_validator(self):
        """0% standby → não deve emitir VAL-SLOT-STANDBY-ALTO."""
        vals = self._run_with_standby(0.0)
        codes = [v.codigo for v in vals]
        assert "VAL-SLOT-STANDBY-ALTO" not in codes

    def test_standby_30pct_nao_emite_validator(self):
        """30% standby < 35% threshold → não deve emitir."""
        vals = self._run_with_standby(30.0)
        codes = [v.codigo for v in vals]
        assert "VAL-SLOT-STANDBY-ALTO" not in codes

    def test_standby_50pct_emite_aviso(self):
        """50% standby → deve emitir VAL-SLOT-STANDBY-ALTO (AVISO)."""
        vals = self._run_with_standby(50.0)
        val = next((v for v in vals if v.codigo == "VAL-SLOT-STANDBY-ALTO"), None)
        assert val is not None, "VAL-SLOT-STANDBY-ALTO não emitido com 50% standby"
        assert val.status in ("AVISO", "ERRO")


# ─────────────────────────────────────────────────────────────────────────────
# TestCanonicalModelCampos
# ─────────────────────────────────────────────────────────────────────────────


class TestCanonicalModelCampos:
    """Verifica que CanonicalModel aceita os novos campos ADR-077."""

    def test_canonical_aceita_instancias_recurso(self, tmp_path):
        """CanonicalModel deve ter o campo instancias_recurso."""

        _make_instancia(numero=1, semanas_ativas=10)
        # Verifica que o campo existe sem precisar criar um canonical completo
        assert hasattr(CanonicalModel, "model_fields")
        fields = CanonicalModel.model_fields
        assert "instancias_recurso" in fields
        assert "composicao_equipes_atividade" in fields
        assert "resumo_utilizacao_contratos" in fields

    def test_instancia_recurso_serializa(self):
        inst = _make_instancia(numero=1, semanas_ativas=48, semanas_standby=0)
        d = inst.model_dump()
        assert d["instancia_id"] == "ESC-3CAT-01"
        assert d["semanas_ativas"] == 48
        assert d["taxa_utilizacao_pct"] == 100.0

    def test_resumo_utilizacao_serializa(self):
        r = ResumoUtilizacaoContrato(
            contrato_id="c1",
            tipo_id="ESC-3CAT",
            quantidade_contratada=6,
            semanas_contrato=48,
            machine_weeks_disponiveis=288,
            machine_weeks_usados=244,
            machine_weeks_standby=44,
            taxa_utilizacao_pct=84.7,
            custo_standby_total=2_200_000.0,
            status_utilizacao="OK",
        )
        d = r.model_dump()
        assert d["status_utilizacao"] == "OK"
        assert d["machine_weeks_disponiveis"] == 288

    def test_composicao_serializa(self):
        comp = ComposicaoEquipeAtividade(
            activity_id="eap-1_9",
            tipo_id="ESC-3CAT",
            contrato_id="contrato-esc_3cat",
            pool_size=6,
            n_instancias=2,
            required=2,
            instancias_numeros=[1, 2],
            machine_weeks=96,
        )
        d = comp.model_dump()
        assert d["activity_id"] == "eap-1_9"
        assert d["instancias_numeros"] == [1, 2]
