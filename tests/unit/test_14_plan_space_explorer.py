"""Testes da skill 14 — Plan Space Explorer (ADR-021)."""

from datetime import UTC, date, datetime

from concilium.application.skills import load_skill_stage

# NEP-041 F2: estágio explorador da skill unificada 13-replanejamento-e-cenarios
run_explorador_cenarios = load_skill_stage("13-replanejamento-e-cenarios", "_explorador", "run_explorador_cenarios")
from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    CustoTotal,
    Indireto,
    LeverEquilibrio,
    Meta,
    PontoEquilibrio,
    Projeto,
    RegimeTrabalho,
    Resultado,
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


def _pe_com_levers(item_id: str, venda_cpu: float, levers: list[LeverEquilibrio]) -> PontoEquilibrio:
    """Cria um PontoEquilibrio com levers reais (ADR-082) para testes do PlanSpace."""
    return PontoEquilibrio(
        item_id=item_id,
        custo_fixo_equipe=venda_cpu * 0.8,
        custo_venda_cpu=venda_cpu,
        delta=venda_cpu * 0.05,
        delta_pct=0.05,
        status_validacao="OK",
        levers_equilibrio=levers,
    )


def test_precondicao_sem_resultado():
    """Sem resultado → ERRO de pré-condição."""
    c = _canonical()
    result = run_explorador_cenarios(c, {}, _PERFIL)
    assert result.has_errors
    assert any(v.codigo == "VAL-PSE-PRECONDICAO" for v in result.validacoes)


def test_verde_com_pe_levers_retorna_oportunidades():
    """VERDE com PE levers reais (ADR-082) → plan_space_result com oportunidades."""
    lever = LeverEquilibrio(
        id="fechar_gap_escala",
        tipo="custo",
        descricao="Serializar cronograma",
        delta_margin=50_000.0,
        delta_margin_pct=0.05,
        viavel=True,
    )
    pe = _pe_com_levers("eap-1", 1_000_000.0, [lever])
    c = _canonical(resultado=_resultado(0.09, "VERDE"), ponto_equilibrio=[pe])
    result = run_explorador_cenarios(c, {}, _PERFIL)
    assert not result.has_errors
    psr = result.canonical.plan_space_result
    assert psr is not None
    assert psr.status_entrada == "VERDE"
    assert psr.repair_path is None
    # Com PE lever real, deve ter ao menos 1 oportunidade (SERIALIZAR_CRONOGRAMA)
    assert len(psr.oportunidades) >= 1
    tipos = {o.lever.tipo for o in psr.oportunidades}
    assert "SERIALIZAR_CRONOGRAMA" in tipos


def test_verde_sem_pe_levers_sem_oportunidades():
    """VERDE sem PE levers e sem indiretos → sem oportunidades (honesto: sem dados = sem sugestões)."""
    c = _canonical(resultado=_resultado(0.09, "VERDE"))
    result = run_explorador_cenarios(c, {}, _PERFIL)
    assert not result.has_errors
    psr = result.canonical.plan_space_result
    assert psr is not None
    assert psr.status_entrada == "VERDE"
    assert psr.repair_path is None


def test_amarelo_com_pe_levers_gera_repair_path():
    """AMARELO + PE levers reais → repair_path com levers ADR-082."""
    lever_escala = LeverEquilibrio(
        id="fechar_gap_escala",
        tipo="custo",
        descricao="Serializar",
        delta_margin=30_000.0,
        delta_margin_pct=0.03,
        viavel=True,
    )
    lever_bdi = LeverEquilibrio(
        id="revisao_bdi_minima",
        tipo="preco",
        descricao="Recalibrar PU",
        delta_margin=20_000.0,
        delta_margin_pct=0.02,
        viavel=True,
    )
    pe = _pe_com_levers("eap-1", 1_000_000.0, [lever_escala, lever_bdi])
    c = _canonical(resultado=_resultado(0.07, "AMARELO"), ponto_equilibrio=[pe])
    result = run_explorador_cenarios(c, {}, _PERFIL)
    assert not result.has_errors
    psr = result.canonical.plan_space_result
    assert psr.status_entrada == "AMARELO"
    assert psr.repair_path is not None
    assert len(psr.repair_path.passos) >= 1
    tipos = {p.lever.tipo for p in psr.repair_path.passos}
    assert tipos & {"SERIALIZAR_CRONOGRAMA", "RECALIBRAR_PU"}


def test_repair_com_levers_pool_e_praticabilidade():
    """VERMELHO + PE levers pool/praticabilidade → tipos corretos no repair path."""
    levers = [
        LeverEquilibrio(
            id="fechar_gap_pool",
            tipo="custo",
            descricao="Pool",
            delta_margin=80_000.0,
            delta_margin_pct=0.08,
            viavel=True,
        ),
        LeverEquilibrio(
            id="fechar_gap_praticabilidade",
            tipo="custo",
            descricao="Prat.",
            delta_margin=20_000.0,
            delta_margin_pct=0.02,
            viavel=True,
        ),
    ]
    pe = _pe_com_levers("eap-1", 1_000_000.0, levers)
    c = _canonical(resultado=_resultado(0.04, "VERMELHO"), ponto_equilibrio=[pe])
    result = run_explorador_cenarios(c, {}, _PERFIL)
    psr = result.canonical.plan_space_result
    assert psr.status_entrada == "VERMELHO"
    tipos = {p.lever.tipo for p in psr.repair_path.passos}
    assert tipos & {"OTIMIZAR_POOL", "MELHORAR_PRATICABILIDADE"}


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
    """Se soma dos PE levers ≥ gap necessário, repair deve ser viável."""
    # Margem entrada = 4%, alvo = 8% → gap = 4 p.p. = 0.04
    # PE lever com delta_margin_pct = 0.10 (10%) resolve sozinho
    lever = LeverEquilibrio(
        id="fechar_gap_escala",
        tipo="custo",
        descricao="Serializar",
        delta_margin=100_000.0,
        delta_margin_pct=0.10,
        viavel=True,
    )
    pe = _pe_com_levers("eap-1", 1_000_000.0, [lever])
    c = _canonical(resultado=_resultado(0.04, "VERMELHO"), ponto_equilibrio=[pe])
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
