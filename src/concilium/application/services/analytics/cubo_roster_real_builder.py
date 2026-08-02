"""Builder do Cubo de Roster Real — ADR-174.

Diferença estrutural deliberada frente a `CuboEstoqueConsumivelBuilder`: aquele
lê só do canônico, porque `recursos_consumiveis` é "baked-in" pela skill-04.
Roster (`Escopo.roster_mo`/`roster_eq`, ADR-173/174) nunca é baked-in no
canônico por decisão de design (ADR-160 D1) — é sempre transiente, buscado à
parte pelo chamador. Por isso este builder recebe `roster_mo`/`roster_eq`/
`catalogo` como parâmetros explícitos, em vez de `getattr(canonical_in, ...)`.

Vive em `application/` (não `domain/services/analytics/`) pela mesma razão do
builder de estoque consumível: importa de `domain/services/financial`, que já
está em `domain/`, mas segue a convenção de onde os outros builders de cubo já
residem nesta versão do repo.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from concilium.domain.models.analytics.cubo_roster_real import (
    CelulaRosterReal,
    CuboRosterReal,
)
from concilium.domain.models.canonical import AtivoEquipamentoReal, MembroEquipeReal
from concilium.domain.services.financial.roster_custo_equipamento import (
    custo_semanal_individual_eq,
)
from concilium.domain.services.financial.roster_custo_mo import (
    custo_semanal_individual_mo,
)


def _get_projeto_id(canonical_in: Any) -> str:
    proj = getattr(canonical_in, "projeto", None)
    if proj is None:
        return ""
    return str(getattr(proj, "nome", "") or getattr(proj, "id", "") or "")


def _iso_week_key(d: date) -> str:
    """Chave de semana ISO 'AAAA-Www' — mesma convenção de `_skill_helpers/_custos.py`."""
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


class CuboRosterRealBuilder:
    """Constrói `CuboRosterReal` a partir do roster real (MO+EQ), bounded pelo
    span do projeto (ADR-174)."""

    def build(
        self,
        canonical_in: Any,
        roster_mo: list[MembroEquipeReal] | None,
        roster_eq: list[AtivoEquipamentoReal] | None,
        catalogo: dict[str, Any] | None,
        *,
        gerado_em: str = "",
    ) -> CuboRosterReal:
        projeto_id = _get_projeto_id(canonical_in)
        semana_inicio, semana_fim = self._span(canonical_in)

        celulas: list[CelulaRosterReal] = []
        if semana_inicio and semana_fim:
            for membro in roster_mo or []:
                celulas.extend(self._celulas_mo(membro, semana_inicio, semana_fim, catalogo))
            for ativo in roster_eq or []:
                celulas.extend(self._celulas_eq(ativo, semana_inicio, semana_fim))

        return CuboRosterReal(projeto_id=projeto_id, gerado_em=gerado_em, celulas=tuple(celulas))

    @staticmethod
    def _span(canonical_in: Any) -> tuple[str | None, str | None]:
        proj = getattr(canonical_in, "projeto", None)
        data_inicio = getattr(proj, "data_inicio", None) if proj is not None else None
        data_termino = getattr(proj, "data_termino", None) if proj is not None else None
        if data_inicio is None or data_termino is None:
            return None, None
        return _iso_week_key(data_inicio), _iso_week_key(data_termino)

    @staticmethod
    def _celulas_mo(
        membro: MembroEquipeReal, semana_inicio: str, semana_fim: str, catalogo: dict[str, Any] | None
    ) -> list[CelulaRosterReal]:
        itens = custo_semanal_individual_mo(membro, semana_inicio, semana_fim, catalogo)
        return [
            CelulaRosterReal(
                categoria="MAO_OBRA",
                grupo_id=membro.funcao_id,
                instancia_id=membro.individuo_id,
                semana_iso=item["semana"],
                custo_direto=item["custo_direto"],
                custo_indireto=item["custo_indireto"],
                custo_total=item["custo_total"],
            )
            for item in itens
        ]

    @staticmethod
    def _celulas_eq(ativo: AtivoEquipamentoReal, semana_inicio: str, semana_fim: str) -> list[CelulaRosterReal]:
        itens = custo_semanal_individual_eq(ativo, semana_inicio, semana_fim)
        return [
            CelulaRosterReal(
                categoria="EQUIPAMENTO",
                grupo_id=ativo.equip_id,
                instancia_id=ativo.ativo_id,
                semana_iso=item["semana"],
                custo_direto=item["custo_direto"],
                custo_indireto=0.0,
                custo_total=item["custo_total"],
            )
            for item in itens
        ]
