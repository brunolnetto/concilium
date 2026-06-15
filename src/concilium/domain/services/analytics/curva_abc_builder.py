"""CurvaABCBuilder — constrói a Curva ABC por insumo do projeto (ADR-058 D2).

Agrega custos de equipes_diretas por funcao_id / equip_id, ordena desc e
classifica em A (80%), B (95%), C (100%) usando o método de Pareto 80-20.

Totalmente puro: sem I/O, sem estado mutável.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from concilium.domain.models.analytics.analitica import CurvaABCInsumo, InsumoDetalheAtividade, ItemCurvaABC


def _accumulate_funcoes_de_equipe(custo_acum: dict, equipe: object) -> None:
    item_id = equipe.item_id  # type: ignore[attr-defined]
    perm = equipe.permanencia_meses or 0.0  # type: ignore[attr-defined]
    for funcao in equipe.funcoes:  # type: ignore[attr-defined]
        fid = funcao.funcao_id or funcao.descricao or "MO-?"
        custo = funcao.custo_mensal_unitario * funcao.num_pessoas * perm
        custo_acum[fid]["descricao"] = funcao.descricao or fid
        custo_acum[fid]["categoria"] = "MAO_OBRA"
        custo_acum[fid]["custo_total"] += custo
        custo_acum[fid]["atividades"].add(item_id)


def _accumulate_equipamentos_de_equipe(custo_acum: dict, equipe: object) -> None:
    item_id = equipe.item_id  # type: ignore[attr-defined]
    perm = equipe.permanencia_meses or 0.0  # type: ignore[attr-defined]
    for equip in equipe.equipamentos:  # type: ignore[attr-defined]
        eid = equip.equip_id or equip.descricao or "EQ-?"
        custo_eq = equip.custo_mensal * perm
        custo_comb = equip.custo_combustivel_mensal * perm
        custo_acum[eid]["descricao"] = equip.descricao or eid
        custo_acum[eid]["categoria"] = "EQUIPAMENTO"
        custo_acum[eid]["custo_total"] += custo_eq
        custo_acum[eid]["atividades"].add(item_id)
        if custo_comb > 0:
            diesel_key = f"{eid}__DIESEL"
            custo_acum[diesel_key]["descricao"] = f"Diesel: {equip.descricao or eid}"
            custo_acum[diesel_key]["categoria"] = "DIESEL"
            custo_acum[diesel_key]["custo_total"] += custo_comb
            custo_acum[diesel_key]["atividades"].add(item_id)


def _build_custo_acum(equipes_diretas: list) -> dict:
    custo_acum: dict = defaultdict(lambda: {"descricao": "", "categoria": "", "custo_total": 0.0, "atividades": set()})
    for equipe in equipes_diretas:
        _accumulate_funcoes_de_equipe(custo_acum, equipe)
        _accumulate_equipamentos_de_equipe(custo_acum, equipe)
    return custo_acum


def _classify_and_build_items(sorted_items: list, total: float) -> list:
    itens: list = []
    acum = 0.0
    for insumo_id, data in sorted_items:
        custo = data["custo_total"]
        pct = custo / total
        acum += pct
        classe = "A" if acum <= 0.80 else ("B" if acum <= 0.95 else "C")
        itens.append(
            ItemCurvaABC(
                insumo_id=insumo_id,
                descricao=data["descricao"],
                categoria=data["categoria"],
                custo_total=round(custo, 2),
                pct_custo=round(pct, 6),
                pct_custo_acumulado=round(acum, 6),
                classe=classe,  # type: ignore[arg-type]
                atividades=tuple(sorted(data["atividades"])),
            )
        )
    return itens


def _sum_by_class(itens: list, classe: str) -> float:
    return sum(i.custo_total for i in itens if i.classe == classe)


def _count_by_class(itens: list, classe: str) -> int:
    return sum(1 for i in itens if i.classe == classe)


def _build_funcoes_detalhes(detalhes: list, funcoes, perm: float) -> None:
    for funcao in funcoes:
        fid = funcao.funcao_id or "MO-?"
        custo = round(funcao.custo_mensal_unitario * funcao.num_pessoas * perm, 2)
        detalhes.append(
            InsumoDetalheAtividade(
                insumo_id=fid,
                descricao=funcao.descricao or fid,
                categoria="MAO_OBRA",
                num_unidades=float(funcao.num_pessoas),
                custo_unitario_mensal=funcao.custo_mensal_unitario,
                permanencia_meses=perm,
                custo_total=custo,
            )
        )


def _build_equipamentos_detalhes(detalhes: list, equipamentos, perm: float) -> None:
    for equip in equipamentos:
        eid = equip.equip_id or "EQ-?"
        custo_eq = round(equip.custo_mensal * perm, 2)
        detalhes.append(
            InsumoDetalheAtividade(
                insumo_id=eid,
                descricao=equip.descricao or eid,
                categoria="EQUIPAMENTO",
                num_unidades=float(equip.num_unidades),
                custo_unitario_mensal=equip.custo_mensal,
                permanencia_meses=perm,
                custo_total=custo_eq,
            )
        )
        if equip.custo_combustivel_mensal > 0:
            custo_comb = round(equip.custo_combustivel_mensal * perm, 2)
            detalhes.append(
                InsumoDetalheAtividade(
                    insumo_id=f"{eid}__DIESEL",
                    descricao=f"Diesel: {equip.descricao or eid}",
                    categoria="DIESEL",
                    num_unidades=float(equip.num_unidades),
                    custo_unitario_mensal=equip.custo_combustivel_mensal,
                    permanencia_meses=perm,
                    custo_total=custo_comb,
                )
            )


class CurvaABCBuilder:
    """Constrói CurvaABCInsumo a partir de um CanonicalModel."""

    def build(self, canonical_in: Any) -> CurvaABCInsumo:
        """Agrega custos por insumo_id e classifica em A/B/C.

        Fonte de dados: canonical_in.equipes_diretas (FuncaoEquipeDireta + EquipamentoEquipeDireta)
        """
        projeto_id = str(getattr(getattr(canonical_in, "projeto", None), "nome", "?"))
        custo_acum = _build_custo_acum(canonical_in.equipes_diretas or [])
        total = sum(v["custo_total"] for v in custo_acum.values())
        if total <= 0:
            return CurvaABCInsumo(
                projeto_id=projeto_id,
                gerado_em=datetime.now(UTC).isoformat(),
                total_custo_direto=0.0,
                itens=(),
                total_a=0.0,
                total_b=0.0,
                total_c=0.0,
                n_itens_a=0,
                n_itens_b=0,
                n_itens_c=0,
            )
        sorted_items = sorted(custo_acum.items(), key=lambda kv: kv[1]["custo_total"], reverse=True)
        itens = _classify_and_build_items(sorted_items, total)
        return CurvaABCInsumo(
            projeto_id=projeto_id,
            gerado_em=datetime.now(UTC).isoformat(),
            total_custo_direto=round(total, 2),
            itens=tuple(itens),
            total_a=round(_sum_by_class(itens, "A"), 2),
            total_b=round(_sum_by_class(itens, "B"), 2),
            total_c=round(_sum_by_class(itens, "C"), 2),
            n_itens_a=_count_by_class(itens, "A"),
            n_itens_b=_count_by_class(itens, "B"),
            n_itens_c=_count_by_class(itens, "C"),
        )

    def build_detalhes_por_atividade(self, canonical_in: Any) -> dict[str, list[InsumoDetalheAtividade]]:
        """Produz {item_id: list[InsumoDetalheAtividade]} para popular custos_atividades."""
        resultado: dict[str, list[InsumoDetalheAtividade]] = {}
        for equipe in canonical_in.equipes_diretas or []:
            item_id = equipe.item_id
            perm = equipe.permanencia_meses or 0.0
            detalhes: list[InsumoDetalheAtividade] = []
            _build_funcoes_detalhes(detalhes, equipe.funcoes, perm)
            _build_equipamentos_detalhes(detalhes, equipe.equipamentos, perm)
            resultado[item_id] = detalhes
        return resultado
