"""
Stage 1 — SICRO Fetcher
=======================
Baixa a planilha oficial SICRO do portal DNIT (dados abertos, CC BY-ND 3.0) e
extrai os insumos para um JSON de referência no formato Concilium.

Saída:
    config/referencias/SICRO_{ANO}_{MES:02d}_{UF}.json

Uso:
    # Baixar direto do DNIT (requer py7zr para extrair o .7z):
    python scripts/sicro_fetch.py --uf CE --ano 2026 --mes 1

    # Usar xlsx já baixado manualmente:
    python scripts/sicro_fetch.py --xlsx caminho/para/arquivo.xlsx --uf CE --ref 2026-01

Dependências extras (além do pyproject.toml):
    pip install requests py7zr
    (openpyxl já está em pyproject.toml)

Notas legais:
    - Dados SICRO são domínio público (DNIT/Gov.br).
    - Conteúdo do portal gov.br publicado sob CC BY-ND 3.0.
    - Fonte: https://www.gov.br/dnit/pt-br/.../relatorios-sicro
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Constantes de navegação do portal DNIT
# ---------------------------------------------------------------------------

BASE_DNIT = (
    "https://www.gov.br/dnit/pt-br/assuntos/planejamento-e-pesquisa/"
    "custos-referenciais/sistemas-de-custos/sicro/relatorios/relatorios-sicro"
)

ESTADOS: dict[str, tuple[str, str]] = {
    # UF: (regiao_slug, estado_slug)
    "AC": ("norte", "acre"),
    "AM": ("norte", "amazonas"),
    "AP": ("norte", "amapa"),
    "PA": ("norte", "para"),
    "RO": ("norte", "rondonia"),
    "RR": ("norte", "roraima"),
    "TO": ("norte", "tocantins"),
    "AL": ("nordeste", "alagoas"),
    "BA": ("nordeste", "bahia"),
    "CE": ("nordeste", "ceara"),
    "MA": ("nordeste", "maranhao"),
    "PB": ("nordeste", "paraiba"),
    "PE": ("nordeste", "pernambuco"),
    "PI": ("nordeste", "piaui"),
    "RN": ("nordeste", "rio-grande-do-norte"),
    "SE": ("nordeste", "sergipe"),
    "DF": ("centro-oeste", "distrito-federal"),
    "GO": ("centro-oeste", "goias"),
    "MS": ("centro-oeste", "mato-grosso-do-sul"),
    "MT": ("centro-oeste", "mato-grosso"),
    "ES": ("sudeste", "espirito-santo"),
    "MG": ("sudeste", "minas-gerais"),
    "RJ": ("sudeste", "rio-de-janeiro"),
    "SP": ("sudeste", "sao-paulo"),
    "PR": ("sul", "parana"),
    "RS": ("sul", "rio-grande-do-sul"),
    "SC": ("sul", "santa-catarina"),
}

MESES: dict[int, str] = {
    1: "janeiro", 2: "fevereiro", 3: "marco", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}

# Localiza o root do projeto (dois níveis acima deste script)
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
REFERENCIAS_DIR = PROJECT_ROOT / "config" / "referencias"


# ---------------------------------------------------------------------------
# Helpers de diretório
# ---------------------------------------------------------------------------

def get_ref_dir(uf: str, sigla: str = "SICRO") -> Path:
    """Retorna o diretório de referência para uma jurisdição.

    Estrutura: config/referencias/{sigla}/BR-{UF}/
    """
    return REFERENCIAS_DIR / sigla / f"BR-{uf.upper()}"


# ---------------------------------------------------------------------------
# Montagem de URL de download
# ---------------------------------------------------------------------------

def build_download_url(uf: str, ano: int, mes: int) -> str:
    """Monta a URL de download do arquivo .7z no portal DNIT."""
    uf = uf.upper()
    if uf not in ESTADOS:
        raise ValueError(f"UF desconhecida: {uf}. Válidas: {', '.join(sorted(ESTADOS))}")
    regiao, estado_slug = ESTADOS[uf]
    mes_slug = MESES[mes]
    filename = f"{uf.lower()}-{mes:02d}-{ano}.7z"
    url = (
        f"{BASE_DNIT}/{regiao}/{estado_slug}/{ano}/{mes_slug}/{filename}"
    )
    return url


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_file(url: str, dest: Path) -> Path:
    """Baixa uma URL para dest. Requer `requests`."""
    try:
        import requests
    except ImportError:
        print("ERRO: instale requests → pip install requests", file=sys.stderr)
        sys.exit(1)

    print(f"Baixando: {url}")
    headers = {"User-Agent": "concilium-sicro-importer/1.0 (uso interno)"}
    with requests.get(url, headers=headers, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    print(f"\r  {pct:.1f}%", end="", flush=True)
    print()
    return dest


# ---------------------------------------------------------------------------
# Extração do .7z
# ---------------------------------------------------------------------------

def extract_7z(archive: Path, dest_dir: Path) -> list[Path]:
    """Extrai um arquivo .7z. Requer `py7zr`."""
    try:
        import py7zr
    except ImportError:
        print(
            "ERRO: py7zr não encontrado.\n"
            "  Instale com: pip install py7zr\n"
            "  OU extraia manualmente e use --xlsx <caminho>",
            file=sys.stderr,
        )
        sys.exit(1)

    with py7zr.SevenZipFile(archive, mode="r") as z:
        z.extractall(path=dest_dir)
    return list(dest_dir.rglob("*.xlsx"))


# ---------------------------------------------------------------------------
# Parser do xlsx SICRO
# ---------------------------------------------------------------------------

def _to_float(val) -> float | None:
    """Converte um valor de célula xlsx para float, ou None se inválido."""
    if val is None or str(val).strip() in ("", "-", "N/A", "NONE", "NAN"):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace("R$", "").strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_sintetico(wb, tipo: str, tipo_nome: str) -> list[dict]:
    """
    Parseia um xlsx Relatório Sintético SICRO 4 (Materiais, Equipamentos ou Mão de Obra).

    Layout por tipo:
      Materiais / Mão de Obra:
        Código | Descrição | Unidade | Custo Unitário (R$)

      Equipamentos:
        Código | Descrição | Valor Aquisição (R$) | Depreciação (R$/h) |
        Oportunidade de Capital (R$/h) | Seguros e Impostos (R$/h) |
        Manutenção (R$/h) | Operação (R$/h)
        → custo horário total = Depreciação + Oportunidade + Seguros/Impostos
                                + Manutenção + Operação
        → unidade sempre "h"
    """
    ws = wb.active or wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))

    # Encontra a linha de cabeçalho
    header_idx = None
    for i, row in enumerate(rows[:20]):
        row_upper = " ".join(str(c).upper() for c in row if c)
        if any(kw in row_upper for kw in ("CÓDIGO", "CODIGO", "DESCRI", "UNIDADE", "DEPRECIA")):
            header_idx = i
            break

    if header_idx is None:
        for i, row in enumerate(rows):
            if row and row[0] and str(row[0]).strip():
                val = str(row[0]).strip()
                if len(val) > 3 and not val.upper().startswith(("RELA", "CERT", "DATA", "ESTA")):
                    header_idx = max(0, i - 1)
                    break

    if header_idx is None:
        print(f"    [AVISO] Não encontrou cabeçalho em '{tipo_nome}'")
        return []

    headers = [str(c).strip().upper().replace("\n", " ") if c else "" for c in rows[header_idx]]

    def find_col(*keywords: str) -> int:
        for kw in keywords:
            for j, h in enumerate(headers):
                if kw in h:
                    return j
        return -1

    col_cod  = find_col("CÓDIGO", "CODIGO", "COD")
    col_desc = find_col("DESCRIÇÃO", "DESCRICAO", "DESCRI", "NOME")

    # --- Equipamentos: layout multi-coluna de custo ---
    is_equip = tipo == "EQUIPAMENTO"
    if is_equip:
        col_deprec    = find_col("DEPRECIA")
        col_oportun   = find_col("OPORTUNIDADE")
        col_seguros   = find_col("SEGUROS")
        col_manut     = find_col("MANUT")
        # "OPERAÇÃO" sem "MÃO DE OBRA" — busca manual para evitar match na col de mão de obra
        col_operacao  = next(
            (j for j, h in enumerate(headers)
             if "OPERA" in h and "MÃO" not in h and "MAO" not in h),
            -1,
        )
        col_mao_obra  = find_col("MÃO DE OBRA DE OPERA", "MAO DE OBRA DE OPERA")
        col_produtivo = find_col("CUSTO PRODUTIVO")
        col_improdut  = find_col("CUSTO IMPRODUTIVO")
        # Colunas de custo horário para somar (sem mão de obra — incluída à parte)
        cols_custo_h = [c for c in [col_deprec, col_oportun, col_seguros, col_manut, col_operacao] if c != -1]
        col_aquisicao = find_col("AQUISIÇÃO", "AQUISICAO", "VALOR DE AQUISIÇÃO")
        col_unid = -1  # equipamentos não têm coluna de unidade no sintético
        print(f"    Cabeçalho (linha {header_idx+1}): {headers}")
        print(f"    Colunas equip → cod={col_cod} desc={col_desc} "
              f"deprec={col_deprec} oport={col_oportun} seg={col_seguros} "
              f"manut={col_manut} oper={col_operacao} mao_obra={col_mao_obra} "
              f"produtivo={col_produtivo} improd={col_improdut} aquis={col_aquisicao}")
    else:
        col_unid  = find_col("UNIDADE", "UNID")
        col_preco = find_col(
            "CUSTO UNIT", "PREÇO UNIT", "PRECO UNIT",
            "VALOR UNIT", "CUSTO (R$)", "PRECO (R$)",
            "TOTAL", "CUSTO"
        )
        # Fallbacks posicionais
        n_cols = len(headers)
        if col_cod   == -1: col_cod   = 0
        if col_desc  == -1: col_desc  = 1 if n_cols > 1 else 0
        if col_unid  == -1: col_unid  = 2 if n_cols > 2 else 0
        if col_preco == -1: col_preco = 3 if n_cols > 3 else (n_cols - 1)
        cols_custo_h = []
        print(f"    Cabeçalho (linha {header_idx+1}): {headers}")
        print(f"    Colunas → cod={col_cod} desc={col_desc} unid={col_unid} preco={col_preco}")

    # Fallback de código
    if col_cod == -1:
        col_cod = 0
    if col_desc == -1:
        col_desc = 1

    insumos: list[dict] = []
    for row in rows[header_idx + 1:]:
        if not row or not row[col_cod]:
            continue
        codigo = str(row[col_cod]).strip()
        if not codigo or codigo.upper() in ("CÓDIGO", "CODIGO", "COD", "NAN", "NONE"):
            continue
        if len(codigo) < 3:
            continue

        descricao = str(row[col_desc]).strip().replace("\xa0", " ") if row[col_desc] else ""

        if is_equip:
            # Custo horário total = soma dos componentes horários
            componentes = {}
            partes = {
                "depreciacao":          col_deprec,
                "oportunidade_capital": col_oportun,
                "seguros_impostos":     col_seguros,
                "manutencao":           col_manut,
                "operacao":             col_operacao,
            }
            total = 0.0
            for nome, col in partes.items():
                if col == -1 or col >= len(row):
                    continue
                v = _to_float(row[col])
                if v is not None:
                    componentes[nome] = round(v, 6)
                    total += v

            # Mão de obra de operação (separada — não faz parte do custo máquina)
            mao_obra_op = None
            if col_mao_obra != -1 and col_mao_obra < len(row):
                mao_obra_op = _to_float(row[col_mao_obra])

            # Custo produtivo e improdutivo (referência direta do DNIT)
            custo_produtivo = None
            if col_produtivo != -1 and col_produtivo < len(row):
                custo_produtivo = _to_float(row[col_produtivo])

            custo_improdutivo = None
            if col_improdut != -1 and col_improdut < len(row):
                custo_improdutivo = _to_float(row[col_improdut])

            aquisicao = None
            if col_aquisicao != -1 and col_aquisicao < len(row):
                aquisicao = _to_float(row[col_aquisicao])

            item: dict = {
                "codigo_referencia": codigo,
                "descricao": descricao,
                "tipo": tipo,
                "unidade": "h",
                "preco_publicado": round(total, 4) if componentes else None,
                "componentes_custo": componentes,
            }
            if mao_obra_op is not None:
                item["mao_obra_operacao"] = round(mao_obra_op, 4)
            if custo_produtivo is not None:
                item["custo_produtivo"] = round(custo_produtivo, 4)
            if custo_improdutivo is not None:
                item["custo_improdutivo"] = round(custo_improdutivo, 4)
            if aquisicao is not None:
                item["valor_aquisicao"] = round(aquisicao, 4)
        else:
            unidade = str(row[col_unid]).strip().replace("\xa0", " ") if col_unid != -1 and row[col_unid] else ""
            preco   = _to_float(row[col_preco]) if col_preco < len(row) else None
            item = {
                "codigo_referencia": codigo,
                "descricao": descricao,
                "tipo": tipo,
                "unidade": unidade,
                "preco_publicado": preco,
            }

        insumos.append(item)

    return insumos


def parse_sicro_xlsx_set(xlsx_paths: list[Path], uf: str, data_ref: str) -> dict:
    """
    Parseia o conjunto de xlsx SICRO 4:
      - Relatório Sintético de Materiais
      - Relatório Sintético de Equipamentos
      - Relatório Sintético de Mão de Obra
    e monta o JSON de referência unificado.
    """
    try:
        import openpyxl
    except ImportError:
        print("ERRO: instale openpyxl → pip install openpyxl", file=sys.stderr)
        sys.exit(1)

    # Classifica os xlsx por nome
    def classify(path: Path) -> str | None:
        n = path.name.upper()
        if ("MATERIAI" in n or "MATERIAL" in n) and "SINT" in n:
            return "MATERIAL"
        if "EQUIPAMENTO" in n and "SINT" in n and "DESONER" not in n:
            return "EQUIPAMENTO"
        if "MÃO DE OBRA" in n or "MAO DE OBRA" in n:
            if "SINT" in n and "DESONER" not in n:
                return "MAO_OBRA"
        if "MÃO" in n or "MAO" in n:
            if "SINT" in n and "DESONER" not in n:
                return "MAO_OBRA"
        return None

    arquivos: dict[str, Path] = {}
    for p in xlsx_paths:
        tipo = classify(p)
        if tipo and tipo not in arquivos:
            arquivos[tipo] = p

    print(f"\n  Arquivos classificados:")
    for t, p in arquivos.items():
        print(f"    {t}: {p.name}")

    insumos_todos: list[dict] = []
    for tipo, path in arquivos.items():
        print(f"\n  Processando [{tipo}]: {path.name}")
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        items = _parse_sintetico(wb, tipo, path.name)
        wb.close()
        print(f"    → {len(items)} itens")
        insumos_todos.extend(items)

    if not insumos_todos:
        print("\n⚠ Nenhum insumo extraído. Veja aviso acima.", file=sys.stderr)

    data_vigencia = f"{data_ref}-01" if len(data_ref) == 7 else data_ref
    url_fonte = build_download_url(uf, int(data_ref[:4]), int(data_ref[5:7])) if len(data_ref) >= 7 else ""
    meta = {
        "$schema": "https://concilium.framework/schemas/v1/tabela_referencia",
        "provedor": "SICRO",
        "versao": data_ref,
        "jurisdicao": f"BR-{uf.upper()}",
        "data_vigencia": data_vigencia,
        "url_fonte": url_fonte,
        "imutavel": True,
    }
    return {
        "insumos": {**meta, "insumos": insumos_todos},
        "cpus":    {**meta, "cpus": []},
        "producoes": {**meta, "producoes": []},
    }


# Mantém alias para compatibilidade com código legado
def parse_sicro_xlsx(xlsx_path: Path, uf: str, data_ref: str) -> dict:
    return parse_sicro_xlsx_set([xlsx_path], uf, data_ref)


def get_insumos_path(uf: str) -> Path:
    """Atalho: retorna o path de insumos.json de uma UF."""
    return get_ref_dir(uf) / "insumos.json"


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SICRO Fetcher — baixa e parseia planilhas DNIT para JSON Concilium",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--uf", help="Sigla da UF (ex: CE, SP). Baixa automaticamente do DNIT.")
    group.add_argument("--xlsx", type=Path, help="Caminho para xlsx já baixado localmente.")

    parser.add_argument("--ano", type=int, default=2026, help="Ano de referência (padrão: 2026).")
    parser.add_argument("--mes", type=int, default=1, help="Mês de referência 1-12 (padrão: 1).")
    parser.add_argument(
        "--ref",
        help="Data de referência no formato YYYY-MM (usado com --xlsx). Ex: 2026-01",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REFERENCIAS_DIR,
        help=f"Diretório de saída (padrão: {REFERENCIAS_DIR})",
    )

    args = parser.parse_args()

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.xlsx:
        # Modo local
        uf = args.uf or input("Informe a UF deste arquivo: ").strip().upper()
        data_ref = args.ref or f"{args.ano}-{args.mes:02d}"
        xlsx_path: Path = args.xlsx
        if not xlsx_path.exists():
            print(f"ERRO: arquivo não encontrado: {xlsx_path}", file=sys.stderr)
            sys.exit(1)
    else:
        # Modo download automático
        uf = args.uf.upper()
        ano = args.ano
        mes = args.mes
        data_ref = f"{ano}-{mes:02d}"

        url = build_download_url(uf, ano, mes)
        print(f"URL: {url}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            archive = tmp_path / f"{uf.lower()}-{mes:02d}-{ano}.7z"
            download_file(url, archive)

            print("Extraindo arquivo .7z...")
            xlsx_files = extract_7z(archive, tmp_path / "extracted")
            if not xlsx_files:
                print("ERRO: nenhum .xlsx encontrado no arquivo.", file=sys.stderr)
                sys.exit(1)
            print(f"  Arquivos xlsx: {[f.name for f in xlsx_files]}")

            # Copia TODOS os xlsx relevantes para fora do tempdir antes que seja deletado
            sinteticos = [
                f for f in xlsx_files
                if "SINT" in f.name.upper() and "DESONER" not in f.name.upper()
                and any(kw in f.name.upper() for kw in ("MATERIAI", "MATERIAL", "EQUIPAMENTO", "MÃO DE OBRA", "MAO DE OBRA", "MÃO", "MAO"))
            ]
            if not sinteticos:
                # Fallback: copia todos
                sinteticos = xlsx_files

            xlsx_paths_local: list[Path] = []
            for src in sinteticos:
                dst = out_dir / src.name
                shutil.copy(src, dst)
                xlsx_paths_local.append(dst)
                print(f"  Salvo: {dst.name}")

    # Parse
    if args.xlsx:
        # Modo local: arquivo único
        xlsx_paths_local = [xlsx_path]  # type: ignore[assignment]

    print(f"\nParsing {len(xlsx_paths_local)} arquivo(s)...")
    data = parse_sicro_xlsx_set(xlsx_paths_local, uf, data_ref)

    # Salva na nova estrutura: {out_dir}/SICRO/BR-{UF}/{insumos,cpus,producoes}.json
    ref_dir = get_ref_dir(uf)
    ref_dir.mkdir(parents=True, exist_ok=True)

    # Move xlsx para dentro do diretório da UF
    if args.uf:  # modo download — xlsx foram salvos em out_dir
        for xlsx in out_dir.glob(f"{uf} *.xlsx"):
            xlsx.rename(ref_dir / xlsx.name)

    for key in ("insumos", "cpus", "producoes"):
        dest = ref_dir / f"{key}.json"
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(data[key], f, indent=2, ensure_ascii=False)
            f.write("\n")

    n_insumos = len(data["insumos"]["insumos"])
    n_cpus = len(data["cpus"]["cpus"])
    print(f"\n✓ Gerado: {ref_dir}/")
    print(f"  {n_insumos} insumos | {n_cpus} cpus")

    if n_insumos == 0:
        print(
            "\n⚠  Nenhum insumo extraído. Possíveis causas:\n"
            "  - Layout do xlsx diferente do esperado\n"
            "  - Arquivo corrompido ou protegido\n"
            "  - Aba com nome diferente\n"
            "  Abra o xlsx manualmente, identifique a aba de insumos e\n"
            "  ajuste a função parse_sicro_xlsx() em scripts/sicro_fetch.py",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
