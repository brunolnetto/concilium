from datetime import UTC, date, datetime

from concilium.application.skills import run_cronograma
from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    EapItem,
    Meta,
    Praticabilidade,
    Projeto,
    RecursoPool,
    RegimeTrabalho,
)


def test_cronograma_emite_val_pool_quando_excede_pool():
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
        # fallback mensal para weeks W23-W31 que cobrem jun-jul
        percentual_produtivo_mensal={"06": 1.0, "07": 1.0},
    )

    eap = [
        EapItem(
            item_id="eap-1",
            ordem=1,
            cpu_id="CPU-01",
            descricao="",
            unidade="m",
            quantitativo=100.0,
        )
    ]

    pool = [
        RecursoPool(
            id="r1",
            tipo_id="TRATOR",
            projeto_id="p1",
            quantidade_total=1,
            quantidade_disponivel=1,
        )
    ]

    canonical = CanonicalModel(meta=meta, projeto=proj, eap=eap, praticabilidade=prat, recurso_pool=pool)

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
                    "equipamentos": [{"equip_id": "TRATOR", "num_unidades": 1}],
                    "funcoes": [{"funcao_id": "OPERADOR", "num_pessoas": 1}],
                },
            }
        ]
    }

    inputs = {"num_equipes_por_item": {"eap-1": {"2026-W23": 2}}}

    result = run_cronograma(canonical, inputs, catalogo)

    # Deve haver validação legada VAL-POOL-01 como ERRO
    assert any(v.codigo == "VAL-POOL-01" and v.status == "ERRO" for v in result.validacoes)

    # E também violações estruturadas anexadas ao canônico
    assert result.canonical.constraint_violations
    assert any(cv.code == "VAL-POOL-01" for cv in result.canonical.constraint_violations)
