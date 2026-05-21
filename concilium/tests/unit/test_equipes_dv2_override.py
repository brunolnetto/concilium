from datetime import UTC, date, datetime

from concilium.application.skills import run_cronograma, run_equipes_e_alocacao
from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    EapItem,
    Meta,
    Praticabilidade,
    Projeto,
    RegimeTrabalho,
)


def test_equipes_respeita_dv2_overrides(config_root, inputs_escopo_terraplenagem):
    # Build canonical with one item spanning Jun-Jul
    meta = Meta(gerado_em=datetime.now(UTC), contexto_id="test")
    proj = Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=0.0, lng=0.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2026, 6, 1),
        data_termino=date(2026, 7, 31),
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )

    prat = Praticabilidade(
        fonte="test",
        limiar_inviabilidade_mm=0,
        calculada_em=datetime.now(UTC),
        percentual_produtivo_mensal={"06": 1.0, "07": 1.0},
    )

    eap = [EapItem(item_id="eap-1", ordem=1, cpu_id="CPU-01", descricao="", unidade="m", quantitativo=100.0)]

    canonical = CanonicalModel(meta=meta, projeto=proj, eap=eap, praticabilidade=prat)

    # Minimal catalog: CPU with simple composition
    catalogo = {
        "cpus": [
            {
                "codigo": "CPU-01",
                "descricao": "",
                "unidade": "m",
                "origem": "PROPRIA",
                "categoria": "DIVERSOS",
                "producao_horaria": 10,
                "composicao_itens": [{"insumo_id": "X", "coeficiente": 1, "categoria_custo": "MAO_OBRA"}],
                "composicao_padrao_equipe": {
                    "equipamentos": [],
                    "funcoes": [{"funcao_id": "OP-1", "num_pessoas": 1}],
                },
            }
        ],
        "insumos": [
            {
                "codigo": "OP-1",
                "tipo": "MAO_OBRA",
                "descricao": "Op",
                "unidade": "mes",
                "preco_unitario": 1000,
                "fonte_preco": "catalogo_proprio",
            }
        ],
    }

    # First, build cronograma with 1 equipe in W23-W27 (covers Jun-Jul)
    inputs_cron = {
        "num_equipes_por_item": {"eap-1": {"2026-W23": 1, "2026-W24": 1, "2026-W25": 1, "2026-W26": 1, "2026-W27": 1}}
    }
    can_with_cron = run_cronograma(canonical, inputs_cron, catalogo).canonical

    # Run equipes_e_alocacao without overrides
    res_default = run_equipes_e_alocacao(can_with_cron, {}, catalogo)
    eq_default = res_default.canonical.equipes_diretas[0]
    perman_default = eq_default.permanencia_meses
    custo_default = eq_default.custo_total

    # Now re-run cronograma with DV2 overrides then run equipes
    # DV2: W23=0, W24=1, W25=1, W26=1, W27=3 (4 active weeks, not 5)
    inputs_cron_dv = {
        "num_equipes_por_item": {"eap-1": {"2026-W23": 0, "2026-W24": 1, "2026-W25": 1, "2026-W26": 1, "2026-W27": 3}}
    }
    can_with_cron_dv = run_cronograma(canonical, inputs_cron_dv, catalogo).canonical
    res_dv = run_equipes_e_alocacao(can_with_cron_dv, {}, catalogo)
    eq_dv = res_dv.canonical.equipes_diretas[0]
    assert eq_dv.permanencia_meses != perman_default
    assert eq_dv.custo_total != custo_default
    # With DV2: W23=0, W24=1, W25=1, W26=1, W27=3 → 4 active weeks (W24-W27)
    # permanencia_meses ≈ 4 / 4.348 ≈ 0.92
    assert 0.5 < eq_dv.permanencia_meses < 1.5
    assert eq_dv.custo_total > 0
