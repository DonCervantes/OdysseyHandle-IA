#!/usr/bin/env bash
# Levanta AutoGuard AI completo en local (datos SIMULADOS, sin llaves, sin red):
#   API FastAPI :8000 + tablero Streamlit :8501 (vía scripts/demo.sh) y el frontend Vite :5173.
#
#   bash frontend/start-local.sh          # levanta todo; Ctrl+C detiene solo el frontend
#   bash frontend/start-local.sh --stop   # detiene API y tablero
#
# Variables opcionales: PYTHON, API_PORT (8000), DASH_PORT (8501), WEB_PORT (5173).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"

if [ "${1:-}" = "--stop" ]; then
  bash "$ROOT/scripts/demo.sh" --stop
  exit 0
fi

command -v npm >/dev/null 2>&1 || { echo "ERROR: necesitas Node.js 18+ con npm (https://nodejs.org)." >&2; exit 1; }

echo "==> Backend (API :$API_PORT y tablero), en modo simulado"
if curl -fsS -m 3 "http://localhost:$API_PORT/health" >/dev/null 2>&1; then
  echo "La API ya responde en :$API_PORT; no se vuelve a levantar."
else
  API_PORT="$API_PORT" bash "$ROOT/scripts/demo.sh" --start
fi

echo "==> Frontend :$WEB_PORT"
cd "$HERE"
[ -d node_modules ] || npm install --no-audit --no-fund
echo "Abre http://localhost:$WEB_PORT  (app: http://localhost:$WEB_PORT/app). Ctrl+C para detener el frontend;"
echo "para detener API y tablero: bash frontend/start-local.sh --stop"
VITE_API_URL="${VITE_API_URL:-http://localhost:$API_PORT}" exec npx vite --port "$WEB_PORT"
