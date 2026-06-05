#!/usr/bin/env python3
"""
Script de validação de tamanho de commit para governança de código.

Verifica se um commit está dentro dos limites técnicos definidos em
COMMIT_GOVERNANCE.md antes de permitir o commit.

Uso:
    # Validar staged files antes de commitar
    python scripts/dev/validate_commit_size.py

    # Como pre-commit hook
    # Adicionar em .pre-commit-config.yaml:
    #   - repo: local
    #     hooks:
    #       - id: validate-commit-size
    #         name: Validate commit size
    #         entry: python scripts/dev/validate_commit_size.py
    #         language: system
    #         pass_filenames: false
    #         always_run: true

Exit codes:
    0 - Commit dentro dos limites
    1 - Commit excede limites (bloqueado)
    2 - Aviso (excede recomendado, mas permite commit)
"""

import subprocess
import sys
from pathlib import Path
from typing import Tuple

# ── Limites de Governança ─────────────────────────────────────────────────────

# Limites recomendados (gera aviso, mas permite commit)
RECOMMENDED_MAX_FILES = 15
RECOMMENDED_MAX_LINES_ADDED = 500
RECOMMENDED_MAX_LINES_REMOVED = 300

# Limites máximos (bloqueia commit)
HARD_MAX_FILES = 30
HARD_MAX_LINES_ADDED = 1000
HARD_MAX_DIFF_SIZE_KB = 100

# Padrões que permitem exceções automáticas
EXCEPTION_PATTERNS = [
    "benchmarks/data/",           # Dados de benchmark
    "tests/fixtures/",            # Fixtures de teste
    "tests/samples/",             # Samples de teste
    ".lock",                      # Lock files (poetry.lock, etc)
    "requirements.txt",           # Requirements
    "package-lock.json",          # NPM lock
    ".snapshot",                  # Jest/pytest snapshots
]

EXCEPTION_EXTENSIONS = [
    ".json",    # Dados estruturados
    ".yaml",    # Configurações
    ".yml",     # Configurações
    ".csv",     # Dados tabulares
    ".md",      # Documentação
]

# ── Cores para Output ──────────────────────────────────────────────────────────

class Color:
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


def print_colored(message: str, color: str) -> None:
    """Print mensagem com cor se terminal suportar."""
    if sys.stdout.isatty():
        print(f"{color}{message}{Color.END}")
    else:
        print(message)


# ── Git Operations ─────────────────────────────────────────────────────────────

def run_git_command(args: list[str]) -> str:
    """Executa comando git e retorna output."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print_colored(f"❌ Erro ao executar git: {e}", Color.RED)
        print_colored(f"   stderr: {e.stderr}", Color.RED)
        sys.exit(1)


def get_staged_files() -> list[str]:
    """Retorna lista de arquivos staged."""
    output = run_git_command(["diff", "--cached", "--name-only"])
    if not output:
        return []
    return [line for line in output.split("\n") if line.strip()]


def get_diff_stats() -> Tuple[int, int, int]:
    """
    Retorna estatísticas do diff staged.
    
    Returns:
        Tuple[files_changed, lines_added, lines_removed]
    """
    output = run_git_command(["diff", "--cached", "--numstat"])
    
    if not output:
        return (0, 0, 0)
    
    total_added = 0
    total_removed = 0
    files_count = 0
    
    for line in output.split("\n"):
        if not line.strip():
            continue
        
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        
        added, removed, _filename = parts
        
        # Arquivos binários retornam "-" para added/removed
        if added != "-" and removed != "-":
            total_added += int(added)
            total_removed += int(removed)
        
        files_count += 1
    
    return (files_count, total_added, total_removed)


def get_diff_size_kb() -> float:
    """Retorna tamanho do diff em KB."""
    output = run_git_command(["diff", "--cached"])
    size_bytes = len(output.encode("utf-8"))
    return size_bytes / 1024


def check_exception_patterns(files: list[str]) -> bool:
    """
    Verifica se arquivos se encaixam em padrões de exceção.
    
    Retorna True se >= 80% dos arquivos são exceções automáticas.
    """
    if not files:
        return False
    
    exception_count = 0
    
    for file in files:
        # Verifica padrões de path
        if any(pattern in file for pattern in EXCEPTION_PATTERNS):
            exception_count += 1
            continue
        
        # Verifica extensões
        if any(file.endswith(ext) for ext in EXCEPTION_EXTENSIONS):
            exception_count += 1
            continue
    
    exception_ratio = exception_count / len(files)
    return exception_ratio >= 0.8


# ── Validações ─────────────────────────────────────────────────────────────────

def validate_commit_size() -> int:
    """
    Valida tamanho do commit staged.
    
    Returns:
        0: OK (dentro dos limites)
        1: Bloqueado (excede limites máximos)
        2: Aviso (excede recomendado, mas permite)
    """
    files = get_staged_files()
    
    if not files:
        print_colored("ℹ️  Nenhum arquivo staged para commit.", Color.BLUE)
        return 0
    
    files_count, lines_added, lines_removed = get_diff_stats()
    diff_size_kb = get_diff_size_kb()
    
    # Verificar se é exceção automática
    is_exception = check_exception_patterns(files)
    
    # Header
    print_colored("\n📊 Análise de Tamanho de Commit", Color.BOLD)
    print_colored("─" * 50, Color.BLUE)
    
    # Estatísticas
    print(f"  📁 Arquivos modificados: {files_count}")
    print(f"  ➕ Linhas adicionadas:   {lines_added:,}")
    print(f"  ➖ Linhas removidas:     {lines_removed:,}")
    print(f"  💾 Tamanho do diff:      {diff_size_kb:.1f} KB")
    
    if is_exception:
        print_colored(f"  ✨ Exceção automática detectada (dados/docs/fixtures)", Color.GREEN)
    
    print_colored("─" * 50, Color.BLUE)
    
    # Status flags
    has_hard_violation = False
    has_soft_violation = False
    violations = []
    warnings = []
    
    # ── Validação: Número de arquivos ───────────────────────────────
    if files_count > HARD_MAX_FILES and not is_exception:
        has_hard_violation = True
        violations.append(
            f"❌ Arquivos: {files_count} > {HARD_MAX_FILES} (limite máximo)"
        )
    elif files_count > RECOMMENDED_MAX_FILES and not is_exception:
        has_soft_violation = True
        warnings.append(
            f"⚠️  Arquivos: {files_count} > {RECOMMENDED_MAX_FILES} (recomendado)"
        )
    
    # ── Validação: Linhas adicionadas ───────────────────────────────
    if lines_added > HARD_MAX_LINES_ADDED and not is_exception:
        has_hard_violation = True
        violations.append(
            f"❌ Linhas adicionadas: {lines_added:,} > {HARD_MAX_LINES_ADDED:,} (limite máximo)"
        )
    elif lines_added > RECOMMENDED_MAX_LINES_ADDED and not is_exception:
        has_soft_violation = True
        warnings.append(
            f"⚠️  Linhas adicionadas: {lines_added:,} > {RECOMMENDED_MAX_LINES_ADDED:,} (recomendado)"
        )
    
    # ── Validação: Tamanho do diff ──────────────────────────────────
    if diff_size_kb > HARD_MAX_DIFF_SIZE_KB and not is_exception:
        has_hard_violation = True
        violations.append(
            f"❌ Tamanho do diff: {diff_size_kb:.1f} KB > {HARD_MAX_DIFF_SIZE_KB} KB (limite máximo)"
        )
    
    # ── Output de Resultados ────────────────────────────────────────
    
    if has_hard_violation:
        print_colored("\n🚫 COMMIT BLOQUEADO", Color.RED)
        print_colored("─" * 50, Color.RED)
        for v in violations:
            print_colored(f"  {v}", Color.RED)
        
        print_colored("\n💡 Ações recomendadas:", Color.YELLOW)
        print("  1. Dividir commit em partes menores (use git add -p)")
        print("  2. Commitar por tema/módulo separadamente")
        print("  3. Se necessário, adicionar [EXCEÇÃO: motivo] na mensagem")
        print_colored("\n  Ver COMMIT_GOVERNANCE.md para detalhes.\n", Color.BLUE)
        return 1
    
    if has_soft_violation:
        print_colored("\n⚠️  AVISO: Commit maior que recomendado", Color.YELLOW)
        print_colored("─" * 50, Color.YELLOW)
        for w in warnings:
            print_colored(f"  {w}", Color.YELLOW)
        
        print_colored("\n💡 Recomendações:", Color.YELLOW)
        print("  • Considere dividir em commits menores")
        print("  • Facilita code review e bisect")
        print("  • Adicione contexto detalhado na mensagem de commit")
        print_colored("\n  Commit será permitido, mas revise antes de push.\n", Color.BLUE)
        return 2
    
    # Sucesso
    print_colored("\n✅ Commit dentro dos limites", Color.GREEN)
    print_colored("─" * 50, Color.GREEN)
    print("  Tamanho adequado para review e integração.\n")
    return 0


# ── Entry Point ────────────────────────────────────────────────────────────────

def main() -> int:
    """Entry point do script."""
    try:
        return validate_commit_size()
    except KeyboardInterrupt:
        print_colored("\n\n⚠️  Validação cancelada pelo usuário.", Color.YELLOW)
        return 1
    except Exception as e:
        print_colored(f"\n❌ Erro inesperado: {e}", Color.RED)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
