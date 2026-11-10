#!/usr/bin/env bash
# Regenerate the two 1080p videos from a real mock run. Keys are read only by narration.py.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAIN="$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir)/.."
PY="${PYTHON:-$MAIN/.venv/bin/python}"
cd "$ROOT"
for tool in node npm ffmpeg ffprobe; do
  command -v "$tool" >/dev/null || { echo "Falta $tool (Node.js y brew install ffmpeg)." >&2; exit 2; }
done
[ -x "$PY" ] || { echo 'Falta .venv del repositorio.' >&2; exit 2; }
[ -d video/node_modules ] || npm ci --prefix video --no-audit --no-fund
# Run services from the main checkout so data and .env have one unambiguous location.
(cd "$MAIN" && bash scripts/demo.sh --start)
for port in 8000 8501 5173; do
  ready=0
  for attempt in {1..30}; do
    if curl -fsS --max-time 2 "http://localhost:$port/" >/dev/null 2>&1 || { [ "$port" = 8000 ] && curl -fsS --max-time 2 http://localhost:8000/health >/dev/null; }; then ready=1; break; fi
    sleep 1
  done
  [ "$ready" = 1 ] || { echo "Servicio :$port no está listo; revisar var/demo/*.log" >&2; exit 1; }
done
"$PY" video/evidence.py
"$PY" video/narration.py
"$PY" video/documents.py
"$PY" video/stage.py
node video/capture.mjs
node video/render.mjs
"$PY" video/verify.py
printf '\nVideos listos: %s/var/video/demo_3min.mp4 y fondo_pitch.mp4\n' "$MAIN"
