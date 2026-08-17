#!/usr/bin/env python3
"""
Script para executar a pipeline no PLANO (nível correto - dentro do ESCOPO).

Uso:
    python scripts/run_cmoc_pipeline_plano.py

Estrutura esperada:
    projetos/
    └── c5ae6948-31f3-4aa9-b65e-f7eb780662f8/
        └── escopos/esc-principal/
            └── planos/04061400-b23e-4e71-affc-218d6fd0e9f9/
                ├── canonical.json
                └── outputs/
"""

from pathlib import Path
import sys
import json

def main():
    # Configuração
    project_id = "c5ae6948-31f3-4aa9-b65e-f7eb780662f8"
    escopo_id = "esc-principal"
    plano_id = "04061400-b23e-4e71-affc-218d6fd0e9f9"
    
    projects_root = Path(__file__).parent.parent / "projetos"
    config_root = Path(__file__).parent.parent / "config"
    
    print("=" * 70)
    print(" PIPELINE CMOC — Nível de PLANO (dentro do ESCOPO)")
    print("=" * 70)
    
    # Importações
    from concilium.infrastructure.storage.store_factory import build_project_repository
    from concilium.application.runtime import Runtime
    
    # Carrega projeto → escopo → plano
    print("\n📦 Carregando estrutura do projeto...")
    repo = build_project_repository(projects_root)
    project_handle = repo.get_project(project_id)
    escopo_handle = project_handle.escopo(escopo_id)
    plano_handle = escopo_handle.plan(plano_id)
    
    meta = plano_handle.meta
    print(f"   ✅ Projeto: {project_handle.meta.get('nome')[:50]}...")
    print(f"   ✅ Escopo: {escopo_id}")
    print(f"   ✅ Plano: {meta.get('nome')}")
    print(f"   Status: {plano_handle.status}")
    
    # Carrega dados do escopo
    print("\n📌 Carregando dados do escopo...")
    escopo_meta = project_handle.read_json(f"escopos/{escopo_id}/meta.json", {})
    print(f"   Nome: {escopo_meta.get('nome')[:50]}...")
    print(f"   Período: {escopo_meta.get('data_inicio')} → {escopo_meta.get('data_termino')}")
    
    # Define EAP básico para supressão vegetal
    print("\n🏗️  Definindo EAP (Estrutura Analítica)...")
    eap_items = [
        {
            "item_id": "SV-001",
            "cpu_id": "CPU-TERRA-ATI-001",
            "descricao": "Supressão de Vegetação - Área 1",
            "unidade": "ha",
            "quantitativo": 15.5,
            "ordem": 1,
        },
        {
            "item_id": "SV-002",
            "cpu_id": "CPU-TERRA-ATI-001",
            "descricao": "Limpeza e Destoca - Área 1",
            "unidade": "ha",
            "quantitativo": 15.5,
            "ordem": 2,
        },
        {
            "item_id": "SV-003",
            "cpu_id": "CPU-TERRA-ATI-001",
            "descricao": "Processamento de Madeira",
            "unidade": "m3",
            "quantitativo": 200.0,
            "ordem": 3,
        },
        {
            "item_id": "SV-004",
            "cpu_id": "CPU-TERRA-ATI-001",
            "descricao": "Limpeza Final e Nivelamento",
            "unidade": "ha",
            "quantitativo": 15.5,
            "ordem": 4,
        },
    ]
    
    for item in eap_items:
        print(f"   - {item['item_id']}: {item['descricao'][:40]} ({item['quantitativo']} {item['unidade']})")
    
    # Configura cronograma de equipes
    print("\n📅 Configurando cronograma...")
    cronograma_equipes = {
        # SV-001 e SV-002: semanas 45-50 (Nov-Dez 2026)
        "SV-001": {
            "2026-W45": 2, "2026-W46": 2, "2026-W47": 2, "2026-W48": 2,
            "2026-W49": 2, "2026-W50": 2,
        },
        "SV-002": {
            "2026-W45": 1, "2026-W46": 1, "2026-W47": 1, "2026-W48": 1,
            "2026-W49": 1, "2026-W50": 1,
        },
        # SV-003: semanas 51-01 (Dez-Jan 2026-2027)
        "SV-003": {
            "2026-W51": 2, "2026-W52": 2, "2026-W53": 2,
            "2027-W01": 2, "2027-W02": 2, "2027-W03": 2,
        },
        # SV-004: semanas 03-04 (Jan 2027) - dentro do período
        "SV-004": {
            "2027-W03": 2, "2027-W04": 2, "2027-W05": 2,
        },
    }
    print(f"   ✅ {len(cronograma_equipes)} itens programados")
    
    # Mapeia regime de trabalho
    regime_trabalho = {
        "dias_semana": escopo_meta.get("dias_semana", 6),
        "horas_dia": escopo_meta.get("horas_dia", 8),
        "horas_improdutivas_dia": escopo_meta.get("horas_improdutivas_dia", 0.5),
    }
    
    # Prepara inputs para pipeline
    print("\n⚙️  Preparando inputs para skills...")
    
    skill_inputs = {
        "01-escopo-e-eap": {
            "nome": escopo_meta.get("nome"),
            "tipo_obra": escopo_meta.get("tipo_obra"),
            "localizacao": escopo_meta.get("localizacao"),
            "coordenadas": {
                "lat": escopo_meta.get("coordenadas_lat"),
                "lng": escopo_meta.get("coordenadas_lng"),
            },
            "regime_trabalho": regime_trabalho,
            "data_inicio": escopo_meta.get("data_inicio"),
            "data_termino": escopo_meta.get("data_termino"),
            "data_base_orcamento": escopo_meta.get("data_inicio"),
            "contexto_id": project_handle.meta.get("contexto_id", "mendeslobo"),
            "eap": eap_items,
        },
        "04-cronograma": {
            "num_equipes_por_item": cronograma_equipes,
        },
    }
    print("   ✅ Inputs preparados")
    
    # Cria Runtime
    print("\n🚀 Inicializando Runtime...")
    runtime = Runtime(config_root=config_root)
    print("   ✅ Runtime criado")
    
    # Executa pipeline NO PLANO (não no projeto)
    print("\n▶️  Executando pipeline... (nível de PLANO)")
    print("-" * 70)
    
    try:
        # ⚠️ NOTA: Runtime.run_pipeline espera ProjectHandle
        # PlanoHandle não tem o mesmo protocolo. Seria necessário adaptar
        # a API de Runtime ou criar um wrapper. Por enquanto, mostramos
        # a estrutura esperada.
        
        # Carrega canonical atual (se houver)
        canonical = plano_handle.load_canonical()
        print(f"   Canonical atual: {'Existe' if canonical else 'Vazio'}")
        
        # Para rodar a pipeline no plano, seria necessário:
        # records = runtime.run_pipeline(plano_handle, skill_inputs=skill_inputs)
        # MAS plano_handle não implementa ProjectHandle protocol
        
        print("\n⚠️  NOTA IMPORTANTE:")
        print("   PlanoHandle não implementa o protocolo ProjectHandle")
        print("   Runtime.run_pipeline() espera ProjectHandle")
        print("   Estrutura esperada para outputs:")
        print(f"   → escopos/{escopo_id}/planos/{plano_id}/outputs/")
        print("\n   Solução:")
        print("   1. Adaptar Runtime para aceitar ambos os tipos")
        print("   2. OU criar wrapper que converta PlanoHandle → ProjectHandle protocol")
        print("   3. OU executar no projeto e depois organizar arquivos")
        
        return 1
        
    except Exception as e:
        print(f"\n❌ Erro na execução:")
        print(f"   {type(e).__name__}: {str(e)[:200]}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
