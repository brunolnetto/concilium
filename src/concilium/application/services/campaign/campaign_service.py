"""ADR-070 — Campaign service: grid generation, evaluation, Pareto, shortlist curation."""

from __future__ import annotations

import concurrent.futures
import copy
import hashlib
import itertools
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from concilium.domain.models.campaign.campaign import TendenciaMarginal

from concilium.domain.models.campaign.campaign import (
    CampaignBundleCube,
    CampaignOutputBundle,
    CampaignStatus,
    CelulaAnalitica,
    CenarioAvaliado,
    CenarioRankeado,
    ClassificacaoEF,
    ClassificacaoO,
    CuboDimensao,
    FaceAnalitica,
    GoResearchCampaignBundle,
    JustificativaCenario,
    ParametroSweep,
    PerfilExpectativas,
    ResumoMarginal,
    VetorEspacoEF,
    VetorEspacoO,
    ViabilidadeStatus,
)

# ---------------------------------------------------------------------------
# F1 — Grid generation
# ---------------------------------------------------------------------------


_PER_ITEM_PREFIX = "_per_item_:"
_CPU_ALT_PREFIX = "_cpu_alt_:"


def _expand_sweep_dims(bundle: GoResearchCampaignBundle) -> tuple[list[str], list[list]]:
    """Expande ParametroSweep em (keys, value_lists) prontos para itertools.product.

    - scope="global":         1 dimensão com k valores (comportamento original).
    - scope="per_item":       len(item_ids) dimensões, cada uma com k valores.
                              Chave interna: "_per_item_:{campo}:{item_id}"
    - scope="cpu_alternativo": idem, mas chave interna: "_cpu_alt_:{campo}:{item_id}"
    """
    keys: list[str] = []
    value_lists: list[list] = []

    for s in bundle.sweep:
        if s.scope in ("per_item", "cpu_alternativo") and s.item_ids:
            prefix = _PER_ITEM_PREFIX if s.scope == "per_item" else _CPU_ALT_PREFIX
            for iid in s.item_ids:
                keys.append(f"{prefix}{s.campo}:{iid}")
                value_lists.append(s.valores)
        else:
            # global (e cpu_alternativo sem item_ids — trata como global)
            keys.append(s.campo)
            value_lists.append(s.valores)

    return keys, value_lists


def gerar_grid(bundle: GoResearchCampaignBundle) -> list[tuple[dict, dict]]:
    """Returns list of (spec_variant, parametros_variados). Applies sweep.

    Suporta scope="global" (padrão), "per_item" e "cpu_alternativo".
    Para per_item e cpu_alternativo, cada item_id é uma dimensão independente
    → cardinalidade = k^len(item_ids) para aquele sweep.
    """
    if not bundle.sweep:
        return [(bundle.base_spec, {})]

    keys, value_lists = _expand_sweep_dims(bundle)

    results = []
    for combo in itertools.product(*value_lists):
        variados = dict(zip(keys, combo, strict=False))
        spec_v = _apply_overrides(copy.deepcopy(bundle.base_spec), variados)
        results.append((spec_v, variados))
    return results


def _apply_overrides(spec: dict, overrides: dict) -> dict:
    """Apply dot-path overrides. Supports nested paths with '.'.

    Chaves especiais ignoradas aqui (processadas em outro estágio):
      - "inputs_*"        → pós-carregamento via _apply_post_load_overrides
      - "_per_item_:*"    → pós-carregamento via _apply_post_load_overrides
      - "_cpu_alt_:*"     → pre-load, mas apenas para spec["spec"]["eap"] (ver abaixo)

    "restricoes_mercado" é tratado aqui como campo top-level (merge de dicts).
    "_cpu_alt_:*" modifica spec["spec"]["eap"][item_id].cpu_id diretamente.
    """
    for key_path, value in overrides.items():
        # Campos que começam com "inputs_" são aplicados APÓS o carregamento do spec
        # (via _apply_post_load_overrides). Ignorar aqui.
        if key_path.startswith("inputs_"):
            continue
        # per_item é resolvido no pós-carregamento
        if key_path.startswith(_PER_ITEM_PREFIX):
            continue
        # cpu_alternativo: modifica spec["spec"]["eap"] antes do carregamento
        if key_path.startswith(_CPU_ALT_PREFIX):
            _apply_cpu_alt_override(spec, key_path, value)
            continue

        parts = key_path.split(".")
        d = spec
        for part in parts[:-1]:
            if part not in d:
                d[part] = {}
            elif not isinstance(d[part], dict):
                d[part] = {}
            d = d[part]
        last = parts[-1]
        # Merge dict values instead of replacing (preserva campos existentes)
        if isinstance(value, dict) and isinstance(d.get(last), dict):
            d[last] = {**d[last], **value}
        else:
            d[last] = value
    return spec


def _apply_cpu_alt_override(spec: dict, key_path: str, value: str) -> None:
    """Substitui cpu_id no spec["spec"]["eap"] para o item_id extraído da chave.

    Formato de key_path: "_cpu_alt_:{campo}:{item_id}"
    onde campo pode ser "eap.cpu_id" ou qualquer variante com "cpu_id".
    """
    # Extrai item_id: é o sufixo após o último ":"
    suffix = key_path[len(_CPU_ALT_PREFIX) :]
    # suffix = "{campo}:{item_id}" — item_id não contém ":" por convenção
    last_colon = suffix.rfind(":")
    if last_colon < 0:
        return
    item_id = suffix[last_colon + 1 :]

    # Navega até a lista eap no spec
    eap_list = None
    # Suporta tanto spec dict plano quanto spec com chave "spec" aninhada
    if "spec" in spec and isinstance(spec["spec"], dict):
        eap_list = spec["spec"].get("eap")
    if eap_list is None:
        eap_list = spec.get("eap")
    if not isinstance(eap_list, list):
        return

    for item in eap_list:
        if isinstance(item, dict) and item.get("item_id") == item_id:
            item["cpu_id"] = value
            break


def _apply_scalar(existing: Any, value: Any) -> Any:
    """Aplica valor ou transformação escalar a um campo existente.

    Sintaxe de valor especial:
        {"__scale__": factor}   → multiplica o valor atual por factor (float)
        {"__add__": delta}      → soma delta ao valor atual (int/float)
        {"__frac_of__": "outro_campo", "__value__": frac}
            → não usado aqui; requer contexto adicional

    Qualquer outro dict faz merge; qualquer outro valor substitui.
    """
    import math as _math

    if isinstance(value, dict):
        if "__scale__" in value and existing is not None:
            try:
                raw = float(existing) * float(value["__scale__"])
                # Preserva tipo int quando o campo original era int
                if isinstance(existing, int):
                    return max(1, int(_math.ceil(raw)))
                return round(raw, 4)
            except (TypeError, ValueError):
                pass
        if "__add__" in value and existing is not None:
            try:
                raw = float(existing) + float(value["__add__"])
                return type(existing)(raw) if isinstance(existing, int) else round(raw, 4)
            except (TypeError, ValueError):
                pass
        # merge dict
        if isinstance(existing, dict):
            return {**existing, **value}
    return value


def _set_path(d: Any, parts: list[str], value: Any) -> None:
    """Navega path (suporta [*] para listas) e aplica valor."""
    if not parts:
        return
    part = parts[0]
    rest = parts[1:]

    if part == "[*]":
        # Aplica a todos os itens de uma lista
        if isinstance(d, list):
            for item in d:
                _set_path(item, rest, value)
        return

    if not rest:
        # Folha: aplicar valor
        if isinstance(d, dict):
            d[part] = _apply_scalar(d.get(part), value)
        return

    # Intermediate node
    if isinstance(d, dict):
        if part not in d:
            d[part] = {} if rest[0] != "[*]" else []
        _set_path(d[part], rest, value)


def _apply_post_load_overrides(spec_obj: object, variados: dict) -> None:
    """Aplica overrides diretamente no ProjectSpec carregado.

    Suporta:
      - dot-path simples:    inputs_cronograma.rcpsp_spec.deadline_weeks
      - wildcard de lista:   inputs_cronograma.rcpsp_spec.activities.[*].ramp_params.n_max
      - valores escalares:   {"__scale__": 1.25} ou {"__add__": 2}
      - per_item:            chave "_per_item_:{campo_inputs}:{item_id}"
                             → aplica value apenas à activity com o item_id dado
    """
    for key_path, value in variados.items():
        if key_path.startswith(_PER_ITEM_PREFIX):
            _apply_per_item_post_load(spec_obj, key_path, value)
            continue
        if not key_path.startswith("inputs_"):
            continue
        parts = key_path.split(".")
        attr = parts[0]
        d = getattr(spec_obj, attr, None)
        if d is None:
            continue
        _set_path(d, parts[1:], value)


def _apply_per_item_post_load(spec_obj: object, key_path: str, value: Any) -> None:
    """Aplica override de per_item a uma única activity por item_id.

    Formato de key_path: "_per_item_:{campo_inputs}:{item_id}"
    onde campo_inputs é ex. "inputs_cronograma.rcpsp_spec.activities.[*].ramp_params.n_max"

    A função substitui o segmento "[*]" pelo filtro de item_id antes de navegar.
    Se o campo não contém "[*]", tenta localizar a activity pelo item_id na lista
    de atividades e aplicar o path relativo ao n_max (última parte do campo).
    """
    suffix = key_path[len(_PER_ITEM_PREFIX) :]
    last_colon = suffix.rfind(":")
    if last_colon < 0:
        return
    campo = suffix[:last_colon]
    item_id = suffix[last_colon + 1 :]

    if not campo.startswith("inputs_"):
        return

    parts = campo.split(".")
    attr = parts[0]
    d = getattr(spec_obj, attr, None)
    if d is None:
        return

    # Navega até a lista que contém [*]; quando encontrar, filtra pelo item_id
    # em vez de aplicar a todos os elementos.
    _set_path_per_item(d, parts[1:], value, item_id)


def _set_path_per_item(d: Any, parts: list[str], value: Any, item_id: str) -> None:
    """Como _set_path, mas quando encontra '[*]' filtra apenas o item com item_id."""
    if not parts:
        return
    part = parts[0]
    rest = parts[1:]

    if part == "[*]":
        if isinstance(d, list):
            for item in d:
                if isinstance(item, dict) and item.get("item_id") == item_id:
                    _set_path(item, rest, value)
        return

    if not rest:
        if isinstance(d, dict):
            d[part] = _apply_scalar(d.get(part), value)
        return

    if isinstance(d, dict):
        if part not in d:
            d[part] = {} if rest[0] != "[*]" else []
        _set_path_per_item(d[part], rest, value, item_id)


def cenario_id(variados: dict) -> str:
    return hashlib.sha1(json.dumps(variados, sort_keys=True, default=str).encode()).hexdigest()[:10]


# ---------------------------------------------------------------------------
# F2 — Vector extraction
# ---------------------------------------------------------------------------


def extrair_vetor_O(canonical: dict, prazo_contratual: int | None) -> VetorEspacoO:
    cron = canonical.get("cronograma") or {}
    prazo = cron.get("makespan_semanas")
    # Fallback: max end_week from scheduled_activities
    if prazo is None:
        acts = cron.get("scheduled_activities") or []
        if acts:
            prazo = max((a.get("end_week") or 0) for a in acts)

    folga = (prazo_contratual - prazo) if (prazo is not None and prazo_contratual) else None

    pes = canonical.get("ponto_equilibrio") or []
    fe_list = [
        pe.get("frentes_equivalentes_necessarias")
        for pe in pes
        if pe.get("frentes_equivalentes_necessarias") is not None
    ]
    fe_med = sum(fe_list) / len(fe_list) if fe_list else None
    n_crit = sum(1 for fe in fe_list if fe > 1.25) if fe_list else 0
    itens_crit_pct = n_crit / len(fe_list) if fe_list else None
    gap_pool = round(sum(pe.get("gap_pool_overhead") or 0 for pe in pes), 2)

    eqs = canonical.get("equipes_diretas") or []
    mob_window = round(sum(e.get("custo_inst_mob_demob") or 0 for e in eqs), 2)

    # ADR-108: métricas de utilização e paralelismo do cronograma
    util = _cronograma_utilizacao(canonical)

    return VetorEspacoO(
        prazo_semanas=prazo,
        folga_semanas=round(folga, 1) if folga is not None else None,
        fe_nec_medio=round(fe_med, 3) if fe_med is not None else None,
        itens_criticos_pct=round(itens_crit_pct, 3) if itens_crit_pct is not None else None,
        gap_pool_total=gap_pool,
        custo_mob_window_total=mob_window,
        utilizacao_recursos_pct=util.get("utilizacao"),
        paralelismo_medio=util.get("paralelismo"),
        idle_pool_pct=util.get("idle_pct"),
    )


def _cubo_analitico_agregado(canonical: dict) -> dict[str, Any]:
    """Agrega cubo_analitico.celulas por categoria/propriedade (ADR-108).

    Retorna {share_mo, share_eq, share_comb, hhi} em [0,1].
    Retorna {} quando cubo vazio — caller atribui None (IC-4: sem falha silenciosa).
    """
    cubo = canonical.get("cubo_analitico") or {}
    celulas = cubo.get("celulas") or []
    if not celulas:
        return {}

    total = 0.0
    mo = 0.0
    eq = 0.0
    comb = 0.0
    por_atividade: dict[str, float] = {}

    for c in celulas:
        if c.get("componente_bdi") != "custo_direto":
            continue
        v = float(c.get("valor_rs") or 0.0)
        total += v
        cat = (c.get("categoria_insumo") or "").lower()
        prop = (c.get("propriedade") or "").lower()
        aid = c.get("atividade_id") or ""
        if cat == "mao_obra":
            mo += v
        elif cat == "equipamento":
            eq += v
        if prop == "combustivel":
            comb += v
        if aid:
            por_atividade[aid] = por_atividade.get(aid, 0.0) + v

    if total <= 0:
        return {}

    hhi = round(sum((v / total) ** 2 for v in por_atividade.values()), 4) if por_atividade else None
    return {
        "share_mo": round(mo / total, 4),
        "share_eq": round(eq / total, 4),
        "share_comb": round(comb / total, 4),
        "hhi": hhi,
    }


def _cronograma_utilizacao(canonical: dict) -> dict[str, Any]:
    """Extrai métricas de utilização e paralelismo do cronograma (ADR-108)."""
    cron = canonical.get("cronograma") or {}
    acts = cron.get("scheduled_activities") or []
    if not acts:
        return {}

    total_mob = 0
    total_prod = 0
    for a in acts:
        dist = a.get("distribuicao_semanal") or {}
        total_mob += len(dist)
        total_prod += sum(1 for d in dist.values() if (d.get("num_equipes") or 0) > 0)
    utilizacao = round(total_prod / total_mob, 4) if total_mob > 0 else None

    semanas: dict[str, int] = {}
    for a in acts:
        for semana, d in (a.get("distribuicao_semanal") or {}).items():
            if (d.get("num_equipes") or 0) > 0:
                semanas[semana] = semanas.get(semana, 0) + 1
    paralelismo = round(sum(semanas.values()) / len(semanas), 3) if semanas else None

    # CuboPoolFace quando disponível (ADR-106 F8)
    pool_face = canonical.get("cubo_pool_face")
    idle_pct: float | None = None
    if pool_face and isinstance(pool_face, dict):
        celulas_pf = pool_face.get("celulas") or []
        total_pf = len(celulas_pf)
        idle_sem = sum(1 for c in celulas_pf if (c.get("estado") or "") == "idle")
        idle_pct = round(idle_sem / total_pf, 4) if total_pf > 0 else None

    return {"utilizacao": utilizacao, "paralelismo": paralelismo, "idle_pct": idle_pct}


def extrair_vetor_EF(canonical: dict, report: dict) -> VetorEspacoEF:
    resultado = canonical.get("resultado") or {}
    custo = resultado.get("custo") or {}
    venda = resultado.get("venda") or {}

    margem = resultado.get("margem_pct")
    custo_pool = custo.get("direto_equipes")
    custo_ind = round(
        sum(v for k, v in custo.items() if "indireto" in k and isinstance(v, (int, float))),
        2,
    )
    preco_venda = venda.get("total_com_bdi")
    pu_q = venda.get("total_sem_bdi")
    ratio = round(custo_pool / pu_q, 4) if (custo_pool and pu_q and pu_q > 0) else None

    gates = (report.get("quality_gates") or {}) if report else {}
    decision = gates.get("decision")
    fidelidade = decision in {"APROVADO", "APROVADO_COM_RESSALVAS"} if decision else None

    # ADR-108: composição de custo do cubo_analitico
    comp = _cubo_analitico_agregado(canonical)

    return VetorEspacoEF(
        margem_pct=round(margem, 4) if margem is not None else None,
        custo_execucao_pool=custo_pool,
        custo_indireto=custo_ind if custo_ind else None,
        preco_venda=preco_venda,
        ratio_pool_vs_cat=ratio,
        share_mo_pct=comp.get("share_mo"),
        share_eq_pct=comp.get("share_eq"),
        share_comb_pct=comp.get("share_comb"),
        concentracao_atividade=comp.get("hhi"),
        fidelidade_gates=fidelidade,
    )


# ---------------------------------------------------------------------------
# F2 — Classification
# ---------------------------------------------------------------------------


def classificar_O(v: VetorEspacoO, perfil: PerfilExpectativas) -> ClassificacaoO:
    scores = []
    if v.folga_semanas is not None:
        scores.append("IDEAL" if v.folga_semanas >= 0 else ("ATENCAO" if v.folga_semanas >= -2 else "CRITICO"))
    if v.fe_nec_medio is not None:
        scores.append("IDEAL" if v.fe_nec_medio <= 1.0 else ("ATENCAO" if v.fe_nec_medio <= 1.25 else "CRITICO"))
    if v.itens_criticos_pct is not None:
        scores.append(
            "IDEAL" if v.itens_criticos_pct == 0 else ("ATENCAO" if v.itens_criticos_pct <= 0.20 else "CRITICO")
        )
    if not scores:
        return "ATENCAO"
    if "CRITICO" in scores:
        return "CRITICO"
    if "ATENCAO" in scores:
        return "ATENCAO"
    return "IDEAL"


def classificar_EF(v: VetorEspacoEF, perfil: PerfilExpectativas) -> ClassificacaoEF:
    scores = []
    if v.margem_pct is not None:
        meta = perfil.meta_margem_pct
        tol = perfil.tolerancia_margem
        scores.append(
            "DENTRO_EXPECTATIVA"
            if v.margem_pct >= meta
            else ("ATENCAO" if v.margem_pct >= meta - tol else "FORA_EXPECTATIVA")
        )
    if v.ratio_pool_vs_cat is not None:
        scores.append(
            "DENTRO_EXPECTATIVA"
            if v.ratio_pool_vs_cat <= 1.0
            else ("ATENCAO" if v.ratio_pool_vs_cat <= 1.10 else "FORA_EXPECTATIVA")
        )
    if v.fidelidade_gates is not None:
        scores.append("DENTRO_EXPECTATIVA" if v.fidelidade_gates else "FORA_EXPECTATIVA")
    if not scores:
        return "ATENCAO"
    if "FORA_EXPECTATIVA" in scores:
        return "FORA_EXPECTATIVA"
    if "ATENCAO" in scores:
        return "ATENCAO"
    return "DENTRO_EXPECTATIVA"


# ---------------------------------------------------------------------------
# F3 — Pareto computation
# ---------------------------------------------------------------------------


def _domina_O(a: CenarioAvaliado, b: CenarioAvaliado) -> bool:
    """a dominates b in O-space (minimizing prazo, fe_nec, gap_pool)."""
    va, vb = a.vetor_O, b.vetor_O
    dims = [
        (va.prazo_semanas, vb.prazo_semanas),
        (va.fe_nec_medio, vb.fe_nec_medio),
        (va.gap_pool_total, vb.gap_pool_total),
    ]
    dims = [(x, y) for x, y in dims if x is not None and y is not None]
    if not dims:
        return False
    no_worse = all(x <= y for x, y in dims)
    strictly_better = any(x < y for x, y in dims)
    return no_worse and strictly_better


def _domina_EF(a: CenarioAvaliado, b: CenarioAvaliado) -> bool:
    """a dominates b in EF-space (maximize margem, minimize custo_indireto)."""
    va, vb = a.vetor_EF, b.vetor_EF
    if va.margem_pct is None or vb.margem_pct is None:
        return False
    margem_ok = va.margem_pct >= vb.margem_pct
    ind_ok = True
    if va.custo_indireto is not None and vb.custo_indireto is not None:
        ind_ok = va.custo_indireto <= vb.custo_indireto
    strictly = va.margem_pct > vb.margem_pct or (
        va.custo_indireto is not None and vb.custo_indireto is not None and va.custo_indireto < vb.custo_indireto
    )
    return margem_ok and ind_ok and strictly


def calcular_pareto(cenarios: list[CenarioAvaliado], espaco: str) -> set[str]:
    """Returns set of cenario_ids on the Pareto frontier for espaco='O'|'EF'."""
    domina = _domina_O if espaco == "O" else _domina_EF
    pareto_ids = set()
    for c in cenarios:
        dominated = any(domina(other, c) for other in cenarios if other.cenario_id != c.cenario_id)
        if not dominated:
            pareto_ids.add(c.cenario_id)
    return pareto_ids


# ---------------------------------------------------------------------------
# F3 — Shortlist curation
# ---------------------------------------------------------------------------


def _build_justificativa(c: CenarioAvaliado, motivo: str) -> JustificativaCenario:
    v_O, v_EF = c.vetor_O, c.vetor_EF
    destaques_O = []
    if v_O.folga_semanas is not None:
        tag = "OK" if v_O.folga_semanas >= 0 else "WARN"
        destaques_O.append(f"[{tag}] Folga {v_O.folga_semanas:+.0f} sem")
    if v_O.fe_nec_medio is not None:
        destaques_O.append(f"fe_nec medio {v_O.fe_nec_medio:.2f}")
    if v_O.itens_criticos_pct == 0:
        destaques_O.append("0 itens criticos")
    elif v_O.itens_criticos_pct is not None:
        destaques_O.append(f"{v_O.itens_criticos_pct * 100:.0f}% itens criticos")

    destaques_EF = []
    if v_EF.margem_pct is not None:
        destaques_EF.append(f"Margem {v_EF.margem_pct * 100:.1f}%")
    if v_EF.ratio_pool_vs_cat is not None:
        if v_EF.ratio_pool_vs_cat <= 1:
            destaques_EF.append(f"Pool {(1 - v_EF.ratio_pool_vs_cat) * 100:.1f}% abaixo mercado")
        else:
            destaques_EF.append(f"Pool {(v_EF.ratio_pool_vs_cat - 1) * 100:.1f}% acima mercado")

    alertas = []
    if c.classificacao_O == "ATENCAO":
        alertas.append("O-space: atencao em alguma dimensao")
    if c.classificacao_EF == "ATENCAO":
        alertas.append("EF-space: margem proxima da meta")

    return JustificativaCenario(
        motivo_inclusao=motivo,
        destaques_O=destaques_O,
        destaques_EF=destaques_EF,
        alertas=alertas,
        parametros_chave=c.parametros_variados,
    )


def curar_shortlist(
    cenarios: list[CenarioAvaliado],
    top_k: int,
    perfil: PerfilExpectativas,
) -> list[CenarioRankeado]:
    viaveis = [c for c in cenarios if c.viabilidade in {"APROVADO", "APROVADO_COM_RESSALVAS"}]
    if not viaveis:
        return []

    pareto_O_ids = calcular_pareto(viaveis, "O")
    pareto_EF_ids = calcular_pareto(viaveis, "EF")

    for c in viaveis:
        c.pareto_O = c.cenario_id in pareto_O_ids
        c.pareto_EF = c.cenario_id in pareto_EF_ids
        c.pareto_intersecao = c.pareto_O and c.pareto_EF

    intersecao = [c for c in viaveis if c.pareto_intersecao]
    pool = intersecao if intersecao else ([c for c in viaveis if c.pareto_EF] or viaveis)

    ranked = sorted(
        pool,
        key=lambda c: (
            c.classificacao_O != "IDEAL",
            c.classificacao_EF != "DENTRO_EXPECTATIVA",
            -(c.vetor_EF.margem_pct or 0),
            (c.vetor_O.prazo_semanas or 9999),
            (c.vetor_O.fe_nec_medio or 9999),
            c.cenario_id,
        ),
    )

    shortlist = []
    for i, c in enumerate(ranked[:top_k]):
        c.rank_final = i + 1
        motivo = "pareto_intersecao" if c.pareto_intersecao else ("pareto_EF" if c.pareto_EF else "melhor_viavel")
        shortlist.append(
            CenarioRankeado(
                rank=i + 1,
                cenario=c,
                justificativa=_build_justificativa(c, motivo),
            )
        )
    return shortlist


def classificar_bundle(cenarios: list[CenarioAvaliado]) -> CampaignStatus:
    viaveis = [c for c in cenarios if c.viabilidade in {"APROVADO", "APROVADO_COM_RESSALVAS"}]
    falhas = [c for c in cenarios if c.erro]
    if not viaveis:
        return "ABORTADO" if len(falhas) == len(cenarios) else "INFEASIBLE"
    intersecao = [c for c in viaveis if c.pareto_intersecao]
    if intersecao:
        return "SUCESSO"
    pareto_O = [c for c in viaveis if c.pareto_O]
    pareto_EF = [c for c in viaveis if c.pareto_EF]
    if pareto_O and pareto_EF and not intersecao:
        return "FRONTEIRA_UNICA"
    return "SUCESSO_PARCIAL"


# ---------------------------------------------------------------------------
# Task picklável para ProcessPoolExecutor (module-level = picklável)
# ---------------------------------------------------------------------------


@dataclass
class _CampaignTask:
    """Contexto completo para um cenário — picklável para multiprocessing."""

    spec_v: dict
    variados: dict
    config_root: str
    projects_root: str
    prazo_contratual: int | None
    perfil: PerfilExpectativas
    procurement_intent: str
    do_reset: bool


def _run_campaign_task(task: _CampaignTask) -> CenarioAvaliado:
    """Avalia um cenário da campanha — module-level para ser picklável."""
    from concilium.application.benchmarks.execution.runner import BenchmarkRunner
    from concilium.application.benchmarks.report.report_builder import BenchmarkReportBuilder
    from concilium.application.benchmarks.report.report_printer import BenchmarkReportPrinter
    from concilium.application.benchmarks.spec.spec_loader import load_spec_from_dict

    class _Silent(BenchmarkReportPrinter):
        def print(self, report: dict) -> None:  # noqa: A003
            pass

    import shutil
    import tempfile

    cid = cenario_id(task.variados)
    spec_with_id = dict(task.spec_v)
    base_slug = spec_with_id.get("slug") or spec_with_id.get("id") or "UNKNOWN"
    scenario_slug = f"{base_slug}-{cid[:6]}"
    # Definir TANTO "slug" QUANTO "id" — spec_loader usa ref.get("id") para o slug do projeto.
    # Sem "id", _infer_slug_from_path leria o nome do tmpdir e criaria um projeto com
    # esse nome em projetos/ (ex: campaign_AGIS-054483_ajeczz9t), impossibilitando a limpeza.
    spec_with_id["slug"] = scenario_slug
    spec_with_id["id"] = scenario_slug
    meta = dict(spec_with_id.get("meta") or {})
    base_nome = meta.get("projeto", base_slug)
    meta["projeto"] = f"{base_nome} [{cid[:6]}]"
    spec_with_id["meta"] = meta

    scenario_projects_root = Path(task.projects_root)
    actual_project_slug: str | None = None  # rastreado para cleanup preciso

    with tempfile.TemporaryDirectory() as tmp_dir:
        ref_path = Path(tmp_dir) / "referencia.json"
        ref_path.write_text(json.dumps(spec_with_id, ensure_ascii=False, default=str))

        try:
            spec_obj = load_spec_from_dict(spec_with_id, ref_path)
            actual_project_slug = spec_obj.slug  # slug real após normalização do spec_loader
            _apply_post_load_overrides(spec_obj, task.variados)
            runner = BenchmarkRunner(
                config_root=Path(task.config_root),
                projects_root=scenario_projects_root,
                report_builder=BenchmarkReportBuilder(),
                report_printer=_Silent(),
            )
            report = runner.run(
                spec_obj,
                reset=task.do_reset,
                skip_artifacts=True,
                procurement_intent=task.procurement_intent,
            )
            canonical: dict = {}
            for _try in (actual_project_slug, actual_project_slug.upper(), actual_project_slug.lower()):
                _can = scenario_projects_root / _try / "v1" / "canonical.json"
                if _can.exists():
                    canonical = json.loads(_can.read_text())
                    break

            v_O = extrair_vetor_O(canonical, task.prazo_contratual)
            v_EF = extrair_vetor_EF(canonical, report)
            decision = (report.get("quality_gates") or {}).get("decision") or "BLOQUEADO"
            via_map: dict[str, ViabilidadeStatus] = {
                "APROVADO": "APROVADO",
                "APROVADO_COM_RESSALVAS": "APROVADO_COM_RESSALVAS",
                "BLOQUEADO_COM_INVESTIGACAO": "BLOQUEADO_COM_INVESTIGACAO",
                "BLOQUEADO": "BLOQUEADO",
            }
            viabilidade: ViabilidadeStatus = via_map.get(decision, "ERRO")
            result = CenarioAvaliado(
                cenario_id=cid,
                parametros_variados=task.variados,
                viabilidade=viabilidade,
                vetor_O=v_O,
                vetor_EF=v_EF,
                classificacao_O=classificar_O(v_O, task.perfil),
                classificacao_EF=classificar_EF(v_EF, task.perfil),
            )
        except Exception as exc:
            result = CenarioAvaliado(
                cenario_id=cid,
                parametros_variados=task.variados,
                viabilidade="ERRO",
                vetor_O=VetorEspacoO(),
                vetor_EF=VetorEspacoEF(),
                classificacao_O="CRITICO",
                classificacao_EF="FORA_EXPECTATIVA",
                erro=str(exc),
            )
        finally:
            # Limpar projeto de cenário em projetos/ usando o slug REAL (não o esperado).
            # O spec_loader pode ter derivado um slug diferente do scenario_slug se "id"
            # não estava definido — agora está, mas o finally usa actual_project_slug
            # como defesa contra futuras inconsistências.
            slugs_to_clean = {scenario_slug, actual_project_slug} if actual_project_slug else {scenario_slug}
            for _slug_clean in slugs_to_clean:
                for _try in (_slug_clean, _slug_clean.upper(), _slug_clean.lower()):
                    _proj = scenario_projects_root / _try
                    if _proj.exists():
                        shutil.rmtree(_proj, ignore_errors=True)

    return result


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def executar_campanha(
    bundle: GoResearchCampaignBundle,
    config_root: str | Path,
    projects_root: str | Path,
    procurement_intent: str = "rfp",
    num_workers: int = 3,
    reset: bool = True,
) -> CampaignOutputBundle:
    """Execute a full campaign: generate grid, evaluate, curate, return bundle.

    ADR-109: verifica fronteira de tratabilidade antes de executar.
    O limiar é configurável via CONCILIUM__CAMPAIGN_CARDINALITY_THRESHOLD (default: 10.000).
    """
    import warnings

    from concilium.infrastructure.settings import get_campaign as _get_campaign_settings

    cfg = _get_campaign_settings()
    n_card = bundle.cardinality()
    if n_card > cfg.cardinality_threshold:
        _w = num_workers or cfg.max_workers
        _s = cfg.seconds_per_scenario
        warnings.warn(
            f"GoResearchCampaignBundle.cardinality={n_card:,} excede fronteira de "
            f"tratabilidade ({cfg.cardinality_threshold:,}). "
            f"Busca exaustiva levaria ~{n_card * _s // _w // 3600:.0f}h "
            f"com {_w} workers ({_s}s/cenário). "
            f"Considere reduzir dimensões ou usar busca guiada. "
            f"Ajuste CONCILIUM__CAMPAIGN_CARDINALITY_THRESHOLD para suprimir este aviso.",
            stacklevel=2,
        )

    grid = gerar_grid(bundle)
    cenarios: list[CenarioAvaliado] = []
    prazo_cont = bundle.perfil_expectativas.prazo_contratual_semanas

    tasks = [
        _CampaignTask(
            spec_v=sv,
            variados=var,
            config_root=str(config_root),
            projects_root=str(projects_root),
            prazo_contratual=prazo_cont,
            perfil=bundle.perfil_expectativas,
            procurement_intent=procurement_intent,
            do_reset=reset,
        )
        for sv, var in grid
    ]

    # ThreadPoolExecutor: correto para este workload (I/O-bound com leitura de canonical,
    # config e catálogo; escrita de JSON). ProcessPoolExecutor com fork causa race conditions
    # em acesso compartilhado ao filesystem de projetos/ resultando em canonical vazio.
    # O speedup medido (3.7×) era real — o bottleneck era o _store_lock removido, não o GIL.
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(_run_campaign_task, t): t for t in tasks}
        for future in concurrent.futures.as_completed(futures):
            cenarios.append(future.result())

    shortlist = curar_shortlist(cenarios, bundle.top_k, bundle.perfil_expectativas)
    status = classificar_bundle(cenarios)
    viaveis = [c for c in cenarios if c.viabilidade in {"APROVADO", "APROVADO_COM_RESSALVAS"}]

    output = CampaignOutputBundle(
        campaign_id=bundle.campaign_id,
        campaign_version=bundle.campaign_version,
        gerado_em=datetime.now(UTC),
        n_cenarios_avaliados=len(cenarios),
        n_cenarios_viaveis=len(viaveis),
        n_falhas=sum(1 for c in cenarios if c.erro),
        status=status,
        cenarios=cenarios,
        shortlist=shortlist,
    )
    return output


# ---------------------------------------------------------------------------
# CampaignBundleCube — camada analítica multidimensional
# ---------------------------------------------------------------------------

_METRICAS_O = [
    "prazo_semanas",
    "fe_nec_medio",
    "itens_criticos_pct",
    "gap_pool_total",
    "utilizacao_recursos_pct",
    "paralelismo_medio",
]
_METRICAS_EF = [
    "margem_pct",
    "ratio_pool_vs_cat",
    "custo_indireto",
    "share_mo_pct",
    "share_eq_pct",
    "share_comb_pct",
    "concentracao_atividade",
]


def _get_metrica(c: CenarioAvaliado, metrica: str) -> float | None:
    vo, vef = c.vetor_O, c.vetor_EF
    return getattr(vo, metrica, None) or getattr(vef, metrica, None)


def _label_variados(variados: dict) -> str:
    """Extrai label legível dos parâmetros variados."""
    parts = []
    for campo, valor in variados.items():
        nome = campo.split(".")[-1]
        if isinstance(valor, dict):
            parts.append(", ".join(f"{k}={v}" for k, v in valor.items()))
        else:
            parts.append(f"{nome}={valor}")
    return " | ".join(parts) if parts else str(variados)


def _tendencia(valores_ord: list, medias: list[float | None]) -> TendenciaMarginal:
    from concilium.domain.models.campaign.campaign import TendenciaMarginal  # noqa: F401

    valid = [(v, m) for v, m in zip(valores_ord, medias, strict=False) if m is not None]
    if len(valid) < 2:
        return "indeterminado"
    ms = [m for _, m in valid]
    if all(ms[i] <= ms[i + 1] for i in range(len(ms) - 1)):
        return "crescente"
    if all(ms[i] >= ms[i + 1] for i in range(len(ms) - 1)):
        return "decrescente"
    return "nao_monotona"


def construir_cubo(bundle: GoResearchCampaignBundle, output: CampaignOutputBundle) -> CampaignBundleCube:
    """Constrói o CampaignBundleCube a partir do bundle e do output da campanha.

    Dimensões = parâmetros do sweep.
    Células = todas as combinações avaliadas (com cenário) ou ausentes (sem cenário).
    Faces = projeções 2D para cada par de dimensões (se sweep ≥ 2 dimensões).
    Resumos marginais = efeito de cada dimensão em cada métrica.
    """
    # --- 1. Dimensões ---
    dims = [
        CuboDimensao(
            nome=s.campo.split(".")[-1],
            campo=s.campo,
            valores=s.valores,
        )
        for s in bundle.sweep
    ]

    # Índice de cenários por variados-hash
    cenario_por_id = {c.cenario_id: c for c in output.cenarios}
    grid, _ = zip(*gerar_grid(bundle), strict=False) if bundle.sweep else ([], [])
    grid_list = list(gerar_grid(bundle))

    # --- 2. Células ---
    celulas: list[CelulaAnalitica] = []
    for _sv, variados in grid_list:
        cid = cenario_id(variados)
        c = cenario_por_id.get(cid)
        celulas.append(
            CelulaAnalitica(
                dimensoes={d.nome: variados.get(d.campo) for d in dims},
                cenario_id=cid if c else None,
                vetor_O=c.vetor_O if c else None,
                vetor_EF=c.vetor_EF if c else None,
                classificacao_O=c.classificacao_O if c else None,
                classificacao_EF=c.classificacao_EF if c else None,
                viabilidade=c.viabilidade if c else None,
                pareto_O=c.pareto_O if c else False,
                pareto_EF=c.pareto_EF if c else False,
                pareto_intersecao=c.pareto_intersecao if c else False,
            )
        )

    n_total = len(celulas)
    n_aval = sum(1 for ce in celulas if ce.cenario_id)
    n_viaveis = sum(1 for ce in celulas if ce.viabilidade in {"APROVADO", "APROVADO_COM_RESSALVAS"})
    n_pareto = sum(1 for ce in celulas if ce.pareto_intersecao)

    # --- 3. Faces (pares de dimensões) ---
    faces: list[FaceAnalitica] = []
    if len(dims) >= 2:
        for i, dx in enumerate(dims):
            for dy in dims[i + 1 :]:
                for metrica in _METRICAS_O + _METRICAS_EF:
                    grade: list[list[float | None]] = []
                    for vy in dy.valores:
                        row = []
                        for vx in dx.valores:
                            matching = [
                                ce
                                for ce in celulas
                                if ce.dimensoes.get(dx.nome) == vx and ce.dimensoes.get(dy.nome) == vy and ce.cenario_id
                            ]
                            if matching:
                                # matching[0].cenario_id só é truthy quando a célula foi
                                # construída a partir de um `c` presente em cenario_por_id
                                # (ver loop de --- 2. Células --- acima); logo o lookup
                                # abaixo sempre resolve — sem fallback necessário.
                                cid = matching[0].cenario_id
                                assert cid is not None, "cenario_id deve ser não-None após filtro"
                                c_match = cenario_por_id[cid]
                                row.append(_get_metrica(c_match, metrica))
                            else:
                                row.append(None)
                        grade.append(row)
                    # Only include face if at least some values are non-None
                    if any(v is not None for row in grade for v in row):
                        faces.append(
                            FaceAnalitica(
                                dim_x=dx.nome,
                                dim_y=dy.nome,
                                metrica=metrica,
                                valores_x=dx.valores,
                                valores_y=dy.valores,
                                grade=grade,
                            )
                        )

    # --- 4. Resumos marginais ---
    resumos: list[ResumoMarginal] = []
    for d in dims:
        for metrica in _METRICAS_O + _METRICAS_EF:
            medias: list[float | None] = []
            for val in d.valores:
                celulas_val = [ce for ce in celulas if ce.dimensoes.get(d.nome) == val and ce.cenario_id]
                vals_m = []
                for ce in celulas_val:
                    # Mesmo invariante do bloco de faces acima: ce.cenario_id truthy
                    # garante presença em cenario_por_id.
                    cid_m = ce.cenario_id
                    assert cid_m is not None, "cenario_id deve ser não-None após filtro"
                    c_m = cenario_por_id[cid_m]
                    v = _get_metrica(c_m, metrica)
                    if v is not None:
                        vals_m.append(v)
                medias.append(round(sum(vals_m) / len(vals_m), 4) if vals_m else None)

            if any(m is not None for m in medias):
                resumos.append(
                    ResumoMarginal(
                        dimensao=d.nome,
                        metrica=metrica,
                        valores=d.valores,
                        medias=medias,
                        tendencia=_tendencia(d.valores, medias),
                    )
                )

    return CampaignBundleCube(
        campaign_id=output.campaign_id,
        dimensoes=dims,
        celulas=celulas,
        faces=faces,
        resumos_marginais=resumos,
        n_celulas_total=n_total,
        n_celulas_avaliadas=n_aval,
        n_celulas_viaveis=n_viaveis,
        n_celulas_pareto=n_pareto,
        cobertura_pct=round(n_aval / n_total, 4) if n_total else 0.0,
    )


# ---------------------------------------------------------------------------
# Classe 4 — CPU alternativo: descoberta de alternativas via catálogo
# ---------------------------------------------------------------------------


def listar_cpus_alternativos(cpu_id: str, config_root: Path) -> list[str]:
    """Retorna lista de cpu_ids alternativos declarados no JSON do catálogo.

    Um CPU alternativo é aquele listado em ``cpus_alternativos`` do JSON do CPU
    corrente. Requer campo ``cpus_alternativos: [str]`` populado no catálogo
    (ADR-070 Classe 4 / F4).

    Returns lista vazia se o CPU não existir ou não declarar alternativas.
    """
    cpu_path = config_root / "catalogos" / "mendeslobo" / "cpus" / f"{cpu_id}.json"
    if not cpu_path.exists():
        # Tenta raízes secundárias (test, samples)
        for sub in ("test", "samples"):
            alt = config_root / "catalogos" / sub / "cpus" / f"{cpu_id}.json"
            if alt.exists():
                cpu_path = alt
                break
        else:
            return []
    try:
        d = json.loads(cpu_path.read_text(encoding="utf-8"))
        alts = d.get("cpus_alternativos") or []
        return [str(a) for a in alts if a]
    except Exception:
        return []


def sugerir_levers_cpu_alternativo(
    base_spec: dict,
    config_root: Path,
) -> list[ParametroSweep]:
    """Gera levers Classe 4 para todos os itens do EAP que têm CPUs alternativos.

    Para cada item da EAP cujo ``cpu_id`` declara ``cpus_alternativos`` no
    catálogo, cria um ``ParametroSweep`` com scope ``cpu_alternativo`` listando
    o CPU original + os alternativos como valores.

    Exemplo de resultado:
        ParametroSweep(
            campo="spec.eap.[*].cpu_id",
            valores=["CPU-TERRA-ESCO-CARGA-2CAT-DMT2000",
                     "CPU-TERRA-ESCO-CARGA-2CAT-DMT3000"],
            scope="cpu_alternativo",
            item_ids=["eap-1_5"],
        )
    """
    spec_inner = base_spec.get("spec") or base_spec
    eap = spec_inner.get("eap") or []
    levers: list[ParametroSweep] = []

    for item in eap:
        if not isinstance(item, dict):
            continue
        item_id = item.get("item_id")
        cpu_id = item.get("cpu_id")
        if not item_id or not cpu_id:
            continue
        alts = listar_cpus_alternativos(cpu_id, config_root)
        if not alts:
            continue
        levers.append(
            ParametroSweep(
                campo="spec.eap.[*].cpu_id",
                valores=[cpu_id] + alts,  # inclui o original como primeira opção
                scope="cpu_alternativo",
                item_ids=[item_id],
            )
        )
    return levers
