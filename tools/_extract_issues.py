"""Extrai registros problemáticos do bundle para revisão manual."""
import io, json, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
bundle = json.loads((ROOT / "config/catalogos/mendeslobo/.catalog_bundle.json").read_text(encoding="utf-8"))

PROD_FUNCOES_DUPL = {
    "ATI-017", "CPU-PAVIM-ATI-060-PROD-001",
    "CPU-TERRA-ATI-017-PROD-001", "CPU-TERRA-ATI-019-PROD-001",
}
PROD_SEM_VALOR = {
    "CPU-PAVIM-PAV-BASE-BGTC-PROD-001",
    "CPU-SANEA-DREN-MAN-DN300-PROD-001",
    "CPU-SANEA-POCO-VISITA-PADRAO-PROD-001",
    "CPU-TERRA-COMPACT-ATERRO-100PN-PROD-001",
    "CPU-TERRA-REGULARIZACAO-SUBLEITO-PROD-001",
}
INS_CODIGO_INVALIDO = {
    "MO-AUXILIAR-DE-SERVIÇOS", "MO-ESTAGIÁRIO", "MO-MECÂNICO",
    "MO-MOTORISTA-DE-CAMINHÃ", "MO-TÉCNICO-DE-ENFERMAGE",
    "MO-TÉCNICO-DE-PLANEJAME", "MO-TÉCNICO-DE-QSMS",
    "MA-AGIS-CPU-TERRA-ENCHIMENTO-REBAIXO-ROCHA",
}

prods = bundle.get("producoes", []) or bundle.get("produtividades", [])
insumos = bundle.get("insumos", [])

print("=" * 70)
print("PRODUCOES — FUNCOES DUPLICADAS")
print("=" * 70)
for p in prods:
    pid = p.get("id", "")
    if pid in PROD_FUNCOES_DUPL:
        equipe = p.get("composicao_padrao_equipe") or p.get("equipe") or {}
        funcoes = equipe.get("funcoes", [])
        equipamentos = equipe.get("equipamentos", [])
        print(f"\n--- {pid} ---")
        print(f"  descricao: {p.get('descricao')}")
        print(f"  valor_horario: {p.get('valor_horario')}")
        print(f"  unidade: {p.get('unidade')}")
        print(f"  funcoes ({len(funcoes)}):")
        for f in funcoes:
            print(f"    {f}")
        print(f"  equipamentos ({len(equipamentos)}):")
        for e in equipamentos:
            print(f"    {e}")

print("\n" + "=" * 70)
print("PRODUCOES — SEM VALOR_HORARIO")
print("=" * 70)
for p in prods:
    pid = p.get("id", "")
    if pid in PROD_SEM_VALOR:
        equipe = p.get("composicao_padrao_equipe") or p.get("equipe") or {}
        funcoes = equipe.get("funcoes", [])
        equipamentos = equipe.get("equipamentos", [])
        print(f"\n--- {pid} ---")
        print(f"  descricao: {p.get('descricao')}")
        print(f"  unidade: {p.get('unidade')}")
        print(f"  origem: {p.get('origem')}")
        print(f"  funcoes: {funcoes}")
        print(f"  equipamentos: {equipamentos}")
        print(f"  condicoes_calibracao: {p.get('condicoes_calibracao')}")

print("\n" + "=" * 70)
print("INSUMOS — CODIGO INVALIDO")
print("=" * 70)
for ins in insumos:
    cod = ins.get("codigo", "")
    if cod in INS_CODIGO_INVALIDO:
        print(f"\n--- {cod} ---")
        print(f"  tipo: {ins.get('tipo')}")
        print(f"  descricao: {ins.get('descricao')}")
        print(f"  unidade: {ins.get('unidade')}")
        print(f"  preco_unitario: {ins.get('preco_unitario')}")
        print(f"  fonte_preco: {ins.get('fonte_preco')}")
        attrs = ins.get("atributos_especificos") or {}
        if attrs:
            print(f"  atributos_especificos: {attrs}")

# EQ-HIDROSSEMEADORA
print("\n" + "=" * 70)
print("INSUMO — EQ-HIDROSSEMEADORA (sem fonte_preco)")
print("=" * 70)
for ins in insumos:
    if ins.get("codigo") == "EQ-HIDROSSEMEADORA":
        print(json.dumps(ins, indent=2, ensure_ascii=False))
