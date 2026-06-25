"""Tool MCP criar_projeto_spec — spec unificado de projeto (ProjetoSpec)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.domain.constants import ISS_PADRAO
from concilium.infrastructure.storage.project import ProjectStore
from concilium.presentation.mcp._context import (
    _lifecycle_coordinator,
    _projetos_root,
    _runtime,
    _wrap_response,
)


def _schema_path() -> Path:
    root = Path(__file__).resolve().parents[6]
    return root / "config" / "schemas" / "projeto_spec.schema.json"


def _validate_spec(spec: dict) -> list[str]:
    """Valida spec contra projeto_spec.schema.json. Retorna lista de erros."""
    try:
        import jsonschema

        schema = json.loads(_schema_path().read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        return [e.message for e in validator.iter_errors(spec)]
    except ImportError:
        return []  # jsonschema opcional — sem validação estrita


def _resolve_tributario(meta: dict, rt: Any) -> dict:
    """Resolve alíquotas tributárias: spec > jurisdição > BR padrão."""
    tributario = dict(meta.get("regime_tributario") or {})
    jurisdicao_id = tributario.pop("jurisdicao_id", None)

    if not all(k in tributario for k in ("iss", "pis", "cofins", "cprb")):
        jur_data: dict = {}
        if jurisdicao_id:
            try:
                jur_data = rt.load_jurisdicao(jurisdicao_id)
            except Exception:
                pass
        aliq = (jur_data.get("motor_tributario_bdi") or {}).get("aliquotas") or {}
        tributario.setdefault("iss", aliq.get("ISS", ISS_PADRAO))
        tributario.setdefault("pis", aliq.get("PIS", 0.0065))
        tributario.setdefault("cofins", aliq.get("COFINS", 0.03))
        tributario.setdefault("cprb", aliq.get("CPRB", 0.045))

    return tributario


from concilium.infrastructure.auth.permission_guard import permission


def register(server: FastMCP) -> None:
    """Registra criar_projeto_spec no servidor MCP."""

    # ADR-116 F5: criar_projeto_spec absorvido em criar_projeto(spec=...) de formulario.py
    # Tool não mais registrada aqui; _resolve_tributario/_validate_spec importados diretamente.
    @permission("project:create")
    def _criar_projeto_spec_impl(spec: dict[str, Any]) -> dict[str, Any]:
        """Use quando o projeto está definido em um documento JSON completo (ProjetoSpec).

        Preferir esta tool quando o cronograma (n_equipes, producao_diaria por item) e o
        regime tributário também estão disponíveis. Para EAP simples com cpu_ids conhecidos
        use iniciar_orcamento. Para serviços em linguagem natural use criar_projeto_formulario.
        O spec segue config/schemas/projeto_spec.schema.json — análogo ao referencia.json dos benchmarks.

        Args:
            spec: ProjetoSpec com:
                meta.nome, contexto_id, tipo_obra, localizacao, coordenadas,
                data_inicio, data_termino, regime_trabalho (opt), regime_tributario (opt)
                escopos[].escopo_id, nome, eap[], cronograma[] (opt)

        Returns:
            project_id, escopos criados (escopo_id, plano_id, status_skill_01),
            proxima_skill_sugerida, tributario_efetivo
        """
        erros = _validate_spec(spec)
        if erros:
            return {"erro": "Spec inválido", "detalhes": erros[:10]}

        meta = spec["meta"]
        rt = _runtime()

        try:
            rt.load_contexto(meta["contexto_id"])
        except Exception as e:
            return {"erro": f"contexto_id inválido: {e}"}

        tributario = _resolve_tributario(meta, rt)
        regime = meta.get("regime_trabalho") or {}
        dias_semana = int(regime.get("dias_semana", 6))
        horas_dia = int(regime.get("horas_dia", 8))

        proj_root = _projetos_root()
        proj_root.mkdir(parents=True, exist_ok=True)
        store = ProjectStore.init(proj_root, meta["nome"], contexto_id=meta["contexto_id"])

        coord = _lifecycle_coordinator()
        escopos_criados = []

        for escopo_spec in spec["escopos"]:
            escopo_id = escopo_spec["escopo_id"]
            try:
                es = store.create_escopo(
                    escopo_id=escopo_id,
                    nome=escopo_spec["nome"],
                    tipo_obra=meta["tipo_obra"],
                    localizacao=meta["localizacao"],
                    coordenadas_lat=meta["coordenadas"]["lat"],
                    coordenadas_lng=meta["coordenadas"]["lng"],
                    data_inicio=meta["data_inicio"],
                    data_termino=meta["data_termino"],
                    dias_semana=dias_semana,
                    horas_dia=horas_dia,
                )
            except Exception as e:
                return {"erro": f"Falha ao criar escopo '{escopo_id}': {e}"}

            ps = es.create_plan(nome="Plano Principal")

            inputs_01 = {
                "nome": meta["nome"],
                "tipo_obra": meta["tipo_obra"],
                "localizacao": meta["localizacao"],
                "coordenadas": meta["coordenadas"],
                "regime_trabalho": {"dias_semana": dias_semana, "horas_dia": horas_dia},
                "data_inicio": meta["data_inicio"],
                "data_termino": meta["data_termino"],
                "versao_referencia_id": rt.load_contexto(meta["contexto_id"]).referencia_id,
                "eap": escopo_spec["eap"],
                "regime_tributario": tributario,
            }

            # Cronograma declarado → armazenado como inputs de skill 04
            cron_spec = escopo_spec.get("cronograma")
            if cron_spec:
                inputs_01["_cronograma_spec"] = cron_spec

            try:
                r = coord.avancar_plano("01-escopo-e-eap", store, ps, inputs=inputs_01)
                status_01 = "ERRO" if r.has_errors else "OK"
                erros_01 = [{"codigo": v.codigo, "mensagem": v.mensagem} for v in r.validacoes if v.status == "ERRO"]
            except Exception as e:
                status_01 = "ERRO"
                erros_01 = [{"codigo": "EXCECAO", "mensagem": str(e)}]

            escopos_criados.append(
                {
                    "escopo_id": escopo_id,
                    "plano_id": ps.plano_id,
                    "status_skill_01": status_01,
                    "erros": erros_01,
                }
            )

        sucesso = all(e["status_skill_01"] == "OK" for e in escopos_criados)
        return _wrap_response(
            {
                "project_id": store.root.name,
                "escopos": escopos_criados,
                "tributario_efetivo": tributario,
                "proxima_skill_sugerida": "02-produtividade-climatica" if sucesso else None,
                "nota": (
                    "Projeto criado via ProjetoSpec. Se cronograma_spec foi fornecido, use-o como input de skill 04."
                )
                if sucesso
                else "Skill 01 falhou em um ou mais escopos.",
            }
        )
