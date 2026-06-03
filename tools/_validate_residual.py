"""Relatório de erros residuais de validação de schema."""
import io, sys, json
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from jsonschema import Draft202012Validator, RefResolver  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = ROOT / "config" / "schemas" / "catalog"

def load(n):
    return json.loads((SCHEMA_ROOT / n).read_text(encoding="utf-8"))

def _store() -> dict:
    out = {}
    for f in SCHEMA_ROOT.glob("*.schema.json"):
        sc = json.loads(f.read_text(encoding="utf-8"))
        if "$id" in sc:
            out[sc["$id"]] = sc
    return out

_STORE = _store()

def make_val(s):
    base = SCHEMA_ROOT.as_uri() + "/"
    return Draft202012Validator(s, resolver=RefResolver(base_uri=base, referrer=s, store=_STORE))

cpu_v = make_val(load("cpu.schema.json"))
prod_v = make_val(load("producao.schema.json"))
ins_v = make_val(load("insumo.schema.json"))

bundle = json.loads((ROOT / "config/catalogos/mendeslobo/.catalog_bundle.json").read_text(encoding="utf-8"))
cpus = bundle.get("cpus", [])
insumos = bundle.get("insumos", [])
prods = bundle.get("producoes", []) or bundle.get("produtividades", [])

erros: list[str] = []
for e in cpus:
    for err in cpu_v.iter_errors(e):
        p = ".".join(str(x) for x in err.absolute_path)
        erros.append(f"CPU {e.get('codigo')}: [{p or '<root>'}] {err.message[:100]}")
for e in prods:
    for err in prod_v.iter_errors(e):
        p = ".".join(str(x) for x in err.absolute_path)
        erros.append(f"PROD {e.get('id')}: [{p or '<root>'}] {err.message[:100]}")
for e in insumos:
    for err in ins_v.iter_errors(e):
        p = ".".join(str(x) for x in err.absolute_path)
        erros.append(f"INS {e.get('codigo')}: [{p or '<root>'}] {err.message[:100]}")

tipos: Counter = Counter()
for e in erros:
    msg = e.split("] ", 1)[-1][:60]
    tipos[msg] += 1

print(f"Total erros residuais: {len(erros)}")
print(f"  CPU: {sum(1 for e in erros if e.startswith('CPU'))}")
print(f"  PROD: {sum(1 for e in erros if e.startswith('PROD'))}")
print(f"  INS: {sum(1 for e in erros if e.startswith('INS'))}")
print()
print("Top tipos de erro (agrupados):")
for msg, cnt in tipos.most_common(25):
    print(f"  {cnt:4d}x  {msg}")
print()
print("Amostra (primeiros 40 erros):")
for e in erros[:40]:
    print(" ", e)
