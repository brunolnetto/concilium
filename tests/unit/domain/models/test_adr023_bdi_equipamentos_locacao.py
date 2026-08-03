"""ADR-023 §D3 (revisado) — BDI de equipamentos derivado da composição real.

TDD: testes escritos antes da correção.

Contexto da correção:
  - O blend 70/30 (equip = 70%·MO + 30%·diesel) era um placeholder do ADR-023
    ("simplificação aceitável para a fase inicial, a ser parametrizada").
  - Pós ADR-088/090, o bucket 'equipamentos' contém apenas locação + manutenção
    (combustível e operador já são categorias separadas) — o pressuposto do blend quebrou.
  - Base legal: Súmula Vinculante 31 do STF — ISS não incide sobre locação de
    bens móveis. Locação pura ⇒ BDI de material (4%). Manutenção (serviço) ⇒ BDI de MO.
  - A consolidação (skill-08) já usava material para equipamentos; a precificação
    ainda usava 70/30 — inconsistência interna eliminada por esta correção.

Regra nova:
  equip_bdi = frac_locacao × bdi_material + (1 − frac_locacao) × bdi_mao_obra
  onde frac_locacao = Σ custo_locacao / Σ (custo_locacao + custo_manutencao) das
  equipes diretas; default 1.0 (locação pura) quando não computável.
"""

from __future__ import annotations

import sys

import pytest


def _load_precificacao():
    from concilium.application.skills import load_skill_stage

    fn = load_skill_stage("06-resultado-financeiro", "_precificacao", "run_precificacao_unitaria")
    return sys.modules[fn.__module__]


class TestBdiEquipamentosDerivado:
    """_resolve_bdi: equipamentos derivado da composição locação/manutenção."""

    def test_default_locacao_pura_usa_material(self):
        """Sem frac informada (default 1.0 = locação pura): equip = material (SV-31)."""
        mod = _load_precificacao()
        validacoes = []
        result = mod._resolve_bdi({}, validacoes)
        # DEFAULT_BDI_TABELA: material = 4%
        assert result["equipamentos"] == pytest.approx(result["material"], abs=1e-6)
        assert result["equipamentos"] == pytest.approx(0.04, abs=0.005)

    def test_blend_70_30_removido(self):
        """O placeholder 70/30 não é mais aplicado."""
        mod = _load_precificacao()
        validacoes = []
        result = mod._resolve_bdi({}, validacoes)
        blend_antigo = round(0.70 * result["mao_obra"] + 0.30 * result["diesel"], 6)
        assert result["equipamentos"] != pytest.approx(blend_antigo, abs=1e-4), (
            "equipamentos ainda usa o placeholder 70/30"
        )

    def test_frac_locacao_parcial_blenda_com_mo(self):
        """frac_locacao=0.6 → 60% material + 40% mao_obra (manutenção é serviço)."""
        mod = _load_precificacao()
        validacoes = []
        result = mod._resolve_bdi({}, validacoes, frac_locacao=0.6)
        esperado = 0.6 * result["material"] + 0.4 * result["mao_obra"]
        assert result["equipamentos"] == pytest.approx(esperado, abs=1e-6)

    def test_frac_locacao_zero_manutencao_pura(self):
        """frac_locacao=0 (manutenção pura, serviço) → equip = mao_obra."""
        mod = _load_precificacao()
        validacoes = []
        result = mod._resolve_bdi({}, validacoes, frac_locacao=0.0)
        assert result["equipamentos"] == pytest.approx(result["mao_obra"], abs=1e-6)

    def test_override_manual_explicito_respeitado(self):
        """inputs.bdi_aplicado.equipamentos explícito continua tendo precedência."""
        mod = _load_precificacao()
        validacoes = []
        result = mod._resolve_bdi(
            {"bdi_aplicado": {"material": 0.04, "diesel": 0.04, "mao_obra": 0.30, "equipamentos": 0.15}},
            validacoes,
        )
        assert result["equipamentos"] == pytest.approx(0.15, abs=1e-6)

    def test_consistencia_com_consolidacao(self):
        """Precificação (default) e consolidação usam a mesma taxa para equipamentos."""
        mod = _load_precificacao()
        import importlib

        cons = importlib.import_module(
            "concilium.application.skills.manifests.06-resultado-financeiro._consolidacao._skill_helpers._bdi_resolucao"
        )

        v1, v2 = [], []
        prec_rates = mod._resolve_bdi({}, v1)
        cons_rates = cons._resolve_bdi_rates({}, v2)
        assert prec_rates["equipamentos"] == pytest.approx(cons_rates["equipamentos"], abs=1e-6), (
            f"precificação={prec_rates['equipamentos']:.4f} vs consolidação={cons_rates['equipamentos']:.4f}"
        )

    def test_consistencia_com_consolidacao_frac_parcial(self):
        """issue #121: antes desta correção, consolidação ignorava frac_locacao e sempre
        usava a taxa de material (locação pura), divergindo de precificação sempre que
        havia manutenção real (frac_locacao < 1.0)."""
        mod = _load_precificacao()
        import importlib

        cons = importlib.import_module(
            "concilium.application.skills.manifests.06-resultado-financeiro._consolidacao._skill_helpers._bdi_resolucao"
        )

        v1, v2 = [], []
        prec_rates = mod._resolve_bdi({}, v1, frac_locacao=0.6)
        cons_rates = cons._resolve_bdi_rates({}, v2, frac_locacao=0.6)
        assert prec_rates["equipamentos"] == pytest.approx(cons_rates["equipamentos"], abs=1e-6), (
            f"precificação={prec_rates['equipamentos']:.4f} vs consolidação={cons_rates['equipamentos']:.4f}"
        )
        # Confirma que de fato blenda (não cai de volta para material puro)
        assert cons_rates["equipamentos"] != pytest.approx(cons_rates["material"], abs=1e-6)


class TestFracLocacaoDoCanonical:
    """run_precificacao_unitaria deriva frac_locacao das equipes do canônico."""

    def test_helper_frac_locacao(self):
        from datetime import UTC, datetime

        from concilium.domain.models.canonical import (
            CanonicalModel,
            Coordenadas,
            EquipeDireta,
            Meta,
            Projeto,
            RegimeTrabalho,
        )

        mod = _load_precificacao()
        meta = Meta(gerado_em=datetime.now(UTC), contexto_id="t")
        projeto = Projeto(
            id="p",
            nome="T",
            tipo_obra="terraplenagem",
            localizacao="BR",
            coordenadas=Coordenadas(lat=0, lng=0),
            regime_trabalho=RegimeTrabalho(dias_semana=6, horas_dia=8),
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
            snapshot_catalogo_id="c",
            snapshot_perfil_id="p",
        )
        eqs = [
            EquipeDireta(
                equipe_id="e1",
                item_id="i1",
                cpu_id="C",
                nome="E1",
                custo_total=0.0,
                custo_locacao_mensal=8_000.0,
                custo_manutencao_mensal=2_000.0,
            ),
        ]
        can = CanonicalModel(meta=meta, projeto=projeto, equipes_diretas=eqs)
        frac = mod._frac_locacao_equipamentos(can)
        assert frac == pytest.approx(0.8, abs=1e-6)

    def test_helper_sem_dados_retorna_1(self):
        from datetime import UTC, datetime

        from concilium.domain.models.canonical import (
            CanonicalModel,
            Coordenadas,
            Meta,
            Projeto,
            RegimeTrabalho,
        )

        mod = _load_precificacao()
        meta = Meta(gerado_em=datetime.now(UTC), contexto_id="t")
        projeto = Projeto(
            id="p",
            nome="T",
            tipo_obra="terraplenagem",
            localizacao="BR",
            coordenadas=Coordenadas(lat=0, lng=0),
            regime_trabalho=RegimeTrabalho(dias_semana=6, horas_dia=8),
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
            snapshot_catalogo_id="c",
            snapshot_perfil_id="p",
        )
        can = CanonicalModel(meta=meta, projeto=projeto, equipes_diretas=[])
        assert mod._frac_locacao_equipamentos(can) == pytest.approx(1.0)

    def test_helper_frac_locacao_em_consolidacao(self):
        """A consolidação (skill-06 _consolidacao) tem o mesmo helper — issue #121:
        antes desta correção, ele não existia lá e a taxa de equipamentos era sempre material."""
        import importlib
        from datetime import UTC, datetime

        from concilium.domain.models.canonical import (
            CanonicalModel,
            Coordenadas,
            EquipeDireta,
            Meta,
            Projeto,
            RegimeTrabalho,
        )

        cons = importlib.import_module(
            "concilium.application.skills.manifests.06-resultado-financeiro._consolidacao._skill_helpers._bdi_resolucao"
        )
        meta = Meta(gerado_em=datetime.now(UTC), contexto_id="t")
        projeto = Projeto(
            id="p",
            nome="T",
            tipo_obra="terraplenagem",
            localizacao="BR",
            coordenadas=Coordenadas(lat=0, lng=0),
            regime_trabalho=RegimeTrabalho(dias_semana=6, horas_dia=8),
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
            snapshot_catalogo_id="c",
            snapshot_perfil_id="p",
        )
        eqs = [
            EquipeDireta(
                equipe_id="e1",
                item_id="i1",
                cpu_id="C",
                nome="E1",
                custo_total=0.0,
                custo_locacao_mensal=8_000.0,
                custo_manutencao_mensal=2_000.0,
            ),
        ]
        can = CanonicalModel(meta=meta, projeto=projeto, equipes_diretas=eqs)
        assert cons._frac_locacao_equipamentos(can) == pytest.approx(0.8, abs=1e-6)
