"""SharePoint backend de armazenamento via BlobStoragePort (ADR-047)."""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from concilium.domain.repositories.blob_storage_port import BlobStoragePort, StorageUnavailableError
from concilium.infrastructure.settings import get_storage

from ._sharepoint_auth import SharePointCredential, _BlobCache  # noqa: F401

logger = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_LARGE_FILE_THRESHOLD = 4 * 1024 * 1024  # 4 MB
# 2026-08-11: teto documentado do Graph API para sub-requests por chamada de
# $batch — ataca o N+1 de carregar o catálogo (issue #147/#148/#149/#153):
# ~800 leituras individuais (1 GET :/content por arquivo) viram ~40 chamadas.
_GRAPH_BATCH_SIZE = 20

# Erros transitórios do Graph API — comuns logo após um blue-green swap, quando o
# token MSAL da revisão nova ainda está "frio" ou o Graph está sob throttling.
_TRANSIENT_STATUS_CODES = frozenset({429, 502, 503, 504})
_TRANSIENT_RETRY_DELAYS_S = (0.5, 1.0, 2.0)
# 2026-08-11: incidente de produção — tempestade de 429 sustentada por 6+ minutos,
# auto-realimentada. Duas causas: (1) o cronograma fixo acima ignorava o header
# Retry-After do Graph — reter cedo demais insistia durante a própria janela de
# throttling; (2) cada retry do usuário abria uma NOVA thread (asyncio.to_thread,
# issue #148) sem cancelar as antigas — múltiplas sequências de retry concorrentes
# no mesmo processo amplificavam o throttling em vez de esperar ele passar.
# _RETRY_AFTER_CAP_S: não vale esperar mais que isto por tentativa — se o Graph
# pedir mais, o chamador tem seu próprio deadline (TOOL_IO_TIMEOUT_S) e é melhor
# falhar rápido do que segurar a thread por um tempo arbitrariamente longo.
_RETRY_AFTER_CAP_S = 10.0
# _MAX_CONCURRENT_REQUESTS: teto de sequências de retry simultâneas por processo
# — bounded queue em vez de concorrência ilimitada quando várias chamadas
# (ex.: múltiplas tentativas do usuário) tentam falar com o Graph ao mesmo tempo.
#
# 2026-08-11 (follow-up): reduzido de 4 pra 2 junto com _MAX_PARALLEL_FETCHES
# (_catalog_storage.py) — concilium-mcp roda com CPU limitada (0.5 vCPU, hoje
# aumentado pra 1.0) e rajadas de threads concorrentes fazendo parsing/TLS
# estouravam a cota de CPU do cgroup, suspendendo o container inteiro
# (inclusive o event loop do asyncio) por minutos. Ver ADR-180/issue #149.
_MAX_CONCURRENT_REQUESTS = 2
_concurrency_limiter = threading.Semaphore(_MAX_CONCURRENT_REQUESTS)


def _retry_after_seconds(r: Any, default: float) -> float:
    """Extrai Retry-After do response 429/503 (RFC 7231 — segundos ou data HTTP).

    Cai para `default` (o cronograma fixo) se o header estiver ausente ou for
    inválido. Resultado limitado a `_RETRY_AFTER_CAP_S` — nunca menor que
    `default` (o Graph pode pedir menos que nosso próprio mínimo, mas não
    vale a pena confiar nisso) nem maior que o cap.
    """
    header = r.headers.get("Retry-After")
    if not header:
        return default
    try:
        seconds = float(header)
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime

            dt = parsedate_to_datetime(header)
            seconds = (dt - datetime.now(dt.tzinfo or UTC)).total_seconds()
        except Exception:
            return default
    return min(max(default, seconds), _RETRY_AFTER_CAP_S)


# issue #147: timeout explícito de leitura — sem isto, algumas chamadas (ex.:
# listar_blobs antes desta correção) dependiam só do default do httpx, e uma
# resposta lenta/silenciosa do Graph podia se acumular por dezenas de segundos
# ao longo de uma listagem recursiva sem erro nem retorno.
_READ_TIMEOUT_S = 30.0
# 2026-08-10: incidente de produção — _ler_blob_cached ficou de fora da correção
# do #147 (só cobriu _get_with_retry/listar_blobs) e travou o único worker do
# concilium-mcp por >30min sem erro nem timeout, ao alcançar o Graph via
# ping()/listar_projetos (tools MCP síncronas, executadas direto no event loop
# pelo FastMCP). Timeout maior para escritas (upload de sessão em chunks de
# 5MB pode legitimamente demorar mais que uma leitura).
_WRITE_TIMEOUT_S = 60.0


class SharePointBlobStorage(BlobStoragePort):
    """BlobStoragePort backed by Microsoft SharePoint / OneDrive for Business.

    Implementa ADR-047 §D1–D6. Todas as operações são endereçadas via caminho
    relativo ao root_path configurado, espelhando a hierarquia do LocalBlobStorage.

    Cache local (ADR-047 §D3):
        - Leituras: ETag + TTL (padrão 60 min)
        - blob_existe(): sempre consulta a API (sem cache)
        - Modo offline: usa cache expirado quando API inacessível

    Aprovação (ADR-047 §D4):
        - aprovar_versao(): checkin de versão major no SharePoint
    """

    def __init__(
        self,
        drive_id: str,
        root_path: str,
        credential: SharePointCredential,
        *,
        cache_dir: Path | None = None,
        cache_ttl_minutes: int = 60,
        read_only: bool = False,
        offline: bool = False,
    ) -> None:
        self._drive_id = drive_id
        self._root_path = root_path.strip("/")
        self._credential = credential
        self._read_only = read_only
        self._offline = offline
        self._cache: _BlobCache | None = _BlobCache(cache_dir, ttl_minutes=cache_ttl_minutes) if cache_dir else None
        self._root_ensured = False
        # 2026-08-11 (pooling): client HTTP persistente, criado uma vez e reusado
        # por toda a vida da instância — ver `_client()`.
        self._http: Any = None
        self._http_lock = threading.Lock()

    @classmethod
    def from_env(cls, *, cache_dir: Path | None = None, system: bool = False) -> SharePointBlobStorage:
        """Instancia a partir das variáveis de ambiente CONCILIUM__SP_*.

        system=True aponta para o Drive "sistema" (auth/config/distribuição),
        isolado do Drive de projetos — ver CONCILIUM__SP_SYSTEM_DRIVE_ID.
        """
        sp = get_storage().sharepoint
        drive_id = sp.system_drive_id if system else sp.drive_id
        root_path = sp.system_root_path if system else sp.root_path
        if not drive_id:
            env_var = "CONCILIUM__SP_SYSTEM_DRIVE_ID ou CONCILIUM__SP_DRIVE_ID" if system else "CONCILIUM__SP_DRIVE_ID"
            raise OSError(f"{env_var} é obrigatório.")
        return cls(
            drive_id=drive_id,
            root_path=root_path,
            credential=SharePointCredential.from_env(),
            cache_dir=cache_dir,
        )

    # ── HTTP helpers ───────────────────────────────────────────────────────

    def _client(self) -> Any:
        """Client HTTP persistente, criado uma vez e reusado por toda chamada.

        2026-08-11: antes, cada operação usava `httpx.get/put/post/delete` de
        módulo — equivalente a `requests.get()` solto, que abre e fecha uma
        conexão TCP+TLS nova a cada chamada. Confirmado em produção: um único
        `load_catalogo("mendeslobo")` (via `_catalog_storage.py`, ~800 arquivos
        individuais) deixava ~400 sockets em TIME_WAIT pro Graph API — zero
        reuso de conexão. `httpx.Client` com pool de conexões elimina o
        handshake TCP+TLS repetido entre chamadas desta mesma instância; o
        limite do pool acompanha `_MAX_CONCURRENT_REQUESTS` (mesmo teto que já
        rege sequências de retry, ver `_get_with_retry`) — não faz sentido
        manter mais conexões ociosas do que o processo pode usar de verdade.
        """
        if self._http is None:
            with self._http_lock:
                if self._http is None:
                    try:
                        import httpx
                    except ImportError as exc:
                        raise ImportError(
                            "O pacote 'httpx' é necessário para o SharePoint backend. "
                            "Instale com: pip install 'concilium[sharepoint]'"
                        ) from exc
                    self._http = httpx.Client(
                        limits=httpx.Limits(
                            max_connections=_MAX_CONCURRENT_REQUESTS * 4,
                            max_keepalive_connections=_MAX_CONCURRENT_REQUESTS * 4,
                        )
                    )
        return self._http

    def close(self) -> None:
        """Fecha o client HTTP persistente e libera conexões do pool (best-effort)."""
        if self._http is not None:
            with self._http_lock:
                if self._http is not None:
                    try:
                        self._http.close()
                    finally:
                        self._http = None

    def _headers(self, extra: dict | None = None) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self._credential.acquire_token()}"}
        if extra:
            h.update(extra)
        return h

    def _item_url(self, path: str) -> str:
        safe = path.strip("/")
        return f"{_GRAPH_BASE}/drives/{self._drive_id}/root:/{self._root_path}/{safe}"

    def _item_content_url(self, path: str) -> str:
        return f"{self._item_url(path)}:/content"

    def _get_with_retry(
        self, httpx: Any, url: str, headers: dict[str, str], params: dict[str, str] | None = None
    ) -> Any:
        """GET com retry/backoff em erros transitórios do Graph (429/502/503/504).

        Toda a sequência de tentativas roda sob `_concurrency_limiter` — no máximo
        `_MAX_CONCURRENT_REQUESTS` sequências de retry simultâneas por processo
        (incidente 2026-08-11: sem isso, cada chamada concorrente abria sua própria
        sequência, amplificando o throttling em vez de esperar ele passar).
        """
        last_response = None
        with _concurrency_limiter:
            for attempt, delay in enumerate((*_TRANSIENT_RETRY_DELAYS_S, None)):
                r = httpx.get(url, headers=headers, params=params, follow_redirects=True, timeout=_READ_TIMEOUT_S)
                if r.status_code not in _TRANSIENT_STATUS_CODES:
                    return r
                last_response = r
                if delay is not None:
                    wait_s = _retry_after_seconds(r, delay)
                    logger.warning(
                        "SharePoint: status %s transitório (tentativa %d/%d) — retry em %.1fs%s",
                        r.status_code,
                        attempt + 1,
                        len(_TRANSIENT_RETRY_DELAYS_S) + 1,
                        wait_s,
                        " (Retry-After respeitado)" if wait_s != delay else "",
                    )
                    time.sleep(wait_s)
        return last_response

    def _post_with_retry(
        self, httpx: Any, url: str, headers: dict[str, str], json_body: dict[str, Any]
    ) -> Any:
        """POST com o mesmo retry/backoff de `_get_with_retry` — usado por `$batch`.

        `$batch` está sujeito ao mesmo throttling (429) das chamadas individuais
        que ele substitui; sem retry aqui, um lote inteiro (até 20 leituras)
        falharia de uma vez em vez de aguardar e tentar de novo como as
        chamadas individuais já fazem.
        """
        last_response = None
        with _concurrency_limiter:
            for attempt, delay in enumerate((*_TRANSIENT_RETRY_DELAYS_S, None)):
                r = httpx.post(url, headers=headers, json=json_body, timeout=_READ_TIMEOUT_S)
                if r.status_code not in _TRANSIENT_STATUS_CODES:
                    return r
                last_response = r
                if delay is not None:
                    wait_s = _retry_after_seconds(r, delay)
                    logger.warning(
                        "SharePoint $batch: status %s transitório (tentativa %d/%d) — retry em %.1fs%s",
                        r.status_code,
                        attempt + 1,
                        len(_TRANSIENT_RETRY_DELAYS_S) + 1,
                        wait_s,
                        " (Retry-After respeitado)" if wait_s != delay else "",
                    )
                    time.sleep(wait_s)
        return last_response

    def _raise_for_read_status(self, r: Any, path: str) -> None:
        """Como r.raise_for_status(), mas erros de leitura persistentes (não 404) viram
        StorageUnavailableError — a rota HTTP não precisa de try/except; o handler
        global em app.py converte para 503 com Retry-After (ver ADR-047 §D7)."""
        try:
            r.raise_for_status()
        except Exception as exc:
            raise StorageUnavailableError(
                f"SharePoint indisponível ao ler '{path}' (status={r.status_code}): {exc}"
            ) from exc

    # ── BlobStoragePort ────────────────────────────────────────────────────

    def ler_blob(self, path: str) -> bytes:
        """Lê blob do SharePoint com cache ETag + TTL (ADR-047 §D2)."""
        httpx = self._client()
        if self._cache:
            result = self._ler_blob_cached(path, httpx)
            if result is not None:
                return result
        return self._ler_blob_direct(path, httpx)

    def _ler_blob_cached(self, path: str, httpx) -> bytes | None:
        # O único caller (ler_blob) já garante `self._cache` truthy antes de
        # chamar este método, então `cache` nunca é None aqui.
        cache = self._cache
        assert cache is not None, "cache deve ser não-None quando _ler_blob_cached é chamado"
        cached = cache.get(path)
        if cached:
            content, meta = cached
            try:
                r = httpx.get(
                    self._item_url(path),
                    headers=self._headers({"If-None-Match": meta.etag}),
                    follow_redirects=True,
                    timeout=_READ_TIMEOUT_S,
                )
                if r.status_code == 304:
                    return content
                if r.status_code == 200:
                    etag = r.headers.get("ETag", meta.etag)
                    lm = r.headers.get("Last-Modified", meta.last_modified)
                    content_r = httpx.get(
                        self._item_content_url(path),
                        headers=self._headers(),
                        follow_redirects=True,
                        timeout=_READ_TIMEOUT_S,
                    )
                    if content_r.status_code == 200:
                        cache.put(path, content_r.content, etag, lm)
                        return content_r.content
            except Exception:
                if self._offline:
                    stale = cache.get_stale(path)
                    if stale:
                        logger.warning(f"SharePoint offline — usando cache expirado: {path}")
                        return stale[0]
                raise
        return None

    def _ler_blob_direct(self, path: str, httpx) -> bytes:
        if self._offline:
            if self._cache:
                stale = self._cache.get_stale(path)
                if stale:
                    return stale[0]
            raise FileNotFoundError(f"Modo offline: blob não encontrado no cache: {path}")
        try:
            r = self._get_with_retry(httpx, self._item_content_url(path), self._headers())
        except Exception as exc:
            raise FileNotFoundError(f"Erro ao acessar SharePoint para {path}: {exc}") from exc
        if r.status_code == 404:
            raise FileNotFoundError(f"Blob não encontrado no SharePoint: {path}")
        self._raise_for_read_status(r, path)
        content = r.content
        if self._cache:
            etag = r.headers.get("ETag", "")
            lm = r.headers.get("Last-Modified", "")
            self._cache.put(path, content, etag, lm)
        return content

    def _batch_relative_content_url(self, path: str) -> str:
        """URL relativa (sem `https://graph.microsoft.com/v1.0`) do conteúdo do
        item — formato exigido pelos sub-requests de `$batch` (Graph rejeita URL
        absoluta ali; a autenticação do lote inteiro é feita 1x, no request
        externo — sub-requests não levam Authorization própria)."""
        safe = path.strip("/")
        return f"/drives/{self._drive_id}/root:/{self._root_path}/{safe}:/content"

    @staticmethod
    def _decode_batch_body(body: Any) -> bytes | None:
        """Decodifica o `body` de uma sub-resposta de `$batch`.

        Para arquivos .json (o caso do catálogo — só JSON), o Graph normalmente
        já devolve o conteúdo inline como objeto JSON nativo (a sub-resposta tem
        Content-Type application/json), sem base64. Trata também string (texto
        puro ou, mais raro, conteúdo base64) por robustez. Formato não
        reconhecido retorna None — o chamador cai para leitura individual só
        daquele path, não do lote inteiro.
        """
        if body is None:
            return None
        if isinstance(body, dict | list):
            return json.dumps(body, ensure_ascii=False).encode("utf-8")
        if isinstance(body, str):
            try:
                decoded = base64.b64decode(body, validate=True)
                decoded.decode("utf-8")  # confirma texto válido — não é binário arbitrário que por acaso decodificou
                return decoded
            except Exception:
                return body.encode("utf-8")
        return None

    def _fetch_download_urls_parallel(self, httpx: Any, download_urls: dict[str, str]) -> dict[str, bytes]:
        """Busca o conteúdo real a partir das URLs pré-autenticadas devolvidas
        pelo `$batch`.

        2026-08-11 (confirmado em produção): o Graph NÃO inlina o conteúdo de
        `:/content` para itens do SharePoint (drive de site, diferente de
        OneDrive pessoal) — toda sub-resposta de `$batch` vem como 302 com
        header `Location` apontando pra uma URL de download pré-autenticada
        (`tempauth` na própria query string) e body vazio. `_decode_batch_body`
        nunca é alcançado nesse caso (status != 200); é preciso seguir o
        redirect manualmente numa segunda fase.

        A URL do `Location` já é pré-autenticada — sem `Authorization`, e sem
        contar contra a cota de throttling do Graph API (é servida pelo próprio
        SharePoint/CDN, não pelo endpoint `/v1.0/`) — pode paralelizar mais
        agressivamente que `_MAX_CONCURRENT_REQUESTS` (esse teto é
        especificamente sobre chamadas ao Graph). Ainda conservador (2×, não
        um valor grande) por causa do teto de CPU do cgroup do container (ADR-180
        / issue #149) — rajada grande de handshakes TLS concorrentes já
        suspendeu o container inteiro antes.
        """
        result: dict[str, bytes] = {}
        items = list(download_urls.items())

        def _fetch(item: tuple[str, str]) -> tuple[str, bytes | None]:
            path, url = item
            try:
                r = httpx.get(url, follow_redirects=True, timeout=_READ_TIMEOUT_S)
                if r.status_code == 200:
                    return path, r.content
            except Exception:
                pass
            return path, None

        with ThreadPoolExecutor(max_workers=min(_MAX_CONCURRENT_REQUESTS * 2, len(items))) as pool:
            for path, content in pool.map(_fetch, items):
                if content is not None:
                    result[path] = content
        return result

    def ler_blobs_batch(self, paths: list[str]) -> dict[str, bytes]:
        """Lê vários blobs numa única (ou poucas) chamada(s) via Graph `$batch` —
        até `_GRAPH_BATCH_SIZE` sub-requests por lote (ver BlobStoragePort).

        Causa raiz de fundo do timeout em pesquisar_catalogo/catalog tools (issue
        #147/#148/#149/#153): carregar o catálogo "mendeslobo" faz 800+ leituras
        individuais (1 GET :/content por arquivo). O pooling de conexão
        (2026-08-11) eliminou o handshake TCP+TLS repetido, mas não o N+1 em si
        — isto ataca o N+1 propriamente, em 2 fases:
          1. `$batch`: até 20 leituras por chamada HTTP ao Graph — ~800
             round-trips → ~40. Pra drives de SharePoint (não OneDrive pessoal),
             cada sub-resposta de `:/content` vem como 302 com a URL de
             download pré-autenticada no header `Location` (confirmado em
             produção — Graph não inlina o conteúdo aqui), não o conteúdo
             direto — por isso a fase 2.
          2. Segue os redirects em paralelo (`_fetch_download_urls_parallel`)
             — são URLs pré-autenticadas, não chamadas ao Graph, então não
             sofrem do throttling que rege `_MAX_CONCURRENT_REQUESTS`.

        Sub-resposta com Content-Type JSON nativo (200 direto, sem redirect —
        mantido por robustez, ex.: OneDrive pessoal ou mudança de comportamento
        do Graph) também é aceita. Paths que falharem em ambas as fases (sub-
        resposta ausente/erro, download falhou) são omitidos do dict de
        retorno — o chamador (`_read_json_blobs`) cai para `ler_blob`
        individual só nesses casos.
        """
        if not paths:
            return {}
        httpx = self._client()
        result: dict[str, bytes] = {}
        download_urls: dict[str, str] = {}

        for i in range(0, len(paths), _GRAPH_BATCH_SIZE):
            chunk = paths[i : i + _GRAPH_BATCH_SIZE]
            id_to_path = {str(idx): p for idx, p in enumerate(chunk)}
            requests_body = {
                "requests": [
                    {"id": rid, "method": "GET", "url": self._batch_relative_content_url(p)}
                    for rid, p in id_to_path.items()
                ]
            }
            try:
                r = self._post_with_retry(httpx, f"{_GRAPH_BASE}/$batch", self._headers(), requests_body)
            except Exception as exc:
                logger.warning(
                    "SharePoint $batch: chamada falhou (%d paths, fallback individual): %s", len(chunk), exc
                )
                continue
            if r is None or r.status_code != 200:
                logger.warning(
                    "SharePoint $batch: status %s inesperado (%d paths, fallback individual)",
                    getattr(r, "status_code", "?"),
                    len(chunk),
                )
                continue

            try:
                responses = r.json().get("responses", [])
            except Exception:
                continue

            for sub in responses:
                path = id_to_path.get(str(sub.get("id")))
                if path is None:
                    continue
                status = sub.get("status")
                if status == 200:
                    content = self._decode_batch_body(sub.get("body"))
                    if content is not None:
                        result[path] = content
                elif status in (301, 302, 303, 307, 308):
                    location = (sub.get("headers") or {}).get("Location")
                    if location:
                        download_urls[path] = location
                # outro status: omitido — cai pro fallback individual do chamador

        if download_urls:
            result.update(self._fetch_download_urls_parallel(httpx, download_urls))

        return result

    def gravar_blob(self, path: str, content: bytes) -> None:
        """Grava blob no SharePoint (ADR-047 §D1, §D3).

        < 4 MB: PUT direto.
        >= 4 MB: upload session com suporte a retomada.
        If-Match: ETag para otimistic concurrency (412 → StorageConcurrencyError).
        """
        if self._read_only:
            raise PermissionError(f"Storage configurado como read-only: {path}")

        httpx = self._client()

        if len(content) < _LARGE_FILE_THRESHOLD:
            self._gravar_pequeno(httpx, path, content)
        else:
            self._gravar_upload_session(httpx, path, content)

        if self._cache:
            self._cache.invalidate(path)

    def _gravar_pequeno(self, httpx: Any, path: str, content: bytes) -> None:
        """PUT direto para arquivos < 4 MB."""
        r = httpx.put(
            self._item_content_url(path),
            headers=self._headers({"Content-Type": "application/octet-stream"}),
            content=content,
            timeout=_WRITE_TIMEOUT_S,
        )
        if r.status_code == 412:
            raise StorageConcurrencyError(
                f"Conflito de escrita (ETag mismatch) para {path}. Outro agente gravou o arquivo concorrentemente."
            )
        r.raise_for_status()

    def _gravar_upload_session(self, httpx: Any, path: str, content: bytes) -> None:
        """Upload session para arquivos >= 4 MB (ADR-047 §D3)."""
        # 1. Create upload session
        r = httpx.post(
            f"{self._item_url(path)}:/createUploadSession",
            headers=self._headers({"Content-Type": "application/json"}),
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
            timeout=_WRITE_TIMEOUT_S,
        )
        r.raise_for_status()
        upload_url = r.json()["uploadUrl"]

        # 2. Upload in chunks
        chunk_size = 5 * 1024 * 1024  # 5 MB
        total = len(content)
        offset = 0
        while offset < total:
            chunk = content[offset : offset + chunk_size]
            end = offset + len(chunk) - 1
            headers = {
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {offset}-{end}/{total}",
                "Content-Type": "application/octet-stream",
            }
            r = httpx.put(upload_url, headers=headers, content=chunk, timeout=_WRITE_TIMEOUT_S)
            r.raise_for_status()
            offset += len(chunk)

    def listar_blobs(self, prefix: str) -> list[str]:
        """Lista blobs com prefixo via children API com paginação (ADR-047 §D1)."""
        httpx = self._client()
        safe = prefix.strip("/")
        url = (
            f"{_GRAPH_BASE}/drives/{self._drive_id}/root:/{self._root_path}/{safe}:/children"
            if safe
            else f"{_GRAPH_BASE}/drives/{self._drive_id}/root:/{self._root_path}:/children"
        )
        results: list[str] = []

        while url:
            try:
                # issue #147: sem timeout explícito aqui, uma falha de rede transitória
                # (ou muitos níveis de recursão em subpastas, cada um sujeito ao default
                # do httpx) podia se acumular em dezenas de segundos sem erro nem retorno
                # — usa o mesmo _get_with_retry (com backoff) das demais leituras, e um
                # timeout de request explícito, para um comportamento previsível e limitado.
                r = self._get_with_retry(
                    httpx, url, self._headers(), params={"$select": "name,folder,file", "$top": "200"}
                )
            except Exception as exc:
                if self._offline and self._cache:
                    logger.warning(f"SharePoint offline — listar_blobs({prefix}) retorna lista vazia.")
                    return []
                raise FileNotFoundError(f"Erro ao listar SharePoint {prefix}: {exc}") from exc

            if r.status_code == 404:
                return []
            self._raise_for_read_status(r, prefix)
            data = r.json()

            for item in data.get("value", []):
                item_path = f"{safe}/{item['name']}".lstrip("/") if safe else item["name"]
                if "folder" in item:
                    # Recurse into subfolders
                    sub = self.listar_blobs(item_path)
                    results.extend(sub)
                else:
                    results.append(item_path)

            url = data.get("@odata.nextLink")  # pagination

        return results

    def blob_existe(self, path: str) -> bool:
        """Verifica existência — sempre consulta a API (sem cache, ADR-047 §D3)."""
        httpx = self._client()
        try:
            r = httpx.get(self._item_url(path), headers=self._headers(), timeout=_READ_TIMEOUT_S)
            return r.status_code == 200
        except Exception:
            return False

    def deletar_blob(self, path: str) -> None:
        """Remove um item do SharePoint via Graph DELETE (ADR-047 §D1).

        Se o path for uma pasta, remove recursivamente (Graph deleta a pasta inteira).
        Lança FileNotFoundError se o item não existir.
        """
        httpx = self._client()
        r = httpx.delete(self._item_url(path), headers=self._headers(), timeout=_READ_TIMEOUT_S)
        if r.status_code == 404:
            raise FileNotFoundError(f"Blob não encontrado para deletar: {path}")
        if r.status_code not in (200, 204):
            r.raise_for_status()
        if self._cache:
            self._cache.invalidate(path)

    def aprovar_versao(self, path: str) -> None:
        """Checkin de versão major no SharePoint (ADR-047 §D4).

        Equivalente ao chmod 444 do LocalBlobStorage. O arquivo passa a ser
        somente-leitura para edições diretas; histórico de versões fica auditável
        no portal M365.

        Graph exige que o item esteja checked out antes de aceitar um checkin
        quando a biblioteca tem "Require Check Out" habilitado — como
        `gravar_blob` grava via PUT direto (nunca checa o arquivo out), o
        checkin sempre falhava com 400 ("the item is not checked out"). Faz o
        checkout aqui, best-effort: se já estiver checked out (por nós ou por
        outra sessão) ou se a biblioteca não exigir check-out, o Graph
        devolve erro no checkout mas o checkin subsequente ainda é a fonte de
        verdade — só ele propaga falha real (permissão, item inexistente etc.).
        """
        httpx = self._client()
        try:
            httpx.post(f"{self._item_url(path)}:/checkout", headers=self._headers(), timeout=_READ_TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001 — best-effort, checkin reporta o erro real
            logger.debug("checkout best-effort falhou para '%s' (seguindo para checkin): %s", path, exc)

        r = httpx.post(
            f"{self._item_url(path)}:/checkin",
            headers=self._headers({"Content-Type": "application/json"}),
            json={"checkInAs": "majorVersion", "comment": "Aprovado via Concilium"},
            timeout=_READ_TIMEOUT_S,
        )
        if r.status_code == 404:
            raise FileNotFoundError(f"Arquivo não encontrado para aprovar: {path}")
        r.raise_for_status()

    def gerar_url_temporaria(self, path: str, ttl_segundos: int = 900, *, scope: str = "anonymous") -> str | None:
        """Cria um sharing link de leitura com expiração (ADR-093 D4).

        Usa Graph ``createLink`` (type=view). `scope="anonymous"` (default) exige
        que o site permita compartilhamento externo — confirmado em produção que
        o site atual NÃO permite (Graph retorna 403 "sharingDisabled", ver
        ADR-135 §D3.1). `scope="organization"` exige apenas login com uma conta do
        mesmo tenant (sem expor o link publicamente) e funciona mesmo com
        compartilhamento externo desabilitado — use esse valor quando o
        destinatário já tem conta no tenant (ex.: link do proxy para funcionários).

        Se a chamada falhar (qualquer scope), retorna ``None`` — não há mais
        fallback de anexo (executáveis/.mcpb são bloqueados por provedores de
        email, ver `notifications._distribution_attachments`), então o
        chamador (`commands_auth.py::_warn_if_no_mcpb_url`) avisa o admin no
        terminal para entrega manual. A falha é logada (não mais engolida
        silenciosamente) para que a causa fique visível nos logs em vez de
        aparecer só como "None" sem explicação.
        """
        from datetime import datetime, timedelta

        httpx = self._client()
        exp = (datetime.now(UTC) + timedelta(seconds=max(60, ttl_segundos))).isoformat()
        try:
            r = httpx.post(
                f"{self._item_url(path)}:/createLink",
                headers=self._headers({"Content-Type": "application/json"}),
                json={"type": "view", "scope": scope, "expirationDateTime": exp},
                timeout=_READ_TIMEOUT_S,
            )
            if r.status_code in (200, 201):
                return (r.json().get("link") or {}).get("webUrl")
            logger.warning(
                "gerar_url_temporaria('%s'): Graph createLink retornou %d: %s",
                path,
                r.status_code,
                r.text[:500],
            )
        except Exception:
            logger.warning("gerar_url_temporaria('%s'): falha ao chamar Graph createLink.", path, exc_info=True)
            return None
        return None

    def ensure_root_path(self) -> None:
        """Cria root_path no SharePoint se não existir (chame no startup da aplicação)."""
        if self._root_ensured:
            return
        self._ensure_root_path(self._client())
        self._root_ensured = True

    def _ensure_root_path(self, httpx: Any) -> None:
        """Cria root_path no SharePoint se não existir (idempotente, segmento a segmento)."""
        if not self._root_path:
            return
        r = httpx.get(
            f"{_GRAPH_BASE}/drives/{self._drive_id}/root:/{self._root_path}",
            headers=self._headers(),
            timeout=10.0,
        )
        if r.status_code == 200:
            return
        if r.status_code != 404:
            r.raise_for_status()
        segments = self._root_path.split("/")
        current = ""
        for segment in segments:
            if current:
                url = f"{_GRAPH_BASE}/drives/{self._drive_id}/root:/{current}:/children"
            else:
                url = f"{_GRAPH_BASE}/drives/{self._drive_id}/root/children"
            r = httpx.post(
                url,
                headers=self._headers({"Content-Type": "application/json"}),
                json={"name": segment, "folder": {}, "@microsoft.graph.conflictBehavior": "replace"},
                timeout=10.0,
            )
            if r.status_code not in (200, 201):
                r.raise_for_status()
            current = f"{current}/{segment}".lstrip("/") if current else segment
        logger.info("SharePoint root_path criado: %s", self._root_path)

    def health_check(self) -> dict[str, Any]:
        """Verifica conectividade com o SharePoint Drive (ADR-047 §D7)."""
        httpx = self._client()
        try:
            r = httpx.get(
                f"{_GRAPH_BASE}/drives/{self._drive_id}",
                headers=self._headers(),
                timeout=10.0,
            )
            if r.status_code == 200:
                data = r.json()
                return {
                    "status": "ok",
                    "drive_name": data.get("name", ""),
                    "drive_type": data.get("driveType", ""),
                    "backend": "sharepoint",
                }
            return {"status": "error", "code": r.status_code, "backend": "sharepoint"}
        except Exception as exc:
            return {"status": "error", "message": str(exc), "backend": "sharepoint"}


class StorageConcurrencyError(Exception):
    """Raised when a concurrent write creates an ETag conflict (HTTP 412)."""
