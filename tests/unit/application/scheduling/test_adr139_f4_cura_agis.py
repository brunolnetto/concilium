"""ADR-139 F4 — Cura de insumos AGIS com código trocado: QA de dados (mendeslobo).

Valida o resultado de `scripts/catalog/cure_insumos_agis_codigo_trocado.py`:

  - Repoints aplicados: cada consumidor aponta para o insumo canônico correto
    (conteúdo real), com rastro do código antigo na descrição da entrada.
  - Erro crítico corrigido: ATI-058/061 consomem MA-CBUQ-FAIXA-C (massa usinada,
    ~R$ 484/t), não CAP puro — material da CPU de CBUQ 3 cm cai de R$ 381,60/m²
    para ~R$ 34,87/m².
  - Códigos mentirosos marcados `_superseded_por` e SEM nenhum consumidor restante
    em todo o catálogo.
  - Produtor-consumidor do CBUQ fechado: usinagem produz, aplicação consome
    (builder → recurso com os dois lados).
  - Idempotência do script.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from concilium.application.scheduling.replenishable_builder import build_replenishable_resources
from scripts.catalog.cure_insumos_agis_codigo_trocado import _REPOINTS, _SUPERSEDED, run_cure

_CAT = Path("config/catalogos/mendeslobo")

pytestmark = pytest.mark.skipif(not _CAT.exists(), reason="catálogo mendeslobo indisponível")


def _load(rel: str) -> dict:
    return json.loads((_CAT / rel).read_text(encoding="utf-8-sig"))


def _materiais(prod: dict) -> list[dict]:
    equipe = prod.get("composicao_padrao_equipe") or prod.get("equipe") or {}
    return equipe.get("materiais") or []


class TestRepointsAplicados:
    @pytest.mark.parametrize("pid", sorted(_REPOINTS))
    def test_consumidor_aponta_para_insumo_canonico(self, pid):
        prod = _load(f"produtividades/{pid}.json")
        insumo_ids = {m["insumo_id"] for m in _materiais(prod)}
        for antigo, (novo, _just) in _REPOINTS[pid].items():
            assert novo in insumo_ids, f"{pid}: esperado {novo}"
            assert antigo not in insumo_ids, f"{pid}: código antigo {antigo} ainda referenciado"

    def test_cbuq_aplicacao_consome_massa_usinada(self):
        """ATI-058: 72 kg/m² de massa a preço de massa (não de CAP)."""
        prod = _load("produtividades/CPU-PAVIM-ATI-058-PROD-001.json")
        (massa,) = [m for m in _materiais(prod) if m["insumo_id"] == "MA-CBUQ-FAIXA-C"]
        insumo = _load("insumos/material/MA-CBUQ-FAIXA-C.json")
        material_por_m2 = massa["consumo_por_hora"] * insumo["preco_unitario"] / prod["producao_horaria"]
        # antes da cura: 381,60/m² (massa a preço de CAP puro); pós-consolidação F4-ter
        # (massa re-concluída a 466,30/t na base de cotações da empresa): ~33,57/m².
        assert material_por_m2 == pytest.approx(33.57, rel=1e-2)


class TestSupersededSemConsumidores:
    def test_marcados_e_orfaos(self):
        consumidos: set[str] = set()
        for sub in ("produtividades", "producoes"):
            for p in (_CAT / sub).glob("*.json"):
                d = json.loads(p.read_text(encoding="utf-8-sig"))
                consumidos.update(m["insumo_id"] for m in _materiais(d))
        for p in (_CAT / "cpus").glob("*.json"):
            d = json.loads(p.read_text(encoding="utf-8-sig"))
            consumidos.update(ci.get("insumo_id") for ci in d.get("composicao_itens") or [])

        for antigo, novo in _SUPERSEDED.items():
            insumo = _load(f"insumos/material/{antigo}.json")
            assert insumo.get("_superseded_por") == novo
            assert antigo not in consumidos, f"{antigo} ainda tem consumidor"


class TestProdutorConsumidorCbuqFechado:
    def test_usinagem_produz_aplicacao_consome(self):
        insumos = {}
        for p in (_CAT / "insumos" / "material").glob("*.json"):
            d = json.loads(p.read_text(encoding="utf-8-sig"))
            insumos[d["codigo"]] = d
        usinagem = _load("produtividades/PROD-USINAGEM-CBUQ-001.json")
        aplicacao = _load("produtividades/CPU-PAVIM-ATI-058-PROD-001.json")
        resources = build_replenishable_resources(
            producoes_por_atividade={"usinagem": usinagem, "cbuq-3cm": aplicacao},
            insumos_por_id=insumos,
            horas_semana=40.0,
        )
        (cbuq,) = [r for r in resources if r.resource_id == "MA-CBUQ-FAIXA-C"]
        assert cbuq.producao_por_semana == {"usinagem": pytest.approx(99.60 * 40)}
        assert cbuq.consumo_por_semana == {"cbuq-3cm": pytest.approx(58.80024 * 40)}


class TestScriptIdempotente:
    def test_reexecucao_nao_altera_nada(self):
        stats = run_cure(apply=False)
        assert stats == {"insumos_criados": 0, "repoints": 0, "superseded_marcados": 0}
