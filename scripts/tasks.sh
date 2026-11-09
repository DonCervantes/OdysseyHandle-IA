#!/usr/bin/env bash
# Tablero de tareas compartido entre sesiones/máquinas/herramientas (Claude, GPT/Codex, Cursor).
#
# - DEFINICIÓN de tareas: TASKS.md en origin/main.
# - ESTADO: rama remota `tasks-state` (archivos <T-XX>/{status,owner,reviewer,review_notes,log}).
#   Cada cambio de estado es un commit + push. Si otra sesión empujó antes, el push se rechaza
#   (no fast-forward), se re-lee el estado y se reintenta => los claims son atómicos entre máquinas.
# - TRABAJO: cada tarea en la rama `task/T-XX`, en el worktree local `.worktrees/T-XX`.
# - MERGE: `approve` mergea en un worktree temporal desde origin/main y empuja a main (reintenta si main avanzó).
#
# Compatible con bash 3.2 (macOS). Sin dependencias además de git.
set -euo pipefail

REMOTE="${TASKS_REMOTE:-origin}"
SB="tasks-state"
COMMON="$(git rev-parse --path-format=absolute --git-common-dir)"
MAIN="$(dirname "$COMMON")"
WT_DIR="$MAIN/.worktrees"
mkdir -p "$WT_DIR"
SESSIONS="claude-dylan claude-elias gpt-dylan cursor-elias"

die() { echo "ERROR: $*" >&2; exit 1; }
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
g() { git -C "$MAIN" "$@"; }

check_agent() { # nombre = <sesion>:<agente>  (p.ej. claude-dylan:w1)
  local who="$1" s="${1%%:*}"
  [ -n "$who" ] || die "falta nombre de agente (<sesion>:<agente>, p.ej. claude-dylan:w1)"
  case " $SESSIONS " in *" $s "*) ;; *) die "sesión '$s' desconocida. Válidas: $SESSIONS";; esac
}

fetch() {
  local i=0
  until g fetch -q "$REMOTE" "+refs/heads/main:refs/remotes/$REMOTE/main" "+refs/heads/$SB:refs/remotes/$REMOTE/$SB" 2>/dev/null; do
    i=$((i+1)); [ $i -ge 5 ] && die "no pude hacer fetch de $REMOTE (¿existe la rama $SB? corre: scripts/tasks.sh init-state)"; sleep 1
  done
}

# ---------- lectura de estado (sobre el commit BASE)
BASE=""
begin() { fetch; BASE="$(g rev-parse "$REMOTE/$SB")"; IDX="$(mktemp "${TMPDIR:-/tmp}/tasksidx.XXXXXX")"; rm -f "$IDX"; GIT_INDEX_FILE="$IDX" g read-tree "$BASE"; }
get() { g show "$BASE:$1/$2" 2>/dev/null || true; }
status() { local s; s="$(get "$1" status)"; echo "${s:-open}"; }
has() { g cat-file -e "$BASE:$1" 2>/dev/null; }

# ---------- escritura (índice temporal + commit-tree + push CAS)
put() { local blob; blob="$(printf '%s\n' "$3" | g hash-object -w --stdin)"; GIT_INDEX_FILE="$IDX" g update-index --add --cacheinfo "100644,$blob,$1/$2"; }
logline() { put "$1" log "$(get "$1" log)
$(now) $2"; }
setst() { put "$1" status "$2"; logline "$1" "$2 ${3:-}"; }
rmtask() { GIT_INDEX_FILE="$IDX" g ls-files -- "$1/" | while read -r f; do GIT_INDEX_FILE="$IDX" g update-index --force-remove "$f"; done; }
commit_push() {
  local tree c; tree="$(GIT_INDEX_FILE="$IDX" g write-tree)"; rm -f "$IDX"
  c="$(g commit-tree "$tree" -p "$BASE" -m "$1")"
  g push -q "$REMOTE" "$c:refs/heads/$SB" 2>/dev/null
}
# txn <funcion> args... : la función lee con get/status, escribe con put/setst y devuelve 0 (commit),
# 3 (no hacer nada, éxito sin cambios) u otro (error). Reintenta si el push pierde la carrera.
txn() {
  local fn="$1"; shift; local i=0 rc
  while :; do
    begin; set +e; "$fn" "$@"; rc=$?; set -e
    if [ $rc -eq 3 ]; then rm -f "$IDX"; return 0; fi
    if [ $rc -ne 0 ]; then rm -f "$IDX"; return $rc; fi
    if commit_push "$fn $*"; then return 0; fi
    i=$((i+1)); [ $i -ge 8 ] && die "demasiados conflictos de push en $SB"; sleep $(( (RANDOM % 3) + 1 ))
  done
}

# ---------- definición de tareas desde origin/main:TASKS.md  -> id|tipo|deps|titulo
parse() {
  g show "$REMOTE/main:TASKS.md" | awk '
    function flush() { if (id) print id "|" tipo "|" deps "|" title }
    /^### T-[0-9]+/ { flush(); id=$2; title=$0; sub(/^### T-[0-9]+ *· */, "", title); tipo="claude"; deps=""; next }
    /^- \*\*tipo:\*\*/ { t=$0; sub(/.*\*\*tipo:\*\* */, "", t); split(t, a, " "); tipo=a[1] }
    /^- \*\*deps:\*\*/ { d=$0; sub(/.*\*\*deps:\*\* */, "", d); out=""; n=split(d, a, /[^T0-9-]+/);
                         for (i=1;i<=n;i++) if (a[i] ~ /^T-[0-9]+$/) out=out (out?" ":"") a[i]; deps=out }
    END { flush() }'
}
taskfield() { parse | awk -F'|' -v id="$1" -v f="$2" '$1==id{print $f}'; }
deps_done() { local d; for d in $(taskfield "$1" 3); do [ "$(status "$d")" = "done" ] || return 1; done; }
exists() { local ids; ids="$(parse | cut -d"|" -f1)"; printf "%s\n" "$ids" | grep -qx "$1" || die "tarea $1 no existe en origin/main:TASKS.md"; }

ensure_worktree() { # id
  local id="$1" wt="$WT_DIR/$1"
  [ -d "$wt" ] && { echo "$wt"; return; }
  g fetch -q "$REMOTE" "+refs/heads/task/$id:refs/remotes/$REMOTE/task/$id" 2>/dev/null || true
  if g show-ref -q --verify "refs/heads/task/$id"; then g worktree add -q "$wt" "task/$id" >&2
  elif g show-ref -q --verify "refs/remotes/$REMOTE/task/$id"; then g worktree add -q --track -b "task/$id" "$wt" "$REMOTE/task/$id" >&2
  else g worktree add -q --no-track -b "task/$id" "$wt" "$REMOTE/main" >&2; fi
  echo "$wt"
}

# ---------- operaciones (dentro de txn)
op_claim() { # id who
  has "$1" && { echo "$1 ya tomada por $(get "$1" owner) [$(status "$1")]" >&2; return 1; }
  deps_done "$1" || { echo "$1 tiene deps sin terminar" >&2; return 1; }
  put "$1" owner "$2"; setst "$1" claimed "$2"
}
op_pick() { # who -> escribe en PICKED la tarea elegida
  PICKED=""; local id st
  for id in $(parse | awk -F'|' '{print $1}'); do
    st="$(status "$id")"
    if [ "$st" = "changes_requested" ] && [ "$(get "$id" owner)" = "$1" ]; then PICKED="$id"; setst "$id" claimed "$1"; return 0; fi
  done
  while IFS='|' read -r id tipo deps title; do
    [ "$tipo" = "claude" ] || continue; has "$id" && continue; deps_done "$id" || continue
    PICKED="$id"; put "$id" owner "$1"; setst "$id" claimed "$1"; return 0
  done < <(parse)
  return 3
}
op_submit() { [ "$(status "$1")" = "claimed" ] || { echo "$1 no está claimed" >&2; return 1; }; setst "$1" review "$(get "$1" owner)"; }
op_review_pick() { # who ; prioriza tareas de OTRA sesión
  PICKED=""; local id pass owner
  for pass in other same; do
    for id in $(parse | awk -F'|' '{print $1}'); do
      [ "$(status "$id")" = "review" ] || continue
      owner="$(get "$id" owner)"; [ "$owner" = "$1" ] && continue
      if [ "$pass" = other ] && [ "${owner%%:*}" = "${1%%:*}" ]; then continue; fi
      PICKED="$id"; put "$id" reviewer "$1"; setst "$id" reviewing "$1"; return 0
    done
  done
  return 3
}
op_set() { # id expected_status new_status note [notes_text]
  [ "$(status "$1")" = "$2" ] || { echo "$1 está en '$(status "$1")', se esperaba '$2'" >&2; return 1; }
  [ -n "${5:-}" ] && put "$1" review_notes "$5"
  setst "$1" "$3" "$4"
}
op_release() { has "$1" || return 3; rmtask "$1"; }
op_mark_done() { put "$1" owner "${2:-humano}"; setst "$1" done manual; }

# ---------- comandos
cmd_list() {
  begin; rm -f "$IDX"
  printf "%-5s %-7s %-18s %-20s %-20s %-4s %s\n" ID TIPO ESTADO DUEÑO REVISOR DEPS TITULO
  parse | while IFS='|' read -r id tipo deps title; do
    local ready="ok"; deps_done "$id" || ready="--"
    printf "%-5s %-7s %-18s %-20s %-20s %-4s %s\n" "$id" "$tipo" "$(status "$id")" "$(get "$id" owner)" "$(get "$id" reviewer)" "$ready" "$title"
  done
}
cmd_claim() { check_agent "$2"; fetch; exists "$1"; txn op_claim "$1" "$2"; echo "CLAIMED $1 -> worktree: $(ensure_worktree "$1")"; }
cmd_claim_next() {
  check_agent "$1"; PICKED=""
  txn op_pick "$1"
  [ -n "$PICKED" ] || { echo "NONE: no hay tareas disponibles ahora (ver 'list')"; return 0; }
  local wt; wt="$(ensure_worktree "$PICKED")"
  echo "CLAIMED $PICKED -> worktree: $wt  (rama task/$PICKED)"
  local n; begin; n="$(get "$PICKED" review_notes)"; rm -f "$IDX"; [ -n "$n" ] && printf "NOTAS DE REVISIÓN PREVIAS:\n%s\n" "$n"
  return 0
}
cmd_submit() {
  local id="$1" wt="$WT_DIR/$1"
  [ -d "$wt" ] || die "no existe $wt"
  [ -z "$(git -C "$wt" status --porcelain)" ] || die "hay cambios sin commit en $wt"
  fetch; [ "$(git -C "$wt" rev-list --count "$REMOTE/main..HEAD")" -gt 0 ] || die "task/$id no tiene commits nuevos sobre main"
  git -C "$wt" push -q -u "$REMOTE" "task/$id" || die "no pude empujar task/$id"
  txn op_submit "$id"; echo "SUBMITTED $id para revisión"
}
cmd_review_next() {
  check_agent "$1"; PICKED=""
  txn op_review_pick "$1"
  [ -n "$PICKED" ] || { echo "NONE: nada pendiente de revisión"; return 0; }
  local wt; wt="$(ensure_worktree "$PICKED")"
  git -C "$wt" pull -q --ff-only "$REMOTE" "task/$PICKED" 2>/dev/null || true
  echo "REVIEW $PICKED -> worktree: $wt   diff: git -C $wt diff $REMOTE/main...HEAD"
}
cmd_approve() {
  local id="$1" i=0 tmp title
  begin; [ "$(status "$id")" = "reviewing" ] || die "$id no está en revisión"; rm -f "$IDX"
  title="$(taskfield "$id" 4)"
  while :; do
    fetch; g fetch -q "$REMOTE" "+refs/heads/task/$id:refs/remotes/$REMOTE/task/$id"
    tmp="$WT_DIR/_merge.$$"; g worktree add -q --detach "$tmp" "$REMOTE/main"
    if ! git -C "$tmp" merge -q --no-ff -m "merge task/$id: $title" "$REMOTE/task/$id"; then
      git -C "$tmp" merge --abort || true; g worktree remove --force "$tmp"
      txn op_set "$id" reviewing changes_requested "merge-conflict" "Conflicto con main: en el worktree haz 'git fetch && git merge origin/main', resuelve, corre tests y vuelve a submit."
      die "conflicto: $id devuelta a su dueño"
    fi
    if git -C "$tmp" push -q "$REMOTE" HEAD:main 2>/dev/null; then g worktree remove --force "$tmp"; break; fi
    g worktree remove --force "$tmp"; i=$((i+1)); [ $i -ge 5 ] && die "main se movió demasiadas veces"; sleep 2
  done
  txn op_set "$id" reviewing done "$(cat /dev/null)"
  g worktree remove --force "$WT_DIR/$id" 2>/dev/null || true
  # Actualiza main local si está limpio (best-effort)
  [ -z "$(g status --porcelain --untracked-files=no)" ] && g merge -q --ff-only "$REMOTE/main" 2>/dev/null || true
  echo "APPROVED+MERGED $id en origin/main"
}
cmd_reject() { local id="$1"; shift; txn op_set "$id" reviewing changes_requested "rechazo" "$*"; echo "REJECTED $id (notas guardadas)"; }
cmd_notes() { begin; rm -f "$IDX"; echo "--- notas"; get "$1" review_notes; echo "--- log"; get "$1" log; }
cmd_init_state() {
  if g ls-remote --exit-code -q "$REMOTE" "refs/heads/$SB" >/dev/null 2>&1; then echo "$SB ya existe"; return; fi
  local blob tree c IDX2; IDX2="$(mktemp "${TMPDIR:-/tmp}/tasksidx.XXXXXX")"; rm -f "$IDX2"
  blob="$(printf 'Estado del tablero de tareas. No editar a mano: usa scripts/tasks.sh\n' | g hash-object -w --stdin)"
  GIT_INDEX_FILE="$IDX2" g update-index --add --cacheinfo "100644,$blob,README"
  tree="$(GIT_INDEX_FILE="$IDX2" g write-tree)"; rm -f "$IDX2"
  c="$(g commit-tree "$tree" -m "init tasks-state")"
  g push -q "$REMOTE" "$c:refs/heads/$SB"; echo "creada rama $SB"
}

case "${1:-help}" in
  list) cmd_list ;;
  claim) cmd_claim "${2:?id}" "${3:-}" ;;
  claim-next) cmd_claim_next "${2:-}" ;;
  submit) cmd_submit "${2:?id}" ;;
  review-next) cmd_review_next "${2:-}" ;;
  approve) cmd_approve "${2:?id}" ;;
  reject) cmd_reject "${2:?id}" "${@:3}" ;;
  notes) cmd_notes "${2:?id}" ;;
  release) txn op_release "${2:?id}"; echo "RELEASED $2 (la rama task/$2 se conserva)" ;;
  mark-done) txn op_mark_done "${2:?id}" "${3:-humano}"; echo "DONE $2" ;;
  path) echo "$WT_DIR/${2:?id}" ;;
  init-state) cmd_init_state ;;
  *) cat <<EOF
uso: scripts/tasks.sh <comando>     (agente = <sesion>:<nombre>; sesiones: $SESSIONS)
  list                        tablero con estado de todas las tareas
  claim-next <agente>         toma tu tarea devuelta o la primera abierta con deps listas (crea worktree)
  claim <T-XX> <agente>       toma una tarea concreta
  submit <T-XX>               empuja task/T-XX y la pasa a revisión
  review-next <revisor>       toma la siguiente tarea en revisión (prioriza otra sesión)
  approve <T-XX>              mergea task/T-XX en origin/main y la marca done
  reject <T-XX> "notas"       la devuelve al dueño con notas
  notes <T-XX>                notas de revisión + log
  release <T-XX>              libera un claim (abandono / huérfano)
  mark-done <T-XX> [quien]    marca hecha una tarea humana
  path <T-XX>                 ruta del worktree local
  init-state                  crea la rama remota $SB (una sola vez)
EOF
  ;;
esac
