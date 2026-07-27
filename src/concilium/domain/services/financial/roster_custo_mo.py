"""ADR-154 F1 — Roster real de mão-de-obra: custo individualizado por semana.

Soma, semana a semana, o custo real de cada `MembroEquipeReal` ativo numa função —
salário-base convertido a taxa semanal, mais encargos reais resolvidos via
`resolver_encargo` (ADR-097, mesma precedência usada em toda a cadeia de custo).

Sem nenhuma ligação com `InstanciaRecurso`/`segmentos_atividade`/`identidade_fisica_id`
(ADR-153) — o pool RCPSP permanece fungível; isto é puramente uma camada de custo
bottom-up a partir de pessoas reais, independente de scheduling.

Granularidade semanal (mesma do resto do motor RCPSP): admissão/desligamento no meio
de uma semana ISO não gera rateio por dia — a semana inteira em que a data cai é
contabilizada por completo.
"""

from __future__ import annotations

from datetime import date, timedelta

from concilium.domain.constants import ENCARGOS_CLT, ENCARGOS_MENSALISTA, SEMANAS_POR_MES
from concilium.domain.models.canonical import MembroEquipeReal
from concilium.domain.services.financial.encargo_resolver import resolver_encargo
from concilium.domain.services.planning.week_sequence import enumerar_semanas


def _intervalo_semana(semana: str) -> tuple[date, date]:
    """Segunda a domingo de uma semana ISO (ex: "2026-W03")."""
    year_str, week_str = semana.split("-W")
    segunda = date.fromisocalendar(int(year_str), int(week_str), 1)
    return segunda, segunda + timedelta(days=6)


def _membro_ativo_na_semana(membro: MembroEquipeReal, semana: str) -> bool:
    segunda, domingo = _intervalo_semana(semana)
    if membro.data_admissao > domingo:
        return False
    return membro.data_desligamento is None or membro.data_desligamento >= segunda


def _custo_semanal_membro(membro: MembroEquipeReal) -> float:
    atrib = {
        "categoria_sindical": membro.categoria_sindical,
        "percentual_encargos_local": membro.percentual_encargos_local,
    }
    taxa_encargo = resolver_encargo(atrib, enc_horista=ENCARGOS_CLT, enc_mensalista=ENCARGOS_MENSALISTA)
    return (membro.salario_base_mensal / SEMANAS_POR_MES) * (1 + taxa_encargo)


def custo_real_mo_semanal(
    roster: list[MembroEquipeReal],
    funcao_id: str,
    semana_inicio: str,
    semana_fim: str,
) -> dict[str, float]:
    """Custo real de MO por semana — soma, por semana, o custo de cada membro do
    roster ativo naquela função e naquele intervalo.

        custo_semana(t) = Σ_{membro ativo em t} (salario_base_mensal / SEMANAS_POR_MES)
                           × (1 + resolver_encargo(membro))

    Membros de outra função (`funcao_id` diferente) são ignorados.
    """
    membros_funcao = [m for m in roster if m.funcao_id == funcao_id]
    custo: dict[str, float] = {}
    for semana in enumerar_semanas(semana_inicio, semana_fim):
        total_semana = sum(
            _custo_semanal_membro(m) for m in membros_funcao if _membro_ativo_na_semana(m, semana)
        )
        custo[semana] = round(total_semana, 2)
    return custo


def custo_real_mo_total(
    roster: list[MembroEquipeReal],
    funcao_id: str,
    semana_inicio: str,
    semana_fim: str,
) -> float:
    """Custo real total de MO no span — soma de `custo_real_mo_semanal`."""
    return round(sum(custo_real_mo_semanal(roster, funcao_id, semana_inicio, semana_fim).values()), 2)
