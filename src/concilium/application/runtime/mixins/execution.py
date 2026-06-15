"""Mixin de execução: run_skill, run_skill_on_plano, taint, side effects."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from concilium.application.skills import SKILLS
from concilium.application.skills.base import SkillResult
from concilium.infrastructure.storage.project import ProjectStore

from ..deliverables.side_effects import (
    _handle_skill_04_side_effects,
    _handle_skill_09_side_effects,
    _json_default,
    _persist_typed_artifacts,
)
from ..exceptions import RuntimeDomainError
from ..gates import _GATE_SKILLS
from ..helpers.pipeline import _execute_skill


class ExecutionMixin:
    """Mixin com métodos de execução de skill e processamento de taint/side-effects."""

    def _resolve_missing_deps(
        self,
        contract: Any,
        skill_id: str,
        project: Any,
        v: str,
        _executed_ok: set[str] | None,
    ) -> list[str]:
        if _executed_ok is not None:
            return [d for d in contract.depends_on_skills if d not in _executed_ok]
        return self.check_manifest_deps(skill_id, project, v)  # type: ignore[attr-defined]

    def _build_log_entry(
        self,
        contract: Any,
        result: Any,
        ts_inicio: Any,
        ts_fim: Any,
        execution_id: str,
        correlation_id: str,
        skill_id: str,
        catalog_source: str = "master",
    ) -> dict:
        return {
            "ts": ts_inicio.isoformat(),
            "execution_id": execution_id,
            "correlation_id": correlation_id,
            "skill": skill_id,
            # NEP-028 D4: proveniência de catálogo por run — reprodutibilidade auditável
            "catalog_source": catalog_source,
            "contract": {
                "required_inputs": contract.required_inputs,
                "optional_inputs": contract.optional_inputs,
                "depends_on_skills": contract.depends_on_skills,
                "produces_section": contract.produces_section,
            },
            "status": "ERRO" if result.has_errors else "OK",
            "duration_ms": int((ts_fim - ts_inicio).total_seconds() * 1000),
            "error_kind": "DOMINIO" if result.has_errors else None,
            "validacoes": [{"codigo": item.codigo, "status": item.status} for item in result.validacoes],
        }

    def run_skill(
        self,
        skill_id: str,
        project: ProjectStore,
        version: str | None = None,
        inputs: dict[str, Any] | None = None,
        trace_id: str | None = None,
        _executed_ok: set[str] | None = None,
    ) -> SkillResult:
        """Executa skill no modelo flat (vN) via FlatVersionStore → run_skill_on_plano."""
        from concilium.infrastructure.storage.flat_version_store import FlatVersionStore

        v = version or project.current_version()
        if v is None:
            raise RuntimeDomainError("Nenhuma versão ativa. Execute 'concilium version new' primeiro.")

        contract = self.get_skill_contract(skill_id)  # type: ignore[attr-defined]
        missing_deps = self._resolve_missing_deps(contract, skill_id, project, v, _executed_ok)
        if missing_deps:
            raise RuntimeDomainError(f"Skill '{skill_id}' requer execução prévia bem-sucedida de: {missing_deps}")

        return self.run_skill_on_plano(skill_id, project, FlatVersionStore(project, v), inputs, trace_id)

    def run_skill_on_plano(
        self,
        skill_id: str,
        project: ProjectStore,
        plano_store: Any,
        inputs: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> SkillResult:
        contract = self.get_skill_contract(skill_id)  # type: ignore[attr-defined]
        skill_fn = SKILLS[skill_id]

        canonical_in = plano_store.load_canonical()
        if canonical_in is None and skill_id != "01-escopo-e-eap":
            raise RuntimeDomainError(
                f"Plano '{plano_store.plano_id}' não possui estado inicial. Execute '01-escopo-e-eap' primeiro."
            )

        escopo_meta = plano_store.escopo_store.meta
        contexto, perfil, catalogo = self._load_context(escopo_meta, project)

        base_inputs = dict(escopo_meta)
        base_inputs.update(inputs or {})
        normalized_inputs = self._apply_runtime_defaults(skill_id, project, contexto, base_inputs)  # type: ignore[attr-defined]
        normalized_inputs.setdefault("escopo_id", escopo_meta["escopo_id"])
        normalized_inputs.setdefault("plano_id", plano_store.plano_id)

        ts_inicio = datetime.now(UTC)
        execution_id = normalized_inputs.get("execution_id") or str(uuid4())
        correlation_id = (
            normalized_inputs.get("correlation_id") or f"{project.meta.get('id', '')}:{plano_store.plano_id}"
        )
        kwargs = self._build_skill_kwargs(  # type: ignore[attr-defined]
            contract,
            canonical_in=canonical_in,
            inputs=normalized_inputs,
            catalogo=catalogo,
            perfil=perfil,
            contexto=contexto,
            project=project,
            version=plano_store.plano_id,
        )

        result = _execute_skill(skill_fn, kwargs, skill_id, execution_id, ts_inicio, plano_store)

        should_save = not (skill_id == "00-escopo" and result.has_errors)
        result, should_save = self._process_taint(skill_id, result, should_save)
        result, should_save = self._process_decision_variables(normalized_inputs, result, should_save)

        if should_save:
            plano_store.save_canonical(result.canonical, created_by=skill_id)

        self._process_side_effects(skill_id, result, project, plano_store.plano_id)

        ts_fim = datetime.now(UTC)
        catalog_source = str(catalogo.get("_catalog_source", "master")) if isinstance(catalogo, dict) else "master"
        plano_store.log_invocation(
            self._build_log_entry(
                contract, result, ts_inicio, ts_fim, execution_id, correlation_id, skill_id, catalog_source
            )
        )
        return result

    def _load_context(self, escopo_meta: dict, project: Any) -> tuple:
        contexto = self.load_contexto(escopo_meta.get("contexto_id") or project.meta["contexto_id"])  # type: ignore[attr-defined]
        perfil = self.load_perfil(escopo_meta.get("snapshot_perfil_id") or contexto.perfil_id)  # type: ignore[attr-defined]
        catalogo_id = escopo_meta.get("snapshot_catalogo_id") or contexto.catalogo_id
        catalogo = self._load_resolved_catalogo(catalogo_id, contexto.jurisdicao_id, project)  # type: ignore[attr-defined]
        catalogo["identidade_visual"] = self.load_tema(contexto.tema_id).to_catalogo_dict()  # type: ignore[attr-defined]
        return contexto, perfil, catalogo

    def _process_taint(self, skill_id: str, result: SkillResult, should_save: bool) -> tuple[SkillResult, bool]:
        if result.has_errors and skill_id in _GATE_SKILLS:
            canonical_before = result.canonical
            blocked = list(set(canonical_before.pipeline_blocked_from) | {skill_id})
            result = SkillResult(
                canonical_before.model_copy(
                    update={"pipeline_blocked_from": blocked, "pipeline_integridade": "CORROMPIDO"}
                ),
                result.validacoes,
            )
            return result, True
        elif not result.has_errors and skill_id in _GATE_SKILLS:
            current_blocked = set(result.canonical.pipeline_blocked_from)
            if skill_id in current_blocked:
                new_blocked = sorted(current_blocked - {skill_id})
                result = SkillResult(
                    result.canonical.model_copy(
                        update={
                            "pipeline_blocked_from": new_blocked,
                            "pipeline_integridade": "CORROMPIDO" if new_blocked else None,
                        }
                    ),
                    result.validacoes,
                )
                return result, True
        return result, should_save

    def _process_decision_variables(
        self, normalized_inputs: dict[str, Any], result: SkillResult, should_save: bool
    ) -> tuple[SkillResult, bool]:
        dv_raw = normalized_inputs.get("decision_variables")
        if dv_raw is not None and not result.has_errors:
            try:
                from concilium.domain.models.project.decision_variables import DecisionVariables

                dv_obj = DecisionVariables.model_validate(dv_raw) if isinstance(dv_raw, dict) else dv_raw
                if result.canonical.decision_variables != dv_obj:
                    result = SkillResult(
                        result.canonical.model_copy(update={"decision_variables": dv_obj}),
                        result.validacoes,
                        result.artifacts,
                    )
                    return result, True
            except Exception:
                pass
        return result, should_save

    def _process_side_effects(self, skill_id: str, result: SkillResult, project: ProjectStore, v: str) -> None:
        _persist_typed_artifacts(result, project, v)

        if skill_id == "09-relatorio-e-artefatos":
            try:
                _deliv_cfg = project.read_json("deliverables_config.json", {})
                _outputs_cfg: dict = _deliv_cfg.get("outputs", {})
            except Exception:
                _outputs_cfg = {}
            _handle_skill_09_side_effects(result, project, v, _outputs_cfg)

        elif skill_id == "12-registro-decisoes":
            decision_log = getattr(result, "decision_log", None)
            if decision_log:
                payload = json.dumps(decision_log, indent=2, ensure_ascii=False, default=_json_default)
                project.save_intermediate_file("decision_log.json", payload, v)
                (project.version_path(v) / "decision_log.json").write_text(payload, encoding="utf-8")

        elif skill_id == "04-cronograma":
            _handle_skill_04_side_effects(result, project, v)
