"""Skill 04 — Cronograma (parte extraída de skill.py)."""

from __future__ import annotations

from datetime import date, timedelta
from math import isfinite
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
    from concilium.domain.services.financial.encargo_resolver import custo_ja_inclui_encargos

    custo_hora = 0.0
    for func in composicao.get("funcoes", []):
        fid = func.get("funcao_id") or ""
        n = float(func.get("num_pessoas", 1) or 1)  # planilha usa frações (0.5, 0.17)
        ins = insumos_lookup.get(fid)
        if not ins:
            continue
        pu = float(ins.get("preco_unitario", 0) or 0)
        unidade = str(ins.get("unidade", "mes")).lower()
        # ADR-097 D1: preco_unitario já all-in (metodo_custo_total) — não aplicar
        # taxa_encargos por cima, independente da unidade (h/hora ou mensal).
        # Fonte única de verdade (substitui o antigo texto livre "inclui encargos",
        # que só olhava "nota", nem "nota_encargos", e só para unidade h/hora).
        ja_com_encargos = custo_ja_inclui_encargos(ins.get("atributos_especificos") or {})
        if unidade in ("h", "hora"):
            # Taxa horária já em R$/h.
            encargos = 0.0 if ja_com_encargos else taxa_encargos
            custo_hora += n * pu * (1.0 + encargos)
        else:
            # Taxa mensal → converte para horária e aplica encargos
            taxa_hora = pu / horas_mes if horas_mes > 0 else 0.0
            encargos = 0.0 if ja_com_encargos else taxa_encargos
            custo_hora += n * taxa_hora * (1.0 + encargos)
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


def _custo_hora_equipamentos(composicao: dict, insumos_lookup: dict[str, dict], horas_mes: float) -> float:
    """Soma custo horário de equipamentos + combustível da composição (NEP-029 D2).

    ADR-132: ``preco_h_unitario`` na composição é override R$/h regime-independente.
    Insumos sem override: ``preco_unitario`` em R$/mês (÷ horas_mes) ou R$/h conforme ``unidade``.
    """
    custo_hora = 0.0
    diesel_ins = _resolve_diesel_insumo(insumos_lookup)

    for equip in composicao.get("equipamentos", []):
        eid = equip.get("equip_id") or ""
        n = float(equip.get("num_unidades", 1) or 1)
        ins = insumos_lookup.get(eid)
        preco_comp = equip.get("preco_h_unitario")
        if preco_comp is not None:
            # Override explícito em R$/h — bypass de regime
            custo_hora += n * float(preco_comp)
        elif ins:
            pu = float(ins.get("preco_unitario", 0) or 0)
            unidade = str(ins.get("unidade", "mes")).strip().lower()
            if unidade in ("h", "hora"):
                custo_hora += n * pu
            else:
                # R$/mês → R$/h via regime do projeto
                custo_hora += n * (pu / horas_mes) if horas_mes > 0 else n * pu
        custo_hora += _custo_hora_combustivel_equip(equip, ins, n, diesel_ins)

    return custo_hora


def _custo_hora_equipe(
    composicao: dict,
    insumos_lookup: dict[str, dict],
    horas_mes: float,
    taxa_encargos: float,
) -> float:
    """ Computa custo horário total da equipe a partir da composição padrão, sempre bottom-up.

    Fórmula (NEP-029 D2) — ponto único de normalização:
      custo_hora_mo  = Σ funcoes: n_pessoas × (preco_unit / horas_mes) × (1 + taxa_encargos)
                       preco_unit em R$/mês (unidade='mes', padrão) ou R$/h (unidade='h')
      custo_hora_eq  = Σ equips: n_unidades × (preco_unit / horas_mes)  [unidade='mes']
                       ou n_unidades × preco_h_unitario                  [override R$/h explc.]
      custo_hora_comb = Σ equips: n_unidades × consumo_L_h × preco_diesel
      total          = custo_hora_mo + custo_hora_eq + custo_hora_comb

    horas_mes vem do regime do projeto — custo horário é paramétrico.
    Diesel é buscado pelos códigos MA-DIESEL-S10, MA-DIESEL ou MA-DIESEL-ESCALA.
    """
    custo_hora_mo = _custo_hora_mao_de_obra(composicao, insumos_lookup, horas_mes, taxa_encargos)
    custo_hora_eq_comb = _custo_hora_equipamentos(composicao, insumos_lookup, horas_mes)
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
    P_original = float(prod.get("producao_horaria") or 0)

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
                    "producao_horaria ou precos_unitarios_sbdi precisa correção no catálogo."
                ),
            )
        )
        return  # não aplica P_canonico — preserva P_original

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

        custo_hora = _custo_hora_equipe(composicao, insumos_lookup, horas_mes, taxa_encargos)
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
        d = date.fromisocalendar(int(year_str), int(week_str), 1)
        month_key = f"{d.month:02d}"
        if month_key in prat_mensal:
            return prat_mensal[month_key]

    return 1.0


def _capacidade_semanal_por_frentes(
    producao_semanal_base: float,
    num_equipes: float,
    n_max: float,
    prod_item: dict[str, Any] | None = None,
) -> float:
    """Physical installed weekly capacity F(m)*H; no team-allocation loss.

    A catalog rate without a flow graph is explicitly interpreted as the
    rate **per independent front** (P10-B, pending calibration provenance #9).
    When a flow graph is provided, its capacities are authoritative in units
    of output per hour; shared bottlenecks are not replicated by m.
    """
    from concilium.domain.services.sinergia_equipe import (
        capacidade_efetiva_frentes,
        construir_producao_catalogo_para_sinergia,
        derivar_producao_horaria,
    )

    if producao_semanal_base < 0 or not isfinite(producao_semanal_base):
        raise ValueError("weekly productivity must be finite and nonnegative")
    if n_max <= 0:
        raise ValueError("maximum number of fronts must be positive")
    if num_equipes == 0:
        return 0.0

    graph_raw = (prod_item or {}).get("grafo_sinergia")
    if graph_raw:
        typed = construir_producao_catalogo_para_sinergia(prod_item or {})
        if typed is None or typed.grafo_sinergia is None:
            raise ValueError("invalid synergy graph; physical capacity cannot be certified")
        graph = typed.grafo_sinergia
        derived = derivar_producao_horaria(graph, typed.equipe)
        if derived.producao_horaria_derivada is None:
            raise ValueError("synergy graph has no productive physical capacity")
        # Work hours are recovered from the original weekly reference,
        # which is calibrated in its own catalog unit. The derived rate
        # is authoritative for F(m), including legacy equipment bottlenecks.
        catalog_rate = float((prod_item or {}).get("producao_horaria") or 0.0)
        if not isfinite(catalog_rate) or catalog_rate <= 0:
            raise ValueError("graph capacity requires positive catalog hourly reference")
        hours = producao_semanal_base / catalog_rate
        if graph.arestas_fluxo:
            # Explicit flow graph: source supply scales with mobilized
            # fronts, downstream shared resources do not.
            effective = capacidade_efetiva_frentes(
                graph, num_equipes, n_max, derived.producao_horaria_derivada
            )
        else:
            # Legacy element-capacity graph represents the composition
            # of ONE front; independently replicated fronts add capacity.
            # It must not be dropped in favour of an uncalibrated catalog P.
            effective = capacidade_efetiva_frentes(
                None, num_equipes, n_max, derived.producao_horaria_derivada * n_max
            )
        return hours * effective

    if producao_semanal_base == 0:
        raise ValueError("active fronts require positive declared productivity")
    return capacidade_efetiva_frentes(
        None, num_equipes, n_max, producao_semanal_base * n_max
    )


def _build_dist_cell(
    producao_semanal_base: float,
    num_eq: float,
    n_max: int,
    fator_clima: float,
    fator_calendario: float,
    quantitativo: float,
    qtd_acumulada: float,
    M_max: float = 1.0,
    fator_jornada: float = 1.0,
    capacidade_fisica_semanal: float | None = None,
) -> DistribuicaoSemanal:
    """Build a weekly physical-capacity cell without allocation penalties.

    The nominal capacity q_max_celula represents F_i(m_ij)*H for the fronts
    **actually mobilized**, never an envelope based on m_i^max. The reduced
    physical output is weather/calendar/journey; a partial final week is a
    separately visible closure fraction phi, not a further productivity loss.
    Legacy eta_s and eta_w remain 1.0 to prevent downstream double application.
    """
    import math

    if capacidade_fisica_semanal is None:
        capacidade_fisica_semanal = producao_semanal_base * num_eq
    if not math.isfinite(capacidade_fisica_semanal) or capacidade_fisica_semanal < 0:
        raise ValueError("invalid installed weekly capacity")
    if not (0.0 <= fator_clima <= 1.0 and 0.0 <= fator_calendario <= 1.0
            and 0.0 <= fator_jornada <= 1.0):
        raise ValueError("exogenous physical factors must lie in [0,1]")
    if not math.isfinite(M_max) or M_max <= 0:
        raise ValueError("calibrated management multiplier must be positive")
    if num_eq < 0 or n_max <= 0:
        raise ValueError("invalid number of fronts")

    q_max = capacidade_fisica_semanal
    eta_p = fator_clima * fator_calendario * fator_jornada
    capacidade_real = q_max * eta_p
    qtd_remanescente = max(0.0, quantitativo - qtd_acumulada)
    qtd_executada = min(capacidade_real, qtd_remanescente)
    fracao_fechamento = (qtd_executada / capacidade_real) if capacidade_real > 0 else 0.0
    # An externally calibrated management loss must be its own versioned
    # physical input; M_max does not multiply the capacity again here.
    eta_total = eta_p  # closure is NOT an efficiency loss
    perda_exogena = max(0.0, q_max - capacidade_real)
    qtd_acumulada_nova = qtd_acumulada + qtd_executada
    pct = qtd_acumulada_nova / quantitativo if quantitativo > 0 else 0.0
    return DistribuicaoSemanal(
        num_equipes=num_eq,
        qtd_executada=qtd_executada,
        qtd_acumulada=qtd_acumulada_nova,
        pct=round(pct, 4),
        eficiencia=1.0,  # control efficiency unknown; neutral in a planned schedule
        fator_clima=round(fator_clima, 4),
        fator_calendario=round(fator_calendario, 4),
        fator_jornada=round(fator_jornada, 4),
        fator_total=round(eta_total, 4),
        eta_s=1.0,  # neutral legacy field; not a loss
        eta_p=round(eta_p, 4),
        eta_w=1.0,  # neutral legacy control factor; phi has its own field
        fracao_fechamento=fracao_fechamento,
        q_max_celula=q_max,
        perda_fisica=perda_exogena,
    )

__all__ = [
    "_apply_producao_canonico",
    "_build_cpu_lookup",
    "_build_dist_cell",
    "_capacidade_semanal_por_frentes",
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
