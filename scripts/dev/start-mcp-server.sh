#!/bin/bash
# Script para iniciar o servidor MCP do Concilium
# Uso: ./scripts/start-mcp-server.sh [start|stop|status|log]

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="${REPO_ROOT}/.concilium/mcp-server.pid"
LOG_FILE="${REPO_ROOT}/.concilium/mcp-server.log"

mkdir -p "${REPO_ROOT}/.concilium"

cmd="${1:-status}"

case "$cmd" in
  start)
    echo "Iniciando MCP Server Concilium..."
    if [ -f "$PID_FILE" ]; then
      old_pid=$(cat "$PID_FILE")
      if ps -p "$old_pid" > /dev/null 2>&1; then
        echo "✅ Server já está rodando (PID: $old_pid)"
        exit 0
      fi
    fi
    
    cd "$REPO_ROOT"
    source .venv/bin/activate
    nohup python -m concilium.presentation.mcp > "$LOG_FILE" 2>&1 &
    pid=$!
    echo $pid > "$PID_FILE"
    sleep 2
    
    # Verifica se o processo continua rodando
    if ps -p $pid > /dev/null 2>&1; then
      echo "✅ MCP Server iniciado (PID: $pid)"
      echo "   Log: $LOG_FILE"
      tail -5 "$LOG_FILE"
    else
      echo "❌ Erro ao iniciar server"
      tail -20 "$LOG_FILE"
      exit 1
    fi
    ;;
  
  stop)
    pkill -f "python -m concilium.presentation.mcp" || true
    if [ -f "$PID_FILE" ]; then
      rm "$PID_FILE"
    fi
    echo "✅ MCP Server parado"
    ;;
  
  status)
    # Verifica via processo, não via PID file (mais robusto)
    if pgrep -f "python -m concilium.presentation.mcp" > /dev/null; then
      pid=$(pgrep -f "python -m concilium.presentation.mcp")
      echo "✅ MCP Server está rodando (PID: $pid)"
      if [ -f "$LOG_FILE" ]; then
        tail -1 "$LOG_FILE"
      fi
    else
      echo "❌ MCP Server não está rodando"
    fi
    ;;
  
  log)
    if [ -f "$LOG_FILE" ]; then
      tail -f "$LOG_FILE"
    else
      echo "❌ Log file não encontrado"
    fi
    ;;
  
  *)
    echo "Uso: $0 {start|stop|status|log}"
    exit 1
    ;;
esac
