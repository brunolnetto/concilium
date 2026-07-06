"""Tool MCP criar_projeto_spec — spec unificado de projeto (ProjetoSpec)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.domain.constants import ISS_PADRAO


def _schema_path() -> Path:
    root = Path(__file__).resolve().parents[6]
    return root / "config" / "schemas" / "projeto_spec.schema.json"


def _validate_spec(spec: dict) -> list[str]:
    """Valida spec contra projeto_spec.schema.json. Retorna lista de erros."""
    try:
        import jsonschema

        schema = json.loads(_schema_path().read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        return [e.message for e in validator.iter_errors(spec)]
    except ImportError:
        return []  # jsonschema opcional — sem validação estrita


def _resolve_tributario(meta: dict, rt: Any) -> dict:
    """Resolve alíquotas tributárias: spec > jurisdição > BR padrão."""
    tributario = dict(meta.get("regime_tributario") or {})
    jurisdicao_id = tributario.pop("jurisdicao_id", None)

    if not all(k in tributario for k in ("iss", "pis", "cofins", "cprb")):
        jur_data: dict = {}
        if jurisdicao_id:
            try:
                jur_data = rt.load_jurisdicao(jurisdicao_id)
            except Exception:
                pass
        aliq = (jur_data.get("motor_tributario_bdi") or {}).get("aliquotas") or {}
        tributario.setdefault("iss", aliq.get("ISS", ISS_PADRAO))
        tributario.setdefault("pis", aliq.get("PIS", 0.0065))
        tributario.setdefault("cofins", aliq.get("COFINS", 0.03))
        tributario.setdefault("cprb", aliq.get("CPRB", 0.045))

    return tributario


def register(server: FastMCP) -> None:
    """Registra criar_projeto_spec no servidor MCP.

    ADR-116 F5: criar_projeto_spec foi absorvido em criar_projeto(spec=...) de
    formulario.py, que reimplementa a mesma lógica usando _resolve_tributario e
    _validate_spec importados diretamente. Nenhuma tool é registrada aqui; a
    função existe apenas para manter a assinatura register(server) esperada por
    server.py, e para reexportar _resolve_tributario/_validate_spec.
    """
