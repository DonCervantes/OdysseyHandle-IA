# Guion de la demo (40 s) — KAVAK AUTOGUARD AI

Corresponde al bloque **5. Demo (40 s)** del pitch de 3 minutos
([`KAVAK_AUTOGUARD_AI_Plan_de_trabajo.md`](../KAVAK_AUTOGUARD_AI_Plan_de_trabajo.md) → *Pitch*). Llega
justo después de "El diferenciador RSI", así que el público ya escuchó *qué* hace el ciclo; aquí lo **ve**.

## Semilla elegida: 42

- Comando: `LLM_PROVIDER=mock python -m autoguard.rsi.loop --seed 42 --output-dir var/runs/demo-seed42`
  (lo hace `bash scripts/demo.sh`). Parámetros por defecto: 60 lotes × 200 autos, una generación cada
  3 lotes ⇒ **12,000 pólizas por variante y 20 generaciones**.
- Por qué 42: es la semilla de referencia de todo el proyecto (T-13, T-23 y los tests), es determinística
  en modo mock (misma corrida ⇒ mismos números y mismos parches) y permite comparar directamente con la línea base sin elegir la semilla por su resultado.
- Tiempo de la corrida en una laptop: 21.4 s medidos en Mac; ~106 s en la máquina del turno anterior (depende del equipo) Se prepara antes del pitch, nunca en vivo.

## Resultados esperados (seed 42)

| Métrica | `estatico` | `parametros` | `rsi` |
| --- | --- | --- | --- |
| Regret acumulado (MXN) | 51,312,336 | 44,014,125 | 36,727,792 |
| Pólizas hasta convergencia | — | No alcanzada | No alcanzada |

- Mejora del RSI frente al estático: **28.4 %**.
- Gate 2 (≥ 40 %): **no cumple**. El tablero lo muestra como "No cumple" y lo decimos sin rodeos si
  preguntan: incluso un oráculo con conocimiento perfecto solo logra ~44 % (43.7–44.8 % según semilla) y
  un aprendiz ideal que ya conoce la estructura verdadera logra 39–41 %; el 40 % fijo está en el límite
  de lo alcanzable en este simulador.
- Parches aceptados del RSI en la corrida: 24; el parche que se usará para la
  reversión: seleccionar el padre del campeón en el historial Git de rsi; el SHA cambia entre ejecuciones.

Comprobación rápida antes de subir al escenario: `bash scripts/demo.sh` imprime el resumen de
`var/runs/demo-seed42/summary.json`; debe coincidir con la tabla de arriba.

## Preparación (10 min antes)

1. `bash scripts/demo.sh --start` → corrida seed 42 lista, API en `:8000`, tablero en `:8501` y frontend en `:5173`.
2. Navegador con **dos pestañas** ya abiertas y con zoom al 125 %:
   - Pestaña A: frontend local `http://localhost:5173` (pantalla de nuevo expediente; si el frontend no
     arrancó, Swagger `http://localhost:8000/docs` en `POST /expedientes`) con los archivos `data/samples/docs/EXP-002-{FAC,TC,POL}.png` y
     `data/samples/fotos/FOTO-002.png` a mano (EXP-002 es el que trae la alerta más clara: `VIN_NO_COINCIDE`, severidad alta, y dos daños).
   - Pestaña B: tablero `http://localhost:8501`, corrida **demo-seed42** seleccionada, *Activar
     reproducción* encendido, velocidad **2×** (20 generaciones en ~20 s) y en generación 0 (↺ Inicio).
3. Cargar una vez el expediente EXP-002 para "calentar" la API (la primera llamada importa módulos).
4. Video de respaldo abierto en otra ventana, pausado en el segundo 0 (ver Plan B).

## Guion segundo a segundo

| Tiempo | En pantalla | Acción | Narración (del pitch) |
| --- | --- | --- | --- |
| 0–8 s | Pestaña A: expediente EXP-002 | Subir factura, tarjeta, póliza y FOTO-002; enviar (~1 s en mock). Aparece la **alerta** `VIN_NO_COINCIDE` (alta), los daños con costo (espejo estrellado, rayón en puerta) y la **prima con sus factores** e intervalo. | *(puente)* "Este es un auto revisado por los agentes: alertas, daños y una prima que se explica sola." |
| 8–12 s | Pestaña B: tablero en G0 | Cambiar de pestaña. Las tres curvas arrancan juntas. Pulsar **▶ Play**. | "Aquí hay tres cotizadores viendo los mismos autos." |
| 12–20 s | Curva *Pérdida media por lote* | La curva de reglas fijas mantiene su nivel con ruido; RSI reduce la pérdida en conjunto, sin descenso monótono. | "El de reglas fijas sigue equivocándose. El nuestro baja su error con cada póliza." |
| 20–28 s | Curva *Regret acumulado* (área sombreada) | Señalar el área: la gris crece más rápido que la verde. Métrica *Reducción de regret RSI* sube hasta 28.4 %. | "Esta área sombreada es el dinero que cuesta aprender, y con RSI es mucho menor." |
| 28–34 s | Avisos "✓ Parche aceptado" + pestaña **La historia de los cambios** | Al terminar la reproducción (se pausa sola), abrir un parche aceptado: hipótesis, métricas antes/después y diff. | "Y cada cambio está aquí, explicado…" |
| 34–40 s | Pestaña **Versiones y garantías** | Apagar *Activar reproducción* (la reversión está deshabilitada durante la demo), variante `rsi`, elegir la versión anterior, marcar la confirmación y pulsar **Revertir configuración de esta variante** → aviso "Nueva versión: …". | "…con un botón para revertirlo." |

Notas de ejecución:

- Si la narración va más lenta, usar velocidad 1× (~40 s para las 20 generaciones) y saltarse el paso
  del expediente; si va más rápida, 4×. Mover el deslizador de generación pausa la reproducción.
- La reversión crea un commit nuevo en el repo Git de la variante; no reescribe las curvas registradas.
  Para dejar la corrida limpia después del ensayo: `bash scripts/demo.sh --force` (regenera la corrida).
- No ejecutar el ciclo RSI en vivo (`POST /rsi/run`): tarda minutos. La demo **reproduce** una corrida
  real ya ejecutada; el tablero no inventa ni suaviza números.

## Plan B

Ordenados de menor a mayor degradación:

1. **Modo demo del tablero con corrida de respaldo.** Si `var/runs/` no tiene corridas (máquina nueva,
   corrida borrada), el tablero cae automáticamente a `data/demo_run/`, o se puede escribir otra carpeta
   en *Corrida de respaldo (plan B)*. Preparar `data/demo_run/` copiando `curve.csv`, `summary.json`,
   `patches.jsonl`, `versions.jsonl` y `meta.jsonl` de `var/runs/demo-seed42/` (una corrida REAL). Sin los
   repos Git la pestaña de reversión queda informativa: narrar la reversión sobre el historial.
   *(Hoy `data/demo_run/` no existe en el repo: se prepara localmente con los artefactos de una corrida ejecutada; no se versionan datos de respaldo.)*
2. **Frontend caído → Swagger o curl.** `http://localhost:8000/docs` → `POST /expedientes` → *Try it
   out*, o desde terminal:

   ```bash
   curl -s -X POST http://localhost:8000/expedientes \
     -F docs=@data/samples/docs/EXP-002-FAC.png \
     -F docs=@data/samples/docs/EXP-002-TC.png \
     -F docs=@data/samples/docs/EXP-002-POL.png \
     -F fotos=@data/samples/fotos/FOTO-002.png \
     -F 'datos={"kilometraje": 45000, "uso": "particular", "zona": "CDMX"}'
   ```

   Se leen en voz alta `alertas` y `cotizacion` (factores de la prima). Bitácora y reversión también por
   API: `GET /patches`, `GET /versions/cotizador`, `POST /versions/cotizador/revert/{sha}`.
3. **Todo falla (laptop, red, proyector con la app) → video de respaldo.** Grabación de 3 min con
   narración (guion en `docs/video_respaldo.md`, T-27; grabación T-96). Se reproduce desde el minuto del
   bloque de demo: marcar al grabar el inicio del bloque de demo (guion de T-27). Llevarlo también en USB y en el teléfono.

## Preguntas probables del jurado

- **¿Los datos son reales?** No: todo es simulado, incluida una función de riesgo oculta que el sistema no
  ve. Es para validar la mecánica antes de tener datos de Kavak.
- **¿Qué impide que el RSI haga trampa?** El evaluador, el holdout y la función objetivo están fuera de su
  alcance (`autoguard/evaluator/`, constantes fijas); un parche solo entra si mejora ≥ 1 % en el holdout
  sin empeorar más de 5 % ningún segmento. Ver `docs/auditoria.md`.
- **¿Llegaron a su meta de 40 %?** No (ver *Resultados esperados*): 27.7 % de media en 4
  semillas frente a un techo del ~44 % del oráculo.
- **¿Y el LLM?** En la demo corre en mock para ser reproducible; la medición con llave real está
  preparada (`scripts/eval_llm.py`, `docs/eval_llm.md`) pero no publicada.
