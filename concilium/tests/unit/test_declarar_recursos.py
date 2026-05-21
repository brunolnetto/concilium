from datetime import UTC, datetime

from concilium.application.skills import run_catalogo_de_recursos
from concilium.domain.models.canonical import CanonicalModel, Coordenadas, Meta, Projeto, RegimeTrabalho


def _minimal_canonical():
    meta = Meta(gerado_em=datetime.now(UTC), contexto_id="test")
    proj = Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=0.0, lng=0.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio="2026-06-01",
        data_termino="2026-12-31",
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )
    return CanonicalModel(meta=meta, projeto=proj)


def test_val_rec01_unknown_tipo_referencia():
    can = _minimal_canonical()
    inputs = {"pool_inicial": [{"tipo_id": "UNKNOWN-TIPO", "quantidade_total": 2}]}
    res = run_catalogo_de_recursos(can, inputs, catalogo={})
    # Deve ter erro VAL-REC-01 e aviso compat VAL-DECL-02
    codigos = {v.codigo: v.status for v in res.validacoes}
    assert "VAL-REC-01" in codigos and codigos["VAL-REC-01"] == "ERRO"
    assert "VAL-DECL-02" in codigos


def test_val_rec02_nonpositive_quantidade():
    can = _minimal_canonical()
    tipos = [{"id": "TRATOR", "nome": "Trator", "categoria": "EQUIPAMENTO", "custo_unitario_dia": 0}]
    inputs = {"tipos_recurso": tipos, "pool_inicial": [{"tipo_id": "TRATOR", "quantidade_total": 0}]}
    res = run_catalogo_de_recursos(can, inputs, catalogo={})
    codigos = {v.codigo: v.status for v in res.validacoes}
    assert "VAL-REC-02" in codigos and codigos["VAL-REC-02"] == "ERRO"


def test_val_decl01_tipo_sem_id():
    """tipos_recurso entry sem nenhum id/tipo/tipo_id deve emitir VAL-DECL-01 AVISO."""
    can = _minimal_canonical()
    inputs = {"tipos_recurso": [{"nome": "Semid", "categoria": "EQUIPAMENTO", "custo_unitario_dia": 0}]}
    res = run_catalogo_de_recursos(can, inputs, catalogo={})
    codigos = {v.codigo: v.status for v in res.validacoes}
    assert "VAL-DECL-01" in codigos and codigos["VAL-DECL-01"] == "AVISO"


def test_templates_recursos_adiciona_novo_tipo():
    """templates_recursos deve pré-declarar tipos que ainda não existem."""
    can = _minimal_canonical()
    inputs = {
        "templates_recursos": {
            "default": [
                {"tipo": "ESCAVADEIRA", "nome": "Escavadeira", "categoria": "EQUIPAMENTO", "custo_unitario_dia": 500}
            ]
        }
    }
    res = run_catalogo_de_recursos(can, inputs, catalogo={})
    tipos_ids = [t.id for t in res.canonical.tipos_recurso]
    assert "ESCAVADEIRA" in tipos_ids


def test_templates_recursos_nao_sobrescreve_tipo_existente():
    """templates_recursos não deve sobrescrever tipo já declarado via tipos_recurso."""
    can = _minimal_canonical()
    inputs = {
        "tipos_recurso": [
            {"id": "MOTONIVELADORA", "nome": "Moto Original", "categoria": "EQUIPAMENTO", "custo_unitario_dia": 1000}
        ],
        "templates_recursos": {
            "default": [{"tipo": "MOTONIVELADORA", "nome": "Moto Template", "custo_unitario_dia": 500}]
        },
    }
    res = run_catalogo_de_recursos(can, inputs, catalogo={})
    tipo = next(t for t in res.canonical.tipos_recurso if t.id == "MOTONIVELADORA")
    assert tipo.nome == "Moto Original"  # original preserved


def test_pool_vazio_sem_pools_existentes_gera_unitario():
    """Quando pool_inicial não gera nenhum pool e não há pools existentes, cria 1 pool por tipo."""
    can = _minimal_canonical()
    inputs = {
        "tipos_recurso": [{"id": "TRATOR", "nome": "Trator", "categoria": "EQUIPAMENTO", "custo_unitario_dia": 0}],
        # No pool_inicial — triggers fallback
    }
    res = run_catalogo_de_recursos(can, inputs, catalogo={})
    pools = res.canonical.recurso_pool
    assert len(pools) >= 1
    assert any(p.tipo_id == "TRATOR" for p in pools)
