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
from concilium.presentation.mcp._context import (
    _lifecycle_coordinator,
    _projetos_root,
    _runtime,
    _wrap_response,
)
from concilium.presentation.mcp.rate_limit import mcp_rate_limit

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
        import json as _json

        from concilium.presentation.mcp._context import _config_root

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


def _normalize_procurement_intent(value: str | None) -> str:
    """Normaliza intenção de procurement para {rfi, rfp}."""
    normalized = (value or "rfi").strip().lower()
    if normalized in {"rfi", "rfp"}:
        return normalized
    return "rfi"


def _procurement_context(intent: str) -> dict[str, str]:
    """Retorna contexto semântico de procurement para a resposta MCP."""
    if intent == "rfp":
        return {
            "intent": "rfp",
            "fase": "comparacao_tecnico_economica",
            "metodo_custo": "operacional_com_cronograma",
            "resumo": (
                "RFP considera cronograma, praticabilidade climatica e tempo nao-produtivo. "
                "O custo total tende a ser maior que o catalogo puro."
            ),
        }
    return {
        "intent": "rfi",
        "fase": "exploracao_inicial",
        "metodo_custo": "catalogo_pu_x_quantitativo",
        "resumo": (
            "RFI usa precificacao de catalogo (PU x quantitativo), sem penalidades operacionais "
            "de clima/ociosidade para comparacao inicial de mercado."
        ),
    }


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
    def criar_projeto(  # noqa: E741
        nome: str = "",
        contexto_id: str = "",
        tipo_obra: str = "",
        localizacao: str = "",
        data_inicio: str = "",
        servicos: list[dict] | None = None,
        data_termino: str | None = None,
        procurement_intent: str = "rfi",
        coordenadas_lat: float = 0.0,
        coordenadas_lng: float = 0.0,
        dias_semana: int = 6,
        horas_dia: int = 8,
        objetivo_pool: str = "balanceado",
        spec: dict | None = None,
    ) -> dict[str, Any]:
        """Cria um novo projeto via formulário (serviços em linguagem natural) ou spec JSON.

        Quando spec=None: usa o modo formulário — resolve cpu_ids automaticamente por NLP.
        Quando spec={...}: usa o modo spec — lê um ProjetoSpec JSON completo com EAP,
        cronograma e regime tributário (equivalente ao criar_projeto_spec anterior).

        Use o modo formulário quando os serviços estão em linguagem natural e cpu_ids não são conhecidos.
        Use o modo spec quando o projeto está definido em um documento JSON (ProjetoSpec).

        Alternativa: iniciar_orcamento (quando cpu_ids já são conhecidos).

        """
        # Route to spec mode if spec dict is provided
        if spec is not None:
            from concilium.infrastructure.storage.project import ProjectStore
            from concilium.presentation.mcp.tools.spec import (
                _resolve_tributario,
                _validate_spec,
            )

            erros_spec = _validate_spec(spec)
            if erros_spec:
                return {"erro": "Spec inválido", "detalhes": erros_spec[:10]}
            meta = spec["meta"]
            rt = _runtime()
            try:
                rt.load_contexto(meta["contexto_id"])
            except Exception as e:
                return {"erro": f"contexto_id inválido: {e}"}
            tributario = _resolve_tributario(meta, rt)
            regime = meta.get("regime_trabalho") or {}
            _dias = int(regime.get("dias_semana", 6))
            _horas = int(regime.get("horas_dia", 8))
            proj_root = _projetos_root()
            proj_root.mkdir(parents=True, exist_ok=True)
            store = ProjectStore.init(proj_root, meta["nome"], contexto_id=meta["contexto_id"])
            coord = _lifecycle_coordinator()
            escopos_criados = []
            for escopo_spec in spec["escopos"]:
                eid = escopo_spec["escopo_id"]
                try:
                    es = store.create_escopo(
                        escopo_id=eid,
                        nome=escopo_spec["nome"],
                        tipo_obra=meta["tipo_obra"],
                        localizacao=meta["localizacao"],
                        coordenadas_lat=meta["coordenadas"]["lat"],
                        coordenadas_lng=meta["coordenadas"]["lng"],
                        data_inicio=meta["data_inicio"],
                        data_termino=meta["data_termino"],
                        dias_semana=_dias,
                        horas_dia=_horas,
                    )
                except Exception as e:
                    return {"erro": f"Falha ao criar escopo '{eid}': {e}"}
                ps = es.create_plan(nome="Plano Principal")
                inputs_01 = {
                    "nome": meta["nome"],
                    "tipo_obra": meta["tipo_obra"],
                    "localizacao": meta["localizacao"],
                    "coordenadas": meta["coordenadas"],
                    "regime_trabalho": {"dias_semana": _dias, "horas_dia": _horas},
                    "data_inicio": meta["data_inicio"],
                    "data_termino": meta["data_termino"],
                    "versao_referencia_id": rt.load_contexto(meta["contexto_id"]).referencia_id,
                    "eap": escopo_spec["eap"],
                    "regime_tributario": tributario,
                }
                if escopo_spec.get("cronograma"):
                    inputs_01["_cronograma_spec"] = escopo_spec["cronograma"]
                try:
                    r = coord.avancar_plano("01-escopo-e-eap", store, ps, inputs=inputs_01)
                    status_01 = "ERRO" if r.has_errors else "OK"
                    erros_01 = [
                        {"codigo": v.codigo, "mensagem": v.mensagem} for v in r.validacoes if v.status == "ERRO"
                    ]
                except Exception as e:
                    status_01, erros_01 = "ERRO", [{"codigo": "EXCECAO", "mensagem": str(e)}]
                escopos_criados.append(
                    {"escopo_id": eid, "plano_id": ps.plano_id, "status_skill_01": status_01, "erros": erros_01}
                )
            sucesso = all(e["status_skill_01"] == "OK" for e in escopos_criados)
            return _wrap_response(
                {
                    "project_id": store.root.name,
                    "escopos": escopos_criados,
                    "tributario_efetivo": tributario,
                    "proxima_skill_sugerida": "02-produtividade-climatica" if sucesso else None,
                }
            )

        # Formulário mode (original criar_projeto_formulario logic below)
        if not nome or not contexto_id or not tipo_obra or not localizacao or not data_inicio:
            return _wrap_response(
                {"erro": "Parâmetros obrigatórios: nome, contexto_id, tipo_obra, localizacao, data_inicio"}
            )
        if servicos is None:
            servicos = []
        # ── original formulario body continues ──
        """Use quando os serviços estão em linguagem natural e os cpu_ids não são conhecidos.

        Resolve automaticamente cpu_id por descrição de texto (NLP). Se houver itens não
        mapeados, retorna um preview para correção antes de criar. Alternativas: iniciar_orcamento
        (quando os cpu_ids já são conhecidos) ou criar_projeto_spec (spec JSON completo com
        cronograma e regime tributário).

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
            procurement_intent: "rfi" | "rfp" (default "rfi")
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
        intent = _normalize_procurement_intent(procurement_intent)
        intent_ctx = _procurement_context(intent)
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
            return _wrap_response(
                {
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
                    "procurement_context": intent_ctx,
                }
            )

        # ── Todos mapeados → criar projeto ────────────────────────────────────

        rt = _runtime()
        proj_root = _projetos_root()
        proj_root.mkdir(parents=True, exist_ok=True)

        from concilium.infrastructure.storage.project import ProjectStore

        store = ProjectStore.init(proj_root, nome, contexto_id=contexto_id)
        store.update_meta(procurement_intent=intent)

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

        # Remove campo interno _score antes de passar para a skill
        eap_clean = [{k: val for k, val in it.items() if k != "_score"} for it in eap_mapeados]

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
            "procurement_intent": intent,
        }

        try:
            coord = _lifecycle_coordinator()
            r = coord.avancar_plano("01-escopo-e-eap", store, ps, inputs=inputs_escopo)
        except Exception as e:
            return _wrap_response(
                {
                    "project_id": store.root.name,
                    "escopo_id": escopo_id,
                    "plano_id": ps.plano_id,
                    "erro": str(e),
                }
            )

        if r.has_errors:
            erros = [val.mensagem for val in r.validacoes if val.status == "ERRO"]
            return _wrap_response(
                {
                    "project_id": store.root.name,
                    "escopo_id": escopo_id,
                    "plano_id": ps.plano_id,
                    "status": "erro_escopo",
                    "erros": erros,
                    "dica": "Verifique se os cpu_ids são válidos para o contexto escolhido.",
                }
            )

        return _wrap_response(
            {
                "status": "criado",
                "project_id": store.root.name,
                "escopo_id": escopo_id,
                "plano_id": ps.plano_id,
                "eap_preview": mapeados_preview,
                "total_itens": len(eap_mapeados),
                "proxima_skill_sugerida": "02-produtividade-climatica",
                "nota": (
                    "Projeto criado com escopo e plano (ADR-031). "
                    "Use disparar_pipeline para calcular praticabilidade climática e prosseguir."
                ),
                "procurement_context": intent_ctx,
            }
        )

    # ADR-101: declarar _meta.ui para MCP Apps (Fase 1)
    try:
        tool = server._tool_manager._tools.get("criar_projeto_formulario")
        if tool is not None:
            tool.meta = _UI_META
    except Exception:
        pass
