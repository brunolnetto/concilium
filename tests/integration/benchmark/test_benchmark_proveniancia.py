"""Testes para Proveniência de Benchmark em Projetos (NEP-039 Fase 3)."""

from datetime import date, datetime
from uuid import uuid4

from src.concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    Meta,
    Projeto,
)


class TestBenchmarkProveniancia:
    """Testes para rastreamento de proveniência de benchmark em projetos."""

    def test_meta_pode_registrar_origem_benchmark(self):
        """Meta registra derivado_de_benchmark, benchmark_versao, execution_id."""
        meta = Meta(
            versao_schema="1.0.0",
            gerado_em=datetime.now(),
            contexto_id="test-context",
            escopo_id="default",
            plano_id=None,
            derivado_de_benchmark="AGIS_2025_Q1",
            benchmark_versao=1,
            benchmark_execution_id="exec-abc123",
        )
        assert meta.derivado_de_benchmark == "AGIS_2025_Q1"
        assert meta.benchmark_versao == 1
        assert meta.benchmark_execution_id == "exec-abc123"

    def test_meta_benchmark_opcional(self):
        """Meta pode ser criada sem proveniência (para projetos manuais)."""
        meta = Meta(
            versao_schema="1.0.0",
            gerado_em=datetime.now(),
            contexto_id="test-context",
            escopo_id="default",
            plano_id=None,
        )
        assert meta.derivado_de_benchmark is None
        assert meta.benchmark_versao is None
        assert meta.benchmark_execution_id is None

    def test_canonical_com_proveniancia_benchmark(self):
        """CanonicalModel pode armazenar proveniência via Meta."""
        meta = Meta(
            versao_schema="1.0.0",
            gerado_em=datetime.now(),
            contexto_id="test-context",
            escopo_id="default",
            plano_id=None,
            derivado_de_benchmark="AGIS_2025_Q1",
            benchmark_versao=1,
            benchmark_execution_id="exec-abc123",
        )

        projeto = Projeto(
            id="p-test",
            nome="Teste",
            tipo_obra="terraplenagem",
            localizacao="GO",
            coordenadas=Coordenadas(lat=-10.0, lng=-50.0),
            regime_trabalho={"dias_semana": 6, "horas_dia": 8},
            data_inicio=date(2026, 1, 1),
            data_termino=date(2026, 12, 31),
            status="RASCUNHO",
            snapshot_catalogo_id="snap-1",
            snapshot_perfil_id="perf-1",
        )

        canonical = CanonicalModel(
            meta=meta,
            projeto=projeto,
            praticabilidade=None,
            eap=[],
            cronograma=None,
            planejamento=[],
            equipes_diretas=[],
            indiretos=[],
        )

        # Verifica que proveniência foi preservada
        assert canonical.meta.derivado_de_benchmark == "AGIS_2025_Q1"
        assert canonical.meta.benchmark_versao == 1


class TestBenchmarkProvenianciaIntegracao:
    """Testes de integração: benchmark → projeto com rastreamento."""

    def test_executar_benchmark_registra_proveniancia(self):
        """Executar benchmark cria projeto com proveniância registrada."""
        # Simula execução de benchmark
        benchmark_id = "AGIS_2025_Q1"
        benchmark_versao = 1
        project_id = f"proj-{uuid4()}"
        execution_id = "exec-abc123"

        # Cria Meta com proveniância
        meta = Meta(
            versao_schema="1.0.0",
            gerado_em=datetime.now(),
            contexto_id="real-contexto",
            escopo_id="default",
            plano_id=None,
            derivado_de_benchmark=benchmark_id,
            benchmark_versao=benchmark_versao,
            benchmark_execution_id=execution_id,
        )

        # Cria projeto
        projeto = Projeto(
            id=project_id,
            nome=f"Projeto derivado de {benchmark_id}",
            tipo_obra="terraplenagem",
            localizacao="GO",
            coordenadas=Coordenadas(lat=-10.0, lng=-50.0),
            regime_trabalho={"dias_semana": 6, "horas_dia": 8},
            data_inicio=date(2026, 1, 1),
            data_termino=date(2026, 12, 31),
            status="RASCUNHO",
            snapshot_catalogo_id="snap-1",
            snapshot_perfil_id="perf-1",
        )

        canonical = CanonicalModel(
            meta=meta,
            projeto=projeto,
            praticabilidade=None,
            eap=[],
            cronograma=None,
            planejamento=[],
            equipes_diretas=[],
            indiretos=[],
        )

        # Verifica rastreamento
        assert canonical.meta.derivado_de_benchmark == benchmark_id
        assert canonical.meta.benchmark_versao == benchmark_versao
        assert canonical.meta.benchmark_execution_id == execution_id

    def test_projeto_manual_nao_tem_proveniancia_benchmark(self):
        """Projetos manuais (não derivados) não têm proveniância."""
        meta = Meta(
            versao_schema="1.0.0",
            gerado_em=datetime.now(),
            contexto_id="real-contexto",
            escopo_id="default",
            plano_id=None,
            # Sem proveniância
        )

        projeto = Projeto(
            id="proj-manual",
            nome="Projeto Manual",
            tipo_obra="pavimentacao",
            localizacao="SP",
            coordenadas=Coordenadas(lat=-20.0, lng=-45.0),
            regime_trabalho={"dias_semana": 6, "horas_dia": 8},
            data_inicio=date(2026, 2, 1),
            data_termino=date(2026, 11, 30),
            status="RASCUNHO",
            snapshot_catalogo_id="snap-2",
            snapshot_perfil_id="perf-2",
        )

        canonical = CanonicalModel(
            meta=meta,
            projeto=projeto,
            praticabilidade=None,
            eap=[],
            cronograma=None,
            planejamento=[],
            equipes_diretas=[],
            indiretos=[],
        )

        # Nenhuma proveniância
        assert canonical.meta.derivado_de_benchmark is None
        assert canonical.meta.benchmark_versao is None
        assert canonical.meta.benchmark_execution_id is None

    def test_rastreamento_versao_benchmark(self):
        """Se benchmark foi re-executado (v2), projeto rastreia v2."""
        # Primeiro projeto usando benchmark v1
        canonical_v1 = CanonicalModel(
            meta=Meta(
                versao_schema="1.0.0",
                gerado_em=datetime.now(),
                contexto_id="test",
                derivado_de_benchmark="AGIS_2025_Q1",
                benchmark_versao=1,
                benchmark_execution_id="exec-1",
            ),
            projeto=Projeto(
                id="proj-1",
                nome="Proj v1",
                tipo_obra="terraplenagem",
                localizacao="GO",
                coordenadas=Coordenadas(lat=-10.0, lng=-50.0),
                regime_trabalho={"dias_semana": 6, "horas_dia": 8},
                data_inicio=date(2026, 1, 1),
                data_termino=date(2026, 12, 31),
                status="RASCUNHO",
                snapshot_catalogo_id="snap-1",
                snapshot_perfil_id="perf-1",
            ),
            eap=[],
            cronograma=None,
            planejamento=[],
            equipes_diretas=[],
            indiretos=[],
        )

        # Segundo projeto usando benchmark v2 (após edição e melhoria)
        canonical_v2 = CanonicalModel(
            meta=Meta(
                versao_schema="1.0.0",
                gerado_em=datetime.now(),
                contexto_id="test",
                derivado_de_benchmark="AGIS_2025_Q1",
                benchmark_versao=2,
                benchmark_execution_id="exec-2",
            ),
            projeto=Projeto(
                id="proj-2",
                nome="Proj v2",
                tipo_obra="terraplenagem",
                localizacao="GO",
                coordenadas=Coordenadas(lat=-10.0, lng=-50.0),
                regime_trabalho={"dias_semana": 6, "horas_dia": 8},
                data_inicio=date(2026, 1, 1),
                data_termino=date(2026, 12, 31),
                status="RASCUNHO",
                snapshot_catalogo_id="snap-1",
                snapshot_perfil_id="perf-1",
            ),
            eap=[],
            cronograma=None,
            planejamento=[],
            equipes_diretas=[],
            indiretos=[],
        )

        # Ambos rastreiam sua origem e versão
        assert canonical_v1.meta.benchmark_versao == 1
        assert canonical_v2.meta.benchmark_versao == 2
        assert canonical_v1.meta.benchmark_execution_id == "exec-1"
        assert canonical_v2.meta.benchmark_execution_id == "exec-2"
