"""ADR-153 F1 — Anotação declarativa de identidade física em segmentos de InstanciaRecurso.

Permite registrar, após o solve, qual ativo físico (matrícula/placa) de fato ocupou
um segmento de um slot de pool — sem que o solver ou a atribuição de slots (ADR-077)
tenham qualquer noção de identidade física. Puramente rótulo declarado externamente,
no mesmo espírito de função pura e aditiva de `pool_timelapse.py` (ADR-152).

Não resolve (fora de escopo desta fase — ver ADR-153 D4):
  - individualização de custo real por pessoa/ativo (a cadeia de custo permanece
    agregada por função/tipo);
  - garantir continuidade do mesmo ativo físico entre segmentos no solver
    (`add_cumulative` permanece inalterado).
"""

from __future__ import annotations

from concilium.domain.models.canonical import InstanciaRecurso


def atribuir_identidade_fisica_segmentos(
    instancias: list[InstanciaRecurso],
    atribuicoes: dict[tuple[str, str], str],
) -> list[InstanciaRecurso]:
    """Enriquece `segmentos_atividade` com `identidade_fisica_id` a partir de uma
    declaração externa `{(instancia_id, semana_inicio): identidade_fisica_id}`.

    Não modifica as instâncias originais — retorna novas instâncias. Chaves de
    `atribuicoes` sem correspondência em nenhum segmento são ignoradas
    silenciosamente (a declaração pode se referir a uma rodada de schedule diferente,
    ou a um slot sem atividade atribuída nesta rodada).
    """
    def _enrich_segmento(instancia: InstanciaRecurso, seg):
        chave = (instancia.instancia_id, seg.semana_inicio)
        if chave not in atribuicoes:
            return seg
        return seg.model_copy(update={"identidade_fisica_id": atribuicoes[chave]})

    return [
        instancia.model_copy(
            update={
                "segmentos_atividade": [
                    _enrich_segmento(instancia, seg) for seg in instancia.segmentos_atividade
                ]
            }
        )
        for instancia in instancias
    ]
