"""Testes para _catalog_storage.py (issue #147 — CONCILIUM__STORE_BACKEND passa a
reger o carregamento do catálogo master, não só de projetos como já corrigia a
issue #146).

Estratégia: `LocalBlobStorage` implementa o mesmo `BlobStoragePort` usado pelo
backend SharePoint real — os testes exercitam a lógica de merge/síntese contra
ele, provando paridade com `CatalogMixin._load_catalogo_from_disk` (caminho
filesystem, inalterado) sem precisar de credenciais reais de SharePoint.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from concilium.application.runtime.mixins import _catalog_storage as cs
from concilium.application.runtime.mixins.catalog import CatalogMixin
from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage


def _make_catalog_mixin(config_root: Path):
    obj = CatalogMixin.__new__(CatalogMixin)
    obj.config_root = config_root
    obj._config_cache = {}
    return obj


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _build_full_catalog_tree(config_root: Path, cat_id: str = "mendeslobo") -> Path:
    """Monta uma árvore que espelha a estrutura real do mendeslobo:
    - cpus/ com 1 arquivo por CPU
    - insumos/{tipo}/{codigo}.json — 1 subpasta por tipo, 1 arquivo por insumo
    - produtividades/ e producoes/ — as duas coexistindo e precisando de merge
    - templates.json com estruturas_indiretas
    - um producao referenciado por CPU que só existe no diretório GLOBAL producoes/
      (fora do catálogo específico) — mesmo caso de _load_producoes_from_cpus.
    """
    cat_dir = config_root / "catalogos" / cat_id

    _write_json(
        cat_dir / "cpus" / "CPU-A.json",
        {
            "codigo": "CPU-A",
            "descricao": "CPU A",
            "categoria": "TERRAPLENAGEM",
            "producao_id_ref": "PROD-A",
        },
    )
    _write_json(
        cat_dir / "cpus" / "CPU-B.json",
        {
            "codigo": "CPU-B",
            "descricao": "CPU B (sintetizada a partir de producao_horaria)",
            "categoria": "TERRAPLENAGEM",
            "producao_id_ref": "PROD-B-SYNTH",
            "producao_horaria": 42.0,
            "composicao_padrao_equipe": {"funcoes": [], "equipamentos": []},
        },
    )
    _write_json(
        cat_dir / "cpus" / "CPU-C.json",
        {
            "codigo": "CPU-C",
            "descricao": "CPU C (producao só no dir global)",
            "categoria": "TERRAPLENAGEM",
            "producao_id_ref": "PROD-GLOBAL",
        },
    )

    # insumos por subpasta (estrutura real do mendeslobo)
    _write_json(
        cat_dir / "insumos" / "mao_obra" / "MO-1.json",
        {"codigo": "MO-1", "tipo": "MAO_OBRA", "descricao": "Servente"},
    )
    _write_json(
        cat_dir / "insumos" / "equipamento" / "EQ-1.json",
        {"codigo": "EQ-1", "tipo": "EQUIPAMENTO", "descricao": "Escavadeira"},
    )

    # produtividades/ e producoes/ coexistindo — merge precisa cobrir os dois
    _write_json(cat_dir / "produtividades" / "PROD-A.json", {"id": "PROD-A", "valor_horario": 10.0})
    _write_json(cat_dir / "producoes" / "PROD-OUTRO.json", {"id": "PROD-OUTRO", "valor_horario": 20.0})

    # templates.json com estruturas_indiretas
    _write_json(
        cat_dir / "templates.json",
        {"templates": {"padrao": {"nome": "Padrão"}}, "estruturas_indiretas": [{"funcao_id": "MO-ENCARREGADO"}]},
    )

    # producao só no diretório GLOBAL (fora do catálogo específico) — CPU-C referencia
    _write_json(config_root / "producoes" / "PROD-GLOBAL.json", {"id": "PROD-GLOBAL", "valor_horario": 99.0})

    return cat_dir


class TestStorageLoadCpus:
    def test_carrega_cpus_de_subpasta(self, tmp_path):
        cat_dir = _build_full_catalog_tree(tmp_path)
        storage = LocalBlobStorage(tmp_path)
        cpus = cs._storage_load_cpus(storage, f"catalogos/{cat_dir.name}")
        codigos = {c["codigo"] for c in cpus}
        assert codigos == {"CPU-A", "CPU-B", "CPU-C"}

    def test_fallback_cpus_json_unico(self, tmp_path):
        cat_dir = tmp_path / "catalogos" / "cat1"
        _write_json(cat_dir / "cpus.json", {"cpus": [{"codigo": "X"}]})
        storage = LocalBlobStorage(tmp_path)
        cpus = cs._storage_load_cpus(storage, "catalogos/cat1")
        assert [c["codigo"] for c in cpus] == ["X"]


class TestStorageLoadInsumos:
    def test_carrega_insumos_de_todas_as_subpastas_por_tipo(self, tmp_path):
        cat_dir = _build_full_catalog_tree(tmp_path)
        storage = LocalBlobStorage(tmp_path)
        insumos = cs._storage_load_insumos(storage, f"catalogos/{cat_dir.name}")
        codigos = {i["codigo"] for i in insumos}
        assert codigos == {"MO-1", "EQ-1"}

    def test_dedup_por_codigo(self, tmp_path):
        cat_dir = tmp_path / "catalogos" / "cat1"
        _write_json(cat_dir / "insumos" / "mao_obra" / "MO-1.json", {"codigo": "MO-1", "tipo": "MAO_OBRA"})
        _write_json(cat_dir / "insumos" / "outro" / "MO-1-dup.json", {"codigo": "MO-1", "tipo": "MAO_OBRA"})
        storage = LocalBlobStorage(tmp_path)
        insumos = cs._storage_load_insumos(storage, "catalogos/cat1")
        assert len(insumos) == 1


class TestStorageLoadProducoesEmSintese:
    def test_merge_producoes_e_produtividades_mais_sintese_mais_global(self, tmp_path):
        cat_dir = _build_full_catalog_tree(tmp_path)
        storage = LocalBlobStorage(tmp_path)
        base = f"catalogos/{cat_dir.name}"
        cpus = cs._storage_load_cpus(storage, base)
        producoes = cs._storage_load_and_synthesize_producoes(storage, cpus, base, "producoes")

        ids = {p["id"] for p in producoes}
        # PROD-A vem de produtividades/, PROD-OUTRO vem de producoes/ (merge dos 2 dirs)
        assert "PROD-A" in ids
        assert "PROD-OUTRO" in ids
        # PROD-B-SYNTH é sintetizada a partir de CPU-B.producao_horaria (nunca existiu como arquivo)
        assert "PROD-B-SYNTH" in ids
        synth = next(p for p in producoes if p["id"] == "PROD-B-SYNTH")
        assert synth["valor_horario"] == 42.0
        # PROD-GLOBAL só existe no diretório global config_root/producoes — precisa ser
        # encontrada via busca por CPU (_storage_load_producoes_from_cpus), não pelo bulk-load.
        assert "PROD-GLOBAL" in ids
        global_prod = next(p for p in producoes if p["id"] == "PROD-GLOBAL")
        assert global_prod["valor_horario"] == 99.0


class TestStorageLoadTemplates:
    def test_carrega_templates_e_estruturas_indiretas(self, tmp_path):
        cat_dir = _build_full_catalog_tree(tmp_path)
        storage = LocalBlobStorage(tmp_path)
        templates, estruturas = cs._storage_load_templates(storage, f"catalogos/{cat_dir.name}")
        assert templates == {"padrao": {"nome": "Padrão"}}
        assert estruturas == [{"funcao_id": "MO-ENCARREGADO"}]

    def test_ausente_retorna_vazio(self, tmp_path):
        storage = LocalBlobStorage(tmp_path)
        templates, estruturas = cs._storage_load_templates(storage, "catalogos/inexistente")
        assert templates == {}
        assert estruturas == []


class TestLoadCatalogoViaStorageParidade:
    """O teste mais importante: o resultado de load_catalogo_via_storage deve ser
    equivalente (mesmas chaves, mesmo conteúdo relevante) ao de
    CatalogMixin._load_catalogo_from_disk para a MESMA árvore de arquivos —
    prova que a leitura via BlobStoragePort não diverge do caminho filesystem real."""

    def test_paridade_com_load_catalogo_from_disk(self, tmp_path):
        cat_id = "mendeslobo"
        # Duas raízes: caminho filesystem usa config_root/catalogos/{id} direto;
        # caminho "sharepoint" simulado usa LocalBlobStorage(tmp_path) com a
        # árvore sob tmp_path/config/... (prefixo "config/catalogos/{id}" relativo
        # à raiz do storage — mesma convenção real do D6 da ADR-047).
        _build_full_catalog_tree(tmp_path, cat_id)
        _build_full_catalog_tree(tmp_path / "config", cat_id)

        mixin = _make_catalog_mixin(tmp_path)
        via_disco = mixin._load_catalogo_from_disk(cat_id)

        with patch.object(cs, "catalog_storage_backend", return_value="sharepoint"):
            with patch.object(cs, "build_blob_storage", return_value=LocalBlobStorage(tmp_path)):
                via_storage = cs.load_catalogo_via_storage(tmp_path, cat_id, force_refresh=True)

        assert {c["codigo"] for c in via_storage["cpus"]} == {c["codigo"] for c in via_disco["cpus"]}
        assert {i["codigo"] for i in via_storage["insumos"]} == {i["codigo"] for i in via_disco["insumos"]}
        assert {p["id"] for p in via_storage["producoes"]} == {p["id"] for p in via_disco["producoes"]}
        assert via_storage["templates"] == via_disco["templates"]
        assert via_storage["estruturas_indiretas"] == via_disco["estruturas_indiretas"]

    def test_cache_ttl_evita_segunda_leitura(self, tmp_path):
        cat_id = "cat1"
        _build_full_catalog_tree(tmp_path / "config", cat_id)
        storage = LocalBlobStorage(tmp_path)

        with patch.object(cs, "catalog_storage_backend", return_value="sharepoint"):
            with patch.object(cs, "build_blob_storage", return_value=storage) as build_mock:
                cs.load_catalogo_via_storage(tmp_path, cat_id, force_refresh=True)
                assert build_mock.call_count == 1
                # Segunda chamada sem force_refresh deve usar o cache local (TTL),
                # sem reconstruir/consultar o storage de novo.
                cs.load_catalogo_via_storage(tmp_path, cat_id)
                assert build_mock.call_count == 1

    def test_force_refresh_ignora_cache(self, tmp_path):
        cat_id = "cat1"
        _build_full_catalog_tree(tmp_path / "config", cat_id)
        storage = LocalBlobStorage(tmp_path)

        with patch.object(cs, "catalog_storage_backend", return_value="sharepoint"):
            with patch.object(cs, "build_blob_storage", return_value=storage) as build_mock:
                cs.load_catalogo_via_storage(tmp_path, cat_id, force_refresh=True)
                cs.load_catalogo_via_storage(tmp_path, cat_id, force_refresh=True)
                assert build_mock.call_count == 2


class TestCatalogMixinLoadCatalogoRoteamento:
    """CatalogMixin.load_catalogo() deve rotear pro caminho certo conforme
    CONCILIUM__STORE_BACKEND — o cerne do fix da issue #147."""

    def test_backend_filesystem_usa_caminho_local_inalterado(self, tmp_path):
        cat_id = "cat1"
        _build_full_catalog_tree(tmp_path, cat_id)
        mixin = _make_catalog_mixin(tmp_path)

        with patch(
            "concilium.application.runtime.mixins._catalog_storage.catalog_storage_backend",
            return_value="filesystem",
        ):
            resultado = mixin.load_catalogo(cat_id)

        assert {c["codigo"] for c in resultado["cpus"]} == {"CPU-A", "CPU-B", "CPU-C"}

    def test_backend_nao_filesystem_usa_storage_port(self, tmp_path):
        cat_id = "cat1"
        _build_full_catalog_tree(tmp_path / "config", cat_id)
        mixin = _make_catalog_mixin(tmp_path)
        storage = LocalBlobStorage(tmp_path)

        with patch(
            "concilium.application.runtime.mixins._catalog_storage.catalog_storage_backend",
            return_value="sharepoint",
        ):
            with patch(
                "concilium.application.runtime.mixins._catalog_storage.build_blob_storage",
                return_value=storage,
            ):
                resultado = mixin.load_catalogo(cat_id)

        assert {c["codigo"] for c in resultado["cpus"]} == {"CPU-A", "CPU-B", "CPU-C"}
        # produtividades fica vazia de propósito — mesma peculiaridade do caminho
        # filesystem, replicada para paridade (ver _load_catalogo_from_disk).
        assert resultado["produtividades"] == []

    def test_cache_em_memoria_por_instancia_ainda_funciona(self, tmp_path):
        """load_catalogo() cacheia em _config_cache — segunda chamada na MESMA
        instância não deve reconsultar o storage, com qualquer backend."""
        cat_id = "cat1"
        _build_full_catalog_tree(tmp_path / "config", cat_id)
        mixin = _make_catalog_mixin(tmp_path)
        storage = LocalBlobStorage(tmp_path)

        with patch(
            "concilium.application.runtime.mixins._catalog_storage.catalog_storage_backend",
            return_value="sharepoint",
        ):
            with patch(
                "concilium.application.runtime.mixins._catalog_storage.build_blob_storage",
                return_value=storage,
            ) as build_mock:
                mixin.load_catalogo(cat_id)
                mixin.load_catalogo(cat_id)
                assert build_mock.call_count == 1
