# Tools Folder

This folder contains operational benchmark utilities used by local workflows and VS Code tasks.

## Supported tools

- `audit_benchmarks_batch.py`: batch audit runner for benchmark slugs
- `run_agis_with_discrepancy_artifacts.py`: AGIS-focused discrepancy artifact pipeline
- `address_agis_discrepancies.py`: apply discrepancy remediation workflow
- `export_benchmark_reports.py`: export benchmark outputs for review
- `compare_benchmark_snapshots_flat.py`: compare flat benchmark report snapshots (`*.benchmark_report.json`)
- `compare_benchmark_snapshots.py`: compatibility wrapper

## Deprecated wrappers

- `tmp_debug_audit_paths.py`
- `tmp_regenerate_audit_six.py`

Both wrappers are intentionally deprecated and return non-zero to prevent accidental use.
Use `audit_benchmarks_batch.py` for deterministic, reproducible audit generation.
