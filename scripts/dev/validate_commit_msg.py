#!/usr/bin/env python3
"""
Script de validação de mensagem de commit.

Valida formato de mensagens de commit seguindo Conventional Commits
conforme definido em COMMIT_GOVERNANCE.md.

Uso:
    # Como pre-commit hook (automático)
    # Configurado em .pre-commit-config.yaml

    # Teste manual
    echo "feat(api): nova feature" | python scripts/dev/validate_commit_msg.py /dev/stdin

Exit codes:
    0 - Mensagem válida
    1 - Mensagem inválida (bloqueia commit)
"""

import re
import sys
from pathlib import Path

# ── Configuração ────────────────────────────────────────────────────────────

# Tipos válidos (Conventional Commits)
VALID_TYPES = {
    "feat", "fix", "refactor", "perf", "test",
    "docs", "style", "build", "ci", "chore", "revert"
}

# Comprimento máximo da linha de resumo
MAX_SUBJECT_LENGTH = 72

# Padrão de formato esperado
# tipo(escopo): mensagem
# ou: tipo: mensagem
COMMIT_MSG_PATTERN = r"^([a-z]+)(\([a-z0-9\-_/]+\))?: .+"

# Padrões que indicam exceção permitida
EXCEPTION_KEYWORDS = [
    "[EXCEÇÃO:",
    "[EXCEPTION:",
    "BREAKING CHANGE:",
    "Merge branch",
    "Revert ",
]

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


# ── Validações ──────────────────────────────────────────────────────────────

def is_exception_commit(message: str) -> bool:
    """Verifica se commit é uma exceção permitida."""
    return any(keyword in message for keyword in EXCEPTION_KEYWORDS)


def validate_commit_message(message: str) -> tuple[bool, list[str]]:
    """
    Valida mensagem de commit.
    
    Returns:
        (is_valid, error_messages)
    """
    lines = message.strip().split("\n")
    
    if not lines:
        return (False, ["Mensagem de commit está vazia"])
    
    subject = lines[0].strip()
    errors = []
    
    # Exceções automáticas (merge commits, reverts)
    if is_exception_commit(subject):
        return (True, [])
    
    # Validação 1: Formato Conventional Commits
    match = re.match(COMMIT_MSG_PATTERN, subject.lower())
    
    if not match:
        errors.append(
            "Formato inválido. Use: tipo(escopo): mensagem\n"
            "  Exemplo: feat(api): adicionar endpoint de validação\n"
            "  Ou: fix(catalog): corrigir cálculo de BDI"
        )
        return (False, errors)
    
    # Extrair tipo e escopo
    commit_type = match.group(1)
    commit_scope = match.group(2)[1:-1] if match.group(2) else None
    
    # Validação 2: Tipo válido
    if commit_type not in VALID_TYPES:
        errors.append(
            f"Tipo '{commit_type}' inválido.\n"
            f"  Tipos válidos: {', '.join(sorted(VALID_TYPES))}"
        )
    
    # Validação 3: Comprimento da linha de resumo
    if len(subject) > MAX_SUBJECT_LENGTH:
        errors.append(
            f"Linha de resumo muito longa: {len(subject)} caracteres "
            f"(máximo: {MAX_SUBJECT_LENGTH})"
        )
    
    # Validação 4: Mensagem começa com letra minúscula após ':'
    message_part = subject.split(":", 1)[1].strip() if ":" in subject else ""
    if message_part and message_part[0].isupper():
        # Permitir exceções como "API", "BDI", etc
        if not message_part.split()[0].isupper():
            errors.append(
                "Mensagem deve começar com letra minúscula após ':'\n"
                f"  Atual: '{message_part}'\n"
                f"  Correto: '{message_part[0].lower() + message_part[1:]}'"
            )
    
    # Validação 5: Mensagem não termina com ponto
    if subject.endswith("."):
        errors.append(
            "Linha de resumo não deve terminar com ponto"
        )
    
    # Validação 6: Corpo separado por linha em branco (se existir)
    if len(lines) > 1 and lines[1].strip() != "":
        errors.append(
            "Corpo da mensagem deve ser separado do resumo por uma linha em branco"
        )
    
    return (len(errors) == 0, errors)


def validate_commit_msg_file(filepath: str) -> int:
    """
    Valida mensagem de commit de um arquivo.
    
    Returns:
        0 se válido, 1 se inválido
    """
    try:
        message = Path(filepath).read_text(encoding="utf-8")
    except Exception as e:
        print_colored(f"❌ Erro ao ler arquivo de commit: {e}", Color.RED)
        return 1
    
    # Remover comentários do git (linhas começando com #)
    lines = [
        line for line in message.split("\n")
        if not line.strip().startswith("#")
    ]
    message_clean = "\n".join(lines).strip()
    
    if not message_clean:
        print_colored("\n❌ Mensagem de commit vazia", Color.RED)
        return 1
    
    is_valid, errors = validate_commit_message(message_clean)
    
    if is_valid:
        print_colored("\n✅ Mensagem de commit válida", Color.GREEN)
        return 0
    
    # Exibir erros
    print_colored("\n🚫 MENSAGEM DE COMMIT INVÁLIDA", Color.RED)
    print_colored("─" * 70, Color.RED)
    
    for error in errors:
        print_colored(f"\n  {error}", Color.YELLOW)
    
    print_colored("\n💡 Formato esperado:", Color.BLUE)
    print("  tipo(escopo): mensagem breve")
    print()
    print("  [corpo opcional com contexto]")
    print()
    print("  [footer opcional: refs, breaking changes]")
    
    print_colored("\n📚 Exemplos válidos:", Color.GREEN)
    print("  feat(api): adicionar endpoint de validação")
    print("  fix(catalog): corrigir cálculo de BDI em CPU tipo 3")
    print("  docs(readme): atualizar instruções de instalação")
    print("  refactor(skills): extrair função de validação comum")
    
    print_colored("\n  Ver COMMIT_GOVERNANCE.md para detalhes completos.\n", Color.BLUE)
    
    return 1


# ── Entry Point ─────────────────────────────────────────────────────────────

def main() -> int:
    """Entry point do script."""
    if len(sys.argv) < 2:
        print_colored(
            "Uso: validate_commit_msg.py <commit-msg-file>",
            Color.RED
        )
        return 1
    
    commit_msg_file = sys.argv[1]
    
    try:
        return validate_commit_msg_file(commit_msg_file)
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
