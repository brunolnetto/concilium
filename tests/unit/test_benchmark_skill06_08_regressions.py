from __future__ import annotations

from datetime import UTC, datetime

import pytest

from concilium.application.skills import run_consolidacao_financeira, run_precificacao_unitaria
from concilium.domain.models.canonical import (
    BdiCategorias,
    CanonicalModel,
    Coordenadas,
    EapItem,
    EquipamentoEquipeDireta,
    EquipeDireta,
    FuncaoEquipeDireta,
    Indireto,
    Meta,
    Planejamento,
    PrecoUnitarioCategoria,
    Projeto,
    RegimeTrabalho,
    SubtotalCategorias,
    SubtotalSemBdiComBdi,
)


def _base_canonical() -> CanonicalModel:
    meta = Meta(gerado_em=datetime.now(UTC), contexto_id="test")
    projeto = Projeto(
        id="p1",
        nome="Projeto Teste",
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
        "insumos": [
            {
                "codigo": "INS-1",
                "unidade": "m3",
                "preco_unitario": 10.0,
            }
        ],
        "produtividades": [{"id": "P-1", "valor_horario": 1.0}],
    }


def test_skill06_nep029_sbdi_primary_and_adr038_blocked():
    """NEP-029: precos_unitarios_sbdi é fonte primária; ADR-038 é bloqueado.

    Sem sbdi → composicao_itens (fallback); ADR-038 ignorado mesmo com override.
    Com sbdi  → sbdi em ambos os modos (normal e benchmark).
    """
    canonical = _base_canonical()
    catalogo = _catalogo_minimo()  # CPU sem precos_unitarios_sbdi

    # Modo normal sem sbdi: fallback para composicao_itens → R$10 × 100 = R$1000
    res_sem_sbdi = run_precificacao_unitaria(canonical, {}, catalogo, {})
    assert res_sem_sbdi.canonical.planejamento[0].subtotal.sem_bdi.total == pytest.approx(1000.0)
    codigos = {v.codigo for v in res_sem_sbdi.validacoes}
    assert "VAL-PLAN-SBDI-MISSING" in codigos  # aviso: sbdi ausente

    # ADR-038 override bloqueado → VAL-PLAN-ADR038-BLOCKED emitido, custo não muda
    res_adr038 = run_precificacao_unitaria(canonical, {"apply_adr038_compensation": True}, catalogo, {})
    assert res_adr038.canonical.planejamento[0].subtotal.sem_bdi.total == pytest.approx(1000.0)
    codigos_adr = {v.codigo for v in res_adr038.validacoes}
    assert "VAL-PLAN-ADR038-BLOCKED" in codigos_adr
    assert "VAL-PLAN-PARAMETRICO" not in codigos_adr

    # Com sbdi: usa sbdi em modo normal e benchmark
    catalogo_com_sbdi = {
        **catalogo,
        "cpus": [
            {
                **catalogo["cpus"][0],
                "precos_unitarios_sbdi": {
                    "mo": 8.0,
                    "diesel": 2.0,
                    "material": 0.0,
                    "equipamentos": 0.0,
                    "total": 10.0,
                },
            }
        ],
    }
    res_sbdi_normal = run_precificacao_unitaria(canonical, {}, catalogo_com_sbdi, {})
    res_sbdi_bench = run_precificacao_unitaria(canonical, {"benchmark_mode": True}, catalogo_com_sbdi, {})
    total_normal = res_sbdi_normal.canonical.planejamento[0].subtotal.sem_bdi.total
    total_bench = res_sbdi_bench.canonical.planejamento[0].subtotal.sem_bdi.total
    assert total_normal == pytest.approx(1000.0)  # 100 × sbdi.total(10)
    assert total_bench == pytest.approx(1000.0)
    codigos_sbdi = {v.codigo for v in res_sbdi_normal.validacoes}
    assert "VAL-PLAN-SBDI" in codigos_sbdi
    assert "VAL-PLAN-SBDI-MISSING" not in codigos_sbdi


def test_skill08_does_not_raise_when_ponto_equilibrio_has_no_custo_realizado():
    canonical = _base_canonical()

    # Preços calibrados para frentes_nec ≤ 1.25 (equipe.custo_total=30k, com_bdi=27k):
    # frentes_nec = custo_operacional_real / custo_venda = 30000/27000 = 1.11 — sem VAL-FRENTES ERRO.
    # delta_op = custo_venda - custo_operacional_real = 27k - 30k = -3k → dispara VAL-PE-PARTICAO AVISO.
    planejamento = Planejamento(
        item_id="i1",
        cpu_id="CPU-X",
        quantitativo=100.0,
        preco_unitario=PrecoUnitarioCategoria(material=270.0, diesel=0.0, mao_obra=0.0, equipamentos=0.0, total=270.0),
        bdi=BdiCategorias(material=0.0, diesel=0.0, mao_obra=0.0, equipamentos=0.0),
        preco_unitario_com_bdi=PrecoUnitarioCategoria(
            material=270.0, diesel=0.0, mao_obra=0.0, equipamentos=0.0, total=270.0
        ),
        subtotal=SubtotalSemBdiComBdi(
            sem_bdi=SubtotalCategorias(material=27000.0, diesel=0.0, mao_obra=0.0, equipamentos=0.0, total=27000.0),
            com_bdi=SubtotalCategorias(material=27000.0, diesel=0.0, mao_obra=0.0, equipamentos=0.0, total=27000.0),
        ),
    )
    indireto = Indireto(categoria="ADM", descricao="ADM", custo_total=100.0)

    can = canonical.model_copy(update={"planejamento": [planejamento], "indiretos": [indireto]})
    perfil = {
        "limiar_ponto_equilibrio": 0.05,
        "faixa_margem_alvo": {"min": 0.08, "max": 0.10},
        "faixa_margem_aceitavel": {"min": 0.06, "max": 0.12},
    }

    result = run_consolidacao_financeira(can, {}, perfil)

    assert not result.has_errors
    assert any(v.codigo == "VAL-PONTO-EQUILIBRIO-PARTICAO" for v in result.validacoes)
