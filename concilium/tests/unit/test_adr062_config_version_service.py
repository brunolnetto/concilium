"""Tests for ADR-062: ConfigVersionService (contexts and profiles versioning)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from concilium.application.services.contexto_version_service import (
    ConfigVersionService,
    ContextoVersionService,
    PerfilVersionService,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_config(tmp_path: Path) -> Path:
    """Creates a temporary config directory with versioned contexts and profiles."""
    # Versioned context: mendeslobo
    ctx_dir = tmp_path / "contextos" / "mendeslobo"
    (ctx_dir / "versions").mkdir(parents=True)
    (ctx_dir / "current").write_text("v1", encoding="utf-8")
    (ctx_dir / "contexto.json").write_text(
        json.dumps({"id": "mendeslobo", "nome": "Mendes Lobo", "current_version": "v1"}),
        encoding="utf-8",
    )
    (ctx_dir / "versions" / "v1.json").write_text(
        json.dumps(
            {
                "version": "v1",
                "created_at": "2026-01-01T00:00:00Z",
                "created_by": "system",
                "motivo": "inicial",
                "id": "mendeslobo",
                "catalogo_id": "cat_v1",
                "jurisdicao_id": "BR",
                "perfil_id": "padrao",
            }
        ),
        encoding="utf-8",
    )

    # Versioned profile: padrao
    perf_dir = tmp_path / "perfis" / "padrao"
    (perf_dir / "versions").mkdir(parents=True)
    (perf_dir / "current").write_text("v1", encoding="utf-8")
    (perf_dir / "perfil.json").write_text(
        json.dumps({"id": "padrao", "nome": "Padrão", "current_version": "v1"}),
        encoding="utf-8",
    )
    (perf_dir / "versions" / "v1.json").write_text(
        json.dumps(
            {
                "version": "v1",
                "created_at": "2026-01-01T00:00:00Z",
                "created_by": "system",
                "motivo": "inicial",
                "id": "padrao",
                "jurisdicao_id": "BR",
                "faixa_margem_alvo": {"min": 0.08, "max": 0.14},
            }
        ),
        encoding="utf-8",
    )

    return tmp_path


# ── ConfigVersionService Tests ────────────────────────────────────────────────


class TestConfigVersionService:
    def test_resolve_versioned_entity(self, tmp_config: Path) -> None:
        svc = ConfigVersionService(tmp_config, "contextos")
        ctx = svc.resolve("mendeslobo", "v1")
        assert ctx is not None
        assert ctx["catalogo_id"] == "cat_v1"
        assert ctx["version"] == "v1"

    def test_resolve_current_version_when_none_given(self, tmp_config: Path) -> None:
        svc = ConfigVersionService(tmp_config, "contextos")
        ctx = svc.resolve("mendeslobo")
        assert ctx is not None
        assert ctx["version"] == "v1"

    def test_resolve_nonexistent_returns_none(self, tmp_config: Path) -> None:
        svc = ConfigVersionService(tmp_config, "contextos")
        assert svc.resolve("does_not_exist") is None

    def test_current_version_default_v1(self, tmp_config: Path) -> None:
        svc = ConfigVersionService(tmp_config, "contextos")
        assert svc.current_version("mendeslobo") == "v1"

    def test_list_entities_includes_versioned_entities(self, tmp_config: Path) -> None:
        svc = ConfigVersionService(tmp_config, "contextos")
        entities = svc.list_entities()
        ids = [e["id"] for e in entities]
        assert "mendeslobo" in ids

    def test_list_entities_has_versions_field(self, tmp_config: Path) -> None:
        svc = ConfigVersionService(tmp_config, "contextos")
        mendeslobo = next(e for e in svc.list_entities() if e["id"] == "mendeslobo")
        assert mendeslobo["versions"] == [
            {
                "version": "v1",
                "catalogo_id": "cat_v1",
                "created_at": "2026-01-01T00:00:00Z",
                "created_by": "system",
                "motivo": "inicial",
                "jurisdicao_id": "BR",
                "perfil_id": "padrao",
            }
        ]

    def test_list_versions_for_entity(self, tmp_config: Path) -> None:
        svc = ConfigVersionService(tmp_config, "contextos")
        versions = svc.list_versions("mendeslobo")
        assert len(versions) == 1
        assert versions[0]["version"] == "v1"

    def test_create_version_increments_number(self, tmp_config: Path) -> None:
        svc = ConfigVersionService(tmp_config, "contextos")
        result = svc.create_version(
            "mendeslobo",
            fields={"catalogo_id": "cat_v2"},
            motivo="Atualizacao catalogo Q2",
            author="test_user",
        )
        assert result["version"] == "v2"
        assert result["catalogo_id"] == "cat_v2"
        assert result["motivo"] == "Atualizacao catalogo Q2"
        assert result["created_by"] == "test_user"

    def test_create_version_updates_current(self, tmp_config: Path) -> None:
        svc = ConfigVersionService(tmp_config, "contextos")
        svc.create_version("mendeslobo", {"catalogo_id": "cat_v2"}, "test", make_current=True)
        assert svc.current_version("mendeslobo") == "v2"

    def test_create_version_does_not_update_current_when_flag_false(self, tmp_config: Path) -> None:
        svc = ConfigVersionService(tmp_config, "contextos")
        svc.create_version("mendeslobo", {"catalogo_id": "cat_v2"}, "test", make_current=False)
        assert svc.current_version("mendeslobo") == "v1"

    def test_create_version_inherits_previous_fields(self, tmp_config: Path) -> None:
        svc = ConfigVersionService(tmp_config, "contextos")
        v2 = svc.create_version("mendeslobo", {"catalogo_id": "cat_v2"}, "update catalog")
        # Should inherit jurisdicao_id from v1
        assert v2["jurisdicao_id"] == "BR"

    def test_compare_same_version_returns_no_diff(self, tmp_config: Path) -> None:
        svc = ConfigVersionService(tmp_config, "contextos")
        diff = svc.compare("mendeslobo", "v1", "v1")
        assert diff["changed"] == {}

    def test_compare_different_versions_returns_diff(self, tmp_config: Path) -> None:
        svc = ConfigVersionService(tmp_config, "contextos")
        svc.create_version("mendeslobo", {"catalogo_id": "cat_v2"}, "update", make_current=False)
        diff = svc.compare("mendeslobo", "v1", "v2")
        assert "catalogo_id" in diff["changed"]
        assert diff["changed"]["catalogo_id"]["de"] == "cat_v1"
        assert diff["changed"]["catalogo_id"]["para"] == "cat_v2"

    def test_compare_result_has_unchanged_field(self, tmp_config: Path) -> None:
        svc = ConfigVersionService(tmp_config, "contextos")
        svc.create_version("mendeslobo", {"catalogo_id": "cat_v2"}, "update", make_current=False)
        diff = svc.compare("mendeslobo", "v1", "v2")
        assert "jurisdicao_id" in diff["unchanged"]


# ── Alias Tests ───────────────────────────────────────────────────────────────


class TestAliases:
    def test_contexto_version_service_is_alias(self, tmp_config: Path) -> None:
        svc = ContextoVersionService(tmp_config)
        ctx = svc.resolve("mendeslobo")
        assert ctx is not None
        assert ctx["catalogo_id"] == "cat_v1"

    def test_contexto_list_contexts_method(self, tmp_config: Path) -> None:
        svc = ContextoVersionService(tmp_config)
        contexts = svc.list_contexts()
        assert any(c["id"] == "mendeslobo" for c in contexts)

    def test_perfil_version_service_is_alias(self, tmp_config: Path) -> None:
        svc = PerfilVersionService(tmp_config)
        perfil = svc.resolve("padrao")
        assert perfil is not None
        assert perfil["jurisdicao_id"] == "BR"

    def test_perfil_list_perfis_method(self, tmp_config: Path) -> None:
        svc = PerfilVersionService(tmp_config)
        perfis = svc.list_perfis()
        assert any(p["id"] == "padrao" for p in perfis)

    def test_perfil_create_version(self, tmp_config: Path) -> None:
        svc = PerfilVersionService(tmp_config)
        v2 = svc.create_version(
            "padrao",
            {"faixa_margem_alvo": {"min": 0.10, "max": 0.18}},
            "Revisao metas margem Q3",
        )
        assert v2["version"] == "v2"
        assert v2["faixa_margem_alvo"] == {"min": 0.10, "max": 0.18}

    def test_perfil_compare(self, tmp_config: Path) -> None:
        svc = PerfilVersionService(tmp_config)
        svc.create_version("padrao", {"jurisdicao_id": "BR-CE"}, "jurisdicao especifica", make_current=False)
        diff = svc.compare("padrao", "v1", "v2")
        assert "jurisdicao_id" in diff["changed"]


# ── Backward Compatibility Tests ──────────────────────────────────────────────


class TestBackwardCompatibility:

    def test_empty_config_dir_returns_empty_list(self, tmp_path: Path) -> None:
        (tmp_path / "contextos").mkdir()
        svc = ContextoVersionService(tmp_path)
        assert svc.list_entities() == []

    def test_resolve_unknown_version_falls_back_to_latest(self, tmp_config: Path) -> None:
        svc = ContextoVersionService(tmp_config)
        # requesting non-existent "v99" should fall back to latest available
        ctx = svc.resolve("mendeslobo", "v99")
        assert ctx is not None  # falls back to v1
