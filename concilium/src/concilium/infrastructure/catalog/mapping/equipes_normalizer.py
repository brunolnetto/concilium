"""Normaliza CPUs materializando equipe local a partir da producao referenciada.

Migrado de scripts/normalize_cpu_equipes_from_producoes.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_DEFAULT_ROOT = Path(__file__).resolve().parents[5]


@dataclass
class AuditRow:
    cpu: str
    producao_id: str
    status: str  # ok | erro | normalizar
    detalhe: str


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _has_local_team(cpu: dict[str, Any]) -> bool:
    comp = cpu.get("equipe") or cpu.get("composicao_padrao_equipe") or {}
    return isinstance(comp, dict) and bool(comp.get("funcoes") or comp.get("equipamentos"))


def _extract_prod_team(prod: dict[str, Any]) -> dict[str, Any] | None:
    comp = prod.get("equipe") or prod.get("composicao_padrao_equipe") or {}
    if not isinstance(comp, dict):
        return None
    return comp if (comp.get("funcoes") or comp.get("equipamentos")) else None


def normalize_equipes_from_producoes(
    catalog_root: Path | None = None,
    *,
    apply: bool = False,
    cpu_filter: str | None = None,
) -> list[AuditRow]:
    """Audita/normaliza CPUs, materializando equipe local da produção referenciada.

    Args:
        catalog_root: raiz do catálogo (padrão: config/catalogos/mendeslobo)
        apply: se True, persiste alterações nas CPUs
        cpu_filter: filtra por código exato de CPU

    Returns:
        Lista de AuditRow com resultado por CPU.
    """
    r = catalog_root or (_DEFAULT_ROOT / "config" / "catalogos" / "mendeslobo")
    cpus_dir = r / "cpus"
    prods_dir = r / "producoes"

    producoes: dict[str, dict[str, Any]] = {}
    for prod_file in sorted(prods_dir.glob("*.json")):
        prod = _load_json(prod_file)
        prod_id = prod.get("id")
        if isinstance(prod_id, str) and prod_id:
            producoes[prod_id] = prod

    rows: list[AuditRow] = []
    for cpu_file in sorted(cpus_dir.glob("*.json")):
        cpu = _load_json(cpu_file)
        cpu_code = cpu.get("codigo")
        if not isinstance(cpu_code, str) or not cpu_code:
            continue
        if cpu_filter and cpu_code != cpu_filter:
            continue

        prod_id = cpu.get("producao_id")
        if not isinstance(prod_id, str) or not prod_id:
            continue

        if _has_local_team(cpu):
            rows.append(AuditRow(cpu=cpu_code, producao_id=prod_id, status="ok", detalhe="cpu_ja_tem_equipe"))
            continue

        prod = producoes.get(prod_id)  # type: ignore[assignment]
        if not prod:
            rows.append(AuditRow(cpu=cpu_code, producao_id=prod_id, status="erro", detalhe="producao_id_inexistente"))
            continue

        prod_team = _extract_prod_team(prod)
        if not prod_team:
            rows.append(AuditRow(cpu=cpu_code, producao_id=prod_id, status="erro", detalhe="producao_sem_equipe"))
            continue

        rows.append(
            AuditRow(cpu=cpu_code, producao_id=prod_id, status="normalizar", detalhe="copiar_equipe_da_producao")
        )
        if apply:
            cpu["equipe"] = prod_team
            _dump_json(cpu_file, cpu)

    return rows
