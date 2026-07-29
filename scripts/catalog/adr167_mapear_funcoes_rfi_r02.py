"""ADR-167 F2: mapeamento função→item específico no catálogo rfi-r02 (contexto mendeslobo-rfi).

Mesmo mapeamento semântico confirmado pelo usuário para mendeslobo (ADR-166 D4),
reaplicado sobre o roster PRÓPRIO do rfi-r02 — que não tem aliases de código
(nenhum `MO-*`/`AGIS-FN-*`/`SV-*`, só `P0xxx` bare), então não precisa da etapa
de agrupamento por descrição normalizada do script da ADR-166. `P0083` (Soldador)
não existe em rfi-r02 — o grupo "esmeril" fica só com mecânico/aux. mecânico/
borracheiro.

Uso:
    python scripts/catalog/adr167_mapear_funcoes_rfi_r02.py --dry-run
    python scripts/catalog/adr167_mapear_funcoes_rfi_r02.py --apply
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

CONTEXTO_ID = "mendeslobo-rfi"
CATALOGO_ID = "rfi-r02"
ACTOR_CRIADOR = "adr167-mapeamento-funcoes-rfi"
ACTOR_APROVADOR = "adr167-mapeamento-funcoes-rfi-aprovador"

# Grupos de função (códigos bare P0xxx — sem aliases neste catálogo).
_MAQUINAS = [
    "P0040", "P0041", "P0042", "P0043", "P0044", "P0045", "P0046", "P0047",
    "P0048", "P0049", "P0050", "P0069", "P0081", "P0082", "P0085", "P0090", "P0091",
]
_MOTOSSERRA = ["P0062"]
_TRANSITO = ["P0032", "P0033", "P0034", "P0035", "P0036", "P0071", "P0079", "P0089"]
_QUIMICOS = ["P0009", "P0030", "P0041", "P0053"]
_ALTURA = ["P0005", "P0015", "P0016", "P0037", "P0038"]
_ESMERIL = ["P0011", "P0014", "P0073"]  # P0083 (Soldador) não existe neste catálogo


def _validar_codigos_existem(config_root: Path, codigos: set[str]) -> None:
    mo_dir = config_root / "catalogos" / CATALOGO_ID / "insumos" / "mao_obra"
    existentes = {json.loads(p.read_text(encoding="utf-8"))["codigo"] for p in mo_dir.glob("*.json")}
    faltando = codigos - existentes
    if faltando:
        raise RuntimeError(f"Códigos ausentes em {CATALOGO_ID}: {sorted(faltando)}")


def _atualizacoes() -> list[dict[str, Any]]:
    return [
        {"insumo_id": "TRE-NR12-MAQUINAS", "novos_funcoes_aplicaveis": sorted(_MAQUINAS)},
        {"insumo_id": "EPI-ABAFADOR-CONCHA", "novos_funcoes_aplicaveis": sorted(set(_MAQUINAS) | set(_MOTOSSERRA))},
        {"insumo_id": "TRE-OP-MOTOSSERRA", "novos_funcoes_aplicaveis": sorted(_MOTOSSERRA)},
        {"insumo_id": "TRE-OP-MOTOPODA", "novos_funcoes_aplicaveis": sorted(_MOTOSSERRA)},
        {"insumo_id": "EPI-ROUPA-MOTOSSERRA", "novos_funcoes_aplicaveis": sorted(_MOTOSSERRA)},
        {"insumo_id": "EPI-PERNEIRA", "novos_funcoes_aplicaveis": sorted(_MOTOSSERRA)},
        {"insumo_id": "TRE-PLANO-TRANSITO", "novos_funcoes_aplicaveis": sorted(_TRANSITO)},
        {"insumo_id": "TRE-PRODUTOS-QUIMICOS", "novos_funcoes_aplicaveis": sorted(_QUIMICOS)},
        {"insumo_id": "TRE-NR35-ALTURA", "novos_funcoes_aplicaveis": sorted(_ALTURA)},
        {"insumo_id": "EPI-PROTETOR-FACIAL", "novos_funcoes_aplicaveis": sorted(_ESMERIL)},
        {"insumo_id": "TRE-NR22-MINERACAO", "novos_funcoes_aplicaveis": []},
    ]


def _register_tools(config_root: Path) -> dict[str, Any]:
    from mcp.server.fastmcp import FastMCP

    os.environ["CONCILIUM__CONFIG_ROOT"] = str(config_root)
    from concilium.infrastructure.settings._storage import _reset_storage

    _reset_storage()

    mod = importlib.import_module("concilium.presentation.mcp.tools.catalogo")
    importlib.reload(mod)
    server: Any = FastMCP("adr167-mapeamento-funcoes-rfi")
    mod.register(server)
    tools: dict[str, Any] = {}
    for t in server._tool_manager.list_tools():
        fn = getattr(t, "fn", None) or getattr(t, "func", None)
        tools[t.name] = fn
    return tools


def run(config_root: Path) -> dict[str, Any]:
    from concilium.infrastructure.auth.permission_guard import reset_auth_context, set_auth_context, set_roles

    todos_codigos = set()
    for grupo in (_MAQUINAS, _MOTOSSERRA, _TRANSITO, _QUIMICOS, _ALTURA, _ESMERIL):
        todos_codigos.update(grupo)
    _validar_codigos_existem(config_root, todos_codigos)

    tools = _register_tools(config_root)

    set_roles(["catalog-manager"])
    tokens = set_auth_context(user_id=ACTOR_CRIADOR, tenant_id=None)
    try:
        rascunho_resp = tools["criar_rascunho_catalogo"](
            contexto_id=CONTEXTO_ID,
            descricao="ADR-167: mapeamento função->item específico (rfi-r02)",
        )
        if "rascunho_id" not in rascunho_resp:
            raise RuntimeError(f"criar_rascunho_catalogo falhou: {rascunho_resp}")
        rascunho_id = rascunho_resp["rascunho_id"]

        lote_resp = tools["atualizar_precos_insumos_lote"](
            contexto_id=CONTEXTO_ID, rascunho_id=rascunho_id, itens=_atualizacoes()
        )
        tools["listar_divergencias_rascunho"](contexto_id=CONTEXTO_ID, rascunho_id=rascunho_id)
    finally:
        reset_auth_context(tokens)

    tokens = set_auth_context(user_id=ACTOR_APROVADOR, tenant_id=None)
    try:
        merge_resp = tools["aprovar_merge_catalogo"](
            contexto_id=CONTEXTO_ID,
            rascunho_id=rascunho_id,
            justificativa="ADR-167: mapeamento função->item específico confirmado pelo usuário (rfi-r02)",
        )
    finally:
        reset_auth_context(tokens)

    return {"rascunho_id": rascunho_id, "lote": lote_resp, "merge": merge_resp}


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-167 F2: mapeamento função->item específico em rfi-r02")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="roda contra cópia temporária de config/")
    group.add_argument("--apply", action="store_true", help="grava de fato em config/catalogos/rfi-r02")
    args = parser.parse_args()

    if args.dry_run:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_config = Path(tmp) / "config"
            shutil.copytree(REPO_ROOT / "config", tmp_config)
            result = run(tmp_config)
        modo = "DRY-RUN (cópia temporária, descartada)"
    else:
        result = run(REPO_ROOT / "config")
        modo = "APLICADO em config/catalogos/rfi-r02"

    lote = result["lote"]
    print(f"[{modo}]")
    print(f"  rascunho_id : {result['rascunho_id']}")
    for r in lote.get("resultados", []):
        linha = f"    {r['insumo_id']}: {r['status']}"
        if r["status"] != "ok":
            linha += f" — {r.get('erro')}"
        print(linha)
    print(f"  merge       : {result['merge']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
