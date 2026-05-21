"""Skill 01 — Praticabilidade.

Calcula o percentual produtivo mensal a partir de:
- Coordenadas geográficas do projeto
- Limiar de inviabilidade (mm/dia) do perfil ativo
- Regime de trabalho (dias por semana)

Lógica:
    para cada mês 01-12:
        consultar dados climáticos da região para ano de referência
        contar dias com precipitação >= limiar = dias_inviaveis
        dias_uteis_mes = média de dias úteis no mês conforme regime_trabalho
        percentual_produtivo[mês] = (dias_uteis_mes - dias_inviaveis_no_mes_uteis) / dias_uteis_mes

Para Fase 1A, usamos a aproximação:
    dias_inviaveis_uteis ≈ dias_inviaveis_total × (regime.dias_semana / 7)
"""

import calendar
from datetime import UTC, datetime
from typing import Any

from concilium.clients.openmeteo import DadosClimaticosMensais, OpenMeteoClient
from concilium.models.canonical import CanonicalModel, Praticabilidade, ValidacaoItem
from concilium.skills.escopo import SkillResult


def _dias_uteis_mes(ano: int, mes: int, dias_semana: int) -> float:
    """Média de dias úteis no mês conforme regime de trabalho."""
    total_dias = calendar.monthrange(ano, mes)[1]
    return total_dias * (dias_semana / 7)


def _calcular_percentual_produtivo(
    dados: DadosClimaticosMensais,
    limiar_mm: float,
    dias_semana: int,
) -> dict[str, float]:
    """Para cada mês, calcula percentual produtivo a partir de dias inviáveis."""
    threshold_key = f"{int(limiar_mm)}mm"
    if threshold_key not in {"5mm", "10mm", "20mm"}:
        # Aproximação: usa o threshold mais próximo
        threshold_key = "10mm"

    percentual: dict[str, float] = {}
    ano = dados.ano_referencia
    for mes_str, contagens in dados.dias_precipitacao_mensal.items():
        mes = int(mes_str)
        dias_inviaveis_total = contagens.get(threshold_key, 0)
        dias_inviaveis_uteis = dias_inviaveis_total * (dias_semana / 7)
        dias_uteis = _dias_uteis_mes(ano, mes, dias_semana)
        if dias_uteis <= 0:
            percentual[mes_str] = 0.0
            continue
        produtivo = max(0.0, (dias_uteis - dias_inviaveis_uteis) / dias_uteis)
        percentual[mes_str] = round(produtivo, 4)

    return percentual


def run_praticabilidade(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    perfil: dict[str, Any],
    client: OpenMeteoClient | None = None,
) -> SkillResult:
    """Popula seção 'praticabilidade' do canônico.

    inputs:
        ano_referencia: int (default: ano anterior ao atual)
    perfil:
        deve conter 'limiar_inviabilidade_mm' ou cair em default 10
    client:
        injetável para teste; se None, instancia OpenMeteoClient padrão
    """
    validacoes: list[ValidacaoItem] = []

    if canonical_in.projeto is None:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PRAT-PRECONDICAO",
                status="ERRO",
                mensagem="Praticabilidade requer canônico com seção 'projeto' populada",
            )
        )
        return SkillResult(canonical_in, validacoes)

    coords = canonical_in.projeto.coordenadas
    regime = canonical_in.projeto.regime_trabalho
    limiar = perfil.get("limiar_inviabilidade_mm", 10)
    ano_ref = inputs.get("ano_referencia", datetime.now(UTC).year - 1)

    cli = client or OpenMeteoClient()
    try:
        dados = cli.fetch_dados_anuais(coords.lat, coords.lng, ano_ref)
    except Exception as e:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PRAT-FONTE",
                status="ERRO",
                mensagem=f"Falha ao consultar fonte climática: {e}",
            )
        )
        return SkillResult(canonical_in, validacoes)

    percentual = _calcular_percentual_produtivo(dados, limiar, regime.dias_semana)

    # VAL-PRAT-01: percentuais entre 0 e 1
    fora_faixa = [(m, p) for m, p in percentual.items() if not (0 <= p <= 1)]
    if fora_faixa:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PRAT-01",
                status="ERRO",
                mensagem=f"Percentuais fora da faixa [0,1]: {fora_faixa}",
            )
        )
    else:
        validacoes.append(ValidacaoItem(codigo="VAL-PRAT-01", status="OK"))

    # VAL-PRAT-02: cobertura completa (12 meses)
    if len(percentual) != 12:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PRAT-02",
                status="ERRO",
                mensagem=f"Esperados 12 meses, recebidos {len(percentual)}",
            )
        )
    else:
        validacoes.append(ValidacaoItem(codigo="VAL-PRAT-02", status="OK"))

    # Atualiza canônico (modelo imutável: criamos novo via model_copy)
    novo = canonical_in.model_copy(
        update={
            "praticabilidade": Praticabilidade(
                fonte=dados.fonte,
                limiar_inviabilidade_mm=limiar,
                calculada_em=datetime.now(UTC),
                percentual_produtivo_mensal=percentual,
            )
        }
    )
    return SkillResult(novo, validacoes)
