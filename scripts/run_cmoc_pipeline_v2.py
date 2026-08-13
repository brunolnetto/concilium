#!/usr/bin/env python3
"""Pipeline CMOC v2 — Com 9 atividades corretas, unidades M² e M³, cronograma balanceado."""

from pathlib import Path
import sys

PROJECT_ID = "c5ae6948-31f3-4aa9-b65e-f7eb780662f8"
ESCOPO_ID = "esc-principal"
PLANO_ID = "04061400-b23e-4e71-affc-218d6fd0e9f9"

PROJECTS_ROOT = Path(__file__).parent.parent / "projetos"
CONFIG_ROOT = Path(__file__).parent.parent / "config"

# 9 atividades com dados reais do projeto CMOC Azamor 3A
# Dados de origem: Estrutura Analítica de Projeto (EAP) real
# 3 GRAFOS DISJUNTOS (independentes):
#   Grafo 1: SV-001, SV-002, SV-003 → SV-004 (FASE 1)
#   Grafo 2: SV-005 → SV-006, SV-007 → SV-008 (FASE 2)
#   Grafo 3: SV-009 (Madeira - independente)
EAP_ITEMS = [
    {"item_id": "SV-001", "cpu_id": "CPU-TERRA-ATI-041", "descricao": "Supressão vegetal de Mata Densa - Incluso os serviço de corte, destocamento, traçamento, baldeio e empilhamento de madeira com DMT até 6 km", "unidade": "m2", "quantitativo": 169798.78, "ordem": 1, "predecessores": []},
    {"item_id": "SV-002", "cpu_id": "CPU-TERRA-ATI-042", "descricao": "Supressão de árvore isolada - Incluso os serviço de corte, destocamento, traçamento, baldeio e empilhamento de madeira com DMT até 6 km", "unidade": "m2", "quantitativo": 33959.76, "ordem": 2, "predecessores": []},
    {"item_id": "SV-003", "cpu_id": "CPU-TERRA-ATI-043", "descricao": "Supressão de vegetação arbustiva - Carga, transporte, descarga e espalhamento com DMT até 4,5 km", "unidade": "m2", "quantitativo": 336787.60, "ordem": 3, "predecessores": []},
    {"item_id": "SV-004", "cpu_id": "CPU-TERRA-ATI-044", "descricao": "Remoção do topsoil - Carga, transporte, descarga e espalhamento com DMT até 4,5 km", "unidade": "m3", "quantitativo": 243245.76, "ordem": 4, "predecessores": [{"item_id": "SV-001"}, {"item_id": "SV-002"}, {"item_id": "SV-003"}]},
    {"item_id": "SV-005", "cpu_id": "CPU-TERRA-ATI-045", "descricao": "Supressão vegetal de Mata Densa - Incluso os serviço de corte, destocamento, traçamento, baldeio e empilhamento de madeira com DMT até 1 km", "unidade": "m2", "quantitativo": 123322.82, "ordem": 5, "predecessores": []},
    {"item_id": "SV-006", "cpu_id": "CPU-TERRA-ATI-046", "descricao": "Supressão de árvore isolada - Incluso os serviço de corte, destocamento, traçamento, baldeio e empilhamento de madeira com DMT até 1 km", "unidade": "m2", "quantitativo": 2853.89, "ordem": 6, "predecessores": []},
    {"item_id": "SV-007", "cpu_id": "CPU-TERRA-ATI-047", "descricao": "Supressão de vegetação arbustiva - Carga, transporte, descarga e espalhamento com DMT até 1 km", "unidade": "m2", "quantitativo": 123285.70, "ordem": 7, "predecessores": []},
    {"item_id": "SV-008", "cpu_id": "CPU-TERRA-ATI-048", "descricao": "Remoção de top soil - Carga, transporte, descarga e espalhamento com DMT até 1 km", "unidade": "m3", "quantitativo": 124731.21, "ordem": 8, "predecessores": [{"item_id": "SV-005"}, {"item_id": "SV-006"}, {"item_id": "SV-007"}]},
    {"item_id": "SV-009", "cpu_id": "CPU-TERRA-ATI-049", "descricao": "Movimentação de armazenamento de Madeira - Carregamento, baldeio e empilhamento de madeira com DMT até 0,5 km", "unidade": "m3", "quantitativo": 1174.00, "ordem": 9, "predecessores": []},
]

# Cronograma estendido para quantitativos reais (muito maiores)
# Múltiplas equipes e semanas de trabalho para absorver a carga real
CRONOGRAMA = {
    # SV-001: 169.798 m² (maior atividade) — distribuída em múltiplas equipes/semanas
    "SV-001": {**{f"2026-W{w:02d}": 4 for w in range(45, 54)}, **{f"2027-W{w:02d}": 4 for w in range(1, 5)}},
    # SV-002: 33.959 m² — múltiplas equipes
    "SV-002": {**{f"2026-W{w:02d}": 3 for w in range(45, 54)}, **{f"2027-W{w:02d}": 2 for w in range(1, 5)}},
    # SV-003: 336.787 m² (maior ainda!) — máximas equipes
    "SV-003": {**{f"2026-W{w:02d}": 5 for w in range(45, 54)}, **{f"2027-W{w:02d}": 5 for w in range(1, 5)}},
    # SV-004: 243.245 m³ — máximas equipes (atividade crítica)
    "SV-004": {**{f"2026-W{w:02d}": 5 for w in range(45, 54)}, **{f"2027-W{w:02d}": 5 for w in range(1, 5)}},
    # SV-005: 123.322 m² — múltiplas equipes
    "SV-005": {**{f"2026-W{w:02d}": 3 for w in range(50, 54)}, **{f"2027-W{w:02d}": 4 for w in range(1, 5)}},
    # SV-006: 2.853 m² (menor atividade!) — 1-2 equipes
    "SV-006": {**{f"2026-W{w:02d}": 1 for w in range(50, 54)}, **{f"2027-W{w:02d}": 1 for w in range(1, 5)}},
    # SV-007: 123.285 m² — múltiplas equipes
    "SV-007": {**{f"2026-W{w:02d}": 2 for w in range(50, 54)}, **{f"2027-W{w:02d}": 3 for w in range(1, 5)}},
    # SV-008: 124.731 m³ — CRÍTICA: estende desde W45 com 5 equipes (precisa 4x mais)
    "SV-008": {**{f"2026-W{w:02d}": 5 for w in range(45, 54)}, **{f"2027-W{w:02d}": 5 for w in range(1, 5)}},
    # SV-009: 1.174 m³ (muito pequeno!) — 1 equipe
    "SV-009": {f"2026-W{w:02d}": 1 for w in range(52, 54)} | {f"2027-W{w:02d}": 1 for w in range(1, 5)},
}


def main() -> int:
    print("=" * 70)
    print(" PIPELINE CMOC v2 — 9 Atividades com Unidades Corretas")
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

    # Limpa canonical anterior
    print("\n🧹 Removendo canonical anterior...")
    try:
        canonical_path = plano._store.path / "canonical.json"
        if canonical_path.exists():
            canonical_path.unlink()
            print("   ✓ Canonical removido")
    except Exception as e:
        print(f"   (ignorado: {e})")

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

    print("\n🏗️  EAP (9 ATIVIDADES CORRIGIDAS):")
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

    # Entregáveis
    output_files = plano.list_output_files()
    print(f"\n📄 Entregáveis em escopos/{ESCOPO_ID}/planos/{PLANO_ID}/outputs/  ({len(output_files)} arquivos)")
    for f in sorted(output_files):
        print(f"   ✅ {f}")

    if err == 0:
        print("\n" + "=" * 70)
        print("🎉 PIPELINE CONCLUÍDA COM SUCESSO! (9 ATIVIDADES EM M² E M³)")
        print("=" * 70)
        return 0

    print("\n⚠️  Pipeline concluída com ERROS")
    return 1


if __name__ == "__main__":
    sys.exit(main())
