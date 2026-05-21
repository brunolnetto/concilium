"""Testes da skill 13 — Replan Advisor (ADR-019 §D1.2)."""

from datetime import UTC, date, datetime

import pytest

from concilium.application.skills import run_assessor_replanejamento
from concilium.domain.models.canonical import (
    CanonicalModel,
    ConflitoPico,
    CustoTotal,
    Indireto,
    Meta,
    Projeto,
    Resultado,
    ResultadoReconciliado,
    ValidacaoItem,
    Venda,
)


def _meta():
    return Meta(versao_schema="1.0.0", gerado_em=datetime.now(UTC), contexto_id="test")


def _projeto():
    from concilium.domain.models.canonical import Coordenadas, RegimeTrabalho

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


def _resultado(margem: float, status: str) -> Resultado:
    venda = 1_000_000.0
    custo = round(venda * (1 - margem), 2)
    return Resultado(
        venda=Venda(total_sem_bdi=800_000.0, total_com_bdi=venda),
        custo=CustoTotal(
            direto_equipes=custo * 0.7,
            indireto_adm=custo * 0.1,
            indireto_top=custo * 0.05,
            indireto_lab=custo * 0.05,
            indireto_qsms=custo * 0.05,
            indireto_mob=custo * 0.05,
            total=custo,
        ),
        resultado_financeiro=round(venda - custo, 2),
        margem_pct=margem,
        status_margem=status,
        validacoes=[ValidacaoItem(codigo="VAL-POL-MARGEM", status="OK")],
    )


def _canonical(**kwargs) -> CanonicalModel:
    base = dict(meta=_meta(), projeto=_projeto())
    base.update(kwargs)
    return CanonicalModel(**base)


_PERFIL = {
    "faixa_margem_alvo": {"min": 0.08, "max": 0.10},
    "faixa_margem_aceitavel": {"min": 0.06, "max": 0.12},
}


def test_verde_retorna_sem_sugestoes():
    """Margem VERDE → replan_suggestions vazia, sem erro."""
    canonical = _canonical(resultado=_resultado(0.09, "VERDE"))
    result = run_assessor_replanejamento(canonical, {}, _PERFIL)

    assert not result.has_errors
    secao = result.canonical.replan_suggestions
    assert secao is not None
    assert secao.status_gatilho == "VERDE"
    assert secao.sugestoes == []
    assert secao.sugestao_prioritaria is None


def test_amarelo_gera_sugestao():
    """Margem AMARELO → ao menos 1 sugestão gerada."""
    canonical = _canonical(resultado=_resultado(0.07, "AMARELO"))
    result = run_assessor_replanejamento(canonical, {}, _PERFIL)

    assert not result.has_errors
    secao = result.canonical.replan_suggestions
    assert secao.status_gatilho == "AMARELO"
    assert secao.delta_margem_necessario == pytest.approx(0.08 - 0.07, abs=1e-5)
    assert len(secao.sugestoes) >= 1
    assert secao.sugestao_prioritaria is not None


def test_vermelho_gera_sugestoes_com_conflitos():
    """Margem VERMELHO + conflitos → sugestão de pool e de cronograma."""
    conflito = ConflitoPico(
        recurso_id="pool-esc",
        tipo_nome="Escavadeira",
        periodo_inicio=date(2026, 3, 1),
        periodo_termino=date(2026, 5, 31),
        quantidade_disponivel=1,
        quantidade_necessaria=2.0,
        excedente=1.0,
        atividades_conflitantes=["atv-001"],
        recomendacoes=["BUY: adquirir escavadeira adicional"],
    )
    canonical = _canonical(
        resultado=_resultado(0.03, "VERMELHO"),
        conflitos_pico=[conflito],
    )
    result = run_assessor_replanejamento(canonical, {}, _PERFIL)

    assert not result.has_errors
    secao = result.canonical.replan_suggestions
    tipos = {s.tipo for s in secao.sugestoes}
    checkpoints = {s.checkpoint_skill for s in secao.sugestoes}
    assert "RECURSOS" in tipos
    assert "03-catalogo-de-recursos" in checkpoints


def test_val_replan_01_preenchido_em_amarelo():
    """VAL-REPLAN-01 status OK quando sugestões geradas."""
    canonical = _canonical(resultado=_resultado(0.07, "AMARELO"))
    result = run_assessor_replanejamento(canonical, {}, _PERFIL)
    val = next(v for v in result.validacoes if v.codigo == "VAL-REPLAN-01")
    assert val.status == "OK"


def test_val_replan_02_checkpoints_validos():
    """VAL-REPLAN-02: nenhuma sugestão com checkpoint inválido."""
    canonical = _canonical(resultado=_resultado(0.05, "VERMELHO"))
    result = run_assessor_replanejamento(canonical, {}, _PERFIL)
    val = next(v for v in result.validacoes if v.codigo == "VAL-REPLAN-02")
    assert val.status == "OK"


def test_indiretos_altos_geram_sugestao_cronograma():
    """Ratio indiretos > 30% → sugestão de cronograma REPLAN-003."""
    resultado_base = _resultado(0.07, "AMARELO")
    # Indiretos = 35% do custo total
    custo_total = resultado_base.custo.total
    indireto = Indireto(
        categoria="ADM",
        descricao="ADM alta",
        custo_total=custo_total * 0.35,
    )
    canonical = _canonical(
        resultado=resultado_base,
        indiretos=[indireto],
    )
    result = run_assessor_replanejamento(canonical, {}, _PERFIL)
    secao = result.canonical.replan_suggestions
    ids = {s.id for s in secao.sugestoes}
    assert "REPLAN-003" in ids


def test_usa_resultado_reconciliado_quando_disponivel():
    """Se resultado_reconciliado existe, usa seus campos em vez do resultado base."""
    recon = ResultadoReconciliado(
        delta_custo_total=50_000.0,
        venda_total_com_bdi=1_000_000.0,
        custo_total_reconciliado=970_000.0,
        margem_reconciliada_pct=0.03,
        status_margem_reconciliado="VERMELHO",
    )
    canonical = _canonical(
        resultado=_resultado(0.09, "VERDE"),  # base verde
        resultado_reconciliado=recon,  # reconciliado vermelho
    )
    result = run_assessor_replanejamento(canonical, {}, _PERFIL)
    secao = result.canonical.replan_suggestions
    # Deve usar o status reconciliado (VERMELHO), não o base (VERDE)
    assert secao.status_gatilho == "VERMELHO"
    assert len(secao.sugestoes) >= 1


def test_precondicao_sem_resultado():
    """Sem resultado → ERRO de pré-condição."""
    canonical = _canonical()
    result = run_assessor_replanejamento(canonical, {}, _PERFIL)
    assert result.has_errors
    assert any(v.codigo == "VAL-REPLAN-PRECONDICAO" for v in result.validacoes)
