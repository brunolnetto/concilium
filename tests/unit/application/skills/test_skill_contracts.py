"""Regression tests: contrato declarativo por manifesto para todas as skills."""

from __future__ import annotations

import tomllib
from pathlib import Path

from concilium.application.runtime import Runtime
from concilium.application.skills import SKILLS


def _manifests_dir() -> Path:
    return Path(__file__).resolve().parents[4] / "src" / "concilium" / "application" / "skills" / "manifests"


def _load_manifest(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def test_todas_skills_tem_manifesto_e_vice_versa(config_root) -> None:
    runtime = Runtime(config_root)
    manifests = sorted(_manifests_dir().glob("*/skill.toml"))
    assert manifests, "Nenhum manifesto encontrado em skills/manifests"

    manifest_ids: set[str] = set()
    for manifest_path in manifests:
        manifest = _load_manifest(manifest_path)
        skill_id = manifest.get("skill", {}).get("id")
        assert skill_id, f"Manifesto sem skill.id: {manifest_path}"
        manifest_ids.add(skill_id)
        assert skill_id in SKILLS, f"Skill do manifesto nao carregada em SKILLS: {skill_id}"

        contract = runtime.get_skill_contract(skill_id)
        assert contract.skill_id == skill_id
        assert contract.signature, f"Assinatura vazia para {skill_id}"
        assert "inputs" in contract.signature, f"Assinatura sem inputs em {skill_id}"

    skills_ids = set(SKILLS.keys())
    assert skills_ids == manifest_ids, (
        f"Divergencia entre SKILLS e manifests. "
        f"Somente em SKILLS={sorted(skills_ids - manifest_ids)}; "
        f"somente em manifests={sorted(manifest_ids - skills_ids)}"
    )


def test_manifestos_definem_contrato_estrutural_valido(config_root) -> None:
    runtime = Runtime(config_root)
    manifests = sorted(_manifests_dir().glob("*/skill.toml"))
    all_skill_ids = set(SKILLS.keys())

    for manifest_path in manifests:
        manifest = _load_manifest(manifest_path)
        skill_id = manifest["skill"]["id"]
        contract = runtime.get_skill_contract(skill_id)

        # inputs.required/optional devem ser listas sem intersecao
        assert isinstance(contract.required_inputs, list), f"required_inputs invalido em {skill_id}"
        assert isinstance(contract.optional_inputs, list), f"optional_inputs invalido em {skill_id}"
        assert not (set(contract.required_inputs) & set(contract.optional_inputs)), (
            f"Inputs repetidos entre required e optional em {skill_id}"
        )

        # depends_on.skills deve referenciar skills existentes
        assert isinstance(contract.depends_on_skills, list), f"depends_on_skills invalido em {skill_id}"
        unknown_deps = [dep for dep in contract.depends_on_skills if dep not in all_skill_ids]
        assert not unknown_deps, f"Dependencias desconhecidas em {skill_id}: {unknown_deps}"

        # produces.canonical_section deve estar declarado para rastreabilidade
        assert contract.produces_section is not None, f"produces.canonical_section ausente em {skill_id}"

        # output_schema padrao do contrato unico
        assert contract.output_schema["result_type"] == "SkillResult"
        assert "canonical" in contract.output_schema["fields"]
        assert "validacoes" in contract.output_schema["fields"]
        assert "has_errors" in contract.output_schema["fields"]
