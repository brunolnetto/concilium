"""Testes da skill 14 — Plan Space Explorer (ADR-021)."""

from datetime import UTC, date, datetime

from concilium.application.skills import run_explorador_cenarios
from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    CustoTotal,
    Indireto,
    Meta,
    Projeto,
    RegimeTrabalho,
    Resultado,
    ResultadoReconciliado,
    ValidacaoItem,
    Venda,
)

_PERFIL = {
    "faixa_margem_alvo": {"min": 0.08, "max": 0.10},
    "faixa_margem_aceitavel": {"min": 0.06, "max": 0.12},
}


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


def _canonical(**kwargs):
    base = dict(meta=_meta(), projeto=_projeto())
    base.update(kwargs)
    return CanonicalModel(**base)


def test_precondicao_sem_resultado():
    """Sem resultado → ERRO de pré-condição."""
    c = _canonical()
    result = run_explorador_cenarios(c, {}, _PERFIL)
    assert result.has_errors
    assert any(v.codigo == "VAL-PSE-PRECONDICAO" for v in result.validacoes)


def test_verde_sem_conflitos_retorna_oportunidades():
    """VERDE sem conflitos → plan_space_result preenchido, repair_path None."""
    c = _canonical(resultado=_resultado(0.09, "VERDE"))
    result = run_explorador_cenarios(c, {}, _PERFIL)
    assert not result.has_errors
    psr = result.canonical.plan_space_result
    assert psr is not None
    assert psr.status_entrada == "VERDE"
    assert psr.repair_path is None
    # Deve ter ao menos REVIEW_BDI como oportunidade
    assert len(psr.oportunidades) >= 1


def test_amarelo_gera_repair_path():
    """AMARELO → repair_path populado com ao menos 1 passo."""
    c = _canonical(resultado=_resultado(0.07, "AMARELO"))
    result = run_explorador_cenarios(c, {}, _PERFIL)
    assert not result.has_errors
    psr = result.canonical.plan_space_result
    assert psr.status_entrada == "AMARELO"
    assert psr.repair_path is not None
    assert len(psr.repair_path.passos) >= 1


def test_repair_com_expand_pool():
    """VERMELHO + conflito BUY + reconciliado → EXPAND_POOL no repair path."""
    recon = ResultadoReconciliado(
        delta_custo_total=150_000.0,
        venda_total_com_bdi=1_000_000.0,
        custo_total_reconciliado=960_000.0,
        margem_reconciliada_pct=0.04,
        status_margem_reconciliado="VERMELHO",
        itens_aquisicao=[],
    )
    c = _canonical(
        resultado=_resultado(0.09, "VERDE"),  # base verde
        resultado_reconciliado=recon,  # reconciliado vermelho
    )
    result = run_explorador_cenarios(c, {}, _PERFIL)
    psr = result.canonical.plan_space_result
    assert psr.status_entrada == "VERMELHO"
    tipos = {p.lever.tipo for p in psr.repair_path.passos}
    assert "EXPAND_POOL" in tipos


def test_repair_com_indiretos_gera_reduce_duration():
    """AMARELO + indiretos altos → REDUCE_DURATION no repair path."""
    res = _resultado(0.07, "AMARELO")
    custo_total = res.custo.total
    indireto = Indireto(categoria="ADM", descricao="ADM", custo_total=custo_total * 0.30)
    c = _canonical(resultado=res, indiretos=[indireto])
    result = run_explorador_cenarios(c, {}, _PERFIL)
    psr = result.canonical.plan_space_result
    tipos = {p.lever.tipo for p in psr.repair_path.passos}
    assert "REDUCE_DURATION" in tipos


def test_repair_viavel_delta_suficiente():
    """Se delta total de levers >= delta necessário, repair deve ser viável."""
    recon = ResultadoReconciliado(
        delta_custo_total=500_000.0,  # grande delta → EXPAND_POOL resolve sozinho
        venda_total_com_bdi=1_000_000.0,
        custo_total_reconciliado=960_000.0,
        margem_reconciliada_pct=0.04,
        status_margem_reconciliado="VERMELHO",
        itens_aquisicao=[],
    )
    c = _canonical(resultado=_resultado(0.09, "VERDE"), resultado_reconciliado=recon)
    result = run_explorador_cenarios(c, {}, _PERFIL)
    psr = result.canonical.plan_space_result
    assert psr.repair_path.viavel is True
    assert psr.repair_path.margem_projetada >= 0.08


def test_verde_oportunidades_ordenadas_por_ganho():
    """Oportunidades VERDE ordenadas por margem_adicional_estimada DESC."""
    res = _resultado(0.09, "VERDE")
    custo_total = res.custo.total
    indireto = Indireto(categoria="ADM", descricao="ADM", custo_total=custo_total * 0.25)
    c = _canonical(resultado=res, indiretos=[indireto])
    result = run_explorador_cenarios(c, {}, _PERFIL)
    psr = result.canonical.plan_space_result
    gains = [o.margem_adicional_estimada for o in psr.oportunidades]
    assert gains == sorted(gains, reverse=True)


def test_val_pse_01_sempre_ok():
    """VAL-PSE-01 deve ser OK quando resultado disponível."""
    c = _canonical(resultado=_resultado(0.09, "VERDE"))
    result = run_explorador_cenarios(c, {}, _PERFIL)
    val = next(v for v in result.validacoes if v.codigo == "VAL-PSE-01")
    assert val.status == "OK"
