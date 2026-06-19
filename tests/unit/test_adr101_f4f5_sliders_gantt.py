"""ADR-101 F4/F5 — Sliders de levers e Gantt interativo.

Cobre:
  F4: simular_cenario_replan com tipo='lever_adjust' — estimativa linear
  F5: diagnostico-pe app tem sliders; artefatos app tem Gantt
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

# ── helpers ─────────────────────────────────────────────────────────────────


def _load_replan():
    import importlib.util

    path = Path(__file__).resolve().parents[2] / "src/concilium/presentation/mcp/tools/replan.py"
    spec = importlib.util.spec_from_file_location("replan_tools", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_canonical(n_items: int = 2, horas_dia: int = 8, dias_semana: int = 6):
    """Constrói um canonical mínimo para testes de simular_cenario_replan."""

    class Regime:
        def __init__(self):
            self.horas_dia = horas_dia
            self.dias_semana = dias_semana

    class Projeto:
        def __init__(self):
            self.regime_trabalho = Regime()

    class PE:
        def __init__(self, item_id, fe_nec, custo):
            self.item_id = item_id
            self.frentes_equivalentes_necessarias = fe_nec
            self.custo_operacional_real = custo

    class Custo:
        def __init__(self):
            self.indireto_adm = 5_000_000.0
            self.indireto_top = 0.0
            self.indireto_lab = 0.0
            self.indireto_qsms = 0.0
            self.indireto_mob = 0.0

    class Venda:
        def __init__(self, total):
            self.total_com_bdi = total

    class Resultado:
        def __init__(self):
            self.custo = Custo()
            self.venda = Venda(80_000_000.0)

    return SimpleNamespace(
        projeto=Projeto(),
        ponto_equilibrio=[PE(f"eap-{i}", 1.1 + i * 0.2, 10_000_000.0) for i in range(n_items)],
        resultado=Resultado(),
    )


# ── Testes de simular_cenario_replan ────────────────────────────────────────


class TestSimularCenarioReplan:
    def test_lever_adjust_retorna_estrutura_correta(self):
        mod = _load_replan()
        canonical = _make_canonical()
        result = mod._simular_lever_adjust(canonical, {"fator_equipes": 1.0})
        assert result["tipo"] == "lever_adjust"
        assert "resumo" in result
        assert "itens" in result
        assert "parametros_aplicados" in result
        assert "nota" in result

    def test_fator_equipes_1_nao_muda_fe_nec(self):
        mod = _load_replan()
        canonical = _make_canonical()
        result = mod._simular_lever_adjust(canonical, {"fator_equipes": 1.0})
        for item in result["itens"]:
            assert abs(item["fe_nec_atual"] - item["fe_nec_estimado"]) < 0.01

    def test_fator_equipes_2_reduz_fe_nec_pela_metade(self):
        mod = _load_replan()
        canonical = _make_canonical()
        result = mod._simular_lever_adjust(canonical, {"fator_equipes": 2.0})
        for item in result["itens"]:
            expected = item["fe_nec_atual"] / 2.0
            assert abs(item["fe_nec_estimado"] - expected) < 0.01

    def test_mais_horas_dia_aumenta_prod_factor(self):
        mod = _load_replan()
        canonical = _make_canonical(horas_dia=8)
        result = mod._simular_lever_adjust(canonical, {"horas_dia": 10})
        pf = result["parametros_aplicados"]["prod_factor"]
        assert abs(pf - 10 / 8) < 0.01

    def test_mais_dias_semana_aumenta_prod_factor(self):
        mod = _load_replan()
        canonical = _make_canonical(dias_semana=6)
        result = mod._simular_lever_adjust(canonical, {"dias_semana": 7})
        pf = result["parametros_aplicados"]["prod_factor"]
        assert abs(pf - 7 / 6) < 0.01

    def test_meta_margem_atingida_sinalizado(self):
        mod = _load_replan()
        canonical = _make_canonical()
        # Venda=80M, indireto=5M, custo_direto=2×10M=20M → margem=(80-5-20)/80=68.75%
        result = mod._simular_lever_adjust(canonical, {"meta_margem_pct": 0.10})
        assert result["resumo"]["meta_atingida_estimada"] is True

    def test_itens_criticos_reduzidos_com_mais_equipes(self):
        mod = _load_replan()
        # fe_nec = 1.1, 1.3, 1.5, 1.7 → 3 críticos (>1.25)
        canonical = _make_canonical(n_items=4)
        canonical.ponto_equilibrio[0].frentes_equivalentes_necessarias = 1.1
        canonical.ponto_equilibrio[1].frentes_equivalentes_necessarias = 1.3
        canonical.ponto_equilibrio[2].frentes_equivalentes_necessarias = 1.5
        canonical.ponto_equilibrio[3].frentes_equivalentes_necessarias = 1.7
        result = mod._simular_lever_adjust(canonical, {"fator_equipes": 2.0})
        # Com fator 2x: fe_nec → 0.55, 0.65, 0.75, 0.85 → 0 críticos
        assert result["resumo"]["itens_criticos_estimado"] == 0
        assert result["resumo"]["itens_criticos_atual"] == 3

    def test_fator_1_custo_estimado_igual_atual(self):
        mod = _load_replan()
        canonical = _make_canonical()
        result = mod._simular_lever_adjust(canonical, {"fator_equipes": 1.0})
        assert result["resumo"]["delta_custo"] == pytest.approx(0.0, abs=1.0)

    def test_fator_maior_aumenta_custo_estimado(self):
        mod = _load_replan()
        canonical = _make_canonical()
        result = mod._simular_lever_adjust(canonical, {"fator_equipes": 1.5})
        assert result["resumo"]["delta_custo"] > 0

    def test_combinacao_fator_e_horas(self):
        mod = _load_replan()
        canonical = _make_canonical(horas_dia=8)
        # fator=1.5, horas=10 → prod_factor = 1.5 × 10/8 = 1.875
        result = mod._simular_lever_adjust(canonical, {"fator_equipes": 1.5, "horas_dia": 10})
        pf = result["parametros_aplicados"]["prod_factor"]
        assert abs(pf - 1.875) < 0.01

    def test_sem_pes_retorna_resumo_zero(self):
        mod = _load_replan()
        canonical = _make_canonical()
        canonical.ponto_equilibrio = []
        result = mod._simular_lever_adjust(canonical, {"fator_equipes": 1.0})
        assert result["resumo"]["fe_nec_medio_atual"] == 0.0
        assert result["itens"] == []


# ── Testes de estrutura dos apps HTML ───────────────────────────────────────


class TestDiagnosticoPeApp:
    """Verifica que o HTML do app de diagnóstico tem os elementos de sliders."""

    def _html(self):
        p = Path(__file__).resolve().parents[2] / "src/concilium/presentation/mcp/apps/diagnostico-pe/index.html"
        return p.read_text(encoding="utf-8")

    def test_arquivo_existe(self):
        p = Path(__file__).resolve().parents[2] / "src/concilium/presentation/mcp/apps/diagnostico-pe/index.html"
        assert p.exists()

    def test_tem_tab_levers(self):
        assert "Levers" in self._html()

    def test_tem_slider_equipes(self):
        html = self._html()
        assert 'id="l-equipes"' in html
        assert 'type="range"' in html

    def test_tem_slider_horas_dia(self):
        assert 'id="l-horas"' in self._html()

    def test_tem_slider_margem(self):
        assert 'id="l-margem"' in self._html()

    def test_tem_botao_aplicar(self):
        assert "aplicarSimulacao" in self._html()
        assert "btn-apply" in self._html()

    def test_tem_secao_impacto_estimado(self):
        assert "Impacto Estimado" in self._html()

    def test_tem_campos_fe_atual_e_novo(self):
        html = self._html()
        assert "si-fe-atual" in html
        assert "si-fe-novo" in html

    def test_tem_items_criticos(self):
        html = self._html()
        assert "si-items-crit" in html
        assert "si-items-novo" in html

    def test_chama_simular_cenario_replan(self):
        assert "simular_cenario_replan" in self._html()

    def test_tem_botao_reset(self):
        assert "resetLevers" in self._html()


class TestArtefatosApp:
    """Verifica que o HTML do app de artefatos tem o Gantt."""

    def _html(self):
        p = Path(__file__).resolve().parents[2] / "src/concilium/presentation/mcp/apps/artefatos/index.html"
        return p.read_text(encoding="utf-8")

    def test_arquivo_existe(self):
        p = Path(__file__).resolve().parents[2] / "src/concilium/presentation/mcp/apps/artefatos/index.html"
        assert p.exists()

    def test_tem_entrada_cronograma_na_sidebar(self):
        html = self._html()
        assert "openGantt" in html or "Cronograma" in html

    def test_tem_funcao_build_gantt(self):
        assert "buildGanttHTML" in self._html()

    def test_tem_suporte_a_svg(self):
        assert "svg" in self._html().lower()

    def test_tem_tooltip_gantt(self):
        html = self._html()
        assert "gantt-tooltip" in html

    def test_processa_scheduled_activities(self):
        assert "scheduled_activities" in self._html()

    def test_tem_legenda_de_recursos(self):
        html = self._html()
        assert "EQUIPE" in html or "colorMap" in html

    def test_lida_com_canonical_cronograma(self):
        html = self._html()
        assert "canonical?.cronograma" in html or "canonical.cronograma" in html

    def test_tem_escala_semanal(self):
        assert "start_week" in self._html()

    def test_tem_ramp_profile_ou_duracao(self):
        html = self._html()
        assert "duration_weeks" in html or "ramp_profile" in html

    def test_auto_open_gantt_quando_sem_artefatos(self):
        assert "openGantt()" in self._html()
