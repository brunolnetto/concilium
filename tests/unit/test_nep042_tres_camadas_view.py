"""NEP-042 D4 — View consolidada de três camadas de precificação.

TDD: testes escritos antes da implementação de _build_tres_camadas_rows.

A view apresenta, por item, as três camadas lado a lado:
  PU_cat (catálogo) | PU_op_autonomo (operacional) | PU_pool (burden instancial)
+ frentes_necessarias, eta_real, economia_pool_abs/pct.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest


def _load_helpers():
    path = (
        Path(__file__).resolve().parents[2]
        / "src/concilium/application/skills/manifests"
        / "09-relatorio-e-artefatos/_skill_helpers_a.py"
    )
    spec = importlib.util.spec_from_file_location("sk09_helpers_nep042", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _canonical():
    from concilium.domain.models.canonical import (
        CanonicalModel,
        Coordenadas,
        EapItem,
        Meta,
        Planejamento,
        PontoEquilibrio,
        PrecoUnitarioCategoria,
        Projeto,
        RegimeTrabalho,
        SubtotalCategorias,
        SubtotalSemBdiComBdi,
    )

    meta = Meta(gerado_em=datetime.now(UTC), contexto_id="test")
    projeto = Projeto(
        id="p1",
        nome="T",
        tipo_obra="terraplenagem",
        localizacao="BR",
        coordenadas=Coordenadas(lat=0, lng=0),
        regime_trabalho=RegimeTrabalho(dias_semana=6, horas_dia=8),
        data_inicio="2026-01-01",
        data_termino="2026-12-31",
        snapshot_catalogo_id="c",
        snapshot_perfil_id="p",
    )
    eap = [EapItem(item_id="i1", ordem=1, cpu_id="CPU-1", descricao="Escavação", unidade="m3", quantitativo=1000.0)]
    plan = [
        Planejamento(
            item_id="i1",
            cpu_id="CPU-1",
            quantitativo=1000.0,
            preco_unitario=PrecoUnitarioCategoria(material=0, diesel=0, mao_obra=0, equipamentos=0, total=500.0),
            bdi={"material": 0.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0},
            preco_unitario_com_bdi=PrecoUnitarioCategoria(
                material=0, diesel=0, mao_obra=0, equipamentos=0, total=575.0
            ),
            subtotal=SubtotalSemBdiComBdi(
                sem_bdi=SubtotalCategorias(material=0, diesel=0, mao_obra=0, equipamentos=0, total=500_000.0),
                com_bdi=SubtotalCategorias(material=0, diesel=0, mao_obra=0, equipamentos=0, total=575_000.0),
            ),
        )
    ]
    pe = [
        PontoEquilibrio(
            item_id="i1",
            custo_fixo_equipe=600_000.0,
            custo_venda_cpu=575_000.0,
            delta=-25_000.0,
            delta_pct=-0.043,
            status_validacao="AVISO",
            pu_operacional_autonomo=600.0,
            eta_real=0.85,
            custo_pool_total=540_000.0,
            custo_pool_por_unidade=540.0,
            economia_pool_abs=60_000.0,
            frentes_equivalentes_necessarias=1.2,
        )
    ]
    return CanonicalModel(meta=meta, projeto=projeto, eap=eap, planejamento=plan, ponto_equilibrio=pe)


class TestBuildTresCamadasRows:
    def test_funcao_existe(self):
        mod = _load_helpers()
        assert hasattr(mod, "_build_tres_camadas_rows")

    def test_uma_linha_por_item(self):
        mod = _load_helpers()
        rows = mod._build_tres_camadas_rows(_canonical())
        assert len(rows) == 1
        assert rows[0]["item_id"] == "i1"

    def test_tres_pus_presentes(self):
        mod = _load_helpers()
        row = mod._build_tres_camadas_rows(_canonical())[0]
        assert row["pu_cat"] == pytest.approx(500.0)
        assert row["pu_op_autonomo"] == pytest.approx(600.0)
        assert row["pu_pool"] == pytest.approx(540.0)

    def test_frentes_e_eta(self):
        mod = _load_helpers()
        row = mod._build_tres_camadas_rows(_canonical())[0]
        assert row["frentes_necessarias"] == pytest.approx(1.2)
        assert row["eta_real"] == pytest.approx(0.85)

    def test_economia_pool(self):
        mod = _load_helpers()
        row = mod._build_tres_camadas_rows(_canonical())[0]
        assert row["economia_pool_abs"] == pytest.approx(60_000.0)
        # economia_pct = economia / custo_autonomo = 60000 / 600000 = 10%
        assert row["economia_pool_pct"] == pytest.approx(0.10, abs=0.01)

    def test_descricao_e_unidade(self):
        mod = _load_helpers()
        row = mod._build_tres_camadas_rows(_canonical())[0]
        assert row["descricao"] == "Escavação"
        assert row["unidade"] == "m3"

    def test_sem_pe_nao_quebra(self):
        from concilium.domain.models.canonical import (
            CanonicalModel,
            Coordenadas,
            Meta,
            Projeto,
            RegimeTrabalho,
        )

        mod = _load_helpers()
        meta = Meta(gerado_em=datetime.now(UTC), contexto_id="test")
        projeto = Projeto(
            id="p1",
            nome="T",
            tipo_obra="terraplenagem",
            localizacao="BR",
            coordenadas=Coordenadas(lat=0, lng=0),
            regime_trabalho=RegimeTrabalho(dias_semana=6, horas_dia=8),
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
            snapshot_catalogo_id="c",
            snapshot_perfil_id="p",
        )
        can = CanonicalModel(meta=meta, projeto=projeto, eap=[], planejamento=[], ponto_equilibrio=[])
        rows = mod._build_tres_camadas_rows(can)
        assert rows == []
