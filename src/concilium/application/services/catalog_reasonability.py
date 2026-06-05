from __future__ import annotations

from datetime import UTC, datetime
from statistics import median
from typing import Any


def _q(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    pos = (len(ordered) - 1) * p
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    frac = pos - low
    return ordered[low] * (1 - frac) + ordered[high] * frac


def _iqr_bounds(values: list[float], *, non_negative: bool = False) -> tuple[float, float] | None:
    if len(values) < 8:
        return None
    q1 = _q(values, 0.25)
    q3 = _q(values, 0.75)
    iqr = q3 - q1
    if iqr <= 0:
        return None
    low = q1 - 1.5 * iqr
    high = q3 + 1.5 * iqr
    if non_negative:
        low = max(0.0, low)
        high = max(0.0, high)
    return low, high


def _robust_bounds(values: list[float], *, non_negative: bool = False) -> tuple[float, float] | None:
    """Compute outlier bounds robust to highly concentrated/multimodal groups.

    Starts with IQR bounds and expands them to include q10..q90 so the range
    does not collapse when many values are identical around the median.
    """
    if len(values) < 8:
        return None
    ordered = sorted(values)
    q10 = _q(ordered, 0.10)
    q90 = _q(ordered, 0.90)
    iqr = _iqr_bounds(ordered, non_negative=non_negative)

    if iqr is None:
        low, high = q10, q90
    else:
        low, high = iqr
        low = min(low, q10)
        high = max(high, q90)

    if non_negative:
        low = max(0.0, low)
        high = max(0.0, high)
    return low, high


def _safe_float(value: Any) -> float | None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num


def _sum_people(funcoes: list[dict[str, Any]]) -> int:
    total = 0
    for f in funcoes:
        try:
            total += int(float(f.get("num_pessoas", 0)))
        except (TypeError, ValueError):
            continue
    return max(total, 0)


def _sum_equips(equipamentos: list[dict[str, Any]]) -> int:
    total = 0
    for e in equipamentos:
        try:
            total += int(float(e.get("num_unidades", 0)))
        except (TypeError, ValueError):
            continue
    return max(total, 0)


def _build_prod_lookup(producoes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for prod in producoes:
        if not isinstance(prod, dict):
            continue
        pid = prod.get("id")
        if isinstance(pid, str) and pid:
            lookup[pid] = prod
    return lookup


def _resolve_team_from_producao(prod: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(prod, dict):
        return [], []
    equipe = prod.get("composicao_padrao_equipe")
    if not isinstance(equipe, dict):
        # Compatibilidade com payload antigo de produtividade.
        equipe = prod.get("equipe")
    if not isinstance(equipe, dict):
        return [], []
    funcoes = equipe.get("funcoes") if isinstance(equipe.get("funcoes"), list) else []
    equipamentos = equipe.get("equipamentos") if isinstance(equipe.get("equipamentos"), list) else []
    return funcoes, equipamentos


def _build_groups(rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (str(row.get("categoria") or "SEM_CATEGORIA"), str(row.get("unidade") or "SEM_UNIDADE"))
        grouped.setdefault(key, []).append(row)
    return grouped


def _build_summary_line(total: int, erros: int, avisos: int, outliers: int) -> str:
    return (
        f"Foram auditadas {total} CPUs. Encontradas {erros} inconsistências críticas, "
        f"{avisos} avisos e {outliers} possíveis outliers de produtividade."
    )


def build_catalog_reasonability_artifact(
    catalog_id: str,
    cpus: list[dict[str, Any]],
    producoes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    prod_lookup = _build_prod_lookup(producoes or [])
    rows: list[dict[str, Any]] = []
    for cpu in cpus:
        codigo = str(cpu.get("codigo") or "")
        producao_id_ref = str(cpu.get("producao_id_ref") or "")
        producao = prod_lookup.get(producao_id_ref)
        producao_horaria = _safe_float((producao or {}).get("valor_horario"))
        funcoes, equipamentos = _resolve_team_from_producao(producao)

        total_pessoas = _sum_people(funcoes)
        total_equip = _sum_equips(equipamentos)
        prod_por_pessoa = (producao_horaria / total_pessoas) if (producao_horaria and total_pessoas > 0) else None

        rows.append(
            {
                "cpu_id": codigo,
                "descricao": cpu.get("descricao") or "",
                "categoria": cpu.get("categoria") or "",
                "unidade": cpu.get("unidade") or "",
                "producao_id_ref": producao_id_ref,
                "producao_horaria": producao_horaria,
                "team_people": total_pessoas,
                "team_equipments": total_equip,
                "producao_por_pessoa": prod_por_pessoa,
                "issues": [],
                "severity": "OK",
            }
        )

    # Regras de consistência diretas (erro/aviso)
    for row in rows:
        issues: list[str] = row["issues"]
        if not row["producao_id_ref"]:
            issues.append("CPU sem producao_id_ref")
        if row["producao_horaria"] is None or row["producao_horaria"] <= 0:
            issues.append("Produtividade horária ausente ou não positiva")
        if row["producao_id_ref"] and row["producao_id_ref"] not in prod_lookup:
            issues.append("producao_id_ref sem registro correspondente em produções/produtividades")
        if row["team_people"] <= 0:
            issues.append("Equipe sem mão de obra definida")

        if any("ausente" in msg or "sem" in msg for msg in issues):
            row["severity"] = "ERRO"
        elif issues:
            row["severity"] = "AVISO"

    # Regras estatísticas por categoria+unidade
    grouped = _build_groups(rows)
    for key, items in grouped.items():
        prod_vals = [float(r["producao_horaria"]) for r in items if r["producao_horaria"] and r["producao_horaria"] > 0]
        ppp_vals = [float(r["producao_por_pessoa"]) for r in items if r["producao_por_pessoa"] and r["producao_por_pessoa"] > 0]

        # Produtividade e produtividade por pessoa são domínios não negativos.
        prod_bounds = _robust_bounds(prod_vals, non_negative=True)
        ppp_bounds = _robust_bounds(ppp_vals, non_negative=True)

        for r in items:
            v = r["producao_horaria"]
            if prod_bounds and v is not None and (v < prod_bounds[0] or v > prod_bounds[1]):
                r["issues"].append(
                    f"Produtividade fora da faixa IQR do grupo {key[0]}/{key[1]} ({prod_bounds[0]:.2f}..{prod_bounds[1]:.2f})"
                )
                if r["severity"] == "OK":
                    r["severity"] = "AVISO"

            vp = r["producao_por_pessoa"]
            if ppp_bounds and vp is not None and (vp < ppp_bounds[0] or vp > ppp_bounds[1]):
                r["issues"].append(
                    "Produtividade por pessoa fora da faixa IQR do grupo "
                    f"{key[0]}/{key[1]} ({ppp_bounds[0]:.2f}..{ppp_bounds[1]:.2f})"
                )
                if r["severity"] == "OK":
                    r["severity"] = "AVISO"

    erros = sum(1 for r in rows if r["severity"] == "ERRO")
    avisos = sum(1 for r in rows if r["severity"] == "AVISO")
    outliers = sum(1 for r in rows if any("IQR" in msg for msg in r["issues"]))

    prod_vals_all = [float(r["producao_horaria"]) for r in rows if isinstance(r["producao_horaria"], (int, float))]
    mediana_prod = median(prod_vals_all) if prod_vals_all else 0.0

    findings_sorted = sorted(
        [r for r in rows if r["issues"]],
        key=lambda x: (0 if x["severity"] == "ERRO" else 1, len(x["issues"]) * -1, x["cpu_id"]),
    )

    return {
        "catalog_id": catalog_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "total_cpus": len(rows),
            "erros": erros,
            "avisos": avisos,
            "outliers": outliers,
            "mediana_producao_horaria": mediana_prod,
            "n_cpus_com_time": sum(1 for r in rows if r["team_people"] > 0 or r["team_equipments"] > 0),
        },
        "narrative": {
            "headline": _build_summary_line(len(rows), erros, avisos, outliers),
            "recommendation": (
                "Priorize CPUs com severidade ERRO para saneamento de producao_id_ref, produtividade e equipe; "
                "em seguida revise AVISOS de outlier por categoria/unidade."
            ),
        },
        "findings": findings_sorted,
        "rows": rows,
    }
