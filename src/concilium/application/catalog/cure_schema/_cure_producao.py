"""Curação do catálogo — parte extraída de cure_schema.py (grupo _cure_producao)."""

from __future__ import annotations

from ._core import CurationReport, _normalize_team, _now_iso


def _cure_producao_cpu_contamination(changed: dict, pid: object, report: CurationReport, apply: bool) -> None:
    # Remove campos exclusivos de CPU que contaminaram Producao
    prod_cpu_fields = {"atributos_categoria", "cpu_ids"}
    contaminados = [k for k in prod_cpu_fields if k in changed]
    if contaminados:
        if apply:
            for k in contaminados:
                del changed[k]
        for k in contaminados:
            report.add_fixed(f"PRODUCAO {pid}: removido campo exclusivo de CPU '{k}'")


def _cure_producao_migra_producao_horaria(changed: dict, pid: object, report: CurationReport, apply: bool) -> None:
    # Migra campo legado valor_horario -> producao_horaria canônico
    if "valor_horario" in changed:
        if apply:
            if "producao_horaria" not in changed and changed.get("valor_horario") is not None:
                changed["producao_horaria"] = changed.get("valor_horario")
            del changed["valor_horario"]
        report.add_fixed(f"PRODUCAO {pid}: migrado/removido campo legado valor_horario")


def _cure_producao_migra_equipe(changed: dict, pid: object, report: CurationReport, apply: bool) -> None:
    # Migra equipe -> composicao_padrao_equipe
    if "equipe" in changed and "composicao_padrao_equipe" not in changed:
        if apply:
            changed["composicao_padrao_equipe"] = changed.pop("equipe")
        report.add_fixed(f"PRODUCAO {pid}: migrado equipe -> composicao_padrao_equipe")

    elif "equipe" in changed and "composicao_padrao_equipe" in changed:
        if apply:
            del changed["equipe"]
        report.add_fixed(f"PRODUCAO {pid}: removido campo legado equipe (composicao_padrao_equipe ja existe)")

    # Normaliza composição padrão para remover duplicidade de funções/equipamentos
    equipe_padrao = changed.get("composicao_padrao_equipe")
    if isinstance(equipe_padrao, dict):
        normalized = _normalize_team(equipe_padrao)
        if normalized != equipe_padrao:
            if apply:
                changed["composicao_padrao_equipe"] = normalized
            report.add_fixed(f"PRODUCAO {pid}: deduplicada composicao_padrao_equipe")


def _cure_producao_legado(changed: dict, pid: object, report: CurationReport, apply: bool) -> None:
    _cure_producao_migra_producao_horaria(changed, pid, report, apply)
    _cure_producao_migra_equipe(changed, pid, report, apply)

    # Nota: cpu_ids já está em prod_cpu_fields acima e é removido de lá quando
    # apply=True; este bloco só dispara em dry-run (apply=False) para reportar
    # o campo pendente de remoção.
    if "cpu_ids" in changed:
        report.add_fixed(f"PRODUCAO {pid}: removido cpu_ids (derivável via CPU.producao_id_ref)")


def _cure_producao_complete_observacao(item: dict) -> dict:
    fixed_item = dict(item)
    if not fixed_item.get("data"):
        fixed_item["data"] = _now_iso()
    if not fixed_item.get("autor"):
        fixed_item["autor"] = "cure_catalog"
    if not fixed_item.get("descricao"):
        fixed_item["descricao"] = "(migrado sem descrição original)"
    if not fixed_item.get("tipo"):
        fixed_item["tipo"] = "migracao"
    return fixed_item


def _cure_producao_historico(changed: dict, pid: object, report: CurationReport, apply: bool) -> None:
    # Estrutura historico_observacoes
    obs = changed.get("historico_observacoes", [])
    if not isinstance(obs, list):
        return
    new_obs = []
    for i, item in enumerate(obs):
        if not isinstance(item, dict):
            report.add_skipped(f"PRODUCAO {pid}: historico_observacoes[{i}] não é objeto — ignorado")
            continue
        missing = [f for f in ("data", "autor", "descricao") if not item.get(f)]
        if missing:
            if apply:
                new_obs.append(_cure_producao_complete_observacao(item))
            report.add_fixed(f"PRODUCAO {pid}: historico_observacoes[{i}] completado com campos ausentes: {missing}")
        else:
            new_obs.append(item)
    if apply:
        changed["historico_observacoes"] = new_obs


def _cure_producao_variantes(changed: dict, pid: object, report: CurationReport, apply: bool) -> None:
    # Normaliza equipes dentro de variantes (quando existirem)
    variantes = changed.get("variantes")
    if not isinstance(variantes, list):
        return
    novas_variantes = []
    touched = False
    for item in variantes:
        if not isinstance(item, dict):
            novas_variantes.append(item)
            continue
        var = dict(item)
        equipe_var = var.get("equipe")
        if isinstance(equipe_var, dict):
            normalized_var = _normalize_team(equipe_var)
            if normalized_var != equipe_var:
                var["equipe"] = normalized_var
                touched = True
        novas_variantes.append(var)
    if apply and touched:
        changed["variantes"] = novas_variantes
    if touched:
        report.add_fixed(f"PRODUCAO {pid}: deduplicadas equipes nas variantes")


def cure_producao(prod: dict, report: CurationReport, apply: bool) -> dict:
    pid = prod.get("id", "<sem-id>")
    changed = dict(prod)

    _cure_producao_cpu_contamination(changed, pid, report, apply)
    _cure_producao_legado(changed, pid, report, apply)
    _cure_producao_historico(changed, pid, report, apply)
    _cure_producao_variantes(changed, pid, report, apply)

    return changed if apply else prod


