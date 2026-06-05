#!/usr/bin/env python3
"""
Script de setup rápido para governança de commits.

Automatiza a configuração inicial dos hooks e templates de commit.

Uso:
    python scripts/dev/setup_commit_governance.py

Ou com PowerShell:
    python scripts/dev/setup_commit_governance.py
"""

import subprocess
import sys
from pathlib import Path

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


def print_step(step: int, message: str) -> None:
    """Print número de etapa."""
    print_colored(f"\n[{step}/5] {message}", Color.BLUE)


def run_command(cmd: list[str], check: bool = True) -> tuple[bool, str]:
    """
    Executa comando e retorna resultado.
    
    Returns:
        (success, output)
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check,
        )
        return (True, result.stdout.strip())
    except subprocess.CalledProcessError as e:
        return (False, e.stderr.strip())
    except FileNotFoundError:
        return (False, f"Comando não encontrado: {cmd[0]}")


def check_git_repo() -> bool:
    """Verifica se está em repositório git."""
    success, _ = run_command(["git", "rev-parse", "--git-dir"], check=False)
    return success


def install_pre_commit() -> bool:
    """Verifica e instala pre-commit se necessário."""
    # Verificar se pre-commit está instalado
    success, _ = run_command(["pre-commit", "--version"], check=False)
    
    if success:
        print_colored("  ✓ pre-commit já está instalado", Color.GREEN)
        return True
    
    print_colored("  ⚠ pre-commit não encontrado, instalando...", Color.YELLOW)
    
    # Tentar instalar via pip
    success, output = run_command(
        [sys.executable, "-m", "pip", "install", "pre-commit"],
        check=False
    )
    
    if not success:
        print_colored(f"  ✗ Falha ao instalar pre-commit: {output}", Color.RED)
        return False
    
    print_colored("  ✓ pre-commit instalado com sucesso", Color.GREEN)
    return True


def install_pre_commit_hooks() -> bool:
    """Instala hooks do pre-commit."""
    print("  Instalando hooks...")
    
    # Install commit hook
    success1, output1 = run_command(["pre-commit", "install"], check=False)
    if not success1:
        print_colored(f"  ✗ Erro ao instalar commit hook: {output1}", Color.RED)
        return False
    
    # Install commit-msg hook
    success2, output2 = run_command(
        ["pre-commit", "install", "--hook-type", "commit-msg"],
        check=False
    )
    if not success2:
        print_colored(f"  ✗ Erro ao instalar commit-msg hook: {output2}", Color.RED)
        return False
    
    print_colored("  ✓ Hooks instalados com sucesso", Color.GREEN)
    return True


def configure_commit_template() -> bool:
    """Configura template de commit no git."""
    template_path = ".git-commit-template"
    
    if not Path(template_path).exists():
        print_colored(f"  ✗ Template não encontrado: {template_path}", Color.RED)
        return False
    
    success, output = run_command(
        ["git", "config", "commit.template", template_path],
        check=False
    )
    
    if not success:
        print_colored(f"  ✗ Erro ao configurar template: {output}", Color.RED)
        return False
    
    print_colored(f"  ✓ Template configurado: {template_path}", Color.GREEN)
    return True


def run_initial_hooks_test() -> bool:
    """Roda hooks em todos os arquivos para testar."""
    print("  Testando hooks (pode demorar alguns segundos)...")
    
    success, output = run_command(
        ["pre-commit", "run", "--all-files"],
        check=False
    )
    
    # Pre-commit retorna 1 se fez alguma correção, mas isso é OK
    # Só é erro se houver falha crítica
    if "error" in output.lower() or "failed" in output.lower():
        print_colored("  ⚠ Alguns hooks falharam, mas setup completo", Color.YELLOW)
        print(f"    Execute 'pre-commit run --all-files' para ver detalhes")
        return True
    
    print_colored("  ✓ Hooks executados com sucesso", Color.GREEN)
    return True


def print_summary() -> None:
    """Exibe sumário com próximos passos."""
    print_colored("\n" + "═" * 70, Color.BOLD)
    print_colored("  ✅ Configuração de Governança de Commits Concluída!", Color.GREEN)
    print_colored("═" * 70, Color.BOLD)
    
    print_colored("\n📝 O que foi configurado:", Color.BLUE)
    print("  • Pre-commit hooks instalados")
    print("  • Validação de tamanho de commit ativa")
    print("  • Validação de formato Conventional Commits ativa")
    print("  • Template de commit configurado")
    print("  • Validações de segurança (arquivos grandes, secrets)")
    
    print_colored("\n🚀 Próximos passos:", Color.BLUE)
    print("  1. Teste o fluxo:")
    print("     git add <arquivo>")
    print("     git commit    # Template será exibido no editor")
    print()
    print("  2. Valide antes de commitar:")
    print("     python scripts/dev/validate_commit_size.py")
    print()
    print("  3. Audite histórico:")
    print("     python scripts/dev/audit_commit_history.py")
    
    print_colored("\n📚 Documentação:", Color.BLUE)
    print("  • Guia completo:  COMMIT_GOVERNANCE.md")
    print("  • Guia rápido:    COMMIT_GOVERNANCE_QUICKSTART.md")
    print("  • Conventional:   https://www.conventionalcommits.org/")
    
    print_colored("\n💡 Dica:", Color.YELLOW)
    print("  Execute 'pre-commit run --all-files' para verificar todos os arquivos.")
    print()


def main() -> int:
    """Entry point do script."""
    print_colored("\n" + "═" * 70, Color.BOLD)
    print_colored("  🔧 Setup de Governança de Commits — Concilium", Color.BOLD)
    print_colored("═" * 70, Color.BOLD)
    
    # Etapa 1: Verificar git repo
    print_step(1, "Verificando repositório Git...")
    
    if not check_git_repo():
        print_colored("\n❌ Erro: Não está em um repositório Git", Color.RED)
        print("   Execute este script na raiz do repositório.")
        return 1
    
    print_colored("  ✓ Repositório Git detectado", Color.GREEN)
    
    # Etapa 2: Instalar pre-commit
    print_step(2, "Verificando pre-commit...")
    
    if not install_pre_commit():
        print_colored("\n❌ Erro ao instalar pre-commit", Color.RED)
        print("   Instale manualmente: pip install pre-commit")
        return 1
    
    # Etapa 3: Instalar hooks
    print_step(3, "Instalando pre-commit hooks...")
    
    if not install_pre_commit_hooks():
        print_colored("\n❌ Erro ao instalar hooks", Color.RED)
        return 1
    
    # Etapa 4: Configurar template
    print_step(4, "Configurando template de commit...")
    
    if not configure_commit_template():
        print_colored("\n⚠ Template não configurado (não crítico)", Color.YELLOW)
        # Não retorna erro, template é opcional
    
    # Etapa 5: Testar hooks
    print_step(5, "Testando hooks...")
    
    run_initial_hooks_test()
    
    # Sumário
    print_summary()
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print_colored("\n\n⚠️  Setup cancelado pelo usuário.", Color.YELLOW)
        sys.exit(1)
    except Exception as e:
        print_colored(f"\n❌ Erro inesperado: {e}", Color.RED)
        import traceback
        traceback.print_exc()
        sys.exit(1)
