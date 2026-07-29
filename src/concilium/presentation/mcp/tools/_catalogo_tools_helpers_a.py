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
    validate_insumo_nao_existe,
)
from concilium.presentation.mcp._context import _config_root, _projetos_root, _runtime, _wrap_response

# ADR-164: teto de itens por chamada nas tools de lote de insumo — evita
# sobrecarga de rede/payload de uma única chamada MCP muito grande.
MAX_LOTE_INSUMOS = 100


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


def _buscar_insumos_por_texto(
    catalogo: dict[str, Any],
    tipo: str | None,
    query: str | None,
    incluir_descontinuados: bool = False,
) -> list[dict[str, Any]]:
    """Filtra insumos por tipo e/ou busca textual em código/descrição (ADR-163 D1).

    Por padrão exclui insumos `status="descontinuado"` (soft delete, ADR-163 D6)
    — `incluir_descontinuados=True` os expõe quando o histórico completo é necessário.
    """
    query_norm = query.lower() if query else None
    matches: list[dict[str, Any]] = []
    for ins in catalogo.get("insumos", []):
        if not incluir_descontinuados and ins.get("status") == "descontinuado":
            continue
        if tipo and ins.get("tipo") != tipo:
            continue
        if query_norm:
            cod = str(ins.get("codigo", "")).lower()
            desc = str(ins.get("descricao", "")).lower()
            if query_norm not in cod and query_norm not in desc:
                continue
        item: dict[str, Any] = {
            "insumo_id": ins.get("codigo"),
            "descricao": ins.get("descricao"),
            "tipo": ins.get("tipo"),
            "categoria": ins.get("categoria"),
            "unidade": ins.get("unidade"),
            "preco_unitario": ins.get("preco_unitario"),
        }
        if ins.get("tipo") == "EQUIPAMENTO":
            attrs = ins.get("atributos_especificos") or {}
            item["valor_locacao_mensal"] = attrs.get("valor_locacao_mensal")
        matches.append(item)
    return matches


def _impl_listar_insumos(
    contexto_id: str,
    tipo: str | None = None,
    query: str | None = None,
    limite: int = 50,
    offset: int = 0,
    incluir_descontinuados: bool = False,
) -> dict[str, Any]:
    """Lista/busca insumos do catálogo por id, descrição e/ou tipo (ADR-163 D1).

    Fecha a lacuna de `pesquisar_catalogo` (que busca só CPUs): identifica
    insumos sem exigir que o chamador já conheça o `insumo_id`.

    Args:
        contexto_id: ID do contexto (ex.: "mendeslobo").
        tipo: Opcional. Filtra por "MATERIAL", "MAO_OBRA" ou "EQUIPAMENTO".
        query: Opcional. Busca textual case-insensitive em código/descrição.
        limite: Máximo de itens retornados por página (padrão 50).
        offset: Deslocamento para paginação (padrão 0).
        incluir_descontinuados: Opcional. Inclui insumos descontinuados
            (soft delete, ADR-163 D6) — excluídos por padrão.
    """
    rt = _runtime()
    try:
        ctx = rt.load_contexto(contexto_id)
        catalogo = rt.load_catalogo(ctx.catalogo_id)
    except Exception as e:
        return {"erro": str(e)}

    todos = _buscar_insumos_por_texto(catalogo, tipo, query, incluir_descontinuados)
    pagina = todos[offset : offset + limite]

    return _wrap_response(
        {
            "contexto_id": contexto_id,
            "catalogo_id": ctx.catalogo_id,
            "total": len(todos),
            "limite": limite,
            "offset": offset,
            "insumos": pagina,
        }
    )


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


def _append_deltas_to_rascunho(
    config_root: Path,
    contexto_id: str,
    rascunho_id: str,
    deltas_novos: list[dict[str, Any]],
) -> str | None:
    """Acrescenta um ou mais deltas ao rascunho numa única leitura+escrita (ADR-164).

    Generaliza o caminho de escrita para lote: uma tool batch com N itens
    válidos grava todos os N deltas com uma única leitura+escrita do arquivo
    do rascunho, em vez de N leituras+escritas (uma por chamada individual).

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
    deltas.extend(deltas_novos)

    try:
        rascunho_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        return f"Falha ao gravar delta no rascunho: {e}"
    return None


def _append_delta_to_rascunho(
    config_root: Path,
    contexto_id: str,
    rascunho_id: str,
    delta: dict[str, Any],
) -> str | None:
    """Acrescenta um delta ao rascunho (ADR-145 D1). Retorna mensagem de erro, ou None em sucesso."""
    return _append_deltas_to_rascunho(config_root, contexto_id, rascunho_id, [delta])


def _apply_preco_insumo_delta(
    catalog_root: Path,
    insumo_id: str,
    novo_preco: float | None,
    jurisdicao_id: str | None,
    nota: str | None,
    autor: str,
    data_vigencia: date,
    novo_valor_locacao_mensal: float | None = None,
) -> None:
    """Aplica um delta de preço e/ou locação mensal ao catálogo mestre no momento
    do merge (ADR-145 D2/D4; `novo_valor_locacao_mensal` — ADR-163 D4).

    Preço base: via RepositorioInsumo.atualizar_preco() — SCD Type 2 real (ADR-041),
    com `nota` gravada no próprio registro histórico (append-only).
    Preço regional: `regionalizacao[jurisdicao_id]` ganha um histórico append-only
    próprio, análogo ao SCD2 do preço base (ADR-145 D4).
    `novo_valor_locacao_mensal` (só EQUIPAMENTO) grava direto em
    `atributos_especificos.valor_locacao_mensal` — mesmo padrão já usado pela
    rotina de cura em lote (`cure_plausibility.py`), sem histórico próprio (campo
    sem leitor de série temporal hoje, ao contrário de `historico_precos`).
    `novo_preco` é opcional: uma cotação de mercado pode trazer só a locação
    mensal, sem alterar o preço/hora.
    """
    from concilium.infrastructure.repositories.insumo import RepositorioInsumo

    insumo_file = validate_and_resolve_insumo_file(
        catalog_root, insumo_id, novo_preco if novo_preco is not None else 0.0
    )
    insumo_data = json.loads(insumo_file.read_text(encoding="utf-8"))

    if novo_preco is not None:
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

    if novo_valor_locacao_mensal is not None:
        attrs = insumo_data.setdefault("atributos_especificos", {})
        attrs["valor_locacao_mensal"] = novo_valor_locacao_mensal

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


def _apply_criar_insumo_delta(catalog_root: Path, insumo_data: dict[str, Any]) -> None:
    """Cria o arquivo do insumo novo no catálogo mestre no momento do merge (ADR-163 D5).

    Mesma convenção de diretório dos insumos existentes: `insumos/{tipo_lower}/{codigo}.json`.
    """
    tipo_dir = str(insumo_data["tipo"]).lower()
    insumos_dir = catalog_root / "insumos" / tipo_dir
    insumos_dir.mkdir(parents=True, exist_ok=True)
    insumo_file = insumos_dir / f"{insumo_data['codigo']}.json"
    insumo_file.write_text(json.dumps(insumo_data, ensure_ascii=False, indent=2), encoding="utf-8")


def _impl_criar_insumo(
    contexto_id: str,
    rascunho_id: str,
    codigo: str,
    tipo: str,
    descricao: str,
    unidade: str,
    preco_unitario: float,
    categoria: str,
    fonte_preco: str,
    atributos_especificos: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Cria um insumo novo no catálogo mestre (ADR-163 D5).

    Mesmo caminho gated por rascunho de `atualizar_preco_insumo` (ADR-145): grava
    um delta de criação; o arquivo só é escrito no momento do merge
    (`aprovar_merge_catalogo`), nunca aqui.

    Args:
        contexto_id: ID do contexto (ex.: "mendeslobo").
        rascunho_id: Obrigatório — crie com criar_rascunho_catalogo antes.
        codigo: Código do insumo (ex.: "EQ-999"). Deve ser inédito no catálogo.
        tipo: "MATERIAL", "MAO_OBRA", "EQUIPAMENTO" ou "TERCEIRIZADO".
        descricao: Descrição do insumo.
        unidade: Unidade de medida (ex.: "h", "m3").
        preco_unitario: Preço/hora ou preço unitário inicial.
        categoria: Categoria do insumo.
        fonte_preco: "catalogo_proprio", "tabela_referencia", "cotacao_mercado" ou "negociado".
        atributos_especificos: Opcional. Ex.: {"valor_locacao_mensal": ...} para EQUIPAMENTO.
    """
    from pydantic import ValidationError

    from concilium.domain.models.catalog.catalogo import Insumo

    rt = _runtime()
    config_dir = _config_root()
    ctx = rt.load_contexto(contexto_id)
    catalog_root = _catalog_root(config_dir, ctx.catalogo_id)

    try:
        validate_insumo_nao_existe(catalog_root, codigo)
    except CatalogGovernanceError as exc:
        return {"erro": str(exc)}

    insumo_data: dict[str, Any] = {
        "codigo": codigo,
        "tipo": tipo,
        "descricao": descricao,
        "unidade": unidade,
        "preco_unitario": preco_unitario,
        "categoria": categoria,
        "fonte_preco": fonte_preco,
        "atributos_especificos": atributos_especificos or {},
    }
    try:
        Insumo(**insumo_data)
    except ValidationError as exc:
        return {"erro": f"Insumo inválido: {exc}"}

    from concilium.infrastructure.auth.permission_guard import get_current_user_id

    delta = {
        "tipo": "criacao_insumo",
        "insumo": insumo_data,
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
            "insumo_id": codigo,
            "nota": "Criação registrada no rascunho — o insumo só existirá no catálogo mestre "
            "após aprovar_merge_catalogo.",
        }
    )


def _impl_criar_insumos_lote(
    contexto_id: str,
    rascunho_id: str,
    itens: list[dict[str, Any]],
) -> dict[str, Any]:
    """Cria múltiplos insumos novos no catálogo mestre numa única chamada (ADR-164).

    Mesmo caminho gated por rascunho de `criar_insumo`, mas grava todos os
    deltas válidos numa única leitura+escrita do rascunho (`_append_deltas_to_rascunho`),
    em vez de N leituras+escritas para N chamadas individuais.

    Validação e persistência não são atômicas do mesmo jeito: cada item é
    validado independentemente (código duplicado no lote, código já existente
    no catálogo, schema inválido) e itens inválidos não abortam o lote inteiro
    — o resultado reporta sucesso/erro por item. Já a escrita dos itens
    válidos é atômica: ou todos os deltas válidos são persistidos juntos, ou
    nenhum é (se o rascunho não existir/estiver em estado terminal).

    Args:
        contexto_id: ID do contexto (ex.: "mendeslobo").
        rascunho_id: Obrigatório — crie com criar_rascunho_catalogo antes.
        itens: Lista de insumos a criar (mesmos campos de `criar_insumo`),
            até MAX_LOTE_INSUMOS itens por chamada.
    """
    if not itens:
        return {"erro": "itens não pode ser vazio."}
    if len(itens) > MAX_LOTE_INSUMOS:
        return {"erro": f"Máximo de {MAX_LOTE_INSUMOS} itens por chamada (recebido: {len(itens)})."}

    from pydantic import ValidationError

    from concilium.domain.models.catalog.catalogo import Insumo
    from concilium.infrastructure.auth.permission_guard import get_current_user_id

    rt = _runtime()
    config_dir = _config_root()
    ctx = rt.load_contexto(contexto_id)
    catalog_root = _catalog_root(config_dir, ctx.catalogo_id)
    autor = get_current_user_id() or "system"
    timestamp = datetime.now(UTC).isoformat()

    resultados: list[dict[str, Any]] = []
    deltas_validos: list[dict[str, Any]] = []
    codigos_no_lote: set[str] = set()

    for item in itens:
        codigo = item.get("codigo")
        try:
            if not codigo:
                raise ValueError("codigo é obrigatório")
            if codigo in codigos_no_lote:
                raise ValueError(f"codigo '{codigo}' duplicado dentro do próprio lote")
            validate_insumo_nao_existe(catalog_root, codigo)
            insumo_data: dict[str, Any] = {
                "codigo": codigo,
                "tipo": item.get("tipo"),
                "descricao": item.get("descricao"),
                "unidade": item.get("unidade"),
                "preco_unitario": item.get("preco_unitario"),
                "categoria": item.get("categoria"),
                "fonte_preco": item.get("fonte_preco"),
                "atributos_especificos": item.get("atributos_especificos") or {},
            }
            Insumo(**insumo_data)
        except (CatalogGovernanceError, ValidationError, ValueError, TypeError) as exc:
            resultados.append({"codigo": codigo, "status": "erro", "erro": str(exc)})
            continue

        codigos_no_lote.add(codigo)
        deltas_validos.append(
            {
                "tipo": "criacao_insumo",
                "insumo": insumo_data,
                "autor": autor,
                "timestamp": timestamp,
            }
        )
        resultados.append({"codigo": codigo, "status": "ok"})

    if deltas_validos:
        erro = _append_deltas_to_rascunho(config_dir, contexto_id, rascunho_id, deltas_validos)
        if erro:
            return {"erro": erro}

    sucesso = sum(1 for r in resultados if r["status"] == "ok")
    return _wrap_response(
        {
            "status": "RASCUNHO",
            "layer": "MASTER",
            "rascunho_id": rascunho_id,
            "total": len(itens),
            "sucesso": sucesso,
            "falhas": len(resultados) - sucesso,
            "resultados": resultados,
        }
    )


def _apply_descontinuacao_insumo_delta(catalog_root: Path, insumo_id: str, motivo: str | None) -> None:
    """Marca o insumo como descontinuado no momento do merge (ADR-163 D6).

    Soft delete: nunca remove o arquivo — só seta `status`, preservando
    fidelidade retroativa de `resolved_catalog.json`/`CatalogSnapshot` que
    referenciem este `insumo_id`.
    """
    insumo_file = validate_and_resolve_insumo_file(catalog_root, insumo_id, 0.0)
    insumo_data = json.loads(insumo_file.read_text(encoding="utf-8"))
    insumo_data["status"] = "descontinuado"
    if motivo:
        insumo_data["motivo_descontinuacao"] = motivo
    insumo_file.write_text(json.dumps(insumo_data, ensure_ascii=False, indent=2), encoding="utf-8")


def _impl_descontinuar_insumo(
    contexto_id: str,
    rascunho_id: str,
    insumo_id: str,
    motivo: str | None = None,
) -> dict[str, Any]:
    """Descontinua (soft delete) um insumo no catálogo mestre (ADR-163 D6).

    Mesmo caminho gated por rascunho de `atualizar_preco_insumo`/`criar_insumo`
    (ADR-145): grava um delta; o insumo só é marcado `status="descontinuado"`
    no momento do merge (`aprovar_merge_catalogo`) — nunca removido fisicamente.

    Args:
        contexto_id: ID do contexto (ex.: "mendeslobo").
        rascunho_id: Obrigatório — crie com criar_rascunho_catalogo antes.
        insumo_id: Código do insumo a descontinuar.
        motivo: Opcional. Justificativa (ex.: "substituído por modelo mais novo").
    """
    rt = _runtime()
    config_dir = _config_root()
    ctx = rt.load_contexto(contexto_id)

    try:
        validate_and_resolve_insumo_file(_catalog_root(config_dir, ctx.catalogo_id), insumo_id, 0.0)
    except CatalogGovernanceError as exc:
        return {"erro": str(exc)}

    from concilium.infrastructure.auth.permission_guard import get_current_user_id

    delta = {
        "tipo": "descontinuacao_insumo",
        "insumo_id": insumo_id,
        "motivo": motivo,
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
            "nota": "Descontinuação registrada no rascunho — o insumo permanece ativo até "
            "aprovar_merge_catalogo (nunca é removido fisicamente).",
        }
    )


def _impl_descontinuar_insumos_lote(
    contexto_id: str,
    rascunho_id: str,
    itens: list[dict[str, Any]],
) -> dict[str, Any]:
    """Descontinua (soft delete) múltiplos insumos numa única chamada (ADR-164).

    Mesmo caminho gated por rascunho de `descontinuar_insumo`, gravando todos
    os deltas válidos numa única leitura+escrita do rascunho.

    Args:
        contexto_id: ID do contexto (ex.: "mendeslobo").
        rascunho_id: Obrigatório — crie com criar_rascunho_catalogo antes.
        itens: Lista de descontinuações — cada item aceita `insumo_id` e
            `motivo` opcional. Até MAX_LOTE_INSUMOS itens por chamada.
    """
    if not itens:
        return {"erro": "itens não pode ser vazio."}
    if len(itens) > MAX_LOTE_INSUMOS:
        return {"erro": f"Máximo de {MAX_LOTE_INSUMOS} itens por chamada (recebido: {len(itens)})."}

    from concilium.infrastructure.auth.permission_guard import get_current_user_id

    rt = _runtime()
    config_dir = _config_root()
    ctx = rt.load_contexto(contexto_id)
    catalog_root = _catalog_root(config_dir, ctx.catalogo_id)
    autor = get_current_user_id() or "system"
    timestamp = datetime.now(UTC).isoformat()

    resultados: list[dict[str, Any]] = []
    deltas_validos: list[dict[str, Any]] = []

    for item in itens:
        insumo_id = item.get("insumo_id")
        try:
            if not insumo_id:
                raise ValueError("insumo_id é obrigatório")
            validate_and_resolve_insumo_file(catalog_root, insumo_id, 0.0)
        except (CatalogGovernanceError, ValueError) as exc:
            resultados.append({"insumo_id": insumo_id, "status": "erro", "erro": str(exc)})
            continue

        deltas_validos.append(
            {
                "tipo": "descontinuacao_insumo",
                "insumo_id": insumo_id,
                "motivo": item.get("motivo"),
                "autor": autor,
                "timestamp": timestamp,
            }
        )
        resultados.append({"insumo_id": insumo_id, "status": "ok"})

    if deltas_validos:
        erro = _append_deltas_to_rascunho(config_dir, contexto_id, rascunho_id, deltas_validos)
        if erro:
            return {"erro": erro}

    sucesso = sum(1 for r in resultados if r["status"] == "ok")
    return _wrap_response(
        {
            "status": "RASCUNHO",
            "layer": "MASTER",
            "rascunho_id": rascunho_id,
            "total": len(itens),
            "sucesso": sucesso,
            "falhas": len(resultados) - sucesso,
            "resultados": resultados,
        }
    )


def _impl_atualizar_preco_insumo(
    contexto_id: str,
    insumo_id: str,
    novo_preco: float | None,
    rascunho_id: str | None = None,
    projeto_id: str | None = None,
    jurisdicao_id: str | None = None,
    nota: str | None = None,
    novo_valor_locacao_mensal: float | None = None,
) -> dict[str, Any]:
    """Atualiza o preço e/ou a locação mensal de um insumo (Base ou Regional).

    Se projeto_id for informado, a alteração é salva como um 'override' local do projeto,
    sem afetar o catálogo mestre corporativo (ADR-038).

    Caso contrário (edição do catálogo mestre), a alteração é gravada como um delta
    dentro do rascunho `rascunho_id` (ADR-145 D1) — o catálogo mestre só é tocado
    quando o rascunho é promovido via aprovar_merge_catalogo.

    Args:
        contexto_id: ID do contexto (mendeslobo).
        insumo_id: Código do insumo.
        novo_preco: O valor de preço/hora atualizado. Opcional se
            novo_valor_locacao_mensal for informado (ADR-163 D4) — uma cotação
            de mercado pode trazer só o custo de locação mensal.
        rascunho_id: Obrigatório para editar o catálogo mestre. Ignorado se projeto_id
            for informado. Crie um rascunho com criar_rascunho_catalogo antes.
        projeto_id: Opcional. Se informado, salva apenas para este projeto.
        jurisdicao_id: Opcional. Região específica.
        nota: Opcional. Justificativa.
        novo_valor_locacao_mensal: Opcional. Custo de locação mensal (só
            EQUIPAMENTO). Pelo menos um entre novo_preco/novo_valor_locacao_mensal
            deve ser informado.
    """
    if novo_preco is None and novo_valor_locacao_mensal is None:
        return {"erro": "Informe ao menos um entre novo_preco e novo_valor_locacao_mensal."}

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
            novo_preco if novo_preco is not None else 0.0,
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
    if novo_valor_locacao_mensal is not None:
        delta["novo_valor_locacao_mensal"] = novo_valor_locacao_mensal
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


def _impl_atualizar_precos_insumos_lote(
    contexto_id: str,
    rascunho_id: str,
    itens: list[dict[str, Any]],
) -> dict[str, Any]:
    """Atualiza preço e/ou locação mensal de múltiplos insumos numa única chamada (ADR-164).

    Mesmo caminho gated por rascunho de `atualizar_preco_insumo` (só catálogo
    mestre — sem suporte a override de projeto em lote), gravando todos os
    deltas válidos numa única leitura+escrita do rascunho.

    Args:
        contexto_id: ID do contexto (ex.: "mendeslobo").
        rascunho_id: Obrigatório — crie com criar_rascunho_catalogo antes.
        itens: Lista de atualizações — cada item aceita os mesmos campos de
            `atualizar_preco_insumo` (insumo_id, novo_preco, novo_valor_locacao_mensal,
            jurisdicao_id, nota), exceto projeto_id. Até MAX_LOTE_INSUMOS itens.
    """
    if not itens:
        return {"erro": "itens não pode ser vazio."}
    if len(itens) > MAX_LOTE_INSUMOS:
        return {"erro": f"Máximo de {MAX_LOTE_INSUMOS} itens por chamada (recebido: {len(itens)})."}

    from concilium.infrastructure.auth.permission_guard import get_current_user_id

    rt = _runtime()
    config_dir = _config_root()
    ctx = rt.load_contexto(contexto_id)
    catalog_root = _catalog_root(config_dir, ctx.catalogo_id)
    autor = get_current_user_id() or "system"
    timestamp = datetime.now(UTC).isoformat()

    resultados: list[dict[str, Any]] = []
    deltas_validos: list[dict[str, Any]] = []

    for item in itens:
        insumo_id = item.get("insumo_id")
        novo_preco = item.get("novo_preco")
        novo_valor_locacao_mensal = item.get("novo_valor_locacao_mensal")
        try:
            if not insumo_id:
                raise ValueError("insumo_id é obrigatório")
            if novo_preco is None and novo_valor_locacao_mensal is None:
                raise ValueError("informe ao menos um entre novo_preco e novo_valor_locacao_mensal")
            validate_and_resolve_insumo_file(
                catalog_root, insumo_id, novo_preco if novo_preco is not None else 0.0
            )
        except (CatalogGovernanceError, ValueError) as exc:
            resultados.append({"insumo_id": insumo_id, "status": "erro", "erro": str(exc)})
            continue

        delta: dict[str, Any] = {
            "tipo": "preco_insumo",
            "insumo_id": insumo_id,
            "novo_preco": novo_preco,
            "jurisdicao_id": item.get("jurisdicao_id"),
            "nota": item.get("nota"),
            "autor": autor,
            "timestamp": timestamp,
        }
        if novo_valor_locacao_mensal is not None:
            delta["novo_valor_locacao_mensal"] = novo_valor_locacao_mensal
        deltas_validos.append(delta)
        resultados.append({"insumo_id": insumo_id, "status": "ok"})

    if deltas_validos:
        erro = _append_deltas_to_rascunho(config_dir, contexto_id, rascunho_id, deltas_validos)
        if erro:
            return {"erro": erro}

    sucesso = sum(1 for r in resultados if r["status"] == "ok")
    return _wrap_response(
        {
            "status": "RASCUNHO",
            "layer": "MASTER",
            "rascunho_id": rascunho_id,
            "total": len(itens),
            "sucesso": sucesso,
            "falhas": len(resultados) - sucesso,
            "resultados": resultados,
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
