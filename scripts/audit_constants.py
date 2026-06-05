"""Auditoria e clusterização de constantes Python no codebase (src/).

Usa AST para encontrar apenas DEFINIÇÕES reais de constantes (assignments de módulo
ou classe com nome ALL_CAPS), evitando falsos positivos de palavras em comentários,
strings, docstrings ou arquivos .md/.toml.

Clusters de saída
-----------------
  SISTÊMICO          Candidatas a .env.example: URLs, paths, timeouts, chaves de
                     infraestrutura que mudam por ambiente.
  BACKEND_CENTRAL    Já centralizadas em domain/constants.py (encargos, BDI, calendário).
  MOVER_PARA_CENTRAL Constantes de regra de negócio/física fora do hub; devem migrar.
  DOMÍNIO_ENUM       Membros de classes-enum do domínio (ValidationCode, ArtifactKind…).
                     Corretamente localizadas — não mover.
  INFRA_LOCAL        Constantes de classe em adaptadores/stores (nomes de arquivo,
                     índices de coluna Excel). Corretamente localizadas — não mover.
  UI_FRONTEND        Exclusivas de presentation/ui/ (cores, ícones, contratos de form).
  APLICAÇÃO_LOCAL    Registros/listas de configuração da camada application que não
                     são regra de negócio numérica (pipelines, fases, vocabs).
  MCP_PROMPTS        Strings de prompt/erro do servidor MCP — podem ser i18n no futuro.
  OUTROS             Classificação não resolvida — revisar manualmente.

Saída:
  constants_clusters.txt : relatório principal clusterizado
  constants_report.txt   : relatório completo por arquivo (com cluster marcado)
  constants_summary.txt  : estatísticas e distribuição por cluster

Uso:
    python scripts/audit_constants.py [--src src/] [--out-dir .]
"""

from __future__ import annotations

import ast
import argparse
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import NamedTuple

# ── Padrão de nome ALL_CAPS válido ────────────────────────────────────────────

_CONST_RE = re.compile(r"^[A-Z][A-Z0-9]{1,}(?:_[A-Z0-9]+)*$")

_SKIP_NAMES = frozenset({
    "TRUE", "FALSE", "NONE", "NOT", "AND", "OR", "IN", "IS", "IF", "ELSE",
    "FOR", "WHILE", "WITH", "AS", "FROM", "IMPORT", "RETURN", "YIELD", "RAISE",
    "TRY", "EXCEPT", "FINALLY", "PASS", "BREAK", "CONTINUE", "DEL", "GLOBAL",
    "LAMBDA", "CLASS", "DEF",
    "OK", "GET", "PUT", "POST", "DELETE", "HEAD", "PATCH",
    "TYPE", "IO", "OS", "RE", "ID", "DB",
})


def is_constant_name(name: str) -> bool:
    if name.startswith("_"):
        return False
    if name in _SKIP_NAMES:
        return False
    return bool(_CONST_RE.match(name))


# ── Clusters ──────────────────────────────────────────────────────────────────

CLUSTERS = [
    "SISTÊMICO",
    "BACKEND_CENTRAL",
    "MOVER_PARA_CENTRAL",
    "DOMÍNIO_ENUM",
    "INFRA_LOCAL",
    "UI_FRONTEND",
    "APLICAÇÃO_LOCAL",
    "MCP_PROMPTS",
    "OUTROS",
]

CLUSTER_DESCRIPTIONS = {
    "SISTÊMICO":          "Candidatas a .env.example (URLs, paths, timeouts, chaves de infra)",
    "BACKEND_CENTRAL":    "Já em domain/constants.py — hub oficial de constantes de domínio",
    "MOVER_PARA_CENTRAL": "Regras de negócio/física fora do hub — devem migrar para domain/constants.py",
    "DOMÍNIO_ENUM":       "Membros de enum do domínio — corretamente localizadas, não mover",
    "INFRA_LOCAL":        "Constantes de classe em adaptadores/stores — corretamente localizadas",
    "UI_FRONTEND":        "Exclusivas de presentation/ui/ — cores, ícones, contratos de formulário",
    "APLICAÇÃO_LOCAL":    "Registros/listas de configuração da camada application — escopo correto",
    "MCP_PROMPTS":        "Strings de prompt/erro do servidor MCP — candidatas a i18n futuro",
    "OUTROS":             "Não classificadas — revisar manualmente",
}

# ── Regras de classificação (aplicadas em ordem — primeira match vence) ───────

# Nomes de classes-enum cujos membros devem permanecer no domínio
_ENUM_CLASS_NAMES = frozenset({
    "ValidationCode", "ArtifactKind", "ArtifactState", "CatalogPermission",
    "TaxRegimeVersion", "FuelType", "State", "CatalogBackend", "AliquotasBdi",
    "SemanticParseError",
})

# Classes de infra cujas constantes são detalhes de implementação
_INFRA_CLASS_NAMES = frozenset({
    "PlanoStore", "ProjectStore", "EscopoStore", "FileSystemArtifactStore",
    "_Lconst", "OpenMeteoClient", "FuelPriceClient", "WorkforcePolicySimulator",
    "DiagnosticoPEBuilder", "CalibrationAnalyzer", "ResolutionContext",
    "ValidadorCPUInsumo",
})

# Constantes cujo valor é regra de negócio/física e devem ir para domain/constants.py
_MOVE_TO_CENTRAL_EXACT = frozenset({
    "HORAS_MES",
    "DEFAULT_PRECO_DIESEL",
    "MARGEM_MINIMA",
})
_MOVE_TO_CENTRAL_PREFIXES = (
    "DIESEL_L_POR_CV", "DIESEL_TOLERANCIA",
    "ZSCORE_",
)

# Padrões de nome que indicam constante sistêmica (env/config)
_SYSTEMIC_NAME_FRAGMENTS = (
    "CONCILIUM_", "_ROOT", "BASE_URL", "REQUEST_TIMEOUT",
    "RESPONSE_SCHEMA_VERSION",
)

# Caminhos de arquivo que hospedam constantes sistêmicas
_SYSTEMIC_FILE_FRAGMENTS = (
    "presentation/cli/shared.py",
    "mcp_server/server.py",
    "mcp_server/_context.py",
    "catalog/mapping/cpu_mapper.py",
)


def _fp(path: Path) -> str:
    """Normaliza separadores para comparação uniforme."""
    return path.as_posix()


def classify(
    name: str,
    pyfile: Path,
    scope: str,
    value_type: str,
    by_name: dict,
) -> str:
    fp = _fp(pyfile)

    # 1. Hub central — domain/constants.py
    if "domain/constants.py" in fp:
        return "BACKEND_CENTRAL"

    # 2. MCP prompts
    if "mcp_server/tools/prompts" in fp:
        return "MCP_PROMPTS"

    # 3. Frontend puro
    if "presentation/ui/" in fp:
        return "UI_FRONTEND"

    # 4. Sistêmico — env-var backed ou config de infraestrutura
    if any(frag in name for frag in _SYSTEMIC_NAME_FRAGMENTS):
        return "SISTÊMICO"
    if any(frag in fp for frag in _SYSTEMIC_FILE_FRAGMENTS):
        # dentro desses arquivos apenas constantes de config são sistêmicas
        if any(kw in name for kw in ("URL", "TIMEOUT", "TTL", "ROOT", "CONFIG", "FILE", "PATH", "SCHEMA")):
            return "SISTÊMICO"

    # 5. Enum de domínio (membros de classe)
    if scope.startswith("class:"):
        cls = scope[len("class:"):]
        if cls in _ENUM_CLASS_NAMES:
            return "DOMÍNIO_ENUM"

    # 6. Constantes de classe de infra/adaptadores (detalhes de implementação)
    if scope.startswith("class:"):
        cls = scope[len("class:"):]
        if cls in _INFRA_CLASS_NAMES:
            return "INFRA_LOCAL"

    # 7. Constantes que devem migrar para domain/constants.py
    if name in _MOVE_TO_CENTRAL_EXACT:
        return "MOVER_PARA_CENTRAL"
    if any(name.startswith(p) for p in _MOVE_TO_CENTRAL_PREFIXES):
        return "MOVER_PARA_CENTRAL"
    # Duplicatas definidas em vários arquivos → candidatas a centralizar
    if len(by_name.get(name, [])) > 1:
        return "MOVER_PARA_CENTRAL"

    # 8. Application layer — registros e listas de configuração
    if "application/" in fp:
        return "APLICAÇÃO_LOCAL"

    # 9. Infra local — adaptadores, storage, catálogo
    if "infrastructure/" in fp:
        return "INFRA_LOCAL"

    # 10. Domain — constantes que ficam no domínio mas fora do hub central
    if "domain/" in fp:
        return "DOMÍNIO_ENUM"  # conservador: tratar como enum local do domínio

    return "OUTROS"


# ── Extração AST ──────────────────────────────────────────────────────────────

class ConstDef(NamedTuple):
    name: str
    pyfile: Path
    line: int
    scope: str
    value_type: str


def extract_constants(filepath: Path) -> list[ConstDef]:
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []

    results: list[ConstDef] = []

    def visit_body(body: list, scope: str) -> None:
        for node in body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and is_constant_name(target.id):
                        results.append(ConstDef(target.id, filepath, node.lineno, scope, type(node.value).__name__))
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and is_constant_name(node.target.id):
                    results.append(ConstDef(node.target.id, filepath, node.lineno, scope, type(node.annotation).__name__))
            elif isinstance(node, ast.ClassDef):
                visit_body(node.body, scope=f"class:{node.name}")

    visit_body(tree.body, scope="module")
    return results


# ── Relatórios ────────────────────────────────────────────────────────────────

def run(src_root: Path, out_dir: Path) -> None:
    by_name: dict[str, list[ConstDef]] = defaultdict(list)
    by_file: dict[Path, list[ConstDef]] = defaultdict(list)

    py_files = sorted(src_root.rglob("*.py"))
    for pyfile in py_files:
        for c in extract_constants(pyfile):
            by_name[c.name].append(c)
            by_file[pyfile].append(c)

    # Classificar
    all_defs: list[tuple[ConstDef, str]] = []
    for defs in by_name.values():
        for c in defs:
            cluster = classify(c.name, c.pyfile, c.scope, c.value_type, by_name)
            all_defs.append((c, cluster))

    by_cluster: dict[str, list[ConstDef]] = defaultdict(list)
    for c, cluster in all_defs:
        by_cluster[cluster].append(c)

    # Mapa nome → cluster para o relatório por arquivo
    name_to_cluster: dict[str, str] = {}
    for c, cluster in all_defs:
        name_to_cluster[c.name] = cluster  # última wins (mesma para todas as cópias)

    out_dir.mkdir(parents=True, exist_ok=True)
    rel = lambda p: p.relative_to(src_root.parent)

    # ── constants_clusters.txt ────────────────────────────────────────────────
    clusters_path = out_dir / "constants_clusters.txt"
    with clusters_path.open("w", encoding="utf-8") as f:
        f.write("# Constantes Python — clusterizadas por responsabilidade\n")
        f.write(f"# Fonte: {src_root}\n\n")

        for cluster in CLUSTERS:
            defs = sorted(by_cluster.get(cluster, []), key=lambda c: (str(c.pyfile), c.line))
            if not defs:
                continue
            f.write(f"{'='*72}\n")
            f.write(f"CLUSTER: {cluster}  ({len(defs)} entradas)\n")
            f.write(f"  {CLUSTER_DESCRIPTIONS[cluster]}\n")
            f.write(f"{'='*72}\n\n")

            # Agrupar por arquivo dentro do cluster
            cluster_by_file: dict[Path, list[ConstDef]] = defaultdict(list)
            for c in defs:
                cluster_by_file[c.pyfile].append(c)

            for pyfile in sorted(cluster_by_file.keys()):
                f.write(f"  {rel(pyfile)}\n")
                for c in sorted(cluster_by_file[pyfile], key=lambda x: x.line):
                    copies = len(by_name[c.name])
                    dup_tag = f"  *** {copies}× definida ***" if copies > 1 else ""
                    f.write(f"    L{c.line:4d}  {c.name:<40} ({c.scope}){dup_tag}\n")
                f.write("\n")

    # ── constants_report.txt (por arquivo, com cluster) ───────────────────────
    report_path = out_dir / "constants_report.txt"
    with report_path.open("w", encoding="utf-8") as f:
        f.write("# Constantes Python — relatório por arquivo\n")
        f.write(f"# Fonte: {src_root}\n\n")
        for pyfile in sorted(by_file.keys()):
            consts = sorted(by_file[pyfile], key=lambda c: c.line)
            f.write(f"{rel(pyfile)}\n")
            for c in consts:
                cluster = name_to_cluster.get(c.name, "?")
                copies = len(by_name[c.name])
                dup_tag = f"  [×{copies}]" if copies > 1 else ""
                f.write(f"  L{c.line:4d}  {c.name:<43} [{cluster}]{dup_tag}\n")
            f.write("\n")

    # ── constants_summary.txt ─────────────────────────────────────────────────
    total_unique = len(by_name)
    total_defs = sum(len(v) for v in by_name.values())
    files_with_consts = len(by_file)

    summary_path = out_dir / "constants_summary.txt"
    with summary_path.open("w", encoding="utf-8") as f:
        f.write("# Sumário da auditoria de constantes\n\n")
        f.write(f"Arquivos .py escaneados         : {len(py_files)}\n")
        f.write(f"Arquivos com constantes         : {files_with_consts}\n")
        f.write(f"Constantes únicas               : {total_unique}\n")
        f.write(f"Total de definições             : {total_defs}\n\n")

        f.write("Distribuição por cluster:\n")
        for cluster in CLUSTERS:
            n = len(by_cluster.get(cluster, []))
            if n:
                f.write(f"  {n:3d}  {cluster:<22}  {CLUSTER_DESCRIPTIONS[cluster]}\n")

        f.write("\nTop 20 arquivos por nº de constantes:\n")
        for pyfile, consts in sorted(by_file.items(), key=lambda x: len(x[1]), reverse=True)[:20]:
            f.write(f"  {len(consts):3d}  {rel(pyfile)}\n")

        f.write("\nConstantes por módulo de topo (src/concilium/<módulo>):\n")
        module_counts: Counter = Counter()
        for pyfile in by_file:
            parts = pyfile.relative_to(src_root).parts
            top = parts[1] if len(parts) > 1 else parts[0]
            module_counts[top] += len(by_file[pyfile])
        for mod, count in module_counts.most_common():
            f.write(f"  {count:4d}  {mod}\n")

    # ── Console ───────────────────────────────────────────────────────────────
    print(f"Arquivos .py escaneados  : {len(py_files)}")
    print(f"Arquivos com constantes  : {files_with_consts}")
    print(f"Constantes únicas        : {total_unique}")
    print(f"Total de definições      : {total_defs}")
    print()
    print("Distribuição por cluster:")
    for cluster in CLUSTERS:
        n = len(by_cluster.get(cluster, []))
        if n:
            print(f"  {n:3d}  {cluster}")
    print()
    print(f"Clusters    → {clusters_path}")
    print(f"Por arquivo → {report_path}")
    print(f"Sumário     → {summary_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Auditoria e clusterização de constantes Python via AST.")
    parser.add_argument("--src", default="src/", help="Diretório raiz do código-fonte")
    parser.add_argument("--out-dir", default=".", help="Diretório de saída dos relatórios")
    args = parser.parse_args()

    src_root = Path(args.src).resolve()
    out_dir = Path(args.out_dir).resolve()

    if not src_root.exists():
        print(f"Erro: diretório '{src_root}' não encontrado.")
        raise SystemExit(1)

    run(src_root, out_dir)


if __name__ == "__main__":
    main()
