"""ADR-152 — Timelapse de ocupação de InstanciaRecurso (pool de MO/equipamento).

Expande `segmentos_atividade`/`segmentos_idle` — já persistidos em `InstanciaRecurso`
(ADR-077/083/085) — numa projeção semana-a-semana de status, análoga a
`project_estoque_semanal` (ADR-128) para material: reconstrói uma visão fina a partir
de dado já resolvido, sem tocar o solver nem a atribuição de slots.

Não individualiza identidade física (pessoa/máquina) — `InstanciaRecurso` continua
sendo um slot contratual, não um ativo físico específico (ADR-059, ADR-077).
"""

from __future__ import annotations

from concilium.domain.models.canonical import InstanciaRecurso, RecursoContrato
from concilium.domain.services.planning.week_sequence import enumerar_semanas


def project_ocupacao_semanal(instancia: InstanciaRecurso) -> dict[str, str]:
    """Projeta o status semana-a-semana de um slot: "prod" | "idle" | "off".

    Precedência estrutural, sem interpretar a convenção legada de
    `semana_mobilizacao`/`semana_desmobilizacao` (ADR-085): toda semana coberta por
    `segmentos_atividade` é "prod"; toda semana coberta por `segmentos_idle` (e não já
    "prod") é "idle"; o residual dentro de `[semana_entrada, semana_saida]` é "off".

    Retorna `{}` quando a instância não tem span de contrato definido.
    """
    if not instancia.semana_entrada or not instancia.semana_saida:
        return {}

    ocupacao: dict[str, str] = {}
    for seg in instancia.segmentos_atividade:
        for semana in enumerar_semanas(seg.semana_inicio, seg.semana_fim):
            ocupacao[semana] = "prod"
    for seg in instancia.segmentos_idle:
        for semana in enumerar_semanas(seg.semana_inicio, seg.semana_fim):
            ocupacao.setdefault(semana, "idle")
    for semana in enumerar_semanas(instancia.semana_entrada, instancia.semana_saida):
        ocupacao.setdefault(semana, "off")
    return ocupacao


def project_ocupacao_contrato_semanal(
    contrato: RecursoContrato, instancias: list[InstanciaRecurso]
) -> dict[str, dict[str, int]]:
    """Agrega `project_ocupacao_semanal` de todas as instâncias de um contrato.

    Retorna `{semana: {"prod": N, "idle": N, "off": N}}` — a soma dos três por semana
    é igual ao número de instâncias do contrato consideradas.
    """
    agregado: dict[str, dict[str, int]] = {}
    for inst in instancias:
        if inst.contrato_id != contrato.contrato_id:
            continue
        for semana, status in project_ocupacao_semanal(inst).items():
            bucket = agregado.setdefault(semana, {"prod": 0, "idle": 0, "off": 0})
            bucket[status] += 1
    return agregado
