"""ADR-170 F1: cria o insumo BEN-ALOJAMENTO (BENEFICIO) em mendeslobo e rfi-r02.

Alojamento é conceitualmente um benefício (mesma categoria de café/almoço/
vale-alimentação/seguro-vida, ADR-165) — só que compartilhado: uma casa serve
várias pessoas, não é um custo direto por pessoa como os demais BENEFICIO.
`quartos_por_casa`/`pessoas_por_quarto` (ADR-170, novos campos de
AtributosInsumo) capturam essa capacidade compartilhada.

O custo continua aparecendo na categoria ADM do pipeline de indiretos (ADR-168),
não junto dos demais benefícios em MOB — só a FONTE do preço/capacidade passa
a ser este insumo em vez de hardcoded/config de perfil (ADR-170 F2).

Uso:
    python scripts/catalog/adr170_criar_ben_alojamento.py --dry-run
    python scripts/catalog/adr170_criar_ben_alojamento.py --apply
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
ACTOR_CRIADOR = "adr170-criar-ben-alojamento"
ACTOR_APROVADOR = "adr170-criar-ben-alojamento-aprovador"

BEN_ALOJAMENTO_ITEM: dict[str, Any] = {
    "codigo": "BEN-ALOJAMENTO",
    "tipo": "BENEFICIO",
    "descricao": "Alojamento (aluguel de casa compartilhada)",
    "unidade": "mes",
    "preco_unitario": 4000.0,
    "categoria": "BENEFICIOS",
    "fonte_preco": "catalogo_proprio",
    "atributos_especificos": {
        "periodicidade_beneficio": "mensal",
        "quartos_por_casa": 3,
        "pessoas_por_quarto": 2,
    },
}


def _register_tools(config_root: Path) -> dict[str, Any]:
    from mcp.server.fastmcp import FastMCP

    os.environ["CONCILIUM__CONFIG_ROOT"] = str(config_root)
    from concilium.infrastructure.settings._storage import _reset_storage

    _reset_storage()

    mod = importlib.import_module("concilium.presentation.mcp.tools.catalogo")
    importlib.reload(mod)
    server: Any = FastMCP("adr170-criar-ben-alojamento")
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
            descricao="ADR-170: novo insumo BEN-ALOJAMENTO",
        )
        if "rascunho_id" not in rascunho_resp:
            raise RuntimeError(f"criar_rascunho_catalogo falhou ({contexto_id}): {rascunho_resp}")
        rascunho_id = rascunho_resp["rascunho_id"]

        criar_resp = tools["criar_insumo"](
            contexto_id=contexto_id,
            rascunho_id=rascunho_id,
            **BEN_ALOJAMENTO_ITEM,
        )
        tools["listar_divergencias_rascunho"](contexto_id=contexto_id, rascunho_id=rascunho_id)
    finally:
        reset_auth_context(tokens)

    tokens = set_auth_context(user_id=ACTOR_APROVADOR, tenant_id=None)
    try:
        merge_resp = tools["aprovar_merge_catalogo"](
            contexto_id=contexto_id,
            rascunho_id=rascunho_id,
            justificativa="ADR-170: BEN-ALOJAMENTO (R$4.000/mês/casa, 3 quartos x 2 pessoas)",
        )
    finally:
        reset_auth_context(tokens)

    return {"rascunho_id": rascunho_id, "criar": criar_resp, "merge": merge_resp}


def run(config_root: Path) -> dict[str, dict[str, Any]]:
    tools = _register_tools(config_root)
    return {ctx: run_um_contexto(tools, ctx) for ctx in CONTEXTOS}


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-170 F1: cria BEN-ALOJAMENTO em mendeslobo/rfi-r02")
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
        print(
            f"  {ctx}: rascunho={r['rascunho_id']} criar={r['criar'].get('status', r['criar'].get('erro'))} "
            f"merge={r['merge'].get('status', r['merge'].get('erro'))}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
