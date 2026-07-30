"""Testes ADR-172 — Produtividade Efetiva de Precificação (β_i) + custo_operacional_agregado.

Cobre `_resolve_beta_praticabilidade` (_preco_cpu.py) e sua integração em
`_resolve_preco_cat_item`/`_build_planejamento_entry`:
  - β_i = média de η_p (praticabilidade: clima×calendário×jornada, já calculada por
    semana em DistribuicaoSemanal.eta_p) ponderada por num_equipes, só semanas ativas
  - fallback 1.0 (sem correção) quando não há cronograma, item sem schedule, ou sem
    semanas ativas — nunca um valor inventado
  - aplicado só na Fonte 1 (bottom-up, produtividade); Fonte 2 sempre beta=1.0
  - produtividade_catalogo (ADR-162 D1) permanece intocado — beta é campo separado

Cobre também `EquipeDireta.custo_operacional_agregado` (skill 05) e seu uso em
`_build_pe_for_equipe` (skill 06 `_consolidacao`) para corrigir um mismatch de escala
descoberto ao verificar β_i contra o benchmark AGIS: `custo_venda_total` é agregado (todas
as frentes), mas `custo_fixo_total` (usado antes para `delta`) é referência de 1 frente —
comparar os dois diretamente subestimava o lado do custo para itens com >1 frente. A
correção usa `custo_operacional_agregado` (integral semana a semana, robusto a rampa por
construção, já soma num_equipes real por semana — sem multiplicar por nenhuma constante
nominal de n_frentes), com fallback em cascata (custo_operacional_real × n_frentes, depois
custo_fixo_total) quando o campo novo não está disponível.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_MANIFESTS = Path(__file__).resolve().parents[4] / "src" / "concilium" / "application" / "skills" / "manifests"


def _load_precif():
    p = _MANIFESTS / "06-resultado-financeiro" / "_precificacao" / "_skill_helpers" / "__init__.py"
    spec = importlib.util.spec_from_file_location("_adr172_precif_helpers", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_adr172_precif_helpers"] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_consolidacao():
    p = _MANIFESTS / "06-resultado-financeiro" / "_consolidacao" / "_skill_helpers" / "__init__.py"
    spec = importlib.util.spec_from_file_location("_adr172_consolidacao_helpers", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_adr172_consolidacao_helpers"] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_skill05():
    p = _MANIFESTS / "05-equipes-e-alocacao" / "_skill_helpers" / "__init__.py"
    spec = importlib.util.spec_from_file_location("_adr172_skill05_helpers", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_adr172_skill05_helpers"] = mod
    spec.loader.exec_module(mod)
    return mod


MOD = _load_precif()
CONSOLID = _load_consolidacao()
SKILL05 = _load_skill05()


def _semana(num_equipes: float, eta_p: float) -> SimpleNamespace:
    return SimpleNamespace(num_equipes=num_equipes, eta_p=eta_p)


def _sa(dist: dict) -> SimpleNamespace:
    return SimpleNamespace(distribuicao_semanal=dist)


class TestResolveBetaPraticabilidade:
    def test_sem_sched_por_item_retorna_1(self):
        assert MOD._resolve_beta_praticabilidade("eap-01", None) == 1.0

    def test_item_sem_schedule_retorna_1(self):
        assert MOD._resolve_beta_praticabilidade("eap-01", {}) == 1.0

    def test_sem_semanas_ativas_retorna_1(self):
        sched = {"eap-01": _sa({"2026-W01": _semana(0, 0.7), "2026-W02": _semana(0, 0.6)})}
        assert MOD._resolve_beta_praticabilidade("eap-01", sched) == 1.0

    def test_caso_ideal_eta_p_1_em_todas_semanas_retorna_1(self):
        sched = {"eap-01": _sa({"2026-W01": _semana(2, 1.0), "2026-W02": _semana(3, 1.0)})}
        assert MOD._resolve_beta_praticabilidade("eap-01", sched) == pytest.approx(1.0)

    def test_praticabilidade_constante_abaixo_de_1(self):
        """η_p=0.8 em toda semana ativa -> β_i=0.8, independente do peso."""
        sched = {"eap-01": _sa({"2026-W01": _semana(2, 0.8), "2026-W02": _semana(5, 0.8)})}
        assert MOD._resolve_beta_praticabilidade("eap-01", sched) == pytest.approx(0.8)

    def test_media_ponderada_por_num_equipes(self):
        """3 semanas com num_equipes=[1,1,4] e eta_p=[1.0,1.0,0.5]:
        β = (1·1.0 + 1·1.0 + 4·0.5)/(1+1+4) = 4.0/6 = 0.6667 — a semana de 4 equipes
        domina a média, não uma média simples dos 3 valores (que daria 0.8333)."""
        sched = {
            "eap-01": _sa(
                {
                    "2026-W01": _semana(1, 1.0),
                    "2026-W02": _semana(1, 1.0),
                    "2026-W03": _semana(4, 0.5),
                }
            )
        }
        beta = MOD._resolve_beta_praticabilidade("eap-01", sched)
        assert beta == pytest.approx(4.0 / 6.0, rel=1e-6)
        media_simples = (1.0 + 1.0 + 0.5) / 3
        assert beta != pytest.approx(media_simples)

    def test_semanas_inativas_nao_contam_no_peso(self):
        """Semana com num_equipes=0 não entra no numerador nem denominador, mesmo com
        eta_p baixo registrado (ex: resíduo de cálculo antes da mobilização)."""
        sched = {
            "eap-01": _sa(
                {
                    "2026-W01": _semana(0, 0.1),
                    "2026-W02": _semana(2, 1.0),
                }
            )
        }
        assert MOD._resolve_beta_praticabilidade("eap-01", sched) == pytest.approx(1.0)

    def test_outro_item_no_mesmo_sched_por_item_nao_interfere(self):
        sched = {
            "eap-01": _sa({"2026-W01": _semana(1, 0.5)}),
            "eap-02": _sa({"2026-W01": _semana(1, 1.0)}),
        }
        assert MOD._resolve_beta_praticabilidade("eap-02", sched) == pytest.approx(1.0)
        assert MOD._resolve_beta_praticabilidade("eap-01", sched) == pytest.approx(0.5)


class TestResolvePrecoCatItemComBeta:
    """Integração: `_resolve_preco_cat_item` aplica β_i só na Fonte 1, retorna 5-tupla."""

    _ARGS = dict(
        prod_lookup={},
        insumo_lookup={},
        repo=MagicMock(),
        jurisdicao_id=None,
        overrides=None,
        data_base="2026-01-01",
        preco_diesel=6.20,
        alpha_clt=1.777,
        alpha_mensalista=1.060,
        catalog_session=None,
    )

    def test_fonte1_sem_schedule_beta_1_preco_inalterado(self):
        item = SimpleNamespace(item_id="eap-01")
        cpu = {"codigo": "CPU-01"}
        preco_cat = {"material": 2.0, "diesel": 1.0, "mao_obra": 5.0, "equipamentos": 3.0}
        validacoes: list = []
        with patch.object(
            MOD._process_item, "_compute_preco_cat_from_production", return_value=(dict(preco_cat), 25.0)
        ):
            result, _equip, usou_fallback, produtividade_catalogo, beta = MOD._resolve_preco_cat_item(
                item,
                cpu,
                self._ARGS["prod_lookup"],
                self._ARGS["insumo_lookup"],
                self._ARGS["repo"],
                self._ARGS["jurisdicao_id"],
                self._ARGS["overrides"],
                self._ARGS["data_base"],
                set(),
                validacoes,
                self._ARGS["preco_diesel"],
                self._ARGS["alpha_clt"],
                self._ARGS["alpha_mensalista"],
                self._ARGS["catalog_session"],
                None,
            )
        assert usou_fallback is False
        assert produtividade_catalogo == pytest.approx(25.0)
        assert beta == pytest.approx(1.0)
        assert result == preco_cat

    def test_fonte1_com_praticabilidade_reduzida_divide_preco(self):
        """β_i=0.8 -> cada categoria de preco_cat é dividida por 0.8 (preço sobe)."""
        item = SimpleNamespace(item_id="eap-01")
        cpu = {"codigo": "CPU-01"}
        preco_cat = {"material": 2.0, "diesel": 1.0, "mao_obra": 5.0, "equipamentos": 3.0}
        sched_por_item = {"eap-01": _sa({"2026-W01": _semana(2, 0.8)})}
        validacoes: list = []
        with patch.object(
            MOD._process_item, "_compute_preco_cat_from_production", return_value=(dict(preco_cat), 25.0)
        ):
            result, _equip, usou_fallback, produtividade_catalogo, beta = MOD._resolve_preco_cat_item(
                item,
                cpu,
                self._ARGS["prod_lookup"],
                self._ARGS["insumo_lookup"],
                self._ARGS["repo"],
                self._ARGS["jurisdicao_id"],
                self._ARGS["overrides"],
                self._ARGS["data_base"],
                set(),
                validacoes,
                self._ARGS["preco_diesel"],
                self._ARGS["alpha_clt"],
                self._ARGS["alpha_mensalista"],
                self._ARGS["catalog_session"],
                sched_por_item,
            )
        assert beta == pytest.approx(0.8)
        assert produtividade_catalogo == pytest.approx(25.0), "produtividade_catalogo (ρ_i) não muda por β_i"
        for cat, valor in preco_cat.items():
            assert result[cat] == pytest.approx(valor / 0.8)

    def test_fonte2_fallback_sempre_beta_1(self):
        """Fonte 2 (composicao_itens) não tem produtividade a corrigir — beta=1.0
        mesmo com cronograma/praticabilidade reduzida disponível."""
        item = SimpleNamespace(item_id="eap-01")
        cpu = {"codigo": "CPU-01"}
        preco_cat_fallback = {"material": 3.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 1.0}
        sched_por_item = {"eap-01": _sa({"2026-W01": _semana(2, 0.5)})}
        validacoes: list = []
        with (
            patch.object(MOD._process_item, "_compute_preco_cat_from_production", return_value=(None, 0.0)),
            patch.object(
                MOD._process_item,
                "_preco_cat_fallback_composicao",
                return_value=(preco_cat_fallback, set()),
            ),
        ):
            result, _equip, usou_fallback, produtividade_catalogo, beta = MOD._resolve_preco_cat_item(
                item,
                cpu,
                self._ARGS["prod_lookup"],
                self._ARGS["insumo_lookup"],
                self._ARGS["repo"],
                self._ARGS["jurisdicao_id"],
                self._ARGS["overrides"],
                self._ARGS["data_base"],
                set(),
                validacoes,
                self._ARGS["preco_diesel"],
                self._ARGS["alpha_clt"],
                self._ARGS["alpha_mensalista"],
                self._ARGS["catalog_session"],
                sched_por_item,
            )
        assert usou_fallback is True
        assert beta == pytest.approx(1.0)
        assert result == preco_cat_fallback


class TestBuildPlanejamentoEntryBeta:
    def _make_item(self, item_id="I-01", cpu_id="CPU-01", q=10.0):
        item = MagicMock()
        item.item_id = item_id
        item.cpu_id = cpu_id
        item.quantitativo = q
        return item

    def test_default_beta_e_1(self):
        item = self._make_item()
        preco_cat = {"material": 5.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        bdi = {"material": 0.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        result = MOD._build_planejamento_entry(item, preco_cat, preco_cat, bdi)
        assert result.beta_praticabilidade == pytest.approx(1.0)

    def test_propaga_beta_informado(self):
        item = self._make_item()
        preco_cat = {"material": 5.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        bdi = {"material": 0.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        result = MOD._build_planejamento_entry(item, preco_cat, preco_cat, bdi, beta_praticabilidade=0.75)
        assert result.beta_praticabilidade == pytest.approx(0.75)

    def test_produtividade_catalogo_e_beta_sao_campos_independentes(self):
        item = self._make_item()
        preco_cat = {"material": 5.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        bdi = {"material": 0.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        result = MOD._build_planejamento_entry(
            item, preco_cat, preco_cat, bdi, produtividade_catalogo=25.0, beta_praticabilidade=0.75
        )
        assert result.produtividade_catalogo == pytest.approx(25.0)
        assert result.beta_praticabilidade == pytest.approx(0.75)


class TestBuildSchedPorItem:
    def test_sem_cronograma_retorna_vazio(self):
        canonical = SimpleNamespace(cronograma=None)
        assert MOD._build_sched_por_item(canonical) == {}

    def test_constroi_mapa_por_activity_id(self):
        sa1 = SimpleNamespace(activity_id="eap-01", distribuicao_semanal={})
        sa2 = SimpleNamespace(activity_id="eap-02", distribuicao_semanal={})
        canonical = SimpleNamespace(cronograma=SimpleNamespace(scheduled_activities=[sa1, sa2]))
        result = MOD._build_sched_por_item(canonical)
        assert result == {"eap-01": sa1, "eap-02": sa2}


class TestEquipeDiretaCustoOperacionalAgregadoField:
    def test_default_e_zero(self):
        from concilium.domain.models.canonical import EquipeDireta

        eq = EquipeDireta(item_id="eap-01", cpu_id="CPU-01", custo_fixo_mensal=1000.0)
        assert eq.custo_operacional_agregado == 0.0


class TestBuildPeForEquipeCustoOperacionalAgregado:
    """ADR-172: `delta` usa `custo_operacional_agregado` (integral semana a semana, robusto a
    rampa) em vez de `custo_fixo_total` puro ou de uma multiplicação nominal por n_frentes —
    achado ao verificar β_i contra o benchmark AGIS (custo_venda_total agregado vs
    custo_fixo_total de 1 frente subestimava o lado do custo para itens com >1 frente)."""

    def _equipe(self, **overrides):
        base = dict(
            item_id="eap-01",
            cpu_id="CPU-01",
            custo_fixo_mensal=100_000.0,
            permanencia_meses=5.0,
            permanencia_efetiva_meses=6.0,
            custo_total=700_000.0,
            custo_total_autonomo=600_000.0,
            num_equipes_base=4,
            custo_operacional_agregado=0.0,
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_campo_novo_populado_e_usado_diretamente(self):
        """custo_operacional_agregado=3_000_000 (ex: integral real de 4 frentes) é usado
        como está — não recalculado, não multiplicado de novo por n_frentes."""
        eq = self._equipe(custo_operacional_agregado=3_000_000.0)
        pe = CONSOLID._build_pe_for_equipe(eq, {"eap-01": 3_500_000.0})
        assert pe is not None
        assert pe.custo_fixo_equipe == pytest.approx(3_000_000.0)
        assert pe.delta == pytest.approx(500_000.0)

    def test_campo_novo_ausente_cai_para_custo_operacional_real_x_n_frentes(self):
        """Sem custo_operacional_agregado (0.0, fixture legada): fallback nominal
        custo_operacional_real(700_000) × num_equipes_base(4) = 2_800_000."""
        eq = self._equipe(custo_operacional_agregado=0.0, num_equipes_base=4, custo_total=700_000.0)
        pe = CONSOLID._build_pe_for_equipe(eq, {"eap-01": 3_000_000.0})
        assert pe is not None
        assert pe.custo_fixo_equipe == pytest.approx(2_800_000.0)
        assert pe.delta == pytest.approx(200_000.0)

    def test_ambos_ausentes_cai_para_custo_fixo_total_sem_dividir_por_zero(self):
        """custo_operacional_agregado=0 e custo_total=0 (equipe sem custo real resolvido):
        último fallback é custo_fixo_total (100_000×6=600_000) — nunca ZeroDivisionError
        em delta_pct."""
        eq = self._equipe(custo_operacional_agregado=0.0, custo_total=0.0)
        pe = CONSOLID._build_pe_for_equipe(eq, {"eap-01": 500_000.0})
        assert pe is not None
        assert pe.custo_fixo_equipe == pytest.approx(600_000.0)
        assert pe.delta == pytest.approx(-100_000.0)
        assert pe.delta_pct == pytest.approx(-100_000.0 / 600_000.0, abs=1e-5)

    def test_delta_reconcilia_com_custo_fixo_equipe_reportado(self):
        """Invariante: delta == custo_venda_cpu - custo_fixo_equipe, sempre, para o campo
        efetivamente reportado (não um valor interno diferente do exposto)."""
        eq = self._equipe(custo_operacional_agregado=1_234_567.0)
        pe = CONSOLID._build_pe_for_equipe(eq, {"eap-01": 2_000_000.0})
        assert pe is not None
        assert pe.delta == pytest.approx(pe.custo_venda_cpu - pe.custo_fixo_equipe, abs=0.02)

    def test_frentes_equivalentes_nao_afetado_pela_correcao(self):
        """frentes_equivalentes continua na base de 1 frente (custo_operacional_real /
        custo_fixo_total) — propósito diferente (produtividade real vs referência),
        não deve mudar com a correção de escala do delta."""
        eq = self._equipe(custo_operacional_agregado=3_000_000.0, custo_total=700_000.0)
        pe = CONSOLID._build_pe_for_equipe(eq, {"eap-01": 3_500_000.0})
        assert pe is not None
        assert pe.frentes_equivalentes == pytest.approx(700_000.0 / 600_000.0, abs=0.01)

    def test_coberta_por_pool_usa_custo_total_direto_nao_agregado_autonomo(self):
        """Issue #139 parte 2: com contrato_tipo_id preenchido, custo_total já é o custo
        real agregado ajustado pelo contrato (issue #139 parte 1) — delta deve usar esse
        valor diretamente, não custo_operacional_agregado (autônomo, pode divergir por
        economia de escala compartilhada ou ociosidade imputada)."""
        eq = self._equipe(
            custo_total=6_000_000.0,  # já agregado, pós-pool
            custo_operacional_agregado=9_000_000.0,  # autônomo, deliberadamente diferente
            contrato_tipo_id="ESC",
        )
        pe = CONSOLID._build_pe_for_equipe(eq, {"eap-01": 6_500_000.0})
        assert pe is not None
        assert pe.custo_fixo_equipe == pytest.approx(6_000_000.0)
        assert pe.delta == pytest.approx(500_000.0)
