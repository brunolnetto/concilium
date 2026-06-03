"""Analisa test_report.json para categorizar as falhas restantes."""
import io, json, sys, re
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

report = json.loads(Path("test_report.json").read_text(encoding="utf-8"))
tests  = report.get("tests", [])

failed = [t for t in tests if t.get("outcome") == "failed"]
print(f"Total falhas: {len(failed)}")

# Agrupa por mensagem de erro (normalizada)
def normalize_msg(msg):
    if not msg: return "UNKNOWN"
    # Pega primeira linha relevante
    lines = [l.strip() for l in msg.splitlines() if l.strip() and not l.startswith(" ")]
    for l in lines:
        if "Error" in l or "assert" in l or "FAILED" in l:
            return re.sub(r"0x[0-9a-f]+", "0xADDR", l)[:100]
    return lines[0][:100] if lines else msg[:100]

groups = defaultdict(list)
for t in failed:
    call  = t.get("call") or {}
    crash = call.get("crash") or {}
    msg   = crash.get("message", "") or call.get("longrepr", "")[:200]
    key   = normalize_msg(msg)
    groups[key].append(t["nodeid"])

print(f"\nPadrões de erro ({len(groups)} únicos):")
for msg, nodes in sorted(groups.items(), key=lambda x: -len(x[1]))[:25]:
    files = set(n.split("::")[0] for n in nodes)
    print(f"\n  [{len(nodes)}x] {msg[:90]}")
    for f in sorted(files)[:3]:
        short = f.replace("tests/unit/","").replace("tests/integration/","")
        print(f"    ← {short}")

# Por arquivo de teste
print("\n\nFALHAS POR ARQUIVO:")
by_file = Counter(t["nodeid"].split("::")[0] for t in failed)
for f, n in by_file.most_common(15):
    short = f.replace("tests/unit/","").replace("tests/integration/","")
    print(f"  {n:3d}x  {short}")
