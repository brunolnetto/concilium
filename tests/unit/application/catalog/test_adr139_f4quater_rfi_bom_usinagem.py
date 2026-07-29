"""ADR-139 F4-quater — rfi-r02: usinagem CBUQ própria + restauração de BOM: QA de dados.

Valida `scripts/catalog/restore_bom_usinagem_rfi_r02.py` e a classificação de origem:

  - Os 41 materiais pré-existentes do rfi-r02 estão 100% classificados (38 compra
    externa via planilha_rfi_r02/ANTT + 3 solos gerados); o CBUQ novo é GERACAO_INTERNA.
  - Fim dos órfãos relevantes: todo material consumível de aplicação mapeado no BOM
    tem consumidor; as 24 entradas seguem o mapeamento do script (taxa 1:1 com o
    valor_horario ou taxa física explícita).
  - Usinagem CBUQ da casa (E0043): grafo de sinergia deriva a produção (fonte
    "derivado" == declarado) e o preço do MA-CBUQ-FAIXA-C é o concluído bottom-up
    (~R$ 506,92/t com CAP da planilha a R$ 6.091/t).
  - Produtor-consumidor fechado no rfi: usinagem produz massa, CBUQ 3 cm consome.
  - Idempotência do script.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from concilium.application.catalog.pu_calculator import derivar_precos_unitarios_sbdi
from concilium.application.scheduling.replenishable_builder import build_replenishable_resources
from concilium.domain.models.catalog.producao import Producao
from concilium.domain.services.sinergia_equipe import resolver_producao_efetiva
from scripts.catalog.restore_bom_usinagem_rfi_r02 import _BOM, run_restore

_CAT = Path("config/catalogos/rfi-r02")

pytestmark = pytest.mark.skipif(not _CAT.exists(), reason="catálogo rfi-r02 indisponível")


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


class TestClassificacaoCompleta:
    def test_todos_materiais_classificados(self):
        docs = [
            json.loads(p.read_text(encoding="utf-8-sig"))
            for p in sorted((_CAT / "insumos" / "material").glob("*.json"))
        ]
        sem_classe = [d["codigo"] for d in docs if not d.get("origem_material")]
        # ADR-165/167: 10 EPIs (prefixo EPI-) replicados de mendeslobo não são material
        # de construção — origem_material (compra externa x geração interna de obra)
        # não se aplica a EPI, mesmo gap já documentado para mendeslobo (ADR-139 F1bis).
        assert all(codigo.startswith("EPI-") for codigo in sem_classe)
        gerados = {d["codigo"] for d in docs if d.get("origem_material") == "GERACAO_INTERNA"}
        assert gerados == {
            "MA-SOLO-ESCAVADO-1CAT",
            "MA-SOLO-ESCAVADO-2CAT",
            "MA-SOLO-ESCAVADO-3CAT",
            "MA-CBUQ-FAIXA-C",
        }


class TestBomRestaurado:
    @pytest.mark.parametrize("pid", sorted(_BOM))
    def test_entradas_conforme_mapeamento(self, pid):
        prod = _load(f"produtividades/{pid}.json")
        equipe = prod.get("composicao_padrao_equipe") or prod.get("equipe") or {}
        materiais = {m["insumo_id"]: m for m in equipe.get("materiais") or []}
        for insumo_id, taxa, _unidade, _just in _BOM[pid]:
            assert insumo_id in materiais, f"{pid}: falta {insumo_id}"
            esperado = taxa if taxa is not None else prod["valor_horario"]
            assert materiais[insumo_id]["consumo_por_hora"] == pytest.approx(esperado)
            assert materiais[insumo_id]["origem_entrada"] == "bom_convertido"

    def test_integridade_referencial_do_bom(self):
        index = _insumo_index()
        for pid, entradas in _BOM.items():
            for insumo_id, _taxa, _unidade, _just in entradas:
                assert insumo_id in index, f"{pid}: insumo {insumo_id} inexistente"


class TestUsinagemCbuqDaCasa:
    def test_producao_derivada_pelo_grafo(self):
        producao = Producao.model_validate(_load("producoes/PROD-USINAGEM-CBUQ-RFI-001.json"))
        resolucao = resolver_producao_efetiva(producao)
        assert resolucao.fonte == "derivado"
        assert resolucao.valor == pytest.approx(producao.valor_horario)
        assert resolucao.derivacao.gargalo_derivado == "E0043"

    def test_preco_concluido_gravado(self):
        producao = _load("producoes/PROD-USINAGEM-CBUQ-RFI-001.json")
        insumo = _load("insumos/material/MA-CBUQ-FAIXA-C.json")
        sbdi = derivar_precos_unitarios_sbdi(producao, _insumo_index())
        assert not sbdi["_meta"]["referencias_faltantes"]
        assert insumo["preco_unitario"] == pytest.approx(sbdi["total"], rel=1e-4)
        # CAP da planilha (R$ 6.091/t) domina: ~R$ 507/t, acima do mendeslobo (466,30)
        assert 495.0 <= insumo["preco_unitario"] <= 520.0

    def test_produtor_consumidor_cbuq_fechado(self):
        index = _insumo_index()
        usinagem = _load("producoes/PROD-USINAGEM-CBUQ-RFI-001.json")
        aplicacao = _load("produtividades/CPU-TERRA-ATI-058-PROD-001.json")
        resources = build_replenishable_resources(
            producoes_por_atividade={"usinagem": usinagem, "cbuq-3cm": aplicacao},
            insumos_por_id=index,
            horas_semana=40.0,
        )
        (cbuq,) = [r for r in resources if r.resource_id == "MA-CBUQ-FAIXA-C"]
        assert cbuq.producao_por_semana == {"usinagem": pytest.approx(99.60 * 40)}
        assert cbuq.consumo_por_semana == {"cbuq-3cm": pytest.approx(58.80024 * 40)}


class TestScriptIdempotente:
    def test_reexecucao_nao_altera_nada(self):
        stats = run_restore(apply=False)
        assert stats["insumos_criados"] == 0
        assert stats["producoes_criadas"] == 0
        assert stats["bom_entradas"] == 0
