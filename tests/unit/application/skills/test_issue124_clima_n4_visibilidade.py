"""Issue #124 — visibilidade do gap climático diagnosticado (N3) nunca cobrado em N4.

Na bridge N1→N2→N3→N4 (`_bridge.py`), `gap_praticabilidade_abs` entra em N3 mas nunca
em N4 (custo operacional real) — decisão arquitetural (ADR-148 D2-bis / ADR-082-cons),
não um bug. Este módulo NÃO altera nenhum cálculo de custo/duração; só valida que o
valor é exposto como campo de 1ª classe (`Resultado.limitacao_clima_n4`) + mensagem
explicativa + `ValidacaoItem` INFO na bridge.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    EapItem,
    EquipamentoEquipeDireta,
    EquipeDireta,
    FuncaoEquipeDireta,
    LimitacaoClimaN4,
    Meta,
    PontoEquilibrio,
    Projeto,
    RegimeTrabalho,
    Resultado,
)


def _load_bridge_module():
    return importlib.import_module(
        "concilium.application.skills.manifests.06-resultado-financeiro._consolidacao._skill_helpers._bridge"
    )


def _load_skill_module():
    return importlib.import_module(
        "concilium.application.skills.manifests.06-resultado-financeiro._consolidacao.skill"
    )


# ── LimitacaoClimaN4 (modelo de domínio) ─────────────────────────────────────


class TestLimitacaoClimaN4Model:
    def test_defaults(self):
        lim = LimitacaoClimaN4()
        assert lim.gap_praticabilidade_abs == 0.0
        assert lim.cobrado_no_custo_operacional is False
        assert "N4" in lim.mensagem
        assert "N3" in lim.mensagem

    def test_mensagem_referencia_adrs_e_issue(self):
        lim = LimitacaoClimaN4(gap_praticabilidade_abs=5_000.0)
        assert "ADR-148" in lim.mensagem
        assert "ADR-082-cons" in lim.mensagem
        assert "#124" in lim.mensagem

    def test_extra_ignore(self):
        lim = LimitacaoClimaN4.model_validate({"gap_praticabilidade_abs": 10.0, "campo_desconhecido": "x"})
        assert lim.gap_praticabilidade_abs == 10.0
        assert not hasattr(lim, "campo_desconhecido")

    def test_resultado_tem_campo_default_none(self):
        res = Resultado(
            venda={"total_sem_bdi": 0.0, "total_com_bdi": 0.0},
            custo={"direto_equipes": 0.0, "total": 0.0},
            resultado_financeiro=0.0,
            margem_pct=0.0,
            status_margem="VERDE",
            validacoes=[],
        )
        assert res.limitacao_clima_n4 is None

    def test_resultado_aceita_limitacao(self):
        res = Resultado(
            venda={"total_sem_bdi": 0.0, "total_com_bdi": 0.0},
            custo={"direto_equipes": 0.0, "total": 0.0},
            resultado_financeiro=0.0,
            margem_pct=0.0,
            status_margem="VERDE",
            validacoes=[],
            limitacao_clima_n4=LimitacaoClimaN4(gap_praticabilidade_abs=1_234.5),
        )
        assert res.limitacao_clima_n4.gap_praticabilidade_abs == pytest.approx(1_234.5)


# ── _bridge.py — helpers unitários ───────────────────────────────────────────


class TestBridgeBuildLimitacaoClimaN4:
    def test_gap_zero_retorna_none(self):
        mod = _load_bridge_module()
        assert mod._bridge_build_limitacao_clima_n4(0.0) is None

    def test_gap_negativo_retorna_none(self):
        mod = _load_bridge_module()
        assert mod._bridge_build_limitacao_clima_n4(-100.0) is None

    def test_gap_positivo_retorna_objeto(self):
        mod = _load_bridge_module()
        lim = mod._bridge_build_limitacao_clima_n4(1_000.456)
        assert lim is not None
        assert lim.gap_praticabilidade_abs == pytest.approx(1_000.46)
        assert lim.cobrado_no_custo_operacional is False


class TestBridgeAppendClimaN4Validacao:
    def test_none_nao_adiciona_nada(self):
        mod = _load_bridge_module()
        validacoes: list = []
        mod._bridge_append_clima_n4_validacao(validacoes, None)
        assert validacoes == []

    def test_presente_adiciona_info(self):
        mod = _load_bridge_module()
        validacoes: list = []
        lim = mod._bridge_build_limitacao_clima_n4(2_500.0)
        mod._bridge_append_clima_n4_validacao(validacoes, lim)
        assert len(validacoes) == 1
        item = validacoes[0]
        assert item.codigo == "VAL-BRIDGE-CLIMA-N4"
        assert item.status == "INFO"
        assert "2.500" in item.mensagem or "2,500" in item.mensagem or "2500" in item.mensagem


class TestBuildBridgeFromPe:
    def _pe(self, gap_prat: float) -> PontoEquilibrio:
        return PontoEquilibrio(
            item_id="i1",
            custo_fixo_equipe=100_000.0,
            custo_venda_cpu=120_000.0,
            delta=20_000.0,
            delta_pct=0.2,
            status_validacao="OK",
            gap_escala_abs=0.0,
            gap_praticabilidade_abs=gap_prat,
        )

    def test_retorna_tupla(self):
        mod = _load_bridge_module()
        validacoes: list = []
        result = mod._build_bridge_from_pe([self._pe(0.0)], 500_000.0, 400_000.0, {}, validacoes)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_sem_gap_climatico_segundo_elemento_none(self):
        mod = _load_bridge_module()
        validacoes: list = []
        bridge, limitacao = mod._build_bridge_from_pe([self._pe(0.0)], 500_000.0, 400_000.0, {}, validacoes)
        assert bridge is not None
        assert limitacao is None
        codigos = {v.codigo for v in validacoes}
        assert "VAL-BRIDGE-CLIMA-N4" not in codigos

    def test_com_gap_climatico_expoe_limitacao(self):
        mod = _load_bridge_module()
        validacoes: list = []
        bridge, limitacao = mod._build_bridge_from_pe([self._pe(8_000.0)], 500_000.0, 400_000.0, {}, validacoes)
        assert bridge is not None
        assert limitacao is not None
        # mesmo valor agregado que compõe N3 (desvio_clima_abs)
        assert limitacao.gap_praticabilidade_abs == pytest.approx(bridge["desvio_clima_abs"])
        assert limitacao.gap_praticabilidade_abs == pytest.approx(8_000.0)
        codigos_status = {v.codigo: v.status for v in validacoes}
        assert codigos_status.get("VAL-BRIDGE-CLIMA-N4") == "INFO"

    def test_soma_multiplos_itens(self):
        mod = _load_bridge_module()
        validacoes: list = []
        pe_items = [self._pe(1_000.0), self._pe(2_500.0), self._pe(0.0)]
        _, limitacao = mod._build_bridge_from_pe(pe_items, 500_000.0, 400_000.0, {}, validacoes)
        assert limitacao is not None
        assert limitacao.gap_praticabilidade_abs == pytest.approx(3_500.0)


# ── skill.py (run_consolidacao_financeira) — wiring completo ─────────────────


def _equipe_planejamento_minimos():
    from concilium.domain.models.canonical import (
        Planejamento,
        PrecoUnitarioCategoria,
        SubtotalCategorias,
        SubtotalSemBdiComBdi,
    )

    equipe = EquipeDireta(
        equipe_id="eq1",
        item_id="i1",
        cpu_id="CPU-X",
        nome="Equipe X",
        num_equipes_base=1,
        funcoes=[FuncaoEquipeDireta(funcao_id="F1", num_pessoas=1)],
        equipamentos=[EquipamentoEquipeDireta(equip_id="E1", num_unidades=1)],
        custo_mao_obra_mensal=5_000.0,
        custo_equipamentos_mensal=5_000.0,
        custo_combustivel_total_mensal=5_000.0,
        custo_fixo_mensal=10_000.0,
        permanencia_meses=1.0,
        custo_total=30_000.0,
    )
    plan = Planejamento(
        item_id="i1",
        cpu_id="CPU-X",
        quantitativo=100.0,
        preco_unitario=PrecoUnitarioCategoria(material=0, diesel=0, mao_obra=100, equipamentos=100, total=200),
        preco_unitario_com_bdi=PrecoUnitarioCategoria(material=0, diesel=0, mao_obra=115, equipamentos=115, total=230),
        subtotal=SubtotalSemBdiComBdi(
            sem_bdi=SubtotalCategorias(material=0, diesel=0, mao_obra=10_000, equipamentos=10_000, total=20_000),
            com_bdi=SubtotalCategorias(material=0, diesel=0, mao_obra=11_500, equipamentos=11_500, total=23_000),
        ),
    )
    return equipe, plan


def _canonical_minimo() -> CanonicalModel:
    meta = Meta(gerado_em=datetime.now(UTC), contexto_id="test")
    projeto = Projeto(
        id="p1",
        nome="Projeto 124",
        tipo_obra="terraplenagem",
        localizacao="BR",
        coordenadas=Coordenadas(lat=0, lng=0),
        regime_trabalho=RegimeTrabalho(dias_semana=6, horas_dia=8),
        data_inicio="2026-01-01",
        data_termino="2026-12-31",
        snapshot_catalogo_id="cat",
        snapshot_perfil_id="perf",
    )
    eap = [EapItem(item_id="i1", ordem=1, cpu_id="CPU-X", descricao="Item", unidade="m3", quantitativo=100.0)]
    equipe, plan = _equipe_planejamento_minimos()
    return CanonicalModel(meta=meta, projeto=projeto, eap=eap, equipes_diretas=[equipe], planejamento=[plan])


_PERFIL = {
    "limiar_ponto_equilibrio": 0.05,
    "faixa_margem_alvo": {"min": 0.08, "max": 0.10},
    "faixa_margem_aceitavel": {"min": 0.06, "max": 0.12},
}


class TestRunConsolidacaoFinanceiraSemGapClimatico:
    """Baseline: sem lesão climática, limitacao_clima_n4 permanece None (sem ruído)."""

    def test_limitacao_none_por_padrao(self):
        skill_mod = _load_skill_module()
        result = skill_mod.run_consolidacao_financeira(_canonical_minimo(), {}, _PERFIL)
        assert result.canonical.resultado is not None
        assert result.canonical.resultado.limitacao_clima_n4 is None
        codigos = {v.codigo for v in result.validacoes}
        assert "VAL-BRIDGE-CLIMA-N4" not in codigos


class TestRunConsolidacaoFinanceiraComGapClimatico:
    """Com gap_praticabilidade_abs > 0 (simulado via _build_ponto_equilibrio patcheado),
    o Resultado final expõe limitacao_clima_n4 e a bridge emite VAL-BRIDGE-CLIMA-N4."""

    def _pe_com_gap(self) -> PontoEquilibrio:
        return PontoEquilibrio(
            item_id="i1",
            custo_fixo_equipe=10_000.0,
            custo_venda_cpu=20_000.0,
            delta=10_000.0,
            delta_pct=1.0,
            status_validacao="OK",
            gap_escala_abs=0.0,
            gap_praticabilidade_abs=4_321.0,
            custo_operacional_real=30_000.0,
        )

    def test_limitacao_clima_n4_populada(self):
        skill_mod = _load_skill_module()
        pe_items = [self._pe_com_gap()]
        with patch.object(skill_mod, "_build_ponto_equilibrio", return_value=pe_items):
            result = skill_mod.run_consolidacao_financeira(_canonical_minimo(), {}, _PERFIL)

        res = result.canonical.resultado
        assert res is not None
        assert res.limitacao_clima_n4 is not None
        assert res.limitacao_clima_n4.gap_praticabilidade_abs == pytest.approx(4_321.0)
        assert res.limitacao_clima_n4.cobrado_no_custo_operacional is False

    def test_validacao_info_presente(self):
        skill_mod = _load_skill_module()
        pe_items = [self._pe_com_gap()]
        with patch.object(skill_mod, "_build_ponto_equilibrio", return_value=pe_items):
            result = skill_mod.run_consolidacao_financeira(_canonical_minimo(), {}, _PERFIL)

        info_items = [v for v in result.validacoes if v.codigo == "VAL-BRIDGE-CLIMA-N4"]
        assert len(info_items) == 1
        assert info_items[0].status == "INFO"

    def test_bridge_analysis_desvio_clima_abs_inalterado(self):
        """A visibilidade nova não altera o valor pré-existente de desvio_clima_abs na bridge."""
        skill_mod = _load_skill_module()
        pe_items = [self._pe_com_gap()]
        with patch.object(skill_mod, "_build_ponto_equilibrio", return_value=pe_items):
            result = skill_mod.run_consolidacao_financeira(_canonical_minimo(), {}, _PERFIL)

        bridge = result.canonical.bridge_analysis
        assert bridge is not None
        assert bridge["desvio_clima_abs"] == pytest.approx(4_321.0)
        assert bridge["desvio_clima_abs"] == pytest.approx(
            result.canonical.resultado.limitacao_clima_n4.gap_praticabilidade_abs
        )
