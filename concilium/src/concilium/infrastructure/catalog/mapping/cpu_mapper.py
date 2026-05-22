"""Mapeamento automÃ¡tico de descriÃ§Ãµes de EAP para cpu_ids via keywords."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_RULES_ENV = "CONCILIUM_BENCHMARK_CPU_MAPPING_RULES_FILE"
_LEGACY_RULES_ENV = "CONCILIUM_CPU_MAPPING_RULES_FILE"


def _tools_root() -> Path:
    # src/concilium/infrastructure/catalog/mapping -> src -> RAIZ
    return Path(__file__).resolve().parents[5]


def _rules_file() -> Path:
    env_path = os.environ.get(_RULES_ENV)
    if env_path:
        return Path(env_path)
    legacy_path = os.environ.get(_LEGACY_RULES_ENV)
    if legacy_path:
        return Path(legacy_path)
    return _tools_root() / "config" / "referencias" / "cpu_mapping_rules.json"


def _clean_keyword_list(keywords: list) -> list[str]:
    result = []
    for kw in keywords:
        s = str(kw).strip()
        if s:
            result.append(s.upper())
    return result


def _load_mapping_keywords() -> dict[str, list[str]]:
    path = _rules_file()
    if not path.exists():
        return {}

    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    rules = payload.get("mapping_keywords", payload) if isinstance(payload, dict) else {}
    if not isinstance(rules, dict):
        return {}

    normalized: dict[str, list[str]] = {}
    for cpu_id, keywords in rules.items():
        if not isinstance(cpu_id, str) or not isinstance(keywords, list):
            continue
        clean_keywords = _clean_keyword_list(keywords)
        if clean_keywords:
            normalized[cpu_id] = clean_keywords
    return normalized


def map_desc(descricao: str) -> str | None:
    """Mapeia uma descriÃ§Ã£o de EAP para um cpu_id via keywords.

    Tenta match completo primeiro, depois parcial com filtro anti-falso-positivo.
    """
    mapping_keywords = _load_mapping_keywords()
    if not mapping_keywords:
        return None

    desc_upper = descricao.upper()
    for code, keywords in mapping_keywords.items():
        if all(kw in desc_upper for kw in keywords):
            return code
    for code, keywords in mapping_keywords.items():
        if any(kw in desc_upper for kw in keywords):
            if "CERCA" in desc_upper and "CERCA" not in keywords:
                continue
            return code
    return None


def apply_cpu_mappings(bench_data_root: Path) -> list[str]:
    """Aplica mapeamento automÃ¡tico de cpu_ids nos referencia.json de todos os benchmarks.

    Args:
        bench_data_root: diretÃ³rio benchmarks/data/

    Returns:
        Lista de mensagens de alteraÃ§Ãµes aplicadas.
    """
    log: list[str] = []
    for project_dir in bench_data_root.iterdir():
        if not project_dir.is_dir():
            continue
        ref_path = project_dir / "referencia.json"
        if not ref_path.exists():
            continue

        with open(ref_path, encoding="utf-8") as f:
            data = json.load(f)

        updated = False
        for item in data.get("eap", []):
            if not item.get("cpu_id"):
                code = map_desc(item["descricao"])
                if code:
                    item["cpu_id"] = code
                    updated = True

        if updated:
            with open(ref_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            log.append(f"[OK] {project_dir.name}: mapeamento cpu_id atualizado")

    return log
