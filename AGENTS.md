# AGENTS.md — Protocolo de trabajo multi-sesión

Este repo lo construyen **4 sesiones de IA en paralelo**, en 2 máquinas y 3 herramientas:

| Sesión | Persona | Herramienta |
| --- | --- | --- |
| `claude-dylan` | Dylan | Claude Code |
| `claude-elias` | Elias | Claude Code |
| `gpt-dylan` | Dylan | GPT / Codex |
| `cursor-elias` | Elias | Cursor |

Proyecto: KAVAK AUTOGUARD AI (ver `KAVAK_AUTOGUARD_AI_Plan_de_trabajo.md`). Backlog: `TASKS.md`.
Todos los datos son **SIMULADOS**.

## Regla de oro

**Nunca edites en el checkout principal (`main`). Nunca hagas push directo a `main`.** Todo trabajo ocurre
en el worktree de tu tarea (`.worktrees/T-XX`, rama `task/T-XX`), y solo `scripts/tasks.sh approve`
mergea a `main`. La coordinación pasa por `scripts/tasks.sh`, que guarda el estado en la rama remota
`tasks-state` con commits atómicos (si dos sesiones reclaman la misma tarea, solo una gana).

## Identidad

Cada agente se llama `<sesion>:<nombre>`, p.ej. `claude-dylan:w1` (worker 1), `cursor-elias:r1`
(revisor 1). Usa SIEMPRE el prefijo de tu sesión. Si tu herramienta lanza subagentes, cada uno lleva un
nombre distinto dentro de la sesión.

## Setup (una vez por máquina)

```bash
git pull origin main
uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -e '.[dev]'
.venv/bin/python -m pytest          # debe pasar
scripts/tasks.sh list
```
Los worktrees usan el `.venv` del checkout principal: `"$(git rev-parse --path-format=absolute --git-common-dir)/../.venv/bin/python"`
(o simplemente la ruta absoluta `<repo>/.venv/bin/python`).

## Ciclo del WORKER

1. `scripts/tasks.sh claim-next <sesion>:<nombre>` → te da `T-XX` y la ruta del worktree. Si dice
   `NONE`, no hay trabajo libre: haz revisión (abajo) o espera.
2. Lee la tarea en `TASKS.md` (qué, rutas, aceptación) y los stubs/contratos que toca.
   Si la tarea fue devuelta, lee las notas que imprime `claim-next` (o `scripts/tasks.sh notes T-XX`).
3. Trabaja **solo dentro del worktree** y **solo en las rutas de tu tarea**. Si necesitas cambiar algo
   fuera de tus rutas (un contrato, otra tarea), no lo hagas: anótalo en el mensaje del commit como
   `NECESITA:` para que el revisor/coordinador lo decida.
4. Commits pequeños y descriptivos en `task/T-XX`. Antes de entregar:
   `git fetch origin && git merge origin/main`, corre `pytest` completo y que pase.
5. `scripts/tasks.sh submit T-XX` (empuja la rama y la pasa a revisión).
6. Vuelve al paso 1.

## Ciclo del REVISOR

1. `scripts/tasks.sh review-next <sesion>:<nombre>` (prioriza tareas de OTRA sesión; nunca revisas lo tuyo).
2. En el worktree que te da: `git fetch origin && git merge origin/main` (si hay conflicto → reject),
   lee el diff `git diff origin/main...HEAD`, corre `pytest`, verifica la sección **aceptación** de la tarea
   y las reglas comunes de `TASKS.md`. Busca bugs reales, no estilo.
3. Si hiciste el merge de main en el paso 2, commitea y `git push` a `task/T-XX`.
4. Decide:
   - `scripts/tasks.sh approve T-XX` → mergea a `origin/main` y la marca `done`.
   - `scripts/tasks.sh reject T-XX "qué falla, archivo:línea, cómo reproducir"` → vuelve a su dueño.
   El revisor no reescribe la tarea; arreglos triviales (≤5 líneas) sí, commiteados en la rama.

## Estados

`open → claimed → review → reviewing → done` y `reviewing → changes_requested → claimed`.
Un claim abandonado se libera con `scripts/tasks.sh release T-XX` (avisa a su dueño si puedes).

## Reglas técnicas

- Python 3.11+, `pydantic` v2, sin dependencias nuevas sin justificarlas.
- Contratos compartidos (`autoguard/contracts.py`, `config_schema.py`, `segments.py`,
  `evaluator/objective.py`) **no se cambian** salvo tarea dedicada.
- **Seguridad del RSI:** nada en `autoguard/rsi/` escribe en `autoguard/evaluator/`; α, β, δ, ε son fijos.
- Todo funciona **sin llaves** (LLM en modo mock vía `autoguard/llm.py`, fallback determinístico) y es
  reproducible con semilla fija. Tests nunca llaman a la red.
- Llaves solo en `.env` (gitignored). Nunca en código ni logs.
- Una tarea con `asignada: <sesion>` solo la puede tomar esa sesión (`claim-next` la salta para las demás).
- Las tareas `tipo: humano` no se reclaman: las hace una persona y se marcan con `mark-done`.
- No toques `TASKS.md` salvo para agregar tareas nuevas al final, y hazlo en una rama de tarea.
