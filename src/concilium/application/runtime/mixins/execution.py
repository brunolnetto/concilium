"""Mixin de execução: run_skill, run_skill_on_plano, taint, side effects."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from concilium.application.services.project.project_repository import ProjectHandle
from concilium.application.skills import SKILLS
from concilium.application.skills.base import SkillResult

from ..deliverables.side_effects import (
    _handle_skill_04_side_effects,
    _handle_skill_09_side_effects,
    _persist_typed_artifacts,
)
from ..exceptions import RuntimeDomainError
from ..gates import _GATE_SKILLS
from ..helpers.pipeline import _execute_skill

if TYPE_CHECKING:
    from ._host_protocol import RuntimeHost

    _Base = RuntimeHost
else:
    _Base = object


class ExecutionMixin(_Base):
    """Mixin com métodos de execução de skill e processamento de taint/side-effects.

    Herda de RuntimeHost só em TYPE_CHECKING: os métodos usados via `self.*` abaixo
    (get_skill_contract, check_manifest_deps, etc.) são fornecidos por outros mixins
    ou pelo próprio Runtime na composição final (ver runtime/__init__.py).
    """

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
        return self.check_manifest_deps(skill_id, project, v)

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
        project: ProjectHandle,
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

        contract = self.get_skill_contract(skill_id)
        missing_deps = self._resolve_missing_deps(contract, skill_id, project, v, _executed_ok)
        if missing_deps:
            raise RuntimeDomainError(f"Skill '{skill_id}' requer execução prévia bem-sucedida de: {missing_deps}")

        return self.run_skill_on_plano(skill_id, project, FlatVersionStore(project, v), inputs, trace_id)

    def run_skill_on_plano(
        self,
        skill_id: str,
        project: ProjectHandle,
        plano_store: Any,
        inputs: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> SkillResult:
        contract = self.get_skill_contract(skill_id)
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
        normalized_inputs = self._apply_runtime_defaults(skill_id, project, contexto, base_inputs)
        normalized_inputs.setdefault("escopo_id", escopo_meta["escopo_id"])
        normalized_inputs.setdefault("plano_id", plano_store.plano_id)

        ts_inicio = datetime.now(UTC)
        execution_id = normalized_inputs.get("execution_id") or str(uuid4())
        correlation_id = (
            normalized_inputs.get("correlation_id") or f"{project.meta.get('id', '')}:{plano_store.plano_id}"
        )
        kwargs = self._build_skill_kwargs(
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
        result = self._process_staleness_check(skill_id, contract, escopo_meta, result, plano_store)

        if should_save:
            plano_store.save_canonical(result.canonical, created_by=skill_id)
            # issue #121/#123: congelamento de premissas — suportado tanto pelo
            # modelo escopo/plano (PlanoStore) quanto pelo modelo vN flat
            # (FlatVersionStore, que delega para ProjectStore/StorageProjectHandle).
            # O hasattr() é mantido como defesa adicional para plano_stores que não
            # implementem o método (ex.: duplos de teste simplificados).
            if hasattr(plano_store, "write_premissas_efetivas"):
                plano_store.write_premissas_efetivas(skill_id, normalized_inputs, escopo_meta)

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
        contexto = self.load_contexto(escopo_meta.get("contexto_id") or project.meta["contexto_id"])
        perfil = self.load_perfil(escopo_meta.get("snapshot_perfil_id") or contexto.perfil_id)
        catalogo_id = escopo_meta.get("snapshot_catalogo_id") or contexto.catalogo_id
        catalogo = self._load_resolved_catalogo(catalogo_id, contexto.jurisdicao_id, project)
        catalogo["identidade_visual"] = self.load_tema(contexto.tema_id).to_catalogo_dict()
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
            except Exception:  # pragma: no cover
                pass
        return result, should_save

    def _process_staleness_check(
        self,
        skill_id: str,
        contract: Any,
        escopo_meta: dict[str, Any],
        result: SkillResult,
        plano_store: Any,
    ) -> SkillResult:
        """Detecta reexecução parcial com premissas divergentes entre skills dependentes.

        Compara o hash de `escopo_meta` (catálogo/jurisdição/perfil do escopo — a
        superfície de premissas compartilhada por todas as skills do plano) contra
        o hash registrado da última vez que cada dependência (`contract.depends_on_skills`)
        rodou. Se divergem, a dependência foi calculada sobre premissas diferentes
        das que este run está usando agora (ex: overlay de catálogo mudou entre uma
        corrida e outra sem reexecutar a cadeia inteira). Emite AVISO — não bloqueia
        a execução; o bloqueio, se cabível, é feito no gate de aprovação (issue #121,
        `application/orchestrators/plano_approval_gate.py`).
        """
        depends_on = getattr(contract, "depends_on_skills", None) or []
        # issue #121/#123: staleness é detectável tanto no modelo escopo/plano
        # (PlanoStore) quanto no modelo vN flat (FlatVersionStore). O hasattr()
        # é mantido como defesa adicional para plano_stores que não implementem
        # o método (ex.: duplos de teste simplificados).
        if not depends_on or not hasattr(plano_store, "read_premissas_por_skill"):
            return result

        import json
        from hashlib import sha256

        from concilium.domain.models.canonical import ValidacaoItem

        escopo_hash_atual = sha256(json.dumps(escopo_meta, sort_keys=True, default=str).encode()).hexdigest()
        por_skill = plano_store.read_premissas_por_skill()

        stale_deps = [
            dep
            for dep in depends_on
            if (registrado := por_skill.get(dep)) and registrado.get("escopo_hash") != escopo_hash_atual
        ]
        if not stale_deps:
            return result

        novas = [
            ValidacaoItem(
                codigo="VAL-STALE-UPSTREAM",
                status="AVISO",
                mensagem=(
                    f"Dependência '{dep}' de '{skill_id}' rodou com premissas de escopo "
                    "(catálogo/jurisdição/perfil) diferentes das atuais — recalcule a "
                    "cadeia antes de aprovar."
                ),
            )
            for dep in stale_deps
        ]
        return SkillResult(result.canonical, [*result.validacoes, *novas], result.artifacts)

    def _process_side_effects(self, skill_id: str, result: SkillResult, project: ProjectHandle, v: str) -> None:
        _persist_typed_artifacts(result, project, v)

        if skill_id == "09-relatorio-e-artefatos":
            try:
                _deliv_cfg = project.read_json("deliverables_config.json", {})
                _outputs_cfg: dict = _deliv_cfg.get("outputs", {})
            except Exception:  # pragma: no cover
                _outputs_cfg = {}
            _handle_skill_09_side_effects(result, project, v, _outputs_cfg)

        elif skill_id == "04-cronograma":
            _handle_skill_04_side_effects(result, project, v)
