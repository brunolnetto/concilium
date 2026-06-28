# Dockerfile de produção — multi-stage.
# Stage 1 (builder): instala deps com uv
# Stage 2 (final):   imagem mínima sem uv, sem deps de dev, usuário não-root
#
# Ambos os stages usam Docker Hub (sem autenticação ghcr.io necessária).

# ─────────────────────────────────────────────────────────────
# Stage 1: builder (resolve deps + build wheel)
# ─────────────────────────────────────────────────────────────
FROM python:3.13-slim-bookworm AS builder

RUN pip install --no-cache-dir uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /workspace/concilium

# Dependencies first (cache layer)
COPY pyproject.toml uv.lock ./

RUN uv sync --locked --no-install-project

# Source code
COPY . .

# Build wheel (this is the key simplification)
RUN uv build


# ─────────────────────────────────────────────────────────────
# Stage 2: runtime (clean + deterministic)
# ─────────────────────────────────────────────────────────────
FROM python:3.13-slim-bookworm

RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot

WORKDIR /app

# Install wheel (no venv copying, no path coupling)
COPY --from=builder /workspace/concilium/dist/*.whl /tmp/

RUN pip install --no-cache-dir /tmp/*.whl \
 && rm -rf /tmp/*.whl

USER nonroot

EXPOSE 8000 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT []