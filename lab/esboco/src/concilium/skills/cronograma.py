"""Skill 02 — Cronograma.

Distribui a execução de cada item da EAP ao longo dos meses do prazo, considerando:
- Produção horária da CPU correspondente
- Praticabilidade mensal (calculada pela skill 01)
- Regime de trabalho (dias por semana, horas por dia)
- Número de equipes alocadas mês a mês (input do planejador)

A skill NÃO decide a alocação — apenas calcula a produção resultante. Cabe ao planejador
iterar até atingir 100% de execução no prazo.

Inputs (no dict 'inputs'):
    num_equipes_por_item: dict[str, dict[str, int]]
        Para cada item_id, um mapa {AAAA-MM: num_equipes}.
        Meses não listados assumem 0 equipes.
"""

import calendar
from datetime import date
from typing import Any

from concilium.models.canonical import (
    CanonicalModel,
    Cronograma,
    DistribuicaoMensal,
    ValidacaoItem,
)
from concilium.skills.escopo import SkillResult


def _meses_entre(inicio: date, fim: date) -> list[str]:
    """Lista de chaves AAAA-MM entre duas datas (inclusivo)."""
    meses = []
    ano, mes = inicio.year, inicio.month
    while (ano, mes) <= (fim.year, fim.month):
        meses.append(f"{ano:04d}-{mes:02d}")
        mes += 1
        if mes == 13:
            mes = 1
            ano += 1
    return meses


def _dias_uteis_no_mes(ano: int, mes: int, dias_semana: int) -> float:
    """Dias úteis no mês conforme regime de trabalho (média)."""
    total_dias = calendar.monthrange(ano, mes)[1]
    return total_dias * (dias_semana / 7)


def _build_cpu_lookup(catalogo: dict[str, Any]) -> dict[str, dict]:
    """Indexa CPUs do catálogo por código."""
    return {c["codigo"]: c for c in catalogo.get("cpus", [])}


def run_cronograma(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    catalogo: dict[str, Any],
) -> SkillResult:
    """Popula seção 'cronograma' do canônico.

    Pré-condições:
        - Seção projeto populada (regime_trabalho, datas)
        - Seção eap populada
        - Seção praticabilidade populada (skill 01)

    inputs deve conter:
        num_equipes_por_item: dict[str, dict[str, int]]
            Ex.: {"eap-01": {"2026-06": 1, "2026-07": 2}, ...}
            Itens ou meses ausentes assumem 0.
    """
    validacoes: list[ValidacaoItem] = []

    if canonical_in.praticabilidade is None:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CRON-PRECONDICAO",
                status="ERRO",
                mensagem="Cronograma requer praticabilidade populada (skill 01)",
            )
        )
        return SkillResult(canonical_in, validacoes)

    if not canonical_in.eap:
        validacoes.append(
            ValidacaoItem(codigo="VAL-CRON-PRECONDICAO", status="ERRO", mensagem="EAP vazia")
        )
        return SkillResult(canonical_in, validacoes)

    cpu_lookup = _build_cpu_lookup(catalogo)
    regime = canonical_in.projeto.regime_trabalho
    horas_dia = regime.horas_dia
    prat_mensal = canonical_in.praticabilidade.percentual_produtivo_mensal

    meses_obra = _meses_entre(canonical_in.projeto.data_inicio, canonical_in.projeto.data_termino)
    num_equipes_por_item = inputs.get("num_equipes_por_item", {})

    cronograma_out: list[Cronograma] = []
    erros_completude: list[tuple[str, float]] = []
    erros_vazios: list[str] = []

    for item in canonical_in.eap:
        cpu = cpu_lookup.get(item.cpu_id)
        if cpu is None:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-EAP-01",
                    status="ERRO",
                    mensagem=f"CPU {item.cpu_id} (item {item.item_id}) não existe no catálogo",
                )
            )
            continue

        producao_diaria = cpu["producao_horaria"] * horas_dia
        equipes_meses = num_equipes_por_item.get(item.item_id, {})

        distribuicao: dict[str, DistribuicaoMensal] = {}
        qtd_acumulada = 0.0

        for mes_ano in meses_obra:
            num_eq = equipes_meses.get(mes_ano, 0)
            if num_eq < 0:
                num_eq = 0

            mes_num = mes_ano[5:7]  # "AAAA-MM" → "MM"
            ano_num = int(mes_ano[0:4])
            mes_int = int(mes_num)
            pct_produtivo = prat_mensal.get(mes_num, 0.0)
            dias_uteis = _dias_uteis_no_mes(ano_num, mes_int, regime.dias_semana)

            qtd_executada = producao_diaria * dias_uteis * pct_produtivo * num_eq

            # Não pode ultrapassar o quantitativo total
            qtd_remanescente = item.quantitativo - qtd_acumulada
            if qtd_executada > qtd_remanescente:
                qtd_executada = max(0.0, qtd_remanescente)

            qtd_acumulada += qtd_executada
            pct = qtd_acumulada / item.quantitativo if item.quantitativo > 0 else 0.0

            distribuicao[mes_ano] = DistribuicaoMensal(
                num_equipes=num_eq,
                qtd_executada=round(qtd_executada, 2),
                qtd_acumulada=round(qtd_acumulada, 2),
                pct=round(pct, 4),
            )

        pct_completude = qtd_acumulada / item.quantitativo if item.quantitativo > 0 else 0.0
        cronograma_out.append(
            Cronograma(
                item_id=item.item_id,
                dias_trabalhados_semana=regime.dias_semana,
                distribuicao_mensal=distribuicao,
                pct_completude=round(pct_completude, 4),
            )
        )

        # VAL-CRON-01: completude
        if pct_completude < 0.999:
            erros_completude.append((item.item_id, pct_completude))

        # VAL-CRON-02: detectar buraco no meio da execução (mês com 0 equipes entre meses produtivos)
        meses_produtivos = [m for m, d in distribuicao.items() if d.num_equipes > 0]
        if len(meses_produtivos) >= 2:
            inicio_idx = meses_obra.index(meses_produtivos[0])
            fim_idx = meses_obra.index(meses_produtivos[-1])
            for i in range(inicio_idx + 1, fim_idx):
                m = meses_obra[i]
                if distribuicao[m].num_equipes == 0:
                    erros_vazios.append(f"{item.item_id}@{m}")

    # Consolidar validações
    if erros_completude:
        msgs = ", ".join(f"{iid} ({pct*100:.1f}%)" for iid, pct in erros_completude)
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CRON-01",
                status="ERRO",
                mensagem=f"Itens não atingiram 100% no prazo: {msgs}",
            )
        )
    else:
        validacoes.append(ValidacaoItem(codigo="VAL-CRON-01", status="OK"))

    if erros_vazios:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CRON-02",
                status="ERRO",
                mensagem=f"Buracos no cronograma: {', '.join(erros_vazios)}",
            )
        )
    else:
        validacoes.append(ValidacaoItem(codigo="VAL-CRON-02", status="OK"))

    novo = canonical_in.model_copy(update={"cronograma": cronograma_out})
    return SkillResult(novo, validacoes)
