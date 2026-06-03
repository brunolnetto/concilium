# Scripts Folder

This folder contains maintenance and data-pipeline helpers for catalogs, benchmarks, and reference data.

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
