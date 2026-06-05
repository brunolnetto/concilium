"""Tool MCP criar_projeto_formulario — ADR-092.

Traduz uma lista de serviços em linguagem natural (QQP) para uma EAP com
cpu_ids resolvidos automaticamente, e cria o projeto se o mapeamento for
suficiente.

Fluxo:
    1. Para cada serviço, tenta mapear a descrição → cpu_id via cpu_mapper.
    2. Retorna preview com: itens mapeados, itens pendentes e scores.
    3. Se todos os itens tiverem cpu_id → cria projeto diretamente.
    4. Se houver itens não-mapeados → retorna preview para o agente corrigir
       (via buscar_cpu) e chamar criar_projeto_formulario novamente com
       cpu_ids explícitos nos itens pendentes.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.infrastructure.auth.permission_guard import permission
from concilium.presentation.mcp_server._context import (
    _lifecycle_coordinator,
    _projetos_root,
    _runtime,
    _wrap_response,
)
from concilium.presentation.mcp_server.rate_limit import mcp_rate_limit


# ── Helpers ───────────────────────────────────────────────────────────────────

def _suggest_cpu(descricao: str) -> tuple[str | None, int]:
    """Retorna (cpu_id, score) para a descrição.

    Score: 2=match por regra (keyword_rules.json), 1=match por similaridade de
    descrição no catálogo, 0=não mapeado.

    Prioridade:
      1. cpu_mapping_rules.json (keyword matching explícito)
      2. Busca por sobreposição de palavras nas descrições do catálogo
    """
    desc_upper = descricao.upper()

    # ── 1. Keyword rules (explícito) ─────────────────────────────────────────
    try:
        from concilium.infrastructure.catalog.mapping.cpu_mapper import _load_mapping_keywords
        keywords_map = _load_mapping_keywords()
        if keywords_map:
            for cpu_id, keywords in keywords_map.items():
                if all(kw in desc_upper for kw in keywords):
                    return cpu_id, 2
            for cpu_id, keywords in keywords_map.items():
                if any(kw in desc_upper for kw in keywords):
                    return cpu_id, 1
    except Exception:
        pass

    # ── 2. Fallback: sobreposição de palavras com descrições do catálogo ─────
    try:
        from concilium.presentation.mcp_server._context import _config_root
        import json as _json
        cpus_dir = _config_root() / "catalogos"
        # Busca o primeiro diretório de catálogo disponível
        catalog_cpus = None
        for cat in sorted(cpus_dir.iterdir()):
            cpus_path = cat / "cpus"
            if cpus_path.is_dir():
                catalog_cpus = cpus_path
                break

        if catalog_cpus:
            words = {w for w in desc_upper.split() if len(w) > 3}
            best_cpu, best_score = None, 0
            for f in catalog_cpus.glob("CPU-*.json"):
                try:
                    data = _json.loads(f.read_text(encoding="utf-8"))
                    cat_desc = (data.get("descricao") or "").upper()
                    cat_words = {w for w in cat_desc.split() if len(w) > 3}
                    overlap = len(words & cat_words)
                    if overlap > best_score:
                        best_score = overlap
                        cpu_id = data.get("codigo") or data.get("cpu_id") or f.stem
                        best_cpu = cpu_id
                except Exception:
                    continue
            if best_cpu and best_score >= 2:
                return best_cpu, 1
    except Exception:
        pass

    return None, 0


def _build_eap_items(servicos: list[dict]) -> tuple[list[dict], list[dict]]:
    """Constrói itens de EAP e retorna (mapeados, nao_mapeados).

    Cada serviço pode ter: descricao, quantidade, unidade, cpu_id (opcional),
    predecessores (opcional).
    """
    eap_items: list[dict] = []
    nao_mapeados: list[dict] = []

    for i, svc in enumerate(servicos, start=1):
        descricao = svc.get("descricao", "")
        quantidade = float(svc.get("quantidade", 1.0))
        unidade = svc.get("unidade", "un")
        predecessores = svc.get("predecessores", [])
        item_id = svc.get("item_id") or f"eap-1_{i}"

        # Usa cpu_id explícito do serviço se fornecido; caso contrário, busca automática
        cpu_id = svc.get("cpu_id") or None
        score = 2 if cpu_id else 0
        if not cpu_id:
            cpu_id, score = _suggest_cpu(descricao)

        item = {
            "item_id": item_id,
            "ordem": i,
            "descricao": descricao,
            "unidade": unidade,
            "quantitativo": quantidade,
            "predecessores": predecessores,
            "cpu_id": cpu_id or "",
            "_score": score,
        }

        if cpu_id:
            eap_items.append(item)
        else:
            nao_mapeados.append({**item, "cpu_id": None})

    return eap_items, nao_mapeados


# ── Registro ──────────────────────────────────────────────────────────────────

_UI_META = {
    "ui": {
        "resourceUri": "ui://concilium/formulario-qqp",
        "permissions": [],
        "csp": {"default-src": ["'self'"], "script-src": ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"]},
    }
}


def register(server: FastMCP) -> None:
    """Registra a tool criar_projeto_formulario no servidor MCP."""

    @server.tool()
    @permission("project:create")
    @mcp_rate_limit(calls=5, period_s=60)
    def criar_projeto_formulario(  # noqa: E741
        nome: str,
        contexto_id: str,
        tipo_obra: str,
        localizacao: str,
        data_inicio: str,
        servicos: list[dict],
        data_termino: str | None = None,
        coordenadas_lat: float = 0.0,
        coordenadas_lng: float = 0.0,
        dias_semana: int = 6,
        horas_dia: int = 8,
        objetivo_pool: str = "balanceado",
    ) -> dict[str, Any]:
        """Cria um projeto a partir de uma lista de serviços em linguagem natural (QQP).

        Resolve automaticamente cpu_id por descrição. Se houver itens não mapeados,
        retorna um preview para o agente corrigir antes de criar.

        Args:
            nome:            Nome do projeto (ex: "Lote 09/10 CE")
            contexto_id:     ID do contexto de cálculo. Use listar_contextos() para opções.
            tipo_obra:       "terraplenagem" | "pavimentacao" | "saneamento"
            localizacao:     "Cidade, UF" (ex: "Aracoiaba, CE")
            data_inicio:     "YYYY-MM-DD"
            servicos:        Lista de serviços. Cada item:
                             {
                               "descricao":   str,   # linguagem natural ou técnica
                               "quantidade":  float,
                               "unidade":     str,
                               "cpu_id":      str | None,  # fornecer se já conhecido
                               "predecessores": []          # opcional
                             }
            data_termino:    "YYYY-MM-DD" (opcional)
            coordenadas_lat/lng: para consulta climática (opcional, default 0)
            dias_semana:     regime de trabalho (default 6)
            horas_dia:       regime de trabalho (default 8)
            objetivo_pool:   "minimizar_prazo" | "minimizar_custo" | "balanceado"

        Returns:
            Se todos mapeados:
              {project_id, version, eap_preview, proxima_skill_sugerida}
            Se há não-mapeados:
              {status: "pendente", mapeados, nao_mapeados, instrucoes}
        """
        eap_mapeados, nao_mapeados = _build_eap_items(servicos)

        # ── Preview de mapeamento ──────────────────────────────────────────────

        mapeados_preview = [
            {
                "item_id": it["item_id"],
                "descricao": it["descricao"],
                "cpu_id": it["cpu_id"],
                "confianca": "alta" if it["_score"] == 2 else "media",
                "quantidade": it["quantitativo"],
                "unidade": it["unidade"],
            }
            for it in eap_mapeados
        ]

        # ── Itens sem mapeamento → devolver para agente corrigir ──────────────

        if nao_mapeados:
            return _wrap_response({
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
                    "Use buscar_cpu(termo) para encontrar o cpu_id correto para cada "
                    "item não mapeado. Em seguida, chame criar_projeto_formulario "
                    "novamente incluindo 'cpu_id' em cada serviço não mapeado."
                ),
            })

        # ── Todos mapeados → criar projeto ────────────────────────────────────

        rt = _runtime()
        proj_root = _projetos_root()
        proj_root.mkdir(parents=True, exist_ok=True)

        from concilium.infrastructure.storage.project import ProjectStore

        store = ProjectStore.init(proj_root, nome, contexto_id=contexto_id)
        v = store.new_version()

        # Remove campo interno _score antes de passar para a skill
        eap_clean = [
            {k: val for k, val in it.items() if k != "_score"}
            for it in eap_mapeados
        ]

        inputs_escopo = {
            "nome": nome,
            "tipo_obra": tipo_obra,
            "localizacao": localizacao,
            "coordenadas": {"lat": coordenadas_lat, "lng": coordenadas_lng},
            "regime_trabalho": {"dias_semana": dias_semana, "horas_dia": horas_dia},
            "data_inicio": data_inicio,
            "data_termino": data_termino or "",
            "versao_referencia_id": rt.load_contexto(contexto_id).referencia_id,
            "eap": eap_clean,
            "objetivo_pool": objetivo_pool,
        }

        try:
            coord = _lifecycle_coordinator()
            r = coord.avancar_projeto("01-escopo-e-eap", store, v, inputs=inputs_escopo)
        except Exception as e:
            return _wrap_response({
                "project_id": store.root.name,
                "version": v,
                "erro": str(e),
            })

        if r.has_errors:
            erros = [v.mensagem for v in r.validacoes if v.status == "ERRO"]
            return _wrap_response({
                "project_id": store.root.name,
                "version": v,
                "status": "erro_escopo",
                "erros": erros,
                "dica": "Verifique se os cpu_ids são válidos para o contexto escolhido.",
            })

        return _wrap_response({
            "status": "criado",
            "project_id": store.root.name,
            "version": v,
            "eap_preview": mapeados_preview,
            "total_itens": len(eap_mapeados),
            "proxima_skill_sugerida": "02-produtividade-climatica",
            "nota": (
                "Projeto criado com escopo EAP. "
                "Use avancar_pipeline para calcular praticabilidade climática e prosseguir."
            ),
        })

    # ADR-101: declarar _meta.ui para MCP Apps (Fase 1)
    try:
        tool = server._tool_manager._tools.get("criar_projeto_formulario")
        if tool is not None:
            tool.meta = _UI_META
    except Exception:
        pass
