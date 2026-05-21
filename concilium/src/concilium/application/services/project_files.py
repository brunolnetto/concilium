from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectFiles:
    skill_inputs: str = "skill_inputs.json"
    overrides: str = "skill_overrides.json"
    benchmark_reference: str = "benchmark_reference.json"
    runs: str = "runs.json"
    audit_log: str = "audit_log.jsonl"
    # ADR-054: workforce mobilization policies (separate file, independent lifecycle)
    mobilizacao_policies: str = "overrides/mobilizacao_policy_override.json"
    # ADR-054: configurable deliverable generation flags
    deliverables_config: str = "deliverables_config.json"
    # ADR-063: EAP items for "project" type (gradual composition)
    eap_items: str = "eap_items.json"

    # ── Arquivos intermediários por versão (dentro de {vN}/intermediate/) ──
    # Estes nomes são relativos ao diretório intermediate/ de cada versão.
    intermediate_relatorio: str = "intermediate/relatorio.json"
    intermediate_memorial_bdi: str = "intermediate/memorial_bdi.json"
    intermediate_schedules_weekly: str = "intermediate/schedules_weekly.json"
    intermediate_decision_log: str = "intermediate/decision_log.json"


DEFAULT_DELIVERABLES: dict = {
    "version": "1.1",
    "outputs": {
        # ── Artefatos em disco (outputs/) ─────────────────────────────────
        "resultado_xlsx": True,  # resultado_planejamento.xlsx — planilha principal
        "modelo_vivo_xlsx": False,  # modelo_vivo.xlsx — versão com fórmulas (pesada)
        "relatorio_md": True,  # relatorio.md — relatório executivo em Markdown
        "memoria_calculo": True,  # memorial_bdi.json — memorial de cálculo BDI (ADR-057)
        # ── Abas Excel analíticas (dentro do resultado_xlsx) ─────────────
        "aba_memorial_bdi": True,  # MEMORIAL.BDI — auditoria de cálculo BDI (ADR-057)
        "aba_curva_abc": True,  # CURVA.ABC — Pareto por insumo (ADR-058)
        "aba_s_curve": True,  # S-CURVE — curva de desembolso acumulado (ADR-058)
        "aba_campanha_frota": True,  # CAMPANHA.FROTA — permanência de equipamentos (ADR-059)
        "aba_cubo_comp": True,  # CUBO.COMP — composição 4D do preço (ADR-058 ext.)
        # ── Toggles legados (mantidos para compatibilidade) ───────────────
        "cronograma_xlsx": True,  # alias de resultado_xlsx — mantido
        "curva_forca_histogram": True,  # histogramas de equipe (HIST.* sheets)
        "curva_producao_cumulativa": True,  # S-CURVE alias
        "relatorio_produtividade": True,  # RESULTADO sheet
        "projecao_custo": True,  # FLUXO.CAIXA sheet
    },
}


DEFAULT_PROJECT_FILES = ProjectFiles()


# ── Architecture note — Storage pattern ──────────────────────────────────────
#
# ALL project data persistence MUST go through ProjectHandle (read_json /
# write_json / save_output_file / save_intermediate_file).  Direct Path
# operations on project directories are a pattern violation.
#
# Intentional exceptions (documented):
#   • ConfigVersionService (contextos/perfis versioning) — IS the abstraction layer
#   • CatalogLoader (catalog reads) — IS the abstraction layer for master catalog
#   • healer.py — one-time data migration utility, not regular data access
#   • benchmarks/runner.py — test/validation artifacts, isolated from production store
