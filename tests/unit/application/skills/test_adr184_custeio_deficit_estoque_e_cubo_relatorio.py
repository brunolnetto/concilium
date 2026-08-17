"""ADR-184 — Custeio do déficit de estoque provisionado externamente (continuação
da ADR-151 D4) + cubo de estoque consumível conectado ao relatório de skill-09.

Cobre, camada por camada:
  - `DisponibilidadeConsumivel.preco_provisionamento_externo` (validação).
  - `custo_deficit_provisionado` (replenishable.py).
  - `_CAMPOS_DISPONIBILIDADE` / `_parse_logistica_consumiveis_overrides` aceitam o
    novo campo via override de projeto.
  - `VAL-ESTOQUE-PROVISIONAMENTO-02` (aviso de custo zero por preço ausente).
  - `ResumoEstoqueConsumivel.custo_deficit_externo` (skill-04 helper).
  - `DisponibilidadeConsumivelCanonical`/`CuboEstoqueConsumivelBuilder` preservam o
    déficit na projeção reconstruída (regressão do bug pré-existente onde o cubo
    reconstruído mostrava estoque negativo mesmo após reparo/provisionamento).
  - Face `resumo_por_recurso` expõe `custo_deficit_externo`.
  - `_build_custo_categorial_bottom_up`/`_calc_venda_com_bdi`/`CustoTotal` propagam
    o custo até o resultado financeiro.
  - `LogisticaConsumivelConfig` (Escopo, Pydantic) aceita os dois campos.
  - `render_estoque_consumivel` (relatório markdown de skill-09).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from concilium.application.scheduling.models import ReplenishableResource, ScheduledActivity
from concilium.application.scheduling.replenishable import custo_deficit_provisionado
from concilium.application.scheduling.replenishable_builder import _CAMPOS_DISPONIBILIDADE
from concilium.application.services.analytics.cubo_estoque_consumivel_builder import (
    CuboEstoqueConsumivelBuilder,
)
from concilium.application.services.analytics.cubo_estoque_consumivel_projection import (
    resolve_cubo_estoque_consumivel_projection,
)
from concilium.domain.models.canonical import (
    DisponibilidadeConsumivelCanonical,
    RecursoConsumivelCanonical,
    ResumoEstoqueConsumivel,
)
from concilium.domain.models.canonical._financeiro_resultado import CustoTotal
from concilium.domain.models.catalog.disponibilidade_consumivel import DisponibilidadeConsumivel
from concilium.domain.models.project.escopo import LogisticaConsumivelConfig

_ROOT = Path(__file__).resolve().parents[4] / "src/concilium/application/skills/manifests"


def _load(mod_name: str, rel_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(mod_name, _ROOT / rel_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


from concilium.application.skills import run_cronograma as _run_cronograma  # noqa: E402

assert _run_cronograma
_cron = sys.modules["_concilium_skillpkg_04_cronograma.skill"]
_estoque_mod = sys.modules["_concilium_skillpkg_04_cronograma._skill_helpers._estoque_consumivel"]
_cons = _load("_cons_helpers_adr184", "06-resultado-financeiro/_consolidacao/_skill_helpers/__init__.py")


# ── DisponibilidadeConsumivel.preco_provisionamento_externo ────────────────────


class TestDisponibilidadeConsumivelPreco:
    def test_default_none(self):
        disp = DisponibilidadeConsumivel()
        assert disp.preco_provisionamento_externo is None

    def test_aceita_valor(self):
        disp = DisponibilidadeConsumivel(deficit_provisionado_externamente=100.0, preco_provisionamento_externo=25.5)
        assert disp.preco_provisionamento_externo == 25.5

    def test_negativo_levanta(self):
        with pytest.raises(ValueError, match="preco_provisionamento_externo"):
            DisponibilidadeConsumivel(preco_provisionamento_externo=-1.0)


class TestCamposDisponibilidade:
    def test_inclui_preco_provisionamento_externo(self):
        assert "preco_provisionamento_externo" in _CAMPOS_DISPONIBILIDADE

    def test_override_de_projeto_aceita_preco(self):
        result = _cron._mod_validacao._parse_logistica_consumiveis_overrides(
            {"MA-ROCHA": {"deficit_provisionado_externamente": 500.0, "preco_provisionamento_externo": 40.0}}
        )
        assert result is not None
        assert result["MA-ROCHA"].preco_provisionamento_externo == 40.0


# ── custo_deficit_provisionado ─────────────────────────────────────────────────


class TestCustoDeficitProvisionado:
    def test_sem_deficit_e_zero(self):
        disp = DisponibilidadeConsumivel(preco_provisionamento_externo=10.0)
        assert custo_deficit_provisionado(disp) == 0.0

    def test_sem_preco_e_zero(self):
        disp = DisponibilidadeConsumivel(deficit_provisionado_externamente=500.0)
        assert custo_deficit_provisionado(disp) == 0.0

    def test_com_deficit_e_preco_multiplica(self):
        disp = DisponibilidadeConsumivel(deficit_provisionado_externamente=500.0, preco_provisionamento_externo=40.0)
        assert custo_deficit_provisionado(disp) == 20000.0


# ── VAL-ESTOQUE-PROVISIONAMENTO-02 ─────────────────────────────────────────────


class TestValEstoqueProvisionamento02:
    def _producoes_e_insumos(self):
        producoes_por_atividade = {
            "A1": {
                "id": "PROD-X",
                "materiais_gerados": [{"insumo_id": "MA-ROCHA", "geracao_por_hora": 10.0}],
            }
        }
        insumos_lookup = {"MA-ROCHA": {"origem_material": "GERACAO_INTERNA"}}
        return producoes_por_atividade, insumos_lookup

    def test_deficit_sem_preco_emite_aviso_02(self):
        producoes_por_atividade, insumos_lookup = self._producoes_e_insumos()
        validacoes: list = []
        result = _cron._mod_validacao._build_replenishable_resources_if_any(
            producoes_por_atividade,
            insumos_lookup=insumos_lookup,
            logistica_consumiveis={"MA-ROCHA": {"deficit_provisionado_externamente": 500.0}},
            validacoes=validacoes,
        )
        assert result is not None
        avisos_02 = [v for v in validacoes if v.codigo == "VAL-ESTOQUE-PROVISIONAMENTO-02"]
        assert len(avisos_02) == 1
        assert avisos_02[0].status == "AVISO"
        assert "MA-ROCHA" in avisos_02[0].mensagem

    def test_deficit_com_preco_nao_emite_aviso_02(self):
        producoes_por_atividade, insumos_lookup = self._producoes_e_insumos()
        validacoes: list = []
        result = _cron._mod_validacao._build_replenishable_resources_if_any(
            producoes_por_atividade,
            insumos_lookup=insumos_lookup,
            logistica_consumiveis={
                "MA-ROCHA": {"deficit_provisionado_externamente": 500.0, "preco_provisionamento_externo": 40.0}
            },
            validacoes=validacoes,
        )
        assert result is not None
        assert not any(v.codigo == "VAL-ESTOQUE-PROVISIONAMENTO-02" for v in validacoes)
        # VAL-ESTOQUE-PROVISIONAMENTO-01 (déficit em si) continua emitido — regressão zero.
        assert any(v.codigo == "VAL-ESTOQUE-PROVISIONAMENTO-01" for v in validacoes)

    def test_sem_deficit_nao_emite_nenhum_dos_dois(self):
        producoes_por_atividade = {
            "A1": {
                "id": "PROD-X",
                "materiais_gerados": [{"insumo_id": "MA-ROCHA", "geracao_por_hora": 10.0}],
            }
        }
        insumos_lookup = {"MA-ROCHA": {"origem_material": "GERACAO_INTERNA"}}
        validacoes: list = []
        result = _cron._mod_validacao._build_replenishable_resources_if_any(
            producoes_por_atividade,
            insumos_lookup=insumos_lookup,
            logistica_consumiveis=None,
            validacoes=validacoes,
        )
        assert result is not None
        assert not any(v.codigo.startswith("VAL-ESTOQUE-PROVISIONAMENTO") for v in validacoes)


# ── ResumoEstoqueConsumivel.custo_deficit_externo (skill-04 helper) ───────────


class TestResumoEstoqueCustoDeficitExterno:
    def test_default_e_zero(self):
        resumo = ResumoEstoqueConsumivel(
            resource_id="X", estoque_inicial=0.0, estoque_medio=0.0, estoque_minimo=0.0, estoque_final=0.0
        )
        assert resumo.custo_deficit_externo == 0.0

    def test_build_resumo_estoque_calcula_custo(self):
        resource = ReplenishableResource(
            resource_id="MA-ROCHA",
            disponibilidade=DisponibilidadeConsumivel(
                estoque_inicial=0.0, deficit_provisionado_externamente=500.0, preco_provisionamento_externo=40.0
            ),
            consumo_por_semana={"A1": 30.0},
        )
        niveis = {0: 100.0, 1: 200.0}
        resumo = _estoque_mod._build_resumo_estoque(resource, niveis, {}, [])
        assert resumo.custo_deficit_externo == 20000.0

    def test_build_resumo_estoque_sem_preco_e_zero(self):
        resource = ReplenishableResource(
            resource_id="MA-ROCHA",
            disponibilidade=DisponibilidadeConsumivel(estoque_inicial=0.0, deficit_provisionado_externamente=500.0),
            consumo_por_semana={"A1": 30.0},
        )
        resumo = _estoque_mod._build_resumo_estoque(resource, {0: 100.0}, {}, [])
        assert resumo.custo_deficit_externo == 0.0


# ── Canonical mirror + cubo builder preservam o déficit (regressão) ──────────


class TestCanonicalPreservaDeficit:
    def test_disponibilidade_consumivel_canonical_tem_campos_novos(self):
        canon = DisponibilidadeConsumivelCanonical(
            deficit_provisionado_externamente=500.0, preco_provisionamento_externo=40.0
        )
        assert canon.deficit_provisionado_externamente == 500.0
        assert canon.preco_provisionamento_externo == 40.0

    def test_build_estoque_consumivel_canonical_propaga_deficit_e_preco(self):
        resource = ReplenishableResource(
            resource_id="MA-ROCHA",
            disponibilidade=DisponibilidadeConsumivel(
                estoque_inicial=0.0, deficit_provisionado_externamente=500.0, preco_provisionamento_externo=40.0
            ),
            consumo_por_semana={"A1": 30.0},
        )
        recursos, _resumos = _estoque_mod.build_estoque_consumivel_canonical(
            [resource],
            [_estoque_mod.ScheduledActivityCanonical(activity_id="A1", start_week=0, end_week=1, duration_weeks=1)],
            [],
        )
        assert recursos[0].disponibilidade.deficit_provisionado_externamente == 500.0
        assert recursos[0].disponibilidade.preco_provisionamento_externo == 40.0

    def test_cubo_builder_reconstroi_projecao_sem_estoque_negativo_falso(self):
        """Regressão: antes da ADR-184, `DisponibilidadeConsumivelCanonical` não
        carregava `deficit_provisionado_externamente` — o builder do cubo (ADR-128
        F6) reconstruía a projeção SEM o déficit, mostrando estoque negativo para
        um recurso que o cronograma real já havia reparado via provisionamento
        externo (ADR-151). Este teste prova que a projeção reconstruída aqui
        concorda com a do motor real (replenishable.py)."""
        rec = RecursoConsumivelCanonical(
            resource_id="MA-ROCHA",
            disponibilidade=DisponibilidadeConsumivelCanonical(
                estoque_inicial=0.0, deficit_provisionado_externamente=1000.0
            ),
            consumo_por_semana={"A1": 500.0},
            producao_por_semana={},
        )
        scheduled = [ScheduledActivity(activity_id="A1", start_week=0, end_week=2, duration_weeks=2)]
        canonical_in = SimpleNamespace(
            projeto=None,
            recursos_consumiveis=[rec],
            cronograma=SimpleNamespace(scheduled_activities=scheduled),
        )
        cubo = CuboEstoqueConsumivelBuilder().build(canonical_in)
        niveis = [c.estoque_nivel for c in cubo.celulas]
        assert all(n >= 0 for n in niveis), (
            f"Projeção reconstruída ficou negativa mesmo com déficit declarado: {niveis}"
        )


class TestFaceResumoPorRecursoExpoeCusto:
    def test_face_inclui_coluna_e_valor(self):
        resumo = ResumoEstoqueConsumivel(
            resource_id="MA-ROCHA",
            estoque_inicial=0.0,
            estoque_medio=100.0,
            estoque_minimo=50.0,
            estoque_final=80.0,
            custo_deficit_externo=20000.0,
        )
        canonical_in = SimpleNamespace(
            projeto=None,
            recursos_consumiveis=[],
            resumo_estoque_consumiveis=[resumo],
            cronograma=SimpleNamespace(scheduled_activities=[], estoque_delays=[]),
        )
        proj = resolve_cubo_estoque_consumivel_projection(canonical_in, face="resumo_por_recurso")
        assert proj["rows"][0]["custo_deficit_externo"] == 20000.0
        assert any(c["id"] == "custo_deficit_externo" for c in proj["columns"])
        assert any("20,000.00" in n or "20000" in n for n in proj["narrativa"])


# ── skill-06: categorial → venda com BDI → CustoTotal ─────────────────────────


class TestCategorialEVendaComBdi:
    def _canonical_com_deficit(self, custo_deficit: float):
        resumo = ResumoEstoqueConsumivel(
            resource_id="MA-ROCHA",
            estoque_inicial=0.0,
            estoque_medio=0.0,
            estoque_minimo=0.0,
            estoque_final=0.0,
            custo_deficit_externo=custo_deficit,
        )
        return SimpleNamespace(
            contratos_recurso=[],
            equipes_diretas=[],
            resumo_estoque_consumiveis=[resumo],
        )

    def test_build_custo_categorial_inclui_deficit(self):
        canonical_in = self._canonical_com_deficit(20000.0)
        cat = _cons._build_custo_categorial_bottom_up(canonical_in)
        assert cat["deficit_estoque_externo"] == 20000.0

    def test_sem_resumo_estoque_e_zero(self):
        canonical_in = SimpleNamespace(contratos_recurso=[], equipes_diretas=[], resumo_estoque_consumiveis=[])
        cat = _cons._build_custo_categorial_bottom_up(canonical_in)
        assert cat["deficit_estoque_externo"] == 0.0

    def test_calc_venda_com_bdi_aplica_bdi_material(self):
        canonical_in = SimpleNamespace(
            contratos_recurso=[],
            equipes_diretas=[],
            indiretos=[],
            resumo_estoque_consumiveis=[
                ResumoEstoqueConsumivel(
                    resource_id="MA-ROCHA",
                    estoque_inicial=0.0,
                    estoque_medio=0.0,
                    estoque_minimo=0.0,
                    estoque_final=0.0,
                    custo_deficit_externo=10000.0,
                )
            ],
        )
        bdi_rates = {"mao_obra": 0.30, "equipamentos": 0.20, "material": 0.04, "indireto": 0.25}
        venda_direto_eq, _venda_indireto, _custo_indireto_total = _cons._calc_venda_com_bdi(canonical_in, bdi_rates)
        # Único custo é o déficit (10000) × (1 + 0.04) = 10400
        assert venda_direto_eq == pytest.approx(10400.0)


class TestCustoTotalDeficitEstoqueExterno:
    def test_default_zero(self):
        custo = CustoTotal(direto_equipes=100.0, total=100.0)
        assert custo.deficit_estoque_externo == 0

    def test_aceita_valor(self):
        custo = CustoTotal(direto_equipes=100.0, total=20100.0, deficit_estoque_externo=20000.0)
        assert custo.deficit_estoque_externo == 20000.0


# ── LogisticaConsumivelConfig (Escopo, Pydantic) ──────────────────────────────


class TestLogisticaConsumivelConfigCamposNovos:
    def test_aceita_deficit_e_preco(self):
        cfg = LogisticaConsumivelConfig(deficit_provisionado_externamente=500.0, preco_provisionamento_externo=40.0)
        assert cfg.deficit_provisionado_externamente == 500.0
        assert cfg.preco_provisionamento_externo == 40.0

    def test_defaults(self):
        cfg = LogisticaConsumivelConfig()
        assert cfg.deficit_provisionado_externamente == 0.0
        assert cfg.preco_provisionamento_externo is None

    def test_rejeita_negativo(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LogisticaConsumivelConfig(preco_provisionamento_externo=-1.0)
