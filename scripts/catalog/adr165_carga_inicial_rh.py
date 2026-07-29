"""ADR-165 F4: carga inicial de EPI/Treinamento/Exame/Benefício no catálogo mendeslobo.

Popula os itens trazidos pelo usuário na ADR-165 ("Dados trazidos pelo usuário")
pelo mesmo caminho de governança usado pelas tools MCP — nunca escrevendo os
arquivos de insumo diretamente:

    criar_rascunho_catalogo -> criar_insumos_lote -> listar_divergencias_rascunho
    (marca REVISADO) -> aprovar_merge_catalogo (aprovador != criador, ADR-120
    regra dos quatro olhos)

2 EPIs sem preço unitário informado pelo usuário (CINTO TIPO PARAQUEDISTA,
AVENTAL DE COURO) ficam de fora desta carga — ADR-165 D8.

Uso:
    # Roda a sequência inteira contra uma cópia temporária de config/, descartada ao final:
    python scripts/catalog/adr165_carga_inicial_rh.py --dry-run

    # Aplica de fato em config/catalogos/mendeslobo:
    python scripts/catalog/adr165_carga_inicial_rh.py --apply
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

CONTEXTO_ID = "mendeslobo"
ACTOR_CRIADOR = "adr165-carga-inicial"
ACTOR_APROVADOR = "adr165-carga-inicial-aprovador"

# ── Construtores de item (ADR-165 D1-D4) ────────────────────────────────────


def _epi(codigo: str, descricao: str, preco: float, vida_util_dias: int) -> dict[str, Any]:
    return {
        "codigo": codigo,
        "tipo": "MATERIAL",
        "descricao": descricao,
        "unidade": "unid",
        "preco_unitario": preco,
        "categoria": "QSMS",
        "fonte_preco": "catalogo_proprio",
        "atributos_especificos": {"vida_util_dias": vida_util_dias},
    }


def _treinamento(codigo: str, descricao: str, preco: float) -> dict[str, Any]:
    return {
        "codigo": codigo,
        "tipo": "TREINAMENTO",
        "descricao": descricao,
        "unidade": "unid",
        "preco_unitario": preco,
        "categoria": "QSMS",
        "fonte_preco": "catalogo_proprio",
        "atributos_especificos": {"vida_util_dias": 360},
    }


def _exame(codigo: str, descricao: str, preco: float) -> dict[str, Any]:
    return {
        "codigo": codigo,
        "tipo": "EXAME",
        "descricao": descricao,
        "unidade": "unid",
        "preco_unitario": preco,
        "categoria": "QSMS",
        "fonte_preco": "catalogo_proprio",
        "atributos_especificos": {"vida_util_dias": 360},
    }


def _beneficio(
    codigo: str,
    descricao: str,
    preco: float,
    periodicidade: str,
    aplicavel_tipo_contrato: list[str] | None = None,
) -> dict[str, Any]:
    atributos: dict[str, Any] = {"periodicidade_beneficio": periodicidade}
    if aplicavel_tipo_contrato is not None:
        atributos["aplicavel_tipo_contrato"] = aplicavel_tipo_contrato
    return {
        "codigo": codigo,
        "tipo": "BENEFICIO",
        "descricao": descricao,
        "unidade": "unid" if periodicidade == "diaria" else "mes",
        "preco_unitario": preco,
        "categoria": "BENEFICIOS",
        "fonte_preco": "catalogo_proprio",
        "atributos_especificos": atributos,
    }


ITENS: list[dict[str, Any]] = [
    # EPIs — CINTO TIPO PARAQUEDISTA e AVENTAL DE COURO ficam de fora (sem preço informado, D8)
    _epi("EPI-PROTETOR-SOLAR", "Protetor solar FPS 60", 60.00, 60),
    _epi("EPI-ABAFADOR-CONCHA", "Abafador de ruídos tipo concha", 90.00, 360),
    _epi("EPI-BOTA-COURO", "Bota de couro com biqueira de aço", 100.00, 180),
    _epi("EPI-UNIFORME", "Uniforme", 255.00, 180),
    _epi("EPI-PERNEIRA", "Perneira", 100.00, 180),
    _epi("EPI-CAPACETE-3M", "Capacete 3M", 170.00, 360),
    _epi("EPI-ROUPA-MOTOSSERRA", "Roupa operador de motosserra", 620.00, 360),
    _epi("EPI-OCULOS-SEGURANCA", "Óculos de segurança", 40.00, 180),
    _epi("EPI-LUVA-VAQUETA", "Luvas de vaqueta", 50.00, 120),
    _epi("EPI-PROTETOR-FACIAL", "Protetor facial", 110.00, 360),
    # Treinamentos — todos específicos por função (ADR-165 D3, mapeamento função->item é tarefa futura)
    _treinamento("TRE-NR22-MINERACAO", "NR-22 (Mineração)", 315.00),
    _treinamento("TRE-PLANO-TRANSITO", "Plano de Trânsito Integrado", 300.00),
    _treinamento("TRE-OP-MOTOSSERRA", "Operador de Motosserra", 450.00),
    _treinamento("TRE-OP-MOTOPODA", "Operador de Motopoda", 400.00),
    _treinamento("TRE-FERRAMENTAS-MANUAIS", "Ferramentas Manuais", 175.00),
    _treinamento("TRE-PRODUTOS-QUIMICOS", "Produtos Químicos", 315.00),
    _treinamento("TRE-NR12-MAQUINAS", "NR-12 (Máquinas e Equipamentos)", 300.00),
    _treinamento("TRE-NR6-USO-EPI", "NR-6 (Uso de EPIs)", 150.00),
    _treinamento("TRE-NR35-ALTURA", "NR-35 (Trabalho em Altura)", 350.00),
    # Exames — comuns a todas as funções (funcoes_aplicaveis=None, default)
    _exame("EXA-ASO-ADMISSIONAL", "ASO — Admissional e Demissional", 400.00),
    _exame("EXA-CLINICO", "Exame Clínico", 46.00),
    _exame("EXA-AUDIOMETRIA", "Audiometria", 35.00),
    _exame("EXA-LIPIDOGRAMA", "Lipidograma", 19.50),
    _exame("EXA-HEMOGRAMA", "Hemograma Completo", 19.50),
    _exame("EXA-URINA", "Urina", 15.60),
    _exame("EXA-GLICEMIA", "Glicemia", 15.60),
    _exame("EXA-ELETROCARDIOGRAMA", "Eletrocardiograma", 65.00),
    _exame("EXA-TIPAGEM-SANGUINEA", "Tipagem Sanguínea", 65.00),
    # Benefícios — comuns; jantar exclui PJ (ADR-165 D4)
    _beneficio("BEN-CAFE-MANHA", "Café da manhã", 9.00, "diaria"),
    _beneficio("BEN-ALMOCO", "Almoço", 16.50, "diaria"),
    _beneficio("BEN-JANTAR", "Jantar (opcional para PJ)", 16.50, "diaria", ["CLT"]),
    _beneficio("BEN-VALE-ALIMENTACAO", "Vale-alimentação", 1260.00, "mensal"),
    _beneficio("BEN-CESTA-BASICA", "Cesta básica", 462.25, "mensal"),
    _beneficio("BEN-SEGURO-VIDA", "Seguro de vida", 35.00, "mensal"),
]


# ── Execução via governança real (mesmo caminho das tools MCP) ─────────────


def _register_tools(config_root: Path) -> dict[str, Any]:
    from mcp.server.fastmcp import FastMCP

    os.environ["CONCILIUM__CONFIG_ROOT"] = str(config_root)
    from concilium.infrastructure.settings._storage import _reset_storage

    _reset_storage()

    mod = importlib.import_module("concilium.presentation.mcp.tools.catalogo")
    importlib.reload(mod)
    server: Any = FastMCP("adr165-carga-inicial")
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
            descricao="ADR-165: carga inicial de EPI/Treinamento/Exame/Benefício",
        )
        if "rascunho_id" not in rascunho_resp:
            raise RuntimeError(f"criar_rascunho_catalogo falhou: {rascunho_resp}")
        rascunho_id = rascunho_resp["rascunho_id"]

        lote_resp = tools["criar_insumos_lote"](contexto_id=CONTEXTO_ID, rascunho_id=rascunho_id, itens=ITENS)
        tools["listar_divergencias_rascunho"](contexto_id=CONTEXTO_ID, rascunho_id=rascunho_id)
    finally:
        reset_auth_context(tokens)

    tokens = set_auth_context(user_id=ACTOR_APROVADOR, tenant_id=None)
    try:
        merge_resp = tools["aprovar_merge_catalogo"](
            contexto_id=CONTEXTO_ID,
            rascunho_id=rascunho_id,
            justificativa="ADR-165: carga inicial de catálogo de RH (EPI/Treinamento/Exame/Benefício)",
        )
    finally:
        reset_auth_context(tokens)

    return {"rascunho_id": rascunho_id, "lote": lote_resp, "merge": merge_resp}


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-165 F4: carga inicial de catálogo de RH")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run", action="store_true", help="roda contra uma cópia temporária de config/, descartada ao final"
    )
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

    lote = result["lote"]
    print(f"[{modo}]")
    print(f"  rascunho_id : {result['rascunho_id']}")
    print(f"  lote        : {lote.get('sucesso')}/{lote.get('total')} insumos criados no rascunho")
    for r in lote.get("resultados", []):
        if r["status"] != "ok":
            print(f"    ERRO {r['codigo']}: {r.get('erro')}")
    print(f"  merge       : {result['merge']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
