"""Ferramentas MCP de gestão de projetos — listar, criar, status, aprovar."""

from __future__ import annotations

import json
from datetime import UTC
from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.infrastructure.storage.project import ProjectStore
from concilium.presentation.mcp_server._context import (
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
            return {"projetos": [], "projetos_root": str(proj_root)}

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
        return {"projetos": out, "projetos_root": str(proj_root)}

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
        """Cria projeto novo e executa skill 00 (escopo).

        Args:
            nome: Nome legível do projeto (ex.: "Lote 09/10 CE")
            contexto_id: ID do contexto (ex.: "test"). Use listar_contextos para opções.
            tipo_obra: "terraplenagem" | "pavimentacao" | "saneamento"
            localizacao: Cidade, UF (ex.: "Aracoiaba, CE")
            coordenadas_lat / lng: Coordenadas para consulta climática
            data_inicio / data_termino: ISO dates "YYYY-MM-DD"
            eap: Lista de itens da EAP. Cada item é dict com:
                 item_id, ordem, cpu_id, descricao, unidade, quantitativo

        Returns:
            project_id, version, status_skills_executadas, próximas_skills_pendentes
        """
        rt = _runtime()
        proj_root = _projetos_root()
        proj_root.mkdir(parents=True, exist_ok=True)

        store = ProjectStore.init(proj_root, nome, contexto_id=contexto_id)
        v = store.new_version()

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
            # ADR-035: Usa o Coordenador para garantir governança
            coord = _lifecycle_coordinator()
            r = coord.avancar_projeto("01-escopo-e-eap", store, v, inputs=inputs_escopo)

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
                    "version": v,
                    "skills_executadas": executadas,
                    "erro": "Skill 01-escopo-e-eap falhou",
                }
        except Exception as e:
            return {"project_id": store.root.name, "version": v, "erro": str(e)}

        return {
            "project_id": store.root.name,
            "version": v,
            "skills_executadas": executadas,
            "proxima_skill_sugerida": "02-produtividade-climatica",
            "nota": (
                "Projeto criado com escopo. Próximo passo: avancar_pipeline para calcular praticabilidade climática."
            ),
        }

    # ── 6. Status ────────────────────────────────────────────────────────
    @server.tool()
    def consultar_status(project_id: str) -> dict[str, Any]:
        """Retorna estado atual do projeto: versão atual, skills executadas, integridade do pipeline."""
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

    # ── 7. Aprovar versão (operação irreversível, requer confirmação humana) ─
    @server.tool()
    def aprovar_versao(project_id: str, version: str | None = None) -> dict[str, Any]:
        """Aprova a versão atual (ou versão indicada) do projeto.

        IMPORTANTE: Esta operação é IRREVERSÍVEL. Marca os arquivos como read-only.
        O Claude Desktop deve confirmar com o usuário antes de invocar.
        """
        store = _project(project_id)
        v = version or store.current_version()
        if v is None:
            return {"erro": "Nenhuma versão ativa para aprovar"}

        try:
            store.approve(v)
        except Exception as e:
            return {"erro": str(e)}

        return {"project_id": project_id, "version": v, "status": "APROVADO"}

    # ── ADR-015 §P2: Bifurcar versão aprovada para nova iteração ─────────────
    @server.tool()
    def nova_versao(
        project_id: str,
        base_version: str | None = None,
    ) -> dict[str, Any]:
        """Cria nova versão de planejamento a partir de uma versão aprovada (ADR-015 §P2).

        Permite retomar o pipeline de orçamento após aprovação (S4 -> S1).
        A nova versão é uma cópia da base; todos os artefatos são herdados
        e o pipeline pode ser re-executado do início ou de qualquer checkpoint.

        Args:
            project_id:   ID do projeto.
            base_version: Versão de origem (padrão: versão atual).  Normalmente
                          a última versão APROVADA.

        Returns:
            project_id, nova_versao, base_usada, proxima_skill_sugerida.
        """
        store = _project(project_id)
        base = base_version or store.current_version()
        if not base:
            return {"erro": "Nenhuma versão ativa para bifurcar"}

        try:
            nova = store.new_version(base=base)
        except Exception as e:
            return {"erro": str(e)}

        return {
            "project_id": project_id,
            "nova_versao": nova,
            "base_usada": base,
            "proxima_skill_sugerida": "02-produtividade-climatica",
            "nota": (
                f"Nova versão {nova} criada a partir de {base}. "
                "Re-execute o pipeline a partir de qualquer checkpoint ou do início."
            ),
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
