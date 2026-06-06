#!/usr/bin/env python
"""Script de validação da implementação ADR-103.

Valida que:
1. Módulo pode ser importado
2. JobService pode ser inicializado
3. Jobs podem ser criados e consultados
4. DTOs funcionam corretamente
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

def main():
    print("=" * 60)
    print("ADR-103 - Validação de Implementação")
    print("=" * 60)
    
    # Test 1: Import
    print("\n[1/5] Testando imports...")
    try:
        from concilium.application.jobs import (
            get_job_service,
            JobDTO,
            JobListDTO,
            JobStatsDTO,
            SystemStatsDTO,
            PipelineJobStateMachine,
            JobRepository,
        )
        print("    ✓ Todos os exports públicos disponíveis")
    except ImportError as e:
        print(f"    ✗ Erro de import: {e}")
        return 1
    
    # Test 2: Service initialization
    print("\n[2/5] Testando inicialização do serviço...")
    try:
        from concilium.application.jobs.service import reset_job_service
        from concilium.application.jobs.repository import reset_repository
        
        reset_job_service()
        reset_repository()
        
        service = get_job_service()
        print(f"    ✓ JobService inicializado: {type(service).__name__}")
    except Exception as e:
        print(f"    ✗ Erro na inicialização: {e}")
        return 1
    
    # Test 3: Create job (mock dependencies)
    print("\n[3/5] Testando criação de job...")
    try:
        from unittest.mock import Mock
        from concilium.infrastructure.settings import JobsSettings
        from concilium.application.jobs.repository import InMemoryJobRepository
        from concilium.application.jobs.service import JobService
        
        config = JobsSettings(max_concurrent_jobs=1, job_ttl_hours=1, job_gc_interval_minutes=5)
        repo = InMemoryJobRepository()
        
        mock_runtime = Mock()
        mock_project = Mock()
        
        service = JobService(
            repository=repo,
            config=config,
            runtime_factory=lambda: mock_runtime,
            project_factory=lambda pid: mock_project,
        )
        
        job = service.disparar_pipeline(
            project_id="test-project",
            skill_id="01-composicao",
            inputs={"test": "data"},
        )
        
        print(f"    ✓ Job criado: {job.job_id}")
        print(f"    ✓ Status: {job.status}")
        assert job.status == "AGUARDANDO_FILA"
        assert job.project_id == "test-project"
        assert job.skill_id == "01-composicao"
    except Exception as e:
        print(f"    ✗ Erro na criação: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Test 4: Query job
    print("\n[4/5] Testando consulta de job...")
    try:
        consultado = service.consultar_job(job.job_id)
        print(f"    ✓ Job consultado: {consultado.job_id}")
        assert consultado.job_id == job.job_id
    except Exception as e:
        print(f"    ✗ Erro na consulta: {e}")
        return 1
    
    # Test 5: List jobs and statistics
    print("\n[5/5] Testando listagem e estatísticas...")
    try:
        job_list = service.listar_jobs()
        print(f"    ✓ Jobs listados: {len(job_list.jobs)}")
        assert len(job_list.jobs) >= 1
        
        stats = service.obter_estatisticas()
        print(f"    ✓ Estatísticas: {stats.contadores['total_jobs_ativos']} jobs ativos")
        assert stats.contadores['total_jobs_ativos'] >= 1
    except Exception as e:
        print(f"    ✗ Erro na listagem: {e}")
        return 1
    
    # Summary
    print("\n" + "=" * 60)
    print("✅ TODAS AS VALIDAÇÕES PASSARAM")
    print("=" * 60)
    print("\nImplementação ADR-103 funcionando corretamente!")
    print("\nArquivos criados:")
    print("  • src/concilium/application/jobs/models.py")
    print("  • src/concilium/application/jobs/state.py")
    print("  • src/concilium/application/jobs/repository.py")
    print("  • src/concilium/application/jobs/service.py")
    print("  • src/concilium/application/jobs/__init__.py")
    print("\nArquivos atualizados:")
    print("  • src/concilium/presentation/mcp/tools/pipeline.py")
    print("\nArquivos removidos:")
    print("  • src/concilium/presentation/mcp/pipeline_jobs.py")
    print("  • src/concilium/presentation/mcp/pipeline_job_state.py")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
