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
import time
from pathlib import Path
from typing import Any

from concilium.domain.repositories.blob_storage_port import BlobStoragePort
from concilium.infrastructure.storage.store_factory import build_blob_storage, resolve_store_backend

from ..deliverables.helpers.insumos import dedup_insumos, ingest_insumos

# Mesmo TTL default do CatalogLoader (ADR-024) — não há mtime de arquivo individual
# pra comparar num backend remoto, então o cache local é invalidado só por tempo.
_REMOTE_CACHE_TTL_SECONDS = 60 * 60


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
    """Lista e lê todo `.json` sob um prefixo — retorna pares (caminho, conteúdo parseado)."""
    out: list[tuple[str, Any]] = []
    try:
        paths = storage.listar_blobs(prefix)
    except FileNotFoundError:
        return out
    for p in sorted(paths):
        if not p.endswith(".json"):
            continue
        try:
            raw = storage.ler_blob(p)
            out.append((p, json.loads(raw.decode("utf-8"))))
        except Exception:
            continue
    return out


def _storage_load_cpus(storage: BlobStoragePort, base: str) -> list[dict]:
    cpus: list[dict] = []
    for _path, data in _read_json_blobs(storage, f"{base}/cpus"):
        if isinstance(data, list):
            cpus.extend(data)
        elif isinstance(data, dict) and "cpus" in data:
            cpus.extend(data["cpus"])
        elif isinstance(data, dict):
            cpus.append(data)
    if cpus:
        return cpus
    # Fallback: cpus.json único (formato legado, ver _load_cpus_from_json).
    try:
        raw = storage.ler_blob(f"{base}/cpus.json")
        data = json.loads(raw.decode("utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "cpus" in data:
            return list(data["cpus"])
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return cpus


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
                    "valor_horario": float(producao_horaria),
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


def _storage_load_producoes_from_cpus(
    storage: BlobStoragePort, cpus: list[dict], base: str, global_prefix: str
) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    search_prefixes = [global_prefix, f"{base}/producoes", f"{base}/produtividades"]
    for cpu in cpus:
        prod_id = cpu.get("producao_id_ref") or cpu.get("producao_id")
        if not prod_id or prod_id in seen:
            continue
        found = _storage_load_producao_by_id(storage, prod_id, search_prefixes)
        if found is not None:
            result.append(found)
            seen.add(prod_id)
    return result


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
    seen_prod_ids = {p.get("id") for p in producoes if "id" in p}
    producoes.extend(_synthesize_missing_producoes(cpus, seen_prod_ids))
    global_prods = _storage_load_producoes_from_cpus(storage, cpus, base, global_prefix)
    return _merge_global_producoes(producoes, global_prods)


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


def load_catalogo_via_storage(config_root: Path, catalogo_id: str, *, force_refresh: bool = False) -> dict[str, Any]:
    """Carrega catálogo via `BlobStoragePort`, backend resolvido de `CONCILIUM__STORE_BACKEND`.

    Cache local (TTL de 1h) — evita 1 round-trip de rede por chamada, já que
    `Runtime` é reinstanciado a cada request (sem cache em memória entre chamadas
    de tool MCP/CLI).
    """
    backend = catalog_storage_backend()
    cache_path = _remote_cache_path(config_root, catalogo_id)

    if not force_refresh and cache_path.exists():
        try:
            age = time.time() - cache_path.stat().st_mtime
            if age < _REMOTE_CACHE_TTL_SECONDS:
                return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    storage = build_blob_storage()
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
    catalogo["producoes"] = _storage_load_and_synthesize_producoes(storage, catalogo["cpus"], base, global_prefix)

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
