#!/usr/bin/env python3
"""Pipeline CMOC — executa no nível correto: escopos/{escopo_id}/planos/{plano_id}/."""

from pathlib import Path
import sys

PROJECT_ID = "c5ae6948-31f3-4aa9-b65e-f7eb780662f8"
ESCOPO_ID = "esc-principal"
PLANO_ID = "04061400-b23e-4e71-affc-218d6fd0e9f9"

PROJECTS_ROOT = Path(__file__).parent.parent / "projetos"
CONFIG_ROOT = Path(__file__).parent.parent / "config"

EAP_ITEMS = [
    # Mata Densa (M²) — DMT ≤ 6km
    {"item_id": "SV-001", "cpu_id": "CPU-TERRA-ATI-041", "descricao": "Supressão Vegetal Mata Densa - Área 1", "unidade": "m2", "quantitativo": 90000.0, "ordem": 1},
    
    # Árvore Isolada (M²) — DMT ≤ 6km
    {"item_id": "SV-002", "cpu_id": "CPU-TERRA-ATI-042", "descricao": "Supressão Vegetal Árvore Isolada - Área 2", "unidade": "m2", "quantitativo": 25000.0, "ordem": 2},
    
    # Vegetação Arbustiva (M²) — DMT ≤ 4,5km
    {"item_id": "SV-003", "cpu_id": "CPU-TERRA-ATI-043", "descricao": "Supressão Vegetal Arbustiva - Área 3", "unidade": "m2", "quantitativo": 50000.0, "ordem": 3},
    
    # Remoção Topsoil (M³) — DMT ≤ 4,5km
    {"item_id": "SV-004", "cpu_id": "CPU-TERRA-ATI-044", "descricao": "Remoção de Topsoil - Área 1", "unidade": "m3", "quantitativo": 20000.0, "ordem": 4},
    
    # Mata Densa (M²) — DMT ≤ 1km (mais próxima)
    {"item_id": "SV-005", "cpu_id": "CPU-TERRA-ATI-045", "descricao": "Supressão Vegetal Mata Densa DMT curta", "unidade": "m2", "quantitativo": 40000.0, "ordem": 5},
    
    # Árvore Isolada (M²) — DMT ≤ 1km (mais próxima)
    {"item_id": "SV-006", "cpu_id": "CPU-TERRA-ATI-046", "descricao": "Supressão Vegetal Árvore Isolada DMT curta", "unidade": "m2", "quantitativo": 12000.0, "ordem": 6},
    
    # Vegetação Arbustiva (M²) — DMT ≤ 1km (mais próxima)
    {"item_id": "SV-007", "cpu_id": "CPU-TERRA-ATI-047", "descricao": "Supressão Vegetal Arbustiva DMT curta", "unidade": "m2", "quantitativo": 30000.0, "ordem": 7},
    
    # Remoção Topsoil (M³) — DMT ≤ 1km (mais próxima)
    {"item_id": "SV-008", "cpu_id": "CPU-TERRA-ATI-048", "descricao": "Remoção de Topsoil DMT curta", "unidade": "m3", "quantitativo": 15000.0, "ordem": 8},
    
    # Movimentação de Madeira (M³)
    {"item_id": "SV-009", "cpu_id": "CPU-TERRA-ATI-049", "descricao": "Movimentação e Armazenamento de Madeira", "unidade": "m3", "quantitativo": 2000.0, "ordem": 9},
]

CRONOGRAMA = {
    # Mata Densa: 9000 m² ao longo de 12 semanas
    "SV-001": {
        "2026-W45": 1, "2026-W46": 1, "2026-W47": 1, "2026-W48": 1, 
        "2026-W49": 1, "2026-W50": 1, "2026-W51": 1, "2026-W52": 1,
        "2026-W53": 1, "2027-W01": 1, "2027-W02": 1
    },
    # Árvore Isolada: 2500 m² ao longo de 8 semanas
    "SV-002": {
        "2026-W45": 1, "2026-W46": 1, "2026-W47": 1, "2026-W48": 1, 
        "2026-W49": 1, "2026-W50": 1, "2026-W51": 1, "2026-W52": 1
    },
    # Arbustiva: 5000 m² ao longo de 10 semanas
    "SV-003": {
        "2026-W45": 1, "2026-W46": 1, "2026-W47": 1, "2026-W48": 1, 
        "2026-W49": 1, "2026-W50": 1, "2026-W51": 1, "2026-W52": 1,
        "2026-W53": 1, "2027-W01": 1
    },
    # Remoção Topsoil: 2000 m³ ao longo de 8 semanas
    "SV-004": {
        "2026-W51": 1, "2026-W52": 1, "2026-W53": 1, "2027-W01": 1,
        "2027-W02": 1, "2027-W03": 1, "2027-W04": 1, "2027-W05": 1
    },
    # Mata Densa (DMT curta): 4000 m² ao longo de 8 semanas
    "SV-005": {
        "2026-W51": 1, "2026-W52": 1, "2026-W53": 1, "2027-W01": 1,
        "2027-W02": 1, "2027-W03": 1, "2027-W04": 1, "2027-W05": 1
    },
    # Árvore Isolada (DMT curta): 1200 m² ao longo de 6 semanas
    "SV-006": {
        "2027-W01": 1, "2027-W02": 1, "2027-W03": 1, "2027-W04": 1,
        "2027-W05": 1, "2027-W06": 1
    },
    # Arbustiva (DMT curta): 3000 m² ao longo de 7 semanas
    "SV-007": {
        "2027-W01": 1, "2027-W02": 1, "2027-W03": 1, "2027-W04": 1,
        "2027-W05": 1, "2027-W06": 1, "2027-W07": 1
    },
    # Remoção Topsoil (DMT curta): 1500 m³ ao longo de 6 semanas
    "SV-008": {
        "2027-W03": 1, "2027-W04": 1, "2027-W05": 1, "2027-W06": 1,
        "2027-W07": 1, "2027-W08": 1
    },
    # Movimentação Madeira: 200 m³ ao longo de 5 semanas
    "SV-009": {
        "2027-W04": 1, "2027-W05": 1, "2027-W06": 1, "2027-W07": 1, "2027-W08": 1
    },
}


def main() -> int:
    print("=" * 70)
    print(" PIPELINE CMOC — Supressão Vegetal Ouvidor/GO")
    print("=" * 70)

    from concilium.application.runtime import Runtime
    from concilium.infrastructure.storage.store_factory import build_project_repository

    # Carrega projeto → escopo → plano
    print("\n📦 Carregando estrutura...")
    repo = build_project_repository(PROJECTS_ROOT)
    project = repo.get_project(PROJECT_ID)
    escopo = project.escopo(ESCOPO_ID)
    plano = escopo.plan(PLANO_ID)

    print(f"   Projeto : {project.meta.get('nome')[:55]}...")
    print(f"   Escopo  : {ESCOPO_ID}")
    print(f"   Plano   : {plano.meta.get('nome')}  [{plano.status}]")

    # Limpa canonical anterior para execução limpa
    print("\n🧹 Removendo canonical anterior...")
    try:
        canonical_path = plano._store.path / "canonical.json"
        if canonical_path.exists():
            canonical_path.unlink()
            print("   ✓ Canonical removido")
    except Exception as e:
        print(f"   (ignorado: {e})")

    # Carrega metadados do escopo
    escopo_meta = escopo.meta
    print(f"\n📌 Escopo: {escopo_meta.get('data_inicio')} → {escopo_meta.get('data_termino')}")

    # Monta inputs
    skill_inputs = {
        "01-escopo-e-eap": {
            "nome": escopo_meta.get("nome"),
            "tipo_obra": escopo_meta.get("tipo_obra"),
            "localizacao": escopo_meta.get("localizacao"),
            "coordenadas": {
                "lat": escopo_meta.get("coordenadas_lat"),
                "lng": escopo_meta.get("coordenadas_lng"),
            },
            "regime_trabalho": {
                "dias_semana": escopo_meta.get("dias_semana", 6),
                "horas_dia": escopo_meta.get("horas_dia", 8),
                "horas_improdutivas_dia": escopo_meta.get("horas_improdutivas_dia", 0.5),
            },
            "data_inicio": escopo_meta.get("data_inicio"),
            "data_termino": escopo_meta.get("data_termino"),
            "data_base_orcamento": escopo_meta.get("data_inicio"),
            "contexto_id": project.meta.get("contexto_id", "mendeslobo"),
            "eap": EAP_ITEMS,
        },
        "04-cronograma": {"num_equipes_por_item": CRONOGRAMA},
    }

    print("\n🏗️  EAP:")
    for item in EAP_ITEMS:
        print(f"   - {item['item_id']}: {item['descricao'][:40]} ({item['quantitativo']} {item['unidade']})")

    # Executa
    print("\n🚀 Inicializando Runtime...")
    runtime = Runtime(config_root=CONFIG_ROOT)

    print("\n▶️  Executando pipeline...")
    print("-" * 70)

    records = runtime.run_pipeline_on_plano(project, plano, skill_inputs=skill_inputs)

    print("-" * 70)

    ok = sum(1 for r in records if r.get("status") == "OK")
    err = sum(1 for r in records if r.get("status") in ("ERRO", "EXCEPTION"))
    total_ms = sum(r.get("duration_ms", 0) for r in records)

    print(f"\n📊 Resultado: {ok}/{len(records)} skills OK  |  {total_ms/1000:.1f}s")
    for r in records:
        sym = "✅" if r["status"] == "OK" else "❌"
        print(f"   {sym} {r['skill_id']:32} {r['status']:10} {r['duration_ms']:5}ms")

    # Entregáveis — agora dentro do plano, no local correto
    output_files = plano.list_output_files()
    print(f"\n📄 Entregáveis em escopos/{ESCOPO_ID}/planos/{PLANO_ID}/outputs/  ({len(output_files)} arquivos)")
    for f in sorted(output_files):
        print(f"   ✅ {f}")

    if err == 0:
        print("\n" + "=" * 70)
        print("🎉 PIPELINE CONCLUÍDA COM SUCESSO!")
        print("=" * 70)
        return 0

    print("\n⚠️  Pipeline concluída com ERROS")
    return 1


if __name__ == "__main__":
    sys.exit(main())
