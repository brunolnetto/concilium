"""Carregamento de catálogo via `BlobStoragePort` — suporte a backends remotos
(SharePoint, S3, Azure, Google Drive) além do filesystem local (issue #147, ADR-047 D5/D6).

Contexto: `Runtime.load_catalogo()` sempre leu o catálogo direto do filesystem
local (`config_root / "catalogos" / id`), ignorando `CONCILIUM__STORE_BACKEND`
— mesma classe de bug da issue #146 (tools MCP de projeto ignoravam o backend),
mas para o catálogo master em vez de artefatos de projeto. O `CatalogLoader`
(`infrastructure/catalog/catalog_loader.py`, ADR-047 D5) já tinha um backend
SharePoint, mas nunca foi wireado ao caminho real E não reproduz a estrutura
real de diretórios (insumos por subpasta×código, merge de producoes/+
produtividades/, templates.json) — por isso este módulo é uma implementação
nova e independente, não uma extensão do `CatalogLoader`.

Este módulo espelha fielmente a lógica de merge/síntese de
`CatalogMixin._load_catalogo_from_disk`, mas opera sobre `listar_blobs`/
`ler_blob` do `BlobStoragePort` em vez de `Path.glob`/`read_text` — funciona
identicamente para `LocalBlobStorage` e qualquer backend remoto, sem duplicar
regra de negócio por backend. Usado só quando `CONCILIUM__STORE_BACKEND`
resolve para algo diferente de `filesystem` — o caminho `filesystem` (padrão,
o único usado em produção hoje) continua passando por
`_load_catalogo_from_disk`, inalterado.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from concilium.domain.repositories.blob_storage_port import BlobStoragePort
from concilium.infrastructure.storage.store_factory import build_blob_storage, resolve_store_backend

from ..deliverables.helpers.insumos import dedup_insumos, ingest_insumos

# Mesmo TTL default do CatalogLoader (ADR-024) — não há mtime de arquivo individual
# pra comparar num backend remoto, então o cache local é invalidado só por tempo.
_REMOTE_CACHE_TTL_SECONDS = 60 * 60

# 2026-08-11: incidente de produção — catálogos grandes (ex. "mendeslobo": centenas
# de CPUs/insumos reais, vs. "mendeslobo-rfi" de referência com 75) levavam 160s+
# pra carregar via SharePoint com cache frio (leitura sequencial: um listar_blobs +
# um ler_blob POR ARQUIVO, cada um pagando o round-trip completo ao Graph,
# ~150-250ms). Cache local (_REMOTE_CACHE_TTL_SECONDS acima) mascarava isso em
# runs normais, mas mora no disco efêmero do container — some a cada deploy/
# restart, forçando uma recarga fria completa bem na hora em que o operador mais
# precisa do ping() responder rápido. Paralelizado via ThreadPoolExecutor; a
# concorrência real com o Graph continua limitada por _concurrency_limiter
# (sharepoint.py, threading.Semaphore) — aqui só paralelizamos o disparo.
#
# 2026-08-11 (follow-up): 8 workers travava o próprio container por 7+ minutos
# em produção — concilium-mcp roda com só 0.5 vCPU (hoje aumentado pra 1.0, mas
# mesmo assim). Rajada de 8 threads fazendo parsing de JSON + handshake TLS
# concorrente estourava a cota de CPU do cgroup, e o container inteiro (INCLUSIVE
# o event loop do asyncio que deveria disparar TOOL_IO_TIMEOUT_S) ficava
# suspenso pelo kernel — o timeout de 45s nunca disparava porque o mecanismo de
# cancelamento também ficava congelado. Reduzido para um valor conservador —
# ainda um ganho real sobre sequencial, sem rajada grande o bastante pra
# derrubar o event loop num container pequeno.
_MAX_PARALLEL_FETCHES = 3

# 2026-08-11 (warm-up + coalescência): um lock por `catalogo_id`, não um lock
# global — carga de "mendeslobo" não deve bloquear a de "mendeslobo-rfi". Sem
# isto, o warm-up assíncrono de startup (`server.py`) e a primeira request real
# do usuário podiam se sobrepor: as duas erram o cache em disco (ainda não
# escrito) e disparam ~800 round-trips ao Graph CADA UMA, dobrando a carga em
# vez de uma reaproveitar o resultado que a outra está gravando. Quem chega
# depois espera o lock e, ao adquiri-lo, reconsulta o cache — que a primeira
# chamada acabou de gravar — em vez de repetir a carga fria.
_load_locks: dict[str, threading.Lock] = {}
_load_locks_guard = threading.Lock()


def _get_catalog_load_lock(catalogo_id: str) -> threading.Lock:
    with _load_locks_guard:
        lock = _load_locks.get(catalogo_id)
        if lock is None:
            lock = threading.Lock()
            _load_locks[catalogo_id] = lock
        return lock


def _fetch_all_parallel(paths: list[str], fetch_one) -> list[Any]:
    """Chama `fetch_one(path)` para cada path em paralelo, preservando a ordem
    de `paths` no resultado (determinismo — mesma ordem que a versão sequencial
    original, importante para lógica de dedup que depende de "primeiro vence")."""
    if not paths:
        return []
    with ThreadPoolExecutor(max_workers=min(_MAX_PARALLEL_FETCHES, len(paths))) as pool:
        return list(pool.map(fetch_one, paths))


def catalog_storage_backend() -> str:
    """Backend efetivo de storage — mesma env var usada por projetos (CONCILIUM__STORE_BACKEND)."""
    return resolve_store_backend()


def _catalog_prefix(catalogo_id: str, backend: str) -> str:
    # SharePoint (e demais backends remotos): root_path do storage já aponta pra raiz
    # do drive/bucket configurada (ex.: "Concilium/prod") — D6 da ADR-047 coloca o
    # catálogo em "config/catalogos/{id}" a partir daí.
    # Filesystem: config_root JÁ É o diretório "config/" (Dockerfile copia config/ pra
    # /app) — sem prefixo "config/" extra.
    if backend == "filesystem":
        return f"catalogos/{catalogo_id}"
    return f"config/catalogos/{catalogo_id}"


def _global_producoes_prefix(backend: str) -> str:
    return "producoes" if backend == "filesystem" else "config/producoes"


def _read_json_blobs(storage: BlobStoragePort, prefix: str) -> list[tuple[str, Any]]:
    """Lista e lê todo `.json` sob um prefixo — retorna pares (caminho, conteúdo parseado).

    Leitura em lote via `ler_blobs_batch` (SharePoint: Graph `$batch`, ver
    SharePointBlobStorage.ler_blobs_batch) — ataca o N+1 de catálogos grandes:
    centenas de arquivos individuais viravam centenas de round-trips (issue
    #147/#148/#149/#153), mesmo com pooling de conexão (que só eliminou o
    handshake TCP+TLS repetido, não o N+1). `getattr` defensivo em vez de
    chamada direta: alguns fakes de teste (duck-typed, não sub-classe de
    BlobStoragePort) não implementam o método — nesse caso todos os paths
    caem no fallback abaixo, preservando o comportamento paralelo-via-ler_blob
    de antes desta otimização. Paths que o lote não resolveu (falha pontual
    num item) também caem nesse mesmo fallback.
    """
    try:
        paths = sorted(p for p in storage.listar_blobs(prefix) if p.endswith(".json"))
    except FileNotFoundError:
        return []
    if not paths:
        return []

    batch_fn = getattr(storage, "ler_blobs_batch", None)
    raw_by_path: dict[str, bytes] = batch_fn(paths) if callable(batch_fn) else {}

    missing = [p for p in paths if p not in raw_by_path]
    if missing:

        def _fetch_raw(p: str) -> bytes | None:
            try:
                return storage.ler_blob(p)
            except Exception:
                return None

        for p, raw in zip(missing, _fetch_all_parallel(missing, _fetch_raw), strict=True):
            if raw is not None:
                raw_by_path[p] = raw

    result: list[tuple[str, Any]] = []
    for p in paths:
        raw = raw_by_path.get(p)
        if raw is None:
            continue
        try:
            result.append((p, json.loads(raw.decode("utf-8"))))
        except Exception:
            continue
    return result


def _slc_processar_blob_data(data: Any) -> list[dict]:
    """Processa um blob JSON data e retorna lista de CPUs extraídas.
    Suporta: list direto, dict com chave 'cpus', dict individual."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "cpus" in data:
        return list(data["cpus"])
    if isinstance(data, dict):
        return [data]
    return []


def _slc_tentar_fallback_legado(storage: BlobStoragePort, base: str) -> list[dict]:
    """Tenta carregar cpus.json legado como fallback quando blobs vazios."""
    try:
        raw = storage.ler_blob(f"{base}/cpus.json")
        data = json.loads(raw.decode("utf-8"))
        return _slc_processar_blob_data(data)
    except (FileNotFoundError, Exception):
        return []


def _storage_load_cpus(storage: BlobStoragePort, base: str) -> list[dict]:
    cpus: list[dict] = []
    for _path, data in _read_json_blobs(storage, f"{base}/cpus"):
        cpus.extend(_slc_processar_blob_data(data))
    if cpus:
        return cpus
    # Fallback: cpus.json único (formato legado, ver _load_cpus_from_json).
    return _slc_tentar_fallback_legado(storage, base)


def _storage_load_insumos(storage: BlobStoragePort, base: str) -> list[dict]:
    # listar_blobs já é recursivo — cobre tanto arquivos soltos direto em insumos/
    # quanto arquivos em subpastas por tipo (insumos/mao_obra/*.json etc.) numa
    # única passada, sem precisar distinguir os dois casos como o loader local faz.
    insumos: list[dict] = []
    for _path, data in _read_json_blobs(storage, f"{base}/insumos"):
        ingest_insumos(data, insumos)
    return dedup_insumos(insumos)


def _storage_load_producoes_dir(storage: BlobStoragePort, base: str, subdir: str) -> list[dict]:
    result: list[dict] = []
    for _path, data in _read_json_blobs(storage, f"{base}/{subdir}"):
        if isinstance(data, list):
            result.extend(data)
        elif isinstance(data, dict):
            result.append(data)
    return result


def _synthesize_missing_producoes(cpus: list[dict], seen_prod_ids: set) -> list[dict]:
    result: list[dict] = []
    for cpu in cpus:
        prod_id_ref = cpu.get("producao_id_ref")
        producao_horaria = cpu.get("producao_horaria")
        if prod_id_ref and producao_horaria and prod_id_ref not in seen_prod_ids:
            result.append(
                {
                    "id": prod_id_ref,
                    "producao_horaria": float(producao_horaria),
                    "composicao_padrao_equipe": cpu.get("composicao_padrao_equipe"),
                }
            )
            seen_prod_ids.add(prod_id_ref)
    return result


def _storage_load_producao_by_id(storage: BlobStoragePort, prod_id: str, search_prefixes: list[str]) -> dict | None:
    for prefix in search_prefixes:
        try:
            raw = storage.ler_blob(f"{prefix}/{prod_id}.json")
            return json.loads(raw.decode("utf-8"))
        except Exception:
            continue
    return None


def _storage_load_producoes_by_ids_batch(
    storage: BlobStoragePort, prod_ids: list[str], search_prefixes: list[str]
) -> dict[str, dict]:
    """Resolve várias `producao_id` de uma vez — mesma semântica de
    `_storage_load_producao_by_id` (primeiro prefixo da lista que existir
    vence), mas em lote por prefixo (ver `ler_blobs_batch`) em vez de 1
    round-trip por (prod_id × prefixo). Catálogos com centenas de CPUs
    distintos pagavam esse custo sequencial mesmo paralelizado.
    """
    remaining = list(prod_ids)
    result: dict[str, dict] = {}

    # getattr defensivo: fakes de teste duck-typed (não sub-classe de
    # BlobStoragePort) sem o método pulam direto pra rede de segurança abaixo
    # — que tenta tudo individualmente, preservando o comportamento
    # paralelo-via-ler_blob de antes desta otimização.
    batch_fn = getattr(storage, "ler_blobs_batch", None)
    if callable(batch_fn):
        for prefix in search_prefixes:
            if not remaining:
                break
            path_to_id = {f"{prefix}/{pid}.json": pid for pid in remaining}
            raw_by_path = batch_fn(list(path_to_id))
            resolved_now: set[str] = set()
            for path, pid in path_to_id.items():
                raw = raw_by_path.get(path)
                if raw is None:
                    continue
                try:
                    result[pid] = json.loads(raw.decode("utf-8"))
                    resolved_now.add(pid)
                except Exception:
                    continue
            remaining = [pid for pid in remaining if pid not in resolved_now]

    # Rede de segurança: o que sobrou (não resolvido em NENHUM prefixo via lote)
    # tenta de novo individualmente antes de desistir — cobre backends sem
    # batch de verdade (já tentaram tudo, custo residual é redundante mas
    # inofensivo) e qualquer falso-negativo pontual do lote.
    if remaining:

        def _fetch(prod_id: str) -> tuple[str, dict] | None:
            found = _storage_load_producao_by_id(storage, prod_id, search_prefixes)
            return (prod_id, found) if found is not None else None

        for r in _fetch_all_parallel(remaining, _fetch):
            if r is not None:
                pid, data = r
                result[pid] = data

    return result


def _storage_load_producoes_from_cpus(
    storage: BlobStoragePort,
    cpus: list[dict],
    base: str,
    global_prefix: str,
    seen_prod_ids: set[str] | None = None,
) -> list[dict]:
    """Producoes referenciadas por `producao_id_ref`/`producao_id` dos CPUs.

    `seen_prod_ids` (já resolvidos via scan de diretório + síntese direta do
    CPU — ver `_storage_load_and_synthesize_producoes`) é excluído ANTES de
    buscar: `_merge_global_producoes` já descartava esses resultados depois
    (dedup por id) — buscar e descartar era rede gasta à toa, principalmente
    perceptível com o N+1 do SharePoint (até 3 prefixos × cada id único).
    """
    search_prefixes = [global_prefix, f"{base}/producoes", f"{base}/produtividades"]
    seen_prod_ids = seen_prod_ids or set()
    prod_ids: list[str] = []
    seen: set[str] = set()
    for cpu in cpus:
        prod_id = cpu.get("producao_id_ref") or cpu.get("producao_id")
        if prod_id and prod_id not in seen and prod_id not in seen_prod_ids:
            seen.add(prod_id)
            prod_ids.append(prod_id)

    return list(_storage_load_producoes_by_ids_batch(storage, prod_ids, search_prefixes).values())


def _merge_global_producoes(producoes: list[dict], global_prods: list[dict]) -> list[dict]:
    seen_ids = {p["id"] for p in producoes if "id" in p}
    for gp in global_prods:
        if gp.get("id") not in seen_ids:
            producoes.append(gp)
    return producoes


def _storage_load_and_synthesize_producoes(
    storage: BlobStoragePort, cpus: list[dict], base: str, global_prefix: str
) -> list[dict]:
    producoes = _storage_load_producoes_dir(storage, base, "producoes")
    producoes += _storage_load_producoes_dir(storage, base, "produtividades")
    seen_prod_ids: set[str] = {p["id"] for p in producoes if "id" in p}
    producoes.extend(_synthesize_missing_producoes(cpus, seen_prod_ids))
    global_prods = _storage_load_producoes_from_cpus(storage, cpus, base, global_prefix, seen_prod_ids)
    return _merge_global_producoes(producoes, global_prods)


def _storage_load_catalog_metadata(storage: BlobStoragePort, base: str) -> dict[str, str]:
    """Load explicit catalog currency through the selected storage backend."""
    try:
        raw = storage.ler_blob(f"{base}/catalog_metadata.json")
    except FileNotFoundError:
        return {}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid catalog metadata at {base}/catalog_metadata.json") from exc
    if not isinstance(payload, dict) or payload.get("schema") != "concilium.catalog-metadata.v1":
        raise ValueError(f"invalid catalog metadata schema at {base}/catalog_metadata.json")
    currency = payload.get("currency")
    if (
        not isinstance(currency, str)
        or len(currency) != 3
        or not currency.isascii()
        or not currency.isalpha()
        or currency != currency.upper()
    ):
        raise ValueError(f"missing or invalid catalog currency at {base}/catalog_metadata.json")
    return {"currency": currency}


def _storage_load_templates(storage: BlobStoragePort, base: str) -> tuple[dict, list]:
    try:
        raw = storage.ler_blob(f"{base}/templates.json")
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return {}, []
    if not isinstance(data, dict):
        return {}, []
    templates = data.get("templates", data)
    estruturas = data.get("estruturas_indiretas", [])
    return templates, estruturas


def _remote_cache_path(config_root: Path, catalogo_id: str) -> Path:
    # Nome deliberadamente distinto de `.catalog_bundle.json` (usado pelo caminho
    # filesystem, invalidado por mtime-scan) — semântica de invalidação diferente
    # (TTL por tempo) merece um arquivo próprio, para não colidir/confundir as duas
    # políticas de cache.
    return config_root / "catalogos" / catalogo_id / ".catalog_bundle_remote.json"


def _read_fresh_cache(cache_path: Path) -> dict[str, Any] | None:
    if not cache_path.exists():
        return None
    try:
        age = time.time() - cache_path.stat().st_mtime
        if age < _REMOTE_CACHE_TTL_SECONDS:
            return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def load_catalogo_via_storage(config_root: Path, catalogo_id: str, *, force_refresh: bool = False) -> dict[str, Any]:
    """Carrega catálogo via `BlobStoragePort`, backend resolvido de `CONCILIUM__STORE_BACKEND`.

    Cache local (TTL de 1h) — evita 1 round-trip de rede por chamada, já que
    `Runtime` é reinstanciado a cada request (sem cache em memória entre chamadas
    de tool MCP/CLI).
    """
    backend = catalog_storage_backend()
    cache_path = _remote_cache_path(config_root, catalogo_id)

    if not force_refresh:
        cached = _read_fresh_cache(cache_path)
        if cached is not None:
            return cached

    # Coalescência por catalogo_id (ver comentário em _get_catalog_load_lock) —
    # quem chega enquanto outra carga do MESMO catálogo está em andamento espera
    # aqui e, ao adquirir o lock, reconsulta o cache antes de repetir os ~800
    # round-trips ao Graph.
    lock = _get_catalog_load_lock(catalogo_id)
    with lock:
        if not force_refresh:
            cached = _read_fresh_cache(cache_path)
            if cached is not None:
                return cached

        storage = build_blob_storage()
        try:
            base = _catalog_prefix(catalogo_id, backend)
            global_prefix = _global_producoes_prefix(backend)

            catalogo: dict[str, Any] = {
                "cpus": [],
                "insumos": [],
                "templates": {},
                "estruturas_indiretas": [],
                # Réplica fiel de uma peculiaridade do caminho filesystem
                # (`_load_catalogo_from_disk`): esta chave é inicializada mas nunca
                # populada — mantida vazia aqui de propósito, para paridade de
                # comportamento entre os dois caminhos (não é um bug introduzido aqui).
                "produtividades": [],
            }
            catalogo["cpus"] = _storage_load_cpus(storage, base)
            catalogo["insumos"] = _storage_load_insumos(storage, base)
            templates, estruturas = _storage_load_templates(storage, base)
            catalogo["templates"] = templates
            catalogo["estruturas_indiretas"] = estruturas
            catalogo["producoes"] = _storage_load_and_synthesize_producoes(
                storage, catalogo["cpus"], base, global_prefix
            )
            catalogo.update(_storage_load_catalog_metadata(storage, base))
        finally:
            # Libera o pool de conexões (SharePointBlobStorage.close(), ver
            # sharepoint.py) — best-effort e via duck-typing: backends que não
            # abrem conexão persistente (ex. filesystem) simplesmente não têm
            # este método.
            close = getattr(storage, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(catalogo, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

        return catalogo


# ── Write helpers (issue #147 parte 2) ────────────────────────────────────────
# Espelham load_catalogo_via_storage: filesystem usa Path direto; qualquer outro
# backend passa por BlobStoragePort com o mesmo prefixo de _catalog_prefix().


def gravar_catalogo_blob(config_root: Path, catalogo_id: str, relative_path: str, content: bytes) -> None:
    """Grava blob individual do catálogo via CONCILIUM__STORE_BACKEND."""
    backend = catalog_storage_backend()
    if backend == "filesystem":
        dest = config_root / "catalogos" / catalogo_id / relative_path.lstrip("/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return
    base = _catalog_prefix(catalogo_id, backend)
    build_blob_storage().gravar_blob(f"{base}/{relative_path.lstrip('/')}", content)


def ler_catalogo_blob(config_root: Path, catalogo_id: str, relative_path: str) -> bytes:
    """Lê blob individual do catálogo via CONCILIUM__STORE_BACKEND."""
    backend = catalog_storage_backend()
    if backend == "filesystem":
        src = config_root / "catalogos" / catalogo_id / relative_path.lstrip("/")
        if not src.exists():
            raise FileNotFoundError(f"Blob de catálogo não encontrado: {relative_path}")
        return src.read_bytes()
    base = _catalog_prefix(catalogo_id, backend)
    return build_blob_storage().ler_blob(f"{base}/{relative_path.lstrip('/')}")


def deletar_catalogo_blob(config_root: Path, catalogo_id: str, relative_path: str) -> None:
    """Remove blob individual do catálogo via CONCILIUM__STORE_BACKEND."""
    backend = catalog_storage_backend()
    if backend == "filesystem":
        dest = config_root / "catalogos" / catalogo_id / relative_path.lstrip("/")
        if dest.exists():
            dest.unlink()
        return
    base = _catalog_prefix(catalogo_id, backend)
    try:
        build_blob_storage().deletar_blob(f"{base}/{relative_path.lstrip('/')}")
    except FileNotFoundError:
        pass


def invalidar_catalogo_cache(config_root: Path, catalogo_id: str) -> None:
    """Invalida os bundles de cache locais após uma escrita no catálogo."""
    for name in (".catalog_bundle.json", ".catalog_bundle_remote.json"):
        p = config_root / "catalogos" / catalogo_id / name
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
