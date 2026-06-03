import sys
sys.path.insert(0, 'src')
sys.path.insert(0, 'tests/unit')

# Import helpers from the test file
import importlib.util
spec = importlib.util.spec_from_file_location("test09", "tests/unit/test_09_criticality_pareto.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

equipes = [mod._equipe("atv-001", 600000.0, 50000.0, 6.0)]
c = mod._canonical(equipes_diretas=equipes, planejamento=mod._planejamento_stub())

from concilium.application.skills import run_diagnostico_criticidade
result = run_diagnostico_criticidade(c, {})
print(f"has_errors: {result.has_errors}")
for v in result.validacoes:
    print(f"  [{v.status}] {v.codigo}: {v.mensagem}")
