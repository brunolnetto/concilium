from datetime import UTC, date, datetime
from importlib import import_module
from types import SimpleNamespace

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


def test_manual_mode_marca_fallback_produtividade_para_cpu_fora_do_catalogo():
    """issue #132: modo MANUAL_ALLOCATION com CPU fora do catálogo sintetiza uma CPU sem
    producao_id_ref (_execute_manual_mode, _validacao.py:244), forçando o fallback de
    produtividade (P=1000). O ScheduledActivityCanonical final deve refletir isso via
    produtividade_fallback_aplicada — sem essa marcação, a correlação com o fallback de
    precificação em skill-06 (VAL-PROD-PU-FALLBACK-DESYNC) nunca dispara para runs em
    modo manual, que é justamente o modo onde a CPU sintética é criada."""
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

    eap = [
        EapItem(
            item_id="eap-1",
            ordem=1,
            cpu_id="CPU-INEXISTENTE",
            descricao="",
            unidade="m",
            quantitativo=100.0,
        )
    ]

    canonical = CanonicalModel(meta=meta, projeto=proj, eap=eap)
    inputs = {"num_equipes_por_item": {"eap-1": {"2026-W23": 2}}}

    result = run_cronograma(canonical, inputs, catalogo={"cpus": []})

    assert any(v.codigo == "VAL-PROD-04" and v.status == "AVISO" for v in result.validacoes)
    sa = next(s for s in result.canonical.cronograma.scheduled_activities if s.activity_id == "eap-1")
    assert sa.produtividade_fallback_aplicada is True


def test_ambiguous_legacy_pool_is_preserved_but_not_physical_capacity():
    pool = RecursoPool(
        id="pool-legacy-ambiguous",
        tipo_id="EQUIP-DECLARED",
        projeto_id="p1",
        quantidade_total=1000,
        quantidade_disponivel=1000,
    )
    assert pool.proveniencia == "LEGACY_UNVERIFIED"

    canonical = CanonicalModel(recurso_pool=[pool])
    extract_pool = import_module(
        "concilium.application.skills.manifests.04-cronograma._skill_helpers._calendario"
    )._extract_pool
    assert extract_pool(canonical).resources == {}
    assert canonical.recurso_pool[0].id == "pool-legacy-ambiguous"


def test_skill05_inferred_pool_is_not_physical_capacity():
    meta = Meta(gerado_em=datetime.now(UTC), contexto_id="test-inferred-pool")
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
    canonical = CanonicalModel(
        meta=meta,
        projeto=proj,
        eap=[
            EapItem(
                item_id="eap-1",
                ordem=1,
                cpu_id="CPU-01",
                descricao="",
                unidade="m",
                quantitativo=100.0,
            )
        ],
        recurso_pool=[
            RecursoPool(
                id="pool-skill05",
                tipo_id="TRATOR",
                projeto_id="p1",
                quantidade_total=1000,
                quantidade_disponivel=1000,
                proveniencia="DERIVADO_SKILL05",
            )
        ],
    )

    extract_pool = import_module(
        "concilium.application.skills.manifests.04-cronograma._skill_helpers._calendario"
    )._extract_pool
    assert extract_pool(canonical).resources == {}

    check_pool = run_cronograma.__globals__["_check_pool_violations"]
    validations = []
    violations = check_pool(
        canonical,
        {"eap-1": {"2026-W23": SimpleNamespace(num_equipes=2)}},
        {
            "CPU-01": {
                "equipe": {"equipamentos": [{"equip_id": "TRATOR", "num_unidades": 1}]}
            }
        },
        validations,
    )
    assert violations == []
    assert not any(v.codigo == "VAL-POOL-01" for v in validations)


def test_legacy_skill05_default_pool_is_classified_as_inferred():
    pool = RecursoPool(
        id="legacy-skill05-pool",
        tipo_id="EQUIP-ESCAV",
        projeto_id="p1",
        quantidade_total=1000,
        quantidade_disponivel=1000,
    )
    assert pool.proveniencia == "DERIVADO_SKILL05"
