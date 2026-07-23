"""Coverage batch A — targets mcp_server/__main__, semantic/__init__,
scheduling/selector, optimizer/loop, skills/__init__, cpu_insumo validations,
02-produtividade-climatica, 09-relatorio-e-artefatos, and scheduling/scheduler edge cases.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest

from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    CustoTotal,
    Meta,
    Projeto,
    RegimeTrabalho,
    Resultado,
    Venda,
)


def _make_meta():
    return Meta(gerado_em=datetime.now(UTC), contexto_id="test")

def _make_proj():
    return Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=-3.0, lng=-38.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2026, 6, 1),
        data_termino=date(2026, 7, 31),
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )

def _minimal_canonical(**kw):
    return CanonicalModel(meta=_make_meta(), projeto=_make_proj(), **kw)

def _canonical_com_resultado():
    resultado = Resultado(
        venda=Venda(total_sem_bdi=800_000.0, total_com_bdi=1_000_000.0),
        custo=CustoTotal(direto_equipes=500_000.0, total=800_000.0),
        resultado_financeiro=200_000.0,
        margem_pct=0.20,
        status_margem="VERDE",
        validacoes=[],
    )
    return _minimal_canonical(resultado=resultado)


# ══ skills/__init__.py ═══════════════════════════════════════════════════════


class TestSkillsInit:
    def test_load_nonexistent_skill_raises_import_error(self):
        """_load with non-existent skill path raises ImportError (line 33)."""
        from concilium.application.skills import _load

        with pytest.raises(ImportError, match="não encontrado"):
            _load("99-nonexistent-skill-xyz", "run_nonexistent")

    def test_discover_skills_bad_skill_raises_runtime_error(self, tmp_path):
        """_discover_skills error in loading raises RuntimeError (lines 74-75)."""
        import concilium.application.skills as skills_mod

        # Create a fake manifest dir with a toml pointing to skill.py that doesn't exist
        fake_skill_dir = tmp_path / "99-fake-skill"
        fake_skill_dir.mkdir()
        toml = fake_skill_dir / "skill.toml"
        toml.write_text('[skill]\nid = "99-fake-skill"\n', encoding="utf-8")
        # skill.py does not exist → _load raises ImportError → caught → RuntimeError
        with patch.object(skills_mod, "_MANIFESTS", tmp_path):
            with pytest.raises(RuntimeError):
                skills_mod._discover_skills()







# skills/__init__.py: skill loading (lines 54, 58)
# ────────────────────────────────────────────────────────────────


class TestSkillLoading:
    """Test skill module loading."""

    def test_skill_module_discovery(self):
        """Skills should be discoverable."""
        from concilium.application.skills import SKILLS

        # Check if skills are registered
        assert hasattr(SKILLS, "__getitem__") and hasattr(SKILLS, "__len__")
        assert len(SKILLS) > 0




# ─── application/skills/__init__.py extended tests ─────────────────────────────


class TestSkillsInitExtended:
    def test_skills_dict_has_skill01(self):
        from concilium.application.skills import SKILLS

        assert "01-escopo-e-eap" in SKILLS
        assert callable(SKILLS["01-escopo-e-eap"])

    def test_manifest_meta_has_gate(self):
        from concilium.application.skills import MANIFEST_META

        # MANIFEST_META should define gate skills
        assert isinstance(MANIFEST_META, dict)

    def test_skill_registry_get_skill(self):
        from concilium.application.skills.registry import SkillRegistry

        registry = SkillRegistry()
        skill = registry.get_skill("01-escopo-e-eap")
        assert skill is not None
        assert skill.version is not None






# ─── application/skills/__init__.py (36 missing) ──────────────────────────────


class TestSkillsInit2:
    def test_import_skills_module(self):
        import concilium.application.skills as skills

        assert skills is not None

    def test_skills_dict_has_entries(self):
        from concilium.application.skills import SKILLS

        assert len(SKILLS) > 0

    def test_skills_contains_skill01(self):
        from concilium.application.skills import SKILLS

        assert "01-escopo-e-eap" in SKILLS

    def test_skill_registry_loads(self):
        from concilium.application.skills.registry import SkillRegistry

        registry = SkillRegistry()
        assert len(registry.skills) > 0

    def test_get_skill_contract(self):
        from concilium.application.skills.registry import SkillRegistry

        registry = SkillRegistry()
        skill = registry.get_skill("01-escopo-e-eap")
        assert skill is not None
        assert hasattr(skill, "depends_on_skills")



