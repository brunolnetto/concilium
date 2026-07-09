"""Skill 04 — Cronograma (parte extraída de skill.py)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from concilium.domain.models.canonical import (
    DistribuicaoSemanal,
    ValidacaoItem,
)


def _iso_week_key(d: date) -> str:
    """Retorna a chave de semana ISO 'AAAA-Www' para uma data."""
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _week_offset(semana_key: str, semanas_obra: list[str], data_inicio: date) -> int:
    """Offset (0-based) de uma chave ISO-week relativo a data_inicio.

    Usa o índice em semanas_obra quando presente; caso a semana exceda o prazo
    nominal (cronograma com makespan > deadline), calcula via aritmética de data
    a partir da segunda-feira da semana ISO. Tolerante a overflow.
    """
    try:
        return semanas_obra.index(semana_key)
    except ValueError:
        year_str, week_str = semana_key.split("-W", 1)
        monday = date.fromisocalendar(int(year_str), int(week_str), 1)
        inicio_monday = data_inicio - timedelta(days=data_inicio.weekday())
        return max(0, (monday - inicio_monday).days // 7)


def _semanas_entre(inicio: date, fim: date) -> list[str]:
    """Lista de chaves 'AAAA-Www' das semanas ISO que cobrem o intervalo [inicio, fim]."""
    semanas: list[str] = []
    seen: set[str] = set()
    d = inicio
    while d <= fim:
        key = _iso_week_key(d)
        if key not in seen:
            seen.add(key)
            semanas.append(key)
        d += timedelta(days=1)
    return semanas


def _build_cpu_lookup(catalogo: dict[str, Any]) -> dict[str, dict]:
    """Indexa CPUs do catálogo por código."""
    return {c["codigo"]: c for c in catalogo.get("cpus", [])}


def _build_producao_lookup(catalogo: dict[str, Any]) -> dict[str, dict]:
    """Indexa artefatos de produtividade por id (ADR-007)."""
    # Suporta tanto 'producoes' (ADR) quanto 'produtividades' (implementação)
    lista = catalogo.get("produtividades", []) or catalogo.get("producoes", [])
    return {p["id"]: p for p in lista}


def _build_insumos_lookup(catalogo: dict[str, Any]) -> dict[str, dict]:
    """Indexa insumos do catálogo por código."""
    return {ins["codigo"]: ins for ins in catalogo.get("insumos", []) if ins.get("codigo")}


def _custo_hora_mao_de_obra(
    composicao: dict, insumos_lookup: dict[str, dict], horas_mes: float, taxa_encargos: float
) -> float:
    """Soma custo horário de mão de obra da composição (NEP-029 D2, termo custo_hora_mo)."""
    custo_hora = 0.0
    for func in composicao.get("funcoes", []):
        fid = func.get("funcao_id") or ""
        n = float(func.get("num_pessoas", 1) or 1)  # planilha usa frações (0.5, 0.17)
        ins = insumos_lookup.get(fid)
        if not ins:
            continue
        pu = float(ins.get("preco_unitario", 0) or 0)
        unidade = str(ins.get("unidade", "mes")).lower()
        if unidade in ("h", "hora"):
            # Taxa horária já em R$/h.
            # Se o insumo indica que encargos já estão incluídos (convenção AGIS-FN-*),
            # não aplicar taxa_encargos adicionalmente.
            nota = str((ins.get("atributos_especificos") or {}).get("nota", "")).lower()
            ja_com_encargos = "inclui encargos" in nota  # substring sem acentos
            encargos = 0.0 if ja_com_encargos else taxa_encargos
            custo_hora += n * pu * (1.0 + encargos)
        else:
            # Taxa mensal → converte para horária e aplica encargos
            taxa_hora = pu / horas_mes if horas_mes > 0 else 0.0
            custo_hora += n * taxa_hora * (1.0 + taxa_encargos)
    return custo_hora


def _resolve_diesel_insumo(insumos_lookup: dict[str, dict]) -> dict | None:
    """Resolve o insumo de diesel pelos códigos aceitos, em ordem de preferência."""
    for cod in ("MA-DIESEL-S10", "MA-DIESEL", "MA-DIESEL-ESCALA"):
        if cod in insumos_lookup:
            return insumos_lookup[cod]
    return None


def _custo_hora_combustivel_equip(equip: dict, ins: dict | None, n: float, diesel_ins: dict | None) -> float:
    """Custo horário de combustível de um equipamento (NEP-029 D2, termo custo_hora_comb)."""
    # Consumo em L/h pode vir do registro de producao (dois nomes:
    # consumo_litros_hora_estimado ou consumo_litros_hora) ou do insumo de equip.
    consumo = float(equip.get("consumo_litros_hora_estimado") or equip.get("consumo_litros_hora") or 0)
    if consumo == 0 and ins:
        consumo = float((ins.get("atributos_especificos") or {}).get("consumo_litros_hora", 0) or 0)
    if consumo <= 0 or not diesel_ins:
        return 0.0
    # Usa preco_unitario (referência da planilha, ex: 6,99 R$/L).
    # Preço regionalizado (SICRO) é referência de mercado regional, não o
    # preço contratual — não usar para calibração de produtividade.
    preco_diesel = float(diesel_ins.get("preco_unitario", 0) or 0)
    return n * consumo * preco_diesel


def _custo_hora_equipamentos(composicao: dict, insumos_lookup: dict[str, dict]) -> float:
    """Soma custo horário de equipamentos + combustível da composição (NEP-029 D2,
    termos custo_hora_eq + custo_hora_comb)."""
    custo_hora = 0.0
    diesel_ins = _resolve_diesel_insumo(insumos_lookup)

    for equip in composicao.get("equipamentos", []):
        eid = equip.get("equip_id") or ""
        n = float(equip.get("num_unidades", 1) or 1)  # planilha usa frações (0.17)
        ins = insumos_lookup.get(eid)
        if ins:
            pu = float(ins.get("preco_unitario", 0) or 0)
            custo_hora += n * pu  # equipment insumos are in R$/h
        custo_hora += _custo_hora_combustivel_equip(equip, ins, n, diesel_ins)

    return custo_hora


def _custo_hora_equipe(
    composicao: dict,
    insumos_lookup: dict[str, dict],
    horas_mes: float,
    taxa_encargos: float,
    custo_hora_referencia: float | None = None,
) -> float:
    """Computa custo horário total da equipe a partir da composição padrão.

    Quando ``custo_hora_referencia`` está disponível (planilha AGIS 2026-05), usa-o
    diretamente sem precisar de lookup de insumos — elimina dependência de catálogo e
    garante identidade exata P_canonico = C (produção da planilha).

    Fórmula (NEP-029 D2):
      custo_hora_mo  = Σ funcoes: n_pessoas × (preco_unit / horas_mes) × (1 + taxa_encargos)
                       onde preco_unit está em R$/mês quando unidade='mes',
                            ou em R$/h quando unidade='h'
      custo_hora_eq  = Σ equips: n_unidades × preco_hora_equip       (unidade='h')
      custo_hora_comb = Σ equips: n_unidades × consumo_L_h × preco_diesel
      total          = custo_hora_mo + custo_hora_eq + custo_hora_comb

    Diesel é buscado pelos códigos MA-DIESEL-S10, MA-DIESEL ou MA-DIESEL-ESCALA.
    Retorna 0.0 se a composição estiver incompleta (insumos não encontrados).
    """
    if custo_hora_referencia and custo_hora_referencia > 0:
        return float(custo_hora_referencia)
    custo_hora_mo = _custo_hora_mao_de_obra(composicao, insumos_lookup, horas_mes, taxa_encargos)
    custo_hora_eq_comb = _custo_hora_equipamentos(composicao, insumos_lookup)
    return custo_hora_mo + custo_hora_eq_comb


def _resolve_cpu_producao_context(cpu: dict, producao_lookup: dict[str, dict]) -> tuple[float, dict, dict] | None:
    """Resolve (pu_sbdi, prod, composicao) para a CPU, ou None se deve ser pulada."""
    pu_sbdi = float((cpu.get("precos_unitarios_sbdi") or {}).get("total") or 0)
    if pu_sbdi <= 0:
        return None

    prod_id = cpu.get("producao_id_ref") or ""
    prod = producao_lookup.get(prod_id)
    if not prod:
        return None

    # composicao_padrao_equipe está no producao record (ADR-053)
    composicao = prod.get("composicao_padrao_equipe") or {}
    if not composicao:
        return None

    return pu_sbdi, prod, composicao


def _apply_producao_canonico(
    cpu_id: str,
    pu_sbdi: float,
    prod: dict,
    custo_hora: float,
    validacoes: list,
) -> None:
    """Deriva P_canonico, aplica a guarda de ratio e grava/valida o resultado em `prod`."""
    P_canonico = custo_hora / pu_sbdi
    P_original = float(prod.get("valor_horario") or prod.get("producao_horaria") or 0)

    ratio = P_canonico / P_original if P_original > 0 else None

    # Guarda de ratio: só aplicar P_canonico quando a discrepância é calibração
    # (≤50% de diferença). Discrepâncias acima disso indicam dado de catálogo
    # inconsistente (e.g., valor_horario padrão copiado incorretamente) — sinalizar
    # como VAL-PROD-INCONSISTENCIA e preservar P_original para não quebrar o scheduler.
    _RATIO_MIN, _RATIO_MAX = 0.5, 2.0
    if ratio is not None and not (_RATIO_MIN <= ratio <= _RATIO_MAX):
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PROD-INCONSISTENCIA",
                status="AVISO",
                mensagem=(
                    f"CPU {cpu_id}: ratio P_can/P_orig={ratio:.3f} fora do intervalo aceitável "
                    f"[{_RATIO_MIN},{_RATIO_MAX}]. "
                    f"P_canonico={P_canonico:.2f} vs P_original={P_original:.2f}. "
                    f"PU_sbdi={pu_sbdi:.4f} implica custo={custo_hora:.1f} R$/h → "
                    "valor_horario ou precos_unitarios_sbdi precisa correção no catálogo."
                ),
            )
        )
        return  # não aplica P_canonico — preserva P_original

    prod["valor_horario_canonico"] = P_canonico

    ratio_txt = f" (ratio={ratio:.3f})" if ratio else ""
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-PROD-CANONICO",
            status="OK",
            mensagem=(
                f"CPU {cpu_id}: P_canonico={P_canonico:.2f} "
                f"[custo_hora={custo_hora:.2f}/PU_sbdi={pu_sbdi:.4f}]{ratio_txt}. "
                "fe_nec → 1/η_p (resíduo de base eliminado)."
            ),
        )
    )


def _enrich_producao_canonico(
    cpu_lookup: dict[str, dict],
    producao_lookup: dict[str, dict],
    insumos_lookup: dict[str, dict],
    horas_mes: float,
    taxa_encargos: float,
    validacoes: list,
) -> None:
    """NEP-029 D2: enriquece producao_lookup com valor_horario_canonico.

    Para cada CPU que possui precos_unitarios_sbdi.total > 0, deriva a
    produtividade canônica P_canonico = custo_hora_equipe / PU_sbdi de modo
    que P_engine = P_catalog por construção:

        custo_direto_engine = custo_hora × Q / P_canonico = PU_sbdi × Q

    O valor é gravado em producao_lookup[prod_id]['valor_horario_canonico'] e
    _resolve_productivity o prefere sobre 'valor_horario'. Isso garante que
    fe_nec = 1/η_p (apenas clima), eliminando o resíduo de mismatch de base.

    Emite VAL-PROD-CANONICO por CPU reportando o ratio P_canonico/P_original
    para rastreabilidade.
    """
    for cpu in cpu_lookup.values():
        cpu_id = cpu.get("codigo") or "?"
        ctx = _resolve_cpu_producao_context(cpu, producao_lookup)
        if ctx is None:
            continue
        pu_sbdi, prod, composicao = ctx

        # Prioriza o custo horário de referência da planilha (gravado no registro de producao)
        # — zero dependência de lookup de insumos, identidade exata P_canonico = C.
        custo_hora_ref = prod.get("custo_hora_total_referencia")
        custo_hora = _custo_hora_equipe(
            composicao,
            insumos_lookup,
            horas_mes,
            taxa_encargos,
            custo_hora_referencia=custo_hora_ref,
        )
        if custo_hora <= 0:
            continue

        _apply_producao_canonico(cpu_id, pu_sbdi, prod, custo_hora, validacoes)


def _lookup_eficiencia(
    semana_key: str,
    prat_semanal: dict[str, float],
    prat_mensal: dict[str, float],
) -> float:
    """Busca eficiência para a semana. Fallback: média mensal do mês correspondente."""
    if prat_semanal and semana_key in prat_semanal:
        return prat_semanal[semana_key]

    if prat_mensal:
        year_str, week_str = semana_key.split("-W")
        week_num = int(week_str)
        month_num = max(1, min(12, (week_num - 1) // 4 + 1))
        month_key = f"{month_num:02d}"
        if month_key in prat_mensal:
            return prat_mensal[month_key]

    return 1.0


def _build_dist_cell(
    producao_semanal_base: float,
    num_eq: int,
    n_max: int,
    fator_clima: float,
    fator_calendario: float,
    quantitativo: float,
    qtd_acumulada: float,
    M_max: float = 1.0,
) -> DistribuicaoSemanal:
    """Monta uma célula semanal com decomposição causal completa (NEP-035).

    Decomposição η = η_s · η_p · η_w onde:
      η_s  = n_j / n_max                  (alocação — fração da força máxima planejada)
      η_p  = fator_clima × fator_calendario (praticabilidade)
      η_w  = m_ij / M_max                  (gestão; M_max=1.0 até calibração)
      η    = η_s · η_p · η_w = fator_total

    q_max_celula = producao_semanal_base × n_max × M_max  (capacidade teórica semanal)
    perda_fisica = q_max_celula × η_s - q_executada        (produção perdida em unidades físicas)

    eficiencia = η_w = m_ij/M_max = utilização (≠ praticabilidade; corrige ADR-082-cons)
    """
    n_max_safe = max(1, n_max)
    n_eq_safe = max(0, num_eq)
    praticabilidade = fator_clima * fator_calendario
    eta_s = min(1.0, n_eq_safe / n_max_safe)
    eta_p = praticabilidade
    q_max = producao_semanal_base * n_max_safe * M_max
    capacidade_real = q_max * eta_s * eta_p
    qtd_remanescente = max(0.0, quantitativo - qtd_acumulada)
    qtd_executada = min(capacidade_real, qtd_remanescente)
    eta_w = (qtd_executada / (capacidade_real * M_max)) if capacidade_real > 0 else 0.0
    eta_w = min(1.0, eta_w)
    eta_total = eta_s * eta_p * eta_w
    perda = max(0.0, q_max - qtd_executada)
    qtd_acumulada_nova = qtd_acumulada + qtd_executada
    pct = qtd_acumulada_nova / quantitativo if quantitativo > 0 else 0.0
    return DistribuicaoSemanal(
        num_equipes=n_eq_safe,
        qtd_executada=round(qtd_executada, 2),
        qtd_acumulada=round(qtd_acumulada_nova, 2),
        pct=round(pct, 4),
        eficiencia=round(eta_w, 4),
        fator_clima=round(fator_clima, 4),
        fator_calendario=round(fator_calendario, 4),
        fator_total=round(eta_total, 4),
        eta_s=round(eta_s, 4),
        eta_p=round(eta_p, 4),
        eta_w=round(eta_w, 4),
        q_max_celula=round(q_max, 2),
        perda_fisica=round(perda, 2),
    )



__all__ = [
    "_apply_producao_canonico",
    "_build_cpu_lookup",
    "_build_dist_cell",
    "_build_insumos_lookup",
    "_build_producao_lookup",
    "_custo_hora_combustivel_equip",
    "_custo_hora_equipamentos",
    "_custo_hora_equipe",
    "_custo_hora_mao_de_obra",
    "_enrich_producao_canonico",
    "_iso_week_key",
    "_lookup_eficiencia",
    "_resolve_cpu_producao_context",
    "_resolve_diesel_insumo",
    "_semanas_entre",
    "_week_offset",
]
