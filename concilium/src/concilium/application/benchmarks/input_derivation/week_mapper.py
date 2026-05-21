"""BenchmarkWeekMapper — ADR-043.

Converte esquema de semanas numéricas (planilha) para ISO-week keys
usadas pelo BenchmarkInputDeriver e pela Skill-02.

Esquema numérico: cronograma.semanas = {"1": {"data_inicio": "2026-01-05", ...}, ...}
Esquema ISO:      cronograma.atividades[i].semanas = {"2026-W02": {...}, ...}
"""

from __future__ import annotations

from datetime import date
from typing import Any


def is_numeric_week_scheme(semanas: dict[str, Any]) -> bool:
    """Retorna True se todas as chaves do dicionário de semanas são numéricas."""
    if not semanas:
        return False
    return all(k.isdigit() for k in semanas.keys())


def build_numeric_to_iso_map(semanas_meta: dict[str, Any]) -> dict[str, str]:
    """Constrói mapeamento {str_num -> iso_week_key} a partir de cronograma.semanas.

    Args:
        semanas_meta: o objeto ``cronograma.semanas`` do referencia.json,
                      com chaves numéricas e valores ``{"data_inicio": "YYYY-MM-DD", ...}``.

    Returns:
        Dicionário ``{"1": "2026-W02", "2": "2026-W03", ...}``.
    """
    result: dict[str, str] = {}
    for k, v in semanas_meta.items():
        if not k.isdigit():
            continue
        if not isinstance(v, dict):
            continue
        data_inicio = v.get("data_inicio")
        if not data_inicio:
            continue
        try:
            d = date.fromisoformat(str(data_inicio))
        except ValueError:
            continue
        iso = d.isocalendar()
        result[k] = f"{iso.year}-W{iso.week:02d}"
    return result


def remap_activity_semanas(
    activity_semanas: dict[str, Any],
    num_to_iso: dict[str, str],
) -> dict[str, Any]:
    """Remapeia um dict de semanas de chaves numéricas para ISO.

    Preserva a estrutura interna de cada semana (num_equipes, qty_planejada, etc.).
    """
    result: dict[str, Any] = {}
    for k, v in activity_semanas.items():
        iso_key = num_to_iso.get(k, k)  # se não encontrar, mantém original
        result[iso_key] = v
    return result


def normalize_referencia_weeks(ref: dict[str, Any]) -> dict[str, Any]:
    """Normaliza o referencia.json in-place: converte semanas numéricas → ISO em
    todas as atividades do cronograma, e injeta data_inicio/data_termino no nível
    raiz quando ausentes.

    Retorna o mesmo dict modificado (não faz cópia profunda por performance).
    """
    cronograma = ref.get("cronograma")
    if not isinstance(cronograma, dict):
        return ref

    semanas_meta = cronograma.get("semanas", {})
    if not is_numeric_week_scheme(semanas_meta):
        return ref  # já está em ISO ou vazio — nada a fazer

    num_to_iso = build_numeric_to_iso_map(semanas_meta)
    if not num_to_iso:
        return ref

    # Injetar data_inicio / data_termino no nível raiz se ausentes
    sorted_nums = sorted(num_to_iso.keys(), key=int)
    if sorted_nums:
        first_week_meta = semanas_meta.get(sorted_nums[0], {})
        last_week_meta = semanas_meta.get(sorted_nums[-1], {})

        if not ref.get("data_inicio") and first_week_meta.get("data_inicio"):
            ref["data_inicio"] = str(first_week_meta["data_inicio"])

        if not ref.get("data_termino") and last_week_meta.get("data_fim"):
            ref["data_termino"] = str(last_week_meta["data_fim"])
        elif not ref.get("data_termino") and last_week_meta.get("data_inicio"):
            ref["data_termino"] = str(last_week_meta["data_inicio"])

    # Remap semanas em cada atividade
    atividades = cronograma.get("atividades")
    if isinstance(atividades, list):
        for atividade in atividades:
            if not isinstance(atividade, dict):
                continue
            semanas = atividade.get("semanas")
            if not isinstance(semanas, dict):
                continue
            if is_numeric_week_scheme(semanas):
                atividade["semanas"] = remap_activity_semanas(semanas, num_to_iso)

    return ref
