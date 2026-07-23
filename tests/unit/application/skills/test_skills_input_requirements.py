"""Testes unitários para Skills 00A, 00B, 01A (User Input Requirements)."""

import pytest

from concilium.application.skills import run_catalogo_de_recursos, run_escopo_e_eap
from concilium.application.skills import run_escopo_e_eap as run_atividades
from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    Meta,
    Projeto,
    RegimeTrabalho,
)


class TestSkillAtividades:
    """Testa Skill 00A: Decomposição de atividades."""

    @pytest.fixture
    def canonical_com_eap(self, inputs_escopo_terraplenagem, projeto_terraplenagem):
        """Cria canonical base com EAP populada."""
        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "test",  # Usar contexto estável
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
        }
        result = run_escopo_e_eap(None, inputs, catalogo=None)
        return result.canonical

    def test_modo_trivial_sem_decomposicao(self, inputs_escopo_terraplenagem):
        """Modo trivial: 1 atividade por item EAP, fracao=1.0."""
        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "test",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
        }
        result = run_escopo_e_eap(None, inputs)

        assert not result.has_errors
        assert len(result.canonical.eap) == 3
        assert result.canonical.atividades is not None
        assert len(result.canonical.atividades) == 3

        for eap_item in result.canonical.eap:
            atividades_do_item = [a for a in result.canonical.atividades if a.eap_item_id == eap_item.item_id]
            assert len(atividades_do_item) == 1
            assert atividades_do_item[0].fracao_quantitativo == 1.0

    def test_decomposicao_com_multiplas_atividades(self, inputs_escopo_terraplenagem):
        """Decomposição: múltiplas atividades por EAP item com frações."""
        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "test",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
            "decomposicao": [
                {
                    "eap_item_id": "eap-01",
                    "atividades": [
                        {"atividade_id": "esc-trecho-1", "descricao": "T1", "fracao_quantitativo": 0.4},
                        {"atividade_id": "esc-trecho-2", "descricao": "T2", "fracao_quantitativo": 0.35},
                        {"atividade_id": "esc-trecho-3", "descricao": "T3", "fracao_quantitativo": 0.25},
                    ],
                }
            ],
        }
        result = run_escopo_e_eap(None, inputs)
        assert not result.has_errors
        atividades_primeiro = [a for a in result.canonical.atividades if a.eap_item_id == "eap-01"]
        assert len(atividades_primeiro) == 3
        assert atividades_primeiro[0].fracao_quantitativo == 0.4
        assert abs(atividades_primeiro[0].quantitativo_atividade - (result.canonical.eap[0].quantitativo * 0.4)) < 0.01

    def test_validacao_fracoes_devem_somar_um(self, inputs_escopo_terraplenagem):
        """Validação: frações devem somar 1.0 ± tolerância."""
        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "test",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
            "decomposicao": [
                {
                    "eap_item_id": "eap-01",
                    "atividades": [
                        {"atividade_id": "esc-trecho-1", "descricao": "T1", "fracao_quantitativo": 0.4},
                        {"atividade_id": "esc-trecho-2", "descricao": "T2", "fracao_quantitativo": 0.35},
                        {"atividade_id": "esc-trecho-3", "descricao": "T3", "fracao_quantitativo": 0.1},
                    ],
                }
            ],
        }
        result = run_escopo_e_eap(None, inputs)
        assert result.has_errors
        assert any("VAL-ATV-02" in v.codigo for v in result.validacoes if v.codigo)

    def test_validacao_ref_eap_invalida(self, inputs_escopo_terraplenagem):
        """Validação: decomposições com referências inválidas são ignoradas (esperado)."""
        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "test",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
            "decomposicao": [
                {
                    "eap_item_id": "eap-inexistente",
                    "atividades": [{"atividade_id": "atv1", "descricao": "T1", "fracao_quantitativo": 1.0}],
                }
            ],
        }
        result = run_escopo_e_eap(None, inputs)
        assert not result.has_errors
        assert result.canonical.atividades is not None


class TestSkillSequenciamento:
    """Testa Skill 00B: Sequenciamento (Activity DAG)."""

    @pytest.fixture
    def canonical_com_atividades(self, inputs_escopo_terraplenagem, projeto_terraplenagem):
        """Cria canonical com atividades já decompostas."""
        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "test",  # Usar contexto estável
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
        }
        result_escopo = run_escopo_e_eap(None, inputs, catalogo=None)

        # Decomposição com 3 trechos
        decomposicao = {
            "decomposicao": [
                {
                    "eap_item_id": result_escopo.canonical.eap[0].item_id,
                    "atividades": [
                        {
                            "atividade_id": "esc-trecho-1",
                            "descricao": "Trecho 1",
                            "fracao_quantitativo": 0.4,
                        },
                        {
                            "atividade_id": "esc-trecho-2",
                            "descricao": "Trecho 2",
                            "fracao_quantitativo": 0.35,
                        },
                        {
                            "atividade_id": "esc-trecho-3",
                            "descricao": "Trecho 3",
                            "fracao_quantitativo": 0.25,
                        },
                    ],
                }
            ]
        }
        result_atividades = run_atividades(result_escopo.canonical, decomposicao)
        return result_atividades.canonical

    def test_modo_trivial_sem_precedencias(self, inputs_escopo_terraplenagem):
        """Modo trivial: sem precedências → todas atividades paralelas."""
        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "test",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
        }
        result = run_escopo_e_eap(None, inputs)
        assert not result.has_errors
        assert len(result.canonical.activity_dag.arestas) == 0

    def test_sequenciamento_linear(self, inputs_escopo_terraplenagem):
        """Sequenciamento linear: T1 → T2 → T3."""
        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "test",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
            "decomposicao": [
                {
                    "eap_item_id": "eap-01",
                    "atividades": [
                        {"atividade_id": "atv1", "descricao": "T1", "fracao_quantitativo": 0.4},
                        {"atividade_id": "atv2", "descricao": "T2", "fracao_quantitativo": 0.6},
                    ],
                }
            ],
            "precedencias": [
                {"predecessora": "atv1", "sucessora": "atv2"},
            ],
        }
        result = run_escopo_e_eap(None, inputs)
        assert not result.has_errors
        assert len(result.canonical.activity_dag.arestas) == 1
        assert result.canonical.activity_dag.arestas[0].de == "atv1"
        assert result.canonical.activity_dag.arestas[0].para == "atv2"

    def test_validacao_ciclo_detectado(self, inputs_escopo_terraplenagem):
        """Validação: detectar ciclos (A→B→A)."""
        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "test",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
            "decomposicao": [
                {
                    "eap_item_id": "eap-01",
                    "atividades": [
                        {"atividade_id": "atv1", "descricao": "T1", "fracao_quantitativo": 0.5},
                        {"atividade_id": "atv2", "descricao": "T2", "fracao_quantitativo": 0.5},
                    ],
                }
            ],
            "precedencias": [
                {"predecessora": "atv1", "sucessora": "atv2"},
                {"predecessora": "atv2", "sucessora": "atv1"},
            ],
        }
        result = run_escopo_e_eap(None, inputs)
        assert result.has_errors
        assert any(v.codigo == "VAL-SEQ-01" for v in result.validacoes if v.codigo)

    def test_validacao_ref_atividade_invalida(self, inputs_escopo_terraplenagem):
        """Validação: predecessora/sucessora devem existir."""
        inputs = {
            **inputs_escopo_terraplenagem,
            "contexto_id": "test",
            "snapshot_catalogo_id": "abc",
            "snapshot_perfil_id": "def",
            "precedencias": [{"predecessora": "eap-01-atv-1", "sucessora": "esc-inexistente"}],
        }
        result = run_escopo_e_eap(None, inputs)
        assert result.has_errors
        assert any("VAL-DAG-01" in v.codigo for v in result.validacoes if v.codigo)


class TestSkillDeclararRecursos:
    """Testa Skill 01A: Declaração de recursos."""

    @pytest.fixture
    def canonical_minimo(self):
        """Cria canonical mínimo para testar Skill 01A."""
        from datetime import UTC, datetime

        meta = Meta(gerado_em=datetime.now(UTC), contexto_id="test")
        projeto = Projeto(
            id="proj-test",
            nome="Teste",
            tipo_obra="terraplenagem",
            localizacao="Test",
            coordenadas=Coordenadas(lat=0, lng=0),
            regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
            snapshot_catalogo_id="abc",
            snapshot_perfil_id="def",
        )
        canonical = CanonicalModel(meta=meta, projeto=projeto)
        return canonical

    def test_modo_trivial_sem_recursos(self, canonical_minimo):
        """Modo trivial: sem recursos → pool vazio."""
        result = run_catalogo_de_recursos(canonical_minimo, {})

        assert not result.has_errors
        assert len(result.canonical.tipos_recurso) == 0
        assert len(result.canonical.recurso_pool) == 0

    def test_declaracao_tipos_e_pool(self, canonical_minimo):
        """Declaração completa: tipos + pool inicial."""
        recursos = {
            "tipos_recurso": [
                {
                    "tipo_id": "escavadeira-cat320",
                    "nome": "Escavadeira CAT 320",
                    "categoria": "MAQUINARIO",
                    "custo_unitario_dia": 1200,
                    "especificacoes": {"bucket_m3": 1.2},
                },
                {
                    "tipo_id": "operador",
                    "nome": "Operador",
                    "categoria": "EQUIPE",
                    "custo_unitario_dia": 350,
                },
            ],
            "pool_inicial": [
                {"tipo_id": "escavadeira-cat320", "quantidade_total": 2},
                {"tipo_id": "operador", "quantidade_total": 4},
            ],
        }
        result = run_catalogo_de_recursos(canonical_minimo, recursos)

        assert not result.has_errors
        assert len(result.canonical.tipos_recurso) == 2
        assert len(result.canonical.recurso_pool) == 2
        # Verificar que pool referencia tipos existentes
        pool_tipos = [p.tipo_id for p in result.canonical.recurso_pool]
        assert "escavadeira-cat320" in pool_tipos
        assert "operador" in pool_tipos

    def test_validacao_pool_ref_tipo_invalido(self, canonical_minimo):
        """Validação: pool_inicial com referência inválida gera aviso."""
        recursos = {
            "tipos_recurso": [
                {
                    "tipo_id": "escavadeira",
                    "nome": "Escavadeira",
                    "categoria": "EQUIPAMENTO",
                    "custo_unitario_dia": 1200,
                }
            ],
            "pool_inicial": [
                {"tipo_id": "escavadeira", "quantidade_total": 2},
                {"tipo_id": "inexistente", "quantidade_total": 1},  # ← Aviso!
            ],
        }
        result = run_catalogo_de_recursos(canonical_minimo, recursos)

        # Skill gera aviso, não erro fatal
        assert any("VAL-DECL-02" in v.codigo for v in result.validacoes if v.codigo)
