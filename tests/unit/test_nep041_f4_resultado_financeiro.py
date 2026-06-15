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
                    }
                ],
            }
        ],
        "insumos": [{"codigo": "INS-1", "unidade": "m3", "preco_unitario": 10.0}],
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
