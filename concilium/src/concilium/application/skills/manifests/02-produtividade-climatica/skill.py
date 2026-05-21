"""Skill 01 — Praticabilidade.

Calcula o percentual produtivo semanal (e mensal, retrocompat) a partir de:
- Coordenadas geográficas do projeto
- Limiar de inviabilidade (mm/dia) do perfil ativo
- Regime de trabalho (dias por semana)

Lógica principal (semanal):
    para cada semana ISO "AAAA-Www" encontrada nos dados climáticos:
        dias_uteis_semana = regime.dias_semana  (semana padrão tem 7 dias)
        dias_inviaveis_semana = dias com precipitação >= limiar naquela semana
        dias_inviaveis_uteis ≈ dias_inviaveis_semana × (dias_semana / 7)
        percentual_produtivo_semana = max(0, (dias_uteis_semana - dias_inviaveis_uteis) / dias_uteis_semana)

Para projetos que se estendem além do ano de referência, a skill extrapola usando
a média do mês ISO correspondente como fallback.
"""

import calendar
from datetime import UTC, datetime
from typing import Any

from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import CanonicalModel, Praticabilidade, ValidacaoItem
from concilium.infrastructure.clients.openmeteo import DadosClimaticosMensais, OpenMeteoClient


def _dias_uteis_mes(ano: int, mes: int, dias_semana: int) -> float:
    """Média de dias úteis no mês conforme regime de trabalho."""
    total_dias = calendar.monthrange(ano, mes)[1]
    return total_dias * (dias_semana / 7)


def _calcular_percentual_produtivo_semanal(
    dados: DadosClimaticosMensais,
    limiar_mm: float,
    dias_semana: int,
) -> dict[str, float]:
    """Para cada semana ISO nos dados, calcula percentual produtivo.

    Retorna dict com chave "AAAA-Www" (ex. "2024-W23") -> fração [0,1].
    """
    threshold_key = f"{int(limiar_mm)}mm"
    if threshold_key not in {"5mm", "10mm", "20mm"}:
        threshold_key = "10mm"

    percentual: dict[str, float] = {}

    for semana_key, contagens in dados.dias_precipitacao_semanal.items():
        dias_inviaveis_total = contagens.get(threshold_key, 0)
        # Aproximação: apenas dias úteis são afetados proporcionalmente
        dias_inviaveis_uteis = dias_inviaveis_total * (dias_semana / 7)
        # Dias úteis esperados numa semana com o regime dado
        dias_uteis = dias_semana
        if dias_uteis <= 0:
            percentual[semana_key] = 0.0
            continue
        produtivo = max(0.0, (dias_uteis - dias_inviaveis_uteis) / dias_uteis)
        percentual[semana_key] = round(produtivo, 4)

    return percentual


def _calcular_percentual_produtivo_mensal(
    dados: DadosClimaticosMensais,
    limiar_mm: float,
    dias_semana: int,
) -> dict[str, float]:
    """Para cada mês, calcula percentual produtivo (mantido para retrocompat)."""
    threshold_key = f"{int(limiar_mm)}mm"
    if threshold_key not in {"5mm", "10mm", "20mm"}:
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


# Retrocompat alias
_calcular_percentual_produtivo = _calcular_percentual_produtivo_mensal


def run_produtividade_climatica(
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

    percentual_semanal = _calcular_percentual_produtivo_semanal(dados, limiar, regime.dias_semana)
    percentual_mensal = _calcular_percentual_produtivo_mensal(dados, limiar, regime.dias_semana)

    # VAL-PRAT-01: percentuais entre 0 e 1 (semanal)
    fora_faixa = [(k, p) for k, p in percentual_semanal.items() if not (0 <= p <= 1)]
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

    # VAL-PRAT-02: cobertura mínima — pelo menos 1 semana de dados
    if len(percentual_semanal) == 0:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PRAT-02",
                status="ERRO",
                mensagem="Nenhuma semana com dados climáticos encontrada",
            )
        )
    else:
        validacoes.append(ValidacaoItem(codigo="VAL-PRAT-02", status="OK"))

    # VAL-PRAT-04: variabilidade sazonal — todas as semanas iguais indica dado suspeito
    valores = list(percentual_semanal.values())
    if len(valores) >= 4 and len(set(valores)) == 1:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PRAT-04",
                status="AVISO",
                mensagem=(
                    f"Variabilidade sazonal nula — todas as semanas com "
                    f"percentual_produtivo={valores[0]:.4f}. "
                    "Verifique consistência dos dados climáticos."
                ),
            )
        )

    # Atualiza canônico (modelo imutável: criamos novo via model_copy)
    novo = canonical_in.model_copy(
        update={
            "praticabilidade": Praticabilidade(
                fonte=dados.fonte,
                limiar_inviabilidade_mm=limiar,
                calculada_em=datetime.now(UTC),
                percentual_produtivo_semanal=percentual_semanal,
                percentual_produtivo_mensal=percentual_mensal,
            )
        }
    )
    return SkillResult(novo, validacoes)
