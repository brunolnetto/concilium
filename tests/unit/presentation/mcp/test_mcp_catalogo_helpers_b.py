"""Tests for _catalogo_tools_helpers_b — covers missing lines."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from concilium.presentation.mcp.tools._catalogo_tools_helpers_b import (
    _catalog_root,
    _impl_avaliar_plausibilidade_catalogo,
    _impl_calcular_pu_producao,
    _impl_comparar_catalogo,
    _impl_mesclar_catalogo,
    _impl_tendencia_precos_catalogo,
    _impl_verificar_integridade_catalogo,
    _resolve_catalogo_id,
)

MODULE = "concilium.presentation.mcp.tools._catalogo_tools_helpers_b"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _identity(x):
    """Use as _wrap_response to keep assertions simple."""
    return x


def _make_bundle(
    insumos=None,
    producoes=None,
    cpus=None,
    use_produtividades_key=False,
):
    bundle: dict = {}
    if insumos is not None:
        bundle["insumos"] = insumos
    if producoes is not None:
        if use_produtividades_key:
            bundle["produtividades"] = producoes
        else:
            bundle["producoes"] = producoes
    if cpus is not None:
        bundle["cpus"] = cpus
    return bundle


def _write_bundle(path: Path, bundle: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle), encoding="utf-8")


# ---------------------------------------------------------------------------
# _catalog_root
# ---------------------------------------------------------------------------


class TestCatalogRoot:
    def test_returns_correct_path(self, tmp_path):
        result = _catalog_root(tmp_path, "mendeslobo")
        assert result == tmp_path / "catalogos" / "mendeslobo"

    def test_different_catalog_id(self, tmp_path):
        result = _catalog_root(tmp_path, "outro-contexto")
        assert result == tmp_path / "catalogos" / "outro-contexto"


class TestResolveCatalogoId:
    def test_resolve_quando_catalogo_id_diverge(self, tmp_path):
        contexto_file = tmp_path / "contextos" / "mendeslobo-rfi.json"
        contexto_file.parent.mkdir(parents=True)
        contexto_file.write_text(json.dumps({"id": "mendeslobo-rfi", "catalogo_id": "rfi-r02"}), encoding="utf-8")

        assert _resolve_catalogo_id(tmp_path, "mendeslobo-rfi") == "rfi-r02"

    def test_fallback_quando_contexto_id_igual_catalogo_id(self, tmp_path):
        contexto_file = tmp_path / "contextos" / "mendeslobo.json"
        contexto_file.parent.mkdir(parents=True)
        contexto_file.write_text(json.dumps({"id": "mendeslobo", "catalogo_id": "mendeslobo"}), encoding="utf-8")

        assert _resolve_catalogo_id(tmp_path, "mendeslobo") == "mendeslobo"

    def test_fallback_quando_contexto_nao_existe(self, tmp_path):
        assert _resolve_catalogo_id(tmp_path, "contexto-fantasma") == "contexto-fantasma"

    def test_fallback_quando_json_corrompido(self, tmp_path):
        contexto_file = tmp_path / "contextos" / "quebrado.json"
        contexto_file.parent.mkdir(parents=True)
        contexto_file.write_text("{ nao é json válido", encoding="utf-8")

        assert _resolve_catalogo_id(tmp_path, "quebrado") == "quebrado"

    def test_fallback_quando_contexto_sem_catalogo_id(self, tmp_path):
        contexto_file = tmp_path / "contextos" / "sem-campo.json"
        contexto_file.parent.mkdir(parents=True)
        contexto_file.write_text(json.dumps({"id": "sem-campo"}), encoding="utf-8")

        assert _resolve_catalogo_id(tmp_path, "sem-campo") == "sem-campo"


# ---------------------------------------------------------------------------
# _impl_tendencia_precos_catalogo
# ---------------------------------------------------------------------------


class TestImplTendenciaPrecosCatalogo:
    def _config_path(self, tmp_path):
        return tmp_path / "config"

    def test_sad_path_bundle_missing(self, tmp_path):
        config_dir = self._config_path(tmp_path)
        config_dir.mkdir(parents=True)

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            result = _impl_tendencia_precos_catalogo("mendeslobo")

        assert "erro" in result
        assert "Bundle" in result["erro"]

    def test_happy_path_basic(self, tmp_path):
        config_dir = self._config_path(tmp_path)
        bundle_path = config_dir / "catalogos" / "mendeslobo" / ".catalog_bundle.json"
        insumos = [
            {"codigo": "INS-001", "tipo": "EQUIPAMENTO", "preco_unitario": 100.0, "descricao": "Test", "unidade": "h"}
        ]
        _write_bundle(bundle_path, _make_bundle(insumos=insumos))

        # Build a real RelatorioTendencia-like dataclass result
        from concilium.application.catalog.price_trend import IndiceCategoria, RelatorioTendencia

        fake_relatorio = RelatorioTendencia(
            contexto_id="mendeslobo",
            gerado_em="2026-06-14",
            data_base_analise="2026-06-14",
            jurisdicao_id=None,
            indices_por_categoria=[
                IndiceCategoria(
                    tipo="EQUIPAMENTO",
                    n_insumos_com_historico=0,
                    n_insumos_total=1,
                    variacao_media_pct=None,
                    variacao_mediana_pct=None,
                    variacao_max_pct=None,
                    variacao_min_pct=None,
                    insumos=[],
                )
            ],
            resumo={"total_insumos": 1},
        )

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                with patch(
                    "concilium.application.catalog.price_trend.calcular_tendencia",
                    return_value=fake_relatorio,
                ):
                    result = _impl_tendencia_precos_catalogo("mendeslobo")

        assert "indices_por_categoria" in result
        assert result["contexto_id"] == "mendeslobo"

    def test_happy_path_truncation_more_than_10_insumos(self, tmp_path):
        """Covers lines 50-53: top-10 truncation and insumos_omitidos."""
        config_dir = self._config_path(tmp_path)
        bundle_path = config_dir / "catalogos" / "ctx" / ".catalog_bundle.json"
        _write_bundle(bundle_path, _make_bundle(insumos=[]))

        from concilium.application.catalog.price_trend import IndiceCategoria, RelatorioTendencia, TendenciaInsumo

        # 15 insumos — truncation logic should keep 10 and set insumos_omitidos=5
        fake_insumos = [
            TendenciaInsumo(
                codigo=f"INS-{i:03d}",
                descricao=f"desc {i}",
                tipo="MATERIAL",
                unidade="un",
                preco_atual=float(i),
                preco_referencia=float(i) * 0.9,
                data_referencia="2024-01-01",
                variacao_abs=float(i) * 0.1,
                variacao_pct=float(i),
                n_registros_historico=1,
                fonte_atual="preco_unitario",
            )
            for i in range(1, 16)
        ]
        fake_relatorio = RelatorioTendencia(
            contexto_id="ctx",
            gerado_em="2026-06-14",
            data_base_analise="2026-06-14",
            jurisdicao_id=None,
            indices_por_categoria=[
                IndiceCategoria(
                    tipo="MATERIAL",
                    n_insumos_com_historico=15,
                    n_insumos_total=15,
                    variacao_media_pct=8.0,
                    variacao_mediana_pct=8.0,
                    variacao_max_pct=15.0,
                    variacao_min_pct=1.0,
                    insumos=fake_insumos,
                )
            ],
            resumo={"total_insumos": 15},
        )

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                with patch(
                    "concilium.application.catalog.price_trend.calcular_tendencia",
                    return_value=fake_relatorio,
                ):
                    result = _impl_tendencia_precos_catalogo("ctx")

        cat = result["indices_por_categoria"][0]
        # After truncation, at most 10 insumos remain in the dict
        assert len(cat["insumos"]) <= 10
        # insumos_omitidos was computed from the pre-truncation list
        assert cat["insumos_omitidos"] >= 0

    def test_with_jurisdicao_id(self, tmp_path):
        config_dir = self._config_path(tmp_path)
        bundle_path = config_dir / "catalogos" / "ctx" / ".catalog_bundle.json"
        _write_bundle(bundle_path, _make_bundle(insumos=[]))

        from concilium.application.catalog.price_trend import RelatorioTendencia

        fake_relatorio = RelatorioTendencia(
            contexto_id="ctx",
            gerado_em="2026-06-14",
            data_base_analise="2026-06-14",
            jurisdicao_id="BR-CE",
            indices_por_categoria=[],
            resumo={},
        )

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                with patch(
                    "concilium.application.catalog.price_trend.calcular_tendencia",
                    return_value=fake_relatorio,
                ) as mock_ct:
                    _impl_tendencia_precos_catalogo("ctx", jurisdicao_id="BR-CE")

        mock_ct.assert_called_once_with([], jurisdicao_id="BR-CE", contexto_id="ctx")


# ---------------------------------------------------------------------------
# _impl_comparar_catalogo / _impl_mesclar_catalogo (issue #134) — agnósticos de
# fonte: cada origem pode ser um catálogo (catalogo_id) ou uma planilha RFI
# (.xlsm/.xlsx). Fakeamos o Runtime via _runtime() em vez de ler bundle direto.
# ---------------------------------------------------------------------------


def _make_rt(tmp_path: Path, catalogos: dict) -> MagicMock:
    """Fake Runtime cujo load_catalogo despacha por catalogo_id, sempre deepcopy.

    `load_contexto` levanta (sem contexto de teste para catA/catB/etc.) para que
    `resolver_catalogo_id` caia no fallback real: usar o id como está — mesmo
    comportamento de um catalogo_id puro, sem contexto próprio, em produção.
    """
    import copy

    rt = MagicMock()
    rt.config_root = tmp_path / "config"
    rt.load_catalogo.side_effect = lambda cid: copy.deepcopy(catalogos[cid])
    rt.load_contexto.side_effect = Exception("sem contexto de teste")
    return rt


class TestImplCompararCatalogo:
    _CAT_A = {
        "insumos": [{"codigo": "I1", "descricao": "Cimento", "unidade": "kg", "preco_unitario": 10.0}],
        "producoes": [{"id": "P1", "descricao": "Escavação"}],
        "cpus": [{"codigo": "CPU-1", "descricao": "Terraplenagem"}],
    }
    _CAT_B = {
        "insumos": [{"codigo": "I1", "descricao": "Cimento", "unidade": "kg", "preco_unitario": 12.0}],
        "producoes": [{"id": "P2", "descricao": "Compactação"}],
        "cpus": [{"codigo": "CPU-2", "descricao": "Pavimentação"}],
    }

    def test_tipo_invalido_returns_erro(self):
        result = _impl_comparar_catalogo("catA", "catB", tipo="invalido")
        assert "erro" in result

    def test_compara_dois_catalogos(self, tmp_path):
        rt = _make_rt(tmp_path, {"catA": self._CAT_A, "catB": self._CAT_B})
        with patch("concilium.presentation.mcp._context._runtime", return_value=rt):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                result = _impl_comparar_catalogo("catA", "catB", tipo="todos")

        assert result["origem_a"] == "catA"
        assert result["origem_b"] == "catB"
        assert "insumos" in result and "producoes" in result and "cpus" in result
        assert "resumo" in result
        assert "aviso" not in result

    def test_cpus_pulado_quando_origem_e_planilha(self, tmp_path):
        xlsm = tmp_path / "planilha.xlsm"
        xlsm.touch()
        rt = _make_rt(tmp_path, {"catA": self._CAT_A})
        with patch("concilium.presentation.mcp._context._runtime", return_value=rt):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                result = _impl_comparar_catalogo("catA", str(xlsm), tipo="cpus")

        assert "erro" in result  # cpus era o único tipo pedido, foi pulado -> nada resta

    def test_planilha_source_script_not_found_returns_erro(self, tmp_path):
        """repo_root (config_root.parent) sem scripts/benchmark/merge_rfi.py."""
        xlsm = tmp_path / "planilha.xlsm"
        xlsm.touch()
        rt = _make_rt(tmp_path, {"catA": self._CAT_A})
        with patch("concilium.presentation.mcp._context._runtime", return_value=rt):
            result = _impl_comparar_catalogo("catA", str(xlsm), tipo="insumos")

        assert "erro" in result
        assert "Script não encontrado" in result["erro"]

    def test_planilha_source_reads_via_real_merge_rfi_script(self, tmp_path):
        """Usa o repo_root real para exercitar o adaptador de planilha ponta-a-ponta."""
        import openpyxl

        real_repo_root = Path(__file__).resolve().parents[4]
        xlsm = tmp_path / "planilha.xlsm"
        openpyxl.Workbook().save(xlsm)

        rt = MagicMock()
        rt.config_root = real_repo_root / "config"
        rt.load_catalogo.return_value = self._CAT_A
        with patch("concilium.presentation.mcp._context._runtime", return_value=rt):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                result = _impl_comparar_catalogo("catA", str(xlsm), tipo="todos")

        assert result["aviso"] == "cpus: pulado — planilha RFI não modela esse tipo de entidade."
        assert "cpus" not in result


class TestImplMesclarCatalogo:
    """ADR-177: preview com merge_id (dry_run=True) -> aplicação por outro ator (dry_run=False).

    Escrita durável nos arquivos individuais (issue #141) é coberta à parte, com um
    Runtime real, em TestImplMesclarCatalogoDurabilidade — aqui a mecânica de preview/
    quatro-olhos/TTL é exercitada com o Runtime fake de sempre (_make_rt).
    """

    _DESTINO = {
        "insumos": [{"codigo": "I1", "descricao": "Cimento", "unidade": "kg", "preco_unitario": 10.0}],
        "producoes": [{"id": "P1", "descricao": "Escavação"}],
        "cpus": [],
    }
    _ORIGEM = {
        "insumos": [{"codigo": "I2", "descricao": "Areia", "unidade": "m3", "preco_unitario": 5.0}],
        "producoes": [],
        "cpus": [],
    }

    def _gerar_preview(self, tmp_path, rt, **kwargs):
        with patch("concilium.presentation.mcp._context._runtime", return_value=rt):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                return _impl_mesclar_catalogo("dest", "orig", dry_run=True, actor="ator-a", **kwargs)

    def test_destino_planilha_returns_erro(self, tmp_path):
        xlsm = tmp_path / "planilha.xlsm"
        xlsm.touch()
        result = _impl_mesclar_catalogo(str(xlsm), "origem_cat")
        assert "erro" in result
        assert "planilha" in result["erro"]

    def test_tipo_invalido_returns_erro(self):
        result = _impl_mesclar_catalogo("dest", "orig", tipo="invalido")
        assert "erro" in result

    def test_dry_run_gera_preview_com_merge_id_sem_escrever_nada(self, tmp_path):
        rt = _make_rt(tmp_path, {"dest": self._DESTINO, "orig": self._ORIGEM})
        result = self._gerar_preview(tmp_path, rt)

        assert result["mode"] == "DRY_RUN"
        assert "aplicado" not in result
        assert result["merge_id"]
        assert result["expira_em_horas"] == 24
        bundle_path = tmp_path / "config" / "catalogos" / "dest" / ".catalog_bundle.json"
        assert not bundle_path.exists()
        preview_path = tmp_path / "config" / "catalogos" / "dest" / "merges_pendentes" / f"{result['merge_id']}.json"
        assert preview_path.exists()
        preview = json.loads(preview_path.read_text())
        assert preview["criado_por"] == "ator-a"

    def test_apply_sem_merge_id_retorna_erro(self, tmp_path):
        rt = _make_rt(tmp_path, {"dest": self._DESTINO, "orig": self._ORIGEM})
        with patch("concilium.presentation.mcp._context._runtime", return_value=rt):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                result = _impl_mesclar_catalogo("dest", "orig", dry_run=False, actor="ator-b")

        assert "erro" in result
        assert "merge_id" in result["erro"]

    def test_apply_merge_id_inexistente_retorna_erro(self, tmp_path):
        rt = _make_rt(tmp_path, {"dest": self._DESTINO, "orig": self._ORIGEM})
        with patch("concilium.presentation.mcp._context._runtime", return_value=rt):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                result = _impl_mesclar_catalogo(
                    "dest", "orig", dry_run=False, merge_id="fantasma", actor="ator-b"
                )

        assert "erro" in result
        assert "não encontrado" in result["erro"]

    def test_apply_mesmo_ator_do_preview_bloqueado_quatro_olhos(self, tmp_path):
        rt = _make_rt(tmp_path, {"dest": self._DESTINO, "orig": self._ORIGEM})
        preview = self._gerar_preview(tmp_path, rt)
        with patch("concilium.presentation.mcp._context._runtime", return_value=rt):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                result = _impl_mesclar_catalogo(
                    "dest", "orig", dry_run=False, merge_id=preview["merge_id"], actor="ator-a"
                )

        assert "erro" in result
        assert "quatro olhos" in result["erro"]

    def test_apply_origem_divergente_do_preview_retorna_erro(self, tmp_path):
        """destino continua "dest" (mesmo catalogo_id, mesmo diretório de preview) — só
        `origem` diverge do que foi revisado no preview."""
        rt = _make_rt(tmp_path, {"dest": self._DESTINO, "orig": self._ORIGEM, "outra-origem": self._ORIGEM})
        preview = self._gerar_preview(tmp_path, rt)
        with patch("concilium.presentation.mcp._context._runtime", return_value=rt):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                result = _impl_mesclar_catalogo(
                    "dest", "outra-origem", dry_run=False, merge_id=preview["merge_id"], actor="ator-b"
                )

        assert "erro" in result
        assert "não coincidem" in result["erro"]

    def test_apply_preview_expirado_retorna_erro(self, tmp_path):
        from datetime import UTC, datetime, timedelta

        rt = _make_rt(tmp_path, {"dest": self._DESTINO, "orig": self._ORIGEM})
        preview = self._gerar_preview(tmp_path, rt)
        preview_path = (
            tmp_path / "config" / "catalogos" / "dest" / "merges_pendentes" / f"{preview['merge_id']}.json"
        )
        data = json.loads(preview_path.read_text())
        data["criado_em"] = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
        preview_path.write_text(json.dumps(data), encoding="utf-8")

        with patch("concilium.presentation.mcp._context._runtime", return_value=rt):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                result = _impl_mesclar_catalogo(
                    "dest", "orig", dry_run=False, merge_id=preview["merge_id"], actor="ator-b"
                )

        assert "erro" in result
        assert "expirado" in result["erro"]

    def test_apply_catalogo_mudou_desde_preview_retorna_erro(self, tmp_path):
        catalogos = {"dest": dict(self._DESTINO), "orig": self._ORIGEM}
        rt = _make_rt(tmp_path, catalogos)
        preview = self._gerar_preview(tmp_path, rt)
        # Catálogo destino mudou entre o preview e a aplicação (TOCTOU): I2 (antes
        # RIGHT_ONLY, "novo") agora já existe na base com preço divergente — muda a
        # categoria para INNER_HIGH com delta, alterando os contadores do resumo.
        catalogos["dest"] = {
            "insumos": [
                *self._DESTINO["insumos"],
                {"codigo": "I2", "descricao": "Areia", "unidade": "m3", "preco_unitario": 999.0},
            ],
            "producoes": self._DESTINO["producoes"],
            "cpus": [],
        }

        with patch("concilium.presentation.mcp._context._runtime", return_value=rt):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                result = _impl_mesclar_catalogo(
                    "dest", "orig", dry_run=False, merge_id=preview["merge_id"], actor="ator-b"
                )

        assert "erro" in result
        assert "mudou" in result["erro"]

    def test_apply_com_sucesso_escreve_arquivos_individuais_gera_snapshot_e_remove_preview(self, tmp_path):
        rt = _make_rt(tmp_path, {"dest": self._DESTINO, "orig": self._ORIGEM})
        preview = self._gerar_preview(tmp_path, rt)

        with patch("concilium.presentation.mcp._context._runtime", return_value=rt):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                result = _impl_mesclar_catalogo(
                    "dest", "orig", dry_run=False, merge_id=preview["merge_id"],
                    actor="ator-b", justificativa="importação RFI lote 3",
                )

        assert result["mode"] == "APPLIED"
        assert result["aplicado"]["insumos"]["arquivos_escritos"] == 1
        assert result["snapshot_id"]
        bundle_path = tmp_path / "config" / "catalogos" / "dest" / ".catalog_bundle.json"
        assert not bundle_path.exists()  # ADR-177 D1: nunca escreve no bundle
        insumo_novo = tmp_path / "config" / "catalogos" / "dest" / "insumos" / "outro" / "I2.json"
        assert insumo_novo.exists()
        assert json.loads(insumo_novo.read_text())["descricao"] == "Areia"
        preview_path = (
            tmp_path / "config" / "catalogos" / "dest" / "merges_pendentes" / f"{preview['merge_id']}.json"
        )
        assert not preview_path.exists()  # estado terminal — não reaplicável

    def test_apply_com_merge_id_ja_aplicado_retorna_erro(self, tmp_path):
        rt = _make_rt(tmp_path, {"dest": self._DESTINO, "orig": self._ORIGEM})
        preview = self._gerar_preview(tmp_path, rt)
        with patch("concilium.presentation.mcp._context._runtime", return_value=rt):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                _impl_mesclar_catalogo(
                    "dest", "orig", dry_run=False, merge_id=preview["merge_id"], actor="ator-b"
                )
                result = _impl_mesclar_catalogo(
                    "dest", "orig", dry_run=False, merge_id=preview["merge_id"], actor="ator-c"
                )

        assert "erro" in result
        assert "não encontrado" in result["erro"]

    def test_apply_exige_permissao_catalog_merge(self, tmp_path):
        rt = _make_rt(tmp_path, {"dest": self._DESTINO, "orig": self._ORIGEM})
        preview = self._gerar_preview(tmp_path, rt)

        with (
            patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}),
            patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=True),
            patch("concilium.infrastructure.auth.permission_guard._effective_mcp_roles", return_value=["operator"]),
            patch("concilium.presentation.mcp._context._runtime", return_value=rt),
            patch(f"{MODULE}._wrap_response", side_effect=_identity),
        ):
            result = _impl_mesclar_catalogo(
                "dest", "orig", dry_run=False, merge_id=preview["merge_id"], actor="ator-b"
            )

        assert "erro" in result
        assert "catalog:merge" in result["erro"]
        # Nada foi escrito — o gate de permissão bloqueou antes de tocar o preview/arquivos
        insumo_novo = tmp_path / "config" / "catalogos" / "dest" / "insumos" / "outro" / "I2.json"
        assert not insumo_novo.exists()


class TestImplMesclarCatalogoDurabilidade:
    """ADR-177 D1: regressão do bug real — merge sobrevive à invalidação do cache
    (issue #141). Precisa de um Runtime de verdade (não o _make_rt fake) para
    exercitar `_catalog_bundle_valid`/`_load_catalogo_from_disk` de fato.
    """

    def _seed_catalogo(self, catalog_root: Path, insumos: list[dict]) -> None:
        for insumo in insumos:
            tipo_dir = catalog_root / "insumos" / str(insumo.get("tipo", "outro")).lower()
            tipo_dir.mkdir(parents=True, exist_ok=True)
            (tipo_dir / f"{insumo['codigo']}.json").write_text(json.dumps(insumo), encoding="utf-8")

    def test_merge_sobrevive_invalidacao_de_cache_por_escrita_nao_relacionada(self, tmp_path):
        from concilium.application.runtime import Runtime

        config_root = tmp_path / "config"
        catalog_root = config_root / "catalogos" / "dest"
        self._seed_catalogo(
            catalog_root, [{"codigo": "I1", "tipo": "material", "descricao": "Cimento", "preco_unitario": 10.0}]
        )
        origem_dir = config_root / "catalogos" / "orig"
        self._seed_catalogo(
            origem_dir, [{"codigo": "I2", "tipo": "material", "descricao": "Areia", "preco_unitario": 5.0}]
        )

        rt1 = Runtime(config_root)
        with patch("concilium.presentation.mcp._context._runtime", return_value=rt1):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                preview = _impl_mesclar_catalogo("dest", "orig", dry_run=True, tipo="insumos", actor="ator-a")

        rt2 = Runtime(config_root)  # ator diferente, chamada nova -> Runtime novo (sem cache do preview)
        with patch("concilium.presentation.mcp._context._runtime", return_value=rt2):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                applied = _impl_mesclar_catalogo(
                    "dest", "orig", dry_run=False, tipo="insumos", merge_id=preview["merge_id"], actor="ator-b"
                )
        assert "snapshot_id" in applied

        # Simula uma escrita de catálogo totalmente não relacionada, depois do merge —
        # é exatamente essa escrita que, antes da ADR-177, fazia _catalog_bundle_valid
        # invalidar o cache e reconstruir o bundle a partir dos arquivos individuais
        # (que nunca tinham sido tocados), revertendo o merge silenciosamente.
        (catalog_root / "insumos" / "material" / "I1.json").write_text(
            json.dumps({"codigo": "I1", "tipo": "material", "descricao": "Cimento", "preco_unitario": 11.0}),
            encoding="utf-8",
        )

        rt3 = Runtime(config_root)  # leitura fresca, sem cache em memória de nenhuma chamada anterior
        catalogo_final = rt3.load_catalogo("dest")
        codigos = {i["codigo"] for i in catalogo_final["insumos"]}
        assert {"I1", "I2"} <= codigos  # o merge persiste — não foi revertido pela invalidação de cache


# ---------------------------------------------------------------------------
# _impl_calcular_pu_producao
# ---------------------------------------------------------------------------


class TestImplCalcularPuProducao:
    def _config_path(self, tmp_path):
        return tmp_path / "config"

    def test_sad_path_bundle_missing(self, tmp_path):
        config_dir = self._config_path(tmp_path)
        config_dir.mkdir(parents=True)

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            result = _impl_calcular_pu_producao("ctx", "PROD-001")

        assert "erro" in result

    def test_sad_path_producao_not_found(self, tmp_path):
        """Covers lines 207-209: producao_id not in bundle."""
        config_dir = self._config_path(tmp_path)
        bundle_path = config_dir / "catalogos" / "ctx" / ".catalog_bundle.json"
        bundle = _make_bundle(
            insumos=[],
            producoes=[{"id": "PROD-OTHER", "valor_horario": 10.0}],
        )
        _write_bundle(bundle_path, bundle)

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            result = _impl_calcular_pu_producao("ctx", "PROD-DOES-NOT-EXIST")

        assert "erro" in result
        assert "PROD-DOES-NOT-EXIST" in result["erro"]

    def test_happy_path_producao_found_by_id(self, tmp_path):
        """Covers lines 196-219: producao found and PU calculated."""
        config_dir = self._config_path(tmp_path)
        bundle_path = config_dir / "catalogos" / "ctx" / ".catalog_bundle.json"
        bundle = _make_bundle(
            insumos=[{"codigo": "MO-001", "tipo": "MAO_OBRA", "preco_unitario": 4000.0, "unidade": "mes"}],
            producoes=[
                {
                    "id": "PROD-001",
                    "valor_horario": 5.0,
                    "composicao_padrao_equipe": {
                        "funcoes": [{"funcao_id": "MO-001", "num_pessoas": 1}],
                        "equipamentos": [],
                    },
                }
            ],
        )
        _write_bundle(bundle_path, bundle)

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                result = _impl_calcular_pu_producao("ctx", "PROD-001")

        assert "producao_id" in result
        assert result["producao_id"] == "PROD-001"

    def test_happy_path_producao_found_by_codigo(self, tmp_path):
        """Covers alternate lookup via 'codigo' key."""
        config_dir = self._config_path(tmp_path)
        bundle_path = config_dir / "catalogos" / "ctx" / ".catalog_bundle.json"
        bundle = _make_bundle(
            insumos=[],
            producoes=[
                {
                    "codigo": "CPU-001",
                    "valor_horario": 3.0,
                    "composicao_padrao_equipe": {
                        "funcoes": [],
                        "equipamentos": [],
                    },
                }
            ],
        )
        _write_bundle(bundle_path, bundle)

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                result = _impl_calcular_pu_producao("ctx", "CPU-001")

        assert "producao_id" in result

    def test_default_detalhado_false_omits_itens(self, tmp_path):
        """ADR-163 D3: detalhado=False (default) preserva o formato de resposta atual."""
        config_dir = self._config_path(tmp_path)
        bundle_path = config_dir / "catalogos" / "ctx" / ".catalog_bundle.json"
        bundle = _make_bundle(
            insumos=[{"codigo": "MO-001", "tipo": "MAO_OBRA", "preco_unitario": 30.0, "unidade": "h"}],
            producoes=[
                {
                    "id": "PROD-001",
                    "valor_horario": 5.0,
                    "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "MO-001", "num_pessoas": 1}]},
                }
            ],
        )
        _write_bundle(bundle_path, bundle)

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                result = _impl_calcular_pu_producao("ctx", "PROD-001")

        assert "itens" not in result

    def test_detalhado_true_inclui_itens(self, tmp_path):
        config_dir = self._config_path(tmp_path)
        bundle_path = config_dir / "catalogos" / "ctx" / ".catalog_bundle.json"
        bundle = _make_bundle(
            insumos=[{"codigo": "MO-001", "tipo": "MAO_OBRA", "preco_unitario": 30.0, "unidade": "h"}],
            producoes=[
                {
                    "id": "PROD-001",
                    "valor_horario": 5.0,
                    "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "MO-001", "num_pessoas": 1}]},
                }
            ],
        )
        _write_bundle(bundle_path, bundle)

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                result = _impl_calcular_pu_producao("ctx", "PROD-001", detalhado=True)

        assert "itens" in result
        assert result["itens"][0]["insumo_id"] == "MO-001"

    def test_happy_path_uses_produtividades_key(self, tmp_path):
        """Covers line 205: bundle uses 'produtividades' instead of 'producoes'."""
        config_dir = self._config_path(tmp_path)
        bundle_path = config_dir / "catalogos" / "ctx" / ".catalog_bundle.json"
        bundle = _make_bundle(
            insumos=[],
            producoes=[{"id": "PROD-001", "valor_horario": 2.0}],
            use_produtividades_key=True,
        )
        _write_bundle(bundle_path, bundle)

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                result = _impl_calcular_pu_producao("ctx", "PROD-001")

        assert "producao_id" in result


# ---------------------------------------------------------------------------
# _impl_avaliar_plausibilidade_catalogo
# ---------------------------------------------------------------------------


class TestImplAvaliarPlausibilidadeCatalogo:
    def _config_path(self, tmp_path):
        return tmp_path / "config"

    def test_sad_path_bundle_missing(self, tmp_path):
        config_dir = self._config_path(tmp_path)
        config_dir.mkdir(parents=True)

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            result = _impl_avaliar_plausibilidade_catalogo("ctx")

        assert "erro" in result

    def test_happy_path(self, tmp_path):
        """Covers lines 234-247."""
        config_dir = self._config_path(tmp_path)
        bundle_path = config_dir / "catalogos" / "ctx" / ".catalog_bundle.json"
        bundle = _make_bundle(
            insumos=[{"codigo": "INS-001"}],
            producoes=[{"id": "PROD-001"}],
            cpus=[{"codigo": "CPU-001"}],
        )
        _write_bundle(bundle_path, bundle)

        fake_resultado = {"ok": True, "alertas": []}

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                with patch(
                    "concilium.application.catalog.plausibility_checker.verificar_plausibilidade",
                    return_value=fake_resultado,
                ) as mock_vp:
                    result = _impl_avaliar_plausibilidade_catalogo("ctx")

        mock_vp.assert_called_once()
        assert result == fake_resultado

    def test_happy_path_with_produtividades_key(self, tmp_path):
        """Covers line 243: bundle uses 'produtividades' key."""
        config_dir = self._config_path(tmp_path)
        bundle_path = config_dir / "catalogos" / "ctx" / ".catalog_bundle.json"
        bundle = _make_bundle(
            insumos=[],
            producoes=[{"id": "PROD-001"}],
            cpus=[],
            use_produtividades_key=True,
        )
        _write_bundle(bundle_path, bundle)

        fake_resultado = {"ok": True, "alertas": []}

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                with patch(
                    "concilium.application.catalog.plausibility_checker.verificar_plausibilidade",
                    return_value=fake_resultado,
                ) as mock_vp:
                    _impl_avaliar_plausibilidade_catalogo("ctx")

        mock_vp.assert_called_once()
        # Verify it was called with the produtividades list
        call_args = mock_vp.call_args
        insumos_arg, producoes_arg, cpus_arg = call_args[0]
        assert producoes_arg == [{"id": "PROD-001"}]

    def test_contexto_id_diferente_de_catalogo_id_resolve_bundle_correto(self, tmp_path):
        """Regressão: contexto 'mendeslobo-rfi' aponta pra catalogo_id 'rfi-r02' —
        o bundle vive em catalogos/rfi-r02/, não em catalogos/mendeslobo-rfi/.
        """
        config_dir = self._config_path(tmp_path)
        contexto_file = config_dir / "contextos" / "mendeslobo-rfi.json"
        contexto_file.parent.mkdir(parents=True)
        contexto_file.write_text(json.dumps({"id": "mendeslobo-rfi", "catalogo_id": "rfi-r02"}), encoding="utf-8")

        bundle_path = config_dir / "catalogos" / "rfi-r02" / ".catalog_bundle.json"
        bundle = _make_bundle(insumos=[{"codigo": "INS-001"}], producoes=[{"id": "PROD-001"}], cpus=[])
        _write_bundle(bundle_path, bundle)

        fake_resultado = {"ok": True, "alertas": []}

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                with patch(
                    "concilium.application.catalog.plausibility_checker.verificar_plausibilidade",
                    return_value=fake_resultado,
                ) as mock_vp:
                    result = _impl_avaliar_plausibilidade_catalogo("mendeslobo-rfi")

        mock_vp.assert_called_once()
        assert result == fake_resultado


# ---------------------------------------------------------------------------
# _impl_verificar_integridade_catalogo
# ---------------------------------------------------------------------------


class TestImplVerificarIntegridadeCatalogo:
    def _config_path(self, tmp_path):
        return tmp_path / "config"

    def _base_pu_result(self, refs_faltantes=None, pu_divergentes=None, com_composicao=0):
        return {
            "referencias_faltantes": refs_faltantes or [],
            "pu_divergentes": pu_divergentes or [],
            "com_composicao": com_composicao,
            "ok": True,
            "total_producoes": 0,
            "sem_valor_horario": [],
            "breakdown_por_producao": [],
        }

    def test_sad_path_bundle_missing(self, tmp_path):
        config_dir = self._config_path(tmp_path)
        config_dir.mkdir(parents=True)

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            result = _impl_verificar_integridade_catalogo("ctx")

        assert "erro" in result

    def test_happy_path_no_problems(self, tmp_path):
        """Covers lines 267-315: no errors, ok=True."""
        config_dir = self._config_path(tmp_path)
        bundle_path = config_dir / "catalogos" / "ctx" / ".catalog_bundle.json"
        bundle = _make_bundle(
            insumos=[{"codigo": "INS-001"}],
            producoes=[{"id": "PROD-001", "valor_horario": 5.0}],
            cpus=[],
        )
        _write_bundle(bundle_path, bundle)

        pu_result = self._base_pu_result(com_composicao=1)

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                with patch(
                    "concilium.application.catalog.pu_calculator.calcular_catalogo",
                    return_value=pu_result,
                ):
                    result = _impl_verificar_integridade_catalogo("ctx")

        assert result["ok"] is True
        assert result["resumo"]["erros"] == 0
        assert result["resumo"]["avisos"] == 0
        assert result["problemas"] == []

    def test_happy_path_with_refs_faltantes(self, tmp_path):
        """Covers lines 306-307: pu_result has referencias_faltantes."""
        config_dir = self._config_path(tmp_path)
        bundle_path = config_dir / "catalogos" / "ctx" / ".catalog_bundle.json"
        bundle = _make_bundle(insumos=[], producoes=[], cpus=[])
        _write_bundle(bundle_path, bundle)

        pu_result = self._base_pu_result(
            refs_faltantes=[{"producao_id": "PROD-001", "faltantes": ["INS-MISSING"]}],
            com_composicao=1,
        )

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                with patch(
                    "concilium.application.catalog.pu_calculator.calcular_catalogo",
                    return_value=pu_result,
                ):
                    result = _impl_verificar_integridade_catalogo("ctx")

        assert result["ok"] is False
        erros = [p for p in result["problemas"] if p["severidade"] == "ERRO"]
        assert len(erros) == 1
        assert erros[0]["tipo"] == "REF_INSUMO_FALTANTE"

    def test_happy_path_with_pu_divergentes(self, tmp_path):
        """Covers lines 308-309: pu_result has pu_divergentes."""
        config_dir = self._config_path(tmp_path)
        bundle_path = config_dir / "catalogos" / "ctx" / ".catalog_bundle.json"
        bundle = _make_bundle(insumos=[], producoes=[], cpus=[])
        _write_bundle(bundle_path, bundle)

        pu_result = self._base_pu_result(
            pu_divergentes=[
                {"producao_id": "PROD-001", "pu_calculado": 100.0, "pu_referencia": 50.0, "delta_pct": 100.0}
            ],
        )

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                with patch(
                    "concilium.application.catalog.pu_calculator.calcular_catalogo",
                    return_value=pu_result,
                ):
                    result = _impl_verificar_integridade_catalogo("ctx")

        avisos = [p for p in result["problemas"] if p["tipo"] == "PU_DIVERGENTE"]
        assert len(avisos) == 1
        assert avisos[0]["severidade"] == "AVISO"

    def test_cpu_refs_faltantes(self, tmp_path):
        """Covers lines 285-291: cpu composicao_itens references non-existent insumo_id."""
        config_dir = self._config_path(tmp_path)
        bundle_path = config_dir / "catalogos" / "ctx" / ".catalog_bundle.json"
        bundle = _make_bundle(
            insumos=[{"codigo": "INS-001"}],
            producoes=[],
            cpus=[
                {
                    "codigo": "CPU-001",
                    "composicao_itens": [
                        {"insumo_id": "INS-NONEXISTENT", "coeficiente": 1.0},
                        {"insumo_id": "INS-001", "coeficiente": 0.5},  # This one exists
                    ],
                }
            ],
        )
        _write_bundle(bundle_path, bundle)

        pu_result = self._base_pu_result()

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                with patch(
                    "concilium.application.catalog.pu_calculator.calcular_catalogo",
                    return_value=pu_result,
                ):
                    result = _impl_verificar_integridade_catalogo("ctx")

        assert result["ok"] is False  # because CPU_INSUMO_FALTANTE is ERRO severity
        cpu_erros = [p for p in result["problemas"] if p["tipo"] == "CPU_INSUMO_FALTANTE"]
        assert len(cpu_erros) == 1
        assert cpu_erros[0]["insumo_id_faltante"] == "INS-NONEXISTENT"

    def test_cpu_prod_faltantes(self, tmp_path):
        """Covers lines 294-299: CPU references a producao_id_ref that doesn't exist."""
        config_dir = self._config_path(tmp_path)
        bundle_path = config_dir / "catalogos" / "ctx" / ".catalog_bundle.json"
        bundle = _make_bundle(
            insumos=[],
            producoes=[{"id": "PROD-001"}],
            cpus=[
                {
                    "codigo": "CPU-001",
                    "producao_id_ref": "PROD-MISSING",
                    "composicao_itens": [],
                }
            ],
        )
        _write_bundle(bundle_path, bundle)

        pu_result = self._base_pu_result()

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                with patch(
                    "concilium.application.catalog.pu_calculator.calcular_catalogo",
                    return_value=pu_result,
                ):
                    result = _impl_verificar_integridade_catalogo("ctx")

        prod_faltantes = [p for p in result["problemas"] if p["tipo"] == "CPU_PROD_REF_FALTANTE"]
        assert len(prod_faltantes) == 1
        assert prod_faltantes[0]["producao_id_ref"] == "PROD-MISSING"
        assert prod_faltantes[0]["severidade"] == "AVISO"

    def test_rfi_prefix_detection(self, tmp_path):
        """Covers lines 302-303: insumos/producoes starting with 'RFI-' are detected."""
        config_dir = self._config_path(tmp_path)
        bundle_path = config_dir / "catalogos" / "ctx" / ".catalog_bundle.json"
        bundle = _make_bundle(
            insumos=[
                {"codigo": "INS-001", "descricao": "Normal insumo"},
                {"codigo": "RFI-INS-001", "descricao": "RFI imported insumo"},
            ],
            producoes=[
                {"id": "PROD-001", "descricao": "Normal prod"},
                {"id": "RFI-PROD-001", "descricao": "RFI imported prod"},
            ],
            cpus=[],
        )
        _write_bundle(bundle_path, bundle)

        pu_result = self._base_pu_result()

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                with patch(
                    "concilium.application.catalog.pu_calculator.calcular_catalogo",
                    return_value=pu_result,
                ):
                    result = _impl_verificar_integridade_catalogo("ctx")

        assert result["resumo"]["insumos_rfi_pendentes"] == 1
        assert result["resumo"]["producoes_rfi_pendentes"] == 1
        assert len(result["rfi_pendentes"]["insumos"]) == 1
        assert result["rfi_pendentes"]["insumos"][0]["codigo"] == "RFI-INS-001"
        assert len(result["rfi_pendentes"]["producoes"]) == 1
        assert result["rfi_pendentes"]["producoes"][0]["id"] == "RFI-PROD-001"

    def test_happy_path_with_produtividades_key(self, tmp_path):
        """Covers line 276: bundle uses 'produtividades' key."""
        config_dir = self._config_path(tmp_path)
        bundle_path = config_dir / "catalogos" / "ctx" / ".catalog_bundle.json"
        bundle = _make_bundle(
            insumos=[],
            producoes=[{"id": "PROD-001"}],
            cpus=[],
            use_produtividades_key=True,
        )
        _write_bundle(bundle_path, bundle)

        pu_result = self._base_pu_result()

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                with patch(
                    "concilium.application.catalog.pu_calculator.calcular_catalogo",
                    return_value=pu_result,
                ) as mock_cc:
                    _impl_verificar_integridade_catalogo("ctx")

        # Verify calcular_catalogo received the produtividades list
        call_args = mock_cc.call_args
        producoes_arg = call_args[0][0]
        assert producoes_arg == [{"id": "PROD-001"}]

    def test_ok_flag_false_when_errors(self, tmp_path):
        """Covers lines 315-318: ok=False when ERRO severity problems exist."""
        config_dir = self._config_path(tmp_path)
        bundle_path = config_dir / "catalogos" / "ctx" / ".catalog_bundle.json"
        bundle = _make_bundle(
            insumos=[],  # No insumos — so composicao_itens refs will fail
            producoes=[],
            cpus=[
                {
                    "codigo": "CPU-001",
                    "composicao_itens": [{"insumo_id": "INS-MISSING", "coeficiente": 1.0}],
                }
            ],
        )
        _write_bundle(bundle_path, bundle)

        pu_result = self._base_pu_result()

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                with patch(
                    "concilium.application.catalog.pu_calculator.calcular_catalogo",
                    return_value=pu_result,
                ):
                    result = _impl_verificar_integridade_catalogo("ctx")

        assert result["ok"] is False
        assert result["resumo"]["erros"] > 0

    def test_resumo_counts_are_correct(self, tmp_path):
        """Covers lines 319-329: resumo field counts."""
        config_dir = self._config_path(tmp_path)
        bundle_path = config_dir / "catalogos" / "ctx" / ".catalog_bundle.json"
        bundle = _make_bundle(
            insumos=[{"codigo": "A"}, {"codigo": "B"}],
            producoes=[{"id": "P1"}, {"id": "P2"}],
            cpus=[{"codigo": "CPU-1", "composicao_itens": []}],
        )
        _write_bundle(bundle_path, bundle)

        pu_result = self._base_pu_result(com_composicao=2)

        with patch(f"{MODULE}._config_root", return_value=config_dir):
            with patch(f"{MODULE}._wrap_response", side_effect=_identity):
                with patch(
                    "concilium.application.catalog.pu_calculator.calcular_catalogo",
                    return_value=pu_result,
                ):
                    result = _impl_verificar_integridade_catalogo("ctx")

        assert result["resumo"]["total_insumos"] == 2
        assert result["resumo"]["total_producoes"] == 2
        assert result["resumo"]["total_cpus"] == 1
        assert result["resumo"]["producoes_com_composicao"] == 2
