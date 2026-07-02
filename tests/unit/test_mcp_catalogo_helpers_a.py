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
    _impl_atualizar_preco_insumo,
    _impl_consultar_preco_insumo_temporal,
    _impl_consultar_saude_catalogo,
    _impl_listar_contextos,
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

        result = _impl_atualizar_preco_insumo("ctx1", "INS-001", 100.0)
        assert "erro" in result
        assert "bad insumo" in result["erro"]

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
        overrides_file = proj_dir / "overrides" / "catalog_prices.json"
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
        (overrides_dir / "catalog_prices.json").write_text(json.dumps(existing), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir)

        result = _impl_atualizar_preco_insumo("ctx1", "INS-002", 99.0, projeto_id="PROJ-001")
        assert result["status"] == "SUCESSO"
        saved = json.loads((overrides_dir / "catalog_prices.json").read_text(encoding="utf-8"))
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
        saved = json.loads((proj_dir / "overrides" / "catalog_prices.json").read_text(encoding="utf-8"))
        assert "INS-001::CE" in saved

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

    def test_master_no_jurisdicao_writes_preco_unitario(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 204-216 — master layer, no jurisdicao_id
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        insumo_file = tmp_path / "ins.json"
        insumo_file.write_text(json.dumps({"preco_unitario": 5.0}), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir, insumo_file=insumo_file)

        result = _impl_atualizar_preco_insumo("ctx1", "INS-001", 42.0)
        assert result["status"] == "SUCESSO"
        assert result["layer"] == "MASTER"
        data = json.loads(insumo_file.read_text(encoding="utf-8"))
        assert data["preco_unitario"] == 42.0

    def test_master_with_jurisdicao_writes_regionalizacao(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # lines 206-209 — master layer with jurisdicao_id
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        insumo_file = tmp_path / "ins.json"
        insumo_file.write_text(json.dumps({"preco_unitario": 5.0}), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir, insumo_file=insumo_file)

        result = _impl_atualizar_preco_insumo("ctx1", "INS-001", 77.0, jurisdicao_id="SP")
        assert result["status"] == "SUCESSO"
        data = json.loads(insumo_file.read_text(encoding="utf-8"))
        assert "SP" in data.get("regionalizacao", {})
        assert data["regionalizacao"]["SP"]["preco"] == 77.0

    def test_master_with_nota_writes_nota_calibracao(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # line 212-213 — nota present
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)
        insumo_file = tmp_path / "ins.json"
        insumo_file.write_text(json.dumps({"preco_unitario": 1.0}), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir, insumo_file=insumo_file)

        _impl_atualizar_preco_insumo("ctx1", "INS-001", 99.0, nota="revisao 2025")
        data = json.loads(insumo_file.read_text(encoding="utf-8"))
        assert data.get("nota_calibracao") == "revisao 2025"

    def test_master_write_exception_returns_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 217-218 — exception → {"erro": "Falha ao persistir no mestre: ..."}
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)

        # insumo_file points to a non-readable/writable place
        bad_insumo = MagicMock()
        bad_insumo.read_text.side_effect = OSError("cannot read")

        monkeypatch.setattr(mod, "_runtime", lambda: rt)
        monkeypatch.setattr(mod, "_config_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "_projetos_root", lambda: projects_dir)
        monkeypatch.setattr(mod, "_wrap_response", _passthrough)
        monkeypatch.setattr(mod, "validate_and_resolve_insumo_file", lambda _cr, _iid, _np: bad_insumo)

        result = _impl_atualizar_preco_insumo("ctx1", "INS-001", 10.0)
        assert "erro" in result
        assert "Falha ao persistir no mestre" in result["erro"]


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
        # lines 324-336 — new overrides file created
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
        overrides_file = proj_dir / "overrides" / "production_variants.json"
        assert overrides_file.exists()
        saved = json.loads(overrides_file.read_text(encoding="utf-8"))
        assert "PROD-001::V1" in saved
        assert saved["PROD-001::V1"]["valor_horario"] == 150.0

    def test_projeto_merges_existing_overrides(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 327-333 — existing overrides merged
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        proj_dir = projects_dir / "PROJ-001"
        overrides_dir = proj_dir / "overrides"
        overrides_dir.mkdir(parents=True)
        existing = {"OTHER::V0": {"nome": "old", "valor_horario": 50.0, "equipe": {}}}
        (overrides_dir / "production_variants.json").write_text(json.dumps(existing), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir)

        equipe = json.dumps({"funcoes": []})
        result = _impl_adicionar_variante_producao(
            "ctx1", "PROD-001", "V2", "Nova Variante", 200.0, equipe, projeto_id="PROJ-001"
        )
        assert result["status"] == "SUCESSO"
        saved = json.loads((overrides_dir / "production_variants.json").read_text(encoding="utf-8"))
        assert "OTHER::V0" in saved
        assert "PROD-001::V2" in saved

    def test_master_governance_error_returns_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 340-347 — CatalogGovernanceError on master branch
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
        result = _impl_adicionar_variante_producao("ctx1", "PROD-001", "V1", "V1", 100.0, equipe)
        assert "erro" in result
        assert "invalid producao" in result["erro"]

    def test_master_adds_variante_when_variantes_absent(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 349-357 — "variantes" key absent → list created and appended
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)

        prod_file = tmp_path / "prod.json"
        prod_data = {"id": "PROD-001"}  # no "variantes" key
        prod_file.write_text(json.dumps(prod_data), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir, prod_file=prod_file)

        equipe = json.dumps({"funcoes": [{"funcao_id": "MO-001"}]})
        result = _impl_adicionar_variante_producao("ctx1", "PROD-001", "V-NEW", "Nova", 88.0, equipe)
        assert result["status"] == "SUCESSO"
        assert result["layer"] == "MASTER"
        data = json.loads(prod_file.read_text(encoding="utf-8"))
        assert len(data["variantes"]) == 1
        assert data["variantes"][0]["id"] == "V-NEW"

    def test_master_replaces_existing_variante_id(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # line 352 — existing variante_id filtered out and new appended
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)

        prod_file = tmp_path / "prod.json"
        prod_data = {
            "id": "PROD-001",
            "variantes": [
                {"id": "V1", "nome": "old", "valor_horario": 50.0, "equipe": {}},
                {"id": "V2", "nome": "keep", "valor_horario": 70.0, "equipe": {}},
            ],
        }
        prod_file.write_text(json.dumps(prod_data), encoding="utf-8")
        self._setup(monkeypatch, rt, tmp_path, projects_dir, prod_file=prod_file)

        equipe = json.dumps({"funcoes": []})
        result = _impl_adicionar_variante_producao("ctx1", "PROD-001", "V1", "updated", 999.0, equipe)
        assert result["status"] == "SUCESSO"
        data = json.loads(prod_file.read_text(encoding="utf-8"))
        ids = [v["id"] for v in data["variantes"]]
        assert ids.count("V1") == 1  # old removed, new appended
        assert "V2" in ids
        updated = next(v for v in data["variantes"] if v["id"] == "V1")
        assert updated["valor_horario"] == 999.0

    def test_master_write_failure_returns_erro(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # lines 356+359 — write_text fails → outer except → {"erro": ...}
        rt = _make_rt("ctx1", "cat1")
        projects_dir = tmp_path / "projetos"
        projects_dir.mkdir(parents=True)

        bad_prod = MagicMock()
        bad_prod.read_text.return_value = json.dumps({"id": "PROD-001", "variantes": []})
        bad_prod.write_text.side_effect = OSError("no space")

        monkeypatch.setattr(mod, "_runtime", lambda: rt)
        monkeypatch.setattr(mod, "_config_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "_projetos_root", lambda: projects_dir)
        monkeypatch.setattr(mod, "_wrap_response", _passthrough)
        monkeypatch.setattr(mod, "validate_and_resolve_producao_file", lambda _cr, _pid, _vh: bad_prod)

        equipe = json.dumps({"funcoes": []})
        result = _impl_adicionar_variante_producao("ctx1", "PROD-001", "V1", "V1", 100.0, equipe)
        assert "erro" in result
        assert "Erro ao adicionar variante" in result["erro"]
