"""Saved exact BDI declaration of a project (N9.1, #206).

The project's tax/profit declaration (``concilium.projeto.bdi-exato.v1``) is
saved beside the legacy float profile, with the same version scheme:

    bdi/perfil_bdi_exato.json             head (latest version)
    bdi/perfil_bdi_exato_v{NNN}.json      immutable snapshot of each version
    bdi/perfil_bdi_exato_diff_v{NNN}.json changed fields against the previous version

It is only ever written from an exact-string declaration, validated with the
code the exact price uses; the float ``bdi/perfil_bdi.json`` is never
converted. The runtime loads the head and hands its declaration to Skill06 as
``bdi_projeto_exato``; a project that has only the float profile gets a reason
instead, and its exact price is not evaluated until the profile is re-saved.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Protocol

from concilium.application.scheduling.exact_pricing_declaration import (
    PROJECT_SCHEMA,
    PricingDeclarationError,
    project_declaration_fingerprint,
    validate_project_declaration,
)

SAVED_SCHEMA = "concilium.projeto.bdi-exato-salvo.v1"
DIFF_SCHEMA = "concilium.projeto.bdi-exato-diff.v1"
HEAD = "bdi/perfil_bdi_exato.json"
LEGACY_HEAD = "bdi/perfil_bdi.json"
INPUT = "bdi_projeto_exato"
UNAVAILABLE_INPUT = "bdi_projeto_exato_indisponivel"
_RESAVE = (
    "re-save the project BDI profile in exact form (MCP salvar_perfil_bdi with declaracao_exata, or "
    f"`concilium bdi update --from-file` with a {PROJECT_SCHEMA} JSON)"
)


class ProjectBdiExactError(ValueError):
    """The exact project BDI declaration cannot be saved."""


class _ProjectFiles(Protocol):
    def exists(self, relative_path: str) -> bool: ...

    def read_json(self, relative_path: str, default: Any) -> Any: ...

    def write_json(self, relative_path: str, payload: Any) -> None: ...


def version_path(versao: int) -> str:
    return f"bdi/perfil_bdi_exato_v{versao:03d}.json"


def diff_path(versao: int) -> str:
    return f"bdi/perfil_bdi_exato_diff_v{versao:03d}.json"


def _record_problem(record: object) -> str | None:
    """Why a stored record is not a saved exact declaration, or ``None``."""
    if not isinstance(record, Mapping) or record.get("schema") != SAVED_SCHEMA:
        return f"it does not declare schema {SAVED_SCHEMA}"
    versao = record.get("versao")
    if type(versao) is not int or versao < 1:
        return "it has no positive integer versao"
    declaration = record.get("declaracao")
    try:
        validate_project_declaration(declaration)
    except PricingDeclarationError as exc:
        return str(exc)
    if record.get("content_hash") != project_declaration_fingerprint(declaration):
        return "content_hash does not match the stored declaration"
    return None


def _leaves(node: object, prefix: str = "") -> dict[str, object]:
    if isinstance(node, Mapping):
        out: dict[str, object] = {}
        for key, value in node.items():
            out.update(_leaves(value, f"{prefix}.{key}" if prefix else str(key)))
        return out
    return {prefix: node}


def save_exact_project_bdi(
    project: _ProjectFiles,
    projeto_id: str,
    declaration: object,
    *,
    confirmado_por: str,
    motivo_revisao: str | None,
    profile_rows: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Validate and save a new version of the project's exact declaration.

    Nothing is written unless the declaration is valid (against ``profile_rows``
    when the caller has the profile's ``tabela_bdi.linhas``; structurally and
    for exactness otherwise), the previous head is intact and the new snapshot
    does not exist yet. Returns the saved record, with ``diff`` from version 2 on.
    """
    try:
        validate_project_declaration(declaration, profile_rows)
    except PricingDeclarationError as exc:
        raise ProjectBdiExactError(str(exc)) from exc
    if not isinstance(confirmado_por, str) or not confirmado_por.strip():
        raise ProjectBdiExactError("confirmado_por is required")

    previous: Mapping[str, Any] | None = None
    if project.exists(HEAD):
        stored = project.read_json(HEAD, None)
        problem = _record_problem(stored)
        if problem is not None:
            raise ProjectBdiExactError(
                f"{HEAD} is not a valid saved exact declaration ({problem}); it is not overwritten"
            )
        previous = stored
    versao = 1 if previous is None else previous["versao"] + 1
    if previous is not None and (not isinstance(motivo_revisao, str) or not motivo_revisao.strip()):
        raise ProjectBdiExactError(
            f"motivo_revisao is required to update an existing exact BDI declaration (current version: {versao - 1})"
        )
    if project.exists(version_path(versao)):
        raise ProjectBdiExactError(f"{version_path(versao)} already exists; snapshots are immutable")

    record: dict[str, Any] = {
        "schema": SAVED_SCHEMA,
        "projeto_id": projeto_id,
        "versao": versao,
        "content_hash": project_declaration_fingerprint(declaration),
        "confirmado_em": datetime.now(UTC).isoformat(),
        "confirmado_por": confirmado_por,
        "motivo_revisao": motivo_revisao,
        "declaracao": declaration,
    }
    diff: dict[str, Any] | None = None
    if previous is not None:
        before, after = _leaves(previous["declaracao"]), _leaves(declaration)
        changed = sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))
        diff = {
            "schema": DIFF_SCHEMA,
            "projeto_id": projeto_id,
            "versao_anterior": previous["versao"],
            "versao_nova": versao,
            "content_hash_anterior": previous["content_hash"],
            "content_hash_novo": record["content_hash"],
            "motivo": motivo_revisao,
            "campos_alterados": changed,
            "gerado_em": record["confirmado_em"],
        }
        project.write_json(diff_path(versao), diff)
    project.write_json(version_path(versao), record)
    project.write_json(HEAD, record)
    return {**record, "diff": diff} if diff is not None else record


def load_exact_project_bdi(project: _ProjectFiles) -> tuple[dict[str, Any] | None, str | None]:
    """``(declaration, reason)`` of the project's saved exact declaration.

    ``(declaration, None)`` when one is saved and intact; ``(None, reason)``
    when the project has project-specific BDI terms the exact path cannot read
    (a damaged exact file, or only the legacy float profile — never converted);
    ``(None, None)`` when the project declares nothing of its own.
    """
    if project.exists(HEAD):
        record = project.read_json(HEAD, None)
        problem = _record_problem(record)
        if problem is not None:
            return None, f"{HEAD} is not a valid saved exact declaration ({problem}); {_RESAVE}"
        return dict(record["declaracao"]), None
    if project.exists(LEGACY_HEAD):
        return None, (
            f"the project has only the legacy floating-point BDI profile ({LEGACY_HEAD}), which is never "
            f"converted; {_RESAVE}"
        )
    return None, None


def inject_exact_project_bdi(project: _ProjectFiles, inputs: dict[str, Any]) -> None:
    """Skill06 inputs: the saved declaration, unless the caller stated its own terms.

    An explicit ``bdi_projeto_exato`` or a hand-written ``p21_pricing_evidence``
    in the run inputs wins and nothing is loaded.
    """
    if inputs.get(INPUT) is not None or inputs.get("p21_pricing_evidence") is not None:
        return
    declaration, reason = load_exact_project_bdi(project)
    if declaration is not None:
        inputs[INPUT] = declaration
    elif reason is not None:
        inputs[UNAVAILABLE_INPUT] = reason
