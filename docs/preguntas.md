# Preguntas del jurado · respuestas para dos minutos

Mantener abierta `demo-seed42` y `var/video/evidence.json`. Seis respuestas de unos veinte segundos.

**0:00–0:20 · ¿Qué ejecución podemos inspeccionar?**
Seed 42, 60 lotes de 200 autos, generaciones cada 3 lotes.
Mismos autos/costos para las tres variantes. Regret fijo 51,312,336, parámetros
44,014,125, RSI 36,727,792 MXN: reducción 28.4%.
Es pérdida asimétrica acumulada de datos simulados, no ahorro de clientes.

**0:20–0:40 · ¿Qué lección salió?**
`rsi-g1-1-ajuste_factor`: reajustar kilometraje. El analista encontró 115 casos de train con
sesgo -19.2%, p=2.02e-18. El evaluador congelado midió pérdida
6,168 → 4,654 en 72 casos reservados
(24.5%). El signo del ajuste viene de la pérdida asimétrica, no de la media.

**0:40–1:00 · ¿Qué heredó el sucesor?**
El YAML del cotizador, confirmado en `833455e0e73abc13a529623dd84b7d4053c859e7` con padre `bcb94c8a4a8fdc0f56d0fd92c367981a8ca254f0`.
El Toyota Corolla SIM-42-0000132 pasa de $14,664 a
$19,372, frente a costo $20,100. Hereda factores concretos y
historia, no solo una respuesta textual. Las siguientes generaciones reciben lecciones y posteriors.

**1:00–1:20 · ¿Cómo aislaron el efecto?**
Misma semilla y mismos autos/costos, holdout por hash fuera del train y variante solo parámetros como control.
En copia del linaje, retiramos la primera lección y recotizamos: vuelve exactamente la prima inicial
$14,664 y pérdida $8,154. Ablación local, no atribución
de toda la ventaja final. El holdout se reutiliza; sus métricas retroalimentan propuestas.

**1:20–1:40 · ¿Qué haría fallar la última versión?**
Cambios de distribución, interacciones no descubiertas y segmentos escasos. Ya falta la interacción
≥30 años con un siniestro; queda 13.6% sobre el oráculo y
aceptación final 0.0%. No se logró 40% ni convergencia estricta.
Validar después en datos reales, un test externo nuevo y supervisión actuarial; no vender esta tarifa como lista.

**1:40–2:00 · ¿Qué hicieron Codex, el equipo y el sistema?**
Codex implementó linaje, loop inicial y tableros, y revisó tareas (lista exacta en evidence.json).
Claude Code y Cursor también participaron. Equipo fijó simulador/objetivo/lista blanca; sistema
propuso y evaluó YAML automáticamente. En producción, el actuario aprobaría. La demo mock no usa el LLM;
la integración real OpenAI se midió separadamente sobre documentos sintéticos.

## Respaldo si preguntan por OpenAI

Resultado copiado del informe medido, no de los tests mock:

 (2026-11-10, LLM real)

Primera corrida con OpenAI `gpt-6.1-sol` (effort `low`, `LLM_CACHE=1`), 24 llamadas reales a la API, sin
aciertos de caché; tokens reportados por la API (no estimados).

| Métrica | Resultado | Meta |
| --- | --- | --- |
| Precisión de extracción documental (15 docs, 80 campos: VIN, placas, marca, modelo, año, vigencia) | **100.0%** | ≥ 90% |
| Recall de daños en fotos (9 fotos; tp=15, fn=0, fp=0) | **100.0%** (precisión 100.0%) | ≥ 80% |
| Tokens | 20,882 entrada · 2,427 salida | — |
| Costo estimado | **USD 0.066** | — |
| Tiempo | ~73 s | — |



Fuente: [eval_llm.md](eval_llm.md). Son imágenes sintéticas limpias: no extrapolar a fotos/documentos reales.
La mezcla de datos y evaluación repetida puede sobreajustar; un nuevo conjunto externo es parte del siguiente paso.

## Evidencia abierta en la máquina

- Frontend `http://localhost:5173/app/parches`: filtrar generación 1, RSI, aceptado; abrir el parche indicado.
- Tablero `http://localhost:8501`: versiones, lecciones, posteriors y «No cumple» del Gate 2.
- `var/video/evidence.json`: caso, SHA completo, YAML diff, comparación y selección reproducible.
- [video_respaldo.md](video_respaldo.md): tabla de cada cifra y su fuente.
