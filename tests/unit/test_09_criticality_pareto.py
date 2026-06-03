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
