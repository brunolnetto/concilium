"""Tests for _catalogo_tools_helpers_a — covers the missing lines listed in the task."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import concilium.presentation.mcp.tools._catalogo_tools_helpers_a as mod
from concilium.presentation.mcp.tools._catalogo_tools_helpers_a import (
    _catalog_root,
    _impl_adicionar_variante_producao,
    _impl_atualizar_composicao_item_cpu,
    _impl_atualizar_preco_insumo,
    _impl_consultar_preco_insumo_temporal,
    _impl_consultar_saude_catalogo,
    _impl_criar_insumo,
    _impl_descontinuar_insumo,
    _impl_listar_contextos,
    _impl_listar_insumos,
    _impl_pesquisar_catalogo,
)

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


def _make_rt(contexto_id: str = "ctx1", catalogo_id: str = "cat1") -> MagicMock:
    """Build a minimal Runtime mock."""
    rt = MagicMock()
    ctx = MagicMock()
    ctx.id = contexto_id
    ctx.catalogo_id = catalogo_id
    rt.load_contexto.return_value = ctx
    rt.load_catalogo.return_value = {"cpus": [], "templates": [], "insumos": []}
    return rt


def _passthrough(d: dict) -> dict:
    return d


def _make_rascunho(config_dir: Path, contexto_id: str, rascunho_id: str, data: dict | None = None) -> Path:
    """Cria o arquivo de versão de um rascunho (ADR-120) para os testes de delta (ADR-145)."""
    versions_dir = config_dir / "contextos" / contexto_id / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    rascunho_file = versions_dir / f"{rascunho_id}.json"
    rascunho_file.write_text(json.dumps(data or {"version": rascunho_id}), encoding="utf-8")
    return rascunho_file


# ---------------------------------------------------------------------------
# _catalog_root
# ---------------------------------------------------------------------------


class TestCatalogRoot:
    def test_returns_correct_path(self, tmp_path: Path) -> None:
        # line 20
        result = _catalog_root(tmp_path, "mendeslobo")
        assert result == tmp_path / "catalogos" / "mendeslobo"


# ---------------------------------------------------------------------------
# _impl_listar_contextos
# ---------------------------------------------------------------------------


class TestImplListarContextos:
    def test_contextos_dir_does_not_exist(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # line 31 — directory absent → returns {"contextos": []}
        missing_dir = tmp_path / "non_existent"
        monkeypatch.setattr(mod, "_runtime", lambda: _make_rt())
        monkeypatch.setattr(mod, "_config_root", lambda: missing_dir)
        monkeypatch.setattr(mod, "_wrap_response", _passthrough)

        result = _impl_listar_contextos()
        assert result == {"contextos": []}

    def test_contextos_dir_with_json_files(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 34-44 — iterates json files, calls rt.load_contexto, reads raw JSON
        ctx_dir = tmp_path / "contextos"
        ctx_dir.mkdir(parents=True)
        raw_data = {"nome": "Mendes Lobo", "descricao": "Contexto teste"}
        (ctx_dir / "ctx1.json").write_text(json.dumps(raw_data), encoding="utf-8")

        rt = _make_rt("ctx1", "cat1")
        rt.load_contexto.return_value.id = "ctx1"
        monkeypatch.setattr(mod, "_runtime", lambda: rt)
        monkeypatch.setattr(mod, "_config_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "_wrap_response", _passthrough)

        result = _impl_listar_contextos()
        assert len(result["contextos"]) == 1
        entry = result["contextos"][0]
        assert entry["id"] == "ctx1"
        assert entry["nome"] == "Mendes Lobo"
        assert entry["descricao"] == "Contexto teste"

    def test_contextos_uses_comment_as_fallback_descricao(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # lines 41 — raw.get("$comment") fallback
        ctx_dir = tmp_path / "contextos"
        ctx_dir.mkdir(parents=True)
        raw_data = {"nome": "X", "$comment": "comment text"}
        (ctx_dir / "ctx2.json").write_text(json.dumps(raw_data), encoding="utf-8")

        rt = _make_rt("ctx2", "cat1")
        rt.load_contexto.return_value.id = "ctx2"
        monkeypatch.setattr(mod, "_runtime", lambda: rt)
        monkeypatch.setattr(mod, "_config_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "_wrap_response", _passthrough)

        result = _impl_listar_contextos()
        entry = result["contextos"][0]
        assert entry["descricao"] == "comment text"


# ---------------------------------------------------------------------------
# _impl_pesquisar_catalogo
# ---------------------------------------------------------------------------


class TestImplPesquisarCatalogo:
    def _setup(self, monkeypatch: pytest.MonkeyPatch, rt: MagicMock, tmp_path: Path) -> None:
        monkeypatch.setattr(mod, "_runtime", lambda: rt)
        monkeypatch.setattr(mod, "_config_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "_projetos_root", lambda: tmp_path / "projetos")
        monkeypatch.setattr(mod, "_wrap_response", _passthrough)

    def test_load_contexto_raises_returns_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 62-67 — exception → {"erro": ...}
        rt = _make_rt()
        rt.load_contexto.side_effect = RuntimeError("not found")
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_pesquisar_catalogo("ctx1")
        assert "erro" in result
        assert "not found" in result["erro"]

    def test_neither_query_nor_tipo_obra(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 69-70 — result has only contexto_id and catalogo_id
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_pesquisar_catalogo("ctx1")
        assert result["contexto_id"] == "ctx1"
        assert result["catalogo_id"] == "cat1"
        assert "eap_sugerida" not in result
        assert "busca_resultados" not in result

    def test_tipo_obra_matches_template(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 73-90 — eap_sugerida populated
        rt = _make_rt("ctx1", "cat1")
        rt.load_catalogo.return_value = {
            "cpus": [{"codigo": "CPU-001", "descricao": "Aterro compactado", "unidade": "m3"}],
            "templates": [
                {
                    "tipo_obra": "TERRAPLENAGEM",
                    "servicos_sugeridos": [{"cpu_id": "CPU-001", "obrigatoriedade": "obrigatorio"}],
                }
            ],
        }
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_pesquisar_catalogo("ctx1", tipo_obra="terraplenagem")
        assert "eap_sugerida" in result
        assert result["eap_sugerida"][0]["cpu_id"] == "CPU-001"
        assert result["eap_sugerida"][0]["descricao"] == "Aterro compactado"
        assert result["eap_sugerida"][0]["obrigatoriedade"] == "obrigatorio"

    def test_tipo_obra_no_template_match(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 73-90 — tipo_obra provided but no match → eap_sugerida absent
        rt = _make_rt("ctx1", "cat1")
        rt.load_catalogo.return_value = {
            "cpus": [],
            "templates": [{"tipo_obra": "PAVIMENTACAO", "servicos_sugeridos": []}],
        }
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_pesquisar_catalogo("ctx1", tipo_obra="saneamento")
        assert "eap_sugerida" not in result

    def test_query_matches_by_descricao(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 93-110 — busca textual
        rt = _make_rt("ctx1", "cat1")
        rt.load_catalogo.return_value = {
            "cpus": [
                {"codigo": "CPU-001", "descricao": "Aterro Compactado", "unidade": "m3", "categoria": "TERRA"},
                {"codigo": "CPU-002", "descricao": "Escavacao", "unidade": "m3", "categoria": "TERRA"},
            ],
            "templates": [],
        }
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_pesquisar_catalogo("ctx1", query="aterro")
        assert "busca_resultados" in result
        assert len(result["busca_resultados"]) == 1
        assert result["busca_resultados"][0]["cpu_id"] == "CPU-001"

    def test_query_matches_by_codigo(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        rt.load_catalogo.return_value = {
            "cpus": [{"codigo": "CPU-999", "descricao": "Descricao X", "unidade": "m", "categoria": "A"}],
            "templates": [],
        }
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_pesquisar_catalogo("ctx1", query="cpu-999")
        assert len(result["busca_resultados"]) == 1

    def test_query_respects_limite(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # line 108-109 — limite enforced
        rt = _make_rt("ctx1", "cat1")
        rt.load_catalogo.return_value = {
            "cpus": [
                {"codigo": f"CPU-{i:03d}", "descricao": "aterro xpto", "unidade": "m3", "categoria": "A"}
                for i in range(10)
            ],
            "templates": [],
        }
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_pesquisar_catalogo("ctx1", query="aterro", limite=3)
        assert len(result["busca_resultados"]) == 3

    def test_both_tipo_obra_and_query(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 73+93 — both keys present
        rt = _make_rt("ctx1", "cat1")
        rt.load_catalogo.return_value = {
            "cpus": [{"codigo": "CPU-001", "descricao": "escavação", "unidade": "m3", "categoria": "T"}],
            "templates": [{"tipo_obra": "TERRAPLENAGEM", "servicos_sugeridos": [{"cpu_id": "CPU-001"}]}],
        }
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_pesquisar_catalogo("ctx1", query="escav", tipo_obra="terraplenagem")
        assert "eap_sugerida" in result
        assert "busca_resultados" in result


# ---------------------------------------------------------------------------
# _impl_listar_insumos (ADR-163 D1)
# ---------------------------------------------------------------------------


class TestImplListarInsumos:
    def _setup(self, monkeypatch: pytest.MonkeyPatch, rt: MagicMock, tmp_path: Path) -> None:
        monkeypatch.setattr(mod, "_runtime", lambda: rt)
        monkeypatch.setattr(mod, "_config_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "_wrap_response", _passthrough)

    def _catalogo_insumos(self) -> dict:
        return {
            "cpus": [],
            "insumos": [
                {
                    "codigo": "EQ-001",
                    "tipo": "EQUIPAMENTO",
                    "descricao": "Caminhão Basculante 12m³",
                    "unidade": "h",
                    "preco_unitario": 112.0,
                    "categoria": "DIVERSOS",
                    "atributos_especificos": {"valor_locacao_mensal": 22400.0},
                },
                {
                    "codigo": "MO-001",
                    "tipo": "MAO_OBRA",
                    "descricao": "Gerente de Contrato",
                    "unidade": "h",
                    "preco_unitario": 80.0,
                    "categoria": "GESTAO",
                },
                {
                    "codigo": "MAT-001",
                    "tipo": "MATERIAL",
                    "descricao": "Brita 1",
                    "unidade": "m3",
                    "preco_unitario": 55.0,
                    "categoria": "AGREGADO",
                },
            ],
        }

    def test_load_contexto_raises_returns_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt()
        rt.load_contexto.side_effect = RuntimeError("not found")
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_listar_insumos("ctx1")
        assert "erro" in result
        assert "not found" in result["erro"]

    def test_sem_filtro_retorna_todos(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        rt.load_catalogo.return_value = self._catalogo_insumos()
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_listar_insumos("ctx1")
        assert result["contexto_id"] == "ctx1"
        assert result["catalogo_id"] == "cat1"
        assert result["total"] == 3
        assert len(result["insumos"]) == 3

    def test_campos_retornados_para_equipamento(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        rt.load_catalogo.return_value = self._catalogo_insumos()
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_listar_insumos("ctx1", tipo="EQUIPAMENTO")
        assert len(result["insumos"]) == 1
        item = result["insumos"][0]
        assert item["insumo_id"] == "EQ-001"
        assert item["descricao"] == "Caminhão Basculante 12m³"
        assert item["tipo"] == "EQUIPAMENTO"
        assert item["categoria"] == "DIVERSOS"
        assert item["unidade"] == "h"
        assert item["preco_unitario"] == 112.0
        assert item["valor_locacao_mensal"] == 22400.0

    def test_nao_equipamento_sem_valor_locacao_mensal(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        rt.load_catalogo.return_value = self._catalogo_insumos()
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_listar_insumos("ctx1", tipo="MAO_OBRA")
        assert len(result["insumos"]) == 1
        assert "valor_locacao_mensal" not in result["insumos"][0]

    def test_filtro_por_tipo(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        rt.load_catalogo.return_value = self._catalogo_insumos()
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_listar_insumos("ctx1", tipo="MATERIAL")
        assert len(result["insumos"]) == 1
        assert result["insumos"][0]["insumo_id"] == "MAT-001"

    def test_busca_por_descricao_parcial_case_insensitive(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        rt = _make_rt("ctx1", "cat1")
        rt.load_catalogo.return_value = self._catalogo_insumos()
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_listar_insumos("ctx1", query="gerente de contrato")
        assert len(result["insumos"]) == 1
        assert result["insumos"][0]["insumo_id"] == "MO-001"

    def test_busca_por_codigo(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        rt.load_catalogo.return_value = self._catalogo_insumos()
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_listar_insumos("ctx1", query="eq-001")
        assert len(result["insumos"]) == 1
        assert result["insumos"][0]["insumo_id"] == "EQ-001"

    def test_paginacao_limite_offset(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        catalogo = {
            "insumos": [
                {"codigo": f"MAT-{i:03d}", "tipo": "MATERIAL", "descricao": "x", "unidade": "m3", "preco_unitario": 1.0}
                for i in range(10)
            ]
        }
        rt.load_catalogo.return_value = catalogo
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_listar_insumos("ctx1", limite=3, offset=2)
        assert result["total"] == 10
        assert len(result["insumos"]) == 3
        assert result["insumos"][0]["insumo_id"] == "MAT-002"

    def test_query_sem_match_retorna_vazio(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        rt.load_catalogo.return_value = self._catalogo_insumos()
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_listar_insumos("ctx1", query="inexistente-xyz")
        assert result["insumos"] == []
        assert result["total"] == 0

    def test_descontinuado_excluido_por_padrao(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """ADR-163 D6: soft delete não deve aparecer em listagens por padrão."""
        rt = _make_rt("ctx1", "cat1")
        catalogo = self._catalogo_insumos()
        catalogo["insumos"][0]["status"] = "descontinuado"
        rt.load_catalogo.return_value = catalogo
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_listar_insumos("ctx1")
        assert result["total"] == 2
        assert all(i["insumo_id"] != "EQ-001" for i in result["insumos"])

    def test_incluir_descontinuados_true_mostra_todos(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        catalogo = self._catalogo_insumos()
        catalogo["insumos"][0]["status"] = "descontinuado"
        rt.load_catalogo.return_value = catalogo
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_listar_insumos("ctx1", incluir_descontinuados=True)
        assert result["total"] == 3
        assert any(i["insumo_id"] == "EQ-001" for i in result["insumos"])


# ---------------------------------------------------------------------------
# _impl_consultar_saude_catalogo
# ---------------------------------------------------------------------------


class TestImplConsultarSaudeCatalogo:
    def _setup(self, monkeypatch: pytest.MonkeyPatch, rt: MagicMock, tmp_path: Path) -> None:
        monkeypatch.setattr(mod, "_runtime", lambda: rt)
        monkeypatch.setattr(mod, "_config_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "_projetos_root", lambda: tmp_path / "projetos")
        monkeypatch.setattr(mod, "_wrap_response", _passthrough)

    def test_load_contexto_raises_returns_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 120-125
        rt = _make_rt()
        rt.load_contexto.side_effect = ValueError("ctx missing")
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_consultar_saude_catalogo("ctx1")
        assert "erro" in result
        assert "ctx missing" in result["erro"]

    def test_no_critical_errors_status_saudavel(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 127-137 — SAUDAVEL
        rt = _make_rt("ctx1", "cat1")
        rt.load_catalogo.return_value = {"cpus": [{"codigo": "A"}, {"codigo": "B"}]}
        monkeypatch.setattr(mod, "collect_catalog_critical_errors", lambda _cat: [])
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_consultar_saude_catalogo("ctx1")
        assert result["status"] == "SAUDAVEL"
        assert result["erros_criticos"] == []
        assert result["total_cpus"] == 2

    def test_with_errors_status_degradado(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 127-137 — DEGRADADO
        rt = _make_rt("ctx1", "cat1")
        rt.load_catalogo.return_value = {"cpus": []}
        monkeypatch.setattr(mod, "collect_catalog_critical_errors", lambda _cat: ["Erro 1", "Erro 2"])
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_consultar_saude_catalogo("ctx1")
        assert result["status"] == "DEGRADADO"
        assert len(result["erros_criticos"]) == 2

    def test_total_cpus_reflects_list_length(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        rt.load_catalogo.return_value = {"cpus": [{"codigo": "X"} for _ in range(5)]}
        monkeypatch.setattr(mod, "collect_catalog_critical_errors", lambda _cat: [])
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_consultar_saude_catalogo("ctx1")
        assert result["total_cpus"] == 5


# ---------------------------------------------------------------------------
# _impl_atualizar_preco_insumo
# ---------------------------------------------------------------------------


class TestImplAtualizarPrecoInsumo:
    def _setup(
        self,
        monkeypatch: pytest.MonkeyPatch,
        rt: MagicMock,
        config_dir: Path,
        projects_dir: Path,
        insumo_file: Path | None = None,
    ) -> None:
        monkeypatch.setattr(mod, "_runtime", lambda: rt)
        monkeypatch.setattr(mod, "_config_root", lambda: config_dir)
        monkeypatch.setattr(mod, "_projetos_root", lambda: projects_dir)
        monkeypatch.setattr(mod, "_wrap_response", _passthrough)
        if insumo_file is not None:
            monkeypatch.setattr(mod, "validate_and_resolve_insumo_file", lambda _cr, _iid, _np: insumo_file)
        else:
            monkeypatch.setattr(mod, "validate_and_resolve_insumo_file", lambda _cr, _iid, _np: MagicMock())

    def test_governance_error_returns_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 161-173 — CatalogGovernanceError → {"erro": ...}
        from concilium.application.orchestrators.catalog_governance import CatalogGovernanceError

        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)

        monkeypatch.setattr(mod, "_runtime", lambda: rt)
        monkeypatch.setattr(mod, "_config_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "_projetos_root", lambda: projects_dir)
        monkeypatch.setattr(mod, "_wrap_response", _passthrough)
        monkeypatch.setattr(
            mod,
            "validate_and_resolve_insumo_file",
            lambda _cr, _iid, _np: (_ for _ in ()).throw(CatalogGovernanceError("bad insumo")),
        )

        result = _impl_atualizar_preco_insumo("ctx1", "INS-001", 100.0, rascunho_id="v1")
        assert "erro" in result
        assert "bad insumo" in result["erro"]

    def test_no_rascunho_id_returns_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # ADR-145 D1 — sem rascunho_id (e sem projeto_id) não pode editar o master
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        self._setup(monkeypatch, rt, tmp_path, projects_dir)

        result = _impl_atualizar_preco_insumo("ctx1", "INS-001", 100.0)
        assert "erro" in result
        assert "rascunho_id" in result["erro"]

    def test_projeto_path_not_found(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 175-179 — proj_path does not exist
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        # project dir NOT created
        self._setup(monkeypatch, rt, tmp_path, projects_dir)

        result = _impl_atualizar_preco_insumo("ctx1", "INS-001", 100.0, projeto_id="PROJ-XYZ")
        assert "erro" in result
        assert "PROJ-XYZ" in result["erro"]

    def test_projeto_happy_path_creates_new_overrides(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 181-199 — creates new overrides_file
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        proj_dir = projects_dir / "PROJ-001"
        proj_dir.mkdir(parents=True)
        self._setup(monkeypatch, rt, tmp_path, projects_dir)

        result = _impl_atualizar_preco_insumo("ctx1", "INS-001", 55.0, projeto_id="PROJ-001")
        assert result["status"] == "SUCESSO"
        assert result["layer"] == "PROJETO"
        # ADR-150: grava em insumos_override.json — o mesmo arquivo lido pelo
        # pipeline real (lifecycle_coordinator._inject_project_catalog_layers)
        # e por catalog_promote/promover_override_projeto. Antes desta ADR,
        # gravava em catalog_prices.json, que nada mais no sistema lia.
        overrides_file = proj_dir / "overrides" / "insumos_override.json"
        assert overrides_file.exists()
        saved = json.loads(overrides_file.read_text(encoding="utf-8"))
        assert "INS-001::BASE" in saved
        assert saved["INS-001::BASE"]["preco"] == 55.0

    def test_projeto_happy_path_merges_existing_overrides(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # lines 184-199 — merges with existing overrides
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        proj_dir = projects_dir / "PROJ-001"
        overrides_dir = proj_dir / "overrides"
        overrides_dir.mkdir(parents=True)
        existing = {"OTHER-INS::BASE": {"preco": 10.0, "nota": "old", "jurisdicao": None}}
        (overrides_dir / "insumos_override.json").write_text(json.dumps(existing), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir)

        result = _impl_atualizar_preco_insumo("ctx1", "INS-002", 99.0, projeto_id="PROJ-001")
        assert result["status"] == "SUCESSO"
        saved = json.loads((overrides_dir / "insumos_override.json").read_text(encoding="utf-8"))
        assert "OTHER-INS::BASE" in saved
        assert "INS-002::BASE" in saved

    def test_projeto_jurisdicao_key_uses_jurisdicao(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # line 189 — key suffix with jurisdicao_id
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        proj_dir = projects_dir / "PROJ-001"
        proj_dir.mkdir(parents=True)
        self._setup(monkeypatch, rt, tmp_path, projects_dir)

        _impl_atualizar_preco_insumo("ctx1", "INS-001", 10.0, projeto_id="PROJ-001", jurisdicao_id="CE")
        saved = json.loads((proj_dir / "overrides" / "insumos_override.json").read_text(encoding="utf-8"))
        assert "INS-001::CE" in saved

    def test_projeto_override_reaches_real_pipeline_read_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Regressão (ADR-150): o override gravado via atualizar_preco_insumo(projeto_id=...)
        precisa ser lido de volta por `RepositorioInsumo.resolver_preco()` — o mesmo
        arquivo consumido pelo pipeline real (`lifecycle_coordinator._inject_project_catalog_layers`).
        Antes da correção, o override era gravado em `catalog_prices.json`, um arquivo
        morto que nada lia — o preço calibrado nunca chegava ao pipeline.
        """
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        proj_dir = projects_dir / "PROJ-001"
        proj_dir.mkdir(parents=True)
        self._setup(monkeypatch, rt, tmp_path, projects_dir)

        _impl_atualizar_preco_insumo("ctx1", "INS-001", 42.5, projeto_id="PROJ-001")

        overrides_file = proj_dir / "overrides" / "insumos_override.json"
        overrides = json.loads(overrides_file.read_text(encoding="utf-8"))
        repo = RepositorioInsumo({"insumos": [{"codigo": "INS-001", "preco_unitario": 1.0}]})
        preco, fonte = repo.resolver_preco("INS-001", overrides=overrides)
        assert preco == 42.5
        assert fonte == "PROJECT_OVERRIDE"

    def test_projeto_edicao_abre_rascunho_de_projeto_implicito(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """ADR-150 D1: a primeira edição de override do projeto abre (lazy) o
        estado de rascunho de projeto, com created_by = quem editou."""
        from concilium.application.orchestrators.catalog_draft_lifecycle import (
            ESTADO_RASCUNHO,
            estado_rascunho,
            rascunho_projeto_file_path,
        )

        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        proj_dir = projects_dir / "PROJ-001"
        proj_dir.mkdir(parents=True)
        self._setup(monkeypatch, rt, tmp_path, projects_dir)
        monkeypatch.setattr("concilium.infrastructure.auth.permission_guard.get_current_user_id", lambda: "engineer1")

        _impl_atualizar_preco_insumo("ctx1", "INS-001", 10.0, projeto_id="PROJ-001")

        estado_file = rascunho_projeto_file_path(projects_dir, "PROJ-001")
        assert estado_file.exists()
        data = json.loads(estado_file.read_text(encoding="utf-8"))
        assert data["created_by"] == "engineer1"
        assert data["projeto_id"] == "PROJ-001"
        assert estado_rascunho(data) == ESTADO_RASCUNHO

    def test_projeto_write_exception_returns_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 200-201 — write fails → {"erro": "Erro ao salvar override de projeto: ..."}
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        proj_dir = projects_dir / "PROJ-001"
        proj_dir.mkdir(parents=True)
        self._setup(monkeypatch, rt, tmp_path, projects_dir)

        # patch write_text to raise
        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            result = _impl_atualizar_preco_insumo("ctx1", "INS-001", 5.0, projeto_id="PROJ-001")
        assert "erro" in result
        assert "Erro ao salvar override de projeto" in result["erro"]

    def test_master_no_jurisdicao_records_delta_in_rascunho(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # ADR-145 D1 — master layer, no jurisdicao_id: grava delta, não escreve no insumo
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        insumo_file = tmp_path / "ins.json"
        insumo_file.write_text(json.dumps({"preco_unitario": 5.0}), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir, insumo_file=insumo_file)
        _make_rascunho(tmp_path, "ctx1", "v1")

        result = _impl_atualizar_preco_insumo("ctx1", "INS-001", 42.0, rascunho_id="v1")
        assert result["status"] == "RASCUNHO"
        assert result["layer"] == "MASTER"

        # o insumo do catálogo mestre permanece intocado até o merge
        data = json.loads(insumo_file.read_text(encoding="utf-8"))
        assert data["preco_unitario"] == 5.0

        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        assert len(rascunho_data["_deltas"]) == 1
        delta = rascunho_data["_deltas"][0]
        assert delta == {
            "tipo": "preco_insumo",
            "insumo_id": "INS-001",
            "novo_preco": 42.0,
            "jurisdicao_id": None,
            "nota": None,
            "autor": "system",
            "timestamp": delta["timestamp"],
        }

    def test_master_with_jurisdicao_records_delta_with_jurisdicao(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # ADR-145 D1 — master layer with jurisdicao_id também vira delta
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        insumo_file = tmp_path / "ins.json"
        insumo_file.write_text(json.dumps({"preco_unitario": 5.0}), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir, insumo_file=insumo_file)
        _make_rascunho(tmp_path, "ctx1", "v1")

        result = _impl_atualizar_preco_insumo("ctx1", "INS-001", 77.0, rascunho_id="v1", jurisdicao_id="SP")
        assert result["status"] == "RASCUNHO"

        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        delta = rascunho_data["_deltas"][0]
        assert delta["jurisdicao_id"] == "SP"
        assert delta["novo_preco"] == 77.0

    def test_master_with_nota_records_nota_in_delta(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # ADR-145 D1/D4 — nota vai para o delta, não sobrescreve um campo único no insumo
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        insumo_file = tmp_path / "ins.json"
        insumo_file.write_text(json.dumps({"preco_unitario": 1.0}), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir, insumo_file=insumo_file)
        _make_rascunho(tmp_path, "ctx1", "v1")

        _impl_atualizar_preco_insumo("ctx1", "INS-001", 99.0, rascunho_id="v1", nota="revisao 2025")
        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        assert rascunho_data["_deltas"][0]["nota"] == "revisao 2025"
        # insumo mestre não deve ganhar nenhum campo "nota_calibracao" legado
        data = json.loads(insumo_file.read_text(encoding="utf-8"))
        assert "nota_calibracao" not in data

    def test_rascunho_inexistente_returns_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # ADR-145 D1 — rascunho_id que não existe em disco
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        insumo_file = tmp_path / "ins.json"
        insumo_file.write_text(json.dumps({"preco_unitario": 5.0}), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir, insumo_file=insumo_file)

        result = _impl_atualizar_preco_insumo("ctx1", "INS-001", 10.0, rascunho_id="v-nao-existe")
        assert "erro" in result
        assert "não encontrado" in result["erro"]

    def test_rascunho_em_estado_terminal_returns_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # ADR-145 D1 — rascunho já aprovado/rejeitado não aceita novos deltas
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        insumo_file = tmp_path / "ins.json"
        insumo_file.write_text(json.dumps({"preco_unitario": 5.0}), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir, insumo_file=insumo_file)
        _make_rascunho(tmp_path, "ctx1", "v1", {"version": "v1", "_aprovado": True})

        result = _impl_atualizar_preco_insumo("ctx1", "INS-001", 10.0, rascunho_id="v1")
        assert "erro" in result
        assert "terminal" in result["erro"]

    # ── ADR-163 D4: novo_valor_locacao_mensal opcional, mesmo caminho gated por rascunho ──

    def test_sem_preco_e_sem_locacao_retorna_erro_validacao(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        self._setup(monkeypatch, rt, tmp_path, projects_dir)
        _make_rascunho(tmp_path, "ctx1", "v1")

        result = _impl_atualizar_preco_insumo("ctx1", "INS-001", None, rascunho_id="v1")
        assert "erro" in result
        assert "novo_preco" in result["erro"] or "novo_valor_locacao_mensal" in result["erro"]

    def test_so_locacao_mensal_grava_delta_com_preco_none(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Cotação de mercado pode trazer só o custo de manutenção mensal (sem
        alterar o preço/hora) — o delta deve refletir isso sem exigir novo_preco."""
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        insumo_file = tmp_path / "ins.json"
        insumo_file.write_text(json.dumps({"preco_unitario": 100.0}), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir, insumo_file=insumo_file)
        _make_rascunho(tmp_path, "ctx1", "v1")

        result = _impl_atualizar_preco_insumo(
            "ctx1", "INS-001", None, rascunho_id="v1", novo_valor_locacao_mensal=22000.0
        )
        assert result["status"] == "RASCUNHO"

        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        delta = rascunho_data["_deltas"][0]
        assert delta["novo_preco"] is None
        assert delta["novo_valor_locacao_mensal"] == 22000.0

        # insumo mestre permanece intocado até o merge
        data = json.loads(insumo_file.read_text(encoding="utf-8"))
        assert data["preco_unitario"] == 100.0

    def test_preco_e_locacao_no_mesmo_delta(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        insumo_file = tmp_path / "ins.json"
        insumo_file.write_text(json.dumps({"preco_unitario": 100.0}), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir, insumo_file=insumo_file)
        _make_rascunho(tmp_path, "ctx1", "v1")

        _impl_atualizar_preco_insumo("ctx1", "INS-001", 120.0, rascunho_id="v1", novo_valor_locacao_mensal=24000.0)
        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        delta = rascunho_data["_deltas"][0]
        assert delta["novo_preco"] == 120.0
        assert delta["novo_valor_locacao_mensal"] == 24000.0

    def test_delta_shape_preserved_sem_locacao(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Regressão: chamada só-com-preço não ganha a chave novo_valor_locacao_mensal —
        preserva o shape exato já coberto por test_master_no_jurisdicao_records_delta_in_rascunho."""
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        insumo_file = tmp_path / "ins.json"
        insumo_file.write_text(json.dumps({"preco_unitario": 5.0}), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir, insumo_file=insumo_file)
        _make_rascunho(tmp_path, "ctx1", "v1")

        _impl_atualizar_preco_insumo("ctx1", "INS-001", 42.0, rascunho_id="v1")
        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        delta = rascunho_data["_deltas"][0]
        assert "novo_valor_locacao_mensal" not in delta

    # ── ADR-165/166: novos_funcoes_aplicaveis opcional, mesmo caminho gated por rascunho ──

    def test_so_funcoes_aplicaveis_grava_delta_sem_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Popular funcoes_aplicaveis de um TREINAMENTO/EPI já existente não exige
        novo_preco nem novo_valor_locacao_mensal."""
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        insumo_file = tmp_path / "ins.json"
        insumo_file.write_text(json.dumps({"preco_unitario": 100.0}), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir, insumo_file=insumo_file)
        _make_rascunho(tmp_path, "ctx1", "v1")

        result = _impl_atualizar_preco_insumo(
            "ctx1",
            "TRE-NR35-ALTURA",
            None,
            rascunho_id="v1",
            novos_funcoes_aplicaveis=["MO-ELETRICISTA", "MO-P0016"],
        )
        assert result["status"] == "RASCUNHO"

        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        delta = rascunho_data["_deltas"][0]
        assert delta["novo_preco"] is None
        assert delta["novos_funcoes_aplicaveis"] == ["MO-ELETRICISTA", "MO-P0016"]

    def test_funcoes_aplicaveis_lista_vazia_e_preservada(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Lista vazia ([]) é um valor válido e distinto de None — "aplica a nenhuma
        função ainda" — não deve ser tratada como ausente."""
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        insumo_file = tmp_path / "ins.json"
        insumo_file.write_text(json.dumps({"preco_unitario": 100.0}), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir, insumo_file=insumo_file)
        _make_rascunho(tmp_path, "ctx1", "v1")

        _impl_atualizar_preco_insumo("ctx1", "TRE-NR22-MINERACAO", None, rascunho_id="v1", novos_funcoes_aplicaveis=[])
        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        delta = rascunho_data["_deltas"][0]
        assert delta["novos_funcoes_aplicaveis"] == []

    def test_delta_shape_preserved_sem_funcoes_aplicaveis(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Regressão: chamada só-com-preço não ganha a chave novos_funcoes_aplicaveis."""
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        insumo_file = tmp_path / "ins.json"
        insumo_file.write_text(json.dumps({"preco_unitario": 5.0}), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir, insumo_file=insumo_file)
        _make_rascunho(tmp_path, "ctx1", "v1")

        _impl_atualizar_preco_insumo("ctx1", "INS-001", 42.0, rascunho_id="v1")
        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        delta = rascunho_data["_deltas"][0]
        assert "novos_funcoes_aplicaveis" not in delta


class TestApplyPrecoInsumoDelta:
    """ADR-163 D4: aplicação do delta de valor_locacao_mensal no merge (aprovar_merge_catalogo)."""

    def test_aplica_valor_locacao_mensal_no_insumo_master(self, tmp_path: Path) -> None:
        from datetime import date

        from concilium.presentation.mcp.tools._catalogo_tools_helpers_a import _apply_preco_insumo_delta

        catalog_root = tmp_path / "cat1"
        insumos_dir = catalog_root / "insumos" / "equipamento"
        insumos_dir.mkdir(parents=True)
        insumo_file = insumos_dir / "EQ-001.json"
        insumo_file.write_text(
            json.dumps({"codigo": "EQ-001", "preco_unitario": 100.0, "atributos_especificos": {}}),
            encoding="utf-8",
        )

        _apply_preco_insumo_delta(
            catalog_root,
            "EQ-001",
            None,
            None,
            None,
            "mgr-1",
            date(2026, 7, 28),
            novo_valor_locacao_mensal=22000.0,
        )

        data = json.loads(insumo_file.read_text(encoding="utf-8"))
        assert data["atributos_especificos"]["valor_locacao_mensal"] == 22000.0
        # preço não deve mudar quando novo_preco é None
        assert data["preco_unitario"] == 100.0

    def test_aplica_preco_e_locacao_juntos(self, tmp_path: Path) -> None:
        from datetime import date

        from concilium.presentation.mcp.tools._catalogo_tools_helpers_a import _apply_preco_insumo_delta

        catalog_root = tmp_path / "cat1"
        insumos_dir = catalog_root / "insumos" / "equipamento"
        insumos_dir.mkdir(parents=True)
        insumo_file = insumos_dir / "EQ-002.json"
        insumo_file.write_text(
            json.dumps({"codigo": "EQ-002", "preco_unitario": 100.0, "atributos_especificos": {}}),
            encoding="utf-8",
        )

        _apply_preco_insumo_delta(
            catalog_root,
            "EQ-002",
            150.0,
            None,
            "revisão de mercado",
            "mgr-1",
            date(2026, 7, 28),
            novo_valor_locacao_mensal=30000.0,
        )

        data = json.loads(insumo_file.read_text(encoding="utf-8"))
        assert data["preco_unitario"] == 150.0
        assert data["atributos_especificos"]["valor_locacao_mensal"] == 30000.0

    def test_aplica_funcoes_aplicaveis_no_insumo_master(self, tmp_path: Path) -> None:
        """ADR-165/166: novos_funcoes_aplicaveis grava direto em
        atributos_especificos.funcoes_aplicaveis no momento do merge."""
        from datetime import date

        from concilium.presentation.mcp.tools._catalogo_tools_helpers_a import _apply_preco_insumo_delta

        catalog_root = tmp_path / "cat1"
        insumos_dir = catalog_root / "insumos" / "treinamento"
        insumos_dir.mkdir(parents=True)
        insumo_file = insumos_dir / "TRE-NR35-ALTURA.json"
        insumo_file.write_text(
            json.dumps({"codigo": "TRE-NR35-ALTURA", "preco_unitario": 350.0, "atributos_especificos": {}}),
            encoding="utf-8",
        )

        _apply_preco_insumo_delta(
            catalog_root,
            "TRE-NR35-ALTURA",
            None,
            None,
            None,
            "mgr-1",
            date(2026, 7, 29),
            novos_funcoes_aplicaveis=["MO-ELETRICISTA", "MO-P0016"],
        )

        data = json.loads(insumo_file.read_text(encoding="utf-8"))
        assert data["atributos_especificos"]["funcoes_aplicaveis"] == ["MO-ELETRICISTA", "MO-P0016"]
        assert data["preco_unitario"] == 350.0

    def test_funcoes_aplicaveis_lista_vazia_e_gravada(self, tmp_path: Path) -> None:
        from datetime import date

        from concilium.presentation.mcp.tools._catalogo_tools_helpers_a import _apply_preco_insumo_delta

        catalog_root = tmp_path / "cat1"
        insumos_dir = catalog_root / "insumos" / "treinamento"
        insumos_dir.mkdir(parents=True)
        insumo_file = insumos_dir / "TRE-NR22-MINERACAO.json"
        insumo_file.write_text(
            json.dumps({"codigo": "TRE-NR22-MINERACAO", "preco_unitario": 315.0, "atributos_especificos": {}}),
            encoding="utf-8",
        )

        _apply_preco_insumo_delta(
            catalog_root,
            "TRE-NR22-MINERACAO",
            None,
            None,
            None,
            "mgr-1",
            date(2026, 7, 29),
            novos_funcoes_aplicaveis=[],
        )

        data = json.loads(insumo_file.read_text(encoding="utf-8"))
        assert data["atributos_especificos"]["funcoes_aplicaveis"] == []


# ---------------------------------------------------------------------------
# _impl_criar_insumo (ADR-163 D5)
# ---------------------------------------------------------------------------


class TestImplCriarInsumo:
    def _setup(self, monkeypatch: pytest.MonkeyPatch, rt: MagicMock, tmp_path: Path) -> None:
        monkeypatch.setattr(mod, "_runtime", lambda: rt)
        monkeypatch.setattr(mod, "_config_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "_wrap_response", _passthrough)

    def _kwargs(self, **overrides):
        base = dict(
            codigo="EQ-999",
            tipo="EQUIPAMENTO",
            descricao="Retroescavadeira",
            unidade="h",
            preco_unitario=120.0,
            categoria="TERRAPLENAGEM",
            fonte_preco="cotacao_mercado",
        )
        base.update(overrides)
        return base

    def test_codigo_ja_existente_retorna_erro_sem_tocar_rascunho(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        insumos_dir = tmp_path / "catalogos" / "cat1" / "insumos" / "equipamento"
        insumos_dir.mkdir(parents=True)
        (insumos_dir / "EQ-999.json").write_text('{"codigo": "EQ-999"}', encoding="utf-8")
        _make_rascunho(tmp_path, "ctx1", "v1")

        result = _impl_criar_insumo("ctx1", "v1", **self._kwargs())
        assert "erro" in result
        assert "já existe" in result["erro"]

        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        assert rascunho_data.get("_deltas", []) == []

    def test_insumo_invalido_retorna_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # codigo fora do pattern ^[A-Z0-9-]{3,40}$ do modelo Insumo
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        (tmp_path / "catalogos" / "cat1").mkdir(parents=True)
        _make_rascunho(tmp_path, "ctx1", "v1")

        result = _impl_criar_insumo("ctx1", "v1", **self._kwargs(codigo="eq minusculo!"))
        assert "erro" in result

    def test_happy_path_grava_delta_de_criacao(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        (tmp_path / "catalogos" / "cat1").mkdir(parents=True)
        _make_rascunho(tmp_path, "ctx1", "v1")

        result = _impl_criar_insumo("ctx1", "v1", **self._kwargs())
        assert result["status"] == "RASCUNHO"
        assert result["layer"] == "MASTER"
        assert result["insumo_id"] == "EQ-999"

        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        assert len(rascunho_data["_deltas"]) == 1
        delta = rascunho_data["_deltas"][0]
        assert delta["tipo"] == "criacao_insumo"
        assert delta["insumo"]["codigo"] == "EQ-999"
        assert delta["insumo"]["descricao"] == "Retroescavadeira"

        # nada foi criado no catálogo mestre ainda
        insumo_file = tmp_path / "catalogos" / "cat1" / "insumos" / "equipamento" / "EQ-999.json"
        assert not insumo_file.exists()

    def test_rascunho_inexistente_returns_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        (tmp_path / "catalogos" / "cat1").mkdir(parents=True)

        result = _impl_criar_insumo("ctx1", "v-nao-existe", **self._kwargs())
        assert "erro" in result
        assert "não encontrado" in result["erro"]

    def test_atributos_especificos_opcional(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        (tmp_path / "catalogos" / "cat1").mkdir(parents=True)
        _make_rascunho(tmp_path, "ctx1", "v1")

        result = _impl_criar_insumo(
            "ctx1", "v1", **self._kwargs(atributos_especificos={"valor_locacao_mensal": 24000.0})
        )
        assert result["status"] == "RASCUNHO"
        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        delta = rascunho_data["_deltas"][0]
        assert delta["insumo"]["atributos_especificos"]["valor_locacao_mensal"] == 24000.0


class TestApplyCriarInsumoDelta:
    def test_cria_arquivo_no_diretorio_do_tipo(self, tmp_path: Path) -> None:
        from concilium.presentation.mcp.tools._catalogo_tools_helpers_a import _apply_criar_insumo_delta

        catalog_root = tmp_path / "cat1"
        insumo_data = {
            "codigo": "EQ-999",
            "tipo": "EQUIPAMENTO",
            "descricao": "Retroescavadeira",
            "unidade": "h",
            "preco_unitario": 120.0,
            "categoria": "TERRAPLENAGEM",
            "fonte_preco": "cotacao_mercado",
            "atributos_especificos": {},
        }
        _apply_criar_insumo_delta(catalog_root, insumo_data)

        insumo_file = catalog_root / "insumos" / "equipamento" / "EQ-999.json"
        assert insumo_file.exists()
        data = json.loads(insumo_file.read_text(encoding="utf-8"))
        assert data["codigo"] == "EQ-999"
        assert data["descricao"] == "Retroescavadeira"


# ---------------------------------------------------------------------------
# _impl_descontinuar_insumo (ADR-163 D6)
# ---------------------------------------------------------------------------


class TestImplDescontinuarInsumo:
    def _setup(self, monkeypatch: pytest.MonkeyPatch, rt: MagicMock, tmp_path: Path) -> None:
        monkeypatch.setattr(mod, "_runtime", lambda: rt)
        monkeypatch.setattr(mod, "_config_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "_wrap_response", _passthrough)

    def test_insumo_inexistente_retorna_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        (tmp_path / "catalogos" / "cat1" / "insumos").mkdir(parents=True)
        _make_rascunho(tmp_path, "ctx1", "v1")

        result = _impl_descontinuar_insumo("ctx1", "v1", "EQ-INEXISTENTE", "obsoleto")
        assert "erro" in result
        assert "não encontrado" in result["erro"]

    def test_happy_path_grava_delta_de_descontinuacao(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        insumos_dir = tmp_path / "catalogos" / "cat1" / "insumos" / "equipamento"
        insumos_dir.mkdir(parents=True)
        insumo_file = insumos_dir / "EQ-001.json"
        insumo_file.write_text(json.dumps({"codigo": "EQ-001", "status": "ativo"}), encoding="utf-8")
        _make_rascunho(tmp_path, "ctx1", "v1")

        result = _impl_descontinuar_insumo("ctx1", "v1", "EQ-001", "substituído por modelo mais novo")
        assert result["status"] == "RASCUNHO"
        assert result["insumo_id"] == "EQ-001"

        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        delta = rascunho_data["_deltas"][0]
        assert delta["tipo"] == "descontinuacao_insumo"
        assert delta["insumo_id"] == "EQ-001"
        assert delta["motivo"] == "substituído por modelo mais novo"

        # arquivo mestre permanece intocado até o merge
        data = json.loads(insumo_file.read_text(encoding="utf-8"))
        assert data["status"] == "ativo"

    def test_rascunho_inexistente_returns_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        insumos_dir = tmp_path / "catalogos" / "cat1" / "insumos" / "equipamento"
        insumos_dir.mkdir(parents=True)
        (insumos_dir / "EQ-001.json").write_text(json.dumps({"codigo": "EQ-001"}), encoding="utf-8")

        result = _impl_descontinuar_insumo("ctx1", "v-nao-existe", "EQ-001", "obsoleto")
        assert "erro" in result
        assert "não encontrado" in result["erro"]


class TestApplyDescontinuacaoInsumoDelta:
    def test_marca_status_descontinuado_sem_remover_arquivo(self, tmp_path: Path) -> None:
        from concilium.presentation.mcp.tools._catalogo_tools_helpers_a import (
            _apply_descontinuacao_insumo_delta,
        )

        catalog_root = tmp_path / "cat1"
        insumos_dir = catalog_root / "insumos" / "equipamento"
        insumos_dir.mkdir(parents=True)
        insumo_file = insumos_dir / "EQ-001.json"
        insumo_file.write_text(json.dumps({"codigo": "EQ-001", "descricao": "X", "status": "ativo"}), encoding="utf-8")

        _apply_descontinuacao_insumo_delta(catalog_root, "EQ-001", "obsoleto")

        assert insumo_file.exists()  # nunca remoção física
        data = json.loads(insumo_file.read_text(encoding="utf-8"))
        assert data["status"] == "descontinuado"
        assert data["descricao"] == "X"  # resto do insumo preservado


# ---------------------------------------------------------------------------
# _impl_criar_insumos_lote (ADR-164)
# ---------------------------------------------------------------------------


class TestImplCriarInsumosLote:
    def _setup(self, monkeypatch: pytest.MonkeyPatch, rt: MagicMock, tmp_path: Path) -> None:
        monkeypatch.setattr(mod, "_runtime", lambda: rt)
        monkeypatch.setattr(mod, "_config_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "_wrap_response", _passthrough)

    def _item(self, **overrides):
        base = dict(
            codigo="EQ-999",
            tipo="EQUIPAMENTO",
            descricao="Retroescavadeira",
            unidade="h",
            preco_unitario=120.0,
            categoria="TERRAPLENAGEM",
            fonte_preco="cotacao_mercado",
        )
        base.update(overrides)
        return base

    def test_lista_vazia_retorna_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)

        result = mod._impl_criar_insumos_lote("ctx1", "v1", [])
        assert "erro" in result

    def test_acima_do_limite_retorna_erro_sem_gravar_nada(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        (tmp_path / "catalogos" / "cat1").mkdir(parents=True)
        _make_rascunho(tmp_path, "ctx1", "v1")

        itens = [self._item(codigo=f"EQ-{i:04d}") for i in range(mod.MAX_LOTE_INSUMOS + 1)]
        result = mod._impl_criar_insumos_lote("ctx1", "v1", itens)
        assert "erro" in result
        assert str(mod.MAX_LOTE_INSUMOS) in result["erro"]

        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        assert rascunho_data.get("_deltas", []) == []

    def test_todos_validos_grava_um_delta_por_item(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        (tmp_path / "catalogos" / "cat1").mkdir(parents=True)
        _make_rascunho(tmp_path, "ctx1", "v1")

        itens = [self._item(codigo="EQ-001"), self._item(codigo="EQ-002"), self._item(codigo="EQ-003")]
        result = mod._impl_criar_insumos_lote("ctx1", "v1", itens)

        assert result["status"] == "RASCUNHO"
        assert result["total"] == 3
        assert result["sucesso"] == 3
        assert result["falhas"] == 0

        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        assert len(rascunho_data["_deltas"]) == 3
        assert {d["insumo"]["codigo"] for d in rascunho_data["_deltas"]} == {"EQ-001", "EQ-002", "EQ-003"}

    def test_codigo_duplicado_dentro_do_lote_falha_so_o_segundo(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        (tmp_path / "catalogos" / "cat1").mkdir(parents=True)
        _make_rascunho(tmp_path, "ctx1", "v1")

        itens = [self._item(codigo="EQ-001"), self._item(codigo="EQ-001")]
        result = mod._impl_criar_insumos_lote("ctx1", "v1", itens)

        assert result["sucesso"] == 1
        assert result["falhas"] == 1
        assert result["resultados"][0]["status"] == "ok"
        assert result["resultados"][1]["status"] == "erro"
        assert "duplicado" in result["resultados"][1]["erro"]

    def test_codigo_ja_existente_no_catalogo_falha_so_aquele_item(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        insumos_dir = tmp_path / "catalogos" / "cat1" / "insumos" / "equipamento"
        insumos_dir.mkdir(parents=True)
        (insumos_dir / "EQ-001.json").write_text('{"codigo": "EQ-001"}', encoding="utf-8")
        _make_rascunho(tmp_path, "ctx1", "v1")

        itens = [self._item(codigo="EQ-001"), self._item(codigo="EQ-002")]
        result = mod._impl_criar_insumos_lote("ctx1", "v1", itens)

        assert result["sucesso"] == 1
        assert result["falhas"] == 1
        falha = next(r for r in result["resultados"] if r["codigo"] == "EQ-001")
        assert falha["status"] == "erro"
        assert "já existe" in falha["erro"]
        sucesso = next(r for r in result["resultados"] if r["codigo"] == "EQ-002")
        assert sucesso["status"] == "ok"

    def test_item_com_schema_invalido_falha_so_aquele_item(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        (tmp_path / "catalogos" / "cat1").mkdir(parents=True)
        _make_rascunho(tmp_path, "ctx1", "v1")

        itens = [self._item(codigo="EQ-001"), self._item(codigo="eq minusculo!")]
        result = mod._impl_criar_insumos_lote("ctx1", "v1", itens)

        assert result["sucesso"] == 1
        assert result["falhas"] == 1

    def test_rascunho_inexistente_retorna_erro_top_level(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        (tmp_path / "catalogos" / "cat1").mkdir(parents=True)

        result = mod._impl_criar_insumos_lote("ctx1", "v-nao-existe", [self._item()])
        assert "erro" in result
        assert "não encontrado" in result["erro"]


# ---------------------------------------------------------------------------
# _impl_atualizar_precos_insumos_lote (ADR-164)
# ---------------------------------------------------------------------------


class TestImplAtualizarPrecosInsumosLote:
    def _setup(self, monkeypatch: pytest.MonkeyPatch, rt: MagicMock, tmp_path: Path) -> None:
        monkeypatch.setattr(mod, "_runtime", lambda: rt)
        monkeypatch.setattr(mod, "_config_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "_wrap_response", _passthrough)

    def test_lista_vazia_retorna_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        result = mod._impl_atualizar_precos_insumos_lote("ctx1", "v1", [])
        assert "erro" in result

    def test_acima_do_limite_retorna_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        itens = [{"insumo_id": f"INS-{i}", "novo_preco": 1.0} for i in range(mod.MAX_LOTE_INSUMOS + 1)]
        result = mod._impl_atualizar_precos_insumos_lote("ctx1", "v1", itens)
        assert "erro" in result

    def test_todos_validos_grava_um_delta_por_item(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        insumos_dir = tmp_path / "catalogos" / "cat1" / "insumos" / "equipamento"
        insumos_dir.mkdir(parents=True)
        (insumos_dir / "EQ-001.json").write_text(json.dumps({"preco_unitario": 100.0}), encoding="utf-8")
        (insumos_dir / "EQ-002.json").write_text(json.dumps({"preco_unitario": 50.0}), encoding="utf-8")
        _make_rascunho(tmp_path, "ctx1", "v1")

        itens = [
            {"insumo_id": "EQ-001", "novo_preco": 150.0},
            {"insumo_id": "EQ-002", "novo_valor_locacao_mensal": 9000.0},
        ]
        result = mod._impl_atualizar_precos_insumos_lote("ctx1", "v1", itens)

        assert result["sucesso"] == 2
        assert result["falhas"] == 0

        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        deltas = rascunho_data["_deltas"]
        assert len(deltas) == 2
        d1 = next(d for d in deltas if d["insumo_id"] == "EQ-001")
        assert d1["novo_preco"] == 150.0
        d2 = next(d for d in deltas if d["insumo_id"] == "EQ-002")
        assert d2["novo_valor_locacao_mensal"] == 9000.0

        # insumos mestre intocados até o merge
        assert json.loads((insumos_dir / "EQ-001.json").read_text())["preco_unitario"] == 100.0

    def test_item_sem_preco_nem_locacao_falha_so_aquele_item(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        insumos_dir = tmp_path / "catalogos" / "cat1" / "insumos" / "equipamento"
        insumos_dir.mkdir(parents=True)
        (insumos_dir / "EQ-001.json").write_text(json.dumps({"preco_unitario": 100.0}), encoding="utf-8")
        _make_rascunho(tmp_path, "ctx1", "v1")

        itens = [{"insumo_id": "EQ-001", "novo_preco": 150.0}, {"insumo_id": "EQ-002"}]
        result = mod._impl_atualizar_precos_insumos_lote("ctx1", "v1", itens)

        assert result["sucesso"] == 1
        assert result["falhas"] == 1
        falha = next(r for r in result["resultados"] if r["insumo_id"] == "EQ-002")
        assert falha["status"] == "erro"

    def test_insumo_inexistente_falha_so_aquele_item(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        insumos_dir = tmp_path / "catalogos" / "cat1" / "insumos" / "equipamento"
        insumos_dir.mkdir(parents=True)
        _make_rascunho(tmp_path, "ctx1", "v1")

        itens = [{"insumo_id": "EQ-INEXISTENTE", "novo_preco": 10.0}]
        result = mod._impl_atualizar_precos_insumos_lote("ctx1", "v1", itens)
        assert result["falhas"] == 1

    def test_novos_funcoes_aplicaveis_por_item_lote(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """ADR-165/166: novos_funcoes_aplicaveis também é aceito por item no lote,
        sozinho (sem novo_preco/novo_valor_locacao_mensal)."""
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        insumos_dir = tmp_path / "catalogos" / "cat1" / "insumos" / "treinamento"
        insumos_dir.mkdir(parents=True)
        (insumos_dir / "TRE-NR35-ALTURA.json").write_text(json.dumps({"preco_unitario": 350.0}), encoding="utf-8")
        (insumos_dir / "TRE-NR22-MINERACAO.json").write_text(json.dumps({"preco_unitario": 315.0}), encoding="utf-8")
        _make_rascunho(tmp_path, "ctx1", "v1")

        itens = [
            {"insumo_id": "TRE-NR35-ALTURA", "novos_funcoes_aplicaveis": ["MO-ELETRICISTA"]},
            {"insumo_id": "TRE-NR22-MINERACAO", "novos_funcoes_aplicaveis": []},
        ]
        result = mod._impl_atualizar_precos_insumos_lote("ctx1", "v1", itens)

        assert result["sucesso"] == 2
        assert result["falhas"] == 0
        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        deltas = rascunho_data["_deltas"]
        d1 = next(d for d in deltas if d["insumo_id"] == "TRE-NR35-ALTURA")
        assert d1["novos_funcoes_aplicaveis"] == ["MO-ELETRICISTA"]
        d2 = next(d for d in deltas if d["insumo_id"] == "TRE-NR22-MINERACAO")
        assert d2["novos_funcoes_aplicaveis"] == []


# ---------------------------------------------------------------------------
# _impl_descontinuar_insumos_lote (ADR-164)
# ---------------------------------------------------------------------------


class TestImplDescontinuarInsumosLote:
    def _setup(self, monkeypatch: pytest.MonkeyPatch, rt: MagicMock, tmp_path: Path) -> None:
        monkeypatch.setattr(mod, "_runtime", lambda: rt)
        monkeypatch.setattr(mod, "_config_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "_wrap_response", _passthrough)

    def test_lista_vazia_retorna_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        result = mod._impl_descontinuar_insumos_lote("ctx1", "v1", [])
        assert "erro" in result

    def test_acima_do_limite_retorna_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        itens = [{"insumo_id": f"INS-{i}"} for i in range(mod.MAX_LOTE_INSUMOS + 1)]
        result = mod._impl_descontinuar_insumos_lote("ctx1", "v1", itens)
        assert "erro" in result

    def test_todos_validos_grava_um_delta_por_item(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        insumos_dir = tmp_path / "catalogos" / "cat1" / "insumos" / "equipamento"
        insumos_dir.mkdir(parents=True)
        (insumos_dir / "EQ-001.json").write_text(json.dumps({"codigo": "EQ-001"}), encoding="utf-8")
        (insumos_dir / "EQ-002.json").write_text(json.dumps({"codigo": "EQ-002"}), encoding="utf-8")
        _make_rascunho(tmp_path, "ctx1", "v1")

        itens = [
            {"insumo_id": "EQ-001", "motivo": "obsoleto"},
            {"insumo_id": "EQ-002", "motivo": "substituído"},
        ]
        result = mod._impl_descontinuar_insumos_lote("ctx1", "v1", itens)

        assert result["sucesso"] == 2
        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        assert len(rascunho_data["_deltas"]) == 2

        # arquivos mestre intocados até o merge (soft delete só no merge)
        assert json.loads((insumos_dir / "EQ-001.json").read_text()).get("status") is None

    def test_insumo_inexistente_falha_so_aquele_item(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        insumos_dir = tmp_path / "catalogos" / "cat1" / "insumos" / "equipamento"
        insumos_dir.mkdir(parents=True)
        (insumos_dir / "EQ-001.json").write_text(json.dumps({"codigo": "EQ-001"}), encoding="utf-8")
        _make_rascunho(tmp_path, "ctx1", "v1")

        itens = [{"insumo_id": "EQ-001"}, {"insumo_id": "EQ-INEXISTENTE"}]
        result = mod._impl_descontinuar_insumos_lote("ctx1", "v1", itens)

        assert result["sucesso"] == 1
        assert result["falhas"] == 1


# ---------------------------------------------------------------------------
# _impl_consultar_preco_insumo_temporal
# ---------------------------------------------------------------------------


class TestImplConsultarPrecoInsumoTemporal:
    def _setup(self, monkeypatch: pytest.MonkeyPatch, rt: MagicMock, projects_dir: Path) -> None:
        monkeypatch.setattr(mod, "_runtime", lambda: rt)
        monkeypatch.setattr(mod, "_projetos_root", lambda: projects_dir)
        monkeypatch.setattr(mod, "_wrap_response", _passthrough)

    def test_invalid_data_referencia_returns_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 242-245
        rt = _make_rt()
        projects_dir = tmp_path / "projetos"
        self._setup(monkeypatch, rt, projects_dir)

        result = _impl_consultar_preco_insumo_temporal("ctx1", "INS-001", "nao-e-data")
        assert "erro" in result
        assert "data_referencia inválida" in result["erro"]
        assert "nao-e-data" in result["erro"]

    def test_load_contexto_raises_returns_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 247-251
        rt = _make_rt()
        rt.load_contexto.side_effect = ValueError("ctx not found")
        projects_dir = tmp_path / "projetos"
        self._setup(monkeypatch, rt, projects_dir)

        result = _impl_consultar_preco_insumo_temporal("ctx1", "INS-001", "2025-01-01")
        assert "erro" in result
        assert "ctx not found" in result["erro"]

    def test_projeto_path_not_found(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 256-259
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        self._setup(monkeypatch, rt, projects_dir)

        mock_repo = MagicMock()
        mock_repo.resolver_preco.return_value = (10.0, "MASTER_BASE")
        with patch("concilium.infrastructure.repositories.insumo.RepositorioInsumo", return_value=mock_repo):
            result = _impl_consultar_preco_insumo_temporal("ctx1", "INS-001", "2025-01-01", projeto_id="MISSING-PROJ")
        assert "erro" in result
        assert "MISSING-PROJ" in result["erro"]

    def test_projeto_overrides_file_exists_valid(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 260-266 — overrides_file exists and is valid JSON dict
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        proj_dir = projects_dir / "PROJ-001"
        overrides_dir = proj_dir / "overrides"
        overrides_dir.mkdir(parents=True)
        overrides_data = {"INS-001::BASE": {"preco": 99.0}}
        (overrides_dir / "insumos_override.json").write_text(json.dumps(overrides_data), encoding="utf-8")
        self._setup(monkeypatch, rt, projects_dir)

        mock_repo = MagicMock()
        mock_repo.resolver_preco.return_value = (99.0, "PROJECT_OVERRIDE")
        with patch("concilium.infrastructure.repositories.insumo.RepositorioInsumo", return_value=mock_repo):
            result = _impl_consultar_preco_insumo_temporal("ctx1", "INS-001", "2025-01-01", projeto_id="PROJ-001")
        assert result["status"] == "SUCESSO"
        assert result["preco_unitario"] == 99.0
        assert result["fonte_preco"] == "PROJECT_OVERRIDE"
        # verify overrides dict was passed
        call_kwargs = mock_repo.resolver_preco.call_args
        assert call_kwargs.kwargs.get("overrides") == overrides_data

    def test_projeto_overrides_file_malformed_json(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 262-267 — malformed JSON → overrides=None
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        proj_dir = projects_dir / "PROJ-001"
        overrides_dir = proj_dir / "overrides"
        overrides_dir.mkdir(parents=True)
        (overrides_dir / "insumos_override.json").write_text("NOT_JSON", encoding="utf-8")
        self._setup(monkeypatch, rt, projects_dir)

        mock_repo = MagicMock()
        mock_repo.resolver_preco.return_value = (5.0, "MASTER_BASE")
        with patch("concilium.infrastructure.repositories.insumo.RepositorioInsumo", return_value=mock_repo):
            _impl_consultar_preco_insumo_temporal("ctx1", "INS-001", "2025-01-01", projeto_id="PROJ-001")
        # overrides=None was passed
        call_kwargs = mock_repo.resolver_preco.call_args
        assert call_kwargs.kwargs.get("overrides") is None

    def test_projeto_overrides_file_not_a_dict(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # line 264 — isinstance(raw, dict) check — list instead of dict → overrides=None
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        proj_dir = projects_dir / "PROJ-001"
        overrides_dir = proj_dir / "overrides"
        overrides_dir.mkdir(parents=True)
        (overrides_dir / "insumos_override.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        self._setup(monkeypatch, rt, projects_dir)

        mock_repo = MagicMock()
        mock_repo.resolver_preco.return_value = (5.0, "MASTER_BASE")
        with patch("concilium.infrastructure.repositories.insumo.RepositorioInsumo", return_value=mock_repo):
            _impl_consultar_preco_insumo_temporal("ctx1", "INS-001", "2025-01-01", projeto_id="PROJ-001")
        call_kwargs = mock_repo.resolver_preco.call_args
        assert call_kwargs.kwargs.get("overrides") is None

    def test_no_projeto_id_overrides_none(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # line 255-256 — projeto_id=None → overrides stays None
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        self._setup(monkeypatch, rt, projects_dir)

        mock_repo = MagicMock()
        mock_repo.resolver_preco.return_value = (10.0, "MASTER_BASE")
        with patch("concilium.infrastructure.repositories.insumo.RepositorioInsumo", return_value=mock_repo):
            result = _impl_consultar_preco_insumo_temporal("ctx1", "INS-001", "2025-06-01")
        assert result["status"] == "SUCESSO"
        call_kwargs = mock_repo.resolver_preco.call_args
        assert call_kwargs.kwargs.get("overrides") is None

    def test_happy_path_response_shape(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 269-288 — full happy path response shape
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        self._setup(monkeypatch, rt, projects_dir)

        mock_repo = MagicMock()
        mock_repo.resolver_preco.return_value = (123.45, "SICRO_REGIONAL")
        with patch("concilium.infrastructure.repositories.insumo.RepositorioInsumo", return_value=mock_repo):
            result = _impl_consultar_preco_insumo_temporal("ctx1", "INS-001", "2025-03-15", jurisdicao_id="CE")
        assert result["preco_unitario"] == 123.45
        assert result["fonte_preco"] == "SICRO_REGIONAL"
        assert result["data_referencia"] == "2025-03-15"
        assert result["insumo_id"] == "INS-001"
        assert result["jurisdicao_id"] == "CE"


# ---------------------------------------------------------------------------
# _impl_adicionar_variante_producao
# ---------------------------------------------------------------------------


class TestImplAdicionarVarianteProducao:
    def _setup(
        self,
        monkeypatch: pytest.MonkeyPatch,
        rt: MagicMock,
        config_dir: Path,
        projects_dir: Path,
        prod_file: Path | None = None,
    ) -> None:
        monkeypatch.setattr(mod, "_runtime", lambda: rt)
        monkeypatch.setattr(mod, "_config_root", lambda: config_dir)
        monkeypatch.setattr(mod, "_projetos_root", lambda: projects_dir)
        monkeypatch.setattr(mod, "_wrap_response", _passthrough)
        if prod_file is not None:
            monkeypatch.setattr(mod, "validate_and_resolve_producao_file", lambda _cr, _pid, _vh: prod_file)

    def test_invalid_equipe_json_returns_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 315-316, 358-359 — json.loads fails → outer except → {"erro": ...}
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        self._setup(monkeypatch, rt, tmp_path, projects_dir)

        result = _impl_adicionar_variante_producao("ctx1", "PROD-001", "V1", "Variante 1", 150.0, "NOT_JSON")
        assert "erro" in result
        assert "Erro ao adicionar variante" in result["erro"]

    def test_projeto_path_not_found(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 320-322
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        self._setup(monkeypatch, rt, tmp_path, projects_dir)

        result = _impl_adicionar_variante_producao(
            "ctx1", "PROD-001", "V1", "Variante 1", 150.0, json.dumps({"funcoes": []}), projeto_id="MISSING-PROJ"
        )
        assert "erro" in result
        assert "MISSING-PROJ" in result["erro"]

    def test_projeto_creates_new_overrides(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 324-336 — new overlay file created, no longer the orphaned
        # production_variants.json (issue #121): grava em producoes_overlay.json,
        # o arquivo que o CatalogResolver de fato lê.
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        proj_dir = projects_dir / "PROJ-001"
        proj_dir.mkdir(parents=True)
        self._setup(monkeypatch, rt, tmp_path, projects_dir)

        equipe = json.dumps({"funcoes": [{"funcao_id": "MO-001", "num_pessoas": 1}]})
        result = _impl_adicionar_variante_producao(
            "ctx1", "PROD-001", "V1", "Variante 1", 150.0, equipe, projeto_id="PROJ-001"
        )
        assert result["status"] == "SUCESSO"
        assert result["layer"] == "PROJETO"
        overlay_file = proj_dir / "overrides" / "producoes_overlay.json"
        assert overlay_file.exists()
        saved = json.loads(overlay_file.read_text(encoding="utf-8"))
        variantes = saved["PROD-001"]["variantes"]
        assert len(variantes) == 1
        assert variantes[0]["id"] == "V1"
        assert variantes[0]["valor_horario"] == 150.0

    def test_projeto_merges_existing_overrides(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 327-333 — existing overlay merged, variantes de outras producoes preservadas
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        proj_dir = projects_dir / "PROJ-001"
        overrides_dir = proj_dir / "overrides"
        overrides_dir.mkdir(parents=True)
        existing = {"OTHER-PROD": {"variantes": [{"id": "V0", "nome": "old", "valor_horario": 50.0, "equipe": {}}]}}
        (overrides_dir / "producoes_overlay.json").write_text(json.dumps(existing), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir)

        equipe = json.dumps({"funcoes": []})
        result = _impl_adicionar_variante_producao(
            "ctx1", "PROD-001", "V2", "Nova Variante", 200.0, equipe, projeto_id="PROJ-001"
        )
        assert result["status"] == "SUCESSO"
        saved = json.loads((overrides_dir / "producoes_overlay.json").read_text(encoding="utf-8"))
        assert saved["OTHER-PROD"]["variantes"][0]["id"] == "V0"
        assert saved["PROD-001"]["variantes"][0]["id"] == "V2"

    def test_no_rascunho_id_returns_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # ADR-145 D1 — sem rascunho_id (e sem projeto_id) não pode editar o master
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        self._setup(monkeypatch, rt, tmp_path, projects_dir)

        equipe = json.dumps({"funcoes": []})
        result = _impl_adicionar_variante_producao("ctx1", "PROD-001", "V1", "V1", 100.0, equipe)
        assert "erro" in result
        assert "rascunho_id" in result["erro"]

    def test_master_governance_error_returns_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # CatalogGovernanceError on master branch
        from concilium.application.orchestrators.catalog_governance import CatalogGovernanceError

        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        monkeypatch.setattr(mod, "_runtime", lambda: rt)
        monkeypatch.setattr(mod, "_config_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "_projetos_root", lambda: projects_dir)
        monkeypatch.setattr(mod, "_wrap_response", _passthrough)
        monkeypatch.setattr(
            mod,
            "validate_and_resolve_producao_file",
            lambda _cr, _pid, _vh: (_ for _ in ()).throw(CatalogGovernanceError("invalid producao")),
        )

        equipe = json.dumps({"funcoes": []})
        result = _impl_adicionar_variante_producao("ctx1", "PROD-001", "V1", "V1", 100.0, equipe, rascunho_id="v1")
        assert "erro" in result
        assert "invalid producao" in result["erro"]

    def test_master_records_delta_when_variantes_absent(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # ADR-145 D1 — grava delta no rascunho; arquivo de producao permanece intocado
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)

        prod_file = tmp_path / "prod.json"
        prod_data = {"id": "PROD-001"}  # no "variantes" key
        prod_file.write_text(json.dumps(prod_data), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir, prod_file=prod_file)
        _make_rascunho(tmp_path, "ctx1", "v1")

        equipe = json.dumps({"funcoes": [{"funcao_id": "MO-001"}]})
        result = _impl_adicionar_variante_producao("ctx1", "PROD-001", "V-NEW", "Nova", 88.0, equipe, rascunho_id="v1")
        assert result["status"] == "RASCUNHO"
        assert result["layer"] == "MASTER"

        data = json.loads(prod_file.read_text(encoding="utf-8"))
        assert "variantes" not in data  # intocado até o merge

        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        delta = rascunho_data["_deltas"][0]
        assert delta["tipo"] == "variante_producao"
        assert delta["producao_id"] == "PROD-001"
        assert delta["variante_id"] == "V-NEW"
        assert delta["valor_horario"] == 88.0
        assert delta["equipe"] == {"funcoes": [{"funcao_id": "MO-001"}]}

    def test_rascunho_inexistente_returns_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        prod_file = tmp_path / "prod.json"
        prod_file.write_text(json.dumps({"id": "PROD-001"}), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir, prod_file=prod_file)

        equipe = json.dumps({"funcoes": []})
        result = _impl_adicionar_variante_producao(
            "ctx1", "PROD-001", "V1", "V1", 100.0, equipe, rascunho_id="v-nao-existe"
        )
        assert "erro" in result
        assert "não encontrado" in result["erro"]


# ---------------------------------------------------------------------------
# _append_delta_to_rascunho (direct — error branches not reachable via the
# public impl functions with valid inputs)
# ---------------------------------------------------------------------------


class TestAppendDeltaToRascunho:
    def test_read_failure_returns_erro(self, tmp_path: Path) -> None:
        # lines 215-216 — rascunho file exists but contains malformed JSON
        versions_dir = tmp_path / "contextos" / "ctx1" / "versions"
        versions_dir.mkdir(parents=True)
        (versions_dir / "v1.json").write_text("NOT_VALID_JSON{", encoding="utf-8")

        result = mod._append_delta_to_rascunho(tmp_path, "ctx1", "v1", {"tipo": "preco_insumo"})
        assert result is not None
        assert "Falha ao ler rascunho" in result
        assert "v1" in result

    def test_write_failure_returns_erro(self, tmp_path: Path) -> None:
        # lines 227-228 — read succeeds, write_text raises
        _make_rascunho(tmp_path, "ctx1", "v1")

        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            result = mod._append_delta_to_rascunho(tmp_path, "ctx1", "v1", {"tipo": "preco_insumo"})
        assert result is not None
        assert "Falha ao gravar delta no rascunho" in result


# ---------------------------------------------------------------------------
# _append_deltas_to_rascunho (ADR-164 — lote: N deltas numa única leitura+escrita)
# ---------------------------------------------------------------------------


class TestAppendDeltasToRascunho:
    def test_grava_multiplos_deltas_numa_unica_escrita(self, tmp_path: Path) -> None:
        _make_rascunho(tmp_path, "ctx1", "v1")
        deltas = [
            {"tipo": "preco_insumo", "insumo_id": "A"},
            {"tipo": "preco_insumo", "insumo_id": "B"},
            {"tipo": "preco_insumo", "insumo_id": "C"},
        ]

        result = mod._append_deltas_to_rascunho(tmp_path, "ctx1", "v1", deltas)
        assert result is None

        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        assert len(rascunho_data["_deltas"]) == 3
        assert [d["insumo_id"] for d in rascunho_data["_deltas"]] == ["A", "B", "C"]

    def test_preserva_deltas_ja_existentes_no_rascunho(self, tmp_path: Path) -> None:
        _make_rascunho(tmp_path, "ctx1", "v1")
        mod._append_delta_to_rascunho(tmp_path, "ctx1", "v1", {"tipo": "preco_insumo", "insumo_id": "PRE"})

        result = mod._append_deltas_to_rascunho(tmp_path, "ctx1", "v1", [{"tipo": "preco_insumo", "insumo_id": "A"}])
        assert result is None

        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        assert [d["insumo_id"] for d in rascunho_data["_deltas"]] == ["PRE", "A"]

    def test_rascunho_inexistente_returns_erro(self, tmp_path: Path) -> None:
        result = mod._append_deltas_to_rascunho(tmp_path, "ctx1", "v-nao-existe", [{"tipo": "preco_insumo"}])
        assert result is not None
        assert "não encontrado" in result

    def test_rascunho_em_estado_terminal_returns_erro(self, tmp_path: Path) -> None:
        _make_rascunho(tmp_path, "ctx1", "v1", {"version": "v1", "_aprovado": True})
        result = mod._append_deltas_to_rascunho(tmp_path, "ctx1", "v1", [{"tipo": "preco_insumo"}])
        assert result is not None
        assert "terminal" in result

    def test_read_failure_returns_erro(self, tmp_path: Path) -> None:
        versions_dir = tmp_path / "contextos" / "ctx1" / "versions"
        versions_dir.mkdir(parents=True)
        (versions_dir / "v1.json").write_text("NOT_VALID_JSON{", encoding="utf-8")

        result = mod._append_deltas_to_rascunho(tmp_path, "ctx1", "v1", [{"tipo": "preco_insumo"}])
        assert result is not None
        assert "Falha ao ler rascunho" in result

    def test_write_failure_returns_erro(self, tmp_path: Path) -> None:
        _make_rascunho(tmp_path, "ctx1", "v1")

        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            result = mod._append_deltas_to_rascunho(tmp_path, "ctx1", "v1", [{"tipo": "preco_insumo"}])
        assert result is not None
        assert "Falha ao gravar delta no rascunho" in result

    def test_lista_vazia_nao_altera_rascunho(self, tmp_path: Path) -> None:
        _make_rascunho(tmp_path, "ctx1", "v1")
        result = mod._append_deltas_to_rascunho(tmp_path, "ctx1", "v1", [])
        assert result is None
        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        assert rascunho_data.get("_deltas", []) == []


# ---------------------------------------------------------------------------
# _apply_variante_producao_delta (direct — applied only at merge time from
# catalogo.py's aprovar_merge_catalogo)
# ---------------------------------------------------------------------------


class TestApplyVarianteProducaoDelta:
    def test_variantes_key_absent_is_initialized(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # line 435 — "variantes" not in data → initialized to []
        prod_file = tmp_path / "prod.json"
        prod_file.write_text(json.dumps({"id": "PROD-001"}), encoding="utf-8")
        monkeypatch.setattr(mod, "validate_and_resolve_producao_file", lambda _cr, _pid, _vh: prod_file)

        mod._apply_variante_producao_delta(
            tmp_path,
            "PROD-001",
            "V-NEW",
            "Nova Variante",
            123.0,
            {"funcoes": []},
        )

        data = json.loads(prod_file.read_text(encoding="utf-8"))
        assert data["variantes"] == [
            {"id": "V-NEW", "nome": "Nova Variante", "valor_horario": 123.0, "equipe": {"funcoes": []}}
        ]


# ---------------------------------------------------------------------------
# _impl_atualizar_composicao_item_cpu — governança de composicao_itens
# ---------------------------------------------------------------------------


def _seed_cpu(catalog_root: Path, cpu_id: str, composicao_itens: list[dict] | None = None) -> Path:
    cpus_dir = catalog_root / "cpus"
    cpus_dir.mkdir(parents=True, exist_ok=True)
    cpu_file = cpus_dir / f"{cpu_id}.json"
    cpu_file.write_text(json.dumps({"codigo": cpu_id, "composicao_itens": composicao_itens or []}), encoding="utf-8")
    return cpu_file


def _seed_insumo(catalog_root: Path, insumo_id: str, tipo: str = "MATERIAL") -> Path:
    insumos_dir = catalog_root / "insumos" / tipo.lower()
    insumos_dir.mkdir(parents=True, exist_ok=True)
    insumo_file = insumos_dir / f"{insumo_id}.json"
    insumo_file.write_text(json.dumps({"codigo": insumo_id, "tipo": tipo}), encoding="utf-8")
    return insumo_file


class TestImplAtualizarComposicaoItemCpu:
    def _setup(self, monkeypatch: pytest.MonkeyPatch, rt: MagicMock, tmp_path: Path) -> None:
        monkeypatch.setattr(mod, "_runtime", lambda: rt)
        monkeypatch.setattr(mod, "_config_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "_wrap_response", _passthrough)

    def test_sem_rascunho_id_retorna_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_atualizar_composicao_item_cpu(
            "ctx1", "CPU-001", "adicionar", "MA-001", "", coeficiente=1.0, categoria_custo="MATERIAL"
        )
        assert "erro" in result
        assert "rascunho_id" in result["erro"]

    def test_acao_invalida_retorna_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_atualizar_composicao_item_cpu("ctx1", "CPU-001", "excluir", "MA-001", "v1")
        assert "erro" in result
        assert "acao" in result["erro"]

    def test_adicionar_sem_coeficiente_retorna_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)

        result = _impl_atualizar_composicao_item_cpu(
            "ctx1", "CPU-001", "adicionar", "MA-001", "v1", categoria_custo="MATERIAL"
        )
        assert "erro" in result
        assert "coeficiente" in result["erro"]

    def test_cpu_inexistente_retorna_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        catalog_root = tmp_path / "catalogos" / "cat1"
        catalog_root.mkdir(parents=True)
        _make_rascunho(tmp_path, "ctx1", "v1")

        result = _impl_atualizar_composicao_item_cpu(
            "ctx1", "CPU-NAO-EXISTE", "adicionar", "MA-001", "v1", coeficiente=1.0, categoria_custo="MATERIAL"
        )
        assert "erro" in result
        assert "não encontrada" in result["erro"]

    def test_insumo_inexistente_retorna_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        catalog_root = tmp_path / "catalogos" / "cat1"
        _seed_cpu(catalog_root, "CPU-001")
        _make_rascunho(tmp_path, "ctx1", "v1")

        result = _impl_atualizar_composicao_item_cpu(
            "ctx1", "CPU-001", "adicionar", "MA-NAO-EXISTE", "v1", coeficiente=1.0, categoria_custo="MATERIAL"
        )
        assert "erro" in result
        assert "não encontrado" in result["erro"]

    def test_adicionar_item_ja_existente_retorna_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        catalog_root = tmp_path / "catalogos" / "cat1"
        _seed_cpu(catalog_root, "CPU-001", [{"insumo_id": "MA-001", "coeficiente": 0.5, "categoria_custo": "MATERIAL"}])
        _seed_insumo(catalog_root, "MA-001")
        _make_rascunho(tmp_path, "ctx1", "v1")

        result = _impl_atualizar_composicao_item_cpu(
            "ctx1", "CPU-001", "adicionar", "MA-001", "v1", coeficiente=1.0, categoria_custo="MATERIAL"
        )
        assert "erro" in result
        assert "já está na composição" in result["erro"]

    def test_atualizar_item_inexistente_retorna_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        catalog_root = tmp_path / "catalogos" / "cat1"
        _seed_cpu(catalog_root, "CPU-001")
        _seed_insumo(catalog_root, "MA-001")
        _make_rascunho(tmp_path, "ctx1", "v1")

        result = _impl_atualizar_composicao_item_cpu(
            "ctx1", "CPU-001", "atualizar", "MA-001", "v1", coeficiente=1.0, categoria_custo="MATERIAL"
        )
        assert "erro" in result
        assert "não encontrado" in result["erro"]

    def test_remover_item_inexistente_retorna_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        catalog_root = tmp_path / "catalogos" / "cat1"
        _seed_cpu(catalog_root, "CPU-001")
        _make_rascunho(tmp_path, "ctx1", "v1")

        result = _impl_atualizar_composicao_item_cpu("ctx1", "CPU-001", "remover", "MA-001", "v1")
        assert "erro" in result
        assert "não encontrado" in result["erro"]

    def test_categoria_custo_invalida_retorna_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # categoria_custo fora do Literal aceito por ComposicaoItem
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        catalog_root = tmp_path / "catalogos" / "cat1"
        _seed_cpu(catalog_root, "CPU-001")
        _seed_insumo(catalog_root, "MA-001")
        _make_rascunho(tmp_path, "ctx1", "v1")

        result = _impl_atualizar_composicao_item_cpu(
            "ctx1", "CPU-001", "adicionar", "MA-001", "v1", coeficiente=1.0, categoria_custo="INEXISTENTE"
        )
        assert "erro" in result
        assert "inválido" in result["erro"]

    def test_coeficiente_negativo_retorna_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # coeficiente deve ser > 0 (ComposicaoItem.coeficiente = Field(gt=0))
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        catalog_root = tmp_path / "catalogos" / "cat1"
        _seed_cpu(catalog_root, "CPU-001")
        _seed_insumo(catalog_root, "MA-001")
        _make_rascunho(tmp_path, "ctx1", "v1")

        result = _impl_atualizar_composicao_item_cpu(
            "ctx1", "CPU-001", "adicionar", "MA-001", "v1", coeficiente=-1.0, categoria_custo="MATERIAL"
        )
        assert "erro" in result
        assert "inválido" in result["erro"]

    def test_adicionar_happy_path_grava_delta_sem_tocar_master(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        catalog_root = tmp_path / "catalogos" / "cat1"
        cpu_file = _seed_cpu(catalog_root, "CPU-001")
        _seed_insumo(catalog_root, "MA-001")
        _make_rascunho(tmp_path, "ctx1", "v1")

        result = _impl_atualizar_composicao_item_cpu(
            "ctx1",
            "CPU-001",
            "adicionar",
            "MA-001",
            "v1",
            coeficiente=0.42,
            categoria_custo="MATERIAL",
            unidade="L",
            nota="corrige derivação de combustível",
        )
        assert result["status"] == "RASCUNHO"
        assert result["layer"] == "MASTER"
        assert result["cpu_id"] == "CPU-001"
        assert result["insumo_id"] == "MA-001"
        assert result["acao"] == "adicionar"

        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        assert len(rascunho_data["_deltas"]) == 1
        delta = rascunho_data["_deltas"][0]
        assert delta["tipo"] == "composicao_item"
        assert delta["cpu_id"] == "CPU-001"
        assert delta["insumo_id"] == "MA-001"
        assert delta["acao"] == "adicionar"
        assert delta["coeficiente"] == 0.42
        assert delta["categoria_custo"] == "MATERIAL"
        assert delta["unidade"] == "L"
        assert delta["nota"] == "corrige derivação de combustível"

        # o catálogo mestre (arquivo da CPU) permanece intocado até o merge
        cpu_data = json.loads(cpu_file.read_text(encoding="utf-8"))
        assert cpu_data["composicao_itens"] == []

    def test_remover_happy_path_grava_delta(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        catalog_root = tmp_path / "catalogos" / "cat1"
        _seed_cpu(
            catalog_root,
            "CPU-001",
            [{"insumo_id": "MA-DIESEL-S10", "coeficiente": 0.4181, "categoria_custo": "DIESEL"}],
        )
        _make_rascunho(tmp_path, "ctx1", "v1")

        result = _impl_atualizar_composicao_item_cpu(
            "ctx1", "CPU-001", "remover", "MA-DIESEL-S10", "v1", nota="combustível deriva do equipamento"
        )
        assert result["status"] == "RASCUNHO"
        assert result["acao"] == "remover"

        rascunho_data = json.loads((tmp_path / "contextos" / "ctx1" / "versions" / "v1.json").read_text())
        delta = rascunho_data["_deltas"][0]
        assert delta["acao"] == "remover"
        assert delta["coeficiente"] is None
        assert delta["categoria_custo"] is None

    def test_listar_retorna_composicao_sem_exigir_insumo_id_ou_rascunho_id(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Regressão: acao='listar' não existia — usuário tentou usá-la pra consultar
        a composição atual de uma CPU e recebeu hang (issue de tool sem deadline,
        não desta função). Leitura pura: não grava delta, não exige rascunho_id."""
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        catalog_root = tmp_path / "catalogos" / "cat1"
        composicao = [{"insumo_id": "MA-001", "coeficiente": 0.5, "categoria_custo": "MATERIAL"}]
        _seed_cpu(catalog_root, "CPU-001", composicao)

        result = _impl_atualizar_composicao_item_cpu("ctx1", "CPU-001", "listar")

        assert result["cpu_id"] == "CPU-001"
        assert result["composicao_itens"] == composicao

    def test_listar_cpu_inexistente_retorna_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        rt = _make_rt("ctx1", "cat1")
        self._setup(monkeypatch, rt, tmp_path)
        catalog_root = tmp_path / "catalogos" / "cat1"
        catalog_root.mkdir(parents=True)

        result = _impl_atualizar_composicao_item_cpu("ctx1", "CPU-NAO-EXISTE", "listar")

        assert "erro" in result
        assert "não encontrada" in result["erro"]


# ---------------------------------------------------------------------------
# _apply_composicao_item_delta — aplicação no merge
# ---------------------------------------------------------------------------


class TestApplyComposicaoItemDelta:
    def test_adicionar_grava_item_na_cpu_master(self, tmp_path: Path) -> None:
        catalog_root = tmp_path / "cat1"
        _seed_cpu(catalog_root, "CPU-001")

        mod._apply_composicao_item_delta(catalog_root, "CPU-001", "MA-001", "adicionar", 0.42, "MATERIAL", "L", None)

        cpu_data = json.loads((catalog_root / "cpus" / "CPU-001.json").read_text(encoding="utf-8"))
        assert cpu_data["composicao_itens"] == [
            {
                "insumo_id": "MA-001",
                "coeficiente": 0.42,
                "categoria_custo": "MATERIAL",
                "unidade": "L",
                "tipo_combustivel": None,
            }
        ]

    def test_atualizar_substitui_item_existente_sem_duplicar(self, tmp_path: Path) -> None:
        catalog_root = tmp_path / "cat1"
        _seed_cpu(
            catalog_root,
            "CPU-001",
            [
                {"insumo_id": "MA-001", "coeficiente": 0.1, "categoria_custo": "MATERIAL"},
                {"insumo_id": "MA-002", "coeficiente": 0.2, "categoria_custo": "MATERIAL"},
            ],
        )

        mod._apply_composicao_item_delta(catalog_root, "CPU-001", "MA-001", "atualizar", 0.99, "MATERIAL", None, None)

        cpu_data = json.loads((catalog_root / "cpus" / "CPU-001.json").read_text(encoding="utf-8"))
        assert len(cpu_data["composicao_itens"]) == 2
        item = next(it for it in cpu_data["composicao_itens"] if it["insumo_id"] == "MA-001")
        assert item["coeficiente"] == 0.99
        outro = next(it for it in cpu_data["composicao_itens"] if it["insumo_id"] == "MA-002")
        assert outro["coeficiente"] == 0.2

    def test_remover_descarta_item_correspondente(self, tmp_path: Path) -> None:
        catalog_root = tmp_path / "cat1"
        _seed_cpu(
            catalog_root,
            "CPU-001",
            [
                {"insumo_id": "MA-DIESEL-S10", "coeficiente": 0.4181, "categoria_custo": "DIESEL"},
                {"insumo_id": "MA-002", "coeficiente": 0.2, "categoria_custo": "MATERIAL"},
            ],
        )

        mod._apply_composicao_item_delta(catalog_root, "CPU-001", "MA-DIESEL-S10", "remover", None, None, None, None)

        cpu_data = json.loads((catalog_root / "cpus" / "CPU-001.json").read_text(encoding="utf-8"))
        assert cpu_data["composicao_itens"] == [
            {"insumo_id": "MA-002", "coeficiente": 0.2, "categoria_custo": "MATERIAL"}
        ]

    def test_cpu_inexistente_levanta_erro_governanca(self, tmp_path: Path) -> None:
        from concilium.application.orchestrators.catalog_governance import CatalogGovernanceError

        catalog_root = tmp_path / "cat1"
        catalog_root.mkdir(parents=True)

        with pytest.raises(CatalogGovernanceError):
            mod._apply_composicao_item_delta(
                catalog_root, "CPU-NAO-EXISTE", "MA-001", "adicionar", 1.0, "MATERIAL", None, None
            )

    def test_adicionar_sem_coeficiente_ou_categoria_levanta_erro(self, tmp_path: Path) -> None:
        # narrowing defensivo — nunca deve ser alcançado via _impl (já valida antes),
        # mas _apply_composicao_item_delta não deve persistir um item incompleto.
        from concilium.application.orchestrators.catalog_governance import CatalogGovernanceError

        catalog_root = tmp_path / "cat1"
        _seed_cpu(catalog_root, "CPU-001")

        with pytest.raises(CatalogGovernanceError):
            mod._apply_composicao_item_delta(
                catalog_root, "CPU-001", "MA-001", "adicionar", None, "MATERIAL", None, None
            )
