---
description: "Use when running, auditing, or debugging Concilium benchmarks, discrepancy artifacts, or catalog plausibility checks. Enforces reproducible forensic workflow for AGIS and similar benchmark pipelines."
name: "Concilium Benchmark Forensics"
---
# Concilium Benchmark Forensics

- Treat these items as strong defaults. Allow exceptions only with an explicit rationale in the task response.
- Aim for MCP-tool-grade determinism: same version + same inputs + same artifacts => same outputs and decisions.
- Prefer reproducibility over quick runtime fallbacks.
- Keep skill outputs deterministic: same inputs must produce the same outputs.
- Define explicit input/output contracts for every benchmark/audit operation (typed fields, stable names, stable units).
- Keep output ordering stable (sort keys/collections before compare/export/report) to avoid spurious diffs.
- Avoid hidden variability sources in logic and reports: current time, locale, timezone, random seeds, env-dependent defaults, implicit filesystem order.
- For unavoidable variability (for example timestamps), isolate it in explicit metadata fields and exclude it from decision logic and parity checks.
- Keep read/audit actions side-effect free when possible; for write paths, require idempotent behavior under safe retry.
- Use explicit versioning for artifact schema/contract and document compatibility when fields change.
- Treat benchmark reference data as stale-prone; regenerate or refresh extraction artifacts before delta analysis.
- When matching benchmark report files, account for suffix variants. Prefer prefix glob patterns like `benchmark_<slug>*` instead of only `benchmark_<slug>.json`.
- Keep CPU/producao normalization in source catalog JSON (or catalog build/audit scripts), not ad-hoc runtime fallback logic inside skills.
- Parse frontend boolean-like inputs defensively. Values such as `"false"` must not be treated as truthy.
- In local benchmark/debug scripts, avoid importing an installed package by accident. Ensure `src/` has precedence in import resolution when needed.
- For Windows terminal compatibility, keep user-facing CLI strings ASCII-safe (for example, use `->` instead of Unicode arrows).
- Before/after benchmark-impacting edits, run the relevant benchmark/audit task and report concrete artifact paths used in verification.
- If behavior differs from expectations, inspect discrepancy artifacts first and explain root cause with file-backed evidence.
