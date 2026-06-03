"""Enumeração e indexação de semanas — utilitário compartilhado (ADR-086).

Suporta os dois formatos de chave de semana usados no Concilium:
  - Sequencial de benchmark: ``"S001"``, ``"S052"`` …
  - ISO 8601: ``"2026-W23"`` …

Usado por:
  - skill-05 (``_build_instancias_recurso``) para registrar segmentos ociosos por slot;
  - ``CuboPoolInstancialBuilder`` para enumerar o span do contrato semana a semana.
"""

from __future__ import annotations

from datetime import date, timedelta

_EPOCH_MONDAY = date(2000, 1, 3)  # segunda-feira da semana ISO 1 de 2000


def week_index(semana: str) -> int:
    """Índice inteiro comparável a partir de uma chave de semana (Snnn ou ISO)."""
    s = str(semana).strip()
    if s.startswith("S") and s[1:].isdigit():
        return int(s[1:])
    if "-W" in s:
        try:
            year_str, week_str = s.split("-W")
            monday = date.fromisocalendar(int(year_str), int(week_str), 1)
            return (monday - _EPOCH_MONDAY).days // 7
        except Exception:
            return 0
    try:
        return int(s.lstrip("0") or "0")
    except ValueError:
        return 0


def _is_iso(semana: str) -> bool:
    return "-W" in str(semana)


def _is_seq(semana: str) -> bool:
    s = str(semana).strip()
    return s.startswith("S") and s[1:].isdigit()


def next_week(semana: str) -> str:
    """Chave da semana imediatamente seguinte, preservando o formato de entrada."""
    s = str(semana).strip()
    if _is_seq(s):
        n = int(s[1:])
        width = len(s) - 1
        return f"S{n + 1:0{width}d}"
    if _is_iso(s):
        year_str, week_str = s.split("-W")
        monday = date.fromisocalendar(int(year_str), int(week_str), 1) + timedelta(days=7)
        iso = monday.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    # Fallback: trata como inteiro puro
    try:
        return str(int(s) + 1)
    except ValueError:
        return s


def enumerar_semanas(inicio: str, fim: str) -> list[str]:
    """Lista inclusiva de chaves de semana de ``inicio`` a ``fim`` (mesmo formato).

    Retorna ``[]`` se ``fim`` precede ``inicio``. Determinístico; sem I/O.
    """
    if inicio is None or fim is None or inicio == "" or fim == "":
        return []
    i_idx, f_idx = week_index(inicio), week_index(fim)
    if f_idx < i_idx:
        return []
    out: list[str] = [inicio]
    cur = inicio
    # Limite de segurança contra formatos inesperados (não deve disparar em uso normal)
    for _ in range(f_idx - i_idx):
        cur = next_week(cur)
        out.append(cur)
        if week_index(cur) >= f_idx:
            break
    return out
