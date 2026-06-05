"""
Stage 2 — SICRO Injector
========================
Lê um JSON de referência SICRO (gerado pelo sicro_fetch.py) e o mapeamento
(sicro_concilium_mapping.yaml), então injeta/atualiza blocos `regionalizacao`
nos arquivos JSON de insumos do catálogo Concilium.

Uso:
    # Injeta CE/2026-01 em todos os insumos mapeados:
    python scripts/sicro_inject.py --ref SICRO_2026_01_CE.json --uf CE

    # Dry-run (mostra o que seria alterado sem gravar):
    python scripts/sicro_inject.py --ref SICRO_2026_01_CE.json --uf CE --dry-run

    # Insumo específico apenas:
    python scripts/sicro_inject.py --ref SICRO_2026_01_CE.json --uf CE --insumo MA-BRITA-1

Resultado em cada JSON de insumo:
    {
      ...campos existentes...,
      "regionalizacao": [
        {
          "jurisdicao_id": "BR-CE",
          "preco_unitario": 95.40,
          "fonte_preco": "SICRO_DNIT",
          "data_referencia": "2026-01-01",
          "sicro_codigo": "I 03 050 01",
          "sicro_descricao": "Brita nº 1",
          "url_fonte": "https://www.gov.br/dnit/..."
        }
      ]
    }

Nota: entradas existentes para a mesma jurisdicao_id são SUBSTITUÍDAS (upsert).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
REFERENCIAS_DIR = PROJECT_ROOT / "config" / "referencias"
CATALOG_ROOT = PROJECT_ROOT / "config" / "catalogos" / "mendeslobo" / "insumos"
MAPPING_FILE = REFERENCIAS_DIR / "sicro_concilium_mapping.yaml"

# Mapeamento UF → jurisdicao_id Concilium
UF_TO_JURISDICAO: dict[str, str] = {
    "AC": "BR-AC", "AL": "BR-AL", "AM": "BR-AM", "AP": "BR-AP",
    "BA": "BR-BA", "CE": "BR-CE", "DF": "BR-DF", "ES": "BR-ES",
    "GO": "BR-GO", "MA": "BR-MA", "MG": "BR-MG", "MS": "BR-MS",
    "MT": "BR-MT", "PA": "BR-PA", "PB": "BR-PB", "PE": "BR-PE",
    "PI": "BR-PI", "PR": "BR-PR", "RJ": "BR-RJ", "RN": "BR-RN",
    "RO": "BR-RO", "RR": "BR-RR", "RS": "BR-RS", "SC": "BR-SC",
    "SE": "BR-SE", "SP": "BR-SP", "TO": "BR-TO",
}


# ---------------------------------------------------------------------------
# Leitura do mapeamento
# ---------------------------------------------------------------------------

def load_mapping(path: Path) -> list[dict]:
    """Carrega sicro_concilium_mapping.yaml. Fallback para json se yaml ausente."""
    if not path.exists():
        print(f"ERRO: arquivo de mapeamento não encontrado: {path}", file=sys.stderr)
        sys.exit(1)

    text = path.read_text(encoding="utf-8")

    if yaml is not None:
        data = yaml.safe_load(text)
    else:
        # Tenta JSON como fallback
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            print(
                "ERRO: PyYAML não instalado e o arquivo não é JSON.\n"
                "  Instale: pip install pyyaml",
                file=sys.stderr,
            )
            sys.exit(1)

    return data.get("mappings", [])


# ---------------------------------------------------------------------------
# Leitura da referência SICRO
# ---------------------------------------------------------------------------

def load_sicro_ref(path: Path) -> dict[str, dict]:
    """
    Carrega JSON de referência SICRO e retorna índice por código SICRO.
    Suporta novo formato (insumos.json com campo "insumos") e formato legado
    (campo "insumos_referencia").
    Retorna: {codigo_sicro: {descricao, unidade, preco_publicado, url_fonte}}
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    url_fonte = data.get("url_fonte", "")
    data_vigencia = data.get("data_vigencia", "")

    # Suporta novo formato ("insumos") e legado ("insumos_referencia")
    items = data.get("insumos") or data.get("insumos_referencia", [])

    index: dict[str, dict] = {}
    for item in items:
        cod = item.get("codigo_referencia", "").strip()
        if cod:
            index[cod] = {
                "descricao": item.get("descricao", ""),
                "unidade": item.get("unidade", ""),
                "preco_publicado": item.get("preco_publicado"),
                "url_fonte": url_fonte,
                "data_vigencia": data_vigencia,
            }
    return index


# ---------------------------------------------------------------------------
# Localiza o arquivo JSON de um insumo no catálogo
# ---------------------------------------------------------------------------

def find_insumo_file(concilium_id: str) -> Path | None:
    """Procura o arquivo .json do insumo nas pastas material/equipamento/mao_obra."""
    for folder in (CATALOG_ROOT / "material", CATALOG_ROOT / "equipamento", CATALOG_ROOT / "mao_obra"):
        candidate = folder / f"{concilium_id}.json"
        if candidate.exists():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Upsert de bloco de regionalização
# ---------------------------------------------------------------------------

def upsert_regionalizacao(insumo_data: dict, entry: dict) -> tuple[dict, bool]:
    """
    Faz upsert de um entry em insumo_data["regionalizacao"].
    Retorna (novo_data, foi_alterado).

    Migra automaticamente o formato antigo (dict keyed by jurisdicao_id) para o
    novo formato lista definido em ADR-035.
    """
    jurisdicao_id = entry["jurisdicao_id"]
    raw = insumo_data.get("regionalizacao", [])

    # Migra formato antigo: {"BR-CE": {"preco": ..., "nota": ...}} → lista
    if isinstance(raw, dict):
        existing: list[dict] = []
        for jid, val in raw.items():
            existing.append({
                "jurisdicao_id": jid,
                "preco_unitario": val.get("preco") if isinstance(val, dict) else val,
                "fonte_preco": "legado",
                "data_referencia": "",
                "sicro_codigo": None,
                "sicro_descricao": "",
                "url_fonte": "",
            })
    else:
        existing = list(raw)

    updated = [e for e in existing if e.get("jurisdicao_id") != jurisdicao_id]
    updated.append(entry)

    # Ordena por jurisdicao_id para saída determinística
    updated.sort(key=lambda e: e.get("jurisdicao_id", ""))

    changed = updated != existing
    insumo_data["regionalizacao"] = updated
    return insumo_data, changed


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SICRO Injector — injeta preços regionais SICRO nos insumos Concilium",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--ref",
        type=Path,
        default=None,
        help="Arquivo JSON de referência SICRO. Se omitido, usa o novo caminho "
             "padrão config/referencias/SICRO/BR-{UF}/insumos.json.",
    )
    parser.add_argument("--uf", required=True, help="UF da referência (ex: CE).")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Exibe as alterações sem gravar nenhum arquivo.",
    )
    parser.add_argument(
        "--insumo",
        help="Processa apenas este insumo_id (ex: MA-BRITA-1). "
             "Omitir processa todos os mapeados.",
    )
    parser.add_argument(
        "--mapping",
        type=Path,
        default=MAPPING_FILE,
        help=f"Arquivo de mapeamento YAML (padrão: {MAPPING_FILE})",
    )

    args = parser.parse_args()

    uf = args.uf.upper()
    jurisdicao_id = UF_TO_JURISDICAO.get(uf)
    if not jurisdicao_id:
        print(f"ERRO: UF desconhecida: {uf}", file=sys.stderr)
        sys.exit(1)

    # Resolve path do arquivo de referência
    if args.ref is not None:
        ref_path: Path = args.ref
        if not ref_path.is_absolute() and not ref_path.exists():
            ref_path = REFERENCIAS_DIR / ref_path
    else:
        # Novo caminho padrão: SICRO/BR-{UF}/insumos.json
        ref_path = REFERENCIAS_DIR / "SICRO" / f"BR-{uf}" / "insumos.json"

    if not ref_path.exists():
        print(f"ERRO: arquivo de referência não encontrado: {ref_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Carregando referência SICRO: {ref_path.name}")
    sicro_index = load_sicro_ref(ref_path)
    print(f"  {len(sicro_index)} insumos indexados.")

    print(f"Carregando mapeamento: {args.mapping.name}")
    mappings = load_mapping(args.mapping)
    print(f"  {len(mappings)} entradas no mapeamento.")

    if args.insumo:
        mappings = [m for m in mappings if m.get("concilium_id") == args.insumo]
        if not mappings:
            print(f"ERRO: insumo '{args.insumo}' não encontrado no mapeamento.", file=sys.stderr)
            sys.exit(1)

    stats = {"ok": 0, "skip_no_code": 0, "skip_not_in_sicro": 0, "skip_no_price": 0, "file_not_found": 0}
    print(f"\n{'DRY-RUN — ' if args.dry_run else ''}Processando {len(mappings)} insumos para {jurisdicao_id}...\n")

    for mapping in mappings:
        concilium_id: str = mapping.get("concilium_id", "")
        sicro_codigo: str | None = mapping.get("sicro_codigo")

        if not sicro_codigo:
            print(f"  [SKIP-NO-CODE]  {concilium_id}")
            stats["skip_no_code"] += 1
            continue

        sicro_item = sicro_index.get(sicro_codigo)
        if not sicro_item:
            print(f"  [SKIP-NOT-SICRO] {concilium_id} → {sicro_codigo} (não encontrado na referência)")
            stats["skip_not_in_sicro"] += 1
            continue

        preco = sicro_item.get("preco_publicado")
        if preco is None:
            print(f"  [SKIP-NO-PRICE]  {concilium_id} → {sicro_codigo} (preço nulo)")
            stats["skip_no_price"] += 1
            continue

        insumo_file = find_insumo_file(concilium_id)
        if not insumo_file:
            print(f"  [FILE-NOT-FOUND] {concilium_id}")
            stats["file_not_found"] += 1
            continue

        with open(insumo_file, encoding="utf-8") as f:
            insumo_data = json.load(f)

        data_ref = sicro_item["data_vigencia"]
        entry = {
            "jurisdicao_id": jurisdicao_id,
            "preco_unitario": preco,
            "fonte_preco": "SICRO_DNIT",
            "data_referencia": data_ref,
            "sicro_codigo": sicro_codigo,
            "sicro_descricao": sicro_item["descricao"],
            "url_fonte": sicro_item["url_fonte"],
        }

        insumo_data, changed = upsert_regionalizacao(insumo_data, entry)
        status = "UPDATED" if changed else "UNCHANGED"
        print(f"  [{status}] {concilium_id} → {sicro_codigo}  R$ {preco:.2f}/{sicro_item['unidade']}")

        if changed and not args.dry_run:
            with open(insumo_file, "w", encoding="utf-8") as f:
                json.dump(insumo_data, f, indent=2, ensure_ascii=False)
                f.write("\n")

        if changed:
            stats["ok"] += 1

    print(f"\n{'='*50}")
    print(f"Resumo:")
    print(f"  Injetados/atualizados : {stats['ok']}")
    print(f"  Sem código SICRO      : {stats['skip_no_code']}")
    print(f"  Não na referência     : {stats['skip_not_in_sicro']}")
    print(f"  Sem preço             : {stats['skip_no_price']}")
    print(f"  Arquivo não encontrado: {stats['file_not_found']}")

    if args.dry_run:
        print("\n⚠  DRY-RUN — nenhum arquivo foi gravado.")
    else:
        print(f"\n✓ Concluído.")


if __name__ == "__main__":
    main()
