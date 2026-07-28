"""MCP catalogo tool implementations — Part A."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from concilium.application.orchestrators.catalog_draft_lifecycle import (
    ESTADO_APROVADO,
    ESTADO_REJEITADO,
    estado_rascunho,
)
from concilium.application.orchestrators.catalog_governance import (
    CatalogGovernanceError,
    collect_catalog_critical_errors,
    validate_and_resolve_cpu_file,
    validate_and_resolve_insumo_file,
    validate_and_resolve_producao_file,
)
from concilium.presentation.mcp._context import _config_root, _projetos_root, _runtime, _wrap_response


def _catalog_root(config_dir: Path, catalogo_id: str) -> Path:
    return config_dir / "catalogos" / catalogo_id


# _catalog_root defined below (avoids circular import)


def _impl_listar_contextos() -> dict[str, Any]:
    """Lista os contextos estratégicos disponíveis (ex: mendeslobo, bbid, etc)."""
    rt = _runtime()
    contextos_dir = _config_root() / "contextos"
    if not contextos_dir.exists():
        return _wrap_response({"contextos": []})

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


def _find_eap_sugerida(catalogo: dict[str, Any], tipo_obra: str, cpus_lookup: dict[Any, dict[str, Any]]) -> list | None:
    """Encontra a EAP sugerida (servicos_sugeridos) do template cujo tipo_obra corresponde (ADR-014).

    Retorna None (não []) quando nenhum template corresponde — distingue "sem
    template" de "template vazio", já que o caller só grava a chave no resultado
    quando há match (ver _impl_pesquisar_catalogo)."""
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
            return servicos
    return None


def _buscar_cpus_por_texto(catalogo: dict[str, Any], query: str, limite: int) -> list:
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
    return matches


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
        eap_sugerida = _find_eap_sugerida(catalogo, tipo_obra, cpus_lookup)
        if eap_sugerida is not None:
            result["eap_sugerida"] = eap_sugerida

    # 2. Busca Textual
    if query:
        result["busca_resultados"] = _buscar_cpus_por_texto(catalogo, query, limite)

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


def _save_preco_insumo_override_projeto(
    projects_dir: Path,
    projeto_id: str,
    insumo_id: str,
    novo_preco: float,
    jurisdicao_id: str | None,
    nota: str | None,
    autor: str | None = None,
) -> dict[str, Any]:
    """Salva o novo preço como override de projeto (ADR-040), sem afetar o catálogo mestre.

    Grava em `insumos_override.json` — o mesmo arquivo lido por
    `RepositorioInsumo.resolver_preco()` via `_inject_project_catalog_layers`
    (pipeline real, `lifecycle_coordinator.py`) e por `concilium manage catalog
    promote`. Antes da correção (ADR-150), esta função gravava em
    `catalog_prices.json` — um arquivo que nada mais no sistema lia: o override
    "livre" nunca chegava ao pipeline real nem à promoção.
    """
    from concilium.application.orchestrators.catalog_draft_lifecycle import abrir_ou_obter_rascunho_projeto

    proj_path = projects_dir / projeto_id
    if not proj_path.exists():
        return {"erro": f"Projeto {projeto_id} não encontrado."}

    overrides_file = proj_path / "overrides" / "insumos_override.json"
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
        abrir_ou_obter_rascunho_projeto(projects_dir, projeto_id, autor or "system")
        return _wrap_response({"status": "SUCESSO", "layer": "PROJETO", "projeto_id": projeto_id, "insumo": insumo_id})
    except Exception as e:
        return {"erro": f"Erro ao salvar override de projeto: {e}"}


def _rascunho_file_path(config_root: Path, contexto_id: str, rascunho_id: str) -> Path:
    return config_root / "contextos" / contexto_id / "versions" / f"{rascunho_id}.json"


def _append_delta_to_rascunho(
    config_root: Path,
    contexto_id: str,
    rascunho_id: str,
    delta: dict[str, Any],
) -> str | None:
    """Acrescenta um delta ao rascunho (ADR-145 D1). Retorna mensagem de erro, ou None em sucesso.

    O catálogo mestre só é tocado no commit (aprovar_merge_catalogo, D2) — esta
    função nunca escreve em `config/catalogos/`, apenas na versão do rascunho.
    """
    rascunho_file = _rascunho_file_path(config_root, contexto_id, rascunho_id)
    if not rascunho_file.exists():
        return f"Rascunho '{rascunho_id}' não encontrado. Use criar_rascunho_catalogo primeiro."

    try:
        data = json.loads(rascunho_file.read_text(encoding="utf-8"))
    except Exception as e:
        return f"Falha ao ler rascunho '{rascunho_id}': {e}"

    estado = estado_rascunho(data)
    if estado in (ESTADO_APROVADO, ESTADO_REJEITADO):
        return f"Rascunho '{rascunho_id}' está em estado terminal ({estado}) e não aceita novas edições."

    deltas: list[dict[str, Any]] = data.setdefault("_deltas", [])
    deltas.append(delta)

    try:
        rascunho_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        return f"Falha ao gravar delta no rascunho: {e}"
    return None


def _apply_preco_insumo_delta(
    catalog_root: Path,
    insumo_id: str,
    novo_preco: float,
    jurisdicao_id: str | None,
    nota: str | None,
    autor: str,
    data_vigencia: date,
) -> None:
    """Aplica um delta de preço ao catálogo mestre no momento do merge (ADR-145 D2/D4).

    Preço base: via RepositorioInsumo.atualizar_preco() — SCD Type 2 real (ADR-041),
    com `nota` gravada no próprio registro histórico (append-only).
    Preço regional: `regionalizacao[jurisdicao_id]` ganha um histórico append-only
    próprio, análogo ao SCD2 do preço base (ADR-145 D4).
    """
    from concilium.infrastructure.repositories.insumo import RepositorioInsumo

    insumo_file = validate_and_resolve_insumo_file(catalog_root, insumo_id, novo_preco)
    insumo_data = json.loads(insumo_file.read_text(encoding="utf-8"))

    if jurisdicao_id:
        regionalizacao = insumo_data.setdefault("regionalizacao", {})
        bloco = regionalizacao.setdefault(jurisdicao_id, {})
        historico = bloco.setdefault("historico", [])
        historico.append(
            {
                "preco": novo_preco,
                "data_inicio_vigencia": data_vigencia.isoformat(),
                "nota": nota,
                "autor": autor,
            }
        )
        bloco["preco"] = novo_preco
    else:
        repo = RepositorioInsumo({"insumos": [insumo_data]})
        repo.atualizar_preco(insumo_id, novo_preco, data_vigencia, fonte=autor, nota=nota)

    insumo_file.write_text(json.dumps(insumo_data, ensure_ascii=False, indent=2), encoding="utf-8")


# Chaves de governança do override (aprovação/justificativa) que não fazem parte
# da definição real de uma CPU no catálogo mestre — nunca devem ser mescladas no
# arquivo master (ADR-150, extensão do escopo de INSUMO para CPU).
_CPU_OVERRIDE_METADATA_KEYS = frozenset({"motivo", "aprovado_por", "aprovado_em", "observacoes", "nota"})


def _apply_cpu_override_delta(catalog_root: Path, cpu_id: str, override_data: dict[str, Any]) -> None:
    """Aplica um delta de override de CPU ao catálogo mestre no momento da promoção (ADR-150).

    Reproduz em escrita a mesma semântica de leitura já usada pelo pipeline real
    (`ConciliumService.resolve_cpu`, `{**master_cpu, **candidate}`): os campos do
    override do projeto sobrepõem os campos correspondentes da CPU master, sem
    descartar o restante da definição (composição, categoria, etc.). Chaves de
    metadado de governança (`motivo`/`aprovado_por`/...) não são gravadas no
    arquivo mestre — não fazem parte do schema de CPU, só do rastro de aprovação.
    """
    cpu_file = validate_and_resolve_cpu_file(catalog_root, cpu_id)
    cpu_data = json.loads(cpu_file.read_text(encoding="utf-8"))
    for key, value in override_data.items():
        if key in _CPU_OVERRIDE_METADATA_KEYS:
            continue
        cpu_data[key] = value
    cpu_file.write_text(json.dumps(cpu_data, ensure_ascii=False, indent=2), encoding="utf-8")


def _impl_atualizar_preco_insumo(
    contexto_id: str,
    insumo_id: str,
    novo_preco: float,
    rascunho_id: str | None = None,
    projeto_id: str | None = None,
    jurisdicao_id: str | None = None,
    nota: str | None = None,
) -> dict[str, Any]:
    """Atualiza o preço de um insumo (Base ou Regional).

    Se projeto_id for informado, a alteração é salva como um 'override' local do projeto,
    sem afetar o catálogo mestre corporativo (ADR-038).

    Caso contrário (edição do catálogo mestre), a alteração é gravada como um delta
    dentro do rascunho `rascunho_id` (ADR-145 D1) — o catálogo mestre só é tocado
    quando o rascunho é promovido via aprovar_merge_catalogo.

    Args:
        contexto_id: ID do contexto (mendeslobo).
        insumo_id: Código do insumo.
        novo_preco: O valor atualizado.
        rascunho_id: Obrigatório para editar o catálogo mestre. Ignorado se projeto_id
            for informado. Crie um rascunho com criar_rascunho_catalogo antes.
        projeto_id: Opcional. Se informado, salva apenas para este projeto.
        jurisdicao_id: Opcional. Região específica.
        nota: Opcional. Justificativa.
    """
    rt = _runtime()
    config_dir = _config_root()
    projects_dir = _projetos_root()

    ctx = rt.load_contexto(contexto_id)

    if projeto_id:
        from concilium.infrastructure.auth.permission_guard import get_current_user_id

        return _save_preco_insumo_override_projeto(
            projects_dir,
            projeto_id,
            insumo_id,
            novo_preco,
            jurisdicao_id,
            nota,
            autor=get_current_user_id() or "system",
        )

    if not rascunho_id:
        return {
            "erro": "rascunho_id é obrigatório para editar o catálogo mestre (ADR-145). "
            "Use criar_rascunho_catalogo para abrir um rascunho e informe o rascunho_id retornado."
        }

    try:
        validate_and_resolve_insumo_file(
            _catalog_root(config_dir, ctx.catalogo_id),
            insumo_id,
            novo_preco,
        )
    except CatalogGovernanceError as exc:
        return {"erro": str(exc)}

    from concilium.infrastructure.auth.permission_guard import get_current_user_id

    delta = {
        "tipo": "preco_insumo",
        "insumo_id": insumo_id,
        "novo_preco": novo_preco,
        "jurisdicao_id": jurisdicao_id,
        "nota": nota,
        "autor": get_current_user_id() or "system",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    erro = _append_delta_to_rascunho(config_dir, contexto_id, rascunho_id, delta)
    if erro:
        return {"erro": erro}

    return _wrap_response(
        {
            "status": "RASCUNHO",
            "layer": "MASTER",
            "rascunho_id": rascunho_id,
            "insumo_id": insumo_id,
            "novo_preco": novo_preco,
            "nota": "Alteração registrada no rascunho — ainda não aplicada ao catálogo mestre. "
            "Use aprovar_merge_catalogo para promover.",
        }
    )


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


def _apply_variante_producao_delta(
    catalog_root: Path,
    producao_id: str,
    variante_id: str,
    nome_variante: str,
    valor_horario: float,
    equipe_data: Any,
) -> None:
    """Aplica um delta de variante de produção ao catálogo mestre no momento do merge (ADR-145 D2)."""
    prod_file = validate_and_resolve_producao_file(catalog_root, producao_id, valor_horario)
    data = json.loads(prod_file.read_text(encoding="utf-8"))
    if "variantes" not in data:
        data["variantes"] = []
    data["variantes"] = [v for v in data["variantes"] if v["id"] != variante_id]
    data["variantes"].append(
        {"id": variante_id, "nome": nome_variante, "valor_horario": valor_horario, "equipe": equipe_data}
    )
    prod_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _impl_adicionar_variante_producao(
    contexto_id: str,
    producao_id: str,
    variante_id: str,
    nome_variante: str,
    valor_horario: float,
    equipe_json: str,
    rascunho_id: str | None = None,
    projeto_id: str | None = None,
) -> dict[str, Any]:
    """Adiciona ou atualiza uma variante de produtividade (Master ou Projeto).

    Alterações no catálogo mestre são gravadas como delta dentro do rascunho
    `rascunho_id` (ADR-145 D1) — o arquivo de produção só é tocado quando o
    rascunho é promovido via aprovar_merge_catalogo.

    Args:
        contexto_id: ID do contexto.
        producao_id: ID da metodologia.
        variante_id: ID único da variante.
        nome_variante: Nome legível.
        valor_horario: Produtividade benchmark.
        equipe_json: String JSON com a composição.
        rascunho_id: Obrigatório para editar o catálogo mestre. Ignorado se projeto_id
            for informado. Crie um rascunho com criar_rascunho_catalogo antes.
        projeto_id: Opcional. Se informado, salva como override local do projeto.
    """
    rt = _runtime()
    config_dir = _config_root()
    projects_dir = _projetos_root()

    try:
        equipe_data = json.loads(equipe_json)

        if projeto_id:
            # Camada de Projeto — grava em producoes_overlay.json (o arquivo que
            # o CatalogResolver de fato lê, ADR-066 §_load_project_producao_overlay).
            # Antes desta correção, este ramo gravava em overrides/production_variants.json,
            # um arquivo que nenhum código de produção consome (achado da avaliação
            # de consistência venda×operacional, issue #121).
            proj_path = projects_dir / projeto_id
            if not proj_path.exists():
                return {"erro": f"Projeto {projeto_id} não encontrado."}

            overlay_file = proj_path / "overrides" / "producoes_overlay.json"
            overlay_file.parent.mkdir(parents=True, exist_ok=True)

            overlay = {}
            if overlay_file.exists():
                overlay = json.loads(overlay_file.read_text(encoding="utf-8"))

            entry = dict(overlay.get(producao_id, {}))
            variantes = [v for v in entry.get("variantes", []) if v.get("id") != variante_id]
            variantes.append(
                {"id": variante_id, "nome": nome_variante, "valor_horario": valor_horario, "equipe": equipe_data}
            )
            entry["variantes"] = variantes
            overlay[producao_id] = entry
            overlay_file.write_text(json.dumps(overlay, indent=2, ensure_ascii=False), encoding="utf-8")
            return _wrap_response(
                {
                    "status": "SUCESSO",
                    "layer": "PROJETO",
                    "projeto_id": projeto_id,
                    "producao": producao_id,
                    "nota": "Variante registrada como alternativa documentada em producoes_overlay.json "
                    "(visível em resolved_catalog.json e exports). Ela NÃO substitui automaticamente o "
                    "'valor_horario'/'custo_hora_total_referencia' usado no cálculo — nenhuma variante, "
                    "de projeto ou de catálogo mestre, é selecionada pelo pipeline hoje.",
                }
            )

        if not rascunho_id:
            return {
                "erro": "rascunho_id é obrigatório para editar o catálogo mestre (ADR-145). "
                "Use criar_rascunho_catalogo para abrir um rascunho e informe o rascunho_id retornado."
            }

        # Camada Master — valida e registra delta no rascunho (D1)
        ctx = rt.load_contexto(contexto_id)
        try:
            validate_and_resolve_producao_file(
                _catalog_root(config_dir, ctx.catalogo_id),
                producao_id,
                valor_horario,
            )
        except CatalogGovernanceError as exc:
            return {"erro": str(exc)}

        from concilium.infrastructure.auth.permission_guard import get_current_user_id

        delta = {
            "tipo": "variante_producao",
            "producao_id": producao_id,
            "variante_id": variante_id,
            "nome_variante": nome_variante,
            "valor_horario": valor_horario,
            "equipe": equipe_data,
            "autor": get_current_user_id() or "system",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        erro = _append_delta_to_rascunho(config_dir, contexto_id, rascunho_id, delta)
        if erro:
            return {"erro": erro}

        return _wrap_response(
            {
                "status": "RASCUNHO",
                "layer": "MASTER",
                "rascunho_id": rascunho_id,
                "producao_id": producao_id,
                "variante_id": variante_id,
                "nota": "Alteração registrada no rascunho — ainda não aplicada ao catálogo mestre. "
                "Use aprovar_merge_catalogo para promover.",
            }
        )
    except Exception as e:
        return {"erro": f"Erro ao adicionar variante: {e}"}
