"""Curação do catálogo — parte extraída de cure_schema.py (grupo _run)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ._core import CurationReport, _load_schema, _make_validator, _validate_all
from ._cure_contextual import cure_contextual
from ._cure_cpu import cure_cpu
from ._cure_insumo import cure_insumo
from ._cure_producao import cure_producao
from ._io import _context_base, _load_entity_files, _persist_entity_files


def _run_print_header(contexto_id: str, apply: bool) -> None:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"\n{'=' * 60}")
    print(f"  Curação do catálogo [{mode}] — contexto: {contexto_id}")
    print(f"{'=' * 60}\n")


def _run_print_report(report: CurationReport, apply: bool) -> None:
    if report.fixed:
        print(f"[AUTO] {len(report.fixed)} correção(ões) automática(s):")
        for m in report.fixed:
            prefix = "  ✓" if apply else "  → (dry-run)"
            print(f"{prefix} {m}")

    if report.manual:
        print(f"\n[MANUAL] {len(report.manual)} item(ns) requerem intervenção manual:")
        for m in report.manual:
            print(f"  ⚠ {m}")

    if report.skipped:
        print(f"\n[INFO] {len(report.skipped)} aviso(s):")
        for m in report.skipped:
            print(f"  · {m}")


def _run_persist_apply(
    cpu_entries: list[tuple[Path, dict]],
    cured_cpus: list[dict],
    prod_entries: list[tuple[Path, dict]],
    cured_prods: list[dict],
    insumo_entries: list[tuple[Path, dict]],
    cured_insumos: list[dict],
    bundle_path: Path,
) -> None:
    n_cpus = _persist_entity_files([(p, obj) for (p, _), obj in zip(cpu_entries, cured_cpus, strict=False)], True)
    n_prods = _persist_entity_files([(p, obj) for (p, _), obj in zip(prod_entries, cured_prods, strict=False)], True)
    n_ins = _persist_entity_files([(p, obj) for (p, _), obj in zip(insumo_entries, cured_insumos, strict=False)], True)
    print(f"  Arquivos atualizados: CPUs={n_cpus}, PRODUCOES={n_prods}, INSUMOS={n_ins}")
    if bundle_path.exists():
        bundle_path.unlink()
        print(f"  Bundle invalidado: {bundle_path}")


def _run_validate_residual(
    contexto_id: str,
    apply: bool,
    cpus: list[dict],
    cured_cpus: list[dict],
    prods: list[dict],
    cured_prods: list[dict],
    insumos: list[dict],
    cured_insumos: list[dict],
) -> None:
    print(f"\n{'─' * 60}")
    print("  Validação residual contra schemas normalizados")
    print(f"{'─' * 60}")

    cpu_v = _make_validator(_load_schema("cpu.schema.json"))
    prod_v = _make_validator(_load_schema("producao.schema.json"))
    ins_v = _make_validator(_load_schema("insumo.schema.json"))

    data_to_validate = cured_cpus if apply else cpus
    erros = (
        _validate_all(data_to_validate, cpu_v, "CPU")
        + _validate_all(cured_prods if apply else prods, prod_v, "PRODUCAO")
        + _validate_all(cured_insumos if apply else insumos, ins_v, "INSUMO")
    )

    if erros:
        print(f"\n[ERRO] {len(erros)} erro(s) residual(is) após curação:")
        for e in erros[:50]:
            print(f"  ✗ {e}")
        if len(erros) > 50:
            print(f"  ... mais {len(erros) - 50} erros")
        if not apply:
            print("\n[INFO] Execução em DRY-RUN: para persistir correções, execute novamente com --apply.")
        print()
        raise RuntimeError(f"{len(erros)} erro(s) residual(is) após curação do catálogo '{contexto_id}'")
    else:
        print("\n  ✓ Nenhum erro residual — catálogo em conformidade com os schemas.\n")


def run(contexto_id: str, apply: bool = False) -> None:
    """Executa a curação do catálogo. Levanta RuntimeError em caso de erros residuais."""
    _run_print_header(contexto_id, apply)

    base = _context_base(contexto_id)
    bundle_path = base / ".catalog_bundle.json"
    cpu_entries = _load_entity_files(base, ("cpus",))
    insumo_entries = _load_entity_files(base, ("insumos",))
    prod_entries = _load_entity_files(base, ("producoes", "produtividades"))

    cpus: list[dict] = [item for _, item in cpu_entries]
    insumos: list[dict] = [item for _, item in insumo_entries]
    prods: list[dict] = [item for _, item in prod_entries]

    report = CurationReport()

    cured_prods = [cure_producao(p, report, apply) for p in prods]
    cured_cpus = [cure_cpu(c, report, apply) for c in cpus]
    cured_insumos = [cure_insumo(i, report, apply) for i in insumos]
    cure_contextual(cured_cpus, cured_prods, cured_insumos, report, apply)

    _run_print_report(report, apply)

    if apply:
        _run_persist_apply(
            cpu_entries, cured_cpus, prod_entries, cured_prods, insumo_entries, cured_insumos, bundle_path
        )

    _run_validate_residual(contexto_id, apply, cpus, cured_cpus, prods, cured_prods, insumos, cured_insumos)


def main() -> None:
    parser = argparse.ArgumentParser(description="Curação do catálogo Concilium")
    parser.add_argument("--contexto", required=True, help="ID do contexto (ex: mendeslobo)")
    parser.add_argument("--apply", action="store_true", help="Aplica mudanças (padrão: dry-run)")
    args = parser.parse_args()
    try:
        run(args.contexto, args.apply)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        sys.exit(1)


