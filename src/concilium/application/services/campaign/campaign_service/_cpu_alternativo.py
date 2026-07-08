"""ADR-070 — Campaign service (parte extraída de campaign_service.py)."""

from __future__ import annotations

import json
from pathlib import Path

from concilium.domain.models.campaign.campaign import ParametroSweep


def listar_cpus_alternativos(cpu_id: str, config_root: Path) -> list[str]:
    """Retorna lista de cpu_ids alternativos declarados no JSON do catálogo.

    Um CPU alternativo é aquele listado em ``cpus_alternativos`` do JSON do CPU
    corrente. Requer campo ``cpus_alternativos: [str]`` populado no catálogo
    (ADR-070 Classe 4 / F4).

    Returns lista vazia se o CPU não existir ou não declarar alternativas.
    """
    cpu_path = config_root / "catalogos" / "mendeslobo" / "cpus" / f"{cpu_id}.json"
    if not cpu_path.exists():
        # Tenta raízes secundárias (test, samples)
        for sub in ("test", "samples"):
            alt = config_root / "catalogos" / sub / "cpus" / f"{cpu_id}.json"
            if alt.exists():
                cpu_path = alt
                break
        else:
            return []
    try:
        d = json.loads(cpu_path.read_text(encoding="utf-8"))
        alts = d.get("cpus_alternativos") or []
        return [str(a) for a in alts if a]
    except Exception:
        return []


def sugerir_levers_cpu_alternativo(
    base_spec: dict,
    config_root: Path,
) -> list[ParametroSweep]:
    """Gera levers Classe 4 para todos os itens do EAP que têm CPUs alternativos.

    Para cada item da EAP cujo ``cpu_id`` declara ``cpus_alternativos`` no
    catálogo, cria um ``ParametroSweep`` com scope ``cpu_alternativo`` listando
    o CPU original + os alternativos como valores.

    Exemplo de resultado:
        ParametroSweep(
            campo="spec.eap.[*].cpu_id",
            valores=["CPU-TERRA-ESCO-CARGA-2CAT-DMT2000",
                     "CPU-TERRA-ESCO-CARGA-2CAT-DMT3000"],
            scope="cpu_alternativo",
            item_ids=["eap-1_5"],
        )
    """
    spec_inner = base_spec.get("spec") or base_spec
    eap = spec_inner.get("eap") or []
    levers: list[ParametroSweep] = []

    for item in eap:
        if not isinstance(item, dict):
            continue
        item_id = item.get("item_id")
        cpu_id = item.get("cpu_id")
        if not item_id or not cpu_id:
            continue
        alts = listar_cpus_alternativos(cpu_id, config_root)
        if not alts:
            continue
        levers.append(
            ParametroSweep(
                campo="spec.eap.[*].cpu_id",
                valores=[cpu_id] + alts,  # inclui o original como primeira opção
                scope="cpu_alternativo",
                item_ids=[item_id],
            )
        )
    return levers


