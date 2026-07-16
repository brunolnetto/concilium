"""NEP-041 Fase 4 — Skill unificada 06-resultado-financeiro (merge 06+07+08).

TDD: testes escritos antes de completar o wiring.

Invariantes:
  - run_resultado_financeiro executa os 3 estágios em sequência (06→07→08)
  - Resultado numericamente idêntico ao pipeline de 3 skills separadas
  - Falha de gate no estágio 1 aborta antes de consolidar (semântica ADR-022)
  - Inputs keyed por IDs legados são mesclados na chave unificada (aliasing)
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    EapItem,
    EquipamentoEquipeDireta,
    EquipeDireta,
    FuncaoEquipeDireta,
    Meta,
    Projeto,
    RegimeTrabalho,
)


def _base_canonical() -> CanonicalModel:
    meta = Meta(gerado_em=datetime.now(UTC), contexto_id="test")
    projeto = Projeto(
        id="p1",
        nome="Projeto F4",
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
    equipe = EquipeDireta(
        equipe_id="eq1",
        item_id="i1",
        cpu_id="CPU-X",
        nome="Equipe X",
        num_equipes_base=1,
        funcoes=[FuncaoEquipeDireta(funcao_id="F1", num_pessoas=1)],
        equipamentos=[EquipamentoEquipeDireta(equip_id="E1", num_unidades=1)],
        custo_mao_obra_mensal=5000.0,
        custo_equipamentos_mensal=5000.0,
        custo_combustivel_total_mensal=5000.0,
        custo_fixo_mensal=10000.0,
        permanencia_meses=1.0,
        custo_total=30000.0,
    )
    return CanonicalModel(meta=meta, projeto=projeto, eap=eap, equipes_diretas=[equipe])


def _catalogo_minimo() -> dict:
    return {
        "cpus": [
            {
                "codigo": "CPU-X",
                "descricao": "CPU teste",
                "unidade": "m3",
                "origem": "REFERENCIA",
                "categoria": "TERRAPLENAGEM",
                "producao_id_ref": "P-1",
                "composicao_itens": [
                    {
                        "insumo_id": "INS-1",
                        "categoria_custo": "MATERIAL",
                        "coeficiente": 1.0,
                        "unidade": "m3",
                    },
                    # ADR-138: fallback (Fonte 2) falha alto se MAO_OBRA/EQUIPAMENTO estiverem
                    # totalmente ausentes de composicao_itens. Este fixture testa paridade entre
                    # a skill unificada e a sequência separada, não o gap de MO/EQ — mantém as
                    # duas categorias presentes com preço zero para não afetar os totais testados.
                    {
                        "insumo_id": "INS-MO",
                        "categoria_custo": "MAO_OBRA",
                        "coeficiente": 1.0,
                        "unidade": "un",
                    },
                    {
                        "insumo_id": "INS-EQ",
                        "categoria_custo": "EQUIPAMENTO",
                        "coeficiente": 1.0,
                        "unidade": "un",
                    },
                ],
            }
        ],
        "insumos": [
            {"codigo": "INS-1", "unidade": "m3", "preco_unitario": 10.0},
            {"codigo": "INS-MO", "unidade": "un", "preco_unitario": 0.0},
            {"codigo": "INS-EQ", "unidade": "un", "preco_unitario": 0.0},
        ],
        "produtividades": [{"id": "P-1", "valor_horario": 1.0}],
    }


_PERFIL = {
    "limiar_ponto_equilibrio": 0.05,
    "faixa_margem_alvo": {"min": 0.08, "max": 0.10},
    "faixa_margem_aceitavel": {"min": 0.06, "max": 0.12},
}


class TestSkillUnificadaDescoberta:
    def test_skill_registrada(self):
        from concilium.application.skills import SKILLS

        assert "06-resultado-financeiro" in SKILLS

    def test_run_importavel(self):
        from concilium.application.skills import run_resultado_financeiro

        assert callable(run_resultado_financeiro)

    def test_e_gate(self):
        from concilium.application.skills import MANIFEST_META

        assert MANIFEST_META["06-resultado-financeiro"]["gate"] is True


class TestParidadeComPipelineSeparado:
    """Resultado da skill unificada == sequência 06→07→08 separada."""

    def test_paridade_numerica(self):
        from concilium.application.skills import load_skill_stage, run_resultado_financeiro

        run_precificacao_unitaria = load_skill_stage(
            "06-resultado-financeiro", "_precificacao", "run_precificacao_unitaria"
        )
        run_custos_indiretos = load_skill_stage("06-resultado-financeiro", "_indiretos", "run_custos_indiretos")
        run_consolidacao_financeira = load_skill_stage(
            "06-resultado-financeiro", "_consolidacao", "run_consolidacao_financeira"
        )

        canonical = _base_canonical()
        catalogo = _catalogo_minimo()

        # Caminho separado (3 skills)
        r1 = run_precificacao_unitaria(canonical, {}, catalogo, _PERFIL)
        r2 = run_custos_indiretos(r1.canonical, {}, catalogo, _PERFIL)
        r3 = run_consolidacao_financeira(r2.canonical, {}, _PERFIL)
        sep = r3.canonical

        # Caminho unificado
        ru = run_resultado_financeiro(canonical, {}, catalogo, _PERFIL)
        uni = ru.canonical

        assert uni.resultado is not None
        assert sep.resultado is not None
        assert uni.resultado.custo.total == pytest.approx(sep.resultado.custo.total, abs=0.01)
        assert uni.resultado.venda.total_com_bdi == pytest.approx(sep.resultado.venda.total_com_bdi, abs=0.01)
        assert uni.resultado.resultado_financeiro == pytest.approx(sep.resultado.resultado_financeiro, abs=0.01)
        assert len(uni.planejamento) == len(sep.planejamento)
        assert len(uni.indiretos) == len(sep.indiretos)

    def test_validacoes_de_todos_estagios(self):
        from concilium.application.skills import run_resultado_financeiro

        ru = run_resultado_financeiro(_base_canonical(), {}, _catalogo_minimo(), _PERFIL)
        codigos = {v.codigo for v in ru.validacoes}
        # Pelo menos uma validação de cada estágio
        assert "VAL-POL-BDI" in codigos  # estágio precificação

    def test_gate_aborta_na_precificacao(self):
        """EAP vazia → erro de precificação → consolidação não roda."""
        from concilium.application.skills import run_resultado_financeiro

        canonical = _base_canonical().model_copy(update={"eap": []})
        ru = run_resultado_financeiro(canonical, {}, _catalogo_minimo(), _PERFIL)
        assert ru.has_errors
        assert ru.canonical.resultado is None  # estágio 3 não rodou

    def test_bdi_indireto_efetivo_numerico_e_usado_diretamente(self):
        """inputs['bdi_indireto_efetivo'] como float é aceito sem cair no fallback None."""
        from concilium.application.skills import run_resultado_financeiro

        ru = run_resultado_financeiro(_base_canonical(), {"bdi_indireto_efetivo": 0.2}, _catalogo_minimo(), _PERFIL)
        assert ru.canonical.resultado is not None

    def test_custo_direto_zero_nao_emite_gap_catalogo_operacional(self):
        """equipes_diretas com custo_total=0 e sem planejamento → custo_direto=0 →
        bloco VAL-GAP-CATALOGO-OPERACIONAL não é emitido (branch 357->372)."""
        from concilium.application.skills import run_resultado_financeiro

        canonical = _base_canonical().model_copy(
            update={
                "equipes_diretas": [
                    e.model_copy(update={"custo_total": 0.0}) for e in _base_canonical().equipes_diretas
                ]
            }
        )
        ru = run_resultado_financeiro(canonical, {}, _catalogo_minimo(), _PERFIL)
        codigos = {v.codigo for v in ru.validacoes}
        assert "VAL-GAP-CATALOGO-OPERACIONAL" not in codigos


class TestWiringJurisdicaoETaxScenario:
    """ADR-038/ADR-055: jurisdição resolvida e tax_scenario agora influenciam
    o BDI efetivamente calculado ponta a ponta (antes eram ignorados/órfãos)."""

    def test_regressao_zero_sem_jurisdicao_nem_tax_scenario(self):
        """Sem os novos inputs, o resultado é idêntico ao comportamento pré-existente
        (DEFAULT_BDI_TABELA puro, sem VAL-*-JURISDICAO/REGIME emitidos)."""
        from concilium.application.skills import run_resultado_financeiro

        ru = run_resultado_financeiro(_base_canonical(), {}, _catalogo_minimo(), _PERFIL)
        assert ru.canonical.resultado is not None
        codigos = {v.codigo for v in ru.validacoes}
        assert "VAL-BDI-JURISDICAO" not in codigos
        assert "VAL-CONSOL-BDI-JURISDICAO" not in codigos
        assert "VAL-BDI-REGIME" not in codigos

    def test_aliquotas_bdi_jurisdicao_muda_bdi_de_mao_obra_nao_muda_material(self):
        """ISS diferente do default (2% vs 5%) deve mudar o BDI calculado de
        mao_obra/servicos/indireto (categorias que têm ISS na base) e NÃO mudar
        material/diesel (categorias sem ISS aplicável)."""
        from concilium.application.skills import run_resultado_financeiro
        from concilium.domain.models.financial.bdi import DEFAULT_BDI_TABELA

        aliquotas = {"ISS": 0.02, "PIS": 0.0065, "COFINS": 0.03}
        ru_default = run_resultado_financeiro(_base_canonical(), {}, _catalogo_minimo(), _PERFIL)
        ru_jurisdicao = run_resultado_financeiro(
            _base_canonical(), {"aliquotas_bdi_jurisdicao": aliquotas}, _catalogo_minimo(), _PERFIL
        )

        assert ru_default.canonical.resultado is not None
        assert ru_jurisdicao.canonical.resultado is not None
        assert DEFAULT_BDI_TABELA.mao_obra.iss == 0.05  # confirma que 0.02 é de fato diferente

        # tabela_bdi_efetiva (persistida pela skill-06) reflete o ISS da jurisdição
        # nas categorias que já tinham ISS na base (mao_obra/servicos/indireto)...
        tabela = ru_jurisdicao.canonical.tabela_bdi_efetiva
        assert tabela is not None
        assert tabela.mao_obra.iss == 0.02
        assert tabela.servicos.iss == 0.02
        assert tabela.indireto.iss == 0.02
        # ...e NÃO nas categorias sem ISS aplicável (material/diesel são mercadoria).
        assert tabela.material.iss == 0.0
        assert tabela.diesel.iss == 0.0
        # default (sem jurisdição) preserva o ISS de fábrica.
        assert ru_default.canonical.tabela_bdi_efetiva.mao_obra.iss == 0.05

        codigos = {v.codigo for v in ru_jurisdicao.validacoes}
        assert "VAL-BDI-JURISDICAO" in codigos  # estágio de precificação aplicou o passo

    def test_tax_scenario_agora_funciona_tambem_na_precificacao(self):
        """ADR-055: tax_scenario era órfão no estágio de precificação (só funcionava
        em consolidação) — agora produz VAL-BDI-REGIME também via run_resultado_financeiro."""
        from concilium.application.skills import run_resultado_financeiro

        tax_scenario = {"regime_version": "pleno_cbs_ibs", "cbs_ibs_combined_rate": 0.265}
        ru = run_resultado_financeiro(
            _base_canonical(), {"tax_scenario": tax_scenario}, _catalogo_minimo(), _PERFIL
        )
        assert ru.canonical.resultado is not None
        codigos = {v.codigo for v in ru.validacoes}
        assert "VAL-BDI-REGIME" in codigos  # precificação (antes órfão)
        assert "VAL-CONSOL-BDI-REGIME" in codigos  # consolidação (já funcionava)


class TestSemResiduosLegados:
    """Pós-limpeza: shims e aliasing de inputs legados foram removidos."""

    def test_normalize_financeiro_inputs_nao_existe_mais(self):
        """O aliasing de chaves legadas foi removido — produtores usam a chave nova."""
        from concilium.application.runtime import Runtime

        assert not hasattr(Runtime, "_normalize_financeiro_inputs")

    def test_shims_de_funcoes_absorvidas_removidos(self):
        """Imports das run functions antigas via package falham — usar load_skill_stage."""
        import pytest as _pytest

        with _pytest.raises((ImportError, AttributeError)):
            from concilium.application.skills import run_precificacao_unitaria  # noqa: F401

    def test_load_skill_stage_e_o_caminho_explicito(self):
        from concilium.application.skills import load_skill_stage

        fn = load_skill_stage("06-resultado-financeiro", "_precificacao", "run_precificacao_unitaria")
        assert callable(fn)

    def test_benchmark_runner_usa_chave_nova(self):
        """O benchmark _prepare_inputs produz inputs keyed pela skill unificada."""
        import inspect

        from concilium.application.benchmarks.execution import runner as bench_runner

        src = inspect.getsource(bench_runner)
        assert '"06-resultado-financeiro"' in src
        assert 'skill_inputs["07-custos-indiretos"]' not in src
        assert 'skill_inputs.setdefault("08-consolidacao-financeira"' not in src

    def test_load_estagio_raises_when_spec_is_none(self):
        """_load_estagio propaga ImportError quando spec_from_file_location falha."""
        import sys
        from unittest.mock import patch

        mod = sys.modules["_concilium_skillpkg_06_resultado_financeiro.skill"]
        with patch("importlib.util.spec_from_file_location", return_value=None):
            with pytest.raises(ImportError, match="Não foi possível carregar spec"):
                mod._load_estagio("_precificacao", "run_precificacao_unitaria")

    def test_consolidacao_skill_module_loads_via_real_package_dotted_path(self):
        """A pasta hifenizada '06-resultado-financeiro' possui __init__.py em cada
        nível, então importlib.import_module com o caminho pontuado (string,
        sem exigir identificador válido) resolve normalmente — cobrindo o
        caminho feliz do bloco try/except (ambos os imports relativos
        internos, _skill_helpers_a e _skill_helpers_b, sucedem)."""
        import importlib

        mod = importlib.import_module(
            "concilium.application.skills.manifests.06-resultado-financeiro._consolidacao.skill"
        )
        assert hasattr(mod, "run_consolidacao_financeira")
        assert hasattr(mod, "_build_abc_analytics")
        assert hasattr(mod, "_build_bridge_from_pe")

    def test_indiretos_skill_module_loads_via_real_package_dotted_path(self):
        """A pasta '_indiretos' possui __init__.py, então importlib.import_module
        com o caminho pontuado resolve o import relativo inicial de skill.py com
        sucesso (ambos os `from ._skill_helpers_x import` completam) — cobrindo
        o caminho feliz do bloco try (linha 42, segundo import nunca alcançado
        pelas demais rotas de carregamento que sempre caem no fallback)."""
        import importlib

        mod = importlib.import_module("concilium.application.skills.manifests.06-resultado-financeiro._indiretos.skill")
        assert hasattr(mod, "run_custos_indiretos")

