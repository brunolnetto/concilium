# Dockerfile de produção — multi-stage.
# Stage 1 (builder): instala deps com uv
# Stage 2 (final):   imagem mínima sem uv, sem deps de dev, usuário não-root
#
# Ambos os stages usam Docker Hub (sem autenticação ghcr.io necessária).

# ── Stage 1: builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS builder

RUN pip install --no-cache-dir uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /workspace/concilium

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

COPY . /workspace/concilium
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# ── Stage 2: final (sem uv, sem deps de dev) ─────────────────────────────────
# Usar o mesmo sabor Debian do builder para garantir compatibilidade do interpretador Python
FROM python:3.12-slim-bookworm

# Usuário não-root para segurança em produção
RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot

# Copia o ambiente virtual e o código do builder
COPY --from=builder --chown=nonroot:nonroot /workspace/concilium /workspace/concilium

# Executáveis do venv (concilium-api, concilium-ui, concilium-mcp) no PATH
ENV PATH="/workspace/concilium/.venv/bin:$PATH"

WORKDIR /workspace/concilium

USER nonroot

# Porta 8000: FastAPI REST
# Porta 8080: FastMCP MCP server (transport HTTP)
EXPOSE 8000 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT []

# Default: API — sobreposto por `command` no compose / ACI
CMD ["concilium-api"]
