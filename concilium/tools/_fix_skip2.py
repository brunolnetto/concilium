"""Skip remaining tests with removed commands."""
from pathlib import Path

f = Path("tests/unit/test_coverage_boost_main.py")
c = f.read_bytes()

skip_adapter = b'@pytest.mark.skip(reason="adapter run command removed")\n'
skip_scenario = b'@pytest.mark.skip(reason="scenario run command removed")\n'

c = c.replace(b'def test_adapter_run_success_path(', skip_adapter + b'def test_adapter_run_success_path(')
c = c.replace(b'def test_scenario_run_full_output(', skip_scenario + b'def test_scenario_run_full_output(')

f.write_bytes(c)
print("Done")
