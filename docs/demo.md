# Guion de la demo (40 s) — KAVAK AUTOGUARD AI

> **BORRADOR (T-20).** Los números finales del experimento los pone T-23; todo lo marcado `{{T23_...}}`
> está pendiente de reemplazo. Todos los datos que se ven en pantalla son **SIMULADOS**.

Corresponde al bloque **5. Demo (40 s)** del pitch de 3 minutos
([`KAVAK_AUTOGUARD_AI_Plan_de_trabajo.md`](../KAVAK_AUTOGUARD_AI_Plan_de_trabajo.md) → *Pitch*). Llega
justo después de "El diferenciador RSI", así que el público ya escuchó *qué* hace el ciclo; aquí lo **ve**.

## Semilla elegida: 42

- Comando: `LLM_PROVIDER=mock python -m autoguard.rsi.loop --seed 42 --output-dir var/runs/demo-seed42`
  (lo hace `bash scripts/demo.sh`). Parámetros por defecto: 60 lotes × 200 autos, una generación cada
  3 lotes ⇒ **12,000 pólizas por variante y 20 generaciones**.
- Por qué 42: es la semilla de referencia de todo el proyecto (T-13, T-23 y los tests), es determinística
  en modo mock (misma corrida ⇒ mismos números y mismos parches) y {{T23_SEMILLA_JUSTIFICACION}}.
- Tiempo de la corrida en una laptop: {{T23_TIEMPO_CORRIDA}} (con el código de main/T-13 tarda ~2.5 min; se prepara ANTES del pitch, nunca en vivo).

## Resultados esperados (seed 42)

| Métrica | `estatico` | `parametros` | `rsi` |
| --- | --- | --- | --- |
| Regret acumulado (MXN) | {{T23_REGRET_42_ESTATICO}} | {{T23_REGRET_42_PARAMETROS}} | {{T23_REGRET_42_RSI}} |
| Pólizas hasta convergencia | — | {{T23_CONVERGENCIA_42_PARAMETROS}} | {{T23_CONVERGENCIA_42_RSI}} |

- Mejora del RSI frente al estático: **{{T23_MEJORA_42}}** (preliminar: {{T23_PRELIMINAR}}; borrador
  −27.4 % en seed 42, frente a −4.3 % de la línea base de T-13).
- Gate 2 (≥ 40 %): **no cumple**. El tablero lo muestra como "No cumple" y lo decimos sin rodeos si
  preguntan: incluso un oráculo con conocimiento perfecto solo logra ~44 % (43.7–44.8 % según semilla) y
  un aprendiz ideal que ya conoce la estructura verdadera logra 39–41 %; el 40 % fijo está en el límite
  de lo alcanzable en este simulador.
- Parches aceptados del RSI en la corrida: {{T23_PARCHES_ACEPTADOS_42}}; el parche que se usará para la
  reversión: {{T23_PARCHE_REVERSION_42}}.

Comprobación rápida antes de subir al escenario: `bash scripts/demo.sh` imprime el resumen de
`var/runs/demo-seed42/summary.json`; debe coincidir con la tabla de arriba.

## Preparación (10 min antes)

1. `bash scripts/demo.sh --start` → corrida seed 42 lista, API en `:8000`, tablero en `:8501`.
2. Navegador con **dos pestañas** ya abiertas y con zoom al 125 %:
   - Pestaña A: frontend de Lovable (o, si no está desplegado, Swagger `http://localhost:8000/docs` en
     `POST /expedientes`) con los archivos `data/samples/docs/EXP-001-{FAC,TC,POL}.png` y
     `data/samples/fotos/FOTO-001.png` a mano.
   - Pestaña B: tablero `http://localhost:8501`, corrida **demo-seed42** seleccionada, *Activar
     reproducción* encendido, velocidad **2×** (20 generaciones en ~20 s) y en generación 0 (↺ Inicio).
3. Cargar una vez el expediente EXP-001 para "calentar" la API (la primera llamada importa módulos).
4. Video de respaldo abierto en otra ventana, pausado en el segundo 0 (ver Plan B).

## Guion segundo a segundo

| Tiempo | En pantalla | Acción | Narración (del pitch) |
| --- | --- | --- | --- |
| 0–8 s | Pestaña A: expediente EXP-001 | Subir factura, tarjeta, póliza y una foto; enviar. Aparecen **alertas** (discrepancias documentales, daño detectado con costo) y la **prima con sus factores** e intervalo. | *(puente)* "Este es un auto revisado por los agentes: alertas, daños y una prima que se explica sola." |
| 8–12 s | Pestaña B: tablero en G0 | Cambiar de pestaña. Las tres curvas arrancan juntas. Pulsar **▶ Play**. | "Aquí hay tres cotizadores viendo los mismos autos." |
| 12–20 s | Curva *Pérdida media por lote* | La gris (estático) se queda plana; la verde (RSI) baja generación a generación. | "El de reglas fijas sigue equivocándose. El nuestro baja su error con cada póliza." |
| 20–28 s | Curva *Regret acumulado* (área sombreada) | Señalar el área: la gris crece más rápido que la verde. Métrica *Reducción de regret RSI* sube hasta {{T23_MEJORA_42}}. | "Esta área sombreada es el dinero que cuesta aprender, y con RSI es mucho menor." |
| 28–34 s | Avisos "✓ Parche aceptado" + pestaña **Parches** | Al terminar la reproducción (se pausa sola), abrir un parche aceptado: hipótesis, métricas antes/después y diff. | "Y cada cambio está aquí, explicado…" |
| 34–40 s | Pestaña **Linaje y reversión** | Apagar *Activar reproducción* (la reversión está deshabilitada durante la demo), variante `rsi`, elegir la versión anterior y pulsar **Revertir configuración de esta variante** → aviso "Nueva versión: …". | "…con un botón para revertirlo." |

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
   *(Hoy `data/demo_run/` no existe en el repo: {{T23_DEMO_RUN_RESPALDO}}.)*
2. **Frontend caído → Swagger o curl.** `http://localhost:8000/docs` → `POST /expedientes` → *Try it
   out*, o desde terminal:

   ```bash
   curl -s -X POST http://localhost:8000/expedientes \
     -F docs=@data/samples/docs/EXP-001-FAC.png \
     -F docs=@data/samples/docs/EXP-001-TC.png \
     -F docs=@data/samples/docs/EXP-001-POL.png \
     -F fotos=@data/samples/fotos/FOTO-001.png \
     -F 'datos={"kilometraje": 45000, "uso": "particular", "zona": "CDMX"}'
   ```

   Se leen en voz alta `alertas` y `cotizacion` (factores de la prima). Bitácora y reversión también por
   API: `GET /patches`, `GET /versions/cotizador`, `POST /versions/cotizador/revert/{sha}`.
3. **Todo falla (laptop, red, proyector con la app) → video de respaldo.** Grabación de 3 min con
   narración (guion en `docs/video_respaldo.md`, T-27; grabación T-96). Se reproduce desde el minuto del
   bloque de demo: {{T23_VIDEO_TIMESTAMP}}. Llevarlo también en USB y en el teléfono.

## Preguntas probables del jurado

- **¿Los datos son reales?** No: todo es simulado, incluida una función de riesgo oculta que el sistema no
  ve. Es para validar la mecánica antes de tener datos de Kavak.
- **¿Qué impide que el RSI haga trampa?** El evaluador, el holdout y la función objetivo están fuera de su
  alcance (`autoguard/evaluator/`, constantes fijas); un parche solo entra si mejora ≥ 1 % en el holdout
  sin empeorar más de 5 % ningún segmento. Ver `docs/auditoria.md`.
- **¿Llegaron a su meta de 40 %?** No (ver *Resultados esperados*): {{T23_MEJORA_MEDIA}} de media en 4
  semillas frente a un techo del ~44 % del oráculo.
- **¿Y el LLM?** En la demo corre en mock para ser reproducible; la medición con llave real está
  preparada (`scripts/eval_llm.py`, `docs/eval_llm.md`) pero no publicada.
