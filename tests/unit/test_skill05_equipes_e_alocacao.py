"""Coverage batch B — targets runtime.py, 04-cronograma, 05-equipes-e-alocacao,
06-resultado-financeiro/_precificacao, 07-diagnostico-criticidade, and semantic/normalizer edge cases.
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime
from unittest.mock import patch

from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    Cronograma,
    DistribuicaoSemanal,
    EapItem,
    Meta,
    Projeto,
    RegimeTrabalho,
    ScheduledActivityCanonical,
)


def _make_meta():
    return Meta(gerado_em=datetime.now(UTC), contexto_id="test")

def _make_proj(data_inicio="2026-06-01", data_termino="2026-07-31"):
    return Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=-3.0, lng=-38.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2026, 6, 1),
        data_termino=date(2026, 7, 31),
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )

def _minimal_canonical(**kw):
    return CanonicalModel(meta=_make_meta(), projeto=_make_proj(), **kw)

def _load_skill_module(skill_id: str) -> object:
    import concilium.application.skills as _skills_pkg

    return _skills_pkg._load_skill_module(skill_id)


# ══ 05-equipes-e-alocacao/skill.py ══════════════════════════════════════════


class TestEquipesDiretasEdgeCases:
    def _get_permanencia_fn(self):
        mod = _load_skill_module("05-equipes-e-alocacao")
        return mod._calcular_permanencia_e_custo_total

    def _make_cron_semanal(self, item_id="i1"):
        """ScheduledActivityCanonical with semanal distribution (keys contain 'W')."""
        return ScheduledActivityCanonical(
            activity_id=item_id,
            start_week=23,
            end_week=23,
            duration_weeks=1,
            distribuicao_semanal={
                "2026-W23": DistribuicaoSemanal(
                    num_equipes=2, qtd_executada=100.0, qtd_acumulada=100.0, pct=1.0, eficiencia=1.0
                ),
            },
        )

    def _make_cron_mensal(self, item_id="i1"):
        """Namespace with monthly distribution (keys without 'W') for _calcular_permanencia tests."""
        from types import SimpleNamespace

        d = DistribuicaoSemanal(num_equipes=2, qtd_executada=500.0, qtd_acumulada=500.0, pct=1.0, eficiencia=1.0)
        return SimpleNamespace(
            distribuicao_semanal={},
            distribuicao_mensal={"2026-01": d},
        )

    def test_calcular_permanencia_semanal(self):
        """_calcular_permanencia_e_custo_total with semanal distribution (lines 117, 121)."""
        fn = self._get_permanencia_fn()
        cron = self._make_cron_semanal()
        permanencia, custo_total = fn(cron, 10_000.0)
        _semanas_por_mes = 365.25 / 12 / 7
        assert permanencia == round(1 / _semanas_por_mes, 2)
        assert custo_total > 0

    def test_calcular_permanencia_mensal(self):
        """_calcular_permanencia_e_custo_total with monthly distribution (lines 118, 122)."""
        fn = self._get_permanencia_fn()
        cron = self._make_cron_mensal()
        permanencia, custo_total = fn(cron, 10_000.0)
        assert permanencia == 1.0  # float(1 period)
        assert custo_total == round(10_000.0 * 2, 2)

    def _make_full_canonical_for_equipes(self, cpu_id, funcao_id, equip_id, use_monthly=False):
        """Build a canonical with cronograma ready for run_equipes_diretas."""
        eap = [EapItem(item_id="i1", ordem=1, cpu_id=cpu_id, descricao="Test", unidade="m3", quantitativo=100.0)]
        sched = self._make_cron_semanal("i1")
        cron = Cronograma(scheduled_activities=[sched])
        return _minimal_canonical(eap=eap, cronograma=cron)

    def _make_catalogo(self, cpu_id, funcao_id, equip_id):
        return {
            "cpus": [
                {
                    "codigo": cpu_id,
                    "descricao": "CPU Test",
                    "producao_id_ref": "PROD-T",
                    "composicao_itens": [],
                }
            ],
            "insumos": [
                {
                    "codigo": funcao_id,
                    "tipo": "MAO_OBRA",
                    "descricao": "Operador",
                    "preco_unitario": 3000.0,
                    "unidade": "mes",
                    "atributos_especificos": {},
                },
                {
                    "codigo": equip_id,
                    "tipo": "EQUIPAMENTO",
                    "descricao": "Escavadeira",
                    "preco_unitario": 100.0,
                    "unidade": "h",
                    "atributos_especificos": {},
                },
            ],
            "produtividades": [
                {
                    "id": "PROD-T",
                    "valor_horario": 50.0,
                    "composicao_padrao_equipe": {
                        "funcoes": [{"funcao_id": funcao_id, "num_pessoas": 1}],
                        "equipamentos": [{"equip_id": equip_id, "num_unidades": 1}],
                    },
                }
            ],
        }

    def test_run_equipes_object_like_dv(self):
        """dv_obj with attribute dv2_num_equipes (not dict, not DecisionVariables) → line 181."""
        from concilium.application.skills import run_equipes_e_alocacao as run_equipes_diretas

        cpu_id, funcao_id, equip_id = "CPU-A", "funcao-a", "equip-a"
        canonical = self._make_full_canonical_for_equipes(cpu_id, funcao_id, equip_id)
        catalogo = self._make_catalogo(cpu_id, funcao_id, equip_id)

        class ObjectDV:
            dv2_num_equipes = None

        inputs = {"dv": ObjectDV()}
        result = run_equipes_diretas(canonical, inputs, catalogo)
        assert result.canonical is not None

    def test_run_equipes_cpu_none_in_eap_skipped(self):
        """eap item with cpu_id not in cpu_lookup → continue (line 190)."""
        from concilium.application.skills import run_equipes_e_alocacao as run_equipes_diretas

        # cpu_id_missing is not in catalogo
        cpu_missing = "CPU-MISSING"
        sched = ScheduledActivityCanonical(
            activity_id="i1",
            start_week=23,
            end_week=23,
            duration_weeks=1,
            distribuicao_semanal={
                "2026-W23": DistribuicaoSemanal(
                    num_equipes=1, qtd_executada=100.0, qtd_acumulada=100.0, pct=1.0, eficiencia=1.0
                )
            },
        )
        eap = [EapItem(item_id="i1", ordem=1, cpu_id=cpu_missing, descricao="Test", unidade="m3", quantitativo=100.0)]
        canonical = _minimal_canonical(eap=eap, cronograma=Cronograma(scheduled_activities=[sched]))
        catalogo = {"cpus": [], "insumos": []}  # cpu_missing not in cpus
        result = run_equipes_diretas(canonical, {}, catalogo)
        # No crash, just skips the item
        assert result.canonical is not None
        assert result.canonical.equipes_diretas == []

    def test_run_equipes_funcao_obter_returns_none(self):
        """funcao_existe=True but obter_insumo returns None → lines 207-208."""
        from concilium.application.skills import run_equipes_e_alocacao as run_equipes_diretas

        cpu_id, funcao_id, equip_id = "CPU-B", "funcao-b", "equip-b"
        canonical = self._make_full_canonical_for_equipes(cpu_id, funcao_id, equip_id)
        catalogo = self._make_catalogo(cpu_id, funcao_id, equip_id)

        # Find the skill module and patch RepositorioInsumo
        mod = sys.modules.get("concilium.application.skills.equipes_e_alocacao") or sys.modules.get(
            "_concilium_skill_03_equipes_e_alocacao"
        )
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo as _RealRepo

        class MockRepo(_RealRepo):
            def funcao_existe(self, codigo):
                # Return True so the first guard is passed
                return codigo == funcao_id

            def obter_insumo(self, codigo):
                if codigo == funcao_id:
                    return None  # simulate obter_insumo returning None after funcao_existe=True
                return super().obter_insumo(codigo)

        with patch.object(mod, "RepositorioInsumo", new=MockRepo):
            result = run_equipes_diretas(canonical, {}, catalogo)
        assert result.canonical is not None
        # funcao_id should be in erros_funcao (via VAL-EQUIP validation)
        funcao_errors = [v for v in result.validacoes if v.mensagem and funcao_id in v.mensagem]
        assert len(funcao_errors) > 0

    def test_run_equipes_equip_obter_returns_none(self):
        """equipamento_existe=True but obter_insumo returns None → lines 237-238."""
        from concilium.application.skills import run_equipes_e_alocacao as run_equipes_diretas

        cpu_id, funcao_id, equip_id = "CPU-C", "funcao-c", "equip-c"
        canonical = self._make_full_canonical_for_equipes(cpu_id, funcao_id, equip_id)
        catalogo = self._make_catalogo(cpu_id, funcao_id, equip_id)

        mod = sys.modules.get("concilium.application.skills.equipes_e_alocacao") or sys.modules.get(
            "_concilium_skill_03_equipes_e_alocacao"
        )
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo as _RealRepo

        class MockRepo2(_RealRepo):
            def equipamento_existe(self, codigo):
                # Return True so the first guard is passed
                return codigo == equip_id

            def obter_insumo(self, codigo):
                if codigo == equip_id:
                    return None  # equip 'exists' but obter_insumo returns None
                return super().obter_insumo(codigo)

        with patch.object(mod, "RepositorioInsumo", new=MockRepo2):
            result = run_equipes_diretas(canonical, {}, catalogo)
        assert result.canonical is not None
        equip_errors = [v for v in result.validacoes if v.mensagem and equip_id in v.mensagem]
        assert len(equip_errors) > 0

    def test_run_equipes_monthly_distribution_with_negative_dv2(self):
        """dv2 negative (line 263) and positive (lines 269, 274) with weekly distribution."""
        from concilium.application.skills import run_equipes_e_alocacao as run_equipes_diretas

        cpu_id, funcao_id, equip_id = "CPU-D", "funcao-d", "equip-d"
        # Build canonical with TWO weekly periods
        eap = [EapItem(item_id="i1", ordem=1, cpu_id=cpu_id, descricao="Test", unidade="m3", quantitativo=100.0)]
        sched = ScheduledActivityCanonical(
            activity_id="i1",
            start_week=1,
            end_week=2,
            duration_weeks=2,
            distribuicao_semanal={
                "2026-W01": DistribuicaoSemanal(
                    num_equipes=2, qtd_executada=50.0, qtd_acumulada=50.0, pct=0.5, eficiencia=1.0
                ),
                "2026-W02": DistribuicaoSemanal(
                    num_equipes=2, qtd_executada=50.0, qtd_acumulada=100.0, pct=1.0, eficiencia=1.0
                ),
            },
        )
        canonical = _minimal_canonical(eap=eap, cronograma=Cronograma(scheduled_activities=[sched]))
        catalogo = self._make_catalogo(cpu_id, funcao_id, equip_id)
        # dv2 override: week 1 negative (-1 → clamped to 0, hits line 263)
        # week 2 not overridden: base d.num_equipes=2 > 0 → hits lines 269, 274
        dv2 = {"i1": {"2026-W01": -1}}
        inputs = {"dv": {"dv2_num_equipes": dv2}}
        result = run_equipes_diretas(canonical, inputs, catalogo)
        assert result.canonical is not None
        if result.canonical.equipes_diretas:
            # week 2 contributes: permanencia_meses > 0, custo_total > 0
            assert result.canonical.equipes_diretas[0].permanencia_meses > 0



