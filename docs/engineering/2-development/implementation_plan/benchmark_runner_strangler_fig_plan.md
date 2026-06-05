# Benchmark Runner Refactor Plan (Strangler Fig)

## Objective

Reduce `concilium/benchmarks/_benchmark_runner.py` to a thin benchmark harness that:

- delegates skill execution to the standard runtime,
- delegates benchmark input derivation to standard application services,
- delegates benchmark reporting/comparison to a dedicated adapter,
- contains no business formulas that can drift from skills.

## Why This Refactor Exists

Today `_benchmark_runner.py` mixes four responsibilities:

1. benchmark fixture loading from `referencia.json`,
2. derived input generation for pipeline execution,
3. pipeline orchestration,
4. post-run comparison/reporting.

The standard execution path already exists in `concilium/src/concilium/presentation/runtime.py`.
The runner only needs to prepare benchmark-specific inputs and render a benchmark-specific report.

The current problem is that parts of item 2 and item 4 contain duplicated business rules, especially:

- team auto-sizing logic for `02-cronograma`,
- synthetic cost aggregation and derived deltas,
- interpretation of output fields for benchmark comparison.

This duplication already produced drift bugs, such as using a weekly-hours formula inconsistent with the skill.

## Target End State

Target layering:

1. `BenchmarkSpecLoader`
Transforms `referencia.json` into a normalized benchmark spec without applying business formulas.

2. `BenchmarkInputDeriver`
Produces benchmark inputs for skills by calling shared domain/application services.

3. Standard `Runtime`
Executes the pipeline exactly as production execution does.

4. `BenchmarkReportBuilder`
Reads canonical artifacts and reference values and emits a comparison report.

5. Thin `_benchmark_runner.py`
Only wires loader, deriver, runtime, and report builder.

## Strangler Seams

The safe seams are:

### Seam A: Spec loading

Current code:

- `load_spec_from_json()` in `concilium/benchmarks/_benchmark_runner.py`

Extract to:

- `concilium/src/concilium/application/benchmarks/spec_loader.py`

Rule:

- no skill formulas,
- only parsing, normalization, defaults, and validation.

### Seam B: Cronograma input derivation

Current code:

- auto-sizing block inside `load_spec_from_json()`

Extract to:

- `concilium/src/concilium/application/benchmarks/input_derivation/cronograma.py`

Rule:

- this service must depend on shared scheduling/productivity services,
- `_benchmark_runner.py` must stop reading CPU/productivity files directly.

### Seam C: Comparison report

Current code:

- `_build_report()` in `concilium/benchmarks/_benchmark_runner.py`

Extract to:

- `concilium/src/concilium/application/benchmarks/report_builder.py`

Rule:

- report formatting is allowed,
- business calculations must be limited to explicit comparison metrics,
- if a metric depends on domain meaning, expose it from canonical/result models or a shared projection service.

### Seam D: Summary execution

Current code:

- `benchmarks/run_all.py`

Extract to:

- keep CLI behavior, but make it consume the new services instead of relying on ad hoc report file conventions.

## Refactor Phases

## Phase 0: Freeze Behavior and Define Golden Outputs

Goal:

- protect current behavior before moving code.

Deliverables:

- snapshot of current benchmark JSON outputs for a representative set,
- approval of which metrics are contractual versus diagnostic,
- list of known data-quality distortions to exclude from refactor decisions.

Exit criteria:

- we can compare old vs new report payloads without guessing,
- benchmark suite is green enough to support refactor safely.

Notes:

- include at least `ROSH`, `LUNDIN`, `VALE`, `MATEC_GUARULHOS`, `ODFJELL`, `AGIS`.

## Phase 1: Extract a Pure Benchmark Spec Loader

Goal:

- move JSON parsing and normalization out of `_benchmark_runner.py`.

Scope:

- create `BenchmarkSpecLoader`,
- move slug/date/EAP/BDI/reference parsing there,
- keep output shape compatible with current `ProjectSpec`.

Do not move yet:

- auto-sizing,
- catalog reads,
- report generation.

Exit criteria:

- `_benchmark_runner.py` no longer parses raw `referencia.json` directly,
- `load_spec_from_json()` becomes a thin compatibility wrapper or is removed.

## Phase 2: Extract Benchmark Input Derivation for Skill 02

Goal:

- move `num_equipes_por_item` derivation into a standard service.

Scope:

- create `BenchmarkInputDeriver` with a dedicated `derive_cronograma_inputs()` path,
- centralize regime/week/productivity math,
- isolate benchmark-only policy knobs such as safety factor and cap.

Important constraint:

- no direct file walking over `config/catalogos/...` from the runner,
- any catalog read should happen through a standard repository/loader abstraction.

Exit criteria:

- `_benchmark_runner.py` no longer knows CPU/producao file layout,
- changing productivity logic happens in one shared place,
- skill 02 and benchmark derivation use the same base concepts and formulas.

## Phase 3: Introduce a Shared Benchmark Projection Layer

Goal:

- stop reinterpreting canonical output ad hoc inside `_build_report()`.

Scope:

- create a projection object such as `BenchmarkProjection` from canonical/result models,
- expose normalized fields used in comparisons:
  - direct cost by equipes,
  - direct cost by catalog,
  - indirect cost total,
  - sale price variants,
  - equilibrium summary,
  - breakdown totals.

Exit criteria:

- `_build_report()` no longer sums domain fields manually,
- benchmark comparison consumes one projection contract instead of multiple raw canonical subtrees.

## Phase 4: Extract Report Builder and Printer

Goal:

- split report semantics from terminal rendering.

Scope:

- create `BenchmarkReportBuilder` to produce the report dict,
- create `BenchmarkReportPrinter` for console output,
- keep JSON artifact schema stable during migration.

Exit criteria:

- `_benchmark_runner.py` becomes orchestration only,
- terminal formatting changes do not affect report payload generation.

## Phase 5: Collapse Runner into a Thin Composition Root

Goal:

- make `_benchmark_runner.py` a legacy shell over standard services.

Scope:

- instantiate spec loader, input deriver, runtime, report builder,
- remove remaining formulas and fallback logic from the runner,
- leave only benchmark-specific orchestration.

Exit criteria:

- `_benchmark_runner.py` is mostly wiring,
- future changes to cronograma, BDI, or result interpretation do not require runner edits.

## Phase 6: Migrate `run_all.py` and Stabilize CLI/Windows Behavior

Goal:

- finish the strangler by moving the batch executor onto the new abstractions.

Scope:

- replace ad hoc subprocess/report-file assumptions with explicit benchmark service APIs,
- fix Windows decode/capture behavior in one place,
- make summary generation consume report objects instead of fragile stdout parsing.

Exit criteria:

- full benchmark suite runs without terminal-specific workarounds,
- summary table is generated from structured outputs only.

## Migration Rules

Rules during the strangler:

1. No big-bang rewrite.
Each phase must preserve the current public benchmark workflow.

2. Compatibility wrappers are allowed.
Old function names may forward to new services temporarily.

3. Move one seam at a time.
Do not mix cronograma derivation extraction with report projection extraction in the same PR.

4. Keep artifact schema stable until Phase 5.
Only introduce schema changes after the report builder is isolated.

5. Prefer projection services over helper formulas.
If a benchmark metric requires domain knowledge, expose it from a shared service rather than recomputing in the runner.

## Proposed Work Packages

Recommended PR sequence:

1. PR-1: `BenchmarkSpecLoader` + compatibility wrapper.
2. PR-2: `BenchmarkInputDeriver` for cronograma sizing.
3. PR-3: shared benchmark projection from canonical/result.
4. PR-4: `BenchmarkReportBuilder` + printer split.
5. PR-5: slim `_benchmark_runner.py`.
6. PR-6: modernize `run_all.py` and summary generation.

## Risks

Primary risks:

- hidden dependence on benchmark JSON artifact shape,
- conflating benchmark policy with production policy,
- moving formulas without locking a golden output set first,
- preserving current bad metrics unintentionally because some reports encode data-quality gaps rather than code behavior.

## Decision Log for This Refactor

Decisions:

- benchmark execution remains on the standard `Runtime`,
- benchmark-specific logic may exist, but only in explicit benchmark services,
- `_benchmark_runner.py` must not own business formulas by the end state,
- the first seam to extract is input derivation for `02-cronograma`, because it is the highest-drift area and the source of recent failures.

## Immediate Next Step

Start with Phase 1 and Phase 2 in separate changesets.

Reason:

- Phase 1 reduces file size and improves testability with low semantic risk.
- Phase 2 removes the most dangerous duplication: productivity and weekly-capacity sizing.