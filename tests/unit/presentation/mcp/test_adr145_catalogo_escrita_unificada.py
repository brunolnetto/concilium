"""Tests for ADR-145 — unificação do caminho de escrita de preço no catálogo mestre.

Cobre o fluxo completo do merge: delta acumulado no rascunho (D1) -> aplicação
via RepositorioInsumo.atualizar_preco/variante de produção (D2) -> geração de
CatalogSnapshot/CatalogDiff com justificativa persistida (D3) -> nota
append-only por alteração (D4).
"""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

_CATALOGO_MOD = "concilium.presentation.mcp.tools.catalogo"


def _register_tools(monkeypatch, tmp_path: Path) -> dict:
    import importlib

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(config_dir))

    mod = importlib.import_module(_CATALOGO_MOD)
    server = FastMCP("test-cat-adr145")
    mod.register(server)

    tools: dict = {}
    for t in server._tool_manager.list_tools():
        fn = getattr(t, "fn", None) or getattr(t, "func", None)
        tools[t.name] = fn
    return tools


def _seed_contexto_e_catalogo(config_dir: Path, contexto_id: str, catalogo_id: str) -> None:
    (config_dir / "contextos").mkdir(parents=True, exist_ok=True)
    (config_dir / "contextos" / f"{contexto_id}.json").write_text(
        json.dumps(
            {
                "id": contexto_id,
                "perfil_id": "default",
                "jurisdicao_id": "BR",
                "referencia_id": "SICRO",
                "catalogo_id": catalogo_id,
            }
        ),
        encoding="utf-8",
    )
    cat_dir = config_dir / "catalogos" / catalogo_id
    (cat_dir / "insumos" / "material").mkdir(parents=True, exist_ok=True)
    (cat_dir / "insumos" / "material" / "MAT-001.json").write_text(
        json.dumps({"codigo": "MAT-001", "tipo": "MATERIAL", "descricao": "Cimento", "preco_unitario": 30.0}),
        encoding="utf-8",
    )
    (cat_dir / "producoes").mkdir(parents=True, exist_ok=True)
    (cat_dir / "producoes" / "PROD-001.json").write_text(
        json.dumps({"id": "PROD-001", "variantes": []}), encoding="utf-8"
    )
    (cat_dir / "cpus").mkdir(parents=True, exist_ok=True)
    (cat_dir / "cpus" / "CPU-001.json").write_text(
        json.dumps(
            {
                "codigo": "CPU-001",
                "composicao_itens": [{"insumo_id": "MAT-001", "coeficiente": 0.5, "categoria_custo": "MATERIAL"}],
            }
        ),
        encoding="utf-8",
    )
    return cat_dir


def _criar_rascunho_com_deltas(config_dir: Path, contexto_id: str, rascunho_id: str, deltas: list[dict]) -> None:
    versions_dir = config_dir / "contextos" / contexto_id / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    (versions_dir / f"{rascunho_id}.json").write_text(
        json.dumps(
            {
                "version": rascunho_id,
                "_revisado": True,
                "created_by": "criador@co.com",
                "_deltas": deltas,
            }
        ),
        encoding="utf-8",
    )


class TestConsultarImpactoReajusteLeDeltasReais:
    """ADR-145 P11 — n_insumos_afetados deriva de _deltas, não da chave inexistente 'modificados'."""

    def test_n_insumos_afetados_bate_com_numero_de_deltas_distintos(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        _criar_rascunho_com_deltas(
            config_dir,
            "ctx-1",
            "v2",
            deltas=[
                {"tipo": "preco_insumo", "insumo_id": "MAT-001", "novo_preco": 35.0},
                {"tipo": "preco_insumo", "insumo_id": "MAT-002", "novo_preco": 12.0},
                # mesma insumo alterada duas vezes no mesmo rascunho — não deve duplicar a contagem
                {"tipo": "preco_insumo", "insumo_id": "MAT-001", "novo_preco": 36.0},
                {"tipo": "variante_producao", "producao_id": "PROD-001", "variante_id": "V1"},
            ],
        )

        result = tools["consultar_impacto_reajuste"](contexto_id="ctx-1", rascunho_id="v2")
        assert result["n_insumos_afetados"] == 2
        assert set(result["insumos_modificados"]) == {"MAT-001", "MAT-002"}


class TestAprovarMergeCatalogoAplicaDeltas:
    def test_merge_aplica_deltas_preco_base_regional_e_variante(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        _criar_rascunho_com_deltas(
            config_dir,
            "ctx-1",
            "v2",
            deltas=[
                {
                    "tipo": "preco_insumo",
                    "insumo_id": "MAT-001",
                    "novo_preco": 35.0,
                    "jurisdicao_id": None,
                    "nota": "reajuste INCC",
                    "autor": "criador@co.com",
                    "timestamp": "2026-01-01T00:00:00Z",
                },
                {
                    "tipo": "preco_insumo",
                    "insumo_id": "MAT-001",
                    "novo_preco": 40.0,
                    "jurisdicao_id": "SP",
                    "nota": "cotação SP",
                    "autor": "criador@co.com",
                    "timestamp": "2026-01-01T00:00:00Z",
                },
                {
                    "tipo": "variante_producao",
                    "producao_id": "PROD-001",
                    "variante_id": "V1",
                    "nome_variante": "Equipe extra",
                    "valor_horario": 55.0,
                    "equipe": {"funcoes": []},
                    "autor": "criador@co.com",
                    "timestamp": "2026-01-01T00:00:00Z",
                },
            ],
        )

        from unittest.mock import patch

        with patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"):
            result = tools["aprovar_merge_catalogo"](
                contexto_id="ctx-1", rascunho_id="v2", justificativa="Reajuste aprovado pela diretoria"
            )

        assert result["status"] == "APROVADO"
        assert result["deltas_aplicados"] == 3
        assert result["snapshot_id"]
        assert result["justificativa"] == "Reajuste aprovado pela diretoria"

        # D2 — preço base via RepositorioInsumo.atualizar_preco (SCD2 real)
        insumo_data = json.loads(
            (config_dir / "catalogos" / "cat-1" / "insumos" / "material" / "MAT-001.json").read_text()
        )
        assert insumo_data["preco_unitario"] == 35.0
        assert insumo_data["historico_precos"][-1]["preco_unitario"] == 35.0
        assert insumo_data["historico_precos"][-1]["nota"] == "reajuste INCC"
        assert insumo_data["historico_precos"][-1]["fonte"] == "criador@co.com"

        # D2/D4 — preço regional com histórico append-only próprio
        assert insumo_data["regionalizacao"]["SP"]["preco"] == 40.0
        assert insumo_data["regionalizacao"]["SP"]["historico"][-1]["nota"] == "cotação SP"

        # D2 — variante de produção aplicada
        prod_data = json.loads((config_dir / "catalogos" / "cat-1" / "producoes" / "PROD-001.json").read_text())
        assert len(prod_data["variantes"]) == 1
        assert prod_data["variantes"][0]["valor_horario"] == 55.0

        # D3 — CatalogSnapshot persistido, justificativa não é só ecoada na resposta
        snapshots_dir = config_dir / "catalogos" / "cat-1" / "snapshots"
        snapshot_file = snapshots_dir / f"{result['snapshot_id']}.json"
        assert snapshot_file.exists()
        snapshot_data = json.loads(snapshot_file.read_text())
        assert snapshot_data["meta"]["created_by"] == "mgr-1"

        # rascunho marcado como aprovado (estado terminal)
        rascunho_data = json.loads((config_dir / "contextos" / "ctx-1" / "versions" / "v2.json").read_text())
        assert rascunho_data["_aprovado"] is True
        assert rascunho_data["_aprovado_por"] == "mgr-1"

    def test_merge_sem_deltas_nao_gera_snapshot(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        _criar_rascunho_com_deltas(config_dir, "ctx-1", "v2", deltas=[])

        from unittest.mock import patch

        with patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"):
            result = tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")

        assert result["status"] == "APROVADO"
        assert result["deltas_aplicados"] == 0
        assert result["snapshot_id"] is None
        assert not (config_dir / "catalogos" / "cat-1" / "snapshots").exists()

    def test_segundo_merge_gera_diff_contra_snapshot_anterior(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")

        from unittest.mock import patch

        _criar_rascunho_com_deltas(
            config_dir,
            "ctx-1",
            "v2",
            deltas=[
                {
                    "tipo": "preco_insumo",
                    "insumo_id": "MAT-001",
                    "novo_preco": 35.0,
                    "jurisdicao_id": None,
                    "nota": None,
                    "autor": "criador@co.com",
                    "timestamp": "2026-01-01T00:00:00Z",
                }
            ],
        )
        with patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"):
            first = tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="primeiro")
        assert first["snapshot_id"]

        _criar_rascunho_com_deltas(
            config_dir,
            "ctx-1",
            "v3",
            deltas=[
                {
                    "tipo": "preco_insumo",
                    "insumo_id": "MAT-001",
                    "novo_preco": 50.0,
                    "jurisdicao_id": None,
                    "nota": None,
                    "autor": "criador@co.com",
                    "timestamp": "2026-02-01T00:00:00Z",
                }
            ],
        )
        with patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-2"):
            second = tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v3", justificativa="segundo")

        assert second["snapshot_id"] != first["snapshot_id"]
        assert "insumo" in second["diff_summary"]

        diffs_dir = config_dir / "catalogos" / "cat-1" / "snapshots" / "diffs"
        assert diffs_dir.exists()
        diff_files = list(diffs_dir.glob("*.json"))
        assert len(diff_files) == 1
        diff_record = json.loads(diff_files[0].read_text())
        assert diff_record["justificativa"] == "segundo"
        assert diff_record["rascunho_id"] == "v3"
        assert diff_record["aprovador"] == "mgr-2"
        assert diff_record["diff"]["previous_snapshot_id"] == first["snapshot_id"]
        assert diff_record["diff"]["current_snapshot_id"] == second["snapshot_id"]


class TestConsultarImpactoReajusteSurfaceComposicaoItem:
    """composicao_item afeta a estrutura de custo de uma CPU — visibilidade própria
    pro revisor dos 4-olhos, análoga a insumos_modificados (mas por cpu_id)."""

    def test_cpus_com_composicao_alterada_deriva_de_deltas_composicao_item(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        _criar_rascunho_com_deltas(
            config_dir,
            "ctx-1",
            "v2",
            deltas=[
                {
                    "tipo": "composicao_item",
                    "cpu_id": "CPU-001",
                    "insumo_id": "MA-DIESEL-S10",
                    "acao": "remover",
                    "coeficiente": None,
                    "categoria_custo": None,
                    "unidade": None,
                    "tipo_combustivel": None,
                },
                # mesma CPU alterada duas vezes no mesmo rascunho — não deve duplicar a contagem
                {
                    "tipo": "composicao_item",
                    "cpu_id": "CPU-001",
                    "insumo_id": "MAT-001",
                    "acao": "atualizar",
                    "coeficiente": 0.7,
                    "categoria_custo": "MATERIAL",
                    "unidade": None,
                    "tipo_combustivel": None,
                },
                {"tipo": "preco_insumo", "insumo_id": "MAT-002", "novo_preco": 12.0},
            ],
        )

        result = tools["consultar_impacto_reajuste"](contexto_id="ctx-1", rascunho_id="v2")
        assert result["n_cpus_com_composicao_alterada"] == 1
        assert result["cpus_com_composicao_alterada"] == ["CPU-001"]
        # não interfere na contagem de insumos_afetados (preco_insumo, já coberta acima)
        assert result["n_insumos_afetados"] == 1


class TestAprovarMergeCatalogoAplicaDeltaComposicaoItem:
    def test_merge_aplica_delta_composicao_item_remocao_e_upsert(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        cpu_dir = config_dir / "catalogos" / "cat-1" / "cpus"
        # CPU-001 já semeada com composicao_itens=[MAT-001 @ 0.5]; adiciona um item
        # DIESEL derivado incorretamente (mesmo caso real que motivou esta feature).
        cpu_data = json.loads((cpu_dir / "CPU-001.json").read_text())
        cpu_data["composicao_itens"].append(
            {"insumo_id": "MA-DIESEL-S10", "coeficiente": 0.4181, "categoria_custo": "DIESEL"}
        )
        (cpu_dir / "CPU-001.json").write_text(json.dumps(cpu_data), encoding="utf-8")
        (config_dir / "catalogos" / "cat-1" / "insumos" / "material" / "MA-DIESEL-S10.json").write_text(
            json.dumps({"codigo": "MA-DIESEL-S10", "tipo": "COMBUSTIVEL"}), encoding="utf-8"
        )

        _criar_rascunho_com_deltas(
            config_dir,
            "ctx-1",
            "v2",
            deltas=[
                {
                    "tipo": "composicao_item",
                    "cpu_id": "CPU-001",
                    "insumo_id": "MA-DIESEL-S10",
                    "acao": "remover",
                    "coeficiente": None,
                    "categoria_custo": None,
                    "unidade": None,
                    "tipo_combustivel": None,
                },
                {
                    "tipo": "composicao_item",
                    "cpu_id": "CPU-001",
                    "insumo_id": "MAT-001",
                    "acao": "atualizar",
                    "coeficiente": 0.65,
                    "categoria_custo": "MATERIAL",
                    "unidade": None,
                    "tipo_combustivel": None,
                },
            ],
        )

        from unittest.mock import patch

        with patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"):
            result = tools["aprovar_merge_catalogo"](
                contexto_id="ctx-1", rascunho_id="v2", justificativa="Combustível deriva do equipamento, não da CPU"
            )

        assert result["status"] == "APROVADO"
        assert result["deltas_aplicados"] == 2

        cpu_data_pos = json.loads((cpu_dir / "CPU-001.json").read_text())
        itens = cpu_data_pos["composicao_itens"]
        assert {it["insumo_id"] for it in itens} == {"MAT-001"}
        assert itens[0]["coeficiente"] == 0.65
