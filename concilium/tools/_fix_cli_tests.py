"""Corrige test_cli_commands.py para refletir nova estrutura CLI."""
import io, re, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

f = Path("tests/unit/test_cli_commands.py")
src = f.read_text(encoding="utf-8")

# Comandos que foram movidos para baixo de `project`
# Só substituímos dentro de runner.invoke(app, [...]) para não quebrar strings
MOVES = [
    (r'runner\.invoke\(app, \["init",', 'runner.invoke(app, ["project", "init",'),
    (r'runner\.invoke\(app, \["init"\]', 'runner.invoke(app, ["project", "init"]'),
    (r'runner\.invoke\(app, \["status",', 'runner.invoke(app, ["project", "status",'),
    (r'runner\.invoke\(app, \["validate",', 'runner.invoke(app, ["project", "validate",'),
    (r'runner\.invoke\(app, \["run",', 'runner.invoke(app, ["project", "run",'),
    (r'runner\.invoke\(app, \["approve",', 'runner.invoke(app, ["project", "approve",'),
    (r'runner\.invoke\(app, \["audit",', 'runner.invoke(app, ["project", "audit",'),
]

for pattern, replacement in MOVES:
    src = re.sub(pattern, replacement, src)

# Substituir "version new" pelo equivalente programático (helper function)
# Adiciona helper no topo depois dos imports
HELPER = '''
def _new_version(projects_root: Path, project_name: str) -> None:
    """Cria nova versão de projeto via ProjectStore (substitui 'version new' CLI removida)."""
    from concilium.infrastructure.storage.project import ProjectStore
    for d in projects_root.iterdir():
        if d.is_dir() and (d / "meta.json").exists():
            import json as _json
            meta = _json.loads((d / "meta.json").read_text(encoding="utf-8"))
            if meta.get("nome") == project_name:
                ps = ProjectStore(d)
                ps.new_version()
                return

'''

# Insere helper após os imports
src = re.sub(
    r'(runner = CliRunner\(\)\n)',
    r'\1' + HELPER,
    src,
)

# Substitui chamadas "version new" pelo helper
src = re.sub(
    r'runner\.invoke\(app, \["version", "new", "([^"]+)"(?:, "[^"]*")?\]\)',
    lambda m: f'_new_version(Path(env_with_config["projects"]), "{m.group(1)}")',
    src,
)

# Marca testes que usam snapshot como skip (comando removido)
src = re.sub(
    r'(def test_cli_snapshot_)',
    r'@pytest.mark.skip(reason="snapshot command removed from CLI")\n\1',
    src,
)

# Corrige test_cli_init_help → usa project
src = src.replace(
    'runner.invoke(app, ["project", "init", "--help"])',
    'runner.invoke(app, ["project", "init", "--help"])',
)
# Garante que test_cli_init_help usa o path correto
src = src.replace(
    'result = runner.invoke(app, ["init", "--help"])',
    'result = runner.invoke(app, ["project", "init", "--help"])',
)

# Fix: test_cli_init_missing_config usa invoke sem nome, adiciona nome dummy
src = src.replace(
    'result = runner.invoke(app, ["project", "init", "X"])',
    'result = runner.invoke(app, ["project", "init", "X", "--contexto", "mendeslobo"])',
)

f.write_text(src, encoding="utf-8")
print("test_cli_commands.py corrigido.")

# Verifica resultado
lines_with_old_pattern = [i+1 for i, l in enumerate(src.splitlines())
                           if 'invoke(app, ["init"' in l or 'invoke(app, ["status"' in l
                           or 'invoke(app, ["run"' in l or 'invoke(app, ["validate"' in l]
if lines_with_old_pattern:
    print(f"AVISO: ainda há padrões antigos nas linhas: {lines_with_old_pattern}")
else:
    print("Todos os padrões antigos foram substituídos.")
