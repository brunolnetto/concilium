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


def suggest_cpu(descricao: str, config_root: Path | None = None) -> tuple[str | None, int]:
    """Mapeia uma descrição de serviço para um cpu_id.

    Returns:
        (cpu_id | None, score)  — score: 2=keyword rule, 1=catalog overlap, 0=not found
    """
    desc_upper = descricao.upper()

    # ── 1. Keyword rules ──────────────────────────────────────────────────────
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

    # ── 2. Catalog word overlap ───────────────────────────────────────────────
    words = {w for w in desc_upper.split() if len(w) > 3}
    if not words:
        return None, 0

    try:
        if config_root is None:
            from concilium.infrastructure.settings import get_storage

            root = get_storage().config_root
        else:
            root = config_root

        cpus_dir = root / "catalogos"
        catalog_cpus: Path | None = None
        for cat in sorted(cpus_dir.iterdir()):
            p = cat / "cpus"
            if p.is_dir():
                catalog_cpus = p
                break

        if catalog_cpus:
            best_cpu, best_score = None, 0
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
            if best_cpu and best_score >= 2:
                return best_cpu, 1
    except Exception:
        pass

    return None, 0


# ── EAP building ──────────────────────────────────────────────────────────────


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
        descricao = str(svc.get("descricao") or "")
        quantidade = float(svc.get("quantidade") or 1.0)
        unidade = str(svc.get("unidade") or "un")
        predecessores = svc.get("predecessores") or []
        item_id = str(svc.get("item_id") or f"eap-1_{i}")

        cpu_id: str | None = svc.get("cpu_id") or None
        score = 2 if cpu_id else 0
        if not cpu_id:
            cpu_id, score = suggest_cpu(descricao, config_root)

        item: dict[str, Any] = {
            "item_id": item_id,
            "ordem": i,
            "descricao": descricao,
            "unidade": unidade,
            "quantitativo": quantidade,
            "predecessores": predecessores,
            "cpu_id": cpu_id or "",
            "_score": score,
            "_confianca": "alta" if score == 2 else ("media" if score == 1 else "nenhuma"),
        }

        if cpu_id:
            mapeados.append(item)
        else:
            nao_mapeados.append({**item, "cpu_id": None})

    return {
        "mapeados": mapeados,
        "nao_mapeados": nao_mapeados,
        "total": len(servicos),
    }


# ── Project creation ──────────────────────────────────────────────────────────


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
    mapeados_preview = [
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

    if nao_mapeados:
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

    # Todos mapeados → criar projeto
    from concilium.application.runtime import Runtime
    from concilium.infrastructure.settings import get_storage
    from concilium.infrastructure.storage.project import ProjectStore

    if projetos_root is None:
        projetos_root = get_storage().projects_root
        if projetos_root is None:
            raise RuntimeError("CONCILIUM__PROJECTS_ROOT não configurado")

    projetos_root.mkdir(parents=True, exist_ok=True)
    store = ProjectStore.init(projetos_root, nome, contexto_id=contexto_id)

    # ADR-031: cria estrutura de escopo+plano para compatibilidade com disparar_pipeline
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
    )
    ps = es.create_plan(nome="Plano Principal")

    eap_clean = [{k: val for k, val in it.items() if not k.startswith("_")} for it in mapeados]

    # Runtime exige config_root; sem o fallback isso quebrava com TypeError em
    # toda chamada real (os testes mockavam Runtime exatamente neste seam).
    rt = Runtime(config_root if config_root is not None else get_storage().config_root)
    inputs_escopo: dict[str, Any] = {
        "nome": nome,
        "tipo_obra": tipo_obra,
        "localizacao": localizacao,
        "coordenadas": {"lat": coordenadas_lat, "lng": coordenadas_lng},
        "regime_trabalho": {"dias_semana": dias_semana, "horas_dia": horas_dia},
        "data_inicio": data_inicio,
        "data_termino": data_termino,
        "versao_referencia_id": rt.load_contexto(contexto_id).referencia_id,
        "eap": eap_clean,
        "objetivo_pool": objetivo_pool,
    }

    try:
        from concilium.application.orchestrators.lifecycle_coordinator import LifecycleCoordinator
        from concilium.infrastructure.storage.file_project_repository import FileProjectHandle

        coord = LifecycleCoordinator(rt)
        r = coord.avancar_plano("01-escopo-e-eap", FileProjectHandle(store), ps, inputs=inputs_escopo)
    except Exception as exc:
        return {"status": "erro", "project_id": store.root.name, "escopo_id": escopo_id, "erro": str(exc)}

    if r.has_errors:
        erros = [val.mensagem for val in r.validacoes if val.status == "ERRO"]
        return {
            "status": "erro_escopo",
            "project_id": store.root.name,
            "escopo_id": escopo_id,
            "plano_id": ps.plano_id,
            "erros": erros,
        }

    return {
        "status": "criado",
        "project_id": store.root.name,
        "escopo_id": escopo_id,
        "plano_id": ps.plano_id,
        "eap_preview": mapeados_preview,
        "total_itens": len(mapeados),
        "proxima_skill_sugerida": "02-produtividade-climatica",
    }
