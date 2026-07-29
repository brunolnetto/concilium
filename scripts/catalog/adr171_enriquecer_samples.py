"""ADR-171 F1: enriquece o catálogo `samples` com os itens das ADR-165/166/167/170.

O benchmark GOLDEN (`benchmarks/projetos/GOLDEN`) usa o catálogo `samples`, não
`mendeslobo`/`rfi-r02` — por isso a regressão do golden test só reagiu à ADR-168
(Alojamento bottom-up, que só depende de headcount) e não às demais ADRs desta
série, que dependem de itens de catálogo que `samples` não tinha. Este script
fecha essa lacuna: cria `P0092` (Coordenador) e `BEN-ALOJAMENTO`, e mapeia
`funcoes_aplicaveis` dos itens específicos (TREINAMENTO/EPI) sobre o roster
próprio de `samples` (78 códigos, sem aliases, nomes descritivos — ex.
`OPERADOR-DE-MOTOSSER`, não `MO-P0062`).

`samples` já teve os 34 itens RH da ADR-165 carregados via
`adr165_carga_inicial_rh.py --contexto samples`.

Uso:
    python scripts/catalog/adr171_enriquecer_samples.py --dry-run
    python scripts/catalog/adr171_enriquecer_samples.py --apply
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

CONTEXTO_ID = "samples"
ACTOR_CRIADOR = "adr171-enriquecer-samples"
ACTOR_APROVADOR = "adr171-enriquecer-samples-aprovador"

NOVOS_INSUMOS: list[dict[str, Any]] = [
    {
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
            "nota_encargos": "Valor já representa custo total ao projeto (mesma convenção de "
            "ADM-PJ/TOPOGRAFO, ADR-167).",
        },
    },
    {
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
    },
]

# Grupos de função (códigos descritivos próprios de `samples`, sem aliases).
_MAQUINAS = [
    "OPER-ESCAV", "OPER-ESPARG", "OPER-MINI-ESCAV", "OPER-MOTO", "OPER-RETRO",
    "OPER-PA-CARR", "OPER-ROLO-COMP", "OPER-ROLO-PNEU", "OPER-TRATOR-EST",
    "OPER-TRATOR-PNE", "OPER-BETONEIRA", "OPER-VALETAD", "OPERADOR-DE-MOTOSCRA",
    "OPERADOR-DE-MAQUINAS",
]
_MOTOSSERRA = ["OPERADOR-DE-MOTOSSER"]
_TRANSITO = [
    "MOTOR-CAM-BASC", "MOTOR-CAM-PIPA", "MOTOR-CAM-COMB", "MOTOR-CAM",
    "MOTOR-ONIBUS", "MOTORISTA-DE-CAMINHÃ",
]
_QUIMICOS = ["LABORATORISTA", "AUX-LAB", "OPER-ESPARG", "PINTOR"]
_ALTURA = ["ELETRICISTA", "MONTADOR", "MONTADOR-AGUA", "CARPINTEIRO", "ARMADOR"]
_ESMERIL = ["MECÂNICO", "AUX-MEC", "BORRACHEIRO"]  # sem SOLDADOR neste catálogo


def _atualizacoes_funcoes() -> list[dict[str, Any]]:
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
    server: Any = FastMCP("adr171-enriquecer-samples")
    mod.register(server)
    tools: dict[str, Any] = {}
    for t in server._tool_manager.list_tools():
        fn = getattr(t, "fn", None) or getattr(t, "func", None)
        tools[t.name] = fn
    return tools


def run(config_root: Path) -> dict[str, Any]:
    from concilium.infrastructure.auth.permission_guard import reset_auth_context, set_auth_context, set_roles

    tools = _register_tools(config_root)

    set_roles(["catalog-manager"])
    tokens = set_auth_context(user_id=ACTOR_CRIADOR, tenant_id=None)
    try:
        rascunho_resp = tools["criar_rascunho_catalogo"](
            contexto_id=CONTEXTO_ID,
            descricao="ADR-171: enriquece samples (Coordenador, BEN-ALOJAMENTO, mapeamento função→item)",
        )
        if "rascunho_id" not in rascunho_resp:
            raise RuntimeError(f"criar_rascunho_catalogo falhou: {rascunho_resp}")
        rascunho_id = rascunho_resp["rascunho_id"]

        criar_resp = tools["criar_insumos_lote"](
            contexto_id=CONTEXTO_ID, rascunho_id=rascunho_id, itens=NOVOS_INSUMOS
        )
        atualizar_resp = tools["atualizar_precos_insumos_lote"](
            contexto_id=CONTEXTO_ID, rascunho_id=rascunho_id, itens=_atualizacoes_funcoes()
        )
        tools["listar_divergencias_rascunho"](contexto_id=CONTEXTO_ID, rascunho_id=rascunho_id)
    finally:
        reset_auth_context(tokens)

    tokens = set_auth_context(user_id=ACTOR_APROVADOR, tenant_id=None)
    try:
        merge_resp = tools["aprovar_merge_catalogo"](
            contexto_id=CONTEXTO_ID,
            rascunho_id=rascunho_id,
            justificativa="ADR-171: Coordenador/BEN-ALOJAMENTO/mapeamento função→item em samples",
        )
    finally:
        reset_auth_context(tokens)

    return {"rascunho_id": rascunho_id, "criar": criar_resp, "atualizar": atualizar_resp, "merge": merge_resp}


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-171 F1: enriquece o catálogo samples")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="roda contra cópia temporária de config/")
    group.add_argument("--apply", action="store_true", help="grava de fato em config/catalogos/samples")
    args = parser.parse_args()

    if args.dry_run:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_config = Path(tmp) / "config"
            shutil.copytree(REPO_ROOT / "config", tmp_config)
            result = run(tmp_config)
        modo = "DRY-RUN (cópia temporária, descartada)"
    else:
        result = run(REPO_ROOT / "config")
        modo = "APLICADO em config/catalogos/samples"

    print(f"[{modo}]")
    print(f"  rascunho_id : {result['rascunho_id']}")
    for r in result["criar"].get("resultados", []):
        if r["status"] != "ok":
            print(f"    ERRO criar {r['codigo']}: {r.get('erro')}")
    for r in result["atualizar"].get("resultados", []):
        if r["status"] != "ok":
            print(f"    ERRO atualizar {r['insumo_id']}: {r.get('erro')}")
    print(f"  merge       : {result['merge']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
