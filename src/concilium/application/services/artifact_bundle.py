"""ADR-093: Serviço de artefatos — classificação por audiência, leitura e bundle zip.

Opera diretamente sobre o layout em disco de um ``ProjectStore``:

    projetos/{id}/{versao}/
        outputs/        relatorio.md, memorial_bdi.{md,pdf}, *.xlsx, *.png, ...
        intermediate/   relatorio.json, schedules_weekly.json, ...
        artifacts/      {artifact_id}.json (+ .meta.json)   — ADR-018

Cada artefato é classificado por **audiência** (``agente`` | ``humano`` | ``ambos``)
para que um agente LLM saiba o que processar (texto/narrativa) vs. o que apenas
incluir no pacote para humanos (planilhas, gráficos, PDFs).

O transporte é adaptativo (ADR-093 D4): localmente, conteúdo binário vai como
base64 inline quando abaixo do limite; acima dele, devolve-se o caminho. Em
produção Azure (ADR-096) a mesma fronteira passa a devolver URL pré-assinada.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

# ── Classificação de audiência (ADR-093 D2) ────────────────────────────────

AUDIENCIA_AGENTE = "agente"
AUDIENCIA_HUMANO = "humano"
AUDIENCIA_AMBOS = "ambos"

# Mapa explícito nome → audiência. Curingas por extensão resolvidos em _classify.
_AUDIENCIA_POR_NOME: dict[str, str] = {
    "relatorio.md": AUDIENCIA_AGENTE,
    "memorial_bdi.md": AUDIENCIA_AGENTE,
    "resumo_executivo.md": AUDIENCIA_AMBOS,
    "resultado_planejamento.xlsx": AUDIENCIA_HUMANO,
    "modelo_vivo.xlsx": AUDIENCIA_HUMANO,
    "memorial_bdi.pdf": AUDIENCIA_HUMANO,
    "relatorio.pdf": AUDIENCIA_HUMANO,
}

_AUDIENCIA_POR_EXT: dict[str, str] = {
    ".png": AUDIENCIA_HUMANO,
    ".jpg": AUDIENCIA_HUMANO,
    ".jpeg": AUDIENCIA_HUMANO,
    ".svg": AUDIENCIA_HUMANO,
    ".pdf": AUDIENCIA_HUMANO,
    ".xlsx": AUDIENCIA_HUMANO,
    ".xls": AUDIENCIA_HUMANO,
    ".csv": AUDIENCIA_AMBOS,
    ".md": AUDIENCIA_AGENTE,
    ".json": AUDIENCIA_AGENTE,
    ".txt": AUDIENCIA_AMBOS,
}

# Extensões consideradas textuais para ler_artefato_texto.
_TEXT_EXTS = {".md", ".json", ".csv", ".txt", ".log", ".yaml", ".yml"}

_DESCRICOES: dict[str, str] = {
    "relatorio.md": "Relatório financeiro completo em narrativa (ideal para leitura por agentes).",
    "relatorio.pdf": "Relatório financeiro em PDF com gráficos embutidos (para humanos).",
    "memorial_bdi.md": "Memorial de cálculo do BDI em texto.",
    "memorial_bdi.pdf": "Memorial de cálculo do BDI em PDF.",
    "resultado_planejamento.xlsx": "Planilha consolidada: cronograma, custos e preço de venda.",
    "modelo_vivo.xlsx": "Modelo vivo editável do planejamento.",
    "resumo_executivo.md": "Resumo executivo de 1 página para decisores.",
    "gantt_cronograma.png": "Gráfico de Gantt do cronograma.",
    "scurve_custo.png": "Curva S de custo acumulado.",
    "pool_ciclo_vida.png": "Ciclo de vida das instâncias de pool de recursos.",
    "pool_utilizacao_temporal.png": "Utilização temporal do pool de recursos.",
    "pool_custo_estado.png": "Custo do pool por estado (produtivo/ocioso/desmobilizado).",
    "pool_economia.png": "Economia obtida pelo compartilhamento de pool.",
}


def classify_audience(filename: str) -> str:
    """Classifica o artefato em ``agente`` | ``humano`` | ``ambos``."""
    name = Path(filename).name
    if name in _AUDIENCIA_POR_NOME:
        return _AUDIENCIA_POR_NOME[name]
    ext = Path(name).suffix.lower()
    return _AUDIENCIA_POR_EXT.get(ext, AUDIENCIA_AMBOS)


def describe_artifact(filename: str) -> str:
    """Descrição em linguagem natural do artefato (para o MANIFESTO)."""
    name = Path(filename).name
    if name in _DESCRICOES:
        return _DESCRICOES[name]
    ext = Path(name).suffix.lower()
    if ext == ".png":
        return f"Gráfico de visualização ({name})."
    if ext == ".json":
        return f"Dados estruturados intermediários ({name})."
    return f"Artefato {name}."


def is_text_artifact(filename: str) -> bool:
    return Path(filename).suffix.lower() in _TEXT_EXTS


# ── Acesso ao layout do ProjectStore ───────────────────────────────────────

_KIND_DIRS = ("outputs", "intermediate", "artifacts")


def _version_dir(store: Any, version: str) -> Path:
    return Path(store.root) / version


def _resolve_version(store: Any, version: str | None) -> str | None:
    if version:
        return version
    try:
        return store.current_version()
    except Exception:
        return None


def _iter_artifact_files(store: Any, version: str) -> list[tuple[str, Path]]:
    """Retorna [(kind, path)] de todos os arquivos das três pastas de artefatos."""
    base = _version_dir(store, version)
    found: list[tuple[str, Path]] = []
    for kind in _KIND_DIRS:
        d = base / kind
        if not d.exists():
            continue
        for f in sorted(d.iterdir()):
            if f.is_file():
                found.append((kind, f))
    return found


def _safe_name(filename: str) -> str:
    """Impede path traversal — apenas o nome final é aceito."""
    name = Path(filename).name
    if name != filename or not name or name in (".", ".."):
        raise ValueError(f"Nome de arquivo inválido: {filename!r}")
    return name


def _find_file(store: Any, version: str, filename: str) -> tuple[str, Path] | None:
    """Localiza um artefato por nome nas três pastas (outputs → intermediate → artifacts)."""
    name = _safe_name(filename)
    base = _version_dir(store, version)
    for kind in _KIND_DIRS:
        candidate = base / kind / name
        if candidate.exists() and candidate.is_file():
            return kind, candidate
    return None


# ── Operações de alto nível (consumidas pelas tools MCP) ────────────────────


def list_artifacts(store: Any, version: str | None) -> dict[str, Any]:
    """Lista artefatos com kind, audiência, tamanho e descrição."""
    resolved = _resolve_version(store, version)
    if resolved is None:
        return {"version": None, "artefatos": [], "total": 0}

    artefatos: list[dict[str, Any]] = []
    for kind, path in _iter_artifact_files(store, resolved):
        # Sidecars .meta.json de artefatos tipados não são entregáveis primários.
        if kind == "artifacts" and path.name.endswith(".meta.json"):
            continue
        artefatos.append(
            {
                "nome": path.name,
                "kind": kind,
                "audiencia": classify_audience(path.name),
                "tamanho_bytes": path.stat().st_size,
                "descricao": describe_artifact(path.name),
            }
        )
    return {"version": resolved, "artefatos": artefatos, "total": len(artefatos)}


def read_text(store: Any, version: str | None, filename: str) -> dict[str, Any]:
    """Lê um artefato textual (md/json/csv/txt) e devolve o conteúdo como string."""
    resolved = _resolve_version(store, version)
    if resolved is None:
        raise FileNotFoundError("Projeto não possui versão ativa.")
    if not is_text_artifact(filename):
        raise ValueError(
            f"'{filename}' não é textual. Use baixar_artefato_binario para binários."
        )
    hit = _find_file(store, resolved, filename)
    if hit is None:
        raise FileNotFoundError(f"Artefato '{filename}' não encontrado na versão '{resolved}'.")
    kind, path = hit
    return {
        "nome": path.name,
        "kind": kind,
        "versao": resolved,
        "audiencia": classify_audience(path.name),
        "conteudo": path.read_text(encoding="utf-8"),
    }


def read_binary_b64(
    store: Any,
    version: str | None,
    filename: str,
    max_mb: float = 10.0,
    transport: Any | None = None,
) -> dict[str, Any]:
    """Lê um artefato binário e o entrega via transporte (base64 inline / caminho / URL).

    ADR-093 D4: a decisão de transporte é delegada a um ``ArtifactTransport``
    (default: local base64 com fallback de caminho). Em produção, um transporte
    Azure devolve URL pré-assinada (ADR-096) sem alterar este chamador.
    """
    resolved = _resolve_version(store, version)
    if resolved is None:
        raise FileNotFoundError("Projeto não possui versão ativa.")
    hit = _find_file(store, resolved, filename)
    if hit is None:
        raise FileNotFoundError(f"Artefato '{filename}' não encontrado na versão '{resolved}'.")
    kind, path = hit

    if transport is None:
        from concilium.application.services.artifact_transport import LocalBase64Transport

        transport = LocalBase64Transport(max_mb=max_mb)

    import mimetypes

    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    entrega = transport.deliver(nome=path.name, data=path.read_bytes(), mime=mime, source_path=path)
    base: dict[str, Any] = {
        "nome": path.name,
        "kind": kind,
        "versao": resolved,
        "audiencia": classify_audience(path.name),
    }
    base.update(entrega)
    return base


def _matches_filtro(item: dict[str, Any], filtro: list[str] | None) -> bool:
    """Filtro por audiência (agente/humano/ambos) ou por nome exato de arquivo."""
    if not filtro:
        return True
    fset = set(filtro)
    if item["audiencia"] in fset or AUDIENCIA_AMBOS in fset:
        return True
    return item["nome"] in fset


def _build_manifesto(projeto_nome: str, version: str, incluidos: list[dict[str, Any]]) -> str:
    linhas = [
        f"# Manifesto — {projeto_nome}",
        "",
        f"**Versão:** {version}",
        f"**Total de artefatos:** {len(incluidos)}",
        "",
        "| Arquivo | Audiência | Tamanho | Descrição |",
        "|---|---|---|---|",
    ]
    for it in incluidos:
        kb = it["tamanho_bytes"] / 1024
        arq = f"graficos/{it['nome']}" if it["nome"].lower().endswith(".png") else it["nome"]
        linhas.append(
            f"| {arq} | {it['audiencia']} | {kb:.1f} KB | {it['descricao']} |"
        )
    linhas.append("")
    return "\n".join(linhas)


def build_bundle(
    store: Any, version: str | None, filtro: list[str] | None = None, transport: Any | None = None
) -> dict[str, Any]:
    """Empacota artefatos (outputs) em zip com MANIFESTO.md; PNGs sob graficos/.

    A entrega do zip (base64 inline ou URL pré-assinada) é delegada ao
    ``ArtifactTransport`` (ADR-093 D4); default local base64.

    Returns:
        dict com nome do zip, transporte (base64/URL), tamanho e o conteúdo.
    """
    resolved = _resolve_version(store, version)
    if resolved is None:
        raise FileNotFoundError("Projeto não possui versão ativa.")

    projeto_nome = str(getattr(store, "meta", {}).get("nome", "projeto")) if hasattr(store, "meta") else "projeto"
    listagem = list_artifacts(store, resolved)["artefatos"]
    # Bundle de entrega prioriza outputs; intermediários só entram via filtro explícito de nome.
    incluidos = [
        it
        for it in listagem
        if (it["kind"] == "outputs" or (filtro and it["nome"] in set(filtro)))
        and _matches_filtro(it, filtro)
    ]

    safe_nome = "".join(c if c.isalnum() or c in "-_" else "_" for c in projeto_nome)[:40] or "projeto"
    root_folder = f"concilium_{safe_nome}_{resolved}"

    base_dir = _version_dir(store, resolved)
    buffer = io.BytesIO()
    nomes_no_zip: list[str] = []
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        manifesto = _build_manifesto(projeto_nome, resolved, incluidos)
        zf.writestr(f"{root_folder}/MANIFESTO.md", manifesto)
        nomes_no_zip.append("MANIFESTO.md")
        for it in incluidos:
            src = base_dir / it["kind"] / it["nome"]
            if not src.exists():
                continue
            subpath = (
                f"graficos/{it['nome']}" if it["nome"].lower().endswith(".png") else it["nome"]
            )
            zf.write(src, f"{root_folder}/{subpath}")
            nomes_no_zip.append(subpath)

    data = buffer.getvalue()
    nome_zip = f"{root_folder}.zip"

    if transport is None:
        from concilium.application.services.artifact_transport import LocalBase64Transport

        transport = LocalBase64Transport(max_mb=50.0)

    entrega = transport.deliver(nome=nome_zip, data=data, mime="application/zip", source_path=None)
    return {
        "versao": resolved,
        "nome_arquivo": nome_zip,
        "conteudo": nomes_no_zip,
        "total_arquivos": len(nomes_no_zip),
        **entrega,
    }
