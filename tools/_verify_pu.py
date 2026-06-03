"""Verifica integridade de PU no catálogo após merge."""
import io, json, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from concilium.application.catalog.pu_calculator import calcular_catalogo, ParametrosCalculo

bundle = json.loads((ROOT / "config/catalogos/mendeslobo/.catalog_bundle.json").read_text(encoding="utf-8"))
insumos   = bundle.get("insumos", [])
producoes = bundle.get("producoes", []) or bundle.get("produtividades", [])

params = ParametrosCalculo(alpha_clt=1.777, alpha_pj=1.06, preco_diesel=6.50)
result = calcular_catalogo(producoes, insumos, params)

print(f"Total producoes      : {result['total_producoes']}")
print(f"Com composicao       : {result['com_composicao']}")
print(f"Sem valor_horario    : {len(result['sem_valor_horario'])}")
print(f"Refs faltantes       : {len(result['referencias_faltantes'])}")
print(f"PU divergentes       : {len(result['pu_divergentes'])}")
print(f"Status global        : {'OK' if result['ok'] else 'ERRO'}")

if result["referencias_faltantes"]:
    print(f"\nReferências faltantes ({len(result['referencias_faltantes'])}):")
    for r in result["referencias_faltantes"][:20]:
        print(f"  {r['producao_id']}: {r['faltantes']}")

if result["sem_valor_horario"]:
    print(f"\nSem valor_horario ({len(result['sem_valor_horario'])}):")
    for pid in result["sem_valor_horario"][:10]:
        print(f"  {pid}")

# Amostra de PUs calculados
print(f"\nAmostra de PUs calculados (primeiras 10 producoes com composicao):")
shown = 0
for bd in result["breakdown_por_producao"]:
    if shown >= 10: break
    pu = bd["pu_calculado"]
    total_h = bd["breakdown"]["total_h"]
    vh = bd["valor_horario"]
    refs = len(bd["referencias_faltantes"])
    status = "OK" if refs == 0 else f"ERRO({refs} refs)"
    print(f"  {bd['producao_id']:40} PU={pu!s:10} CH={total_h:.2f} VH={vh} {status}")
    shown += 1
