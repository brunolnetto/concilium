"""
sicro_fetch_all.py
==================
Faz o download e parse do SICRO para todas as UFs brasileiras.
Gera apenas os JSONs de referência — NÃO modifica o catálogo.

Uso:
    python scripts/sicro_pipeline_all.py --ano 2026 --mes 1
    python scripts/sicro_pipeline_all.py --ano 2026 --mes 1 --uf CE SP MG
    python scripts/sicro_pipeline_all.py --ano 2026 --mes 1 --force-fetch   # re-baixa mesmo se JSON existe

Saída:
    config/referencias/SICRO_{ANO}_{MES:02d}_{UF}.json  — um arquivo por UF
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from sicro_fetch import build_download_url, download_file, extract_7z, parse_sicro_xlsx_set, ESTADOS, REFERENCIAS_DIR, get_ref_dir

# Todas as UFs suportadas (ordenadas alfabeticamente)
ALL_UFS = sorted(ESTADOS.keys())

ANOS_MESES_SLUG = {
    1: "janeiro", 2: "fevereiro", 3: "marco", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}


# ---------------------------------------------------------------------------
# Fetch de uma UF
# ---------------------------------------------------------------------------

def fetch_uf(uf: str, ano: int, mes: int, refs_dir: Path, force: bool = False) -> Path | None:
    """
    Baixa e parseia o SICRO de uma UF.
    Salva em refs_dir/SICRO/BR-{UF}/{insumos,cpus,producoes}.json
    Retorna o path de insumos.json, ou None em caso de falha.
    """
    import shutil as _sh, tempfile

    ref_dir = get_ref_dir(uf)
    out_file = ref_dir / "insumos.json"

    if out_file.exists() and not force:
        print(f"  [{uf}] insumos.json já existe, pulando download.")
        return out_file

    url = build_download_url(uf, ano, mes)
    print(f"  [{uf}] Baixando: {url}")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            archive = tmp_path / f"{uf.lower()}-{mes:02d}-{ano}.7z"

            download_file(url, archive)

            print(f"  [{uf}] Extraindo .7z...")
            xlsx_files = extract_7z(archive, tmp_path / "extracted")
            if not xlsx_files:
                print(f"  [{uf}] ERRO: nenhum xlsx encontrado no .7z")
                return None

            sinteticos = [
                f for f in xlsx_files
                if "SINT" in f.name.upper() and "DESONER" not in f.name.upper()
                and any(
                    kw in f.name.upper()
                    for kw in ("MATERIAI", "MATERIAL", "EQUIPAMENTO", "MÃO", "MAO")
                )
            ]
            if not sinteticos:
                sinteticos = xlsx_files

            # Copia xlsx para o diretório da UF
            ref_dir.mkdir(parents=True, exist_ok=True)
            xlsx_locals: list[Path] = []
            for src in sinteticos:
                dst = ref_dir / src.name
                _sh.copy(src, dst)
                xlsx_locals.append(dst)

        # Parse fora do tempdir
        data_ref = f"{ano}-{mes:02d}"
        data = parse_sicro_xlsx_set(xlsx_locals, uf, data_ref)

        for key in ("insumos", "cpus", "producoes"):
            dest = ref_dir / f"{key}.json"
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(data[key], f, indent=2, ensure_ascii=False)
                f.write("\n")

        n = len(data["insumos"]["insumos"])
        print(f"  [{uf}] ✓ {n} insumos → {ref_dir.relative_to(refs_dir)}/")
        return out_file

    except Exception as exc:
        import traceback; traceback.print_exc()
        print(f"  [{uf}] ERRO no fetch: {exc}")
        return None


# ---------------------------------------------------------------------------
# Relatório final
# ---------------------------------------------------------------------------

def print_report(results: list[dict], ano: int, mes: int) -> None:
    print()
    print("=" * 60)
    print(f"  RELATÓRIO FINAL — SICRO {ano}/{mes:02d}")
    print("=" * 60)
    ok_ufs = [r for r in results if "error" not in r]
    fail_ufs = [r for r in results if "error" in r]
    for r in results:
        if "error" in r:
            print(f"  {r['uf']:<6} ERRO: {r['error']}")
        else:
            print(f"  {r['uf']:<6} ✓ {r['insumos']:>5} insumos → {r['arquivo']}")
    print()
    print(f"  UFs com sucesso : {len(ok_ufs)}")
    print(f"  UFs com falha   : {len(fail_ufs)}")
    if fail_ufs:
        print(f"  Falhas: {[r['uf'] for r in fail_ufs]}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download SICRO para todas as UFs — gera apenas JSONs de referência",
    )
    parser.add_argument("--ano", type=int, default=2026)
    parser.add_argument("--mes", type=int, default=1)
    parser.add_argument(
        "--uf", nargs="+", metavar="UF",
        help="Processa apenas estas UFs (ex: --uf CE SP MG). Padrão: todas.",
    )
    parser.add_argument(
        "--force-fetch", action="store_true",
        help="Força re-download mesmo se o JSON já existir.",
    )
    args = parser.parse_args()

    ufs = [u.upper() for u in args.uf] if args.uf else ALL_UFS
    invalid = [u for u in ufs if u not in ESTADOS]
    if invalid:
        print(f"ERRO: UFs inválidas: {invalid}. Válidas: {sorted(ESTADOS)}", file=sys.stderr)
        sys.exit(1)

    print(f"Download SICRO {args.ano}/{args.mes:02d}")
    print(f"UFs: {ufs}")
    print(f"force-fetch={args.force_fetch}")
    print()

    results: list[dict] = []

    for i, uf in enumerate(ufs, 1):
        print(f"[{i}/{len(ufs)}] === {uf} ===")
        ref_file = fetch_uf(uf, args.ano, args.mes, REFERENCIAS_DIR, force=args.force_fetch)
        if ref_file is None:
            results.append({"uf": uf, "error": "fetch falhou"})
        else:
            n = len(json.loads(ref_file.read_text(encoding="utf-8"))["insumos"])
            results.append({"uf": uf, "insumos": n, "arquivo": str(ref_file.parent.relative_to(REFERENCIAS_DIR))})
        # Respeita o servidor
        if i < len(ufs):
            time.sleep(1.5)

    print_report(results, args.ano, args.mes)


if __name__ == "__main__":
    main()
