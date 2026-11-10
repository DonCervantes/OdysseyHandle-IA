# Demo RSI Hackathon · KAVAK AUTOGUARD AI

Formato: **3:00 de demo + 2:00 de preguntas**. Datos simulados; el sistema usa mock reproducible.
La historia sigue «versión inicial → lección heredada → comparación». No ejecutar el entrenamiento
ni pedir al LLM respuestas nuevas durante el pitch.

```bash
bash scripts/demo.sh --start    # API :8000, frontend :5173, tablero :8501
bash scripts/video.sh           # genera ambos videos y verifica sus streams
```

Salidas locales: `var/video/demo_3min.mp4` (voz de Dylan) y `var/video/fondo_pitch.mp4` (sin audio).
El archivo `var/video/verification.json` certifica duración, resolución, audio, hashes y continuidad del loop.
Ambos usan 1920×1080, H.264, 30 fps y duran 180 segundos; el narrado deja los últimos dos segundos sin voz.
Para presentar en vivo, reproducir el fondo en repetición y usar el guion; para respaldo, reproducir la demo narrada.

## Guion de tres minutos

| Tiempo | Qué mostrar | Qué demostrar |
| --- | --- | --- |
| 00:00–00:40 | Contexto México; caso del holdout con prima v0 y costo; salida del analista y pérdida asimétrica | La falla de reglas fijas es medible; la prima óptima corresponde al cuantil 0.6, no a anular el sesgo medio. |
| 00:40–01:45 | Parche real, diff YAML, métricas reservadas y commit; mismo caso con sucesor; versiones, lecciones y posteriors; botón del actuario | El sucesor hereda una modificación concreta. EQUIPO fija el marco; SISTEMA detecta, propone, evalúa y acepta. |
| 01:45–03:00 | Tres variantes y cuatro semillas; casos reservados; reversión; límites; contribuciones del equipo | Comparación controlada y atribución local, sin ocultar que el Gate 2 no se cumple. |

## Ejecución y caso listos

Corrida `demo-seed42`: seed=42, batches=60, batch_size=200, k=3.
Caso **SIM-42-0000132**, Toyota Corolla 2002, 242,689 km, CDMX, uso particular.
Se seleccionó por la mediana de costo/prima del segmento diagnosticado en el holdout, no por máxima ganancia.
El mejorador recibió 292 casos de train; el evaluador reservó 72.

El parche **rsi-g1-1-ajuste_factor** cambia los factores de kilometraje. Padre `cotizador@bcb94c8`,
sucesor `cotizador@833455e`. El caso pasa de **$14,664 a $19,372**,
con costo simulado **$20,100**. En el holdout completo, pérdida media
**$6,168 → $4,654**.

La reversión se EJECUTA sobre un clon temporal detenido en ese primer sucesor: restaura el YAML del padre
y se vuelve a cotizar. Prima y pérdida regresan exactamente a sus valores iniciales. El linaje original
no se modifica. Esto aísla **esa lección**; no mide la aportación de la lección dentro del campeón final ni
atribuye toda la mejora global a un único parche.

| Variante | Regret acumulado MXN | Reducción vs reglas fijas |
| --- | ---: | ---: |
| estatico | 51,312,336 | 0.0% |
| parametros | 44,014,125 | 14.2% |
| rsi | 36,727,792 | 28.4% |

Aquí «regret» es el nombre del artefacto para **pérdida asimétrica acumulada**, no exceso acumulado sobre
un oráculo. No presentarlo como utilidad financiera ni ahorro comercial. Los tres modelos cotizan los
mismos autos y costos; las ventas y los datos disponibles para aprender pueden diferir por sus primas.

| Semilla | Mejora RSI reportada |
| --- | ---: |
| 42 | 28.4% |
| 1 | 25.9% |
| 7 | 27.4% |
| 123 | 29.2% |

## Ensayo automatizado y límites

Playwright recorre landing, parche aceptado, revisión humana, curvas, posteriors y linaje en las apps
reales; conserva los WEBM y PNG originales en `var/video/tomas/`. No cambia el frontend ni sus respuestas.
La revisión humana usa una copia persistida explícitamente como **ENSAYO**, pendiente en `var/demo.db`.
El botón Aprobar es real pero **no se pulsa**; el parche original conserva su veredicto del evaluador.
El revisor humano en producción es una propuesta de operación, no un paso ejecutado por esta corrida.

El holdout no entra al mejorador; sus métricas sí retroalimentan el proceso, y se reutiliza entre
propuestas. No llamarlo un test externo nuevo nunca consultado. El ejemplo reservado que empeora
permanece en la tabla: una mejora agregada no garantiza mejora para todos los autos.

Gate 2 no alcanzado: 28.4% < 40%, convergencia estricta null; exceso final sobre el
oráculo 13.6%, aceptación final 0.0%.
La interacción ≥30 años con exactamente un siniestro sigue sin aprenderse (diagnóstico T-23).
La demo es mock: no confundir la optimización determinística de tarifas con una llamada al LLM real.
La evaluación de OpenAI está medida por separado en [eval_llm.md](eval_llm.md), sobre imágenes simuladas.

## Plan B y preguntas

Reproducir `demo_3min.mp4` desde el inicio; llevar copia local y USB. Si hay voz en vivo, usar únicamente
`fondo_pitch.mp4`, sin pista de audio y en loop. No depender de internet durante la presentación.
Preparar los dos minutos con [preguntas.md](preguntas.md). Narración y fuentes en [video_respaldo.md](video_respaldo.md).
