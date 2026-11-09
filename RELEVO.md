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
| **Turno actual** | claude-elias (desde 23:12 UTC, por indicación de la persona) |
| **Orden de turnos** | claude-elias → gpt-dylan → claude-dylan → cursor-elias → (repite) |
| **Última actualización** | 2026-11-09 22:42 UTC · claude-elias (T-23 y T-25 hechas; T-20 en pausa; turno → gpt-dylan) |

## Reglas del turno

1. Al empezar: `git checkout main && git pull origin main` y lee este archivo completo.
2. Si el "Turno actual" no es tu sesión, **no trabajes**: espera. (Excepción: Fase 0.)
3. Si en la cola hay una tarea **asignada a tu sesión** (`asignada: <sesion>`) en estado `pendiente` o
   `en pausa`, tómala primero. Si no, toma la **primera** tarea de la cola con estado `pendiente` o `en pausa`
   que no esté asignada a otra sesión. Escribe en ella
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
| claude-elias | T-23 (claude-elias:w2), T-25 (claude-elias:w1) | ☑ |
| cursor-elias | ninguno (T-21, T-26, T-28 hechas) | ☑ |
| gpt-dylan | ninguno (T-10, T-13, T-15, T-24, T-29 hechas) | ☑ |
| claude-dylan | ninguno (coordinador; revisores detenidos) | ☑ |

---

## Cola de tareas (en orden)

### 1. T-23 · Cumplir el Gate 2 (PRIORIDAD MÁXIMA)
- **estado:** **hecha** · claude-elias · 22:42 UTC · merge en main `6cbae83` (Gate 2 NO cumplido; documentado)
- **resumen:** RSI de −4.3% a −25.9…−29.2% de regret vs estático (el doble que `parametros`); el 40% no se
  alcanza y se documenta por qué: incluso un aprendiz ideal que ya conoce la estructura verdadera logra
  39.3–40.6% y el oráculo 43.7–44.8% ⇒ el RSI captura 66–74% de la mejora del aprendiz ideal. **Propuesta para
  el equipo: Gate relativo a esas cotas.** Revisada por agente independiente (aprobada con cambios menores,
  aplicados). Tabla (MXN, modo mock, mejora vs estático):

  | seed | estático | parametros | rsi | % del oráculo | % del aprendiz ideal |
  | --- | --- | --- | --- | --- | --- |
  | 42 | 51.31M | 44.01M (−14.2%) | **36.73M (−28.4%)** | 64% | 70% |
  | 1 | 51.18M | 42.61M (−16.7%) | **37.93M (−25.9%)** | 59% | 66% |
  | 7 | 50.98M | 43.50M (−14.7%) | **37.00M (−27.4%)** | 61% | 68% |
  | 123 | 51.05M | 42.05M (−17.6%) | **36.16M (−29.2%)** | 66% | 74% |

  Convergencia estricta (≤1.10× oráculo hasta el final): ninguna variante. A la meseta (secundaria): rsi/parametros
  8600/8200 (42), 4600/4600 (1), 3000/1000 (7), 10800/3000 (123) — parametros se estanca antes pero en +35–58% sobre
  el oráculo vs rsi +12–25%. Seed 42 tarda ~106 s. Detalle completo en el mensaje del merge `6cbae83`; scripts de
  las cotas en la rama `exp/T-23-cotas` (`tools/t23_cotas/`, sin mergear). Decisiones que afectan a otras tareas:
  `summary.json` agrega `referencia_oraculo`, `exceso_final_vs_oraculo`, `convergencia_meseta_polizas`,
  `tasa_aceptacion_rsi` (con `evaluados`); `curve.csv` agrega `loss_oraculo`/`ratio_oraculo`; `convergencia_polizas`
  puede ser `null`. Hallazgo para otra tarea: `patch_id` se repite entre variantes en `patches.jsonl` y
  `api/main.py:_buscar_parche` toma el primero (puede ser el de `parametros`).
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
- **Contexto (histórico, del cierre de Fase 0; ya integrado):** (claude-elias, 22:10 UTC)
  - **Hecho en `task/T-23` (commit 4c7e67c, tests de rsi/evaluador/meta en verde):**
    - `analista.py`: `optimal_multiplier` = argmin EXACTO de `objective.loss` (cuantil ponderado nivel
      α/(α+β)=0.6 de costo/prima, pesos = prima; verificado contra malla de 30k puntos). `best_multiplier`
      = lo anterior encogido hacia 1 por n/(n+30), acotado a [0.5, 2]. α y β se LEEN evaluando `loss(0,1)` y
      `loss(1,0)` (no se importan constantes; pasa el test AST). Impacto = pérdida reducible; p-value =
      prueba de signo contra P(costo>prima)=0.4. Bins nuevos de `danos_costo` (antes era indescubrible).
    - `mejorador.py`: `propose(..., train=df, evitar=set)` = modo con datos (`_propose_data`); sin `train`
      el comportamiento original queda idéntico (tests heredados intactos). `ajuste_factor` = Gauss-Southwell
      (reajusta COMPLETO el factor que más baja la pérdida train); `nueva_variable` = factor completo de la
      variable no usada que más baja la pérdida (todas las marcas / bins de daños); `cambio_regla` =
      hipótesis del analista, 2 variables primero; pre-chequeo `_robustify` (baja pérdida train y ningún
      segmento de train n≥30 empeora >2.5%; si no, amortigua raíz ×2); una hipótesis/objetivo por generación;
      `patch_target` para el tabú. Fix Windows en `tests/test_mejorador.py` (encoding utf-8).
    - `loop.py`: evalúa todos los parches contra el MISMO campeón y compone los aceptados por ganancia
      re-evaluando cada uno sobre la composición (si no mejora ⇒ `rechazado` con razón); tabú de 2 gens
      para objetivos rechazados; convergencia = primer N desde el que la media móvil (3 lotes) queda ≤ 1.10×
      la del oráculo calibrado hasta el final (estático ⇒ null); summary agrega `referencia_oraculo`,
      `exceso_final_vs_oraculo`, `tasa_aceptacion_rsi`; `curve.csv` agrega `loss_oraculo` y `ratio_oraculo`.
      CLI y formato de `patches.jsonl` sin cambios.
  - **Números seed 42** (estático 51.31M): línea base rsi 49.11M (−4.3%) → v1 40.06M (−21.9%) → actual
    **39.81M (−22.4%)**, parametros 43.90M, exceso final vs oráculo rsi +21% (parametros +46%), aceptación
    1ª/última gen 0.33/0.33. Ni rsi ni parametros "convergen" con la definición estricta. **Tiempo: 226 s con
    CPU compartida (~145 s sin carga) ⇒ riesgo con el límite de 3 min.**
  - **Hallazgo clave (cotas honestas):** oráculo calibrado (conoce el riesgo desde la póliza 1) = mejora
    máxima 44.3% (42) · 43.7% (1) · 44.8% (7) · 44.1% (123). Aprendiz online IDEAL que YA conoce la estructura
    verdadera y reajusta todo óptimamente cada K=3 lotes, sin holdout/δ/ε: **40.6% (42) · 39.3% (1) · 40.3% (7)
    · 39.7% (123)**. La censura por ventas no es el límite (ajustando solo con vendidas se llega a +0.6% del
    oráculo). ⇒ **el 40% fijo es inalcanzable honestamente** para un RSI que debe descubrir la estructura y
    pasar el evaluador congelado; propuesta: Gate relativo (p.ej. RSI captura ≥X% de la mejora del aprendiz
    ideal y converge antes que `parametros`). Scripts para reproducir: rama `exp/T-23-cotas`, `tools/t23_cotas/`.
  - **Diagnóstico de rechazos (v1):** el ε=5% por segmento sobre un holdout chico (~70 filas al inicio)
    bloquea los reajustes amplios (marca, zona rechazados una y otra vez por segmentos ruidosos n≈30–60);
    antiguedad nunca se reajustó; la interacción ≥30 años & 1 siniestro (×0.65) nunca entró; el bandido
    gasta slots en `cambio_prompt`.
  - **Experimentos a medias, NO integrados, sin medir** (detenidos en el cierre): `exp/T-23-x1` (presupuesto
    de slots del bandido / aprendizaje temprano: loop, mejorador, meta + tests), `exp/T-23-x3`
    (rendimiento; NO verificado que dé resultados idénticos), `exp/T-23-x4` (tests unitarios nuevos
    `tests/test_rsi_asimetrico.py`, sin correr completo). x2 (aceptación) no dejó cambios.
  - **Falta:** (1) bajar el tiempo a < 3 min holgado (perfilar `_robustify`/`_check_segments`/analista);
    (2) revisar/medir x1 e integrar si mejora; (3) tests para la lógica nueva (partir de x4); (4) correr
    seeds 42/1/7/123 y tabla; (5) merge origin/main, pytest, commit con números + cotas y propuesta de Gate.
  - **Correr:** `PYTHONPATH=. python -m autoguard.rsi.loop --seed 42 --output-dir /tmp/x`; tests:
    `python -m pytest tests/test_mejorador.py tests/test_analista.py tests/test_loop.py tests/test_evaluator.py tests/test_meta.py`.

### 2. T-25 · Prueba de punta a punta vía API
- **estado:** **hecha** · claude-elias · 22:32 UTC · merge en main `e0a1092`
- **resumen:** `tests/test_e2e.py` recorre todo el flujo vía API con TestClient, SQLite y directorios temporales,
  modo mock y semilla 42: expediente EXP-001 → perfil + cotización (coincide con `/quote` y el linaje) →
  `POST /outcomes` idempotente → `POST /rsi/run` en proceso + `/runs/latest` + `/patches` → aprobar un parche
  cambia la prima y la `agent_version` → revertir devuelve la prima original (linaje con 3 versiones). Tarda
  ~37 s (aceptación < 60 s). Pytest completo: sin fallos nuevos (solo los preexistentes de Windows).
- **rama:** `task/T-25`
- **definición:** `TASKS.md` → T-25. Ruta: `tests/test_e2e.py`. No depende de T-23.
- **Contexto para continuar:** (claude-elias, 22:10 UTC)
  - **Hecho:** `tests/test_e2e.py` (206 líneas, un test) con TestClient, BD y directorios temporales y un
    `rsi_runner` en proceso: health (mock) → `POST /expedientes` EXP-001 (perfil Nissan Versa 2019, 3 tipos de
    documento, daños de la foto) → la cotización coincide con `/quote` y con `cotizador.quote` → `POST /outcomes`
    (idempotente, duplicados) → `POST /rsi/run` pequeño + `GET /rsi/run/{id}` + `/runs/latest` → `GET /patches`
    (fuente run) → aprobar un parche que cambia la prima del auto → nueva versión campeona y `/quote` registra la
    nueva `agent_version` y la prima esperada → revertir con `POST /versions/cotizador/revert/{sha}` → la prima
    vuelve a la original. **Pasa en ~47 s en modo mock** (Windows; aceptación < 60 s).
  - **Falta (corto):** `git merge origin/main` en la rama, pytest completo (en Windows fallan de origen
    9 tests de `test_sandbox.py` por `preexec_fn` y el umbral de tiempo de
    `test_api.py::test_expediente_sample_mock_fast_and_persisted`: no son de T-25), revisar el diff contra la
    aceptación y merge a main.

### 3. T-20 · README, guion de demo y semilla de demo
- **estado:** hecha · gpt-dylan
- **resumen:** README y demo completados sin marcadores; seed42 verificada (28.4%, 24 s, 24 parches RSI aceptados). Script fuerza mock, valuación offline y SQLite local. No se versiona respaldo: se prepara desde artefactos reales. Suite 259 passed; un intento previo tuvo el fallo intermitente conocido de sandbox memoria/timeout.
- **rama:** `task/T-20`
- **definición:** `TASKS.md` → T-20. Rutas: `README.md`, `docs/demo.md`, `scripts/demo.sh`.
- **notas:** el tablero RSI está en `dashboard/app.py` (con modo demo en vivo, T-29) y el dashboard de
  progreso en `tools/progreso/`. n8n, Linear y Miro quedaron fuera del plan. Variables en `.env.example`
  (se carga solo, T-22). Mencionar limitaciones honestas: datos simulados, sandbox sin Docker, LLM sin medir
  con llave real (`docs/eval_llm.md`).
- **Contexto para continuar:** (claude-elias, 22:42 UTC)
  - **Hecho (borrador, agente claude-elias:w3):** `README.md` (qué es, diagrama, instalación sin llaves,
    cómo correr tests/experimento/API/tablero/progreso/evals, tabla de resultados, Gate 2 honesto,
    limitaciones), `docs/demo.md` (semilla 42, guion de 40 s segundo a segundo con EXP-002 + FOTO-002 porque da
    `VIN_NO_COINCIDE` alta y 2 daños, plan B, preguntas del jurado) y `scripts/demo.sh` (`--start/--stop/--force/
    --help`, puertos `API_PORT`/`DASH_PORT`; probado en Git Bash: corrida seed 42, `/health`, tablero 200,
    `/expedientes` con EXP-001/2/3).
  - **Falta:** (1) `git fetch && git checkout -B task/T-20 origin/task/T-20 && git merge origin/main`
    (main ya tiene T-23); (2) reemplazar los marcadores — listarlos con
    `grep -no "{{T23_[A-Z0-9_]*}}" README.md docs/demo.md` — usando la tabla de T-23 de arriba (mejora media rsi
    27.7%; convergencia: usar la de meseta y explicar que la estricta no la alcanza nadie; `RESUMEN_GATE2` =
    resumen de T-23); quitar el texto "−27.4 % en seed 42 y −25.6 % en seed 1" (preliminar) y las notas
    "BORRADOR"; (3) regenerar la corrida de seed 42 con el código de main para `TIEMPO_CORRIDA`,
    `PARCHES_ACEPTADOS_42` y `PARCHE_REVERSION_42` (`bash scripts/demo.sh --force`); (4) `data/demo_run/` no
    existe: decidir si se versiona la corrida de respaldo (marcador `DEMO_RUN_RESPALDO`); (5) `docs/demo.md`
    cita `docs/video_respaldo.md` (T-27, aún no existe); (6) el tablero no deja revertir con el modo demo
    activo: el guion apaga "Activar reproducción" en los segundos 34–40, ensayarlo; (7) pytest, revisar contra
    la aceptación y merge a main.

### 4. T-27 · Guion y narración del video de respaldo
- **estado:** hecha · gpt-dylan
- **resumen:** Guion de 3 minutos, bloque demo 00:55–01:35, narración para ElevenLabs y lista de tomas. Cifras reales seed42 (28.4%), cuatro semillas y limitaciones explícitas; audio/video pendientes humanos. Suite 259 passed.
- **rama:** `task/T-27`
- **definición:** `TASKS.md` → T-27. Ruta: `docs/video_respaldo.md`. Texto listo para ElevenLabs.
- **Contexto para continuar:** —

### 5. T-30 · Pulir el frontend con el RSI como protagonista (sin look "vibecodeado")
- **asignada:** gpt-dylan (es lo primero que hace en su turno)
- **estado:** hecha · gpt-dylan · 2026-11-09
- **resumen:** Titular dinámico, convergencia nullable, colores y nombres de negocio, parches aceptados en curvas, ciclo explicado, filtros, métricas holdout y confirmación de reversión. Tasa de aceptación y posteriors; estilo alineado con Lovable. Capturas antes/después y por sección en docs. 259 tests generales + 3 dashboard pasan; seed 42 actual: 28.4% de mejora, 21.4 s en esta máquina.
- **rama:** `task/T-30`
- **rutas:** `dashboard/` (tablero RSI en Streamlit, incluido el modo demo de T-29), `.streamlit/config.toml`,
  `docs/lovable_prompt.md` (alinear el estilo del frontend de Lovable con el del tablero), capturas en `docs/`.
  No tocar `autoguard/` salvo lectura; si el tablero necesita un dato que el loop no escribe, agrégalo como
  tarea nueva al final de la cola.
- **objetivo:** que los jueces entiendan en 40 s que el sistema **se mejora solo y aprende a mejorarse**, y
  que el producto se vea diseñado por un equipo, no generado.
- **el RSI al frente (en este orden en la página principal):**
  1. Titular con la cifra clave de la corrida (regret RSI vs estático, % de reducción, pólizas a
     convergencia) leída de `var/runs/<run_id>/summary.json`, nunca escrita a mano.
  2. Curvas de pérdida vs pólizas de las 3 variantes con el **área de regret sombreada** y anotaciones en
     los puntos donde se aceptó un parche.
  3. El ciclo RSI como diagrama con el estado de la generación actual: recolector → analista → mejorador →
     evaluador congelado → linaje → meta-mejorador.
  4. Bitácora de parches como historia: hipótesis → cambio (diff legible) → métricas en holdout antes/después
     → veredicto y motivo; filtros por veredicto y tipo; botón de reversión con confirmación.
  5. "Aprende a mejorar": evolución de los posteriors del bandido por tipo de parche y tasa de aceptación
     por generación, con las lecciones del meta-mejorador.
  6. Garantías: evaluador inmutable, holdout que el mejorador nunca ve, lista blanca de variables, todo
     revertible. Linaje de versiones navegable.
- **criterios anti-"vibecodeado" (el revisor los verifica uno por uno):**
  - Sistema visual propio y sobrio: 1 familia tipográfica, escala de tamaños consistente, paleta corta
    (neutros + 1 color de acento + colores semánticos para las 3 variantes, iguales en todas las gráficas),
    tema en `.streamlit/config.toml`. Sin gradientes decorativos, sin emojis en títulos, sin "glassmorphism".
  - Textos escritos por una persona: títulos que afirman algo ("El RSI reduce el regret 47%") en vez de
    genéricos ("Dashboard", "Métricas"); sin relleno tipo "potenciado por IA"; español consistente.
  - Números formateados (MXN con separador de miles, % con 1 decimal, pólizas enteras) y unidades en
    cada eje y tarjeta; leyendas con nombres de negocio ("Reglas fijas", "Solo parámetros", "RSI completo").
  - Jerarquía clara: una idea por sección, espacio en blanco, nada de 12 tarjetas iguales en fila.
  - Estados vacíos, de carga y de error útiles (p.ej. "Aún no hay corridas: ejecuta `python -m
    autoguard.rsi.loop --seed 42`"). Nada de texto placeholder ni datos inventados.
  - Etiqueta discreta y permanente "Datos simulados".
  - Funciona en pantalla de proyector (1280×720) y se lee a distancia.
- **aceptación:** `streamlit run dashboard/app.py` arranca con una corrida mock y con la corrida pre-grabada
  del modo demo; los tests existentes de `dashboard/` siguen en verde; capturas antes/después en
  `docs/tablero-rsi.png` (y una nueva por sección clave); el resumen en esta tarea lista qué cambió.
  Si T-23 cambia los números, el tablero los refleja sin tocar código.
- **Contexto para continuar:** —

### 6. Tareas humanas (las hace una persona; la sesión de turno solo puede preparar instrucciones)
- **T-92** Crear proyecto Supabase y aplicar `db/migrations/001_init.sql`; poner `DATABASE_URL` en `.env`.
- **T-93** Pegar `docs/lovable_prompt.md` en Lovable, conectar GitHub primero.
- **T-95** Desplegar backend (Railway/Render) y tablero (Streamlit Cloud).
- **T-96** Grabar video de respaldo (requiere T-27) y ensayar el pitch 3 veces.
- **T-97** Cancelar Lovable Pro antes de la renovación.

### 7. T-31 · Migrar el proveedor LLM a OpenAI
- **estado:** **hecha** · claude-dylan · merge en main `f428888`
- **resumen:** `autoguard/llm.py` usa la Responses API de OpenAI (`client.responses.create`): `instructions` +
  `input`, imágenes como `input_image` y PDF como `input_file` (data URL base64), JSON mode (`json_object`) con
  validación local contra el schema, `reasoning.effort` (default `low`) y holgura de 2000 tokens porque el
  razonamiento cuenta contra `max_output_tokens`; `incomplete`/`refusal` ⇒ reintento y luego `fallback()`;
  4xx de `openai` sin reintento. Modelo por defecto **`gpt-6.1-sol`** (OpenAI lo recomienda como balance
  calidad/costo; texto+imagen, structured outputs, effort; USD 2/10 por 1M tokens), cambiable con `LLM_MODEL`
  (`gpt-6-luna` = más barato). Fuente: developers.openai.com/api/docs/models y /quickstart (2026-11-09).
  `scripts/eval_llm.py` usa `llm.build_request` y esas tarifas. `.env.example` pide solo `OPENAI_API_KEY`;
  `pyproject` cambia `anthropic` por `openai` (reinstalar: `uv pip install -e '.[dev]'`). Tests: 261 passed, sin
  red; `ANTHROPIC_API_KEY` se sigue limpiando en tests como legado. **No se probó con llave real**: el primer uso
  real conviene hacerlo con `python scripts/eval_llm.py` y `LLM_CACHE=1`.
- **rama:** `task/T-31`
- **rutas:** `autoguard/llm.py`, `scripts/eval_llm.py`, `.env.example`, `pyproject.toml`, tests LLM/settings/evaluación y documentación afectada.
- **qué:** usar OpenAI en lugar de Anthropic. Conservar `complete_json`, modo mock sin llaves, validación, imágenes/PDF, fallback y caché. Adaptar evaluación real y conteo de tokens, actualizar limpieza de secretos en tests y eliminar requisitos de Anthropic. Elegir y documentar un modelo con las capacidades requeridas al implementar, consultando documentación oficial.
- **aceptación:** sin llave o provider mock no hay llamadas; cliente falso cubre JSON, imágenes/PDF, errores y reintento; suite completa sin red. No leer ni imprimir llaves. `.env.example` debe pedir solo OPENAI_API_KEY como credencial de proveedor obligatoria.
- **Contexto para continuar:** `.env` LOCAL ya preparado con OPENAI_API_KEY (vacía si no existía) y LLM_PROVIDER=mock. Se quitaron la llave Anthropic y el modelo Claude del archivo local; nunca se trasladó una llave Anthropic a OpenAI. El código sigue usando Anthropic hasta implementar esta tarea. Preservar cualquier OPENAI_API_KEY que el usuario introduzca. No activar llamadas reales como parte de tests. Fuente: https://developers.openai.com/api/docs/quickstart .

### 8. T-32 · `patch_id` repetido entre variantes en `patches.jsonl`
- **estado:** **hecha** · claude-dylan · merge en main
- **resumen:** `rsi/loop.py` escribe en `patches.jsonl` el id `<variante>-<patch_id>` (`unique_patch_id`,
  idempotente) y `api/services.run_patches` aplica el mismo prefijo a corridas viejas, así
  `/patches/{id}/approve` ya no puede aprobar el parche de `parametros` cuando se eligió uno de `rsi`. Los
  commits del linaje y la BD conservan su formato. Para la UI/Lovable: los ids ahora traen el prefijo de
  variante (p.ej. `rsi-g4-2-nueva_variable-r2`). Tests nuevos en `test_api.py` y `test_loop.py`; 263 passed.
- **rama:** `task/T-32`
- **qué:** hallazgo de T-23: los `patch_id` se repiten entre variantes (`parametros` y `rsi`) en
  `patches.jsonl`, y `autoguard/api/main.py:_buscar_parche` toma el primero que encuentra (puede aprobar el
  parche de `parametros` cuando el usuario eligió uno de `rsi`). Hacer los ids únicos por variante (p.ej.
  prefijo `rsi-`/`par-` al escribir) o buscar por (variante, patch_id); cuidar que el tablero y la API sigan
  leyendo corridas viejas. Test que lo reproduzca.
- **Contexto para continuar:** —

### 9. T-33 · Frontend completo de AutoGuard AI (local, sin Lovable)
- **estado:** en curso · claude-elias · 23:12 UTC (pedido directo de la persona)
- **rama:** `task/T-33`
- **rutas:** `frontend/` (nueva). No toca backend ni otras rutas.
- **qué:** frontend end to end en React + Vite + TypeScript que corre en local contra la API (`http://localhost:8000`):
  landing con narrativa para México (datos públicos con fuente: INEGI, AMIS, etc.) y la app: nuevo expediente y su
  resultado, dictamen de siniestro, laboratorio RSI (curvas de la última corrida), bitácora de parches con
  aprobar/rechazar y versiones con reversión. Estilo visual: el de la referencia que dio la persona (claro, cálido,
  titular grande con palabra en degradado, maqueta de la app en el hero). Sin deploy a producción. Datos simulados
  etiquetados.
- **aceptación:** `npm install && npm run dev` en `frontend/` levanta el sitio; con la API local corriendo, todas
  las pantallas funcionan contra endpoints reales; `npm run build` sin errores; cifras de México con fuente visible.
- **Contexto para continuar:** —

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
- 2026-11-09 22:10 UTC · claude-elias · Fase 0 cierre: T-23 y T-25 en pausa con ramas en origin (`task/T-23` 4c7e67c, `task/T-25` ab8582e) y "Contexto para continuar" lleno. T-23: rsi −4.3% → −22.4% (seed 42); cotas medidas: oráculo ~44%, aprendiz ideal 39–41% ⇒ 40% fijo inalcanzable honestamente. Experimentos a medias en `exp/T-23-x1/x3/x4` y scripts de cotas en `exp/T-23-cotas`. T-19 revisada y aprobada antes de la pausa. 6 agentes en segundo plano detenidos (w1, r1, x1–x4). Las 4 sesiones cerraron ⇒ Fase 0 completa.
- 2026-11-09 22:08 UTC · claude-elias · Inicio de turno (Fase 0 completa); toma T-23 (en curso).
- 2026-11-09 22:21 UTC · claude-elias · Checkpoint T-23 (a8e9013: rsi −27.4% seed 42). Por instrucción de la persona, agentes en paralelo dentro del turno: w1 cierra T-25, w3 redacta T-20 (sin merge hasta T-23).
- 2026-11-09 22:32 UTC · claude-elias · T-25 hecha (merge `e0a1092`, verificado: solo `tests/test_e2e.py`). T-23 lista en `task/T-23` (3f4e88d, pytest sin fallos nuevos, seed 42 en 106 s), en revisión por agente independiente antes del merge.
- 2026-11-09 UTC · claude-dylan · Agregada T-30 (pulir frontend con el RSI al frente), asignada a gpt-dylan para su turno; regla 3: las tareas asignadas a tu sesión van primero.
- 2026-11-09 22:42 UTC · claude-elias · Fin de turno. T-23 hecha (merge `6cbae83`): rsi −25.9…−29.2% vs estático en seeds 42/1/7/123 (base −4.3%), Gate 2 no cumplido y documentado con cotas (aprendiz ideal 39–41%, oráculo ~44%) + propuesta de Gate relativo; revisada por agente independiente. T-25 hecha (`e0a1092`). T-20 en pausa con borrador completo en `task/T-20` (falta poner números, ver su contexto). Agentes detenidos. Turno → gpt-dylan.

- 2026-11-09 · gpt-dylan · T-30 y T-20 hechas, capturas y resultados reales publicados; continúa con T-27.

- 2026-11-09 · gpt-dylan · T-30, T-20 y T-27 integradas y verificadas (259 tests generales; dashboard 3). Corrida seed42 regenerada: 28.4%, convergencia estricta null. .env local preparado por solicitud humana sin versionar llaves. Cola automática terminada; turno → claude-dylan para coordinación de pendientes humanos.

- 2026-11-09 · gpt-dylan · Por petición del usuario, proveedor elegido OpenAI; .env local preparado sin exponer valores. T-31 pendiente para siguiente turno; el cliente aún no está migrado. Turno de claude-dylan conservado.
- 2026-11-09 22:55 UTC · claude-dylan · Inicio de turno; toma T-31 (en curso). Agregada T-32 (patch_id repetido entre variantes, hallazgo de T-23).
- 2026-11-09 23:20 UTC · claude-dylan · T-31 hecha (merge `f428888`: LLM migrado a OpenAI, `gpt-6.1-sol`, 261 tests). T-32 queda pendiente. Turno → claude-elias por indicación de la persona (su límite ya casi se restablece).
- 2026-11-09 23:25 UTC · claude-dylan · La persona indica que claude-dylan sigue en turno; toma T-32 (en curso). Siguiente turno: claude-elias.
- 2026-11-09 23:40 UTC · claude-dylan · T-32 hecha (patch_id único por variante). La cola automatizada quedó vacía: solo quedan tareas humanas (T-92, T-93, T-95, T-96, T-97). Siguiente turno: claude-elias.
- 2026-11-09 23:12 UTC · claude-elias · Inicio de turno por indicación de la persona; agrega y toma T-33 (frontend completo local, rama `task/T-33`, solo `frontend/`).
