"""ADR-139/ADR-130 — Usinagem BGTC/CBUQ: preço CONCLUÍDO por composição + grafo de sinergia.

Valida o dado real criado por `scripts/catalog/build_usinagem_bgtc_cbuq.py`:

  - O grafo de sinergia de cada usinagem é válido (sem VAL-SINERGIA-01) e a produção
    efetiva vem DERIVADA do gargalo (fonte "derivado"), igual ao `producao_horaria`
    declarado — a produção não é número de mão.
  - O `preco_unitario` gravado nos usinados é exatamente o concluído bottom-up:
    custo horário (MO + equipamentos + materiais) ÷ produção derivada.
  - Sanidade contra referências públicas (SICRO 202604-SP / mercado 2025): BGTC na
    vizinhança de R$ 308,83/m³ (sem tempo fixo/FIC que não modelamos); CBUQ dentro
    de ~R$ 477–500/t (usinagem 199,84 + CAP 5,545% × R$ 5.200/t).
  - Preço legado preservado em `historico_precos` (92,50 / 385,00).
  - Produtor-consumidor fechado: a usinagem produz `MA-BGTC-MIX` e a base BGTC o
    consome — `build_replenishable_resources` + CP-SAT agendam a cadeia usina→
    pavimentação sem estoque negativo.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from concilium.application.catalog.pu_calculator import derivar_precos_unitarios_sbdi
from concilium.application.scheduling.cpsat_scheduler import CpSatScheduler
from concilium.application.scheduling.models import Activity, ActivityDAG, ResourcePool
from concilium.application.scheduling.replenishable import has_estoque_negativo, project_estoque_semanal
from concilium.application.scheduling.replenishable_builder import build_replenishable_resources
from concilium.domain.models.catalog.producao import Producao
from concilium.domain.services.sinergia_equipe import resolver_producao_efetiva

_CAT = Path("config/catalogos/mendeslobo")

pytestmark = pytest.mark.skipif(not _CAT.exists(), reason="catálogo mendeslobo indisponível")

# Faixas na base de COTAÇÕES DA EMPRESA (consolidação F4-ter: agregados AGIS 2026 +
# cotações 2025-05 com _alerta_preco), abaixo da faixa SICRO-SP — o preço SICRO de
# cada agregado está preservado em historico_precos; ao recotar, o preço re-conclui.
_CASOS = {
    "MA-BGTC-MIX": {
        "producao": "PROD-USINAGEM-BGTC-001",
        "faixa": (235.0, 260.0),  # 245,63; ref. SICRO-SP integral seria ~301–309
        "preco_legado": 92.5,
    },
    "MA-CBUQ-FAIXA-C": {
        "producao": "PROD-USINAGEM-CBUQ-001",
        "faixa": (450.0, 480.0),  # 466,30; com agregados SICRO-SP seria ~484
        "preco_legado": 385.0,
    },
}


def _load(rel: str) -> dict:
    return json.loads((_CAT / rel).read_text(encoding="utf-8-sig"))


def _insumo_index() -> dict[str, dict]:
    index: dict[str, dict] = {}
    for sub in ("material", "equipamento", "mao_obra"):
        for p in (_CAT / "insumos" / sub).glob("*.json"):
            d = json.loads(p.read_text(encoding="utf-8-sig"))
            if isinstance(d, dict) and d.get("codigo"):
                index[d["codigo"]] = d
    return index


@pytest.mark.parametrize("insumo_id", sorted(_CASOS))
class TestPrecoConcluidoPorSinergia:
    def test_producao_derivada_pelo_grafo(self, insumo_id):
        caso = _CASOS[insumo_id]
        producao = Producao.model_validate(_load(f"produtividades/{caso['producao']}.json"))
        resolucao = resolver_producao_efetiva(producao)
        assert resolucao.fonte == "derivado"
        assert resolucao.valor == pytest.approx(producao.producao_horaria)
        assert not any(v.status == "ERRO" for v in resolucao.validacoes)
        assert resolucao.derivacao is not None
        assert resolucao.derivacao.gargalo_derivado == producao.grafo_sinergia.gargalo_declarado

    def test_preco_gravado_igual_ao_concluido(self, insumo_id):
        caso = _CASOS[insumo_id]
        producao = _load(f"produtividades/{caso['producao']}.json")
        insumo = _load(f"insumos/material/{insumo_id}.json")
        sbdi = derivar_precos_unitarios_sbdi(producao, _insumo_index())
        assert not sbdi["_meta"]["referencias_faltantes"]
        assert insumo["preco_unitario"] == pytest.approx(sbdi["total"], rel=1e-4)

    def test_faixa_de_sanidade_referencia_publica(self, insumo_id):
        caso = _CASOS[insumo_id]
        insumo = _load(f"insumos/material/{insumo_id}.json")
        lo, hi = caso["faixa"]
        assert lo <= insumo["preco_unitario"] <= hi

    def test_classificacao_e_historico_preservado(self, insumo_id):
        caso = _CASOS[insumo_id]
        insumo = _load(f"insumos/material/{insumo_id}.json")
        assert insumo["origem_material"] == "GERACAO_INTERNA"
        historicos = [h["preco_unitario"] for h in insumo.get("historico_precos") or []]
        assert caso["preco_legado"] in historicos


class TestCadeiaUsinaPavimentacao:
    def test_usinagem_alimenta_base_bgtc(self):
        insumos = _insumo_index()
        usinagem = _load("produtividades/PROD-USINAGEM-BGTC-001.json")
        base = _load("produtividades/CPU-PAVIM-PAV-BASE-BGTC-PROD-001.json")
        resources = build_replenishable_resources(
            producoes_por_atividade={"usinagem": usinagem, "base": base},
            insumos_por_id=insumos,
            horas_semana=40.0,
        )
        bgtc = [r for r in resources if r.resource_id == "MA-BGTC-MIX"]
        assert len(bgtc) == 1
        assert bgtc[0].producao_por_semana == {"usinagem": pytest.approx(113.18 * 40)}
        assert bgtc[0].consumo_por_semana == {"base": pytest.approx(23.1 * 40)}

        dag = ActivityDAG(
            activities=[
                Activity(
                    activity_id="usinagem", description="Usinagem BGTC", duration_weeks=2, required_resources={"EQ": 1}
                ),
                Activity(activity_id="base", description="Base BGTC", duration_weeks=3, required_resources={"EQ": 1}),
            ]
        )
        output = CpSatScheduler(horizon_weeks=20, timeout_seconds=10).schedule(
            dag, ResourcePool(resources={"EQ": 2}), replenishable_resources=resources
        )
        assert output.feasible
        assert not has_estoque_negativo(project_estoque_semanal(bgtc[0], output.scheduled_activities))
