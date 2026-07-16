"""ADR-141 D2: _list_versions expõe flags de rascunho/rejeição quando presentes."""

from __future__ import annotations

import json
from pathlib import Path

from concilium.application.services.catalog.contexto_version_service import ContextoVersionService


def _write_version(root: Path, contexto_id: str, version: str, data: dict) -> None:
    versions_dir = root / "contextos" / contexto_id / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    payload = {"version": version, "created_at": "2026-07-16T00:00:00", "created_by": "engineer1", **data}
    (versions_dir / f"{version}.json").write_text(json.dumps(payload), encoding="utf-8")


class TestListVersionsExposesRascunhoFlags:
    def test_rascunho_flag_included_when_present(self, tmp_path: Path):
        _write_version(
            tmp_path,
            "mendeslobo",
            "v2",
            {"motivo": "rascunho: reajuste", "_rascunho": True, "_rascunho_descricao": "reajuste"},
        )
        svc = ContextoVersionService(tmp_path)

        versions = svc.list_versions("mendeslobo")

        assert len(versions) == 1
        assert versions[0]["_rascunho"] is True
        assert versions[0]["_rascunho_descricao"] == "reajuste"

    def test_rejeitado_flags_included_when_present(self, tmp_path: Path):
        _write_version(
            tmp_path,
            "mendeslobo",
            "v3",
            {
                "_rascunho": True,
                "_rejeitado": True,
                "_motivo_rejeicao": "preço fora da faixa",
                "_rejeitado_por": "catalog_mgr1",
            },
        )
        svc = ContextoVersionService(tmp_path)

        versions = svc.list_versions("mendeslobo")

        assert versions[0]["_rejeitado"] is True
        assert versions[0]["_motivo_rejeicao"] == "preço fora da faixa"
        assert versions[0]["_rejeitado_por"] == "catalog_mgr1"

    def test_flags_absent_when_not_a_rascunho(self, tmp_path: Path):
        """Versão normal (não-rascunho) não ganha nenhuma dessas chaves — mudança é aditiva."""
        _write_version(tmp_path, "mendeslobo", "v1", {"motivo": "base"})
        svc = ContextoVersionService(tmp_path)

        versions = svc.list_versions("mendeslobo")

        entry = versions[0]
        assert "_rascunho" not in entry
        assert "_rejeitado" not in entry
        assert "_motivo_rejeicao" not in entry
        assert "_rejeitado_por" not in entry
