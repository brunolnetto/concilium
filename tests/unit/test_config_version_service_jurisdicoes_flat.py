from __future__ import annotations

import json
from pathlib import Path

from concilium.application.services.contexto_version_service import JurisdictionVersionService


def test_list_jurisdicoes_includes_flat_files(tmp_path: Path) -> None:
    root = tmp_path / "config"
    jur = root / "jurisdicoes"
    jur.mkdir(parents=True)

    (jur / "BR-SC.json").write_text(
        json.dumps({"codigo": "BR-SC", "nome": "Brasil - Santa Catarina"}),
        encoding="utf-8",
    )

    svc = JurisdictionVersionService(root)
    ids = {item.get("id") for item in svc.list_jurisdicoes()}
    assert "BR-SC" in ids


def test_create_version_from_flat_jurisdicao_bootstraps_base(tmp_path: Path) -> None:
    root = tmp_path / "config"
    jur = root / "jurisdicoes"
    jur.mkdir(parents=True)

    (jur / "BR-GO.json").write_text(
        json.dumps(
            {
                "codigo": "BR-GO",
                "nome": "Brasil - Goias",
                "motor_tributario_bdi": {"aliquotas": {"ISS": 0.05}},
            }
        ),
        encoding="utf-8",
    )

    svc = JurisdictionVersionService(root)
    created = svc.create_version(
        "BR-GO",
        fields={"provedores_referencia": [{"id": "SINAPI", "data_referencia": "2026-04"}]},
        motivo="update",
        author="tester",
    )

    assert created["version"] == "v1"
    assert created["codigo"] == "BR-GO"
    assert created["provedores_referencia"][0]["id"] == "SINAPI"
    assert (jur / "BR-GO" / "versions" / "v1.json").exists()
    assert (jur / "BR-GO" / "current").read_text(encoding="utf-8").strip() == "v1"


def test_flat_and_versioned_same_id_are_deduplicated_in_list(tmp_path: Path) -> None:
    root = tmp_path / "config"
    jur = root / "jurisdicoes"
    jur.mkdir(parents=True)

    # Flat definition
    (jur / "BR-DF.json").write_text(
        json.dumps({"codigo": "BR-DF", "nome": "Distrito Federal (flat)"}),
        encoding="utf-8",
    )

    # Versioned definition with same logical id
    vdir = jur / "BR-DF"
    (vdir / "versions").mkdir(parents=True)
    (vdir / "current").write_text("v1", encoding="utf-8")
    (vdir / "meta.json").write_text(
        json.dumps({"id": "BR-DF", "nome": "Distrito Federal (versioned)", "current_version": "v1"}),
        encoding="utf-8",
    )
    (vdir / "versions" / "v1.json").write_text(
        json.dumps({"version": "v1", "nome": "Distrito Federal (versioned)"}),
        encoding="utf-8",
    )

    svc = JurisdictionVersionService(root)
    items = [item for item in svc.list_jurisdicoes() if item.get("id") == "BR-DF"]
    assert len(items) == 1
    assert items[0].get("current_version") == "v1"


def test_resolve_prefers_versioned_over_flat_when_both_exist(tmp_path: Path) -> None:
    root = tmp_path / "config"
    jur = root / "jurisdicoes"
    jur.mkdir(parents=True)

    (jur / "BR-RJ.json").write_text(
        json.dumps({"codigo": "BR-RJ", "nome": "Rio de Janeiro (flat)", "origem": "flat"}),
        encoding="utf-8",
    )

    vdir = jur / "BR-RJ"
    (vdir / "versions").mkdir(parents=True)
    (vdir / "current").write_text("v2", encoding="utf-8")
    (vdir / "meta.json").write_text(
        json.dumps({"id": "BR-RJ", "nome": "Rio de Janeiro", "current_version": "v2"}),
        encoding="utf-8",
    )
    (vdir / "versions" / "v1.json").write_text(
        json.dumps({"version": "v1", "origem": "versioned_v1"}),
        encoding="utf-8",
    )
    (vdir / "versions" / "v2.json").write_text(
        json.dumps({"version": "v2", "origem": "versioned_v2"}),
        encoding="utf-8",
    )

    svc = JurisdictionVersionService(root)
    current = svc.resolve("BR-RJ")
    assert current is not None
    assert current.get("origem") == "versioned_v2"

    explicit = svc.resolve("BR-RJ", "v1")
    assert explicit is not None
    assert explicit.get("origem") == "versioned_v1"


def test_list_versions_prefers_versioned_when_flat_also_exists(tmp_path: Path) -> None:
    root = tmp_path / "config"
    jur = root / "jurisdicoes"
    jur.mkdir(parents=True)

    (jur / "BR-PA.json").write_text(json.dumps({"codigo": "BR-PA", "nome": "Para"}), encoding="utf-8")

    vdir = jur / "BR-PA"
    (vdir / "versions").mkdir(parents=True)
    (vdir / "current").write_text("v2", encoding="utf-8")
    (vdir / "versions" / "v1.json").write_text(
        json.dumps({"version": "v1", "motivo": "init"}),
        encoding="utf-8",
    )
    (vdir / "versions" / "v2.json").write_text(
        json.dumps({"version": "v2", "motivo": "update"}),
        encoding="utf-8",
    )

    svc = JurisdictionVersionService(root)
    versions = svc.list_versions("BR-PA")
    assert [v.get("version") for v in versions] == ["v1", "v2"]
