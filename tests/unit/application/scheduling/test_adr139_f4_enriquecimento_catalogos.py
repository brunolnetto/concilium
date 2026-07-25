"""ADR-139 F4 — Enriquecimento produtor-consumidor (`rfi-r02` + `mendeslobo`): QA de dados.

Mesma filosofia dos testes de cluster da ADR-130 F4: valida o dado real dos catálogos
após `scripts/catalog/enrich_produtor_consumidor.py`, usando o próprio mapeamento
declarativo do script como fonte única de expectativa:

  - Censo por catálogo (rfi-r02: 8 produtoras / 5 consumidoras; mendeslobo: 6 / 7),
    com 3 insumos GERACAO_INTERNA em cada.
  - Toda entrada do mapeamento presente no dado, com taxa correta (valor_horario ou
    taxa explícita — ex.: rebaixo 20 cm) e `origem_entrada="bom_convertido"`.
  - Integridade referencial (VAL-PROD-GERACAO-01) e balanço de massas fechado
    (todo material gerado consumido tem produtora no mesmo catálogo).
  - E2E por catálogo no CP-SAT via `build_replenishable_resources`.
  - Idempotência: reexecutar o script não altera nada.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from concilium.application.scheduling.cpsat_scheduler import CpSatScheduler
from concilium.application.scheduling.models import Activity, ActivityDAG, ResourcePool
from concilium.application.scheduling.replenishable import has_estoque_negativo, project_estoque_semanal
from concilium.application.scheduling.replenishable_builder import build_replenishable_resources
from scripts.catalog.enrich_produtor_consumidor import _CONSUMIDORAS, _PRODUTORAS

_CATALOGOS = Path("config/catalogos")

pytestmark = pytest.mark.skipif(not _CATALOGOS.exists(), reason="catálogos indisponíveis")

_SOLOS = {"MA-SOLO-ESCAVADO-1CAT", "MA-SOLO-ESCAVADO-2CAT", "MA-SOLO-ESCAVADO-3CAT"}

# produtoras_dado inclui as usinagens (PROD-USINAGEM-*): 2 no mendeslobo
# (build_usinagem_bgtc_cbuq.py) e 1 no rfi-r02 (restore_bom_usinagem_rfi_r02.py),
# além das mapeadas pelo script de enriquecimento. mendeslobo ganhou +6 em F5-ter
# (cure_producao_escavacao_solo_mendeslobo.py): as 6 escavações 1CAT/2CAT/3CAT ×
# DMT2000/3000 passam a declarar materiais_gerados, replicando o padrão já
# correto de rfi-r02 (achado 2026-07-25: AGIS consumia esses materiais sem
# nenhum produtor vinculado).
_ESPERADO = {
    "rfi-r02": {"produtoras_dado": 9, "consumidoras": 5, "gerados": _SOLOS | {"MA-CBUQ-FAIXA-C"}},
    "mendeslobo": {
        "produtoras_dado": 14,
        "consumidoras": 7,
        "gerados": _SOLOS | {"MA-BGTC-MIX", "MA-CBUQ-FAIXA-C"},
    },
}


def _load(cat: str, rel: str) -> dict:
    return json.loads((_CATALOGOS / cat / rel).read_text(encoding="utf-8-sig"))


def _all_producoes(cat: str) -> list[dict]:
    docs = []
    for sub in ("produtividades", "producoes"):
        d = _CATALOGOS / cat / sub
        if d.is_dir():
            docs.extend(json.loads(p.read_text(encoding="utf-8-sig")) for p in sorted(d.glob("*.json")))
    return docs


def _insumos_material(cat: str) -> dict[str, dict]:
    docs = [
        json.loads(p.read_text(encoding="utf-8-sig"))
        for p in sorted((_CATALOGOS / cat / "insumos" / "material").glob("*.json"))
    ]
    return {d["codigo"]: d for d in docs}


def _equipe(prod: dict) -> dict:
    return prod.get("composicao_padrao_equipe") or prod.get("equipe") or {}


def _consumos_gerados(prod: dict) -> list[dict]:
    return [
        m
        for m in _equipe(prod).get("materiais") or []
        if m.get("origem_entrada") == "bom_convertido" and m["insumo_id"].startswith("MA-SOLO-ESCAVADO-")
    ]


@pytest.mark.parametrize("cat", sorted(_ESPERADO))
class TestCensoEnriquecimento:
    def test_insumos_gerados_classificados(self, cat):
        insumos = _insumos_material(cat)
        gerados = {c for c, d in insumos.items() if d.get("origem_material") == "GERACAO_INTERNA"}
        assert gerados == _ESPERADO[cat]["gerados"]
        for codigo in gerados & _SOLOS:
            d = insumos[codigo]
            # Solo de corte: custo já capturado na CPU produtora (convenção D1) + pilha limitada
            assert d["preco_unitario"] == 0.0
            disp = (d.get("atributos_especificos") or {}).get("disponibilidade") or {}
            assert disp.get("capacidade_armazenamento") == 50000.0
        for codigo in gerados - _SOLOS:
            # Usinados: custo interno de produção concluído bottom-up (> 0)
            assert insumos[codigo]["preco_unitario"] > 0.0

    def test_produtoras_conforme_mapeamento(self, cat):
        produtoras = [p for p in _all_producoes(cat) if p.get("materiais_gerados")]
        assert len(produtoras) == _ESPERADO[cat]["produtoras_dado"]
        for rel, (insumo_id, taxa, _just) in _PRODUTORAS[cat].items():
            prod = _load(cat, rel)
            gerados = [g for g in prod.get("materiais_gerados") or [] if g["insumo_id"] == insumo_id]
            assert len(gerados) == 1, f"{cat}:{rel}"
            esperada = taxa if taxa is not None else prod["valor_horario"]
            assert gerados[0]["geracao_por_hora"] == pytest.approx(esperada)
            assert "ADR-139" in (gerados[0].get("descricao") or "")

    def test_consumidoras_conforme_mapeamento(self, cat):
        consumidoras = [p for p in _all_producoes(cat) if _consumos_gerados(p)]
        assert len(consumidoras) == _ESPERADO[cat]["consumidoras"]
        assert len(_CONSUMIDORAS[cat]) == _ESPERADO[cat]["consumidoras"]
        for rel, (insumo_id, taxa, _just) in _CONSUMIDORAS[cat].items():
            prod = _load(cat, rel)
            mats = [m for m in _equipe(prod).get("materiais") or [] if m["insumo_id"] == insumo_id]
            assert len(mats) == 1, f"{cat}:{rel}"
            esperada = taxa if taxa is not None else prod["valor_horario"]
            assert mats[0]["consumo_por_hora"] == pytest.approx(esperada)
            assert mats[0]["origem_entrada"] == "bom_convertido"


@pytest.mark.parametrize("cat", sorted(_ESPERADO))
class TestIntegridadeReferencial:
    def test_todo_material_gerado_referencia_insumo_geracao_interna(self, cat):
        """VAL-PROD-GERACAO-01 sobre o catálogo inteiro."""
        insumos = _insumos_material(cat)
        for p in _all_producoes(cat):
            for g in p.get("materiais_gerados") or []:
                insumo = insumos.get(g["insumo_id"])
                assert insumo is not None, f"{cat}:{p['id']}: insumo '{g['insumo_id']}' inexistente"
                assert insumo.get("origem_material") == "GERACAO_INTERNA", f"{cat}:{p['id']}"

    def test_balanco_de_massas_fechado(self, cat):
        """Todo material gerado consumido tem ao menos uma produtora no mesmo catálogo."""
        producoes = _all_producoes(cat)
        produzidos = {g["insumo_id"] for p in producoes for g in p.get("materiais_gerados") or []}
        consumidos_gerados = {m["insumo_id"] for p in producoes for m in _consumos_gerados(p)}
        assert consumidos_gerados <= produzidos


class TestEndToEnd:
    def test_rfi_r02_corte_1cat_alimenta_compactacao_pn(self):
        insumos = _insumos_material("rfi-r02")
        corte = _load("rfi-r02", "produtividades/CPU-TERRA-ESCO-CARGA-1CAT-DMT2000-PROD-001.json")
        compac = _load("rfi-r02", "produtividades/CPU-TERRA-COMPAC-PN-PROD-001.json")
        self._roda_piloto(insumos, corte, compac)

    def test_mendeslobo_escavacao_alimenta_aterro(self):
        insumos = _insumos_material("mendeslobo")
        corte = _load("mendeslobo", "producoes/PROD-ATI-011.json")
        aterro = _load("mendeslobo", "producoes/PROD-ATI-017.json")
        self._roda_piloto(insumos, corte, aterro)

    @staticmethod
    def _roda_piloto(insumos: dict, produtora: dict, consumidora: dict) -> None:
        resources = build_replenishable_resources(
            producoes_por_atividade={"corte": produtora, "aterro": consumidora},
            insumos_por_id=insumos,
            horas_semana=40.0,
        )
        solo = [r for r in resources if r.resource_id == "MA-SOLO-ESCAVADO-1CAT"]
        assert len(solo) == 1
        dag = ActivityDAG(
            activities=[
                Activity(activity_id="corte", description="Corte", duration_weeks=3, required_resources={"EQ": 1}),
                Activity(activity_id="aterro", description="Aterro", duration_weeks=3, required_resources={"EQ": 1}),
            ]
        )
        output = CpSatScheduler(horizon_weeks=20, timeout_seconds=10).schedule(
            dag, ResourcePool(resources={"EQ": 2}), replenishable_resources=resources
        )
        assert output.feasible
        assert not has_estoque_negativo(project_estoque_semanal(solo[0], output.scheduled_activities))


class TestScriptIdempotente:
    def test_reexecucao_nao_altera_nada(self):
        from scripts.catalog.enrich_produtor_consumidor import run_enrichment

        stats = run_enrichment(apply=False)
        assert stats == {"insumos_criados": 0, "produtoras_enriquecidas": 0, "consumidoras_enriquecidas": 0}
