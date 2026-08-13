#!/usr/bin/env python3
"""Pipeline CMOC v2 — Com 9 atividades corretas, unidades M² e M³, cronograma balanceado."""

from pathlib import Path
import sys

PROJECT_ID = "c5ae6948-31f3-4aa9-b65e-f7eb780662f8"
ESCOPO_ID = "esc-principal"
PLANO_ID = "04061400-b23e-4e71-affc-218d6fd0e9f9"

PROJECTS_ROOT = Path(__file__).parent.parent / "projetos"
CONFIG_ROOT = Path(__file__).parent.parent / "config"

# 9 atividades com unidades corretas (M² ou M³) e quantitativos balanceados
EAP_ITEMS = [
    {"item_id": "SV-001", "cpu_id": "CPU-TERRA-ATI-041", "descricao": "Supressão Vegetal Mata Densa - Área 1", "unidade": "m2", "quantitativo": 45000.0, "ordem": 1},
    {"item_id": "SV-002", "cpu_id": "CPU-TERRA-ATI-042", "descricao": "Supressão Vegetal Árvore Isolada - Área 2", "unidade": "m2", "quantitativo": 12500.0, "ordem": 2},
    {"item_id": "SV-003", "cpu_id": "CPU-TERRA-ATI-043", "descricao": "Supressão Vegetal Arbustiva - Área 3", "unidade": "m2", "quantitativo": 25000.0, "ordem": 3},
    {"item_id": "SV-004", "cpu_id": "CPU-TERRA-ATI-044", "descricao": "Remoção de Topsoil - Área 1", "unidade": "m3", "quantitativo": 10000.0, "ordem": 4},
    {"item_id": "SV-005", "cpu_id": "CPU-TERRA-ATI-045", "descricao": "Supressão Vegetal Mata Densa DMT curta", "unidade": "m2", "quantitativo": 20000.0, "ordem": 5},
    {"item_id": "SV-006", "cpu_id": "CPU-TERRA-ATI-046", "descricao": "Supressão Vegetal Árvore Isolada DMT curta", "unidade": "m2", "quantitativo": 6000.0, "ordem": 6},
    {"item_id": "SV-007", "cpu_id": "CPU-TERRA-ATI-047", "descricao": "Supressão Vegetal Arbustiva DMT curta", "unidade": "m2", "quantitativo": 15000.0, "ordem": 7},
    {"item_id": "SV-008", "cpu_id": "CPU-TERRA-ATI-048", "descricao": "Remoção de Topsoil DMT curta", "unidade": "m3", "quantitativo": 7500.0, "ordem": 8},
    {"item_id": "SV-009", "cpu_id": "CPU-TERRA-ATI-049", "descricao": "Movimentação e Armazenamento de Madeira", "unidade": "m3", "quantitativo": 1000.0, "ordem": 9},
]

# Cronograma estendido com múltiplas equipes por semana para absorver carga
CRONOGRAMA = {
    "SV-001": {**{f"2026-W{w:02d}": 2 for w in range(45, 54)}, **{f"2027-W{w:02d}": 2 for w in range(1, 5)}},
    "SV-002": {**{f"2026-W{w:02d}": 2 for w in range(45, 54)}, **{f"2027-W{w:02d}": 1 for w in range(1, 5)}},
    "SV-003": {**{f"2026-W{w:02d}": 2 for w in range(45, 54)}, **{f"2027-W{w:02d}": 2 for w in range(1, 4)}},
    "SV-004": {**{f"2026-W{w:02d}": 2 for w in range(49, 54)}, **{f"2027-W{w:02d}": 2 for w in range(1, 5)}},
    "SV-005": {**{f"2026-W{w:02d}": 2 for w in range(50, 54)}, **{f"2027-W{w:02d}": 2 for w in range(1, 5)}},
    "SV-006": {**{f"2026-W{w:02d}": 1 for w in range(50, 54)}, **{f"2027-W{w:02d}": 1 for w in range(1, 5)}},
    "SV-007": {**{f"2026-W{w:02d}": 1 for w in range(50, 54)}, **{f"2027-W{w:02d}": 2 for w in range(1, 5)}},
    "SV-008": {**{f"2026-W{w:02d}": 1 for w in range(51, 54)}, **{f"2027-W{w:02d}": 2 for w in range(1, 5)}},
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
