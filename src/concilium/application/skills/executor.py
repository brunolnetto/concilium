"""Domain-agnostic skill executor.

Separates orchestration mechanics from domain concerns.

Responsibilities (this module):
- Topological ordering from manifest dependency graph
- Signature-based kwarg dispatch (providers_factory injects values)
- In-memory dependency tracking (bypasses invocations.log reads)
- Per-skill timing and critical-path analysis

Not responsible for (injected as callbacks):
- What state model to use (CanonicalModel or anything else)
- How to load domain config (catalogo, perfil, contexto...)
- When and how to persist state
- Domain side effects (Excel, relatorio, decision_log...)
- Domain-specific error semantics (CORROMPIDO, gate taint...)

Skill result duck-typing contract (all attributes are optional):
- result.has_errors: bool  — treated as failure when True
- result.validacoes: list  — items with .status and .mensagem
- result.<any>             — resolved via resolve_state callback

Usage::

    executor = SkillExecutor(skills=SKILLS, manifest_meta=MANIFEST_META)

    def providers_factory(skill_id, state, extra_inputs):
        return {"canonical_in": state, "inputs": extra_inputs, ...}

    def resolve_state(skill_id, result, prev_state):
        new_state = result.canonical
        # apply domain mutations (taint, decision variables, etc.)
        return new_state

    def on_after_skill(skill_id, result, new_state, record):
        project.save_canonical(new_state, v, created_by=skill_id)
        project.log_invocation(v, {"skill": skill_id, ...})
        _process_side_effects(skill_id, result, project, v)

    executor = SkillExecutor(
        skills=SKILLS,
        manifest_meta=MANIFEST_META,
        on_before_skill=lambda sid: print(f"  > {sid}...", end=" ", flush=True),
        on_after_skill=on_after_skill,
    )
    final_state, records = executor.run_pipeline(
        state_in=initial_canonical,
        providers_factory=providers_factory,
        skill_inputs=per_skill_inputs,
        resolve_state=resolve_state,
    )
    executor.print_report(records)
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from graphlib import TopologicalSorter

# ── Execution record ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ExecutionRecord:
    """Immutable timing + outcome record for a single skill execution."""

    skill_id: str
    status: str  # "OK" | "ERRO" | "EXCEPTION"
    duration_ms: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ── Critical path ─────────────────────────────────────────────────────────────


def critical_path(
    records: list[ExecutionRecord],
    manifest_meta: dict[str, dict],
) -> tuple[int, list[str]]:
    """Longest weighted path through the skill DAG.

    cp[node] = duration[node] + max(cp[dep] for dep in deps, default=0)

    Returns (cp_duration_ms, ordered list of skill_ids on the path).
    The CP is the minimum wall-clock time achievable with unlimited parallelism.
    """
    dur: dict[str, int] = {r.skill_id: r.duration_ms for r in records}
    memo: dict[str, tuple[int, list[str]]] = {}

    def _resolve(node: str) -> tuple[int, list[str]]:
        if node in memo:
            return memo[node]
        if node not in dur:
            return (0, [])
        deps = [d for d in manifest_meta.get(node, {}).get("depends_on", {}).get("skills", []) if d in dur]
        best_dep_ms, best_dep_path = max(
            (_resolve(d) for d in deps),
            key=lambda x: x[0],
            default=(0, []),
        )
        memo[node] = (best_dep_ms + dur[node], best_dep_path + [node])
        return memo[node]

    for node in dur:
        _resolve(node)

    return max(memo.values(), key=lambda x: x[0]) if memo else (0, [])


# ── Report ────────────────────────────────────────────────────────────────────


def _format_report(
    records: list[ExecutionRecord],
    manifest_meta: dict[str, dict],
    wall_clock_ms: int,
) -> str:
    """Build pipeline timing report as a plain-ASCII string."""
    if not records:
        return ""

    cp_ms, cp_path = critical_path(records, manifest_meta)
    total_sum = sum(r.duration_ms for r in records)
    cp_set = set(cp_path)

    w = 72
    lines: list[str] = []
    sep = "=" * w
    lines += [
        "",
        f"  {sep}",
        f"  {'PIPELINE TIMING REPORT':^{w}}",
        f"  {sep}",
        f"  {'Skill':<36} {'ms':>6}   {'%':>5}  {'status':<8}  bar (5%=#)",
        f"  {'-' * 36} {'-' * 6}   {'-' * 5}  {'-' * 8}  {'-' * 20}",
    ]

    for r in sorted(records, key=lambda x: x.duration_ms, reverse=True):
        pct = r.duration_ms / wall_clock_ms * 100 if wall_clock_ms else 0.0
        bar = "#" * round(pct / 5)
        cp_marker = " << CP" if r.skill_id in cp_set else ""
        lines.append(f"  {r.skill_id:<36} {r.duration_ms:>6}   {pct:>4.1f}%  {r.status:<8}  {bar}{cp_marker}")

    gain = round((1 - cp_ms / wall_clock_ms) * 100, 1) if wall_clock_ms else 0.0
    cp_str = " -> ".join(cp_path) if cp_path else "-"

    lines += [
        f"  {'-' * w}",
        f"  {'Soma sequencial (sum of durations)':<44} {total_sum:>5} ms",
        f"  {'Caminho critico - paralelo ideal (CP)':<44} {cp_ms:>5} ms",
        f"  {'Wall-clock medido':<44} {wall_clock_ms:>5} ms",
        f"  {'Ganho potencial c/ paralelismo':<44} {gain:>4.1f}%",
        f"  CP: {cp_str}",
        f"  {sep}",
        "",
    ]
    return "\n".join(lines)


# ── Executor ──────────────────────────────────────────────────────────────────


def _default_state_extractor(result: Any, prev_state: Any) -> Any:
    return getattr(result, "canonical", prev_state)


# ── Telemetry helpers (ADR-095) ───────────────────────────────────────────────


def _get_skill_span(skill_id: str) -> Any:
    """Retorna context manager OTEL span para a skill, ou nullcontext se OTEL indisponível."""
    try:
        from concilium.infrastructure.telemetry import skill_span

        return skill_span(skill_id)
    except Exception:
        from contextlib import nullcontext

        return nullcontext(None)


def _emit_skill_telemetry(skill_id: str, status: str, duration_ms: int) -> None:
    """Emite métrica de duração e define atributos no span ativo (best-effort)."""
    try:
        from concilium.infrastructure.telemetry import record_skill_duration, set_current_span_attrs

        record_skill_duration(skill_id, status, duration_ms)
        set_current_span_attrs({"skill.status": status, "skill.duration_ms": duration_ms})
    except Exception:
        pass


class SkillExecutor:
    """Domain-agnostic skill runner.

    All domain knowledge is injected through three callbacks:

    providers_factory(skill_id, state, extra_inputs) -> dict
        Build the flat kwargs dict passed to the skill function.
        This is where domain config (catalogo, perfil, contexto...)
        is resolved and injected.

    resolve_state(skill_id, result, prev_state) -> new_state
        Extract and optionally mutate state from a skill result.
        Default: ``getattr(result, "canonical", prev_state)``.
        Use this hook for domain-specific post-processing (taint
        propagation, decision-variable injection, etc.).

    on_after_skill(skill_id, result, new_state, record)
        Called after state is resolved. Use for persistence,
        side effects (Excel, JSON outputs...), and audit logging.
    """

    def __init__(
        self,
        skills: dict[str, Callable],
        manifest_meta: dict[str, dict],
        on_before_skill: Callable[[str], None] | None = None,
        on_after_skill: Callable[[str, Any, Any, ExecutionRecord], None] | None = None,
    ) -> None:
        self._skills = skills
        self._meta = manifest_meta
        self._on_before_skill = on_before_skill
        self._on_after_skill = on_after_skill

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_topology(self) -> TopologicalSorter[str]:
        """Builds and prepares a TopologicalSorter from manifest meta."""
        from graphlib import TopologicalSorter

        ts: TopologicalSorter[str] = TopologicalSorter()
        for sid, m in self._meta.items():
            deps = m.get("depends_on", {}).get("skills", [])
            ts.add(sid, *deps)
        ts.prepare()
        return ts

    @staticmethod
    def _extract_validacao_msgs(result: object) -> tuple[list, list]:
        """Extracts error and warning messages from a skill result."""
        errors = [v.mensagem for v in getattr(result, "validacoes", []) if v.status == "ERRO"]
        warnings = [v.mensagem for v in getattr(result, "validacoes", []) if v.status == "AVISO"]
        return errors, warnings

    def _execute_node(
        self,
        node: str,
        state: object,
        skill_inputs: dict,
        providers_factory: Callable[[str, Any, dict[str, Any]], dict[str, Any]],
        resolve_state_fn: Callable[..., Any],
    ) -> tuple[ExecutionRecord, object, bool]:
        """Executes a single skill node; returns (record, new_state, gate_failed)."""
        if self._on_before_skill:
            self._on_before_skill(node)

        with _get_skill_span(node):
            t0 = time.perf_counter_ns()
            result = None
            try:
                providers = providers_factory(node, state, skill_inputs.get(node, {}))
                result = self.dispatch(node, providers)
                duration_ms = round((time.perf_counter_ns() - t0) / 1_000_000)
                has_errors = bool(getattr(result, "has_errors", False))
                errors, warnings = self._extract_validacao_msgs(result)
                status = "ERRO" if has_errors else "OK"
                new_state = resolve_state_fn(node, result, state)
                record = ExecutionRecord(node, status, duration_ms, errors, warnings)
                _emit_skill_telemetry(node, status, duration_ms)
                if self._on_after_skill:
                    self._on_after_skill(node, result, new_state, record)
                gate_fail = has_errors and self._meta.get(node, {}).get("gate", False)
                return record, new_state, gate_fail
            except Exception as exc:
                duration_ms = round((time.perf_counter_ns() - t0) / 1_000_000)
                record = ExecutionRecord(node, "EXCEPTION", duration_ms, [str(exc)])
                _emit_skill_telemetry(node, "EXCEPTION", duration_ms)
                if self._on_after_skill:
                    self._on_after_skill(node, result, state, record)
                gate_fail = self._meta.get(node, {}).get("gate", False)
                return record, state, gate_fail

    # ── Single skill dispatch ─────────────────────────────────────────────────

    def dispatch(self, skill_id: str, providers: dict[str, Any]) -> Any:
        """Execute one skill, injecting only the parameters it declares.

        Parameters not present in ``providers`` are silently omitted, so
        skill functions only receive what they ask for.
        """
        fn = self._skills[skill_id]
        params = inspect.signature(fn).parameters
        kwargs = {p: providers[p] for p in params if p in providers}
        return fn(**kwargs)

    # ── Pipeline ──────────────────────────────────────────────────────────────

    def run_pipeline(
        self,
        *,
        state_in: Any,
        providers_factory: Callable[[str, Any, dict[str, Any]], dict[str, Any]],
        skill_inputs: dict[str, dict[str, Any]] | None = None,
        resolve_state: Callable[..., Any] | None = None,
    ) -> tuple[Any, list[ExecutionRecord]]:
        """Run all registered skills in dependency order.

        Args:
            state_in: Initial state fed to the first skill.
            providers_factory: Builds the kwarg dict before each skill.
                Receives (skill_id, current_state, extra_inputs).
            skill_inputs: Per-skill extra input dicts.
            resolve_state: Extracts and post-processes the new state from a
                skill result. Receives (skill_id, result, prev_state).
                Defaults to ``getattr(result, "canonical", prev_state)``.
        Returns:
            (final_state, list[ExecutionRecord]) — one record per executed skill.

        Gate semantics: if a skill tagged ``gate=true`` in its manifest
        produces errors or raises, the pipeline stops after that skill.
        The ``on_after_skill`` hook is still called so the caller can
        persist any taint applied via ``resolve_state``.
        """
        _resolve_state = resolve_state or _default_state_extractor
        skill_inputs = skill_inputs or {}
        records: list = []
        state = state_in
        t_start = time.perf_counter_ns()
        ts = self._build_topology()
        gate_failed = False
        while ts.is_active() and not gate_failed:
            for node in list(ts.get_ready()):
                if node not in self._skills:
                    ts.done(node)
                    continue
                record, state, node_gate = self._execute_node(
                    node,
                    state,
                    skill_inputs,
                    providers_factory,
                    _resolve_state,
                )
                records.append(record)
                ts.done(node)
                if node_gate:
                    gate_failed = True
                    break
        wall_clock_ms = round((time.perf_counter_ns() - t_start) / 1_000_000)
        try:
            print(_format_report(records, self._meta, wall_clock_ms))
        except Exception as _report_exc:
            import logging as _logging

            _logging.getLogger(__name__).warning("Report render falhou (best-effort): %s", _report_exc)
        return state, records

    # ── Report ────────────────────────────────────────────────────────────────

    def print_report(self, records: list[ExecutionRecord], wall_clock_ms: int) -> None:
        """Print the timing + critical path report to stdout."""
        try:
            print(_format_report(records, self._meta, wall_clock_ms))
        except Exception:
            pass
