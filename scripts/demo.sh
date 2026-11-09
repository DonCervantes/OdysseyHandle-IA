#!/usr/bin/env bash
# Prepara la demo de KAVAK AUTOGUARD AI en modo mock (datos SIMULADOS, sin llaves, sin red).
#
#   bash scripts/demo.sh            # corre el experimento seed 42 (si falta) e imprime cómo levantar todo
#   bash scripts/demo.sh --start    # además levanta API y tablero en segundo plano
#   bash scripts/demo.sh --stop     # detiene lo que levantó --start
#   bash scripts/demo.sh --force    # regenera la corrida de la demo aunque ya exista
#
# Variables opcionales: PYTHON (intérprete), API_PORT (8000), DASH_PORT (8501).
# Guion de la demo: docs/demo.md.
set -euo pipefail

SEED=42
RUN_NAME="demo-seed${SEED}"
API_PORT="${API_PORT:-8000}"
DASH_PORT="${DASH_PORT:-8501}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
RUNS_DIR="$ROOT/var/runs"
RUN_DIR="$RUNS_DIR/$RUN_NAME"
STATE_DIR="$ROOT/var/demo"

START=0
STOP=0
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --start) START=1 ;;
    --stop) STOP=1 ;;
    --force) FORCE=1 ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Opción desconocida: $arg (usa --help)" >&2; exit 2 ;;
  esac
done

say() { printf '\n==> %s\n' "$*"; }

stop_services() {
  local found=0 name pid_file pid
  for name in api tablero; do
    pid_file="$STATE_DIR/$name.pid"
    [ -f "$pid_file" ] || continue
    found=1
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" && echo "Detenido $name (pid $pid)."
    else
      echo "$name (pid $pid) ya no estaba corriendo."
    fi
    rm -f "$pid_file"
  done
  [ "$found" -eq 1 ] || echo "No hay servicios de la demo registrados en $STATE_DIR."
}

if [ "$STOP" -eq 1 ]; then
  stop_services
  exit 0
fi

# ------------------------------------------------------------------ 1. venv
find_python() {
  if [ -n "${PYTHON:-}" ]; then echo "$PYTHON"; return 0; fi
  local candidates=("$ROOT/.venv/bin/python" "$ROOT/.venv/Scripts/python.exe")
  # En un worktree de git, el .venv vive en el checkout principal.
  local common
  if common="$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)"; then
    candidates+=("$common/../.venv/bin/python" "$common/../.venv/Scripts/python.exe")
  fi
  local c
  for c in "${candidates[@]}"; do
    if [ -x "$c" ]; then echo "$c"; return 0; fi
  done
  return 1
}

say "Verificando entorno virtual"
if ! PY="$(find_python)"; then
  cat >&2 <<'EOF'
No encontré el venv (.venv). Créalo primero desde la raíz del repo:
  python -m venv .venv && .venv/bin/python -m pip install -e '.[dev]'
(o define PYTHON=/ruta/a/python)
EOF
  exit 1
fi
if ! "$PY" -c 'import autoguard, streamlit, uvicorn' 2>/dev/null; then
  echo "El venv ($PY) no tiene las dependencias. Ejecuta: $PY -m pip install -e '.[dev]'" >&2
  exit 1
fi
echo "Python: $PY ($("$PY" --version 2>&1))"

# ------------------------------------------------------------------ 2. modo mock
export AUTOGUARD_NO_DOTENV=1
export VALUACION_OFFLINE=1
export DATABASE_URL="sqlite:///$ROOT/var/demo.db"
export LLM_PROVIDER=mock
export AUTOGUARD_RUNS_DIR="$RUNS_DIR"
export PYTHONIOENCODING=utf-8
echo "LLM_PROVIDER=mock (sin llamadas al LLM real) · corridas en $RUNS_DIR"

# ------------------------------------------------------------------ 3. corrida seed 42
if [ "$FORCE" -eq 1 ] && [ -d "$RUN_DIR" ]; then
  say "Borrando corrida anterior ($RUN_DIR) por --force"
  rm -rf "$RUN_DIR"
fi
if [ -f "$RUN_DIR/summary.json" ]; then
  say "La corrida de la demo ya existe: $RUN_DIR (usa --force para regenerarla)"
else
  if [ -d "$RUN_DIR" ]; then
    echo "Hay una corrida incompleta en $RUN_DIR (sin summary.json). Bórrala o usa --force." >&2
    exit 1
  fi
  mkdir -p "$RUNS_DIR"
  say "Corriendo el experimento RSI (seed $SEED, 3 variantes; tarda unos minutos)"
  "$PY" -m autoguard.rsi.loop --seed "$SEED" --output-dir "$RUN_DIR" > "$RUN_DIR.log"
  echo "Salida completa en $RUN_DIR.log"
fi

say "Resumen de la corrida (datos SIMULADOS)"
"$PY" - "$RUN_DIR/summary.json" <<'EOF'
import json, sys
s = json.load(open(sys.argv[1], encoding="utf-8"))
r = s["regret"]
for v in ("estatico", "parametros", "rsi"):
    print(f"  regret {v:<10} {r[v]:>16,.0f} MXN")
print(f"  mejora RSI vs estático: {s['mejora_rsi']:.1%}")
c = s.get("convergencia_polizas", {})
print(f"  convergencia (pólizas): rsi={c.get('rsi')} parametros={c.get('parametros')}")
print(f"  gate2: {s['gate2']} · {s['elapsed_seconds']:.0f} s")
EOF

# ------------------------------------------------------------------ 4. API y tablero
if [ "$START" -eq 1 ]; then
  mkdir -p "$STATE_DIR"
  stop_services >/dev/null 2>&1 || true
  say "Levantando API en :$API_PORT y tablero en :$DASH_PORT (segundo plano)"
  nohup "$PY" -m uvicorn autoguard.api.main:app --port "$API_PORT" \
    > "$STATE_DIR/api.log" 2>&1 &
  echo $! > "$STATE_DIR/api.pid"
  nohup "$PY" -m streamlit run dashboard/app.py --server.port "$DASH_PORT" --server.headless true \
    > "$STATE_DIR/tablero.log" 2>&1 &
  echo $! > "$STATE_DIR/tablero.pid"
  cat <<EOF
  API:     http://localhost:$API_PORT/docs   (log: var/demo/api.log)
  Tablero: http://localhost:$DASH_PORT       (log: var/demo/tablero.log)
  En el tablero elige la corrida "$RUN_NAME", activa "Activar reproducción" y pulsa ▶ Play.
  Para detener todo: bash scripts/demo.sh --stop
EOF
else
  cat <<EOF

Listo. Para levantar la demo (cada uno en su terminal, desde $ROOT):
  LLM_PROVIDER=mock $PY -m uvicorn autoguard.api.main:app --port $API_PORT
  AUTOGUARD_RUNS_DIR=$RUNS_DIR $PY -m streamlit run dashboard/app.py --server.port $DASH_PORT
o en segundo plano: bash scripts/demo.sh --start   (detener: bash scripts/demo.sh --stop)
En el tablero elige la corrida "$RUN_NAME", activa "Activar reproducción" y pulsa ▶ Play.
Guion: docs/demo.md
EOF
fi
