# Scripts Folder

This folder contains maintenance and data-pipeline helpers for catalogs, benchmarks, and reference data.

## Commit governance (dev/)

Scripts for enforcing commit size limits, format validation, and historical audit:

- `dev/validate_commit_size.py` — Pre-commit hook to block oversized commits
- `dev/validate_commit_msg.py` — Pre-commit hook to enforce Conventional Commits format
- `dev/audit_commit_history.py` — Analyze commit history for governance violations

See [COMMIT_GOVERNANCE.md](../COMMIT_GOVERNANCE.md) and [COMMIT_GOVERNANCE_QUICKSTART.md](../COMMIT_GOVERNANCE_QUICKSTART.md) for usage.

## Benchmark and audit helpers

- `profile_benchmark.py`
- `prune_benchmark_reference.py`
- `compare_benchmark_snapshots_tree.py` (project-tree snapshot layout)
- `compare_benchmark_snapshots.py` (compatibility wrapper)

## Catalog and plausibility helpers

- `_build_catalog.py`
- `catalog_audit.py`
- `cure_catalog.py`
- `cure_plausibility.py`
- `audit_pu_catalogo.py`
- `audit_constants.py`
- `reconcile_producao_refs.py`
- `refactor_cpu_producao_adr053.py`

## Data import/update helpers

- `sinapi_fetch.py`
- `sicro_fetch.py`
- `sicro_inject.py`
- `sicro_pipeline_all.py`
- `anp_fetch.py`
- `run_price_update.py`

## Misc utilities

- `generate_pesquisa.py`
- `merge_rfi.py`
- `migrate_overlays.py`
- `price_resolver.py`
- `reclassificar_diversos.py`
- `lint_report.py`

Notes:
- Prefer `tools/` scripts for operational benchmark workflows tied to VS Code tasks.
- Prefer `scripts/` for one-off maintenance and data transformation workflows.
