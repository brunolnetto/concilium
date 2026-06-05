#!/usr/bin/env python3
"""
Script de auditoria de histórico de commits.

Analisa commits existentes no repositório para identificar:
- Commits muito grandes (excedem limites de governança)
- Padrões de commits por autor
- Hotspots (arquivos mais modificados)
- Violações de formato de mensagem

Uso:
    # Analisar últimos 100 commits
    python scripts/dev/audit_commit_history.py

    # Analisar commits desde uma data
    python scripts/dev/audit_commit_history.py --since 2026-01-01

    # Analisar range específico
    python scripts/dev/audit_commit_history.py --range main..feature-branch

    # Gerar relatório JSON
    python scripts/dev/audit_commit_history.py --output audit.json

    # Modo detalhado
    python scripts/dev/audit_commit_history.py --verbose
"""

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Limites de Referência (mesmos do validate_commit_size.py) ──────────────

RECOMMENDED_MAX_FILES = 15
HARD_MAX_FILES = 30
HARD_MAX_LINES = 1000

# ── Tipos de Commit Válidos (Conventional Commits) ─────────────────────────

VALID_COMMIT_TYPES = {
    "feat", "fix", "refactor", "perf", "test", "docs",
    "style", "build", "ci", "chore", "revert"
}

# ── Cores para Output ───────────────────────────────────────────────────────

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


# ── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class CommitStats:
    """Estatísticas de um commit individual."""
    sha: str
    author: str
    date: str
    message_subject: str
    files_changed: int
    lines_added: int
    lines_removed: int
    total_lines: int
    exceeds_file_limit: bool
    exceeds_line_limit: bool
    follows_convention: bool
    commit_type: Optional[str]
    commit_scope: Optional[str]


@dataclass
class AuditReport:
    """Relatório completo de auditoria."""
    total_commits: int
    commits_exceeding_limits: int
    commits_without_convention: int
    top_authors: list[tuple[str, int]]
    top_hotspots: list[tuple[str, int]]
    largest_commits: list[CommitStats]
    commits_by_type: dict[str, int]
    date_range: tuple[str, str]


# ── Git Operations ──────────────────────────────────────────────────────────

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
        sys.exit(1)


def parse_commit_message(message: str) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Parse mensagem de commit e verifica Conventional Commits.
    
    Returns:
        (follows_convention, commit_type, commit_scope)
    """
    # Formato: tipo(escopo): mensagem
    # ou: tipo: mensagem
    pattern = r"^([a-z]+)(\([a-z0-9\-_/]+\))?: .+"
    match = re.match(pattern, message.lower())
    
    if not match:
        return (False, None, None)
    
    commit_type = match.group(1)
    commit_scope = match.group(2)[1:-1] if match.group(2) else None
    
    follows_convention = commit_type in VALID_COMMIT_TYPES
    
    return (follows_convention, commit_type, commit_scope)


def get_commit_stats(sha: str) -> CommitStats:
    """Obtém estatísticas de um commit específico."""
    # Informações básicas do commit
    info = run_git_command([
        "show", "--no-patch",
        "--format=%an%n%ai%n%s",
        sha
    ]).split("\n")
    
    author = info[0]
    date = info[1]
    subject = info[2]
    
    # Estatísticas de diff
    numstat = run_git_command([
        "show", "--numstat", "--format=", sha
    ])
    
    files_changed = 0
    lines_added = 0
    lines_removed = 0
    
    for line in numstat.split("\n"):
        if not line.strip():
            continue
        
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        
        added, removed, _filename = parts
        
        # Arquivos binários retornam "-"
        if added != "-" and removed != "-":
            lines_added += int(added)
            lines_removed += int(removed)
        
        files_changed += 1
    
    total_lines = lines_added + lines_removed
    
    # Parse mensagem
    follows_convention, commit_type, commit_scope = parse_commit_message(subject)
    
    return CommitStats(
        sha=sha[:8],
        author=author,
        date=date,
        message_subject=subject[:80],
        files_changed=files_changed,
        lines_added=lines_added,
        lines_removed=lines_removed,
        total_lines=total_lines,
        exceeds_file_limit=(files_changed > HARD_MAX_FILES),
        exceeds_line_limit=(lines_added > HARD_MAX_LINES),
        follows_convention=follows_convention,
        commit_type=commit_type,
        commit_scope=commit_scope,
    )


def get_file_hotspots(git_range: str) -> list[tuple[str, int]]:
    """Retorna arquivos mais modificados no range."""
    output = run_git_command([
        "log", git_range,
        "--format=format:",
        "--name-only"
    ])
    
    file_counts = Counter(
        line for line in output.split("\n")
        if line.strip()
    )
    
    return file_counts.most_common(20)


# ── Auditoria ───────────────────────────────────────────────────────────────

def audit_commits(
    git_range: str = "HEAD~100..HEAD",
    verbose: bool = False
) -> AuditReport:
    """
    Audita commits no range especificado.
    
    Args:
        git_range: Range de commits (ex: "HEAD~100..HEAD", "main..feature")
        verbose: Exibir progresso detalhado
    """
    # Obter lista de commits
    commit_shas = run_git_command([
        "log", git_range, "--format=%H"
    ]).split("\n")
    
    if not commit_shas or commit_shas == [""]:
        print_colored("❌ Nenhum commit encontrado no range especificado.", Color.RED)
        sys.exit(1)
    
    total_commits = len(commit_shas)
    
    if verbose:
        print_colored(f"\n🔍 Analisando {total_commits} commits...", Color.BLUE)
    
    # Analisar cada commit
    all_stats: list[CommitStats] = []
    author_counts = Counter()
    type_counts = Counter()
    
    for i, sha in enumerate(commit_shas, 1):
        if verbose and i % 10 == 0:
            print(f"  Progresso: {i}/{total_commits}", end="\r")
        
        stats = get_commit_stats(sha)
        all_stats.append(stats)
        
        author_counts[stats.author] += 1
        if stats.commit_type:
            type_counts[stats.commit_type] += 1
    
    if verbose:
        print()  # Nova linha após progresso
    
    # Calcular métricas
    commits_exceeding = sum(
        1 for s in all_stats
        if s.exceeds_file_limit or s.exceeds_line_limit
    )
    
    commits_without_convention = sum(
        1 for s in all_stats
        if not s.follows_convention
    )
    
    # Top N
    largest_commits = sorted(
        all_stats,
        key=lambda s: s.total_lines,
        reverse=True
    )[:10]
    
    top_authors = author_counts.most_common(10)
    
    # Date range
    first_commit_date = all_stats[-1].date if all_stats else ""
    last_commit_date = all_stats[0].date if all_stats else ""
    
    # Hotspots
    hotspots = get_file_hotspots(git_range)
    
    return AuditReport(
        total_commits=total_commits,
        commits_exceeding_limits=commits_exceeding,
        commits_without_convention=commits_without_convention,
        top_authors=top_authors,
        top_hotspots=hotspots,
        largest_commits=largest_commits,
        commits_by_type=dict(type_counts),
        date_range=(first_commit_date, last_commit_date),
    )


# ── Output Formatado ────────────────────────────────────────────────────────

def print_report(report: AuditReport, detailed: bool = False) -> None:
    """Exibe relatório formatado no terminal."""
    
    print_colored("\n" + "═" * 70, Color.BOLD)
    print_colored("  📊 RELATÓRIO DE AUDITORIA DE COMMITS", Color.BOLD)
    print_colored("═" * 70, Color.BOLD)
    
    # Resumo Geral
    print_colored("\n📈 Resumo Geral", Color.BLUE)
    print_colored("─" * 70, Color.BLUE)
    print(f"  Total de commits analisados:     {report.total_commits}")
    print(f"  Período:                          {report.date_range[0][:10]} → {report.date_range[1][:10]}")
    
    # Violações
    print_colored("\n⚠️  Violações de Governança", Color.YELLOW)
    print_colored("─" * 70, Color.YELLOW)
    
    exceeding_pct = (report.commits_exceeding_limits / report.total_commits) * 100
    convention_pct = (report.commits_without_convention / report.total_commits) * 100
    
    color = Color.RED if exceeding_pct > 20 else Color.YELLOW if exceeding_pct > 10 else Color.GREEN
    print_colored(
        f"  Commits excedendo limites:        {report.commits_exceeding_limits} "
        f"({exceeding_pct:.1f}%)",
        color
    )
    
    color = Color.RED if convention_pct > 30 else Color.YELLOW if convention_pct > 15 else Color.GREEN
    print_colored(
        f"  Commits sem Conventional Commits: {report.commits_without_convention} "
        f"({convention_pct:.1f}%)",
        color
    )
    
    # Top Autores
    print_colored("\n👥 Top Autores", Color.BLUE)
    print_colored("─" * 70, Color.BLUE)
    for i, (author, count) in enumerate(report.top_authors[:5], 1):
        pct = (count / report.total_commits) * 100
        print(f"  {i}. {author:<30} {count:>4} commits ({pct:.1f}%)")
    
    # Distribuição por Tipo
    if report.commits_by_type:
        print_colored("\n🏷️  Distribuição por Tipo", Color.BLUE)
        print_colored("─" * 70, Color.BLUE)
        sorted_types = sorted(
            report.commits_by_type.items(),
            key=lambda x: x[1],
            reverse=True
        )
        for commit_type, count in sorted_types[:10]:
            pct = (count / report.total_commits) * 100
            print(f"  {commit_type:<15} {count:>4} ({pct:.1f}%)")
    
    # Hotspots
    print_colored("\n🔥 Hotspots (Arquivos Mais Modificados)", Color.BLUE)
    print_colored("─" * 70, Color.BLUE)
    for i, (file, count) in enumerate(report.top_hotspots[:10], 1):
        print(f"  {i:>2}. [{count:>3}x] {file}")
    
    # Maiores Commits
    print_colored("\n📦 Maiores Commits", Color.BLUE)
    print_colored("─" * 70, Color.BLUE)
    
    for i, commit in enumerate(report.largest_commits[:10], 1):
        warning = ""
        if commit.exceeds_file_limit:
            warning += " 🚫 FILES"
        if commit.exceeds_line_limit:
            warning += " 🚫 LINES"
        
        color = Color.RED if warning else Color.YELLOW if commit.total_lines > 500 else Color.END
        
        print_colored(
            f"  {i:>2}. [{commit.sha}] {commit.total_lines:>6} linhas "
            f"({commit.files_changed:>3} arquivos){warning}",
            color
        )
        print(f"      {commit.message_subject}")
        
        if detailed:
            print(f"      Autor: {commit.author}, Data: {commit.date[:10]}")
    
    # Recomendações
    print_colored("\n💡 Recomendações", Color.BLUE)
    print_colored("─" * 70, Color.BLUE)
    
    if report.commits_exceeding_limits > 0:
        print("  • Revisar commits grandes e dividir em partes menores no futuro")
    
    if report.commits_without_convention > report.total_commits * 0.3:
        print("  • Adotar Conventional Commits de forma consistente")
        print("  • Usar template de commit: git config commit.template .git-commit-template")
    
    if not report.commits_by_type:
        print("  • Implementar validação de formato de mensagem no pre-commit")
    
    print_colored("\n  Ver COMMIT_GOVERNANCE.md para diretrizes completas.", Color.GREEN)
    print_colored("═" * 70 + "\n", Color.BOLD)


# ── Entry Point ─────────────────────────────────────────────────────────────

def main() -> int:
    """Entry point do script."""
    parser = argparse.ArgumentParser(
        description="Auditar histórico de commits do repositório",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Analisar últimos 100 commits
  python scripts/dev/audit_commit_history.py

  # Analisar commits desde janeiro
  python scripts/dev/audit_commit_history.py --since 2026-01-01

  # Analisar branch específica
  python scripts/dev/audit_commit_history.py --range main..feature-branch

  # Gerar relatório JSON
  python scripts/dev/audit_commit_history.py --output audit.json
        """
    )
    
    parser.add_argument(
        "--since",
        help="Analisar commits desde data (formato: YYYY-MM-DD)",
    )
    
    parser.add_argument(
        "--range",
        help="Range de commits (ex: main..feature-branch)",
    )
    
    parser.add_argument(
        "-n", "--limit",
        type=int,
        default=100,
        help="Número máximo de commits para analisar (padrão: 100)",
    )
    
    parser.add_argument(
        "-o", "--output",
        help="Salvar relatório em arquivo JSON",
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Exibir progresso detalhado",
    )
    
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Exibir informações detalhadas no relatório",
    )
    
    args = parser.parse_args()
    
    # Determinar range de commits
    if args.range:
        git_range = args.range
    elif args.since:
        git_range = f"--since={args.since}"
    else:
        git_range = f"HEAD~{args.limit}..HEAD"
    
    try:
        # Executar auditoria
        report = audit_commits(git_range, verbose=args.verbose)
        
        # Exibir relatório
        print_report(report, detailed=args.detailed)
        
        # Salvar JSON se solicitado
        if args.output:
            output_path = Path(args.output)
            
            # Converter para dict serializável
            report_dict = {
                "total_commits": report.total_commits,
                "commits_exceeding_limits": report.commits_exceeding_limits,
                "commits_without_convention": report.commits_without_convention,
                "top_authors": report.top_authors,
                "top_hotspots": report.top_hotspots,
                "largest_commits": [asdict(c) for c in report.largest_commits],
                "commits_by_type": report.commits_by_type,
                "date_range": report.date_range,
            }
            
            output_path.write_text(
                json.dumps(report_dict, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            
            print_colored(f"✅ Relatório salvo em {output_path}", Color.GREEN)
        
        return 0
    
    except KeyboardInterrupt:
        print_colored("\n\n⚠️  Auditoria cancelada pelo usuário.", Color.YELLOW)
        return 1
    except Exception as e:
        print_colored(f"\n❌ Erro inesperado: {e}", Color.RED)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
