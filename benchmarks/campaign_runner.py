#!/usr/bin/env python3
"""Wrapper de conveniência para exploração de campanha AGIS em desenvolvimento.

Para uso em produção, usar o comando CLI:
    concilium project campaign AGIS

Este script existe apenas para facilitar execução rápida sem a instalação
completa do pacote CLI.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from concilium.presentation.cli.commands_campaign import campaign

if __name__ == "__main__":
    import typer
    typer.run(campaign)
