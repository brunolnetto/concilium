"""Serviço de formulário QQP/EAP — ADR-092.

Lógica de negócio compartilhada entre a tool MCP e o endpoint REST:
  - Sugestão de CPU por descrição de serviço (keyword → catálogo)
  - Construção da estrutura EAP a partir de uma lista de serviços
  - Criação do projeto e execução da skill-01 (escopo-e-eap)

Prioridade de busca de CPU:
  1. cpu_mapping_rules.json — regras de keyword explícitas
  2. Sobreposição de palavras com descrições do catálogo
  3. Retorna None (agente/UI pede confirmação)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ── CPU suggestion ────────────────────────────────────────────────────────────


def _suggest_cpu_by_keywords(desc_upper: str) -> tuple[str | None, int] | None:
    """Tenta mapear via cpu_mapping_rules.json; retorna None se nenhuma regra aplicável."""
    try:
        from concilium.infrastructure.catalog.mapping.cpu_mapper import _load_mapping_keywords

        rules = _load_mapping_keywords()
        if rules:
            for cpu_id, kws in rules.items():
                if all(kw in desc_upper for kw in kws):
                    return cpu_id, 2
            for cpu_id, kws in rules.items():
                if any(kw in desc_upper for kw in kws):
                    return cpu_id, 1
    except Exception:
        pass
    return None


def _resolve_catalog_cpus_dir(config_root: Path | None) -> Path | None:
    """Localiza o diretório de CPUs do primeiro catálogo disponível."""
    if config_root is None:
        from concilium.infrastructure.settings import get_storage

        root = get_storage().config_root
    else:
        root = config_root

    cpus_dir = root / "catalogos"
    for cat in sorted(cpus_dir.iterdir()):
        p = cat / "cpus"
        if p.is_dir():
            return p
    return None


def _find_best_catalog_cpu(catalog_cpus: Path, words: set[str]) -> tuple[str | None, int]:
    """Percorre os arquivos CPU-*.json do catálogo e retorna o de maior sobreposição de palavras."""
    best_cpu: str | None = None
    best_score = 0
    for f in catalog_cpus.glob("CPU-*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            cat_desc = (data.get("descricao") or "").upper()
            cat_words = {w for w in cat_desc.split() if len(w) > 3}
            overlap = len(words & cat_words)
            if overlap > best_score:
                best_score = overlap
                best_cpu = data.get("codigo") or data.get("cpu_id") or f.stem
        except Exception:
            continue
    return best_cpu, best_score


def _suggest_cpu_by_catalog_overlap(words: set[str], config_root: Path | None) -> tuple[str | None, int]:
    """Sugere cpu_id pela sobreposição de palavras com descrições do catálogo."""
    try:
        catalog_cpus = _resolve_catalog_cpus_dir(config_root)
        if catalog_cpus:
            best_cpu, best_score = _find_best_catalog_cpu(catalog_cpus, words)
            if best_cpu and best_score >= 2:
                return best_cpu, 1
    except Exception:
        pass
    return None, 0


def suggest_cpu(descricao: str, config_root: Path | None = None) -> tuple[str | None, int]:
    """Mapeia uma descrição de serviço para um cpu_id.

    Returns:
        (cpu_id | None, score)  — score: 2=keyword rule, 1=catalog overlap, 0=not found
    """
    desc_upper = descricao.upper()

    # ── 1. Keyword rules ──────────────────────────────────────────────────────
    hit = _suggest_cpu_by_keywords(desc_upper)
    if hit is not None:
        return hit

    # ── 2. Catalog word overlap ───────────────────────────────────────────────
    words = {w for w in desc_upper.split() if len(w) > 3}
    if not words:
        return None, 0

    return _suggest_cpu_by_catalog_overlap(words, config_root)


# ── EAP building ──────────────────────────────────────────────────────────────


def _resolve_item_cpu(svc: dict[str, Any], descricao: str, config_root: Path | None) -> tuple[str | None, int]:
    """Resolve cpu_id/score de um serviço: usa cpu_id explícito ou sugere a partir da descrição."""
    cpu_id: str | None = svc.get("cpu_id") or None
    score = 2 if cpu_id else 0
    if not cpu_id:
        cpu_id, score = suggest_cpu(descricao, config_root)
    return cpu_id, score


def _build_eap_item(svc: dict[str, Any], ordem: int, config_root: Path | None) -> dict[str, Any]:
    """Constrói um item de EAP a partir de um serviço, resolvendo cpu_id/score/confiança."""
    descricao = str(svc.get("descricao") or "")
    quantidade = float(svc.get("quantidade") or 1.0)
    unidade = str(svc.get("unidade") or "un")
    predecessores = svc.get("predecessores") or []
    item_id = str(svc.get("item_id") or f"eap-1_{ordem}")

    cpu_id, score = _resolve_item_cpu(svc, descricao, config_root)

    return {
        "item_id": item_id,
        "ordem": ordem,
        "descricao": descricao,
        "unidade": unidade,
        "quantitativo": quantidade,
        "predecessores": predecessores,
        "cpu_id": cpu_id or "",
        "_score": score,
        "_confianca": "alta" if score == 2 else ("media" if score == 1 else "nenhuma"),
    }


def build_eap(
    servicos: list[dict[str, Any]],
    config_root: Path | None = None,
) -> dict[str, Any]:
    """Mapeia serviços para itens de EAP com sugestões de cpu_id.

    Args:
        servicos: Lista de dicts com chaves:
            descricao, quantidade, unidade, cpu_id (opcional), predecessores (opcional)
        config_root: Raiz de configuração para busca no catálogo

    Returns:
        {
          "mapeados":     [EAP item dict com cpu_id resolvido],
          "nao_mapeados": [dicts sem cpu_id],
          "total":        int,
        }
    """
    mapeados: list[dict] = []
    nao_mapeados: list[dict] = []

    for i, svc in enumerate(servicos, start=1):
        item = _build_eap_item(svc, i, config_root)

        if item["cpu_id"]:
            mapeados.append(item)
        else:
            nao_mapeados.append({**item, "cpu_id": None})

    return {
        "mapeados": mapeados,
        "nao_mapeados": nao_mapeados,
        "total": len(servicos),
    }


# ── Project creation ──────────────────────────────────────────────────────────


def _build_mapeados_preview(mapeados: list[dict]) -> list[dict]:
    """Resumo dos itens mapeados para preview na resposta."""
    return [
        {
            "item_id": it["item_id"],
            "descricao": it["descricao"],
            "cpu_id": it["cpu_id"],
            "confianca": it["_confianca"],
            "quantidade": it["quantitativo"],
            "unidade": it["unidade"],
        }
        for it in mapeados
    ]


def _build_pendente_mapeamento_response(
    servicos: list[dict[str, Any]], mapeados_preview: list[dict], nao_mapeados: list[dict]
) -> dict[str, Any]:
    """Monta a resposta quando ainda há itens sem cpu_id resolvido."""
    return {
        "status": "pendente_mapeamento",
        "total_servicos": len(servicos),
        "mapeados": mapeados_preview,
        "nao_mapeados": [
            {
                "item_id": it["item_id"],
                "descricao": it["descricao"],
                "quantidade": it["quantitativo"],
                "unidade": it["unidade"],
            }
            for it in nao_mapeados
        ],
        "instrucoes": (
            "Forneça cpu_id para os itens não mapeados e repita a chamada. "
            "Use buscar_cpu(termo) para encontrar o código correto."
        ),
    }


def _resolve_projetos_root(projetos_root: Path | None) -> Path:
    """Resolve a raiz de projetos, usando o storage configurado como fallback."""
    if projetos_root is None:
        from concilium.infrastructure.settings import get_storage

        projetos_root = get_storage().projects_root
        if projetos_root is None:
            raise RuntimeError("CONCILIUM__PROJECTS_ROOT não configurado")
    return projetos_root


def _create_project_store_and_plan(
    projetos_root: Path,
    nome: str,
    contexto_id: str,
    tipo_obra: str,
    localizacao: str,
    coordenadas_lat: float,
    coordenadas_lng: float,
    data_inicio: str,
    data_termino: str,
    dias_semana: int,
    horas_dia: int,
    horas_improdutivas_dia: float = 0.5,
) -> tuple[Any, str, Any]:
    """Inicializa o ProjectStore e cria escopo+plano principal (ADR-031)."""
    from concilium.infrastructure.storage.project import ProjectStore

    projetos_root.mkdir(parents=True, exist_ok=True)
    store = ProjectStore.init(projetos_root, nome, contexto_id=contexto_id)

    escopo_id = "esc-principal"
    es = store.create_escopo(
        escopo_id=escopo_id,
        nome=nome,
        tipo_obra=tipo_obra,
        localizacao=localizacao,
        coordenadas_lat=coordenadas_lat,
        coordenadas_lng=coordenadas_lng,
        data_inicio=data_inicio,
        data_termino=data_termino or "",
        dias_semana=dias_semana,
        horas_dia=horas_dia,
        horas_improdutivas_dia=horas_improdutivas_dia,
    )
    ps = es.create_plan(nome="Plano Principal")
    return store, escopo_id, ps


def _run_escopo_skill(
    rt: Any, store: Any, ps: Any, inputs_escopo: dict[str, Any], escopo_id: str
) -> tuple[Any | None, dict[str, Any] | None]:
    """Executa a skill 01-escopo-e-eap. Retorna (resultado, None) ou (None, resposta_de_erro)."""
    try:
        from concilium.application.orchestrators.lifecycle_coordinator import LifecycleCoordinator
        from concilium.infrastructure.storage.file_project_repository import FileProjectHandle

        coord = LifecycleCoordinator(rt)
        r = coord.avancar_plano("01-escopo-e-eap", FileProjectHandle(store), ps, inputs=inputs_escopo)
    except Exception as exc:
        return None, {"status": "erro", "project_id": store.root.name, "escopo_id": escopo_id, "erro": str(exc)}

    if r.has_errors:
        erros = [val.mensagem for val in r.validacoes if val.status == "ERRO"]
        return None, {
            "status": "erro_escopo",
            "project_id": store.root.name,
            "escopo_id": escopo_id,
            "plano_id": ps.plano_id,
            "erros": erros,
        }

    return r, None


def criar_projeto(
    nome: str,
    contexto_id: str,
    tipo_obra: str,
    localizacao: str,
    data_inicio: str,
    servicos: list[dict[str, Any]],
    data_termino: str = "",
    coordenadas_lat: float = 0.0,
    coordenadas_lng: float = 0.0,
    dias_semana: int = 6,
    horas_dia: int = 8,
    horas_improdutivas_dia: float = 0.5,
    objetivo_pool: str = "balanceado",
    projetos_root: Path | None = None,
    config_root: Path | None = None,
) -> dict[str, Any]:
    """Cria um projeto a partir de serviços em linguagem natural.

    Returns dict com chaves:
      status: "criado" | "pendente_mapeamento" | "erro"
      Se criado: project_id, version, eap_preview
      Se pendente: mapeados, nao_mapeados, instrucoes
      Se erro: erro
    """
    eap_result = build_eap(servicos, config_root)
    mapeados = eap_result["mapeados"]
    nao_mapeados = eap_result["nao_mapeados"]

    # Resumo de mapeamento para preview
    mapeados_preview = _build_mapeados_preview(mapeados)

    if nao_mapeados:
        return _build_pendente_mapeamento_response(servicos, mapeados_preview, nao_mapeados)

    # Todos mapeados → criar projeto
    from concilium.application.runtime import Runtime
    from concilium.infrastructure.settings import get_storage

    projetos_root = _resolve_projetos_root(projetos_root)

    # ADR-031: cria estrutura de escopo+plano para compatibilidade com disparar_pipeline
    store, escopo_id, ps = _create_project_store_and_plan(
        projetos_root,
        nome,
        contexto_id,
        tipo_obra,
        localizacao,
        coordenadas_lat,
        coordenadas_lng,
        data_inicio,
        data_termino,
        dias_semana,
        horas_dia,
        horas_improdutivas_dia,
    )

    eap_clean = [{k: val for k, val in it.items() if not k.startswith("_")} for it in mapeados]

    # Runtime exige config_root; sem o fallback isso quebrava com TypeError em
    # toda chamada real (os testes mockavam Runtime exatamente neste seam).
    rt = Runtime(config_root if config_root is not None else get_storage().config_root)
    inputs_escopo: dict[str, Any] = {
        "nome": nome,
        "tipo_obra": tipo_obra,
        "localizacao": localizacao,
        "coordenadas": {"lat": coordenadas_lat, "lng": coordenadas_lng},
        "regime_trabalho": {
            "dias_semana": dias_semana,
            "horas_dia": horas_dia,
            "horas_improdutivas_dia": horas_improdutivas_dia,
        },
        "data_inicio": data_inicio,
        "data_termino": data_termino,
        "versao_referencia_id": rt.load_contexto(contexto_id).referencia_id,
        "eap": eap_clean,
        "objetivo_pool": objetivo_pool,
    }

    _r, error = _run_escopo_skill(rt, store, ps, inputs_escopo, escopo_id)
    if error is not None:
        return error

    return {
        "status": "criado",
        "project_id": store.root.name,
        "escopo_id": escopo_id,
        "plano_id": ps.plano_id,
        "eap_preview": mapeados_preview,
        "total_itens": len(mapeados),
        "proxima_skill_sugerida": "02-produtividade-climatica",
    }
