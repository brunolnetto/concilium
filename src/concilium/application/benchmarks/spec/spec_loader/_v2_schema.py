"""Normalização do schema v2 de referência para o formato interno."""

from __future__ import annotations

from typing import Any

_EBR_KEY_MAP: dict[str, str] = {
    "materiais": "material",
    "material": "material",
    "diesel": "diesel",
    "mao_obra": "mao_obra",
    "equipamentos": "equipamentos",
    "servicos": "servicos",
    "indireto": "indireto",
}


def _v2_build_root_fields(ref: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    """1. meta → campos raiz (+ id/slug/contexto_id preservados do nível raiz).

    Preservar "id" e "slug" do nível raiz para que spec_loader derive o slug correto
    (slug = ref.get("id") or _infer_slug_from_path). Sem isso, _infer_slug_from_path
    lê o nome do diretório temporário e cria projetos com nomes errados.
    """
    out: dict[str, Any] = {}
    if ref.get("id"):
        out["id"] = ref["id"]
    if ref.get("slug"):
        out["slug"] = ref["slug"]
    # Propaga contexto_id do topo ou de meta — permite override do contexto por benchmark
    ctx = ref.get("contexto_id") or meta.get("contexto_id")
    if ctx:
        out["contexto_id"] = ctx

    out["projeto"] = meta.get("projeto", "")
    out["data_inicio"] = meta.get("data_inicio", "")
    out["data_termino"] = meta.get("data_termino", "")
    # localizacao aceita string ("Brasil") ou {lat, lng} — ambos propagados downstream
    out["localizacao"] = meta.get("localizacao", "")
    out["regime_trabalho"] = meta.get("regime_trabalho", {"horas_dia": 8, "dias_semana": 6})
    out["mode"] = meta.get("mode", "benchmark_config")
    return out


def _v2_build_cronograma(spec: dict[str, Any], eap_by_id: dict[str, Any]) -> tuple[list, list]:
    """4. cronograma: propaga formato compacto E constrói atividades v1 (retrocompat).

    Formato compacto: {item_id, equipes: {n_inicial, n_max, taxa_mob, taxa_demob}}
    duration_weeks é calculado em skill-04 a partir de Q/P — não armazenado na spec.
    """
    atividades = []
    cron_compacto = []
    for item in spec.get("cronograma") or []:
        item_id = item["item_id"]
        eap_item = eap_by_id.get(item_id, {})
        compact: dict[str, Any] = {"item_id": item_id}
        if "equipes" in item:
            compact["equipes"] = item["equipes"]
        if "producao_diaria" in item:
            compact["producao_diaria"] = item["producao_diaria"]
        cron_compacto.append(compact)
        atividades.append(
            {
                "item_id": item_id,
                "producao_diaria": item.get("producao_diaria", 0.0),
                "quantitativo": eap_item.get("quantitativo", 0.0),
                "semanas": item.get("semanas") or {},
                "equipes": item.get("equipes"),
            }
        )
    return atividades, cron_compacto


def _v2_build_planejamento(spec: dict[str, Any], eap_by_id: dict[str, Any]) -> list:
    """5. planejamento: flat v2 → subtotal aninhado v1."""
    planejamento_detalhado = []
    for item in spec.get("planejamento") or []:
        item_id = item["item_id"]
        eap_item = eap_by_id.get(item_id, {})
        planejamento_detalhado.append(
            {
                "item_id": item_id,
                "cpu_id": eap_item.get("cpu_id", ""),
                "quantitativo": eap_item.get("quantitativo", 0.0),
                "subtotal": {
                    "sem_bdi": {"total": item.get("custo_sem_bdi", 0.0)},
                    "com_bdi": {"total": item.get("custo_com_bdi", 0.0)},
                },
            }
        )
    return planejamento_detalhado


def _v2_build_indiretos(spec: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """7. indiretos[] → indiretos_detalhamento (dict) + equipes_indiretas (lista).

    driver "mensal"  → custo_fixo_mensal_total  (multiplicado por duração no pipeline)
    driver "projeto" → custo_fixo_total          (custo único, ex: mobilização)
    """
    indiretos_detalhamento: dict[str, Any] = {}
    equipes_indiretas: list[dict[str, Any]] = []
    for ind in spec.get("indiretos") or []:
        cat = ind["categoria"]
        driver = ind.get("driver", "mensal")
        if driver == "projeto":
            indiretos_detalhamento[cat] = {"custo_fixo_total": ind.get("custo_fixo_total", 0.0)}
        else:
            indiretos_detalhamento[cat] = {"custo_fixo_mensal_total": ind.get("custo_fixo_mensal_total", 0.0)}
        mao_obra = ind.get("mao_obra") or []
        if mao_obra:
            eq_ind: dict[str, Any] = {"id": f"INDIR-{cat}", "categoria": cat, "mao_obra": mao_obra}
            # Auditoria AGIS 2026-06-11: a planilha decompõe indiretos em MO+EQUIP+VERBAS
            # (indiretos.adm.txt). Propagar os totais mensais para BDI fiel por sub-categoria.
            for campo in ("equipamentos_mensal_total", "verbas_mensal_total"):
                if isinstance(ind.get(campo), (int, float)):
                    eq_ind[campo] = float(ind[campo])
            equipes_indiretas.append(eq_ind)
    return indiretos_detalhamento, equipes_indiretas


def _v2_build_eap_and_rcpsp(spec: dict[str, Any]) -> tuple[list, dict[str, Any], dict]:
    """2. eap direto + 3. rcpsp_spec (inalterado)."""
    eap = spec.get("eap") or []
    eap_by_id: dict[str, Any] = {item["item_id"]: item for item in eap if "item_id" in item}
    rcpsp_spec = spec.get("rcpsp_spec") or {}
    return eap, eap_by_id, rcpsp_spec


def _v2_build_logistica_consumiveis(spec: dict[str, Any]) -> dict[str, Any]:
    """ADR-151: spec.logistica_consumiveis → ref['logistica_consumiveis'] (mesmo
    padrão de rcpsp_spec) — provisionamento externo de déficit declarado no
    benchmark, repassado para inputs_cronograma em _load_dict.py."""
    return spec.get("logistica_consumiveis") or {}


def _v2_build_tail_fields(ref: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """8. diretos → equipes_detalhadas, 9. cenarios, 10. resultado (já no topo em v2)."""
    return {
        "equipes_detalhadas": spec.get("diretos") or [],
        "cenarios": spec.get("cenarios") or [],
        "resultado": ref.get("resultado") or {},
    }


def _unpack_v2_schema(ref: dict[str, Any]) -> dict[str, Any]:
    """Converte schema v2 (meta+spec+resultado) para formato v1-compatível com o pipeline.

    Schema v2 é detectado pela presença da chave 'spec' no dict raiz.
    A estrutura v2 é mais limpa e compacta; esta função expande para o formato
    que o resto do pipeline (spec_loader + input_deriver) já sabe consumir.

    Mapeamento:
        meta.*                  → campos raiz (projeto, data_inicio, …)
        spec.eap                → ref["eap"]
        spec.rcpsp_spec         → ref["rcpsp_spec"]
        spec.cronograma[]       → ref["cronograma"]["atividades"] (+ quantitativo da eap)
        spec.planejamento[]     → ref["planejamento_detalhado"] (subtotal aninhado)
        spec.bdi                → ref["bdi"]
        spec.indiretos[]        → ref["indiretos_detalhamento"] + ref["equipes_indiretas"]
        spec.diretos            → ref["equipes_detalhadas"]
        spec.cenarios           → ref["cenarios"]
        resultado               → ref["resultado"]  (mantido no topo)
    """
    meta = ref.get("meta") or {}
    spec = ref.get("spec") or {}

    out = _v2_build_root_fields(ref, meta)

    eap, eap_by_id, rcpsp_spec = _v2_build_eap_and_rcpsp(spec)
    out["eap"] = eap
    out["rcpsp_spec"] = rcpsp_spec
    logistica_consumiveis = _v2_build_logistica_consumiveis(spec)
    if logistica_consumiveis:
        out["logistica_consumiveis"] = logistica_consumiveis

    atividades, cron_compacto = _v2_build_cronograma(spec, eap_by_id)
    out["cronograma"] = {"atividades": atividades}
    # Expõe a lista compacta direta para _norm_ref_build_rcpsp_activities
    out["cronograma_compacto"] = cron_compacto

    out["planejamento_detalhado"] = _v2_build_planejamento(spec, eap_by_id)

    # 6. bdi
    out["bdi"] = spec.get("bdi") or {}

    indiretos_detalhamento, equipes_indiretas = _v2_build_indiretos(spec)
    out["indiretos_detalhamento"] = indiretos_detalhamento
    out["equipes_indiretas"] = equipes_indiretas

    out.update(_v2_build_tail_fields(ref, spec))

    return out


