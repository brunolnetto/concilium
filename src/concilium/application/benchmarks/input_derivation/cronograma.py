from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from concilium.domain.models.catalog.snapshot import CatalogSnapshot
from concilium.infrastructure.catalog.catalog_loader import CatalogLoader


def _scale_item_if_needed(
    item_id: str,
    week_map: dict,
    ativ_by_id: dict,
    dias_semana: int,
    num_equipes_por_item: dict,
) -> None:
    ativ = ativ_by_id.get(item_id)
    if not ativ:
        return
    qty = float(ativ.get("quantitativo") or 0.0)
    prod_diaria = float(ativ.get("producao_diaria") or 0.0)
    if qty <= 0 or prod_diaria <= 0:
        return
    cap = sum(n * dias_semana * prod_diaria for n in week_map.values())
    if cap < qty:
        scale = math.ceil(qty / max(cap, 1e-6))
        num_equipes_por_item[item_id] = {w: (max(1, n * scale) if n > 0 else 0) for w, n in week_map.items()}


def _scale_derived_equipes(ref: dict, derived_from_ref: dict, num_equipes_por_item: dict) -> None:
    regime = ref.get("regime_trabalho", {"horas_dia": 8, "dias_semana": 6})
    dias_semana = regime.get("dias_semana", 6)
    ativ_by_id = {
        (a.get("item_id") or a.get("activity_id")): a for a in (ref.get("cronograma") or {}).get("atividades", [])
    }
    for item_id, week_map in list(derived_from_ref.items()):
        _scale_item_if_needed(item_id, week_map, ativ_by_id, dias_semana, num_equipes_por_item)


def _catalog_based_sizing(
    items_sem_ref: list,
    weeks: list,
    horas_semana: float,
    snapshot: CatalogSnapshot,
    num_equipes_por_item: dict,
) -> None:
    cpu_lookup: dict = {}
    for cpu in snapshot.cpus:
        if "codigo" in cpu:
            cpu_lookup[cpu["codigo"]] = cpu
    prod_lookup: dict = {}
    for prod in snapshot.produtividades:
        pk = prod.get("id") or prod.get("codigo")
        if pk:
            prod_lookup[pk] = prod
    for item in items_sem_ref:
        cpu_id = item.get("cpu_id")
        qty = item.get("quantitativo", 0)
        cpu_data = cpu_lookup.get(cpu_id)
        if not cpu_data or qty <= 0:
            continue
        prod = BenchmarkInputDeriver._resolve_productivity(cpu_data, prod_lookup)
        needed = math.ceil(qty / (prod * horas_semana * len(weeks)) * 1.25)
        num_equipes_por_item[item["item_id"]] = {week: min(1000, max(1, needed)) for week in weeks}


def _drfs_get_item_ids(eap: list) -> set:
    """Returns set of non-empty item_id values from eap list."""
    return {item.get("item_id") for item in eap if item.get("item_id")}


def _drfs_build_week_map(cronograma: dict) -> dict:
    """Builds iso_key -> numeric_key reverse map from cronograma.semanas metadata."""
    semanas_meta = cronograma.get("semanas", {})
    if semanas_meta and all(k.isdigit() for k in semanas_meta.keys()):
        from concilium.application.benchmarks.input_derivation.week_mapper import (
            build_numeric_to_iso_map,
        )

        num_to_iso = build_numeric_to_iso_map(semanas_meta)
        return {v: k for k, v in num_to_iso.items()}
    return {}


def _drfs_get_week_equipes(semanas: dict, week: str, iso_to_num: dict) -> int:
    """Returns num_equipes for a single week key, trying ISO then numeric fallback."""
    week_row = semanas.get(week)
    if week_row is None and iso_to_num:
        num_key = iso_to_num.get(week)
        if num_key:
            week_row = semanas.get(num_key)
    if isinstance(week_row, dict):
        num_equipes = week_row.get("num_equipes", 0)
    else:
        num_equipes = 0
    try:
        return max(0, int(round(float(num_equipes))))
    except Exception:
        return 0


def _drfs_extract_item_weeks(atividade: dict, weeks: list, iso_to_num: dict) -> tuple[dict | None, bool]:
    """Builds week->n_equipes dict for one atividade; returns (dict, has_non_zero)."""
    semanas = atividade.get("semanas")
    if not isinstance(semanas, dict):
        return None, False
    item_weeks: dict = {week: 0 for week in weeks}
    has_non_zero = False
    for week in weeks:
        n = _drfs_get_week_equipes(semanas, week, iso_to_num)
        item_weeks[week] = n
        if n > 0:
            has_non_zero = True
    return item_weeks, has_non_zero


class BenchmarkInputDeriver:
    """Deriva inputs sinteticos para benchmarks sem expor o runner ao layout do catalogo."""

    def __init__(self, config_root: Path, project_root: Path | None = None) -> None:
        self._config_root = Path(config_root)
        self._project_root = Path(project_root) if project_root else self._config_root.parent

    def _load_and_size(
        self,
        ref: dict[str, Any],
        items_sem_ref: list,
        weeks: list,
        catalog_name: str,
        num_equipes_por_item: dict,
    ) -> None:
        try:
            regime = ref.get("regime_trabalho", {"horas_dia": 8, "dias_semana": 6})
            horas_semana = regime.get("horas_dia", 8) * regime.get("dias_semana", 6)
            loader = CatalogLoader(
                config_root=self._config_root,
                project_root=self._project_root,
                offline=False,
                force_refresh=False,
            )
            snapshot, _ = loader.load(catalog_name)
            _catalog_based_sizing(items_sem_ref, weeks, horas_semana, snapshot, num_equipes_por_item)
        except Exception as exc:
            print(f"  [WARN] Erro no auto-sizing: {exc}")

    def derive_num_equipes_por_item(
        self,
        ref: dict[str, Any],
        eap: list[dict[str, Any]],
        weeks: list[str],
        catalog_name: str = "mendeslobo",
    ) -> dict[str, dict[str, int]]:
        num_equipes_por_item: dict[str, dict[str, int]] = {}

        derived_from_ref = self._derive_from_reference_schedule(ref, eap, weeks)
        num_equipes_por_item.update(derived_from_ref)

        if derived_from_ref:
            _scale_derived_equipes(ref, derived_from_ref, num_equipes_por_item)

        items_sem_ref = [item for item in eap if item.get("item_id") not in num_equipes_por_item]
        if items_sem_ref:
            self._load_and_size(ref, items_sem_ref, weeks, catalog_name, num_equipes_por_item)

        for item in eap:
            if item.get("item_id") not in num_equipes_por_item:
                num_equipes_por_item[item["item_id"]] = {week: 1 for week in weeks}

        return num_equipes_por_item

    @staticmethod
    def _derive_from_reference_schedule(
        ref: dict[str, Any],
        eap: list[dict[str, Any]],
        weeks: list[str],
    ) -> dict[str, dict[str, int]]:
        cronograma = ref.get("cronograma")
        if not isinstance(cronograma, dict):
            return {}
        atividades = cronograma.get("atividades")
        if not isinstance(atividades, list):
            return {}
        item_ids = _drfs_get_item_ids(eap)
        if not item_ids:
            return {}
        iso_to_num = _drfs_build_week_map(cronograma)
        result: dict = {}
        for atividade in atividades:
            if not isinstance(atividade, dict):
                continue
            activity_id = atividade.get("activity_id") or atividade.get("item_id")
            if activity_id not in item_ids:
                continue
            item_weeks, has_non_zero = _drfs_extract_item_weeks(atividade, weeks, iso_to_num)
            if has_non_zero:
                result[activity_id] = item_weeks
        return result

    @staticmethod
    def _resolve_productivity(cpu: dict[str, Any], prod_lookup: dict[str, dict[str, Any]]) -> float:
        prod_id = cpu.get("producao_id_ref")
        prod_item = prod_lookup.get(prod_id) if prod_id else None
        if prod_item is not None:
            value = prod_item.get("valor_horario")
            if value is None:
                value = prod_item.get("producao_horaria")
            if isinstance(value, (int, float)):
                return float(value)

        return 1.0
