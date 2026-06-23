"""Unit tests for concilium.presentation.mcp.tools.formulario.

Covers _suggest_cpu, _build_eap_items, and the criar_projeto tool
registered via register().
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

import concilium.presentation.mcp.rate_limit as _rate_limit_mod
from concilium.presentation.mcp.tools.formulario import (
    _build_eap_items,
    _suggest_cpu,
    register,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_server() -> FastMCP:
    """Return a fresh FastMCP instance for tool registration."""
    return FastMCP("test-formulario")


def _get_tools(server: FastMCP) -> dict[str, Any]:
    """Extract {name: callable} from a server's tool manager."""
    return {name: tool.fn for name, tool in server._tool_manager._tools.items()}


@pytest.fixture(autouse=True)
def reset_rate_limit_counters():
    """Clear the in-memory rate-limit counters before every test."""
    _rate_limit_mod._counters.clear()
    yield
    _rate_limit_mod._counters.clear()


# ===========================================================================
# _suggest_cpu
# ===========================================================================


class TestSuggestCpu:
    """Tests for _suggest_cpu(descricao) -> (cpu_id | None, score)."""

    def test_score2_all_keywords_present(self):
        """Returns (cpu_id, 2) when all keywords for a rule match."""
        keywords_map = {
            "CPU-ESCAVADEIRA": ["ESCAVACAO", "HIDRAULICA"],
            "CPU-TRATOR": ["TRATOR", "ESTEIRA"],
        }
        with patch(
            "concilium.infrastructure.catalog.mapping.cpu_mapper._load_mapping_keywords",
            return_value=keywords_map,
        ):
            cpu_id, score = _suggest_cpu("Escavacao Hidraulica de solo")
            assert cpu_id == "CPU-ESCAVADEIRA"
            assert score == 2

    def test_score1_any_keyword_present(self):
        """Returns (cpu_id, 1) when only some (any) keywords match (score-1 path)."""
        keywords_map = {
            # All-keywords rule won't match (needs both ESCAVACAO and HIDRAULICA)
            "CPU-ESCAVADEIRA": ["ESCAVACAO", "HIDRAULICA"],
            # Any-keyword partial match for second rule
            "CPU-TRATOR": ["TRATOR", "ESTEIRA"],
        }
        # Description has TRATOR but not ESTEIRA → doesn't pass 'all', passes 'any'
        with patch(
            "concilium.infrastructure.catalog.mapping.cpu_mapper._load_mapping_keywords",
            return_value=keywords_map,
        ):
            cpu_id, score = _suggest_cpu("servico com trator pesado")
            assert cpu_id == "CPU-TRATOR"
            assert score == 1

    def test_keyword_rules_exception_falls_to_catalog_overlap(self, tmp_path):
        """When keyword rules raise, falls back to catalog word-overlap search."""
        # Build a minimal fake catalog JSON
        cpu_json = {
            "codigo": "CPU-ATERRO-001",
            "descricao": "Aterro compactado mecanicamente solo argiloso",
        }
        cat_dir = tmp_path / "catalogos" / "meu-catalogo" / "cpus"
        cat_dir.mkdir(parents=True)
        (cat_dir / "CPU-ATERRO-001.json").write_text(json.dumps(cpu_json), encoding="utf-8")

        # Patch _load_mapping_keywords to raise so we enter the except branch
        with (
            patch(
                "concilium.infrastructure.catalog.mapping.cpu_mapper._load_mapping_keywords",
                side_effect=RuntimeError("boom"),
            ),
            patch(
                "concilium.presentation.mcp._context._storage_live",
            ) as mock_storage,
        ):
            settings = MagicMock()
            settings.config_root = tmp_path
            mock_storage.return_value = settings

            # Description shares enough words with catalog entry (>=2 overlap)
            # "ATERRO" and "COMPACTADO" should overlap
            cpu_id, score = _suggest_cpu("Aterro compactado mecanicamente")
            # Falls into catalog fallback: best_score >= 2 → returns (cpu_id, 1)
            assert cpu_id == "CPU-ATERRO-001"
            assert score == 1

    def test_no_match_returns_none_zero(self):
        """Returns (None, 0) when no keyword rule or catalog entry matches."""
        keywords_map: dict = {}
        with (
            patch(
                "concilium.infrastructure.catalog.mapping.cpu_mapper._load_mapping_keywords",
                return_value=keywords_map,
            ),
            patch(
                "concilium.presentation.mcp._context._storage_live",
            ) as mock_storage,
        ):
            settings = MagicMock()
            # Point config_root to a place with no catalogos
            settings.config_root = Path("/nonexistent/path/xyz")
            mock_storage.return_value = settings

            cpu_id, score = _suggest_cpu("xyz999 xyzabc unknown service")
            assert cpu_id is None
            assert score == 0

    def test_catalog_overlap_below_threshold_returns_none(self, tmp_path):
        """When best word overlap < 2, returns (None, 0)."""
        # Only 1 overlapping word — below the >=2 threshold
        cpu_json = {"codigo": "CPU-XYZ", "descricao": "Aterro diferente"}
        cat_dir = tmp_path / "catalogos" / "meu-catalogo" / "cpus"
        cat_dir.mkdir(parents=True)
        (cat_dir / "CPU-XYZ.json").write_text(json.dumps(cpu_json), encoding="utf-8")

        with (
            patch(
                "concilium.infrastructure.catalog.mapping.cpu_mapper._load_mapping_keywords",
                return_value={},
            ),
            patch(
                "concilium.presentation.mcp._context._storage_live",
            ) as mock_storage,
        ):
            settings = MagicMock()
            settings.config_root = tmp_path
            mock_storage.return_value = settings

            cpu_id, score = _suggest_cpu("aterro pequeno")  # only 1 match word
            assert cpu_id is None
            assert score == 0


# ===========================================================================
# _build_eap_items
# ===========================================================================


class TestBuildEapItems:
    """Tests for _build_eap_items(servicos) -> (mapeados, nao_mapeados)."""

    def test_all_services_have_explicit_cpu_id(self):
        """All services with cpu_id set → all go to mapeados with score=2."""
        servicos = [
            {
                "descricao": "Escavacao",
                "quantidade": 100.0,
                "unidade": "m3",
                "cpu_id": "CPU-ESCAV-001",
            },
            {
                "descricao": "Aterro",
                "quantidade": 50.0,
                "unidade": "m3",
                "cpu_id": "CPU-ATERRO-001",
            },
        ]
        mapeados, nao_mapeados = _build_eap_items(servicos)

        assert len(mapeados) == 2
        assert len(nao_mapeados) == 0
        assert mapeados[0]["cpu_id"] == "CPU-ESCAV-001"
        assert mapeados[0]["_score"] == 2
        assert mapeados[1]["cpu_id"] == "CPU-ATERRO-001"
        assert mapeados[1]["_score"] == 2

    def test_services_without_cpu_id_resolved_by_suggest(self):
        """Services without cpu_id get resolved via _suggest_cpu mock."""
        servicos = [
            {
                "descricao": "Escavacao hidraulica",
                "quantidade": 100.0,
                "unidade": "m3",
            }
        ]
        with patch(
            "concilium.presentation.mcp.tools.formulario._suggest_cpu",
            return_value=("CPU-ESCAV-001", 2),
        ):
            mapeados, nao_mapeados = _build_eap_items(servicos)

        assert len(mapeados) == 1
        assert len(nao_mapeados) == 0
        assert mapeados[0]["cpu_id"] == "CPU-ESCAV-001"
        assert mapeados[0]["_score"] == 2

    def test_services_where_suggest_returns_none_go_to_nao_mapeados(self):
        """Services where _suggest_cpu returns (None, 0) go to nao_mapeados."""
        servicos = [
            {
                "descricao": "Servico desconhecido XYZ",
                "quantidade": 10.0,
                "unidade": "m",
            }
        ]
        with patch(
            "concilium.presentation.mcp.tools.formulario._suggest_cpu",
            return_value=(None, 0),
        ):
            mapeados, nao_mapeados = _build_eap_items(servicos)

        assert len(mapeados) == 0
        assert len(nao_mapeados) == 1
        assert nao_mapeados[0]["cpu_id"] is None
        assert nao_mapeados[0]["descricao"] == "Servico desconhecido XYZ"

    def test_mixed_some_mapped_some_not(self):
        """Mixed: some services with cpu_id, some resolved, some not resolved."""
        servicos = [
            {
                "descricao": "Escavacao com cpu_id explícito",
                "quantidade": 100.0,
                "unidade": "m3",
                "cpu_id": "CPU-ESCAV-001",
            },
            {
                "descricao": "Servico auto-resolvido",
                "quantidade": 20.0,
                "unidade": "m",
            },
            {
                "descricao": "Servico sem match",
                "quantidade": 5.0,
                "unidade": "un",
            },
        ]

        def _fake_suggest(descricao: str):
            if "auto-resolvido" in descricao.lower():
                return "CPU-AUTO-001", 1
            return None, 0

        with patch(
            "concilium.presentation.mcp.tools.formulario._suggest_cpu",
            side_effect=_fake_suggest,
        ):
            mapeados, nao_mapeados = _build_eap_items(servicos)

        assert len(mapeados) == 2
        assert len(nao_mapeados) == 1
        cpu_ids_mapped = [it["cpu_id"] for it in mapeados]
        assert "CPU-ESCAV-001" in cpu_ids_mapped
        assert "CPU-AUTO-001" in cpu_ids_mapped
        assert nao_mapeados[0]["cpu_id"] is None

    def test_item_id_defaults_and_ordem(self):
        """item_id defaults to 'eap-1_{i}' and ordem is set correctly."""
        servicos = [
            {"descricao": "Svc A", "quantidade": 1.0, "unidade": "un", "cpu_id": "CPU-A"},
            {"descricao": "Svc B", "quantidade": 2.0, "unidade": "m", "cpu_id": "CPU-B"},
        ]
        mapeados, _ = _build_eap_items(servicos)
        assert mapeados[0]["item_id"] == "eap-1_1"
        assert mapeados[0]["ordem"] == 1
        assert mapeados[1]["item_id"] == "eap-1_2"
        assert mapeados[1]["ordem"] == 2

    def test_explicit_item_id_preserved(self):
        """If item_id is in the service dict, it is preserved."""
        servicos = [
            {
                "descricao": "Svc A",
                "quantidade": 1.0,
                "unidade": "un",
                "cpu_id": "CPU-A",
                "item_id": "custom-001",
            }
        ]
        mapeados, _ = _build_eap_items(servicos)
        assert mapeados[0]["item_id"] == "custom-001"


# ===========================================================================
# criar_projeto (registered tool)
# ===========================================================================


@pytest.fixture()
def tool_criar(tmp_path):
    """Register formulario tools on a fresh server; return the inner callable."""
    server = _make_server()

    with patch(
        "concilium.presentation.mcp.tools.formulario._wrap_response",
        side_effect=lambda d: d,  # return input unchanged for easy assertions
    ):
        register(server)

    tools = _get_tools(server)
    return tools["criar_projeto"]


# Minimal kwargs shared across tests
_COMMON_KWARGS = dict(
    nome="Proj Teste",
    contexto_id="mendeslobo",
    tipo_obra="terraplenagem",
    localizacao="Fortaleza, CE",
    data_inicio="2026-01-01",
)


class TestCriarProjetoFormulario:
    """Tests for the criar_projeto MCP tool."""

    def test_nao_mapeados_returns_pendente_without_creating_project(self, tool_criar):
        """If any service is unmapped, return pendente_mapeamento without touching storage."""
        servicos = [{"descricao": "Servico X", "quantidade": 10.0, "unidade": "m"}]

        with (
            patch(
                "concilium.presentation.mcp.tools.formulario._build_eap_items",
                return_value=(
                    [],  # mapeados
                    [
                        {
                            "item_id": "eap-1_1",
                            "ordem": 1,
                            "descricao": "Servico X",
                            "unidade": "m",
                            "quantitativo": 10.0,
                            "predecessores": [],
                            "cpu_id": None,
                            "_score": 0,
                        }
                    ],
                ),
            ),
            patch("concilium.presentation.mcp.tools.formulario._runtime") as mock_rt,
            patch("concilium.presentation.mcp.tools.formulario._projetos_root") as mock_pr,
            patch(
                "concilium.presentation.mcp.tools.formulario._wrap_response",
                side_effect=lambda d: d,
            ),
        ):
            result = tool_criar(servicos=servicos, **_COMMON_KWARGS)

        assert result["status"] == "pendente_mapeamento"
        assert result["total_servicos"] == 1
        assert len(result["nao_mapeados"]) == 1
        # _runtime and _projetos_root must NOT have been called
        mock_rt.assert_not_called()
        mock_pr.assert_not_called()

    def test_all_mapped_success_returns_criado(self, tmp_path):
        """When all mapped and coordinator succeeds, returns status=criado."""
        server = _make_server()
        register(server)
        tool = _get_tools(server)["criar_projeto"]

        servicos = [
            {
                "descricao": "Escavacao",
                "quantidade": 100.0,
                "unidade": "m3",
                "cpu_id": "CPU-ESCAV-001",
            }
        ]

        # Build mock store + escopo + plan
        mock_ps = MagicMock()
        mock_ps.plano_id = "plan-001"

        mock_es = MagicMock()
        mock_es.create_plan.return_value = mock_ps

        mock_root = MagicMock()
        mock_root.name = "proj-001"

        mock_store = MagicMock()
        mock_store.root = mock_root
        mock_store.create_escopo.return_value = mock_es

        # Coordinator result: no errors
        mock_r = MagicMock()
        mock_r.has_errors = False

        mock_coord = MagicMock()
        mock_coord.avancar_plano.return_value = mock_r

        mock_contexto = MagicMock()
        mock_contexto.referencia_id = "ref-123"

        mock_rt = MagicMock()
        mock_rt.load_contexto.return_value = mock_contexto

        with (
            patch(
                "concilium.presentation.mcp.tools.formulario._wrap_response",
                side_effect=lambda d: d,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._runtime",
                return_value=mock_rt,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._projetos_root",
                return_value=tmp_path,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._lifecycle_coordinator",
                return_value=mock_coord,
            ),
            patch(
                "concilium.infrastructure.storage.project.ProjectStore.init",
                return_value=mock_store,
            ),
        ):
            result = tool(servicos=servicos, **_COMMON_KWARGS)

        assert result["status"] == "criado"
        assert "eap_preview" in result
        assert result["total_itens"] == 1
        assert "proxima_skill_sugerida" in result

    def test_coordinator_raises_exception_returns_erro_key(self, tmp_path):
        """When coord.avancar_plano raises, returns dict with 'erro' key."""
        server = _make_server()
        register(server)
        tool = _get_tools(server)["criar_projeto"]

        servicos = [
            {
                "descricao": "Escavacao",
                "quantidade": 100.0,
                "unidade": "m3",
                "cpu_id": "CPU-ESCAV-001",
            }
        ]

        mock_ps = MagicMock()
        mock_ps.plano_id = "plan-001"

        mock_es = MagicMock()
        mock_es.create_plan.return_value = mock_ps

        mock_root = MagicMock()
        mock_root.name = "proj-err"

        mock_store = MagicMock()
        mock_store.root = mock_root
        mock_store.create_escopo.return_value = mock_es

        mock_coord = MagicMock()
        mock_coord.avancar_plano.side_effect = ValueError("pipeline error!")

        mock_contexto = MagicMock()
        mock_contexto.referencia_id = "ref-123"

        mock_rt = MagicMock()
        mock_rt.load_contexto.return_value = mock_contexto

        with (
            patch(
                "concilium.presentation.mcp.tools.formulario._wrap_response",
                side_effect=lambda d: d,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._runtime",
                return_value=mock_rt,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._projetos_root",
                return_value=tmp_path,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._lifecycle_coordinator",
                return_value=mock_coord,
            ),
            patch(
                "concilium.infrastructure.storage.project.ProjectStore.init",
                return_value=mock_store,
            ),
        ):
            result = tool(servicos=servicos, **_COMMON_KWARGS)

        assert "erro" in result
        assert "pipeline error!" in result["erro"]

    def test_has_errors_true_returns_erro_escopo(self, tmp_path):
        """When r.has_errors is True, returns status=erro_escopo with erros list."""
        server = _make_server()
        register(server)
        tool = _get_tools(server)["criar_projeto"]

        servicos = [
            {
                "descricao": "Escavacao",
                "quantidade": 100.0,
                "unidade": "m3",
                "cpu_id": "CPU-ESCAV-001",
            }
        ]

        mock_ps = MagicMock()
        mock_ps.plano_id = "plan-001"

        mock_es = MagicMock()
        mock_es.create_plan.return_value = mock_ps

        mock_root = MagicMock()
        mock_root.name = "proj-escopo-err"

        mock_store = MagicMock()
        mock_store.root = mock_root
        mock_store.create_escopo.return_value = mock_es

        # Create validation errors
        val1 = MagicMock()
        val1.mensagem = "cpu_id invalido"
        val1.status = "ERRO"

        val2 = MagicMock()
        val2.mensagem = "quantidade negativa"
        val2.status = "ERRO"

        mock_r = MagicMock()
        mock_r.has_errors = True
        mock_r.validacoes = [val1, val2]

        mock_coord = MagicMock()
        mock_coord.avancar_plano.return_value = mock_r

        mock_contexto = MagicMock()
        mock_contexto.referencia_id = "ref-123"

        mock_rt = MagicMock()
        mock_rt.load_contexto.return_value = mock_contexto

        with (
            patch(
                "concilium.presentation.mcp.tools.formulario._wrap_response",
                side_effect=lambda d: d,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._runtime",
                return_value=mock_rt,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._projetos_root",
                return_value=tmp_path,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._lifecycle_coordinator",
                return_value=mock_coord,
            ),
            patch(
                "concilium.infrastructure.storage.project.ProjectStore.init",
                return_value=mock_store,
            ),
        ):
            result = tool(servicos=servicos, **_COMMON_KWARGS)

        assert result["status"] == "erro_escopo"
        assert "erros" in result
        assert "cpu_id invalido" in result["erros"]
        assert "quantidade negativa" in result["erros"]

    def test_pendente_mapeamento_instrucoes_included(self):
        """pendente_mapeamento response includes 'instrucoes' field."""
        server = _make_server()
        register(server)
        tool = _get_tools(server)["criar_projeto"]

        servicos = [{"descricao": "Unknown", "quantidade": 1.0, "unidade": "un"}]

        with (
            patch(
                "concilium.presentation.mcp.tools.formulario._build_eap_items",
                return_value=(
                    [],
                    [
                        {
                            "item_id": "eap-1_1",
                            "ordem": 1,
                            "descricao": "Unknown",
                            "unidade": "un",
                            "quantitativo": 1.0,
                            "predecessores": [],
                            "cpu_id": None,
                            "_score": 0,
                        }
                    ],
                ),
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._wrap_response",
                side_effect=lambda d: d,
            ),
        ):
            result = tool(servicos=servicos, **_COMMON_KWARGS)

        assert "instrucoes" in result
        assert "buscar_cpu" in result["instrucoes"]

    def test_mapeados_preview_confidence_alta_vs_media(self, tmp_path):
        """mapeados_preview sets confianca='alta' for score=2, 'media' for score=1."""
        server = _make_server()
        register(server)
        tool = _get_tools(server)["criar_projeto"]

        # Two services: one with explicit cpu_id (score=2), one resolved auto (score=1)
        servicos = [
            {
                "descricao": "Escav explícita",
                "quantidade": 10.0,
                "unidade": "m3",
                "cpu_id": "CPU-A",  # score=2
            },
            {
                "descricao": "Escav auto",
                "quantidade": 5.0,
                "unidade": "m3",
                # no cpu_id → _suggest_cpu returns score=1
            },
        ]

        mock_ps = MagicMock()
        mock_ps.plano_id = "plan-001"
        mock_es = MagicMock()
        mock_es.create_plan.return_value = mock_ps
        mock_root = MagicMock()
        mock_root.name = "proj-conf"
        mock_store = MagicMock()
        mock_store.root = mock_root
        mock_store.create_escopo.return_value = mock_es

        mock_r = MagicMock()
        mock_r.has_errors = False
        mock_coord = MagicMock()
        mock_coord.avancar_plano.return_value = mock_r
        mock_contexto = MagicMock()
        mock_contexto.referencia_id = "ref-x"
        mock_rt = MagicMock()
        mock_rt.load_contexto.return_value = mock_contexto

        with (
            patch(
                "concilium.presentation.mcp.tools.formulario._suggest_cpu",
                return_value=("CPU-B", 1),
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._wrap_response",
                side_effect=lambda d: d,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._runtime",
                return_value=mock_rt,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._projetos_root",
                return_value=tmp_path,
            ),
            patch(
                "concilium.presentation.mcp.tools.formulario._lifecycle_coordinator",
                return_value=mock_coord,
            ),
            patch(
                "concilium.infrastructure.storage.project.ProjectStore.init",
                return_value=mock_store,
            ),
        ):
            result = tool(servicos=servicos, **_COMMON_KWARGS)

        assert result["status"] == "criado"
        preview = result["eap_preview"]
        # First item: explicit cpu_id → score=2 → confianca='alta'
        alta_items = [it for it in preview if it["confianca"] == "alta"]
        media_items = [it for it in preview if it["confianca"] == "media"]
        assert len(alta_items) == 1
        assert len(media_items) == 1
