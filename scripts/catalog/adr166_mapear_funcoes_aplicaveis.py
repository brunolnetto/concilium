"""ADR-166 F1: preenche `funcoes_aplicaveis` dos itens ADR-165 específicos por função.

Mapeamento função→item confirmado com o usuário (rascunho publicado como artefato
antes desta carga, 3 perguntas de confirmação — ver ADR-166 §D4). Usa a mesma
extensão de `atualizar_preco_insumo(novos_funcoes_aplicaveis=...)` (ADR-166 D1)
pelo caminho de governança rascunho→merge/quatro-olhos, igual à F4 da ADR-165.

Grupos de função são derivados por normalização da `descricao` de cada Insumo
MAO_OBRA em `config/catalogos/mendeslobo/insumos/mao_obra/`, unificando os
aliases de código (`MO-*`/`MO-P0xxx`/`P0xxx`/`AGIS-FN-*`/`SV-P0xxx-D/N`) que
descrevem o mesmo cargo — ver ADR-163 (achado de duplicação de código por função).

Uso:
    python scripts/catalog/adr166_mapear_funcoes_aplicaveis.py --dry-run
    python scripts/catalog/adr166_mapear_funcoes_aplicaveis.py --apply
"""

from __future__ import annotations

import argparse
import glob
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

CONTEXTO_ID = "mendeslobo"
ACTOR_CRIADOR = "adr166-mapeamento-funcoes"
ACTOR_APROVADOR = "adr166-mapeamento-funcoes-aprovador"


def _norm(desc: str) -> str:
    s = desc.lower().strip()
    s = re.sub(r"\s*\([^)]*\)", "", s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.replace("serra verde ", "").replace("caminhao carroceria/prancha", "caminhao prancha")
    s = re.sub(r"\bcam\b", "caminhao", s)
    s = re.sub(r"\bretro escavadeira\b", "retroescavadeira", s)
    s = re.sub(r"\bpneus\b", "pneu", s)
    s = re.sub(r"\bagua/esgoto\b", "agua e esgoto", s)
    s = re.sub(r"(motorista|encarregado)\s+(?!de\s)", r"\1 de ", s)
    return re.sub(r"\s+", " ", s).strip()


def _grupos_funcao(config_root: Path) -> dict[str, list[str]]:
    """Agrupa códigos MAO_OBRA por descrição normalizada -> lista de códigos (aliases)."""
    groups: dict[str, set[str]] = defaultdict(set)
    mo_dir = config_root / "catalogos" / CONTEXTO_ID / "insumos" / "mao_obra"
    for f in sorted(glob.glob(str(mo_dir / "*.json"))):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        groups[_norm(d.get("descricao", ""))].add(d["codigo"])
    return {k: sorted(v) for k, v in groups.items()}


def _codigos(grupos: dict[str, list[str]], *chaves: str) -> list[str]:
    out: set[str] = set()
    for k in chaves:
        out.update(grupos.get(k, []))
    return sorted(out)


_MAQUINA_CHAVES = (
    "operador de escavadeira", "operador de mini escavadeira", "operador de retroescavadeira",
    "operador de motoniveladora", "operador de rolo compactador", "operador de rolo de pneu",
    "operador de trator de esteiras", "operador de trator de pneu", "operador de pa carregadeira",
    "operador de betoneira", "operador de motoscraper", "operador de vibroacabadora",
    "operador de bobcat", "operador de fresadora", "operador de perfuratriz",
    "operador de guindaste", "operador de valetadeira", "operador de espargidor",
    "operador de maquinas da const civil",
)
_MOTOSSERRA_CHAVES = ("operador de motosserra",)
_TRANSITO_CHAVES = (
    "motorista de caminhao", "motorista de caminhao basculante", "motorista de caminhao comboio",
    "motorista de caminhao munck", "motorista de caminhao pipa", "motorista de caminhao prancha",
    "motorista de onibus", "sinaleiro",
)
_QUIMICOS_CHAVES = ("laboratorista", "auxiliar de laboratorio", "operador de espargidor", "pintor")
_ALTURA_CHAVES = ("eletricista", "montador", "montador de agua e esgoto", "carpinteiro", "armador")
_ESMERIL_CHAVES = ("soldador", "mecanico", "auxiliar mecanico", "borracheiro")


def _atualizacoes(grupos: dict[str, list[str]]) -> list[dict[str, Any]]:
    maquinas = _codigos(grupos, *_MAQUINA_CHAVES)
    motosserra = _codigos(grupos, *_MOTOSSERRA_CHAVES)
    transito = _codigos(grupos, *_TRANSITO_CHAVES)
    quimicos = _codigos(grupos, *_QUIMICOS_CHAVES)
    altura = _codigos(grupos, *_ALTURA_CHAVES)
    esmeril = _codigos(grupos, *_ESMERIL_CHAVES)

    return [
        {"insumo_id": "TRE-NR12-MAQUINAS", "funcoes_aplicaveis": maquinas},
        {"insumo_id": "EPI-ABAFADOR-CONCHA", "funcoes_aplicaveis": sorted(set(maquinas) | set(motosserra))},
        {"insumo_id": "TRE-OP-MOTOSSERRA", "funcoes_aplicaveis": motosserra},
        {"insumo_id": "TRE-OP-MOTOPODA", "funcoes_aplicaveis": motosserra},
        {"insumo_id": "EPI-ROUPA-MOTOSSERRA", "funcoes_aplicaveis": motosserra},
        {"insumo_id": "EPI-PERNEIRA", "funcoes_aplicaveis": motosserra},
        {"insumo_id": "TRE-PLANO-TRANSITO", "funcoes_aplicaveis": transito},
        {"insumo_id": "TRE-PRODUTOS-QUIMICOS", "funcoes_aplicaveis": quimicos},
        {"insumo_id": "TRE-NR35-ALTURA", "funcoes_aplicaveis": altura},
        {"insumo_id": "EPI-PROTETOR-FACIAL", "funcoes_aplicaveis": esmeril},
        # NR-22 é exigência por área/projeto, não por cargo — sem função associada por ora (ADR-166).
        {"insumo_id": "TRE-NR22-MINERACAO", "funcoes_aplicaveis": []},
    ]


def _register_tools(config_root: Path) -> dict[str, Any]:
    from mcp.server.fastmcp import FastMCP

    os.environ["CONCILIUM__CONFIG_ROOT"] = str(config_root)
    from concilium.infrastructure.settings._storage import _reset_storage

    _reset_storage()

    mod = importlib.import_module("concilium.presentation.mcp.tools.catalogo")
    importlib.reload(mod)
    server: Any = FastMCP("adr166-mapeamento-funcoes")
    mod.register(server)
    tools: dict[str, Any] = {}
    for t in server._tool_manager.list_tools():
        fn = getattr(t, "fn", None) or getattr(t, "func", None)
        tools[t.name] = fn
    return tools


def run(config_root: Path) -> dict[str, Any]:
    from concilium.infrastructure.auth.permission_guard import reset_auth_context, set_auth_context, set_roles

    grupos = _grupos_funcao(config_root)
    atualizacoes = _atualizacoes(grupos)
    tools = _register_tools(config_root)

    set_roles(["catalog-manager"])
    tokens = set_auth_context(user_id=ACTOR_CRIADOR, tenant_id=None)
    resultados = []
    try:
        rascunho_resp = tools["criar_rascunho_catalogo"](
            contexto_id=CONTEXTO_ID,
            descricao="ADR-166: mapeamento função->item específico (EPI/treinamento)",
        )
        if "rascunho_id" not in rascunho_resp:
            raise RuntimeError(f"criar_rascunho_catalogo falhou: {rascunho_resp}")
        rascunho_id = rascunho_resp["rascunho_id"]

        lote_itens = [
            {"insumo_id": item["insumo_id"], "novos_funcoes_aplicaveis": item["funcoes_aplicaveis"]}
            for item in atualizacoes
        ]
        lote_resp = tools["atualizar_precos_insumos_lote"](
            contexto_id=CONTEXTO_ID, rascunho_id=rascunho_id, itens=lote_itens
        )
        resultados = lote_resp.get("resultados", [])

        tools["listar_divergencias_rascunho"](contexto_id=CONTEXTO_ID, rascunho_id=rascunho_id)
    finally:
        reset_auth_context(tokens)

    tokens = set_auth_context(user_id=ACTOR_APROVADOR, tenant_id=None)
    try:
        merge_resp = tools["aprovar_merge_catalogo"](
            contexto_id=CONTEXTO_ID,
            rascunho_id=rascunho_id,
            justificativa="ADR-166: mapeamento função->item específico confirmado pelo usuário",
        )
    finally:
        reset_auth_context(tokens)

    return {"rascunho_id": rascunho_id, "resultados": resultados, "merge": merge_resp, "grupos": grupos}


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-166 F1: mapeamento função->item específico")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="roda contra cópia temporária de config/")
    group.add_argument("--apply", action="store_true", help="grava de fato em config/catalogos/mendeslobo")
    args = parser.parse_args()

    if args.dry_run:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_config = Path(tmp) / "config"
            shutil.copytree(REPO_ROOT / "config", tmp_config)
            result = run(tmp_config)
        modo = "DRY-RUN (cópia temporária, descartada)"
    else:
        result = run(REPO_ROOT / "config")
        modo = "APLICADO em config/catalogos/mendeslobo"

    print(f"[{modo}]")
    print(f"  rascunho_id : {result['rascunho_id']}")
    for r in result["resultados"]:
        linha = f"    {r['insumo_id']}: {r['status']}"
        if r["status"] != "ok":
            linha += f" — {r.get('erro')}"
        print(linha)
    print(f"  merge       : {result['merge']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
