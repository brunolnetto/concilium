"""Tests for ADR-150 — extensão do escopo de promoção gated para CPU.

Cobre a extensão de `promover_override_projeto` para também processar
`cpus_override.json` (produtividade/composição calibrada de projeto), sob o
mesmo rascunho e o mesmo gate dual (ownership + quatro-olhos) já usado para
`insumos_override.json` (ver test_adr150_promover_override_projeto.py).

Também documenta, via teste, a decisão de NÃO cobrir `bdi_override.json`:
investigação desta extensão constatou que esse arquivo não tem nenhum leitor
no pipeline real nem gravador fora da inicialização vazia em
`create_project` — a governança de BDI por projeto já existe, mas por um
mecanismo totalmente diferente (`PerfilBdiProjeto`/`bdi-update`), sem conceito
de "promoção ao catálogo master" (ver ADR-150, seção Achados).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from mcp.server.fastmcp import FastMCP

_CATALOGO_MOD = "concilium.presentation.mcp.tools.catalogo"


def _register_tools(monkeypatch, tmp_path: Path) -> dict:
    import importlib

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    projects_dir = tmp_path / "projetos"
    projects_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(config_dir))
    monkeypatch.setenv("CONCILIUM__PROJECTS_ROOT", str(projects_dir))

    mod = importlib.import_module(_CATALOGO_MOD)
    importlib.reload(mod)
    server = FastMCP("test-cat-adr150-cpu")
    mod.register(server)

    tools: dict = {}
    for t in server._tool_manager.list_tools():
        fn = getattr(t, "fn", None) or getattr(t, "func", None)
        tools[t.name] = fn
    return tools


def _seed_contexto_e_catalogo(config_dir: Path, contexto_id: str, catalogo_id: str) -> Path:
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
    (cat_dir / "cpus").mkdir(parents=True, exist_ok=True)
    (cat_dir / "cpus" / "CPU-001.json").write_text(
        json.dumps(
            {
                "codigo": "CPU-001",
                "descricao": "Escavação manual",
                "unidade": "m3",
                "categoria": "TERRAPLENAGEM",
                "composicao_itens": [],
                "producao_id_ref": "CPU-001-PROD-001",
                "producao_horaria": 2.0,
            }
        ),
        encoding="utf-8",
    )
    return cat_dir


def _seed_projeto(
    projects_dir: Path,
    projeto_id: str,
    *,
    owner_id: str | None,
    contexto_id: str | None = None,
    insumo_overrides: dict | None = None,
    cpu_overrides: dict | None = None,
    bdi_override: dict | None = None,
    created_by: str | None = None,
) -> Path:
    proj_dir = projects_dir / projeto_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    meta: dict = {"owner_id": owner_id}
    if contexto_id:
        meta["contexto_id"] = contexto_id
    (proj_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    overrides_dir = proj_dir / "overrides"
    overrides_dir.mkdir(parents=True, exist_ok=True)
    (overrides_dir / "insumos_override.json").write_text(
        json.dumps(insumo_overrides if insumo_overrides is not None else {}),
        encoding="utf-8",
    )
    (overrides_dir / "cpus_override.json").write_text(
        json.dumps(cpu_overrides if cpu_overrides is not None else {}),
        encoding="utf-8",
    )
    if bdi_override is not None:
        (overrides_dir / "bdi_override.json").write_text(json.dumps(bdi_override), encoding="utf-8")
    if created_by:
        (overrides_dir / "_rascunho_estado.json").write_text(
            json.dumps({"_rascunho": True, "created_by": created_by, "projeto_id": projeto_id}),
            encoding="utf-8",
        )
    return proj_dir


def _promote_as(monkeypatch, tools, *, user_id: str, roles: set[str], **kwargs) -> dict:
    with (
        patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}),
        patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value=user_id),
        patch("concilium.infrastructure.auth.permission_guard._current_roles") as mock_roles,
    ):
        mock_roles.get.return_value = frozenset(roles)
        return tools["promover_override_projeto"](**kwargs)


class TestPromoverOverrideProjetoCpu:
    def test_promove_cpu_junto_com_insumo_em_uma_unica_chamada(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        projects_dir = tmp_path / "projetos"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        _seed_projeto(
            projects_dir,
            "PROJ-001",
            owner_id="owner-1",
            contexto_id="ctx-1",
            insumo_overrides={"MAT-001::BASE": {"preco": 55.0, "nota": "cotação X"}},
            cpu_overrides={"CPU-001": {"producao_horaria": 3.5}},
            created_by="eng-1",
        )

        result = _promote_as(
            monkeypatch,
            tools,
            user_id="owner-1",
            roles={"catalog-manager"},
            projeto_id="PROJ-001",
            justificativa="calibração de campo",
        )

        assert result["status"] == "APROVADO"
        assert result["deltas_aplicados"] == 2
        assert result["deltas_insumo"] == 1
        assert result["deltas_cpu"] == 1

        cpu_file = config_dir / "catalogos" / "cat-1" / "cpus" / "CPU-001.json"
        cpu_data = json.loads(cpu_file.read_text(encoding="utf-8"))
        assert cpu_data["producao_horaria"] == 3.5

        insumo_file = config_dir / "catalogos" / "cat-1" / "insumos" / "material" / "MAT-001.json"
        assert json.loads(insumo_file.read_text(encoding="utf-8"))["preco_unitario"] == 55.0

        # Ambos os overrides aplicados são arquivados e os arquivos live ficam vazios.
        overrides_dir = projects_dir / "PROJ-001" / "overrides"
        assert json.loads((overrides_dir / "insumos_override.json").read_text(encoding="utf-8")) == {}
        assert json.loads((overrides_dir / "cpus_override.json").read_text(encoding="utf-8")) == {}
        historico_dir = overrides_dir / "historico"
        historico_files = {p.name for p in historico_dir.glob("*.json")}
        assert any(name.startswith("insumos_override_") for name in historico_files)
        assert any(name.startswith("cpus_override_") for name in historico_files)

    def test_promove_apenas_cpu_sem_insumo_pendente(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        projects_dir = tmp_path / "projetos"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        _seed_projeto(
            projects_dir,
            "PROJ-001",
            owner_id="owner-1",
            contexto_id="ctx-1",
            cpu_overrides={"CPU-001": {"producao_horaria": 4.0}},
            created_by="eng-1",
        )

        result = _promote_as(
            monkeypatch,
            tools,
            user_id="owner-1",
            roles={"catalog-manager"},
            projeto_id="PROJ-001",
            justificativa="só cpu",
        )

        assert result["status"] == "APROVADO"
        assert result["deltas_aplicados"] == 1
        assert result["deltas_insumo"] == 0
        assert result["deltas_cpu"] == 1

        cpu_file = config_dir / "catalogos" / "cat-1" / "cpus" / "CPU-001.json"
        assert json.loads(cpu_file.read_text(encoding="utf-8"))["producao_horaria"] == 4.0

    def test_override_de_cpu_faz_merge_preservando_campos_nao_tocados(self, monkeypatch, tmp_path):
        """Mesma semântica de leitura de ConciliumService.resolve_cpu ({**master, **override})."""
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        projects_dir = tmp_path / "projetos"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        _seed_projeto(
            projects_dir,
            "PROJ-001",
            owner_id="owner-1",
            contexto_id="ctx-1",
            cpu_overrides={"CPU-001": {"producao_horaria": 9.9, "motivo": "aferição de campo"}},
            created_by="eng-1",
        )

        result = _promote_as(
            monkeypatch,
            tools,
            user_id="owner-1",
            roles={"catalog-manager"},
            projeto_id="PROJ-001",
            justificativa="merge",
        )
        assert result["status"] == "APROVADO"

        cpu_file = config_dir / "catalogos" / "cat-1" / "cpus" / "CPU-001.json"
        cpu_data = json.loads(cpu_file.read_text(encoding="utf-8"))
        # Campo sobreposto pelo override
        assert cpu_data["producao_horaria"] == 9.9
        # Campos originais preservados (merge, não substituição integral)
        assert cpu_data["descricao"] == "Escavação manual"
        assert cpu_data["categoria"] == "TERRAPLENAGEM"
        assert cpu_data["producao_id_ref"] == "CPU-001-PROD-001"
        # Metadado de governança não vaza para o schema de CPU do master
        assert "motivo" not in cpu_data

    def test_gate_quatro_olhos_bloqueia_promocao_de_override_de_cpu(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        projects_dir = tmp_path / "projetos"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        # created_by == owner_id: o dono editou o próprio override
        _seed_projeto(
            projects_dir,
            "PROJ-001",
            owner_id="owner-1",
            contexto_id="ctx-1",
            cpu_overrides={"CPU-001": {"producao_horaria": 4.0}},
            created_by="owner-1",
        )

        result = _promote_as(
            monkeypatch,
            tools,
            user_id="owner-1",
            roles={"catalog-manager"},
            projeto_id="PROJ-001",
            justificativa="x",
        )

        assert "erro" in result
        assert "quatro olhos" in result["erro"]
        cpu_file = config_dir / "catalogos" / "cat-1" / "cpus" / "CPU-001.json"
        assert json.loads(cpu_file.read_text(encoding="utf-8"))["producao_horaria"] == 2.0

    def test_gate_bloqueia_quem_nao_e_dono_nem_admin_para_override_de_cpu(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        projects_dir = tmp_path / "projetos"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        _seed_projeto(
            projects_dir,
            "PROJ-001",
            owner_id="owner-1",
            contexto_id="ctx-1",
            cpu_overrides={"CPU-001": {"producao_horaria": 4.0}},
            created_by="eng-1",
        )

        result = _promote_as(
            monkeypatch,
            tools,
            user_id="mgr-1",
            roles={"catalog-manager"},
            projeto_id="PROJ-001",
            justificativa="x",
        )

        assert "erro" in result
        assert "dono do projeto" in result["erro"] or "admin" in result["erro"]

    def test_sem_pendencias_quando_insumo_e_cpu_estao_vazios(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        projects_dir = tmp_path / "projetos"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        _seed_projeto(projects_dir, "PROJ-001", owner_id="owner-1", contexto_id="ctx-1")

        result = _promote_as(
            monkeypatch,
            tools,
            user_id="owner-1",
            roles={"catalog-manager"},
            projeto_id="PROJ-001",
            justificativa="nada a promover",
        )

        assert result["status"] == "SEM_PENDENCIAS"


class TestOverridesFileEdgeCases:
    """Cobre os desvios de leitura de insumos_override.json/cpus_override.json:
    arquivo ausente e conteúdo malformado (JSON inválido) — em ambos os casos o
    dict correspondente vira {} e a promoção segue com o que sobrar."""

    def test_insumos_override_json_ausente_promove_so_cpu(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        projects_dir = tmp_path / "projetos"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        _seed_projeto(
            projects_dir,
            "PROJ-001",
            owner_id="owner-1",
            contexto_id="ctx-1",
            cpu_overrides={"CPU-001": {"producao_horaria": 4.0}},
            created_by="eng-1",
        )
        (projects_dir / "PROJ-001" / "overrides" / "insumos_override.json").unlink()

        result = _promote_as(
            monkeypatch,
            tools,
            user_id="owner-1",
            roles={"catalog-manager"},
            projeto_id="PROJ-001",
            justificativa="sem arquivo de insumo",
        )

        assert result["status"] == "APROVADO"
        assert result["deltas_insumo"] == 0
        assert result["deltas_cpu"] == 1

    def test_insumos_override_json_malformado_e_tratado_como_vazio(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        projects_dir = tmp_path / "projetos"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        _seed_projeto(
            projects_dir,
            "PROJ-001",
            owner_id="owner-1",
            contexto_id="ctx-1",
            cpu_overrides={"CPU-001": {"producao_horaria": 4.0}},
            created_by="eng-1",
        )
        (projects_dir / "PROJ-001" / "overrides" / "insumos_override.json").write_text(
            "{invalido", encoding="utf-8"
        )

        result = _promote_as(
            monkeypatch,
            tools,
            user_id="owner-1",
            roles={"catalog-manager"},
            projeto_id="PROJ-001",
            justificativa="insumo malformado",
        )

        assert result["status"] == "APROVADO"
        assert result["deltas_insumo"] == 0
        assert result["deltas_cpu"] == 1
        # Conteúdo malformado não é considerado "override pendente" (overrides
        # vira {}, que é falsy) — por isso não é arquivado nem limpo.
        insumos_file = projects_dir / "PROJ-001" / "overrides" / "insumos_override.json"
        assert insumos_file.read_text(encoding="utf-8") == "{invalido"

    def test_cpus_override_json_malformado_e_tratado_como_vazio(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        projects_dir = tmp_path / "projetos"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        _seed_projeto(
            projects_dir,
            "PROJ-001",
            owner_id="owner-1",
            contexto_id="ctx-1",
            insumo_overrides={"MAT-001::BASE": {"preco": 55.0}},
            created_by="eng-1",
        )
        (projects_dir / "PROJ-001" / "overrides" / "cpus_override.json").write_text(
            "{invalido", encoding="utf-8"
        )

        result = _promote_as(
            monkeypatch,
            tools,
            user_id="owner-1",
            roles={"catalog-manager"},
            projeto_id="PROJ-001",
            justificativa="cpu malformado",
        )

        assert result["status"] == "APROVADO"
        assert result["deltas_insumo"] == 1
        assert result["deltas_cpu"] == 0
        cpus_file = projects_dir / "PROJ-001" / "overrides" / "cpus_override.json"
        assert cpus_file.read_text(encoding="utf-8") == "{invalido"


class TestCpuOverrideEntryNaoDict:
    def test_entrada_de_cpu_que_nao_e_dict_e_ignorada(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        projects_dir = tmp_path / "projetos"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        _seed_projeto(
            projects_dir,
            "PROJ-001",
            owner_id="owner-1",
            contexto_id="ctx-1",
            cpu_overrides={"CPU-001": "producao_horaria=4.0"},
            created_by="eng-1",
        )

        result = _promote_as(
            monkeypatch,
            tools,
            user_id="owner-1",
            roles={"catalog-manager"},
            projeto_id="PROJ-001",
            justificativa="entrada invalida",
        )

        assert result["status"] == "APROVADO"
        assert result["deltas_cpu"] == 0
        cpu_file = config_dir / "catalogos" / "cat-1" / "cpus" / "CPU-001.json"
        assert json.loads(cpu_file.read_text(encoding="utf-8"))["producao_horaria"] == 2.0


class TestBdiOverrideNaoCoberto:
    """Documenta a decisão deliberada de não promover bdi_override.json (ver ADR-150 Achados)."""

    def test_bdi_override_json_nao_e_tocado_pela_promocao(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        projects_dir = tmp_path / "projetos"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        bdi_payload = {"material": 0.05, "motivo": "regime especial negociado"}
        _seed_projeto(
            projects_dir,
            "PROJ-001",
            owner_id="owner-1",
            contexto_id="ctx-1",
            cpu_overrides={"CPU-001": {"producao_horaria": 4.0}},
            bdi_override=bdi_payload,
            created_by="eng-1",
        )

        result = _promote_as(
            monkeypatch,
            tools,
            user_id="owner-1",
            roles={"catalog-manager"},
            projeto_id="PROJ-001",
            justificativa="x",
        )

        assert result["status"] == "APROVADO"
        assert "deltas_bdi" not in result

        # bdi_override.json permanece exatamente como estava — nem aplicado, nem
        # arquivado, nem limpo. Não há caminho de promoção para este arquivo.
        bdi_file = projects_dir / "PROJ-001" / "overrides" / "bdi_override.json"
        assert json.loads(bdi_file.read_text(encoding="utf-8")) == bdi_payload
        historico_dir = projects_dir / "PROJ-001" / "overrides" / "historico"
        if historico_dir.exists():
            assert not any("bdi" in p.name for p in historico_dir.glob("*.json"))
