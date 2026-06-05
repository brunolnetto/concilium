"""Helpers de execução de pipeline: resolução de estado, callbacks e formatação de registros."""

from __future__ import annotations

from typing import Any

from ..exceptions import RuntimeTechnicalError
from ..gates import _GATE_SKILLS


def _parse_executed_skills(log_path: Any) -> set:
    """Parses invocations log and returns set of executed skill IDs."""
    executed: set = set()
    if not log_path.exists():
        return executed
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            import json as _json
            entry = _json.loads(line)
            if entry.get("status") in ("OK", "ERRO") and "skill" in entry:
                executed.add(entry["skill"])
        except Exception:
            pass
    return executed


def _execute_skill(skill_fn, kwargs, skill_id, execution_id, ts_inicio, plano_store):
    """Run skill_fn; on exception logs and re-raises appropriately."""
    from ..exceptions import RuntimeError as _RuntimeError
    try:
        return skill_fn(**kwargs)
    except Exception as exc:
        plano_store.log_invocation(
            {
                "ts": ts_inicio.isoformat(),
                "execution_id": execution_id,
                "skill": skill_id,
                "status": "ERRO",
                "erro": str(exc),
            }
        )
        if isinstance(exc, _RuntimeError):
            raise
        raise RuntimeTechnicalError(f"Falha técnica na skill '{skill_id}': {exc}") from exc


def _apply_dv(new_canonical: Any, dv_raw: Any) -> Any:
    """Apply decision variables to canonical model if valid."""
    try:
        from concilium.domain.models.decision_variables import DecisionVariables

        dv_obj = DecisionVariables.model_validate(dv_raw) if isinstance(dv_raw, dict) else dv_raw
        if new_canonical.decision_variables != dv_obj:
            return new_canonical.model_copy(update={"decision_variables": dv_obj})
    except Exception:
        pass
    return new_canonical


def _resolve_state(skill_id: str, result: Any, skill_inputs: dict) -> Any:
    """State resolution for run_pipeline: taint propagation + decision variables."""
    new_canonical = result.canonical
    if result.has_errors and skill_id in _GATE_SKILLS:
        blocked = list(set(new_canonical.pipeline_blocked_from) | {skill_id})
        new_canonical = new_canonical.model_copy(
            update={
                "pipeline_blocked_from": blocked,
                "pipeline_integridade": "CORROMPIDO",
            }
        )
    elif not result.has_errors and skill_id in _GATE_SKILLS:
        current_blocked = set(new_canonical.pipeline_blocked_from)
        if skill_id in current_blocked:
            new_blocked = sorted(current_blocked - {skill_id})
            new_canonical = new_canonical.model_copy(
                update={
                    "pipeline_blocked_from": new_blocked,
                    "pipeline_integridade": "CORROMPIDO" if new_blocked else None,
                }
            )
    dv_raw = skill_inputs.get(skill_id, {}).get("decision_variables")
    if dv_raw is not None and not result.has_errors:
        new_canonical = _apply_dv(new_canonical, dv_raw)
    return new_canonical


def _oas_log_invocation(runtime, store, version, invocation_context, skill_id, result, record):
    """Log skill invocation to store. Errors are silently swallowed."""
    try:
        from datetime import UTC as _UTC
        from datetime import datetime

        contract = runtime.get_skill_contract(skill_id)
        error_kind = "DOMINIO" if record.status == "ERRO" else ("TECNICO" if record.status == "EXCEPTION" else None)
        store.log_invocation(
            version,
            {
                "ts": datetime.now(_UTC).isoformat(),
                "skill": skill_id,
                **invocation_context,
                "contract": {
                    "required_inputs": contract.required_inputs,
                    "optional_inputs": contract.optional_inputs,
                    "depends_on_skills": contract.depends_on_skills,
                    "produces_section": contract.produces_section,
                },
                "status": record.status,
                "duration_ms": record.duration_ms,
                "error_kind": error_kind,
                "avisos": record.warnings,
                "validacoes": [
                    {"codigo": val.codigo, "status": val.status} for val in getattr(result, "validacoes", [])
                ],
            },
        )
    except Exception:
        pass


def _oas_save_state(store, version, skill_id, result, new_state, record):
    """Persist canonical state after skill execution (taint-aware)."""
    should_save = not (skill_id == "00-escopo" and record.status == "ERRO")
    if new_state is not None and should_save and record.status != "EXCEPTION":
        store.save_canonical(new_state, version, created_by=skill_id)
    elif result is None and skill_id in _GATE_SKILLS and new_state is not None:
        blocked = list(set(new_state.pipeline_blocked_from) | {skill_id})
        tainted = new_state.model_copy(
            update={
                "pipeline_blocked_from": blocked,
                "pipeline_integridade": "CORROMPIDO",
            }
        )
        store.save_canonical(tainted, version, created_by=f"taint:{skill_id}")


def _on_after_skill(runtime, store, version, invocation_context, skill_id, result, new_state, record):
    """on_after_skill callback: persistence + side effects + logging."""
    _oas_save_state(store, version, skill_id, result, new_state, record)
    if result is not None:
        runtime._process_side_effects(skill_id, result, store, version)
    msg = f"[{record.status}] {record.duration_ms}ms"
    if record.errors:
        msg += f"  {'; '.join(record.errors)}"
    print(msg)
    if record.status == "EXCEPTION" and runtime._meta_is_gate(skill_id):
        print(f"  [STOP] Interrompendo pipeline: skill portao '{skill_id}' falhou.")
    _oas_log_invocation(runtime, store, version, invocation_context, skill_id, result, record)


def _print_skill_start(skill_id: str) -> None:
    print(f"  > {skill_id}...", end=" ", flush=True)


def _format_records(records: list) -> list[dict]:
    """Format execution records to pipeline return format."""
    result = []
    for r in records:
        entry: dict = {
            "skill": r.skill_id,
            "status": r.status,
            "duration_ms": r.duration_ms,
            "avisos": r.warnings,
        }
        if r.errors:
            entry["erros"] = r.errors
        if r.status == "EXCEPTION" and r.errors:
            entry["erro"] = r.errors[0]
        result.append(entry)
    return result


__all__ = [
    "_apply_dv",
    "_execute_skill",
    "_format_records",
    "_on_after_skill",
    "_oas_log_invocation",
    "_oas_save_state",
    "_parse_executed_skills",
    "_print_skill_start",
    "_resolve_state",
]
