"""Testes para `_warm_up_catalogos_background` (server.py) — issue #153 follow-up.

Pré-carrega catálogos com backend remoto (SharePoint/S3/...) em thread separada
durante o startup do servidor, pra que a primeira request REAL do usuário
encontre o cache local já quente em vez de pagar o cold-load inteiro
(`_catalog_storage.load_catalogo_via_storage`, TTL de 1h). Best-effort: nenhum
cenário aqui deve propagar exceção — uma falha de warm-up nunca pode derrubar
o startup do servidor.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from concilium.presentation.mcp import server as mod

_BACKEND_TARGET = "concilium.application.runtime.mixins._catalog_storage.catalog_storage_backend"


def _write_contextos(contextos_dir: Path, ids: list[str]) -> None:
    contextos_dir.mkdir(parents=True, exist_ok=True)
    for cid in ids:
        (contextos_dir / f"{cid}.json").write_text("{}", encoding="utf-8")


class TestWarmUpCatalogosBackground:
    def test_backend_filesystem_e_no_op(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Backend "filesystem" já é rápido (leitura local) — nem chega a
        instanciar o Runtime."""
        monkeypatch.setattr(_BACKEND_TARGET, lambda: "filesystem")
        rt = MagicMock()
        monkeypatch.setattr(mod, "_runtime", lambda: rt)

        mod._warm_up_catalogos_background()

        rt.load_contexto.assert_not_called()
        rt.load_catalogo.assert_not_called()

    def test_contextos_dir_ausente_e_no_op(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(_BACKEND_TARGET, lambda: "sharepoint")
        monkeypatch.setattr(mod, "_config_root", lambda: tmp_path / "nao-existe")
        rt = MagicMock()
        monkeypatch.setattr(mod, "_runtime", lambda: rt)

        mod._warm_up_catalogos_background()

        rt.load_catalogo.assert_not_called()

    def test_carrega_cada_catalogo_id_unico_uma_vez(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """ctx1 e ctx3 apontam pro mesmo catalogo_id ("mendeslobo") — deve
        carregar só uma vez, não uma por contexto."""
        _write_contextos(tmp_path / "contextos", ["ctx1", "ctx2", "ctx3"])
        catalogo_por_contexto = {"ctx1": "mendeslobo", "ctx2": "rfi-r02", "ctx3": "mendeslobo"}

        rt = MagicMock()

        def _load_contexto(contexto_id: str):
            ctx = MagicMock()
            ctx.catalogo_id = catalogo_por_contexto[contexto_id]
            return ctx

        rt.load_contexto.side_effect = _load_contexto

        monkeypatch.setattr(_BACKEND_TARGET, lambda: "sharepoint")
        monkeypatch.setattr(mod, "_config_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "_runtime", lambda: rt)

        mod._warm_up_catalogos_background()

        carregados = sorted(call.args[0] for call in rt.load_catalogo.call_args_list)
        assert carregados == ["mendeslobo", "rfi-r02"]

    def test_falha_em_um_catalogo_nao_impede_os_demais(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        _write_contextos(tmp_path / "contextos", ["ctx1", "ctx2"])
        catalogo_por_contexto = {"ctx1": "quebrado", "ctx2": "ok"}

        rt = MagicMock()

        def _load_contexto(contexto_id: str):
            ctx = MagicMock()
            ctx.catalogo_id = catalogo_por_contexto[contexto_id]
            return ctx

        def _load_catalogo(catalogo_id: str):
            if catalogo_id == "quebrado":
                raise RuntimeError("Graph indisponível")
            return {"cpus": []}

        rt.load_contexto.side_effect = _load_contexto
        rt.load_catalogo.side_effect = _load_catalogo

        monkeypatch.setattr(_BACKEND_TARGET, lambda: "sharepoint")
        monkeypatch.setattr(mod, "_config_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "_runtime", lambda: rt)

        mod._warm_up_catalogos_background()  # não deve lançar

        carregados = sorted(call.args[0] for call in rt.load_catalogo.call_args_list)
        assert carregados == ["ok", "quebrado"]

    def test_falha_ao_resolver_contexto_individual_e_ignorada(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Um contexto malformado (`rt.load_contexto` lança) não impede o
        warm-up dos demais — só pula esse contexto."""
        _write_contextos(tmp_path / "contextos", ["ctx-quebrado", "ctx-ok"])

        rt = MagicMock()

        def _load_contexto(contexto_id: str):
            if contexto_id == "ctx-quebrado":
                raise RuntimeError("contexto malformado")
            ctx = MagicMock()
            ctx.catalogo_id = "cat-ok"
            return ctx

        rt.load_contexto.side_effect = _load_contexto

        monkeypatch.setattr(_BACKEND_TARGET, lambda: "sharepoint")
        monkeypatch.setattr(mod, "_config_root", lambda: tmp_path)
        monkeypatch.setattr(mod, "_runtime", lambda: rt)

        mod._warm_up_catalogos_background()

        rt.load_catalogo.assert_called_once_with("cat-ok")

    def test_falha_inesperada_no_setup_nao_propaga(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mesmo uma falha fora do loop principal (ex.: erro ao resolver o
        backend) fica contida — warm-up nunca pode derrubar o startup."""
        monkeypatch.setattr(_BACKEND_TARGET, MagicMock(side_effect=RuntimeError("boom")))

        mod._warm_up_catalogos_background()  # não deve lançar
