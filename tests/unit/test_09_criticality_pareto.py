"""Testes da skill 09 — Cost Criticality com dominância de Pareto (ADR-020)."""

from datetime import UTC, date, datetime

from concilium.application.skills import run_diagnostico_criticidade
from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    CostCriticalityResult,
    CriticidadeProfile,
    Cronograma,
    EquipeDireta,
    Meta,
    Planejamento,
    Projeto,
    RegimeTrabalho,
)


def _meta():
    return Meta(versao_schema="1.0.0", gerado_em=datetime.now(UTC), contexto_id="test")


def _projeto():
    return Projeto(
        id="p-test",
        nome="Teste",
        tipo_obra="terraplenagem",
        localizacao="CE",
        coordenadas=Coordenadas(lat=-3.7, lng=-38.5),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
        snapshot_catalogo_id="c1",
        snapshot_perfil_id="p1",
    )


def _equipe(item_id: str, custo_total: float, custo_mo: float = 0.0, perm: float = 1.0):
    return EquipeDireta(
        item_id=item_id,
        descricao=item_id,
        custo_total=custo_total,
        custo_mao_obra_mensal=custo_mo,
        permanencia_meses=perm,
    )


def _planejamento_stub():
    return [Planejamento(item_id="stub")]


def _cronograma_stub():
    return Cronograma()


def _canonical(**kwargs):
    base = dict(meta=_meta(), projeto=_projeto(), cronograma=_cronograma_stub())
    base.update(kwargs)
    return CanonicalModel(**base)


def test_retorna_cost_criticality_result_tipado():
    """Resultado deve ser CostCriticalityResult, não dict."""
    equipes = [
        _equipe("atv-001", 600_000.0, 50_000.0, 6.0),
        _equipe("atv-002", 300_000.0, 30_000.0, 4.0),
        _equipe("atv-003", 100_000.0, 10_000.0, 2.0),
    ]
    c = _canonical(equipes_diretas=equipes, planejamento=_planejamento_stub())
    result = run_diagnostico_criticidade(c, {})
    assert not result.has_errors
    ccr = result.canonical.cost_criticality_report
    assert isinstance(ccr, CostCriticalityResult)
    assert ccr.n_atividades == 3
    assert len(ccr.atividades) == 3
    assert all(isinstance(p, CriticidadeProfile) for p in ccr.atividades)


def test_fronteira_pareto_nao_vazia():
    """Deve haver pelo menos uma atividade na fronteira de Pareto."""
    equipes = [
        _equipe("atv-001", 700_000.0, 60_000.0, 8.0),
        _equipe("atv-002", 200_000.0, 20_000.0, 2.0),
        _equipe("atv-003", 100_000.0, 10_000.0, 1.0),
    ]
    c = _canonical(equipes_diretas=equipes, planejamento=_planejamento_stub())
    result = run_diagnostico_criticidade(c, {})
    ccr = result.canonical.cost_criticality_report
    assert ccr.n_pareto_frontier >= 1


def test_atividade_dominante_e_A_plus():
    """Atividade com custo muito maior e recurso constrangido → A+."""
    equipes = [
        _equipe("atv-A", 800_000.0, 80_000.0, 10.0),
        _equipe("atv-B", 100_000.0, 10_000.0, 1.0),
        _equipe("atv-C", 50_000.0, 5_000.0, 0.5),
        _equipe("atv-D", 30_000.0, 3_000.0, 0.3),
        _equipe("atv-E", 20_000.0, 2_000.0, 0.2),
    ]
    c = _canonical(equipes_diretas=equipes, planejamento=_planejamento_stub())
    result = run_diagnostico_criticidade(c, {})
    ccr = result.canonical.cost_criticality_report
    # atv-A domina todas — deve ser A+
    perfil_A = next(p for p in ccr.atividades if p.atividade_id == "atv-A")
    assert perfil_A.pareto_frontier is True
    assert perfil_A.classe == "A+"
    assert perfil_A.rank_lexicografico == 1


def test_sem_score_sintetico():
    """CriticidadeProfile não deve ter campo 'score'."""
    equipes = [_equipe("atv-001", 500_000.0), _equipe("atv-002", 500_000.0)]
    c = _canonical(equipes_diretas=equipes, planejamento=_planejamento_stub())
    result = run_diagnostico_criticidade(c, {})
    ccr = result.canonical.cost_criticality_report
    for perfil in ccr.atividades:
        assert not hasattr(perfil, "score"), "CriticidadeProfile não deve ter score sintético"


def test_rank_lexicografico_ordenado():
    """Atividades ordenadas por rank_lexicografico crescente na lista."""
    equipes = [_equipe(f"atv-{i}", (5 - i) * 100_000.0) for i in range(5)]
    c = _canonical(equipes_diretas=equipes, planejamento=_planejamento_stub())
    result = run_diagnostico_criticidade(c, {})
    ccr = result.canonical.cost_criticality_report
    ranks = [p.rank_lexicografico for p in ccr.atividades]
    assert ranks == sorted(ranks)


def test_classificacao_sem_pesos():
    """Classificação determinística — sem parâmetro pesos_score."""
    equipes = [_equipe(f"item-{i}", (10 - i) * 50_000.0) for i in range(10)]
    c = _canonical(equipes_diretas=equipes, planejamento=_planejamento_stub())
    r1 = run_diagnostico_criticidade(c, {})
    r2 = run_diagnostico_criticidade(c, {})  # sem pesos — deve ser idêntico
    classes1 = [p.classe for p in r1.canonical.cost_criticality_report.atividades]
    classes2 = [p.classe for p in r2.canonical.cost_criticality_report.atividades]
    assert classes1 == classes2


def test_precondicao_sem_equipes():
    """Sem equipes_diretas → ERRO de pré-condição."""
    c = _canonical(planejamento=_planejamento_stub())
    result = run_diagnostico_criticidade(c, {})
    assert result.has_errors
    assert any(v.codigo in ("VAL-CC-PRECONDICAO", "VAL-DIAG-PRE") for v in result.validacoes)


def test_dimensoes_independentes_expostas():
    """Cada perfil deve expor .custo, .duracao, .recurso, .sensibilidade com rank e percentil."""
    equipes = [
        _equipe("atv-X", 400_000.0, 40_000.0, 4.0),
        _equipe("atv-Y", 600_000.0, 60_000.0, 6.0),
    ]
    c = _canonical(equipes_diretas=equipes, planejamento=_planejamento_stub())
    result = run_diagnostico_criticidade(c, {})
    for p in result.canonical.cost_criticality_report.atividades:
        for dim in (p.custo, p.duracao, p.recurso, p.sensibilidade):
            assert 0.0 <= dim.percentil <= 1.0
            assert dim.rank >= 1








# ══ 07-diagnostico-criticidade/skill.py ═══════════════════════════════════════


def _minimal_canonical(**kw):
    return CanonicalModel(meta=_meta(), projeto=_projeto(), **kw)


def _load_skill_module(skill_id: str) -> object:
    import concilium.application.skills as _skills_pkg

    return _skills_pkg._load_skill_module(skill_id)


class TestCostCriticalityEdgeCases:
    def _classify(self):
        mod = _load_skill_module("07-diagnostico-criticidade")
        return mod._classify

    def test_classify_score_tier_a(self):
        """rank in top-40% without frontier → 'A'; top-20% on frontier → 'A+'."""
        fn = self._classify()
        assert fn(2, 5, False) == "A"  # rank 2/5, top_40=ceil(5*0.4)=2 → A
        assert fn(1, 5, True) == "A+"  # rank 1/5, on_frontier, top_20=ceil(5*0.2)=1 → A+

    def test_classify_score_tier_b(self):
        """rank in top-70% but not top-40% → 'B'."""
        fn = self._classify()
        assert fn(3, 5, False) == "B"  # rank 3/5, top_40=2, top_70=ceil(5*0.7)=4 → B
        assert fn(4, 5, False) == "B"  # rank 4/5, top_70=4 → B

    def test_run_diagnostico_criticidade_custo_total_zero_returns_early(self):
        """custo_total_obra == 0 → ERRO VAL-CC-01 and early return."""
        from concilium.application.skills import run_diagnostico_criticidade
        from concilium.domain.models.canonical import (
            BdiCategorias,
            PrecoUnitarioCategoria,
            SubtotalCategorias,
            SubtotalSemBdiComBdi,
        )

        # equipe with custo_total=0 → custo_total_obra=0 → early return with ERRO
        equipe = EquipeDireta(
            equipe_id="eq-i1",
            item_id="i1",
            cpu_id="CPU-X",
            nome="Equipe Test",
            custo_total=0.0,  # zero → triggers early return
            custo_mao_obra_mensal=0.0,
            permanencia_meses=0.0,
        )
        plan = Planejamento(
            item_id="i1",
            cpu_id="CPU-X",
            quantitativo=100.0,
            preco_unitario=PrecoUnitarioCategoria(material=0.0, diesel=0.0, mao_obra=0.0, equipamentos=0.0, total=0.0),
            bdi=BdiCategorias(material=0.0, diesel=0.0, mao_obra=0.0, equipamentos=0.0),
            preco_unitario_com_bdi=PrecoUnitarioCategoria(
                material=0.0, diesel=0.0, mao_obra=0.0, equipamentos=0.0, total=0.0
            ),
            subtotal=SubtotalSemBdiComBdi(
                sem_bdi=SubtotalCategorias(material=0.0, diesel=0.0, mao_obra=0.0, equipamentos=0.0, total=0.0),
                com_bdi=SubtotalCategorias(material=0.0, diesel=0.0, mao_obra=0.0, equipamentos=0.0, total=0.0),
            ),
        )
        canonical = _minimal_canonical(equipes_diretas=[equipe], planejamento=[plan])
        result = run_diagnostico_criticidade(canonical, {})
        errors = [v for v in result.validacoes if v.codigo == "VAL-CC-01" and v.status == "ERRO"]
        assert len(errors) >= 1



