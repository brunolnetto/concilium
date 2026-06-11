"""Ferramentas MCP de gestão de projetos — listar, criar, status, aprovar."""

from __future__ import annotations

import json
from datetime import UTC
from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.infrastructure.storage.project import ProjectStore
from concilium.presentation.mcp._context import (
    _lifecycle_coordinator,
    _project,
    _projetos_root,
    _runtime,
    _wrap_response,
)


def register(server: FastMCP) -> None:
    """Registra as ferramentas de projeto no servidor MCP."""

    # ── 2. Listar projetos existentes ─────────────────────────────────────
    @server.tool()
    def listar_projetos() -> dict[str, Any]:
        """Lista os projetos existentes no sistema com versão atual e contexto."""
        proj_root = _projetos_root()
        if not proj_root.exists():
            return _wrap_response({"projetos": [], "projetos_root": str(proj_root)})

        out = []
        for p in sorted(proj_root.iterdir()):
            if not p.is_dir():
                continue
            try:
                store = ProjectStore(p)
                meta = store.meta
                out.append(
                    {
                        "id": p.name,
                        "nome": meta.get("nome", "?"),
                        "contexto_id": meta.get("contexto_id"),
                        "current_version": meta.get("current_version"),
                        "versoes": store.list_versions(),
                    }
                )
            except Exception as e:
                out.append({"id": p.name, "erro": str(e)})
        return _wrap_response({"projetos": out, "projetos_root": str(proj_root)})

    # ── 3. Iniciar orçamento ─────────────────────────────────────────────
    @server.tool()
    def iniciar_orcamento(
        nome: str,
        contexto_id: str,
        tipo_obra: str,
        localizacao: str,
        coordenadas_lat: float,
        coordenadas_lng: float,
        data_inicio: str,
        data_termino: str,
        eap: list[dict[str, Any]],
        dias_semana: int = 6,
        horas_dia: int = 8,
    ) -> dict[str, Any]:
        """Use quando a EAP já está completamente definida com cpu_ids conhecidos.

        Alternativas: criar_projeto_formulario (quando os serviços estão em linguagem natural
        e os cpu_ids precisam ser resolvidos automaticamente) ou criar_projeto_spec (quando o
        projeto completo — incluindo cronograma e regime tributário — está em um documento JSON).

        Args:
            nome: Nome legível do projeto (ex.: "Lote 09/10 CE")
            contexto_id: ID do contexto (ex.: "mendeslobo"). Use listar_contextos para opções.
            tipo_obra: "terraplenagem" | "pavimentacao" | "saneamento"
            localizacao: Cidade, UF (ex.: "Aracoiaba, CE")
            coordenadas_lat / lng: Coordenadas para consulta climática e calendário
            data_inicio / data_termino: ISO dates "YYYY-MM-DD"
            eap: Lista de itens com item_id, cpu_id, quantitativo e predecessores

        Returns:
            project_id, escopo_id, plano_id, status_skill_01, proxima_skill_sugerida
        """
        rt = _runtime()
        proj_root = _projetos_root()
        proj_root.mkdir(parents=True, exist_ok=True)

        store = ProjectStore.init(proj_root, nome, contexto_id=contexto_id)

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
            data_termino=data_termino,
            dias_semana=dias_semana,
            horas_dia=horas_dia,
        )
        ps = es.create_plan(nome="Plano Principal")

        inputs_escopo = {
            "nome": nome,
            "tipo_obra": tipo_obra,
            "localizacao": localizacao,
            "coordenadas": {"lat": coordenadas_lat, "lng": coordenadas_lng},
            "regime_trabalho": {"dias_semana": dias_semana, "horas_dia": horas_dia},
            "data_inicio": data_inicio,
            "data_termino": data_termino,
            "versao_referencia_id": rt.load_contexto(contexto_id).referencia_id,
            "eap": eap,
        }

        executadas = []
        try:
            # ADR-035: Usa o Coordenador para garantir governança (ADR-031: via plano)
            coord = _lifecycle_coordinator()
            r = coord.avancar_plano("01-escopo-e-eap", store, ps, inputs=inputs_escopo)

            executadas.append(
                {
                    "skill": "01-escopo-e-eap",
                    "status": "ERRO" if r.has_errors else "OK",
                    "validacoes": [
                        {"codigo": x.codigo, "status": x.status} for x in r.validacoes if x.status == "ERRO"
                    ],
                }
            )
            if r.has_errors:
                return {
                    "project_id": store.root.name,
                    "escopo_id": escopo_id,
                    "plano_id": ps.plano_id,
                    "skills_executadas": executadas,
                    "erro": "Skill 01-escopo-e-eap falhou",
                }
        except Exception as e:
            return {"project_id": store.root.name, "escopo_id": escopo_id, "erro": str(e)}

        return {
            "project_id": store.root.name,
            "escopo_id": escopo_id,
            "plano_id": ps.plano_id,
            "skills_executadas": executadas,
            "proxima_skill_sugerida": "02-produtividade-climatica",
            "nota": (
                "Projeto criado com escopo e plano (ADR-031). "
                "Próximo passo: disparar_pipeline para calcular praticabilidade climática."
            ),
        }

    # ── 6. Status ────────────────────────────────────────────────────────
    @server.tool()
    def consultar_status(project_id: str) -> dict[str, Any]:
        """Retorna estado atual do projeto: escopos/plano ativo, skills executadas, integridade do pipeline."""
        store = _project(project_id)
        meta = store.meta
        v = meta.get("current_version")
        out: dict[str, Any] = {
            "project_id": project_id,
            "nome": meta.get("nome"),
            "contexto_id": meta.get("contexto_id"),
            "current_version": v,
            "versoes": store.list_versions(),
        }

        # NEP-039 D4: expõe proveniência de benchmark quando o projeto é derivado
        if meta.get("derivado_de_benchmark"):
            out["proveniencia_benchmark"] = {
                "derivado_de_benchmark": meta.get("derivado_de_benchmark"),
                "benchmark_versao": meta.get("benchmark_versao"),
                "benchmark_execution_id": meta.get("benchmark_execution_id"),
            }

        # ADR-031: expõe escopos e plano ativo para projetos sem current_version (flat)
        try:
            escopos = store.list_escopos()
            if escopos:
                escopo_ativo = escopos[0] if len(escopos) == 1 else None
                plano_ativo = None
                skills_plano: list[dict] = []
                canonical_plano = None
                if escopo_ativo:
                    try:
                        es = store.escopo(escopo_ativo)
                        active_plan = es.active_plan()
                        if active_plan:
                            plano_ativo = active_plan.plano_id
                            for line in active_plan.read_invocations():
                                skills_plano.append(
                                    {"skill": line.get("skill"), "status": line.get("status"), "ts": line.get("ts")}
                                )
                            canonical_plano = active_plan.load_canonical()
                    except Exception:
                        pass
                out["escopos"] = escopos
                if escopo_ativo:
                    out["escopo_ativo"] = escopo_ativo
                if plano_ativo:
                    out["plano_ativo"] = plano_ativo
                if skills_plano:
                    out["invocations"] = skills_plano
                if canonical_plano and canonical_plano.resultado:
                    res = canonical_plano.resultado
                    out["resultado_atual"] = {
                        "preco_venda": res.venda.total_com_bdi,
                        "custo_total": res.custo.total,
                        "margem_pct": res.margem_pct,
                        "status_margem": res.status_margem,
                    }
                if canonical_plano:
                    out["pipeline_integridade"] = canonical_plano.pipeline_integridade or "PARCIAL"
        except Exception:
            pass

        if v:
            log_path = store.version_path(v) / store.INVOCATIONS_LOG
            executadas: list[dict] = []
            skills_com_erro: list[str] = []
            if log_path.exists():
                for line in log_path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        try:
                            entry = json.loads(line)
                            skill_name = entry.get("skill", "")
                            status = entry.get("status", "")
                            executadas.append({"skill": skill_name, "status": status, "ts": entry.get("ts")})
                            if status == "ERRO":
                                skills_com_erro.append(skill_name)
                        except json.JSONDecodeError:
                            pass
            out["invocations"] = executadas

            canonical = store.load_canonical(v)

            # ADR-022: integridade e taint — exibidos PRIMEIRO para evitar que dados
            # corrompidos sejam consumidos pelo agente sem aviso explícito.
            if canonical:
                blocked = canonical.pipeline_blocked_from or []
                integridade = canonical.pipeline_integridade
                if not integridade:
                    # Derivação compatível para canônicos antigos sem o campo
                    if blocked:
                        integridade = "CORROMPIDO"
                    elif skills_com_erro:
                        integridade = "PARCIAL"
                    else:
                        integridade = "COMPLETO"
                out["pipeline_integridade"] = integridade
                if blocked:
                    out["pipeline_blocked_from"] = blocked
                    out["aviso_integridade"] = (
                        f"⚠️  PIPELINE CORROMPIDO — skills GATE falharam: {blocked}. "
                        "Resultados financeiros NÃO devem ser usados para decisão de negócio. "
                        "Corrija e re-execute a partir do checkpoint válido."
                    )
                if canonical.resultado:
                    res = canonical.resultado
                    resultado_info: dict[str, Any] = {
                        "preco_venda": res.venda.total_com_bdi,
                        "custo_total": res.custo.total,
                        "margem_pct": res.margem_pct,
                        "status_margem": res.status_margem,
                    }
                    if integridade == "CORROMPIDO":
                        resultado_info["AVISO"] = "Valores baseados em pipeline corrompido — inválidos"
                    out["resultado_atual"] = resultado_info

        return _wrap_response(out)

    # ── 7. Aprovar plano (ADR-031) ────────────────────────────────────────────
    @server.tool()
    def aprovar_versao(project_id: str, escopo_id: str | None = None, plano_id: str | None = None) -> dict[str, Any]:
        """Aprova o plano ativo do projeto (operação irreversível — confirmar com o usuário).

        Arquiva os planos alternativos do escopo e congela o plano aprovado.
        Use consultar_estrutura_projeto para obter escopo_id e plano_id antes de chamar.
        """
        from concilium.presentation.mcp.tools.escopo import _resolve_escopo_id

        store = _project(project_id)
        try:
            eid = _resolve_escopo_id(store, escopo_id)
            es = store.escopo(eid)
            pid = plano_id or (es.active_plan().plano_id if es.active_plan() else None)
            if not pid:
                return {"erro": f"Nenhum plano ativo no escopo '{eid}'. Informe plano_id."}
            arquivados = es.approve_plan(pid)
        except Exception as e:
            return {"erro": str(e)}

        return {
            "project_id": project_id,
            "escopo_id": eid,
            "plano_aprovado": pid,
            "planos_arquivados": arquivados,
            "status": "APROVADO",
        }

    # ── Nova iteração de planejamento (ADR-031) ───────────────────────────────
    @server.tool()
    def nova_versao(project_id: str, escopo_id: str | None = None, nome: str | None = None) -> dict[str, Any]:
        """Cria novo plano para uma nova iteração de orçamento no mesmo escopo.

        Equivalente ao antigo bifurcar-versão, mas operando na estrutura ADR-031:
        cria um novo plano dentro do escopo existente.
        """
        from concilium.presentation.mcp.tools.escopo import _resolve_escopo_id

        store = _project(project_id)
        try:
            eid = _resolve_escopo_id(store, escopo_id)
            es = store.escopo(eid)
            ps = es.create_plan(nome=nome or "Nova Iteração")
        except Exception as e:
            return {"erro": str(e)}

        return {
            "project_id": project_id,
            "escopo_id": eid,
            "plano_id": ps.plano_id,
            "proxima_skill_sugerida": "01-escopo-e-eap",
            "nota": f"Novo plano '{ps.plano_id}' criado. Execute disparar_pipeline para iniciar o orçamento.",
        }

    # ── ADR-023 §D6: Salvar / atualizar perfil BDI do projeto (Phase 1C) ─────
    @server.tool()
    def salvar_perfil_bdi(
        project_id: str,
        tributario: dict[str, Any],
        lucro: dict[str, Any],
        confirmado_por: str,
        motivo_revisao: str | None = None,
    ) -> dict[str, Any]:
        """Persiste um snapshot imutável do perfil BDI do projeto (ADR-023 §D6).

        Na criação, salva versão 1.  Em revisões posteriores, incrementa a versão
        e emite um BdiPerfilDiff para rastreabilidade.

        Args:
            project_id:    ID do projeto.
            tributario:    Dict serializável de PerfilTributarioProjeto
                           (regime, municipio, iss_aliquota_municipal, e
                           mao_obra/material/servicos/indireto/diesel com AplicacaoTributaria).
            lucro:         Dict serializável de PerfilLucroProjeto
                           (mao_obra, material, servicos, indireto, diesel — frações 0–1).
            confirmado_por: Nome do engenheiro responsável pela confirmação.
            motivo_revisao: Texto livre obrigatório em versões > 1.

        Returns:
            perfil_id, versao, content_hash, diff (se versão > 1).
        """
        import hashlib
        from datetime import datetime

        from concilium.domain.models.bdi import (
            BdiPerfilDiff,
            PerfilBdiProjeto,
            PerfilLucroProjeto,
            PerfilTributarioProjeto,
        )

        # Valida entradas via modelos Pydantic
        try:
            trib_model = PerfilTributarioProjeto.model_validate(tributario)
            lucro_model = PerfilLucroProjeto.model_validate(lucro)
        except Exception as e:
            return {"erro": f"Dados inválidos: {e}"}

        store = _project(project_id)
        perfil_dir = store.root / "bdi"
        perfil_dir.mkdir(parents=True, exist_ok=True)
        perfil_path = perfil_dir / "perfil_bdi.json"

        agora = datetime.now(UTC)
        versao = 1
        diff: dict | None = None

        # Carrega perfil anterior se existir
        perfil_anterior_raw: dict | None = None
        if perfil_path.exists():
            try:
                perfil_anterior_raw = json.loads(perfil_path.read_text(encoding="utf-8"))
                versao = (perfil_anterior_raw.get("versao") or 1) + 1
            except Exception:
                pass

        if versao > 1 and not motivo_revisao:
            return {
                "erro": (
                    f"motivo_revisao é obrigatório ao atualizar um perfil BDI existente (versão atual: {versao - 1})."
                )
            }

        # Computa hash antes de criar o modelo (hash is required field)
        hash_payload = {
            "tributario": trib_model.model_dump(mode="json"),
            "lucro": lucro_model.model_dump(mode="json"),
            "projeto_id": project_id,
            "versao": versao,
        }
        content_hash = hashlib.sha256(json.dumps(hash_payload, sort_keys=True).encode()).hexdigest()[:16]

        # Monta o perfil imutável
        perfil = PerfilBdiProjeto(
            projeto_id=project_id,
            versao=versao,
            content_hash=content_hash,
            confirmado_em=agora,
            confirmado_por=confirmado_por,
            tributario=trib_model,
            lucro=lucro_model,
        )

        payload = perfil.model_dump(mode="json")
        payload["motivo_revisao"] = motivo_revisao

        # Emite BdiPerfilDiff se versão > 1
        if perfil_anterior_raw and versao > 1:
            try:
                anterior_model = PerfilBdiProjeto.model_validate(perfil_anterior_raw)
                # Computa campos alterados por comparação de dicts
                ant_dict = anterior_model.model_dump(mode="json")
                nov_dict = perfil.model_dump(mode="json")
                campos: list[str] = []
                for secao in ("tributario", "lucro"):
                    for k, v in nov_dict.get(secao, {}).items():
                        if ant_dict.get(secao, {}).get(k) != v:
                            campos.append(f"{secao}.{k}")
                diff_model = BdiPerfilDiff(
                    projeto_id=project_id,
                    versao_anterior=anterior_model.versao,
                    versao_nova=versao,
                    perfil_anterior_id=anterior_model.perfil_id,
                    perfil_novo_id=perfil.perfil_id,
                    motivo=motivo_revisao or "",
                    campos_alterados=campos,
                    resumo=f"v{anterior_model.versao} -> v{versao}: {len(campos)} campo(s) alterado(s)",
                )
                diff = diff_model.model_dump(mode="json")
            except Exception:
                diff = {"nota": "Não foi possível calcular diff — estrutura anterior incompatível"}

        # Persiste snapshot versionado + arquivo de cabeça
        versao_path = perfil_dir / f"perfil_bdi_v{versao:03d}.json"
        versao_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        perfil_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

        result: dict[str, Any] = {
            "project_id": project_id,
            "perfil_id": perfil.perfil_id,
            "versao": versao,
            "content_hash": content_hash,
            "confirmado_por": confirmado_por,
            "confirmado_em": agora.isoformat(),
        }
        if diff:
            result["diff"] = diff
        return result

    # ADR-101: _meta.ui para MCP Apps (Fase 1)
    _ui_metas = {
        "consultar_status": {"ui": {"resourceUri": "ui://concilium/dashboard-resultado", "permissions": []}},
    }
    for tool_name, meta in _ui_metas.items():
        try:
            tool = server._tool_manager._tools.get(tool_name)
            if tool is not None:
                tool.meta = meta
        except Exception:
            pass
