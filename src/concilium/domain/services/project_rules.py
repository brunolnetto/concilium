from typing import Any


def validate_delete_version(tipo_projeto: str, versions: list[str], version: str):
    if len(versions) == 1 and tipo_projeto == "project":
        raise RuntimeError("Não é permitido excluir a última versão de um projeto do tipo PROJECT.")


def resolve_compare_version(project, version: str) -> str:
    if project.load_canonical(version) is not None:
        return version

    versions = project.list_versions()
    if not version.startswith("v") or not version[1:].isdigit():
        raise ValueError(f"Versao invalida: {version}")

    target_num = int(version[1:])
    for candidate in reversed(versions):
        if not candidate.startswith("v") or not candidate[1:].isdigit():
            continue
        if int(candidate[1:]) > target_num:
            continue
        if project.load_canonical(candidate) is not None:
            return candidate

    raise ValueError(f"Versao sem canônico disponível: {version}")


def calculate_deltas(left_summary: dict[str, Any], right_summary: dict[str, Any]) -> dict[str, float]:
    def _delta(key: str) -> float:
        _r = right_summary.get(key)
        _l = left_summary.get(key)
        return float(_r if _r is not None else 0.0) - float(_l if _l is not None else 0.0)

    return {
        "preco_venda_total": _delta("preco_venda_total"),
        "custo_total": _delta("custo_total"),
        "margem_pct": _delta("margem_pct"),
        "resultado_bruto": _delta("resultado_bruto"),
        "pe_deficit_items": _delta("pe_deficit_items"),
    }
