"""Extrai referÃªncias de iteraÃ§Ã£o do engine por projeto, gravando em extracted_references/."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_DEFAULT_ROOT = Path(__file__).resolve().parents[5]
_BENCH_REPORT_GLOB = "benchmark_*.json"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _safe_float(v: Any) -> float:
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def _normalize_project_token(value: str) -> str:
    raw = str(value or "").upper()
    raw = raw.replace("_", " ")
    raw = re.sub(r"\bCALIBRADO\b", "", raw)
    raw = re.sub(r"[^A-Z0-9]+", " ", raw)
    return " ".join(raw.split())


def _find_latest_project_by_name(project_name: str, projects_root: Path) -> Path:
    target_norm = _normalize_project_token(project_name)
    best: tuple[str, Path] | None = None
    for d in projects_root.iterdir():
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = _load_json(meta_path)
        except Exception:
            continue
        nome_norm = _normalize_project_token(meta.get("nome") or "")
        if nome_norm != target_norm:
            continue
        created = str(meta.get("criado_em") or "")
        if best is None or created > best[0]:
            best = (created, d)
    if best is None:
        raise FileNotFoundError(f"Projeto nao encontrado para nome={project_name}")
    return best[1]


def iter_benchmark_reports(root: Path | None = None) -> list[Path]:
    """Retorna todos os arquivos benchmark_*.json da raiz."""
    r = root or _DEFAULT_ROOT
    return [p for p in r.glob(_BENCH_REPORT_GLOB) if p.name != "benchmark_template.json"]


def extract_engine_iteration_references(
    report_path: Path,
    root: Path | None = None,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """Extrai referÃªncias de iteraÃ§Ã£o do engine para um benchmark report.

    Args:
        report_path: caminho para o benchmark_*.json
        root: raiz do repositÃ³rio
        out_dir: diretÃ³rio de saÃ­da (padrÃ£o: benchmarks/extracted_references/)

    Returns:
        DicionÃ¡rio com referÃªncias extraÃ­das (tambÃ©m gravado em out_dir).
    """
    r = root or _DEFAULT_ROOT
    projects_root = r / "projetos"
    out = out_dir or (r / "benchmarks" / "extracted_references")
    out.mkdir(parents=True, exist_ok=True)

    bench = _load_json(report_path)
    slug = bench.get("slug") or report_path.stem.replace("benchmark_", "").upper()
    projeto_nome = bench.get("projeto") or slug

    project_dir = _find_latest_project_by_name(projeto_nome, projects_root)
    canonical_path = project_dir / "v1" / "canonical.json"
    canonical = _load_json(canonical_path) if canonical_path.exists() else {}

    # Extrai estrutura por etapa do canonical
    result: dict[str, Any] = {
        "slug": slug,
        "projeto": projeto_nome,
        "equipes": {
            "equipes": canonical.get("equipes_diretas", []),
        },
        "planejamento": {
            "itens_com_precos": canonical.get("planejamento", []),
        },
        "indiretos": {cat: {} for cat in ("ADM", "TOP", "LAB", "QSMS", "MOB")},
        "resultado": canonical.get("resultado", {}),
    }

    # Indiretos por categoria
    for ind in canonical.get("indiretos") or []:
        cat = ind.get("categoria")
        if cat:
            result["indiretos"][cat] = ind

    out_file = out / f"iteracao_referencias_{slug.lower()}.json"
    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
