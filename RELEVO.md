# RELEVO — trabajo por turnos

La metodología en paralelo (`scripts/tasks.sh`, claims, revisores) está **EN PAUSA** desde el
2026-11-09 21:45 UTC. Ahora se trabaja **por turnos**: una sesión a la vez toma la primera tarea
pendiente de la cola, la termina o la deja documentada aquí, y le pasa el turno a la siguiente.

Este archivo es la **única fuente de verdad** del trabajo pendiente. Quien lo lea debe poder continuar
sin otro contexto. Contexto general del proyecto: `KAVAK_AUTOGUARD_AI_Plan_de_trabajo.md`, `TASKS.md`
(definición detallada de cada tarea) y `AGENTS.md` (reglas técnicas, que siguen vigentes).

---

## Turno

| Campo | Valor |
| --- | --- |
| **Turno actual** | CIERRE (todas las sesiones cierran su trabajo en curso; ver "Fase 0") |
| **Orden de turnos** | claude-elias → gpt-dylan → claude-dylan → cursor-elias → (repite) |
| **Última actualización** | 2026-11-09 22:05 UTC · cursor-elias (cierre Fase 0 + rebase) |

## Reglas del turno

1. Al empezar: `git checkout main && git pull origin main` y lee este archivo completo.
2. Si el "Turno actual" no es tu sesión, **no trabajes**: espera. (Excepción: Fase 0.)
3. Toma la **primera** tarea de la cola con estado `pendiente` o `en pausa`. Escribe en ella
   `estado: en curso · <tu-sesion> · <hora UTC>` y haz commit + push a main de inmediato
   (así nadie más la toma).
4. Trabaja en la rama `task/T-XX` (si ya existe en origin, continúa desde ella:
   `git fetch origin && git checkout -B task/T-XX origin/task/T-XX`). Tests con
   `.venv/bin/python -m pytest` (scripts con `-m`: `PYTHONPATH=.`). Todo debe seguir corriendo sin llaves.
5. **Tu turno dura hasta que se acabe el límite de uso de tu sesión.** No pares al terminar una tarea:
   sigue con la siguiente de la cola. Como el límite puede cortarte sin aviso, trabaja con **checkpoints**:
   - Al **terminar una tarea**: `git merge origin/main` en la rama, pytest en verde, revisa tu propio diff
     contra la "aceptación" de `TASKS.md`, merge a main (`git checkout main && git merge --no-ff task/T-XX &&
     git push origin main`) y márcala `hecha` con un resumen de 2–5 líneas (qué se hizo, números,
     decisiones que afectan a otras tareas). Luego toma la siguiente.
   - **Cada ~20 minutos de trabajo** (y antes de cualquier operación larga): commit y
     `git push origin task/T-XX` de TODO lo que tengas aunque esté a medias, y actualiza en main la sección
     **Contexto para continuar** de la tarea: qué está hecho, qué falta (pasos concretos), archivos tocados,
     cómo correr/verificar, hallazgos, intentos fallidos y por qué. Así, si el límite te corta, la
     siguiente sesión continúa sin perder nada.
   - Si ves un aviso de que tu límite está por acabarse: haz el checkpoint de inmediato, deja la tarea en
     `en pausa`, escribe tu línea en la Bitácora y pasa el turno (regla 6).
6. **Paso del turno.** Si alcanzas a cerrar: línea en la Bitácora, "Turno actual" = siguiente sesión del
   orden, commit + push a main (`git pull --rebase origin main` si el push es rechazado).
   Si una sesión se quedó sin límite antes de pasar el turno, la persona le dice a la siguiente sesión
   "es tu turno": esa sesión pone "Turno actual" = ella misma, anota en la Bitácora que la anterior se
   quedó sin límite, revisa la rama y el "Contexto para continuar" de la tarea que quedó `en curso`, y la
   retoma desde ahí.
7. No toques tareas que no están en la cola. Si encuentras un problema fuera de tu tarea, agrégalo como
   tarea nueva al final de la cola con su contexto.

---

## Fase 0 · Cierre (todas las sesiones, ahora)

Cada sesión con trabajo en curso lo cierra según la regla 5 (terminar o documentar) y lo registra en su
tarea abajo y en la Bitácora. **No tomes tareas nuevas.** Detén tus agentes en segundo plano después de
que hayan empujado su trabajo. Cuando las 4 sesiones hayan registrado su cierre en la Bitácora, el turno
pasa a **claude-elias**.

| Sesión | Trabajo en curso al pausar | Cierre registrado |
| --- | --- | --- |
| claude-elias | T-23 (claude-elias:w2), T-25 (claude-elias:w1) | ☐ |
| cursor-elias | ninguno (T-21, T-26, T-28 hechas) | ☑ |
| gpt-dylan | ninguno (T-10, T-13, T-15, T-24, T-29 hechas) | ☑ |
| claude-dylan | ninguno (coordinador; revisores detenidos) | ☑ |

---

## Cola de tareas (en orden)

### 1. T-23 · Cumplir el Gate 2 (PRIORIDAD MÁXIMA)
- **estado:** en curso · claude-elias:w2 (desde 20:59 UTC; aún sin rama en origin al pausar)
- **rama:** `task/T-23`
- **definición:** `TASKS.md` → T-23 (y notas de integración en T-13).
- **línea base (seed 42, modo mock):** regret estático 51.31M · `parametros` 44.80M · `rsi` 49.11M
  (RSI solo −4.3%; meta ≥ −40% y converger en menos pólizas que `parametros`).
- **causas conocidas:** (1) el mejorador corrige la media de `error_rel`, pero con pérdida asimétrica
  (α=1.5, β=1.0) el multiplicador óptimo es el que minimiza `objective.loss` en train (≈ cuantil 0.6 del
  costo), no la media; (2) parches de la misma generación evaluados contra un campeón ya modificado ⇒ doble
  corrección; (3) métrica de convergencia rota (el estático sale "convergido" a las 600 pólizas).
- **prohibido:** tocar `autoguard/sim/`, `autoguard/evaluator/`, `objective.py`, contratos. En `rsi/` solo
  se importa del evaluador `objective.loss`, `split_holdout`, `evaluate` (hay test AST). Mantener la CLI
  `python -m autoguard.rsi.loop --seed --batches --batch-size --k` y el formato `patches.jsonl` (los usa la API
  y el tablero).
- **verificación:** `LLM_PROVIDER=mock PYTHONPATH=. .venv/bin/python -m autoguard.rsi.loop --seed S` para
  S = 42, 1, 7, 123; reportar tabla de regret por semilla. Si no se logra el 40% honestamente,
  documentar números y causas (no maquillar el simulador).
- **Contexto para continuar:** _(lo llena claude-elias en el cierre)_

### 2. T-25 · Prueba de punta a punta vía API
- **estado:** en curso · claude-elias:w1 (al pausar)
- **rama:** `task/T-25`
- **definición:** `TASKS.md` → T-25. Ruta: `tests/test_e2e.py`. No depende de T-23.
- **Contexto para continuar:** _(lo llena claude-elias en el cierre)_

### 3. T-20 · README, guion de demo y semilla de demo
- **estado:** pendiente (requiere T-23 hecha: usa sus números reales)
- **rama:** `task/T-20`
- **definición:** `TASKS.md` → T-20. Rutas: `README.md`, `docs/demo.md`, `scripts/demo.sh`.
- **notas:** el tablero RSI está en `dashboard/app.py` (con modo demo en vivo, T-29) y el dashboard de
  progreso en `tools/progreso/`. n8n, Linear y Miro quedaron fuera del plan. Variables en `.env.example`
  (se carga solo, T-22). Mencionar limitaciones honestas: datos simulados, sandbox sin Docker, LLM sin medir
  con llave real (`docs/eval_llm.md`).
- **Contexto para continuar:** —

### 4. T-27 · Guion y narración del video de respaldo
- **estado:** pendiente (requiere T-20)
- **rama:** `task/T-27`
- **definición:** `TASKS.md` → T-27. Ruta: `docs/video_respaldo.md`. Texto listo para ElevenLabs.
- **Contexto para continuar:** —

### 5. Tareas humanas (las hace una persona; la sesión de turno solo puede preparar instrucciones)
- **T-92** Crear proyecto Supabase y aplicar `db/migrations/001_init.sql`; poner `DATABASE_URL` en `.env`.
- **T-93** Pegar `docs/lovable_prompt.md` en Lovable, conectar GitHub primero.
- **T-95** Desplegar backend (Railway/Render) y tablero (Streamlit Cloud).
- **T-96** Grabar video de respaldo (requiere T-27) y ensayar el pitch 3 veces.
- **T-97** Cancelar Lovable Pro antes de la renovación.

### Decisión abierta
El equipo está evaluando **cambiar el plan de trabajo** (posible cambio de foco según el resultado de
T-23). Si este archivo recibe una sección "Plan nuevo", esa sección manda sobre la cola de arriba.

---

## Ya hecho (no volver a hacer)

T-00 scaffold y contratos · T-01 cliente LLM con mock · T-02 BD (8 tablas) · T-03 simulador con riesgo
oculto · T-04 cotizador explicable · T-05 agente documental · T-06 recolector · T-07 analista · T-08
mejorador · T-09 evaluador congelado · T-10 linaje Git · T-11 meta-mejorador Thompson · T-12 agente visual ·
T-13 ciclo RSI + experimento de 3 variantes (Gate 2 NO cumplido) · T-14 API FastAPI · T-15 tablero
Streamlit · T-17 valuación Tavily/Firecrawl · T-18 sandbox (sin Docker) · T-19 prompt de Lovable · T-21
auditoría · T-22 carga de `.env` · T-24 dashboard de progreso · T-26 dictamen de siniestros · T-28 evaluación
con LLM real · T-29 modo demo del tablero. Suite: 232 tests en verde al pausar.

---

## Bitácora (una línea por turno, la más reciente al final)

- 2026-11-09 21:45 UTC · claude-dylan · Pausa de la metodología paralela; creado RELEVO.md; Fase 0 abierta.
- 2026-11-09 21:54 UTC · gpt-dylan · Fase 0 cerrada: T-10, T-13, T-15, T-24 y T-29 integradas; T-21 y T-28 revisadas/aprobadas. Sin cambios ni claims pendientes; workers w2/w3 y revisor r1 detenidos. Validación final de T-29: 232 tests generales + 3 dashboard en verde. Dashboards locales siguen activos: progreso :8502 y RSI :8501 (corrida mock en /tmp/autoguard-dashboard-runs). Esperando cierre de las otras sesiones; turno permanece CIERRE.
- 2026-11-09 UTC · claude-dylan · Orden de turnos cambiado: cursor-elias pasa al último lugar (claude-elias → gpt-dylan → claude-dylan → cursor-elias).
- 2026-11-09 UTC · claude-dylan · Reglas: cada turno dura hasta el límite de uso de la sesión, con checkpoints (push + contexto) al terminar cada tarea y cada ~20 min.
- 2026-11-09 22:05 UTC · cursor-elias · Fase 0 cierre: sin trabajo en curso; T-21/T-26/T-28 ya en main; agentes detenidos; casilla ☑. Conflicto de rebase resuelto respetando orden nuevo del coordinador. Esperando cierre de claude-elias; turno permanece CIERRE.
