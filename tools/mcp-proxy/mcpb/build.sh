#!/usr/bin/env bash
# Empacota os 3 binários PyInstaller do proxy (build-proxy.yml) num único
# .mcpb universal (ADR-161 D1/D3) via `mcpb pack` do CLI oficial
# @anthropic-ai/mcpb. Não builda os binários — apenas os empacota.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${1:?uso: build.sh <dir-com-os-3-binarios> [output.mcpb]}"
OUTPUT="${2:-$SCRIPT_DIR/concilium-mcp-proxy.mcpb}"

REQUIRED_BINS=(
  "concilium-mcp-proxy.exe"
  "concilium-mcp-proxy-macos"
  "concilium-mcp-proxy-linux"
)
for bin in "${REQUIRED_BINS[@]}"; do
  if [ ! -f "$BIN_DIR/$bin" ]; then
    echo "erro: $BIN_DIR/$bin não encontrado" >&2
    exit 1
  fi
done

STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

mkdir -p "$STAGING/server"
for bin in "${REQUIRED_BINS[@]}"; do
  cp "$BIN_DIR/$bin" "$STAGING/server/$bin"
done
chmod +x "$STAGING/server/concilium-mcp-proxy-linux" "$STAGING/server/concilium-mcp-proxy-macos"
cp "$SCRIPT_DIR/manifest.json" "$STAGING/manifest.json"

npx --yes @anthropic-ai/mcpb validate "$STAGING/manifest.json"
npx --yes @anthropic-ai/mcpb pack "$STAGING" "$OUTPUT"

echo "gerado: $OUTPUT"
