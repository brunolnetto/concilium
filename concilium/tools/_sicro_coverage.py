"""Analisa cobertura SICRO vs catálogo e identifica o que pode ser atualizado."""
import io, json, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sicro_path = ROOT / "config/referencias/SICRO/BR-CE/insumos.json"
bundle_path = ROOT / "config/catalogos/mendeslobo/.catalog_bundle.json"

sicro_data = json.loads(sicro_path.read_text(encoding="utf-8"))
sicro_ins   = sicro_data.get("insumos", [])
bundle      = json.loads(bundle_path.read_text(encoding="utf-8"))
cat_insumos = bundle.get("insumos", [])

# Índice SICRO por código de referência
sicro_by_cod  = {i["codigo_referencia"]: i for i in sicro_ins if i.get("codigo_referencia")}
sicro_by_desc = {}  # fuzzy fallback

por_tipo = {}
for i in sicro_ins:
    t = i.get("tipo","?")
    por_tipo[t] = por_tipo.get(t, 0) + 1
print(f"SICRO BR-CE {sicro_data.get('versao')} — {len(sicro_ins)} insumos")
for t, n in sorted(por_tipo.items()):
    print(f"  {t}: {n}")

# Stale no catálogo
stale = [i for i in cat_insumos if (i.get("data_referencia_preco") or "") <= "2025-12-31"]
print(f"\nInsumos STALE no catálogo (data <= 2025-12-31): {len(stale)}")
stale_por_tipo = {}
for i in stale:
    t = i.get("tipo","?")
    stale_por_tipo[t] = stale_por_tipo.get(t, 0) + 1
for t, n in sorted(stale_por_tipo.items()):
    print(f"  {t}: {n}")

# Match via codigo_referencia_externa (P#### para MAO_OBRA, E#### para EQ, M#### para MAT)
print("\nCOBERTURA POR TIPO:")
for tipo in ("MAO_OBRA", "EQUIPAMENTO", "MATERIAL"):
    cat_tipo = [i for i in stale if i.get("tipo") == tipo]
    matched, unmatched = [], []
    for ins in cat_tipo:
        ext = ins.get("codigo_referencia_externa") or ""
        codes = [c.strip() for c in ext.split(",") if c.strip()]
        also_check = [ins.get("codigo")] if ins.get("codigo") else []
        found = next((c for c in codes + also_check if c in sicro_by_cod), None)
        if found:
            matched.append((ins["codigo"], found, sicro_by_cod[found].get("preco_publicado")))
        else:
            unmatched.append(ins)

    print(f"\n  {tipo} ({len(cat_tipo)} stale):")
    print(f"    Mapeáveis via SICRO: {len(matched)}")
    print(f"    Sem mapeamento:      {len(unmatched)}")
    if matched[:5]:
        print(f"    Amostra matched:")
        for cat_cod, sicro_cod, preco in matched[:5]:
            print(f"      {cat_cod:<30} ← SICRO {sicro_cod} R${preco}")
    if unmatched[:5]:
        print(f"    Amostra sem match (precisam de pesquisa/web):")
        for ins in unmatched[:5]:
            print(f"      {ins['codigo']:<30} desc={ins.get('descricao','')[:35]}")

# Mostra amostra do SICRO MAO_OBRA para avaliar estrutura
print("\nAMOSTRA SICRO MAO_OBRA (primeiros 8):")
mo_sicro = [i for i in sicro_ins if i.get("tipo") == "MAO_OBRA"][:8]
for i in mo_sicro:
    print(f"  {i.get('codigo_referencia','?'):8} {i.get('descricao','')[:40]:40} R${i.get('preco_publicado')}/h")
