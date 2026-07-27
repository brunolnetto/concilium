"""ADR-156 F1 — Composição de funções por tipo de pool + substituição segura de MO.

`RecursoContrato.tipo_id` não representa uma função de MO isolada — é um hash da
composição inteira de uma equipe (`_tipo_recurso_fungivel`, ADR-046), que pode
combinar múltiplas funções de MO e equipamentos sob o mesmo tipo_id. Substituir
`custo_unit_semanal_mo` por um roster de uma única função corromperia o resultado
de um tipo misto.

`extrair_composicao_funcoes_mo` expõe a mesma informação usada para gerar o hash,
sem tocar o pipeline real (`_tipo_recurso_fungivel` continua intocado).
`aplicar_roster_custo_real_mo` só substitui quando o roster cobre, com headcount
suficiente, TODAS as funções da composição — nunca substituição parcial, que
misturaria custo real com custo calibrado dentro do mesmo tipo.

Sem wiring ao orquestrador real de skill-05 nem a `Escopo` — ver ADR-157 (futura).
"""

from __future__ import annotations

from concilium.domain.models.canonical import MembroEquipeReal, RecursoContrato
from concilium.domain.models.catalog.catalogo import ComposicaoPadraoEquipe
from concilium.domain.services.financial.roster_custo_mo import custo_real_mo_total


def extrair_composicao_funcoes_mo(composicao: ComposicaoPadraoEquipe) -> dict[str, int]:
    """Extrai {funcao_id: num_pessoas} de uma ComposicaoPadraoEquipe do catálogo.

    Mesma informação usada por `_tipo_recurso_fungivel` (`_pool_contrato_construcao.py`)
    para gerar o hash do tipo_id — exposta aqui como função standalone, sem tocar o
    pipeline real. Funções sem `funcao_id` são ignoradas.
    """
    return {f.funcao_id: f.num_pessoas for f in composicao.funcoes if f.funcao_id}


def _cobertura_suficiente(roster: list[MembroEquipeReal], funcao_id: str, necessario: int) -> bool:
    distintos = {m.individuo_id for m in roster if m.funcao_id == funcao_id}
    return len(distintos) >= necessario


def roster_cobre_composicao_mo(contrato: RecursoContrato, roster: list[MembroEquipeReal]) -> bool:
    return all(
        _cobertura_suficiente(roster, funcao_id, num_pessoas * contrato.quantidade_contratada)
        for funcao_id, num_pessoas in contrato.composicao_funcoes_mo.items()
    )


def aplicar_roster_custo_real_mo(
    contrato: RecursoContrato,
    roster: list[MembroEquipeReal],
) -> RecursoContrato:
    """Substitui `custo_unit_semanal_mo` (e `custo_unit_semanal`/`custo_total_contrato`
    dependentes) pelo custo real do roster — só quando o roster cobre, com headcount
    suficiente, TODAS as funções em `contrato.composicao_funcoes_mo`.

    Verificação de cobertura por função: número de indivíduos distintos no roster com
    aquele `funcao_id` >= `num_pessoas_por_equipe × quantidade_contratada`. Se qualquer
    função não tiver cobertura suficiente (ou `composicao_funcoes_mo` estiver vazio),
    retorna o contrato SEM NENHUMA MUDANÇA — nunca faz substituição parcial.

    Não recalcula `particao_por_item` nem os demais campos derivados — decisão de
    ordem de execução no pipeline real fica para ADR-157.
    """
    if not contrato.composicao_funcoes_mo:
        return contrato
    if not roster_cobre_composicao_mo(contrato, roster):
        return contrato

    custo_real_total = sum(
        custo_real_mo_total(roster, funcao_id, contrato.semana_inicio, contrato.semana_fim)
        for funcao_id in contrato.composicao_funcoes_mo
    )
    denom = contrato.quantidade_contratada * contrato.semanas_contrato
    cus_mo_novo = round(custo_real_total / denom, 4) if denom > 0 else 0.0
    cus_outros = contrato.custo_unit_semanal_eq + contrato.custo_unit_semanal_comb + contrato.custo_unit_semanal_mat
    cus_semanal_novo = round(cus_mo_novo + cus_outros, 4)
    custo_total_novo = round(contrato.quantidade_contratada * cus_semanal_novo * contrato.semanas_contrato, 2)
    return contrato.model_copy(
        update={
            "custo_unit_semanal_mo": cus_mo_novo,
            "custo_unit_semanal": cus_semanal_novo,
            "custo_total_contrato": custo_total_novo,
        }
    )
