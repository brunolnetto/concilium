import json, sys, io
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]

# Contexto test
ctx = ROOT / "config/contextos/test.json"
if ctx.exists():
    d = json.loads(ctx.read_text(encoding="utf-8"))
    cat_id = d.get("catalogo_id", "?")
    print(f"contexto test catalogo_id: {cat_id}")
else:
    print("contexto test.json NAO ENCONTRADO")
    cat_id = None

# Bundle mendeslobo
bundle = ROOT / "config/catalogos/mendeslobo/.catalog_bundle.json"
b = json.loads(bundle.read_text(encoding="utf-8"))
cpus = b.get("cpus", [])
targets = ["ESCO-CARGA-1CAT-DMT2000", "CPU-TERRA-ESCO-CARGA-1CAT-DMT2000", "CPU-ESCO-CARGA-1CAT-DMT2000"]
for t in targets:
    found = [c for c in cpus if c.get("codigo") == t]
    print(f"  {t}: {'FOUND' if found else 'NOT FOUND'}")

# Lista catálogos disponíveis
print("\nCatálogos disponíveis:")
for f in (ROOT / "config/catalogos").iterdir():
    if f.is_dir():
        print(f"  {f.name}")

# O que os testes usam como EAP
import re
test_files = list((ROOT / "tests").rglob("*.py"))
pattern = re.compile(r"cpu_id.*['\"]([A-Z][A-Z0-9-]+)['\"]")
cpu_ids_in_tests = set()
for tf in test_files:
    for m in pattern.findall(tf.read_text(encoding="utf-8", errors="replace")):
        if "ESCO" in m or "CPU" in m:
            cpu_ids_in_tests.add(m)
print("\nCPU IDs com ESCO/CPU nos testes:")
for c in sorted(cpu_ids_in_tests):
    found = any(cpu.get("codigo") == c for cpu in cpus)
    print(f"  {c}: {'OK' if found else 'MISSING'}")
