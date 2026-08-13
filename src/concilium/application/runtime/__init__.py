"""Runtime do Concilium: carrega config, valida dependências e executa skills."""

from __future__ import annotations

import functools
import inspect
import tomllib
from pathlib import Path
from typing import Any

from concilium.application.services.project.project_repository import PlanoHandle, ProjectHandle
from concilium.application.skills import MANIFEST_META, SKILLS
from concilium.application.skills.executor import ExecutionRecord, SkillExecutor
from concilium.domain.models.canonical import CanonicalModel

# Re-exports para compatibilidade retroativa
from .contracts import SkillExecutionContract
from .deliverables.reports.financial_report_markdown import render_financial_report_markdown
from .deliverables.reports.memorial_bdi_markdown import render_memorial_bdi_markdown as _memorial_bdi_to_md
from .deliverables.reports.pdf_renderer import render_markdown_pdf as _md_to_pdf_bytes
from .deliverables.reports.report_markdown_sections import render_planejamento_table
from .deliverables.side_effects import _json_default  # noqa: F401
from .exceptions import RuntimeDomainError, RuntimeError, RuntimeTechnicalError  # noqa: F401
from .gates import _GATE_SKILLS
from .helpers.pipeline import (
    _format_records,
    _on_after_skill,
    _parse_executed_skills,
    _print_skill_start,
    _resolve_state,
)
from .mixins.catalog import CatalogMixin
from .mixins.config import ConfigMixin
from .mixins.execution import ExecutionMixin
from .mixins.inputs import InputsMixin


def _md_planejamento(plan: list[dict[str, Any]]) -> list[str]:
    return render_planejamento_table(plan)


class Runtime(ConfigMixin, CatalogMixin, InputsMixin, ExecutionMixin):
    """Camada de orquestracao: composicao de stores + dispatch declarativo."""

    def load_manifest(self, skill_id: str) -> dict[str, Any] | None:
        key = f"manifest:{skill_id}"
        if key in self._config_cache:
            return self._config_cache[key]
        manifests_dir = Path(__file__).parent.parent / "skills" / "manifests"
        manifest_path = manifests_dir / skill_id / "skill.toml"
        if not manifest_path.exists():
            self._config_cache[key] = None
            return None
        with manifest_path.open("rb") as f:
            result = tomllib.load(f)
        self._config_cache[key] = result
        return result

    def get_skill_contract(self, skill_id: str) -> SkillExecutionContract:
        if skill_id not in SKILLS:
            raise RuntimeDomainError(f"Skill desconhecida: '{skill_id}'. Disponíveis: {list(SKILLS)}")
        manifest = self.load_manifest(skill_id) or {}
        fn = SKILLS[skill_id]
        signature = list(inspect.signature(fn).parameters.keys())
        inputs_cfg = manifest.get("inputs", {})
        depends_cfg = manifest.get("depends_on", {})
        produces_cfg = manifest.get("produces", {})
        return SkillExecutionContract(
            skill_id=skill_id,
            signature=signature,
            required_inputs=inputs_cfg.get("required", []),
            optional_inputs=inputs_cfg.get("optional", []),
            depends_on_skills=depends_cfg.get("skills", []),
            produces_section=produces_cfg.get("canonical_section"),
            output_schema={"result_type": "SkillResult", "fields": ["canonical", "validacoes", "has_errors"]},
        )

    def check_manifest_deps(self, skill_id: str, project: ProjectHandle, version: str) -> list[str]:
        manifest = self.load_manifest(skill_id)
        if manifest is None:
            return []
        dep_skills: list[str] = manifest.get("depends_on", {}).get("skills", [])
        if not dep_skills:
            return []
        # `version_path(version) / INVOCATIONS_LOG` é um Path lógico não-backed em
        # backends não-filesystem (StorageProjectHandle) — sempre ler via read_lines().
        lines = project.read_lines(f"{version}/{project.INVOCATIONS_LOG}")
        executed_ok = _parse_executed_skills(lines)
        return [dep for dep in dep_skills if dep not in executed_ok]

    def create_snapshots(self, project: ProjectHandle) -> dict[str, str]:
        """Cria snapshots imutáveis de jurisdição e perfil.

        ADR-066 Fase 8: o catálogo NÃO é mais copiado integralmente aqui — CPUs são
        resolvidas sob demanda via `resolve_cpu()` (catalogo_base) e o catálogo por
        skill via `_load_resolved_catalogo()`/`resolved_catalog.json` (Fase 4).
        Retorna o `catalogo_id` real (não mais um hash de conteúdo) para preencher
        `snapshot_catalogo_id` como referência de proveniência. Projetos antigos com
        `snapshots/catalogo-*.json` em disco continuam sendo lidos normalmente
        (fallback de `resolve_cpu`) — só a escrita foi removida.
        """
        snaps = project.snapshots
        contexto = self.load_contexto(project.meta["contexto_id"])
        result: dict[str, str] = {}
        result["jurisdicao"] = snaps.store("jurisdicao", self.load_jurisdicao(contexto.jurisdicao_id))
        result["perfil"] = snaps.store("perfil", self.load_perfil(contexto.perfil_id))
        result["catalogo"] = contexto.catalogo_id
        return result

    def run_pipeline(
        self,
        store: ProjectHandle,
        skill_inputs: dict[str, dict] | None = None,
        invocation_context: dict[str, Any] | None = None,
        skill_sequence: list[str] | None = None,
    ) -> list[dict]:
        """Executa o pipeline completo via SkillExecutor (domain-agnostic).

        O domínio é injetado como três closures:
        - providers_factory: resolve configs e normaliza inputs por skill
        - resolve_state: extrai canônico do resultado + aplica taint e decision variables
        - on_after_skill: persiste estado, processa side effects, grava invocations.log
        """
        skill_inputs = skill_inputs or {}
        invocation_context = invocation_context or {}
        version = store.current_version()
        if version is None:
            raise RuntimeDomainError("Nenhuma versão ativa. Execute 'concilium version new' primeiro.")

        initial_state = store.load_canonical(version)
        skip_bootstrap = initial_state is not None

        providers_factory = functools.partial(self._providers_factory, store, version)

        def resolve_state(skill_id: str, result: Any, prev_state: Any) -> Any:
            return _resolve_state(skill_id, result, skill_inputs)

        on_before_skill = functools.partial(_print_skill_start)

        def on_after_skill(skill_id: str, result: Any, new_state: Any, record: ExecutionRecord) -> None:
            _on_after_skill(self, store, version, invocation_context, skill_id, result, new_state, record)

        ordered_skill_ids = skill_sequence or list(SKILLS.keys())
        active_skills = {sid: SKILLS[sid] for sid in ordered_skill_ids if sid in SKILLS}
        if skip_bootstrap:
            active_skills = {sid: fn for sid, fn in active_skills.items() if sid != "01-escopo-e-eap"}
        executor = SkillExecutor(  # type: ignore[arg-type]
            active_skills,
            MANIFEST_META,
            on_before_skill=on_before_skill,
            on_after_skill=on_after_skill,
        )
        _final_state, records = executor.run_pipeline(
            state_in=initial_state,
            providers_factory=providers_factory,
            skill_inputs=skill_inputs,
            resolve_state=resolve_state,
        )

        return _format_records(records)

    def _providers_factory(self, store: Any, version: str, skill_id: str, state: Any, extra_inputs: dict) -> dict:
        contexto = self.load_contexto(store.meta["contexto_id"])
        perfil = self.load_perfil(contexto.perfil_id)
        catalogo = self._load_resolved_catalogo(contexto.catalogo_id, contexto.jurisdicao_id, store)
        catalogo["identidade_visual"] = self.load_tema(contexto.tema_id).to_catalogo_dict()
        # NEP-028 A1: propagar fonte do catálogo para observabilidade nos inputs (lido por integrações externas)
        normalized = self._apply_runtime_defaults(skill_id, store, contexto, extra_inputs)
        normalized.setdefault("_catalog_source", catalogo.get("_catalog_source", "master"))

        # ADR-100 Phase 4: CatalogSession cacheada por run — junction tables + drive-spill.
        # Criada uma vez por execução de pipeline e reutilizada entre skills.
        # Skills que declaram `catalog_session` recebem joins SQL vetorizados.
        session_key = f"{contexto.catalogo_id}:{contexto.jurisdicao_id}:{store.root.name}"
        catalog_session = self._get_or_create_catalog_session(catalogo, session_key)

        return {
            "canonical_in": state,
            "inputs": normalized,
            "catalogo": catalogo,
            "catalog_session": catalog_session,  # ADR-100: CatalogSession | None
            "perfil": perfil,
            "contexto": contexto,
            "project": store,
            "version": version,
            "runtime": self,
        }

    def _meta_is_gate(self, skill_id: str) -> bool:
        return MANIFEST_META.get(skill_id, {}).get("gate", False)

    def plan_with_decisions(
        self,
        canonical: CanonicalModel,
        decisions: Any,
        catalogo: dict | None = None,
        perfil: dict | None = None,
        extra_inputs: dict | None = None,
    ) -> tuple:
        from concilium.application.optimizer.loop import adjust_schedule

        return adjust_schedule(
            canonical_in=canonical,
            decision_variables=decisions,
            catalogo=catalogo,
            perfil=perfil,
            extra_inputs=extra_inputs,
        )

    def run_pipeline_on_plano(
        self,
        project: ProjectHandle,
        plano: PlanoHandle,
        skill_inputs: dict[str, dict] | None = None,
        skill_sequence: list[str] | None = None,
    ) -> list[dict]:
        """Executa pipeline no modelo Escopo/Plano.

        Estado (canonical, outputs, invocations.log) gravado no plano, dentro de
        escopos/{escopo_id}/planos/{plano_id}/. Contexto (catálogo, perfil,
        snapshots, overrides) lido do projeto.
        """
        from datetime import UTC, datetime

        from .gates import _GATE_SKILLS
        from .helpers.pipeline import _print_skill_start

        skill_inputs = skill_inputs or {}
        ordered = skill_sequence or list(SKILLS.keys())
        records: list[dict] = []
        executed_ok: set[str] = set()
        blocked = False

        for skill_id in ordered:
            if skill_id not in SKILLS:
                continue
            if blocked:
                break
            _print_skill_start(skill_id)
            ts0 = datetime.now(UTC)
            try:
                result = self.run_skill_on_plano(
                    skill_id,
                    project,
                    plano,
                    inputs=skill_inputs.get(skill_id),
                )
                duration_ms = int((datetime.now(UTC) - ts0).total_seconds() * 1000)
                status = "ERRO" if result.has_errors else "OK"
                entry: dict = {"skill_id": skill_id, "status": status, "duration_ms": duration_ms}
                errs = [v.mensagem for v in result.validacoes if v.status == "ERRO" and v.mensagem]
                if errs:
                    entry["erros"] = errs
                    print(f"[{status}] {duration_ms}ms  {'; '.join(errs[:3])}")
                else:
                    print(f"[{status}] {duration_ms}ms")
                records.append(entry)
                if not result.has_errors:
                    executed_ok.add(skill_id)
                elif skill_id in _GATE_SKILLS:
                    print(f"  [STOP] Interrompendo pipeline: skill portão '{skill_id}' falhou.")
                    blocked = True
            except Exception as exc:
                duration_ms = int((datetime.now(UTC) - ts0).total_seconds() * 1000)
                msg = str(exc)
                print(f"[EXCEPTION] {duration_ms}ms  {msg}")
                records.append({"skill_id": skill_id, "status": "EXCEPTION", "duration_ms": duration_ms, "erro": msg})
                if skill_id in _GATE_SKILLS:
                    print(f"  [STOP] Interrompendo pipeline: skill portão '{skill_id}' falhou.")
                    blocked = True

        return records
