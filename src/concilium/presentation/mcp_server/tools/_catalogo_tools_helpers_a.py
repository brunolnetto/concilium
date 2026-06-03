"""MCP catalogo tool implementations — Part A."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from concilium.application.orchestrators.catalog_governance import (
    CatalogGovernanceError,
    collect_catalog_critical_errors,
    validate_and_resolve_insumo_file,
    validate_and_resolve_producao_file,
)
from concilium.presentation.mcp_server._context import _config_root, _projetos_root, _runtime, _wrap_response


def _catalog_root(config_dir: Path, catalogo_id: str) -> Path:
    return config_dir / "catalogos" / catalogo_id


# _catalog_root defined below (avoids circular import)


def _impl_listar_contextos() -> dict[str, Any]:
    """Lista os contextos estratégicos disponíveis (ex: mendeslobo, bbid, etc)."""
    rt = _runtime()
    contextos_dir = _config_root() / "contextos"
    if not contextos_dir.exists():
        return {"contextos": []}

    contextos = []
    for p in sorted(contextos_dir.glob("*.json")):
        ctx = rt.load_contexto(p.stem)
        raw = json.loads(p.read_text(encoding="utf-8"))
        contextos.append(
            {
                "id": ctx.id,
                "nome": raw.get("nome", ctx.id),
                "descricao": raw.get("descricao", raw.get("$comment", "")),
            }
        )
    return _wrap_response({"contextos": contextos})


def _impl_pesquisar_catalogo(
    contexto_id: str,
    query: str | None = None,
    tipo_obra: str | None = None,
    limite: int = 20,
) -> dict[str, Any]:
    """Pesquisa inteligente no catálogo: busca CPUs ou sugere EAP (templates).

    Args:
        contexto_id: ID do contexto (ex.: "mendeslobo").
        query: Opcional. Termo de busca para CPUs (ex: "Aterro").
        tipo_obra: Opcional. Se informado, retorna a EAP sugerida para este tipo
            (terraplenagem, pavimentacao, saneamento).
        limite: Máximo de resultados para busca textual (padrão 20).
    """
    rt = _runtime()
    try:
        ctx = rt.load_contexto(contexto_id)
        catalogo = rt.load_catalogo(ctx.catalogo_id)
    except Exception as e:
        return {"erro": str(e)}

    result: dict[str, Any] = {"contexto_id": contexto_id, "catalogo_id": ctx.catalogo_id}
    cpus_lookup = {cpu.get("codigo"): cpu for cpu in catalogo.get("cpus", [])}

    # 1. Templates de EAP (ADR-014)
    if tipo_obra:
        tipo_upper = tipo_obra.upper()
        for tmpl in catalogo.get("templates", []):
            if tmpl.get("tipo_obra", "").upper() == tipo_upper:
                servicos = []
                for s in tmpl.get("servicos_sugeridos", []):
                    cid = s.get("cpu_id")
                    cpu = cpus_lookup.get(cid, {})
                    servicos.append(
                        {
                            "cpu_id": cid,
                            "descricao": cpu.get("descricao", cid),
                            "unidade": cpu.get("unidade", ""),
                            "obrigatoriedade": s.get("obrigatoriedade", "tipico"),
                        }
                    )
                result["eap_sugerida"] = servicos
                break

    # 2. Busca Textual
    if query:
        query_norm = query.lower()
        matches = []
        for cpu in catalogo.get("cpus", []):
            cod = str(cpu.get("codigo", "")).lower()
            desc = str(cpu.get("descricao", "")).lower()
            if query_norm in cod or query_norm in desc:
                matches.append(
                    {
                        "cpu_id": cpu.get("codigo"),
                        "descricao": cpu.get("descricao"),
                        "unidade": cpu.get("unidade"),
                        "categoria": cpu.get("categoria"),
                    }
                )
                if len(matches) >= limite:
                    break
        result["busca_resultados"] = matches

    return _wrap_response(result)


def _impl_consultar_saude_catalogo(contexto_id: str) -> dict[str, Any]:
    """Audita o catálogo em busca de erros de governança (ADR-035).

    Verifica integridade de CPUs, insumos e produção. Útil para debugar bloqueios de pipeline.
    """
    rt = _runtime()
    try:
        ctx = rt.load_contexto(contexto_id)
        catalogo = rt.load_catalogo(ctx.catalogo_id)
    except Exception as e:
        return {"erro": str(e)}

    erros = collect_catalog_critical_errors(catalogo)

    return _wrap_response(
        {
            "contexto_id": contexto_id,
            "catalogo_id": ctx.catalogo_id,
            "status": "SAUDAVEL" if not erros else "DEGRADADO",
            "erros_criticos": erros,
            "total_cpus": len(catalogo.get("cpus", [])),
        }
    )


def _impl_atualizar_preco_insumo(
    contexto_id: str,
    insumo_id: str,
    novo_preco: float,
    projeto_id: str | None = None,
    jurisdicao_id: str | None = None,
    nota: str | None = None,
) -> dict[str, Any]:
    """Atualiza o preço de um insumo (Base ou Regional).

    Se projeto_id for informado, a alteração é salva como um 'override' local do projeto,
    sem afetar o catálogo mestre corporativo (ADR-038).

    Args:
        contexto_id: ID do contexto (mendeslobo).
        insumo_id: Código do insumo.
        novo_preco: O valor atualizado.
        projeto_id: Opcional. Se informado, salva apenas para este projeto.
        jurisdicao_id: Opcional. Região específica.
        nota: Opcional. Justificativa.
    """
    rt = _runtime()
    config_dir = _config_root()
    projects_dir = _projetos_root()

    ctx = rt.load_contexto(contexto_id)
    try:
        insumo_file = validate_and_resolve_insumo_file(
            _catalog_root(config_dir, ctx.catalogo_id),
            insumo_id,
            novo_preco,
        )
    except CatalogGovernanceError as exc:
        return {"erro": str(exc)}

    if projeto_id:
        # Camada de Projeto (Project Layer Overrides)
        proj_path = projects_dir / projeto_id
        if not proj_path.exists():
            return {"erro": f"Projeto {projeto_id} não encontrado."}

        overrides_file = proj_path / "overrides" / "catalog_prices.json"
        overrides_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            overrides = {}
            if overrides_file.exists():
                overrides = json.loads(overrides_file.read_text(encoding="utf-8"))

            key = f"{insumo_id}::{jurisdicao_id or 'BASE'}"
            overrides[key] = {
                "preco": novo_preco,
                "nota": nota or "Calibração local de projeto",
                "jurisdicao": jurisdicao_id,
            }

            overrides_file.write_text(json.dumps(overrides, indent=2, ensure_ascii=False), encoding="utf-8")
            return _wrap_response(
                {"status": "SUCESSO", "layer": "PROJETO", "projeto_id": projeto_id, "insumo": insumo_id}
            )
        except Exception as e:
            return {"erro": f"Erro ao salvar override de projeto: {e}"}

    # Camada Master (Master Layer)
    try:
        data = json.loads(insumo_file.read_text(encoding="utf-8"))
        if jurisdicao_id:
            if "regionalizacao" not in data:
                data["regionalizacao"] = {}
            data["regionalizacao"][jurisdicao_id] = {"preco": novo_preco, "nota": nota}
        else:
            data["preco_unitario"] = novo_preco
            if nota:
                data["nota_calibracao"] = nota

        insumo_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return _wrap_response({"status": "SUCESSO", "layer": "MASTER", "insumo_id": insumo_id})
    except Exception as e:
        return {"erro": f"Falha ao persistir no mestre: {e}"}


def _impl_consultar_preco_insumo_temporal(
    contexto_id: str,
    insumo_id: str,
    data_referencia: str,
    projeto_id: str | None = None,
    jurisdicao_id: str | None = None,
) -> dict[str, Any]:
    """Consulta preço de insumo em data de referência com rastreabilidade de fonte (ADR-041).

    Args:
        contexto_id: ID do contexto (ex.: mendeslobo).
        insumo_id: Código do insumo.
        data_referencia: Data de arbitragem (YYYY-MM-DD).
        projeto_id: Opcional. Se informado, aplica layer de overrides do projeto (ADR-040).
        jurisdicao_id: Opcional. Região para fallback SICRO regional.
    """
    from concilium.infrastructure.repositories.insumo import RepositorioInsumo

    rt = _runtime()
    projects_dir = _projetos_root()

    try:
        dt_ref = date.fromisoformat(data_referencia)
    except ValueError:
        return {"erro": f"data_referencia inválida: {data_referencia}. Use YYYY-MM-DD."}

    try:
        ctx = rt.load_contexto(contexto_id)
        catalogo = rt.load_catalogo(ctx.catalogo_id)
    except Exception as e:
        return {"erro": str(e)}

    repo = RepositorioInsumo(catalogo)

    overrides: dict[str, Any] | None = None
    if projeto_id:
        proj_path = projects_dir / projeto_id
        if not proj_path.exists():
            return {"erro": f"Projeto {projeto_id} não encontrado."}
        overrides_file = proj_path / "overrides" / "insumos_override.json"
        if overrides_file.exists():
            try:
                raw = json.loads(overrides_file.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    overrides = raw
            except Exception:
                overrides = None

    preco, fonte = repo.resolver_preco(
        insumo_id,
        jurisdicao_id=jurisdicao_id,
        overrides=overrides,
        data_referencia=dt_ref,
    )

    return _wrap_response(
        {
            "status": "SUCESSO",
            "contexto_id": contexto_id,
            "catalogo_id": ctx.catalogo_id,
            "insumo_id": insumo_id,
            "data_referencia": dt_ref.isoformat(),
            "preco_unitario": preco,
            "fonte_preco": fonte,
            "projeto_id": projeto_id,
            "jurisdicao_id": jurisdicao_id,
        }
    )


def _impl_adicionar_variante_producao(
    contexto_id: str,
    producao_id: str,
    variante_id: str,
    nome_variante: str,
    valor_horario: float,
    equipe_json: str,
    projeto_id: str | None = None,
) -> dict[str, Any]:
    """Adiciona ou atualiza uma variante de produtividade (Master ou Projeto).

    Args:
        contexto_id: ID do contexto.
        producao_id: ID da metodologia.
        variante_id: ID único da variante.
        nome_variante: Nome legível.
        valor_horario: Produtividade benchmark.
        equipe_json: String JSON com a composição.
        projeto_id: Opcional. Se informado, salva como override local do projeto.
    """
    rt = _runtime()
    config_dir = _config_root()
    projects_dir = _projetos_root()

    try:
        equipe_data = json.loads(equipe_json)

        if projeto_id:
            # Camada de Projeto
            proj_path = projects_dir / projeto_id
            if not proj_path.exists():
                return {"erro": f"Projeto {projeto_id} não encontrado."}

            overrides_file = proj_path / "overrides" / "production_variants.json"
            overrides_file.parent.mkdir(parents=True, exist_ok=True)

            overrides = {}
            if overrides_file.exists():
                overrides = json.loads(overrides_file.read_text(encoding="utf-8"))

            key = f"{producao_id}::{variante_id}"
            overrides[key] = {"nome": nome_variante, "valor_horario": valor_horario, "equipe": equipe_data}
            overrides_file.write_text(json.dumps(overrides, indent=2, ensure_ascii=False), encoding="utf-8")
            return _wrap_response(
                {"status": "SUCESSO", "layer": "PROJETO", "projeto_id": projeto_id, "producao": producao_id}
            )

        # Camada Master
        ctx = rt.load_contexto(contexto_id)
        try:
            prod_file = validate_and_resolve_producao_file(
                _catalog_root(config_dir, ctx.catalogo_id),
                producao_id,
                valor_horario,
            )
        except CatalogGovernanceError as exc:
            return {"erro": str(exc)}

        data = json.loads(prod_file.read_text(encoding="utf-8"))
        if "variantes" not in data:
            data["variantes"] = []
        data["variantes"] = [v for v in data["variantes"] if v["id"] != variante_id]
        data["variantes"].append(
            {"id": variante_id, "nome": nome_variante, "valor_horario": valor_horario, "equipe": equipe_data}
        )
        prod_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return _wrap_response({"status": "SUCESSO", "layer": "MASTER", "producao_id": producao_id})
    except Exception as e:
        return {"erro": f"Erro ao adicionar variante: {e}"}
