#!/usr/bin/env python
"""Script de Auditoria de PU em Catálogo (ADR-049 — Camada 1).

Valida convergência de PU teórico vs catalogado para todas as CPUs do catálogo.

Uso:
    python scripts/audit_pu_catalogo.py --contexto mendeslobo [--output report.json]
"""

import argparse
import json
import os
import sys
from pathlib import Path

from concilium.application.runtime import Runtime
from concilium.domain.services.validador_pu_catalogo import validar_pu_catalogo
from concilium.infrastructure.repositories.insumo import RepositorioInsumo


def _workspace_root() -> Path:
    """Resolve workspace root using CONCILIUM__ROOT env or auto-detection."""
    env_root = os.environ.get("CONCILIUM__ROOT")
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if (candidate / "pyproject.toml").exists() and (candidate / "config").is_dir():
            return candidate
    
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "config").is_dir():
            return candidate
    
    # Fallback to script's parent directories
    return Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(
        description="Auditoria de PU em Catálogo (ADR-049)"
    )
    parser.add_argument(
        "--contexto",
        required=True,
        help="ID do contexto (ex: mendeslobo)",
    )
    parser.add_argument(
        "--output",
        help="Arquivo de saída JSON (default: stdout)",
    )
    
    args = parser.parse_args()
    
    try:
        config_root = _workspace_root() / "config"
        runtime = Runtime(config_root=config_root)
        contexto = runtime.load_contexto(args.contexto)
        catalogo = runtime.load_catalogo(contexto.catalogo_id)
    except Exception as e:
        print(f"Erro ao carregar catálogo: {e}", file=sys.stderr)
        return 1
    
    # Monta lookups
    producoes = {p["id"]: p for p in catalogo.get("producoes", [])}
    insumos_dict = {i["codigo"]: i for i in catalogo.get("insumos", [])}
    cpus = catalogo.get("cpus", [])
    
    repo = RepositorioInsumo(catalogo)
    
    # Executa validação para cada CPU
    resultados = []
    num_verde = 0
    num_amarelo = 0
    num_vermelho = 0
    
    print(f"Auditando {len(cpus)} CPUs do catálogo '{args.contexto}'...", file=sys.stderr)
    
    for cpu in cpus:
        resultado = validar_pu_catalogo(
            cpu=cpu,
            producoes_lookup=producoes,
            insumos_lookup=insumos_dict,
            repo=repo,
        )
        resultados.append(resultado.model_dump(mode="json"))
        
        if resultado.status_convergencia == "VERDE":
            num_verde += 1
            marker = "✓"
        elif resultado.status_convergencia == "AMARELO":
            num_amarelo += 1
            marker = "⚠"
        else:
            num_vermelho += 1
            marker = "✗"
        
        print(
            f"  {marker} {resultado.cpu_id}: {resultado.status_convergencia} "
            f"(desvio={resultado.desvio_pct:.2f}% se catalogado)",
            file=sys.stderr
        )
    
    # Resumo
    print(file=sys.stderr)
    print(f"Resumo: {num_verde} VERDE | {num_amarelo} AMARELO | {num_vermelho} VERMELHO", file=sys.stderr)
    
    # Output
    output_data = {
        "contexto": args.contexto,
        "num_total": len(cpus),
        "resumo": {
            "verde": num_verde,
            "amarelo": num_amarelo,
            "vermelho": num_vermelho,
        },
        "resultados": resultados,
    }
    
    if args.output:
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"Relatório salvo em {args.output}", file=sys.stderr)
    else:
        print(json.dumps(output_data, indent=2))
    
    return 0 if num_vermelho == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
