"""Tests for concilium.application.services.project.formulario_service — coverage sweep."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from concilium.application.services.project.formulario_service import (
    build_eap,
    criar_projeto,
    suggest_cpu,
)

# ── suggest_cpu ───────────────────────────────────────────────────────────────


_MAPPER_PATH = "concilium.infrastructure.catalog.mapping.cpu_mapper._load_mapping_keywords"


class TestSuggestCpuKeywordRules:
    def test_load_mapping_keywords_raises_falls_through_to_catalog(self, tmp_path):
        """Lines 32-44: exception in _load_mapping_keywords → falls through."""
        catalogos = tmp_path / "catalogos" / "cat1" / "cpus"
        catalogos.mkdir(parents=True)
        cpu_file = catalogos / "CPU-001.json"
        cpu_file.write_text(
            json.dumps({"codigo": "CPU-001", "descricao": "Escavacao de solo mole"}),
            encoding="utf-8",
        )

        # Patch _load_mapping_keywords to raise so the try/except falls through
        with patch(_MAPPER_PATH, side_effect=ImportError("no module")):
            cpu_id, score = suggest_cpu("Escavacao de solo mole em fundacao", config_root=tmp_path)
        # Should fall through to catalog overlap; overlap >= 2 → returns cpu_id, 1
        assert cpu_id == "CPU-001"
        assert score == 1

    def test_all_keywords_match_returns_score_2(self):
        """Lines 37-39: all keywords match → score 2."""
        rules = {"CPU-XYZ": ["ESCAVACAO", "MECANICA"]}
        with patch(_MAPPER_PATH, return_value=rules):
            cpu_id, score = suggest_cpu("Escavacao Mecanica de solos", config_root=Path("/nonexistent"))
        assert cpu_id == "CPU-XYZ"
        assert score == 2

    def test_any_keyword_matches_returns_score_1(self):
        """Lines 40-42: any keyword matches → score 1 (no all-match)."""
        # CPU-ABC requires BOTH ESCAVACAO and MECANICA (all-match fails for input without MECANICA)
        # any-match will hit because ESCAVACAO is present
        rules = {"CPU-ABC": ["ESCAVACAO", "MECANICA"]}
        with patch(_MAPPER_PATH, return_value=rules):
            # Has ESCAVACAO but not MECANICA → all() fails, any() passes → score 1
            cpu_id, score = suggest_cpu("Escavacao manual de fundacao", config_root=Path("/nonexistent"))
        assert cpu_id == "CPU-ABC"
        assert score == 1


class TestSuggestCpuCatalogOverlap:
    def test_catalog_overlap_gte_2_returns_cpu_id(self, tmp_path):
        """Lines 59-81: config_root given, catalog dir, overlap >= 2 → cpu_id, 1."""
        catalogos = tmp_path / "catalogos" / "2024" / "cpus"
        catalogos.mkdir(parents=True)
        cpu_file = catalogos / "CPU-999.json"
        cpu_file.write_text(
            json.dumps({"codigo": "CPU-999", "descricao": "Escavacao mecanica solo argiloso"}),
            encoding="utf-8",
        )

        with patch(
            "concilium.infrastructure.catalog.mapping.cpu_mapper._load_mapping_keywords",
            return_value={},
        ):
            cpu_id, score = suggest_cpu("Escavacao mecanica solo", config_root=tmp_path)
        assert cpu_id == "CPU-999"
        assert score == 1

    def test_catalog_overlap_lt_2_returns_none(self, tmp_path):
        """Lines 80-81 (else branch): best_score < 2 → None, 0."""
        catalogos = tmp_path / "catalogos" / "2024" / "cpus"
        catalogos.mkdir(parents=True)
        cpu_file = catalogos / "CPU-888.json"
        cpu_file.write_text(
            json.dumps({"codigo": "CPU-888", "descricao": "Concreto moldado"}),
            encoding="utf-8",
        )

        with patch(
            "concilium.infrastructure.catalog.mapping.cpu_mapper._load_mapping_keywords",
            return_value={},
        ):
            # only 1 word overlap ("CONCRETO") < 2
            cpu_id, score = suggest_cpu("Concreto X", config_root=tmp_path)
        assert cpu_id is None
        assert score == 0

    def test_short_desc_no_words_gt_3_chars(self):
        """Lines 47-49: no words longer than 3 chars → None, 0 immediately."""
        with patch(
            "concilium.infrastructure.catalog.mapping.cpu_mapper._load_mapping_keywords",
            return_value={},
        ):
            cpu_id, score = suggest_cpu("ab cd")
        assert cpu_id is None
        assert score == 0

    def test_config_root_path_exception_returns_none(self, tmp_path):
        """Lines 51-83 outer except: exception accessing config_root → None, 0."""
        bad_root = tmp_path / "does_not_exist"
        # iterdir on non-existent raises FileNotFoundError

        with patch(
            "concilium.infrastructure.catalog.mapping.cpu_mapper._load_mapping_keywords",
            return_value={},
        ):
            cpu_id, score = suggest_cpu("Escavacao mecanica solo argiloso profundo", config_root=bad_root)
        assert cpu_id is None
        assert score == 0

    def test_uses_get_storage_when_config_root_none(self):
        """Lines 52-55: config_root is None → calls get_storage()."""
        mock_storage = MagicMock()
        mock_storage.config_root = Path("/nonexistent/root")

        with (
            patch(_MAPPER_PATH, return_value={}),
            patch(
                "concilium.infrastructure.settings.get_storage",
                return_value=mock_storage,
            ),
        ):
            cpu_id, score = suggest_cpu("Escavacao mecanica solo argiloso profundo")
        # get_storage was called and fell through to exception (nonexistent path)
        assert cpu_id is None
        assert score == 0

    def test_catalog_uses_codigo_field(self, tmp_path):
        """Line 77: uses data['codigo'] as cpu_id."""
        catalogos = tmp_path / "catalogos" / "2024" / "cpus"
        catalogos.mkdir(parents=True)
        cpu_file = catalogos / "CPU-777.json"
        cpu_file.write_text(
            json.dumps({"codigo": "MY-CODE", "descricao": "Escavacao mecanica solo argiloso"}),
            encoding="utf-8",
        )

        with patch(
            "concilium.infrastructure.catalog.mapping.cpu_mapper._load_mapping_keywords",
            return_value={},
        ):
            cpu_id, score = suggest_cpu("Escavacao mecanica solo argiloso", config_root=tmp_path)
        assert cpu_id == "MY-CODE"
        assert score == 1

    def test_catalog_falls_back_to_stem_when_no_codigo(self, tmp_path):
        """Line 77: falls back to f.stem when no codigo or cpu_id."""
        catalogos = tmp_path / "catalogos" / "2024" / "cpus"
        catalogos.mkdir(parents=True)
        cpu_file = catalogos / "CPU-STEM.json"
        cpu_file.write_text(
            json.dumps({"descricao": "Escavacao mecanica solo argiloso"}),
            encoding="utf-8",
        )

        with patch(
            "concilium.infrastructure.catalog.mapping.cpu_mapper._load_mapping_keywords",
            return_value={},
        ):
            cpu_id, score = suggest_cpu("Escavacao mecanica solo argiloso", config_root=tmp_path)
        assert cpu_id == "CPU-STEM"
        assert score == 1

    def test_bad_json_in_catalog_file_continues(self, tmp_path):
        """Lines 78-79: bad JSON in one file → continue to next."""
        catalogos = tmp_path / "catalogos" / "2024" / "cpus"
        catalogos.mkdir(parents=True)
        bad_file = catalogos / "CPU-BAD.json"
        bad_file.write_text("not valid json", encoding="utf-8")
        good_file = catalogos / "CPU-GOOD.json"
        good_file.write_text(
            json.dumps({"codigo": "CPU-GOOD", "descricao": "Escavacao mecanica solo argiloso"}),
            encoding="utf-8",
        )

        with patch(
            "concilium.infrastructure.catalog.mapping.cpu_mapper._load_mapping_keywords",
            return_value={},
        ):
            cpu_id, score = suggest_cpu("Escavacao mecanica solo argiloso", config_root=tmp_path)
        assert cpu_id == "CPU-GOOD"
        assert score == 1


# ── build_eap ─────────────────────────────────────────────────────────────────


class TestBuildEap:
    def test_service_with_cpu_id_confianca_alta(self):
        """Lines 119-137: service with cpu_id → score=2, confianca=alta, mapeados."""
        servicos = [{"descricao": "Servico A", "quantidade": 10, "unidade": "m2", "cpu_id": "CPU-001"}]
        result = build_eap(servicos)
        assert len(result["mapeados"]) == 1
        assert len(result["nao_mapeados"]) == 0
        assert result["mapeados"][0]["_confianca"] == "alta"
        assert result["mapeados"][0]["cpu_id"] == "CPU-001"
        assert result["total"] == 1

    def test_service_without_cpu_id_suggest_returns_cpu_goes_to_mapeados(self):
        """Lines 121-122, 136-137: no cpu_id, suggest returns cpu_id → mapeados."""
        servicos = [{"descricao": "Escavacao manual", "quantidade": 5, "unidade": "m3"}]
        with patch(
            "concilium.application.services.project.formulario_service.suggest_cpu",
            return_value=("CPU-SUG", 1),
        ):
            result = build_eap(servicos)
        assert len(result["mapeados"]) == 1
        assert result["mapeados"][0]["cpu_id"] == "CPU-SUG"
        assert result["mapeados"][0]["_confianca"] == "media"
        assert len(result["nao_mapeados"]) == 0

    def test_service_without_cpu_id_suggest_returns_none_goes_to_nao_mapeados(self):
        """Lines 138-139: suggest returns None → nao_mapeados with cpu_id=None."""
        servicos = [{"descricao": "Servico desconhecido", "quantidade": 1, "unidade": "vb"}]
        with patch(
            "concilium.application.services.project.formulario_service.suggest_cpu",
            return_value=(None, 0),
        ):
            result = build_eap(servicos)
        assert len(result["nao_mapeados"]) == 1
        assert result["nao_mapeados"][0]["cpu_id"] is None
        assert result["nao_mapeados"][0]["_confianca"] == "nenhuma"
        assert len(result["mapeados"]) == 0

    def test_mixed_services(self):
        """Lines 112-141: mix of mapped and unmapped services."""
        servicos = [
            {"descricao": "Servico A", "cpu_id": "CPU-001", "quantidade": 10, "unidade": "m2"},
            {"descricao": "Servico B", "quantidade": 5, "unidade": "m3"},
        ]

        def fake_suggest(desc, config_root=None):
            if "B" in desc:
                return (None, 0)
            return ("CPU-999", 2)

        with patch(
            "concilium.application.services.project.formulario_service.suggest_cpu",
            side_effect=fake_suggest,
        ):
            result = build_eap(servicos)
        assert len(result["mapeados"]) == 1
        assert len(result["nao_mapeados"]) == 1
        assert result["total"] == 2

    def test_default_item_id_and_values(self):
        """Lines 112-117: default item_id, quantidade, unidade."""
        servicos = [{"descricao": "Servico sem campos opcionais"}]
        with patch(
            "concilium.application.services.project.formulario_service.suggest_cpu",
            return_value=("CPU-X", 2),
        ):
            result = build_eap(servicos)
        item = result["mapeados"][0]
        assert item["item_id"] == "eap-1_1"
        assert item["quantitativo"] == 1.0
        assert item["unidade"] == "un"
        assert item["predecessores"] == []


# ── criar_projeto ─────────────────────────────────────────────────────────────


def _make_mock_store(project_root_name: str = "proj-abc"):
    store = MagicMock()
    store.root = MagicMock()
    store.root.name = project_root_name
    es = MagicMock()
    ps = MagicMock()
    ps.plano_id = "plano-001"
    es.create_plan.return_value = ps
    store.create_escopo.return_value = es
    return store, es, ps


def _mapped_servicos():
    return [{"descricao": "Escavacao", "quantidade": 10, "unidade": "m3", "cpu_id": "CPU-001"}]


class TestCriarProjeto:
    def test_nao_mapeados_present_returns_pendente_mapeamento(self):
        """Lines 192-210: nao_mapeados → pendente_mapeamento."""
        servicos = [{"descricao": "Servico desconhecido", "quantidade": 1, "unidade": "vb"}]
        with patch(
            "concilium.application.services.project.formulario_service.suggest_cpu",
            return_value=(None, 0),
        ):
            result = criar_projeto(
                nome="Proj",
                contexto_id="ctx-1",
                tipo_obra="predial",
                localizacao="SP",
                data_inicio="2026-01-01",
                servicos=servicos,
                projetos_root=Path("/tmp/proj"),
            )
        assert result["status"] == "pendente_mapeamento"
        assert "nao_mapeados" in result
        assert "instrucoes" in result

    def test_all_mapped_lifecycle_raises_returns_erro(self, tmp_path):
        """Lines 257-263: LifecycleCoordinator raises → erro."""
        store, es, ps = _make_mock_store()

        mock_runtime = MagicMock()
        mock_contexto = MagicMock()
        mock_contexto.referencia_id = "ref-2024"
        mock_runtime.load_contexto.return_value = mock_contexto

        with (
            patch("concilium.infrastructure.storage.project.ProjectStore") as MockPS,
            patch(
                "concilium.application.runtime.Runtime",
                return_value=mock_runtime,
            ),
            patch(
                "concilium.application.orchestrators.lifecycle_coordinator.LifecycleCoordinator",
                side_effect=RuntimeError("boom"),
            ),
        ):
            MockPS.init.return_value = store
            result = criar_projeto(
                nome="Proj",
                contexto_id="ctx-1",
                tipo_obra="predial",
                localizacao="SP",
                data_inicio="2026-01-01",
                servicos=_mapped_servicos(),
                projetos_root=tmp_path,
            )
        assert result["status"] == "erro"
        assert "erro" in result
        assert result["project_id"] == "proj-abc"

    def test_all_mapped_has_errors_returns_erro_escopo(self, tmp_path):
        """Lines 265-273: r.has_errors → erro_escopo."""
        store, es, ps = _make_mock_store()

        mock_runtime = MagicMock()
        mock_contexto = MagicMock()
        mock_contexto.referencia_id = "ref-2024"
        mock_runtime.load_contexto.return_value = mock_contexto

        mock_result = MagicMock()
        mock_result.has_errors = True
        val1 = MagicMock()
        val1.mensagem = "Campo obrigatorio ausente"
        val1.status = "ERRO"
        mock_result.validacoes = [val1]

        mock_coord = MagicMock()
        mock_coord.avancar_plano.return_value = mock_result

        with (
            patch("concilium.infrastructure.storage.project.ProjectStore") as MockPS,
            patch(
                "concilium.application.runtime.Runtime",
                return_value=mock_runtime,
            ),
            patch(
                "concilium.application.orchestrators.lifecycle_coordinator.LifecycleCoordinator",
                return_value=mock_coord,
            ),
        ):
            MockPS.init.return_value = store
            result = criar_projeto(
                nome="Proj",
                contexto_id="ctx-1",
                tipo_obra="predial",
                localizacao="SP",
                data_inicio="2026-01-01",
                servicos=_mapped_servicos(),
                projetos_root=tmp_path,
            )
        assert result["status"] == "erro_escopo"
        assert "erros" in result
        assert result["erros"] == ["Campo obrigatorio ausente"]
        assert result["plano_id"] == "plano-001"

    def test_all_mapped_success_returns_criado(self, tmp_path):
        """Lines 275-283: success → criado."""
        store, es, ps = _make_mock_store()

        mock_runtime = MagicMock()
        mock_contexto = MagicMock()
        mock_contexto.referencia_id = "ref-2024"
        mock_runtime.load_contexto.return_value = mock_contexto

        mock_result = MagicMock()
        mock_result.has_errors = False

        mock_coord = MagicMock()
        mock_coord.avancar_plano.return_value = mock_result

        with (
            patch("concilium.infrastructure.storage.project.ProjectStore") as MockPS,
            patch(
                "concilium.application.runtime.Runtime",
                return_value=mock_runtime,
            ),
            patch(
                "concilium.application.orchestrators.lifecycle_coordinator.LifecycleCoordinator",
                return_value=mock_coord,
            ),
        ):
            MockPS.init.return_value = store
            result = criar_projeto(
                nome="Proj",
                contexto_id="ctx-1",
                tipo_obra="predial",
                localizacao="SP",
                data_inicio="2026-01-01",
                servicos=_mapped_servicos(),
                projetos_root=tmp_path,
            )
        assert result["status"] == "criado"
        assert result["project_id"] == "proj-abc"
        assert result["escopo_id"] == "esc-principal"
        assert result["plano_id"] == "plano-001"
        assert result["proxima_skill_sugerida"] == "02-produtividade-climatica"
        assert "eap_preview" in result
        assert result["total_itens"] == 1

    def test_projetos_root_none_uses_get_storage(self, tmp_path):
        """Lines 217-220: projetos_root=None → uses get_storage().projects_root."""
        store, es, ps = _make_mock_store()

        mock_storage = MagicMock()
        mock_storage.projects_root = tmp_path

        mock_runtime = MagicMock()
        mock_contexto = MagicMock()
        mock_contexto.referencia_id = "ref-2024"
        mock_runtime.load_contexto.return_value = mock_contexto

        mock_result = MagicMock()
        mock_result.has_errors = False

        mock_coord = MagicMock()
        mock_coord.avancar_plano.return_value = mock_result

        with (
            patch("concilium.infrastructure.storage.project.ProjectStore") as MockPS,
            patch(
                "concilium.application.runtime.Runtime",
                return_value=mock_runtime,
            ),
            patch(
                "concilium.application.orchestrators.lifecycle_coordinator.LifecycleCoordinator",
                return_value=mock_coord,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage",
                return_value=mock_storage,
            ),
        ):
            MockPS.init.return_value = store
            result = criar_projeto(
                nome="Proj",
                contexto_id="ctx-1",
                tipo_obra="predial",
                localizacao="SP",
                data_inicio="2026-01-01",
                servicos=_mapped_servicos(),
                projetos_root=None,
            )
        assert result["status"] == "criado"

    def test_projetos_root_none_and_storage_none_raises(self):
        """Lines 217-220: projects_root=None from storage → RuntimeError."""
        mock_storage = MagicMock()
        mock_storage.projects_root = None

        with (
            patch(
                "concilium.infrastructure.settings.get_storage",
                return_value=mock_storage,
            ),
            patch("concilium.application.runtime.Runtime"),
        ):
            with pytest.raises(RuntimeError, match="CONCILIUM__PROJECTS_ROOT"):
                criar_projeto(
                    nome="Proj",
                    contexto_id="ctx-1",
                    tipo_obra="predial",
                    localizacao="SP",
                    data_inicio="2026-01-01",
                    servicos=_mapped_servicos(),
                    projetos_root=None,
                )
