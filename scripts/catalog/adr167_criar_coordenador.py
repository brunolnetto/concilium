"""ADR-167 F1: cria o cargo "Coordenador" (P0092, PJ, R$12.500/mês) em mendeslobo e rfi-r02.

Fecha a lacuna que impedia consertar a verba ADM lump (`_composicao_default_por_categoria`,
item "Coordenador" hardcoded) — o cargo não existia em nenhum dos dois catálogos.
Código `P0092` escolhido por ser o menor número livre em ambos os rosters
(mendeslobo vai até P0089/SV-*, rfi-r02 até P0093, com P0092 livre nos dois) —
mesmo `funcao_id` funciona nos dois contextos sem ambiguidade.

Segue a mesma convenção de campo já usada por MO-ADM-PJ/MO-TOPOGRAFO (PJ,
categoria_sindical "pj_CE", metodo_custo_total "custo_total_ja_incluido" —
valor já representa custo total ao projeto, sem encargos adicionais).

Uso:
    python scripts/catalog/adr167_criar_coordenador.py --dry-run
    python scripts/catalog/adr167_criar_coordenador.py --apply
"""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

CONTEXTOS = ["mendeslobo", "mendeslobo-rfi"]
ACTOR_CRIADOR = "adr167-criar-coordenador"
ACTOR_APROVADOR = "adr167-criar-coordenador-aprovador"

COORDENADOR_ITEM: dict[str, Any] = {
    "codigo": "P0092",
    "tipo": "MAO_OBRA",
    "descricao": "Coordenador",
    "unidade": "mes",
    "preco_unitario": 12500.0,
    "categoria": "DIVERSOS",
    "fonte_preco": "negociado",
    "atributos_especificos": {
        "categoria_sindical": "pj_CE",
        "horas_extras_pct_padrao": 0.0,
        "tipo_contrato": "PJ",
        "metodo_custo_total": "custo_total_ja_incluido",
        "taxa_encargos_pct": 0.0,
        "nota_encargos": "Valor já representa custo total ao projeto (salário + encargos + benefícios), "
        "conforme orçamento gerencial de RH (mesma convenção de MO-ADM-PJ/MO-TOPOGRAFO).",
    },
}


def _register_tools(config_root: Path) -> dict[str, Any]:
    from mcp.server.fastmcp import FastMCP

    os.environ["CONCILIUM__CONFIG_ROOT"] = str(config_root)
    from concilium.infrastructure.settings._storage import _reset_storage

    _reset_storage()

    mod = importlib.import_module("concilium.presentation.mcp.tools.catalogo")
    importlib.reload(mod)
    server: Any = FastMCP("adr167-criar-coordenador")
    mod.register(server)
    tools: dict[str, Any] = {}
    for t in server._tool_manager.list_tools():
        fn = getattr(t, "fn", None) or getattr(t, "func", None)
        tools[t.name] = fn
    return tools


def run_um_contexto(tools: dict[str, Any], contexto_id: str) -> dict[str, Any]:
    from concilium.infrastructure.auth.permission_guard import reset_auth_context, set_auth_context, set_roles

    set_roles(["catalog-manager"])
    tokens = set_auth_context(user_id=ACTOR_CRIADOR, tenant_id=None)
    try:
        rascunho_resp = tools["criar_rascunho_catalogo"](
            contexto_id=contexto_id,
            descricao="ADR-167: novo cargo Coordenador (P0092, PJ)",
        )
        if "rascunho_id" not in rascunho_resp:
            raise RuntimeError(f"criar_rascunho_catalogo falhou ({contexto_id}): {rascunho_resp}")
        rascunho_id = rascunho_resp["rascunho_id"]

        criar_resp = tools["criar_insumo"](
            contexto_id=contexto_id,
            rascunho_id=rascunho_id,
            **COORDENADOR_ITEM,
        )
        tools["listar_divergencias_rascunho"](contexto_id=contexto_id, rascunho_id=rascunho_id)
    finally:
        reset_auth_context(tokens)

    tokens = set_auth_context(user_id=ACTOR_APROVADOR, tenant_id=None)
    try:
        merge_resp = tools["aprovar_merge_catalogo"](
            contexto_id=contexto_id,
            rascunho_id=rascunho_id,
            justificativa="ADR-167: novo cargo Coordenador (P0092, PJ, R$12.500/mês)",
        )
    finally:
        reset_auth_context(tokens)

    return {"rascunho_id": rascunho_id, "criar": criar_resp, "merge": merge_resp}


def run(config_root: Path) -> dict[str, dict[str, Any]]:
    tools = _register_tools(config_root)
    return {ctx: run_um_contexto(tools, ctx) for ctx in CONTEXTOS}


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-167 F1: cria o cargo Coordenador (P0092) em mendeslobo/rfi-r02")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="roda contra cópia temporária de config/")
    group.add_argument("--apply", action="store_true", help="grava de fato nos dois catálogos")
    args = parser.parse_args()

    if args.dry_run:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_config = Path(tmp) / "config"
            shutil.copytree(REPO_ROOT / "config", tmp_config)
            resultados = run(tmp_config)
        modo = "DRY-RUN (cópia temporária, descartada)"
    else:
        resultados = run(REPO_ROOT / "config")
        modo = "APLICADO em mendeslobo e rfi-r02"

    print(f"[{modo}]")
    for ctx, r in resultados.items():
        print(f"  {ctx}: rascunho={r['rascunho_id']} criar={r['criar'].get('status', r['criar'].get('erro'))} "
              f"merge={r['merge'].get('status', r['merge'].get('erro'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
