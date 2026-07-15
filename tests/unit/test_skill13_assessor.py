"""Tests for skill 13 _assessor — run_assessor_replanejamento.

Covers all branches in:
  - VAL-REPLAN-PRECONDICAO (resultado=None early return)
  - status VERDE (empty suggestions, history appended)
  - status AMARELO / VERMELHO with various combinations:
      - REPLAN-001 (pool) via BUY/HIRE recomendacoes
      - REPLAN-002 (equipes) via A+ CriticidadeProfile
      - REPLAN-003 (cronograma) via indiretos ratio >30%
      - REPLAN-005 (BDI) fallback when no other suggestions apply
  - resultado_reconciliado overrides margem_atual / status_gatilho
  - inputs['meta_margem_alvo'] overrides faixa_alvo min
  - perfil dict overrides faixa_margem_alvo / faixa_margem_aceitavel
  - sugestoes sorted by _score_sugestao so sugestao_prioritaria is highest-scored
  - VAL-REPLAN-02 ERRO when checkpoint_skill not in _VALID_CHECKPOINTS
"""

from datetime import UTC, date, datetime

import pytest

from concilium.application.skills import load_skill_stage

run_assessor_replanejamento = load_skill_stage(
    "08-replanejamento-e-cenarios", "_assessor", "run_assessor_replanejamento"
)

from concilium.domain.models.canonical import (  # noqa: E402
    CanonicalModel,
    ConflitoPico,
    CostCriticalityResult,
    CriticidadeProfile,
    CustoTotal,
    DimensaoCriticidade,
    Indireto,
    Meta,
    Projeto,
    Resultado,
    ResultadoReconciliado,
    ValidacaoItem,
    Venda,
)

pytestmark = [pytest.mark.slow]


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def _meta() -> Meta:
    return Meta(versao_schema="1.0.0", gerado_em=datetime.now(UTC), contexto_id="test-skill13")


def _projeto() -> Projeto:
    from concilium.domain.models.canonical import Coordenadas, RegimeTrabalho

    return Projeto(
        id="proj-skill13",
        nome="Projeto Skill13",
        tipo_obra="terraplenagem",
        localizacao="CE",
        coordenadas=Coordenadas(lat=-3.7, lng=-38.5),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
        snapshot_catalogo_id="cat-1",
        snapshot_perfil_id="perf-1",
    )


def _venda(total: float = 1_000_000.0) -> Venda:
    return Venda(
        total_sem_bdi=total * 0.8,
        total_com_bdi=total,
    )


def _custo_total(total: float) -> CustoTotal:
    return CustoTotal(
        direto_equipes=total * 0.7,
        indireto_adm=total * 0.075,
        indireto_top=total * 0.075,
        indireto_lab=total * 0.05,
        indireto_qsms=total * 0.05,
        indireto_mob=total * 0.05,
        total=total,
    )


def _resultado(margem: float, status: str) -> Resultado:
    venda = 1_000_000.0
    custo = round(venda * (1 - margem), 2)
    return Resultado(
        venda=_venda(venda),
        custo=_custo_total(custo),
        resultado_financeiro=round(venda - custo, 2),
        margem_pct=margem,
        status_margem=status,
        validacoes=[ValidacaoItem(codigo="VAL-POL-MARGEM", status="OK")],
    )


def _conflito_pico(tipo_nome: str, excedente: float = 1.0, recomendacoes: list[str] | None = None) -> ConflitoPico:
    return ConflitoPico(
        recurso_id=f"pool-{tipo_nome.lower()}",
        tipo_nome=tipo_nome,
        periodo_inicio=date(2026, 3, 1),
        periodo_termino=date(2026, 5, 31),
        quantidade_disponivel=1,
        quantidade_necessaria=1.0 + excedente,
        excedente=excedente,
        atividades_conflitantes=["atv-001"],
        recomendacoes=recomendacoes or ["BUY: adquirir adicional"],
    )


def _dimensao(valor: float = 0.5) -> DimensaoCriticidade:
    return DimensaoCriticidade(valor_raw=valor, rank=1, percentil=0.9)


def _criticidade_profile(atividade_id: str, classe: str = "A+") -> CriticidadeProfile:
    return CriticidadeProfile(
        atividade_id=atividade_id,
        custo=_dimensao(100_000.0),
        duracao=_dimensao(0.5),
        recurso=_dimensao(0.3),
        sensibilidade=_dimensao(0.8),
        pareto_frontier=True,
        rank_lexicografico=1,
        classe=classe,
        interpretacao="Atividade crítica de custo.",
    )


def _cost_criticality_result(classes: list[str] | None = None) -> CostCriticalityResult:
    if classes is None:
        classes = ["A+"]
    atividades = [_criticidade_profile(f"atv-{i:03d}", c) for i, c in enumerate(classes)]
    return CostCriticalityResult(
        atividades=atividades,
        n_pareto_frontier=sum(1 for c in classes if c == "A+"),
        n_atividades=len(classes),
    )


def _indireto(categoria: str = "ADM", custo_total: float = 300_000.0) -> Indireto:
    return Indireto(categoria=categoria, descricao=f"Indireto {categoria}", custo_total=custo_total)


def _canonical(**kwargs) -> CanonicalModel:
    base: dict = dict(meta=_meta(), projeto=_projeto())
    base.update(kwargs)
    return CanonicalModel(**base)


def _perfil() -> dict:
    """Return a fresh perfil dict each call to avoid mutation across tests.

    The source code does ``faixa_alvo["min"] = float(meta_override)`` which
    mutates the dict returned by ``perfil.get("faixa_margem_alvo", ...)``.
    Using a module-level constant would cause test pollution.
    """
    return {
        "faixa_margem_alvo": {"min": 0.08, "max": 0.10},
        "faixa_margem_aceitavel": {"min": 0.06, "max": 0.12},
    }


# Backward-compat alias used in some tests; prefer _perfil() for mutation safety.
_PERFIL = {
    "faixa_margem_alvo": {"min": 0.08, "max": 0.10},
    "faixa_margem_aceitavel": {"min": 0.06, "max": 0.12},
}


# ---------------------------------------------------------------------------
# 1. Pré-condição: resultado=None → ERRO VAL-REPLAN-PRECONDICAO, early return
# ---------------------------------------------------------------------------


class TestPrecondicao:
    def test_resultado_none_returns_error(self):
        """resultado=None → VAL-REPLAN-PRECONDICAO ERRO, early return."""
        canonical = _canonical()  # no resultado
        result = run_assessor_replanejamento(canonical, {}, None)

        assert result.has_errors
        codigos = [v.codigo for v in result.validacoes]
        assert "VAL-REPLAN-PRECONDICAO" in codigos
        err = next(v for v in result.validacoes if v.codigo == "VAL-REPLAN-PRECONDICAO")
        assert err.status == "ERRO"
        # No replan_suggestions set (still None) — early return
        assert result.canonical.replan_suggestions is None

    def test_resultado_none_no_suggestions(self):
        """With resultado=None the canonical returned still has no replan_suggestions."""
        canonical = _canonical()
        result = run_assessor_replanejamento(canonical, {})
        assert result.canonical.replan_suggestions is None


# ---------------------------------------------------------------------------
# 2. Status VERDE → empty ReplanSuggestions, VAL-REPLAN-01 OK, history appended
# ---------------------------------------------------------------------------


class TestVerde:
    def test_verde_empty_suggestions(self):
        """VERDE → sugestoes=[], sugestao_prioritaria=None."""
        canonical = _canonical(resultado=_resultado(0.09, "VERDE"))
        result = run_assessor_replanejamento(canonical, {}, _perfil())

        assert not result.has_errors
        secao = result.canonical.replan_suggestions
        assert secao is not None
        assert secao.status_gatilho == "VERDE"
        assert secao.sugestoes == []
        assert secao.sugestao_prioritaria is None
        assert secao.delta_margem_necessario == 0.0

    def test_verde_val_replan_01_ok(self):
        """VERDE → VAL-REPLAN-01 status OK."""
        canonical = _canonical(resultado=_resultado(0.09, "VERDE"))
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        val = next(v for v in result.validacoes if v.codigo == "VAL-REPLAN-01")
        assert val.status == "OK"
        assert "VERDE" in val.mensagem

    def test_verde_appends_to_replanning_history(self):
        """VERDE → history entry appended with status_gatilho='VERDE'."""
        canonical = _canonical(resultado=_resultado(0.09, "VERDE"))
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        history = result.canonical.replanning_history
        assert len(history) == 1
        entry = history[0]
        assert entry["status_gatilho"] == "VERDE"
        assert entry["n_sugestoes"] == 0
        assert entry["sugestao_prioritaria"] is None

    def test_verde_preserves_existing_history(self):
        """VERDE → existing history entries preserved, new one appended."""
        existing = [{"timestamp": "2026-01-01T00:00:00+00:00", "status_gatilho": "AMARELO"}]
        canonical = _canonical(resultado=_resultado(0.09, "VERDE"), replanning_history=existing)
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        history = result.canonical.replanning_history
        assert len(history) == 2
        assert history[0]["status_gatilho"] == "AMARELO"
        assert history[1]["status_gatilho"] == "VERDE"


# ---------------------------------------------------------------------------
# 3. REPLAN-001 (pool) — BUY/HIRE recomendacoes in conflitos_pico
# ---------------------------------------------------------------------------


class TestReplan001Pool:
    def test_amarelo_buy_hire_gera_replan001(self):
        """AMARELO + conflito BUY → REPLAN-001 RECURSOS suggestion."""
        conflito = _conflito_pico("Escavadeira", excedente=1.5, recomendacoes=["BUY: adquirir adicional"])
        canonical = _canonical(resultado=_resultado(0.07, "AMARELO"), conflitos_pico=[conflito])
        result = run_assessor_replanejamento(canonical, {}, _perfil())

        secao = result.canonical.replan_suggestions
        ids = {s.id for s in secao.sugestoes}
        assert "REPLAN-001" in ids

    def test_vermelho_hire_gera_replan001(self):
        """VERMELHO + HIRE in recomendacoes → REPLAN-001."""
        conflito = _conflito_pico("Motoniveladora", recomendacoes=["HIRE: contratar motoniveladora extra"])
        canonical = _canonical(resultado=_resultado(0.03, "VERMELHO"), conflitos_pico=[conflito])
        result = run_assessor_replanejamento(canonical, {}, _perfil())

        ids = {s.id for s in result.canonical.replan_suggestions.sugestoes}
        assert "REPLAN-001" in ids

    def test_replan001_parametros_incluem_tipo_nome(self):
        """REPLAN-001 parametros_sugeridos include pool.TipoNome.quantidade_total."""
        conflito = _conflito_pico("Trator", excedente=2.0, recomendacoes=["ADQUIRIR: trator adicional"])
        canonical = _canonical(resultado=_resultado(0.05, "VERMELHO"), conflitos_pico=[conflito])
        result = run_assessor_replanejamento(canonical, {}, _perfil())

        sugestao_001 = next(s for s in result.canonical.replan_suggestions.sugestoes if s.id == "REPLAN-001")
        params = sugestao_001.parametros_sugeridos
        assert any("Trator" in k for k in params.keys())

    def test_conflito_sem_buy_hire_nao_gera_replan001(self):
        """Conflito sem BUY/HIRE recomendacoes → sem REPLAN-001."""
        conflito = _conflito_pico("Caminhao", recomendacoes=["OTIMIZAR alocação", "reduzir demanda"])
        canonical = _canonical(resultado=_resultado(0.07, "AMARELO"), conflitos_pico=[conflito])
        result = run_assessor_replanejamento(canonical, {}, _perfil())

        ids = {s.id for s in result.canonical.replan_suggestions.sugestoes}
        assert "REPLAN-001" not in ids

    def test_multiplos_conflitos_buy_hire(self):
        """Multiple BUY conflicts → REPLAN-001 covers up to 3."""
        conflitos = [
            _conflito_pico("Escavadeira", recomendacoes=["BUY"]),
            _conflito_pico("Motoniveladora", recomendacoes=["HIRE"]),
            _conflito_pico("Trator", recomendacoes=["CONTRATAR"]),
            _conflito_pico("Compactador", recomendacoes=["AQUISIÇÃO adicional"]),
        ]
        canonical = _canonical(resultado=_resultado(0.03, "VERMELHO"), conflitos_pico=conflitos)
        result = run_assessor_replanejamento(canonical, {}, _perfil())

        sugestao_001 = next((s for s in result.canonical.replan_suggestions.sugestoes if s.id == "REPLAN-001"), None)
        assert sugestao_001 is not None
        # At most 3 params from _build_sugestao_pool (conflitos_com_aquisicao[:3])
        assert len(sugestao_001.parametros_sugeridos) <= 3


# ---------------------------------------------------------------------------
# 4. REPLAN-002 (equipes) — A+ atividades in cost_criticality_report
# ---------------------------------------------------------------------------


class TestReplan002Equipes:
    def test_a_plus_gera_replan002(self):
        """cost_criticality_report with A+ → REPLAN-002 EQUIPES suggestion."""
        ccr = _cost_criticality_result(classes=["A+", "A"])
        canonical = _canonical(resultado=_resultado(0.05, "VERMELHO"), cost_criticality_report=ccr)
        result = run_assessor_replanejamento(canonical, {}, _perfil())

        ids = {s.id for s in result.canonical.replan_suggestions.sugestoes}
        assert "REPLAN-002" in ids

    def test_no_a_plus_nao_gera_replan002(self):
        """cost_criticality_report with only A/B/C → sem REPLAN-002."""
        ccr = _cost_criticality_result(classes=["A", "B", "C"])
        canonical = _canonical(resultado=_resultado(0.07, "AMARELO"), cost_criticality_report=ccr)
        result = run_assessor_replanejamento(canonical, {}, _perfil())

        ids = {s.id for s in result.canonical.replan_suggestions.sugestoes}
        assert "REPLAN-002" not in ids

    def test_no_cost_criticality_report_nao_gera_replan002(self):
        """cost_criticality_report=None → sem REPLAN-002."""
        canonical = _canonical(resultado=_resultado(0.07, "AMARELO"))
        result = run_assessor_replanejamento(canonical, {}, _perfil())

        ids = {s.id for s in result.canonical.replan_suggestions.sugestoes}
        assert "REPLAN-002" not in ids

    def test_replan002_checkpoint(self):
        """REPLAN-002 must have checkpoint_skill='05-equipes-e-alocacao'."""
        ccr = _cost_criticality_result(classes=["A+"])
        canonical = _canonical(resultado=_resultado(0.04, "VERMELHO"), cost_criticality_report=ccr)
        result = run_assessor_replanejamento(canonical, {}, _perfil())

        sugestao = next(s for s in result.canonical.replan_suggestions.sugestoes if s.id == "REPLAN-002")
        assert sugestao.checkpoint_skill == "05-equipes-e-alocacao"
        assert sugestao.confianca == "BAIXA"

    def test_replan002_confianca_baixa_score_lower_than_media(self):
        """REPLAN-002 (BAIXA) should have lower score than REPLAN-001 (MEDIA) with same delta."""
        # Build canonical with both A+ and BUY conflicts so we get both suggestions
        ccr = _cost_criticality_result(classes=["A+"])
        conflito = _conflito_pico("Escavadeira", recomendacoes=["BUY"])
        canonical = _canonical(
            resultado=_resultado(0.04, "VERMELHO"),
            cost_criticality_report=ccr,
            conflitos_pico=[conflito],
        )
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        sugestoes = result.canonical.replan_suggestions.sugestoes
        # REPLAN-001 has MEDIA confidence (0.7), REPLAN-002 has BAIXA (0.4)
        # Both get same delta fraction, so REPLAN-001 score > REPLAN-002 score
        ids_ordered = [s.id for s in sugestoes]
        if "REPLAN-001" in ids_ordered and "REPLAN-002" in ids_ordered:
            idx_001 = ids_ordered.index("REPLAN-001")
            idx_002 = ids_ordered.index("REPLAN-002")
            # After sorting by score descending, REPLAN-001 should appear before REPLAN-002
            assert idx_001 < idx_002


# ---------------------------------------------------------------------------
# 5. REPLAN-003 (cronograma) — indiretos ratio >30% of custo_total
# ---------------------------------------------------------------------------


class TestReplan003Cronograma:
    def test_indiretos_acima_30pct_gera_replan003(self):
        """Indiretos > 30% of custo_total → REPLAN-003 CRONOGRAMA suggestion."""
        resultado = _resultado(0.07, "AMARELO")
        custo_total = resultado.custo.total  # 930_000
        indireto = _indireto("ADM", custo_total=custo_total * 0.35)  # 35% > 30%
        canonical = _canonical(resultado=resultado, indiretos=[indireto])
        result = run_assessor_replanejamento(canonical, {}, _perfil())

        ids = {s.id for s in result.canonical.replan_suggestions.sugestoes}
        assert "REPLAN-003" in ids

    def test_indiretos_abaixo_30pct_nao_gera_replan003(self):
        """Indiretos <= 30% of custo_total → sem REPLAN-003."""
        resultado = _resultado(0.07, "AMARELO")
        custo_total = resultado.custo.total
        indireto = _indireto("TOP", custo_total=custo_total * 0.20)  # 20% <= 30%
        canonical = _canonical(resultado=resultado, indiretos=[indireto])
        result = run_assessor_replanejamento(canonical, {}, _perfil())

        ids = {s.id for s in result.canonical.replan_suggestions.sugestoes}
        assert "REPLAN-003" not in ids

    def test_indiretos_vazios_nao_gera_replan003(self):
        """No indiretos → sem REPLAN-003."""
        canonical = _canonical(resultado=_resultado(0.05, "VERMELHO"), indiretos=[])
        result = run_assessor_replanejamento(canonical, {}, _perfil())

        ids = {s.id for s in result.canonical.replan_suggestions.sugestoes}
        assert "REPLAN-003" not in ids

    def test_replan003_checkpoint_cronograma(self):
        """REPLAN-003 checkpoint_skill must be '04-cronograma'."""
        resultado = _resultado(0.07, "AMARELO")
        custo_total = resultado.custo.total
        indireto = _indireto("QSMS", custo_total=custo_total * 0.40)
        canonical = _canonical(resultado=resultado, indiretos=[indireto])
        result = run_assessor_replanejamento(canonical, {}, _perfil())

        sugestao = next((s for s in result.canonical.replan_suggestions.sugestoes if s.id == "REPLAN-003"), None)
        assert sugestao is not None
        assert sugestao.checkpoint_skill == "04-cronograma"

    def test_multiplos_indiretos_somados(self):
        """Multiple Indireto objects are summed to compute ratio."""
        resultado = _resultado(0.07, "AMARELO")
        custo_total = resultado.custo.total
        # Each contributes 15%, together 30%, edge case: should not trigger (>30 strictly)
        ind1 = _indireto("ADM", custo_total=custo_total * 0.15)
        ind2 = _indireto("TOP", custo_total=custo_total * 0.16)  # 31% total
        canonical = _canonical(resultado=resultado, indiretos=[ind1, ind2])
        result = run_assessor_replanejamento(canonical, {}, _perfil())

        ids = {s.id for s in result.canonical.replan_suggestions.sugestoes}
        assert "REPLAN-003" in ids


# ---------------------------------------------------------------------------
# 6. REPLAN-005 (BDI) fallback — no pool/equipes/cronograma suggestions
# ---------------------------------------------------------------------------


class TestReplan005BdiFallback:
    def test_amarelo_sem_dados_extras_cai_em_replan005(self):
        """AMARELO without conflicts, CCR, or high indiretos → REPLAN-005 BDI fallback."""
        canonical = _canonical(resultado=_resultado(0.07, "AMARELO"))
        result = run_assessor_replanejamento(canonical, {}, _perfil())

        ids = {s.id for s in result.canonical.replan_suggestions.sugestoes}
        assert "REPLAN-005" in ids

    def test_vermelho_sem_dados_extras_cai_em_replan005(self):
        """VERMELHO without conflicts, CCR, or high indiretos → REPLAN-005 BDI fallback."""
        canonical = _canonical(resultado=_resultado(0.02, "VERMELHO"))
        result = run_assessor_replanejamento(canonical, {}, _perfil())

        ids = {s.id for s in result.canonical.replan_suggestions.sugestoes}
        assert "REPLAN-005" in ids

    def test_replan005_checkpoint_custos_indiretos(self):
        """REPLAN-005 checkpoint_skill must be '06-resultado-financeiro'."""
        canonical = _canonical(resultado=_resultado(0.07, "AMARELO"))
        result = run_assessor_replanejamento(canonical, {}, _perfil())

        sugestao = next(s for s in result.canonical.replan_suggestions.sugestoes if s.id == "REPLAN-005")
        assert sugestao.checkpoint_skill == "06-resultado-financeiro"
        assert sugestao.tipo == "BDI"
        assert sugestao.confianca == "BAIXA"

    def test_replan005_delta_positivo(self):
        """REPLAN-005 delta_margem_estimado must be positive."""
        canonical = _canonical(resultado=_resultado(0.04, "VERMELHO"))
        result = run_assessor_replanejamento(canonical, {}, _perfil())

        sugestao = next(s for s in result.canonical.replan_suggestions.sugestoes if s.id == "REPLAN-005")
        assert sugestao.delta_margem_estimado > 0


# ---------------------------------------------------------------------------
# 7. resultado_reconciliado overrides margem_atual and status_gatilho
# ---------------------------------------------------------------------------


class TestResultadoReconciliado:
    def test_reconciliado_verde_overrides_base_vermelho(self):
        """resultado_reconciliado VERDE overrides base VERMELHO."""
        recon = ResultadoReconciliado(
            margem_reconciliada_pct=0.09,
            status_margem_reconciliado="VERDE",
        )
        canonical = _canonical(
            resultado=_resultado(0.02, "VERMELHO"),
            resultado_reconciliado=recon,
        )
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        secao = result.canonical.replan_suggestions
        assert secao.status_gatilho == "VERDE"
        assert secao.sugestoes == []

    def test_reconciliado_vermelho_overrides_base_verde(self):
        """resultado_reconciliado VERMELHO overrides base VERDE."""
        recon = ResultadoReconciliado(
            margem_reconciliada_pct=0.03,
            status_margem_reconciliado="VERMELHO",
        )
        canonical = _canonical(
            resultado=_resultado(0.09, "VERDE"),
            resultado_reconciliado=recon,
        )
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        secao = result.canonical.replan_suggestions
        assert secao.status_gatilho == "VERMELHO"
        assert len(secao.sugestoes) >= 1

    def test_reconciliado_amarelo_overrides_base_verde(self):
        """resultado_reconciliado AMARELO overrides base VERDE and generates suggestions."""
        recon = ResultadoReconciliado(
            margem_reconciliada_pct=0.07,
            status_margem_reconciliado="AMARELO",
        )
        canonical = _canonical(
            resultado=_resultado(0.09, "VERDE"),
            resultado_reconciliado=recon,
        )
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        secao = result.canonical.replan_suggestions
        assert secao.status_gatilho == "AMARELO"

    def test_reconciliado_margem_used_for_delta(self):
        """delta_margem_necessario uses reconciliado's margem, not base."""
        recon = ResultadoReconciliado(
            margem_reconciliada_pct=0.05,  # Needs 0.08 - 0.05 = 0.03 delta for AMARELO
            status_margem_reconciliado="AMARELO",
        )
        canonical = _canonical(
            resultado=_resultado(0.09, "VERDE"),
            resultado_reconciliado=recon,
        )
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        secao = result.canonical.replan_suggestions
        assert secao.delta_margem_necessario == pytest.approx(0.08 - 0.05, abs=1e-5)


# ---------------------------------------------------------------------------
# 8. inputs['meta_margem_alvo'] overrides faixa_alvo min
# ---------------------------------------------------------------------------


class TestMetaMargemAlvoOverride:
    def test_meta_margem_alvo_increases_delta_in_amarelo(self):
        """inputs['meta_margem_alvo']=0.12 → delta = 0.12 - margem for AMARELO."""
        canonical = _canonical(resultado=_resultado(0.07, "AMARELO"))
        result = run_assessor_replanejamento(canonical, {"meta_margem_alvo": 0.12}, _perfil())
        secao = result.canonical.replan_suggestions
        assert secao.delta_margem_necessario == pytest.approx(0.12 - 0.07, abs=1e-5)

    def test_meta_margem_alvo_as_string_parsed(self):
        """inputs['meta_margem_alvo'] as string is converted via float()."""
        canonical = _canonical(resultado=_resultado(0.07, "AMARELO"))
        result = run_assessor_replanejamento(canonical, {"meta_margem_alvo": "0.10"}, _perfil())
        secao = result.canonical.replan_suggestions
        assert secao.delta_margem_necessario == pytest.approx(0.10 - 0.07, abs=1e-5)

    def test_meta_margem_alvo_not_in_inputs_uses_perfil(self):
        """No meta_margem_alvo in inputs → uses perfil faixa_alvo min=0.08."""
        canonical = _canonical(resultado=_resultado(0.07, "AMARELO"))
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        secao = result.canonical.replan_suggestions
        assert secao.delta_margem_necessario == pytest.approx(0.08 - 0.07, abs=1e-5)


# ---------------------------------------------------------------------------
# 9. perfil dict overrides faixa_margem_alvo / faixa_margem_aceitavel
# ---------------------------------------------------------------------------


class TestPerfilOverride:
    def test_perfil_none_uses_defaults(self):
        """perfil=None → uses hardcoded defaults (alvo min=0.08, aceitavel min=0.06)."""
        canonical = _canonical(resultado=_resultado(0.07, "AMARELO"))
        result = run_assessor_replanejamento(canonical, {}, None)
        secao = result.canonical.replan_suggestions
        assert secao.delta_margem_necessario == pytest.approx(0.08 - 0.07, abs=1e-5)

    def test_perfil_overrides_faixa_alvo(self):
        """Custom perfil faixa_margem_alvo min=0.15 → delta uses 0.15 for AMARELO."""
        custom_perfil = {
            "faixa_margem_alvo": {"min": 0.15, "max": 0.20},
            "faixa_margem_aceitavel": {"min": 0.10, "max": 0.25},
        }
        canonical = _canonical(resultado=_resultado(0.07, "AMARELO"))
        result = run_assessor_replanejamento(canonical, {}, custom_perfil)
        secao = result.canonical.replan_suggestions
        assert secao.delta_margem_necessario == pytest.approx(0.15 - 0.07, abs=1e-5)

    def test_perfil_overrides_faixa_aceitavel_for_vermelho(self):
        """Custom perfil faixa_margem_aceitavel min=0.04 → delta uses 0.04 for VERMELHO."""
        custom_perfil = {
            "faixa_margem_alvo": {"min": 0.08, "max": 0.10},
            "faixa_margem_aceitavel": {"min": 0.04, "max": 0.12},
        }
        canonical = _canonical(resultado=_resultado(0.02, "VERMELHO"))
        result = run_assessor_replanejamento(canonical, {}, custom_perfil)
        secao = result.canonical.replan_suggestions
        assert secao.delta_margem_necessario == pytest.approx(0.04 - 0.02, abs=1e-5)

    def test_perfil_empty_uses_defaults(self):
        """Empty perfil dict → uses hardcoded defaults via .get()."""
        canonical = _canonical(resultado=_resultado(0.07, "AMARELO"))
        result = run_assessor_replanejamento(canonical, {}, {})
        secao = result.canonical.replan_suggestions
        assert secao.delta_margem_necessario == pytest.approx(0.08 - 0.07, abs=1e-5)


# ---------------------------------------------------------------------------
# 10. Sorting by _score_sugestao — sugestao_prioritaria is highest-scored
# ---------------------------------------------------------------------------


class TestScoringSorting:
    def test_sugestao_prioritaria_is_highest_score(self):
        """sugestao_prioritaria is the id of the suggestion with highest _score."""
        # REPLAN-001 has MEDIA (0.7) confidence, REPLAN-003 has MEDIA (0.7) as well.
        # REPLAN-002 has BAIXA (0.4) confidence.
        # We can verify the list is sorted descending by checking the first element.
        resultado = _resultado(0.05, "VERMELHO")
        custo_total = resultado.custo.total
        conflito = _conflito_pico("Escavadeira", excedente=2.0, recomendacoes=["BUY"])
        ccr = _cost_criticality_result(classes=["A+"])
        indireto = _indireto("ADM", custo_total=custo_total * 0.40)  # >30%

        canonical = _canonical(
            resultado=resultado,
            conflitos_pico=[conflito],
            cost_criticality_report=ccr,
            indiretos=[indireto],
        )
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        secao = result.canonical.replan_suggestions

        # Verify sugestao_prioritaria matches first in sorted list
        assert secao.sugestao_prioritaria == secao.sugestoes[0].id

    def test_sugestoes_sorted_descending_by_score(self):
        """sugestoes list is sorted descending by delta * conf_weight."""
        resultado = _resultado(0.04, "VERMELHO")
        custo_total = resultado.custo.total
        conflito = _conflito_pico("Caminhao", recomendacoes=["BUY"])
        ccr = _cost_criticality_result(classes=["A+"])
        indireto = _indireto("TOP", custo_total=custo_total * 0.35)

        canonical = _canonical(
            resultado=resultado,
            conflitos_pico=[conflito],
            cost_criticality_report=ccr,
            indiretos=[indireto],
        )
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        sugestoes = result.canonical.replan_suggestions.sugestoes

        conf_weight = {"ALTA": 1.0, "MEDIA": 0.7, "BAIXA": 0.4}
        scores = [s.delta_margem_estimado * conf_weight[s.confianca] for s in sugestoes]
        assert scores == sorted(scores, reverse=True), "sugestoes devem estar em ordem decrescente de score"

    def test_replan005_is_prioritaria_when_only_suggestion(self):
        """When only REPLAN-005 exists, it must be sugestao_prioritaria."""
        canonical = _canonical(resultado=_resultado(0.07, "AMARELO"))
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        secao = result.canonical.replan_suggestions
        assert secao.sugestao_prioritaria == "REPLAN-005"


# ---------------------------------------------------------------------------
# 11. VAL-REPLAN-02 ERRO when checkpoint_skill not in _VALID_CHECKPOINTS
# ---------------------------------------------------------------------------


class TestValReplan02:
    def test_valid_checkpoints_return_ok(self):
        """All built-in suggestions use valid checkpoints → VAL-REPLAN-02 OK."""
        conflito = _conflito_pico("Trator", recomendacoes=["BUY"])
        canonical = _canonical(resultado=_resultado(0.04, "VERMELHO"), conflitos_pico=[conflito])
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        val = next(v for v in result.validacoes if v.codigo == "VAL-REPLAN-02")
        assert val.status == "OK"

    def test_val_replan_02_always_present(self):
        """VAL-REPLAN-02 validation is always present for non-VERDE status."""
        canonical = _canonical(resultado=_resultado(0.07, "AMARELO"))
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        codigos = [v.codigo for v in result.validacoes]
        assert "VAL-REPLAN-02" in codigos

    def test_val_replan_01_ok_when_suggestions_generated(self):
        """VAL-REPLAN-01 status OK when suggestions exist."""
        canonical = _canonical(resultado=_resultado(0.07, "AMARELO"))
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        val = next(v for v in result.validacoes if v.codigo == "VAL-REPLAN-01")
        assert val.status == "OK"
        assert "AMARELO" in val.mensagem or "sugestão" in val.mensagem.lower()


# ---------------------------------------------------------------------------
# 12. History entry structure (ADR-056 §T5)
# ---------------------------------------------------------------------------


class TestHistoryEntry:
    def test_amarelo_history_entry_structure(self):
        """AMARELO run appends history entry with correct keys and values."""
        canonical = _canonical(resultado=_resultado(0.07, "AMARELO"))
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        history = result.canonical.replanning_history
        assert len(history) == 1
        entry = history[0]

        # Required keys per ADR-056 §T5
        assert "timestamp" in entry
        assert "status_gatilho" in entry
        assert "margem_atual_pct" in entry
        assert "delta_margem_necessario_pct" in entry
        assert "n_sugestoes" in entry
        assert "sugestao_prioritaria" in entry

        assert entry["status_gatilho"] == "AMARELO"
        assert entry["margem_atual_pct"] == pytest.approx(7.0, abs=0.01)

    def test_vermelho_history_entry_has_correct_sugestao_prioritaria(self):
        """VERMELHO history entry sugestao_prioritaria matches secao.sugestao_prioritaria."""
        canonical = _canonical(resultado=_resultado(0.03, "VERMELHO"))
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        history = result.canonical.replanning_history
        secao = result.canonical.replan_suggestions
        assert history[0]["sugestao_prioritaria"] == secao.sugestao_prioritaria


# ---------------------------------------------------------------------------
# 13. Delta calculation: AMARELO uses alvo min, VERMELHO uses aceitavel min
# ---------------------------------------------------------------------------


class TestDeltaCalculation:
    def test_amarelo_delta_uses_alvo_min(self):
        """AMARELO delta = alvo_min (0.08) - margem_atual."""
        canonical = _canonical(resultado=_resultado(0.06, "AMARELO"))
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        secao = result.canonical.replan_suggestions
        assert secao.delta_margem_necessario == pytest.approx(0.08 - 0.06, abs=1e-5)

    def test_vermelho_delta_uses_aceitavel_min(self):
        """VERMELHO delta = aceitavel_min (0.06) - margem_atual."""
        canonical = _canonical(resultado=_resultado(0.03, "VERMELHO"))
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        secao = result.canonical.replan_suggestions
        assert secao.delta_margem_necessario == pytest.approx(0.06 - 0.03, abs=1e-5)


# ---------------------------------------------------------------------------
# 14. Combined scenarios
# ---------------------------------------------------------------------------


class TestCombinedScenarios:
    def test_all_three_main_suggestions_generated(self):
        """With BUY conflict + A+ + indiretos>30% → REPLAN-001, 002, 003 all present."""
        resultado = _resultado(0.04, "VERMELHO")
        custo_total = resultado.custo.total
        conflito = _conflito_pico("Escavadeira", recomendacoes=["BUY: extra"])
        ccr = _cost_criticality_result(classes=["A+", "A+"])
        indireto = _indireto("ADM", custo_total=custo_total * 0.35)

        canonical = _canonical(
            resultado=resultado,
            conflitos_pico=[conflito],
            cost_criticality_report=ccr,
            indiretos=[indireto],
        )
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        ids = {s.id for s in result.canonical.replan_suggestions.sugestoes}
        assert "REPLAN-001" in ids
        assert "REPLAN-002" in ids
        assert "REPLAN-003" in ids
        # REPLAN-005 should NOT appear when other suggestions exist
        assert "REPLAN-005" not in ids

    def test_all_suggestions_have_valid_checkpoints(self):
        """All built-in suggestion types produce valid checkpoint_skill values."""
        _VALID = {
            "03-catalogo-de-recursos",
            "04-cronograma",
            "05-equipes-e-alocacao",
            "06-resultado-financeiro",
        }
        resultado = _resultado(0.04, "VERMELHO")
        custo_total = resultado.custo.total
        conflito = _conflito_pico("Trator", recomendacoes=["BUY"])
        ccr = _cost_criticality_result(classes=["A+"])
        indireto = _indireto("MOB", custo_total=custo_total * 0.35)

        canonical = _canonical(
            resultado=resultado,
            conflitos_pico=[conflito],
            cost_criticality_report=ccr,
            indiretos=[indireto],
        )
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        for s in result.canonical.replan_suggestions.sugestoes:
            assert s.checkpoint_skill in _VALID, f"{s.id} has invalid checkpoint: {s.checkpoint_skill}"

    def test_empty_inputs_dict(self):
        """Empty inputs dict works without errors."""
        canonical = _canonical(resultado=_resultado(0.07, "AMARELO"))
        result = run_assessor_replanejamento(canonical, {})
        assert result.canonical.replan_suggestions is not None

    def test_verde_result_not_has_errors(self):
        """VERDE result never has errors."""
        canonical = _canonical(resultado=_resultado(0.15, "VERDE"))
        result = run_assessor_replanejamento(canonical, {}, _perfil())
        assert not result.has_errors

    def test_replan_suggestions_fields(self):
        """ReplanSugestao fields are populated correctly for REPLAN-001."""
        conflito = _conflito_pico("Escavadeira", excedente=2.0, recomendacoes=["BUY: extra"])
        canonical = _canonical(resultado=_resultado(0.04, "VERMELHO"), conflitos_pico=[conflito])
        result = run_assessor_replanejamento(canonical, {}, _perfil())

        s = next(s for s in result.canonical.replan_suggestions.sugestoes if s.id == "REPLAN-001")
        assert s.tipo == "RECURSOS"
        assert s.checkpoint_skill == "03-catalogo-de-recursos"
        assert s.delta_margem_estimado > 0
        assert s.confianca == "MEDIA"
        assert len(s.restricoes) > 0
        assert "Escavadeira" in s.justificativa
