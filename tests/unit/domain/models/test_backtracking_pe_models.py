"""Coverage sweep 3 — files with 20-35 lines missing."""

from __future__ import annotations

# ─── domain/models/backtracking_pe.py ────────────────────────────────────────


class TestBacktrackingPEModels:
    def test_solucao_inversa_fields(self):
        from concilium.domain.models.financial.backtracking_pe import SolucaoInversa

        s = SolucaoInversa(
            parametro="horas_dia",
            valor_atual=8.0,
            valor_requerido=10.0,
            delta_abs=2.0,
            delta_pct=0.25,
            impacto_preco_pct=0.05,
            impacto_produtividade_pct=0.1,
            impacto_recursos_pct=0.0,
            impacto_prazo_semanas=-2.0,
            pe_gap_recalculado=0.12,
            roundtrip_valido=True,
            erro_roundtrip=0.001,
            confianca=3,
        )
        assert s.parametro == "horas_dia"
        assert s.delta_abs == 2.0

    def test_backtracking_pe_classes_importable(self):
        from concilium.domain.models.financial.backtracking_pe import BacktrackingPEItem, BacktrackingPERelatorio

        assert BacktrackingPEItem is not None
        assert BacktrackingPERelatorio is not None









# ─── domain/models/financial/backtracking_pe.py ───────────────────────────────


def _make_solucao(**kwargs):
    from concilium.domain.models.financial.backtracking_pe import SolucaoInversa

    defaults = dict(
        parametro="L",
        valor_atual=0.15,
        valor_requerido=0.20,
        delta_abs=0.05,
        delta_pct=33.3,
        impacto_preco_pct=5.0,
        impacto_produtividade_pct=0.0,
        impacto_recursos_pct=0.0,
        impacto_prazo_semanas=0.0,
        pe_gap_recalculado=0.001,
        roundtrip_valido=True,
        erro_roundtrip=0.001,
        confianca=4,
    )
    defaults.update(kwargs)
    return SolucaoInversa(**defaults)


class TestSolucaoInversa:
    def test_label_known_param(self):
        s = _make_solucao(parametro="L")
        assert "margem" in s.label.lower() or s.label != "L"

    def test_label_unknown_param(self):
        s = _make_solucao(parametro="CUSTOM")
        assert s.label == "CUSTOM"

    def test_impacto_cliente_descricao(self):
        s = _make_solucao(parametro="P")
        assert "Sem repasse" in s.impacto_cliente_descricao

    def test_impacto_cliente_unknown(self):
        s = _make_solucao(parametro="CUSTOM")
        assert s.impacto_cliente_descricao == "—"

    def test_estrelas_property(self):
        s = _make_solucao(confianca=3)
        assert s.estrelas == "★★★☆☆"

    def test_descricao_delta_L(self):
        s = _make_solucao(parametro="L", valor_atual=0.10, valor_requerido=0.15, delta_abs=0.05)
        assert "pp" in s.descricao_delta

    def test_descricao_delta_P(self):
        s = _make_solucao(parametro="P", valor_atual=50, valor_requerido=60, delta_pct=20)
        assert "un/h" in s.descricao_delta

    def test_descricao_delta_N_MAX(self):
        s = _make_solucao(parametro="N_MAX", valor_atual=2, valor_requerido=3, delta_abs=1)
        assert "equipes" in s.descricao_delta

    def test_descricao_delta_T0_RAMP(self):
        s = _make_solucao(parametro="T0_RAMP", delta_abs=-2)
        assert "semanas" in s.descricao_delta

    def test_descricao_delta_fallback(self):
        s = _make_solucao(parametro="COMBINADA", delta_abs=1.5)
        assert "Δ" in s.descricao_delta or "1.50" in s.descricao_delta


class TestBacktrackingPEItem:
    def _make_item(self, solucoes=()):
        from concilium.domain.models.financial.backtracking_pe import BacktrackingPEItem

        return BacktrackingPEItem(
            atividade_id="A1",
            descricao="Atividade 1",
            pe_gap_atual=0.05,
            pe_gap_alvo=0.10,
            solucoes=tuple(solucoes),
            solucao_recomendada=None,
            roundtrips_falharam=(),
        )

    def test_tem_solucao_sem_repasse_true(self):
        sol = _make_solucao(roundtrip_valido=True, impacto_preco_pct=0.2)
        item = self._make_item([sol])
        assert item.tem_solucao_sem_repasse is True

    def test_tem_solucao_sem_repasse_false(self):
        sol = _make_solucao(roundtrip_valido=True, impacto_preco_pct=5.0)
        item = self._make_item([sol])
        assert item.tem_solucao_sem_repasse is False


class TestBacktrackingPERelatorio:
    def _make_relatorio(self, n_fails=0):
        from concilium.domain.models.financial.backtracking_pe import BacktrackingPERelatorio

        return BacktrackingPERelatorio(
            projeto_id="proj-1",
            gerado_em="2026-01-01",
            pe_gap_alvo=0.10,
            itens=(),
            consistencia_global=True,
            n_roundtrips_falharam=n_fails,
        )

    def test_aviso_consistencia_none_when_no_fails(self):
        r = self._make_relatorio(n_fails=0)
        assert r.aviso_consistencia is None

    def test_aviso_consistencia_has_message_when_fails(self):
        r = self._make_relatorio(n_fails=2)
        assert "2" in r.aviso_consistencia

    def test_to_dict(self):
        r = self._make_relatorio()
        d = r.to_dict()
        assert d["projeto_id"] == "proj-1"
        assert isinstance(d["itens"], list)



