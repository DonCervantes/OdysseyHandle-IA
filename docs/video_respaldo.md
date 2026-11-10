# Videos de respaldo y fondo · producción reproducible

Guion nuevo según «Cómo mostrar el aprendizaje»: inicial 00:00–00:40, lección 00:40–01:45,
comparación 01:45–03:00. Sustituye el guion antiguo de seis secciones. No se reutilizó la locución anterior.

```bash
bash scripts/video.sh
```

Dependencias de producción aisladas en `video/package.json` y lockfile: Remotion para composición,
Playwright para tomas reales, ffmpeg/ffprobe para normalizar audio, recortar captura y verificar streams.
No se agregan dependencias al runtime del producto. Requiere Node.js, ffmpeg, el venv del repo y Chromium
(`cd video && npx playwright install chromium` si falta; `CHROME_PATH` permite elegir un ejecutable).
ElevenLabs lee únicamente `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` y `ELEVENLABS_MODEL_ID` de `.env`.
No se imprimen sus valores. La voz usa el ID/modelo configurados; no cambia a otra voz ni inventa un clon.
Cada sección tiene caché por hash de texto/voz/modelo para no gastar de nuevo si no cambió.

Salidas: `var/video/demo_3min.mp4`, `var/video/fondo_pitch.mp4`; archivos locales ignorados por Git.
El narrado es de 180 s con voz AAC y dos segundos finales libres. Fondo de 180 s **sin stream de audio**:
curvas desde CSV, ciclo animado, linaje creciente, fundido final a la misma imagen inicial.
Paleta del tablero: fijo `#64748b`, parámetros `#b7791f`, RSI `#007f73`, fondo `#f8faf9`.

## Narración exacta y montaje

«RSI» se pronuncia «erre ese i». Importes de locución y rótulos se calculan desde la misma evidencia.
### 00:00–00:16 · Las reglas fijas repiten el error

En México, siete de cada diez vehículos circulan sin seguro, según la AMIS. Y una tarifa con reglas fijas cobra mal a segmentos enteros. AutoGuard aprende de ese error. Esta demo usa datos simulados.

Audio original: 12.24 s; ajuste de tempo: 1.000×; colocación desde 0 s.

### 00:16–00:40 · Un caso reservado revela la falla

Este Toyota Corolla viene del conjunto reservado. Las reglas fijas cotizan 14 664 pesos; el costo observado fue 20 100. El analista detecta subcotización de 19 coma 2 por ciento en 115 autos de alto kilometraje. Penalizamos más cobrar de menos: buscamos el cuantil cero punto seis del costo, no su media.

Audio original: 20.80 s; ajuste de tempo: 1.000×; colocación desde 16 s.

### 00:40–01:04 · La lección queda guardada

La lección propone reajustar el factor de kilometraje. Aquí están la hipótesis, el cambio del YAML y su commit. En el conjunto reservado, la pérdida media baja de 6 168 a 4 654 pesos. El evaluador congelado acepta: mejora suficiente y ningún segmento excede el límite de deterioro.

Audio original: 19.44 s; ajuste de tempo: 1.000×; colocación desde 40 s.

### 01:04–01:24 · El sucesor hereda el cambio

El sucesor hereda esa configuración y cotiza el mismo auto en 19 372 pesos. Cambió la regla del cotizador; no el auto ni su costo. Cada lección aceptada queda en el linaje. Se acumulan versiones, lecciones y posteriors que orientan qué mejora intentar después.

Audio original: 17.68 s; ajuste de tempo: 1.000×; colocación desde 64 s.

### 01:24–01:45 · Sistema y equipo tienen papeles distintos

El equipo fijó la pérdida, los umbrales, el simulador y la lista blanca. El sistema detectó, propuso, evaluó y aceptó. El meta mejorador aprende de aciertos y rechazos. En producción, el actuario aprobaría aquí. Este botón muestra la intervención humana; la corrida experimental automatiza las decisiones.

Audio original: 18.80 s; ajuste de tempo: 1.000×; colocación desde 84 s.

### 01:45–02:10 · Mismos autos, tres formas de aprender

Comparamos doce mil autos por variante, con la misma semilla. Regret significa aquí pérdida asimétrica acumulada. Reglas fijas: 51.31 millones; solo parámetros: 44.01; erre ese i completo: 36.73. Reduce 28 coma 4 por ciento. En cuatro semillas, la mejora va de 25.9 a 29.2 por ciento. Estos casos reservados nunca entraron al mejorador.

Audio original: 28.24 s; ajuste de tempo: 1.153×; colocación desde 105 s.

### 02:10–02:30 · Sin la lección, vuelve la falla

Aislamos el efecto: revertimos solo esa primera lección en una copia del linaje. La prima vuelve a 14 664 pesos y regresa la pérdida original. La variante solo parámetros es nuestro control. Esta reversión prueba el cambio local; no atribuye toda la mejora final a un único parche.

Audio original: 18.64 s; ajuste de tempo: 1.000×; colocación desde 130 s.

### 02:30–02:46 · Lo que todavía falla

El resultado final sigue 13 coma 6 por ciento sobre el oráculo. No aprendió la interacción de autos de treinta años con un siniestro. La aceptación termina en cero. No alcanzamos la meta del cuarenta por ciento ni la convergencia estricta.

Audio original: 13.12 s; ajuste de tempo: 1.000×; colocación desde 150 s.

### 02:46–03:00 · Construido desde cero con evidencia

Codex construyó linaje, ciclo y tableros, y revisó entregas. Claude Code y Cursor también participaron. Scripts y relevo coordinaron al equipo. Empezamos desde cero este nueve de noviembre.

Audio original: 11.92 s; ajuste de tempo: 1.000×; colocación desde 166 s.

## Cifras y trazabilidad

| Cifra / evidencia | Valor utilizado | Fuente exacta |
| --- | --- | --- |
| Regret fijo / parámetros / RSI | 51,312,336 / 44,014,125 / 36,727,792 MXN | `var/runs/demo-seed42/summary.json → regret` |
| Mejora RSI / solo parámetros | 28.4% / 14.2% | `summary.json → mejora_rsi`; `1 − regret.parametros / regret.estatico` |
| Pólizas / generaciones / parches RSI aceptados | 12,000 / 20 / 24 | `summary.json → batches,batch_size,k`; contar `patches.jsonl` por variante/veredicto |
| Curvas originales | 180 filas | `curve.csv → variant,polizas,loss,regret` |
| Hipótesis elegida | n=115, sesgo=-19.2%, p=2.02e-18 | `patches.jsonl → rsi-g1-1-ajuste_factor`; reconstrucción exacta con `video/evidence.py` |
| Holdout antes / después | 6,168 / 4,654 MXN; 24.5% | mismo parche → `metrics_before.loss`, `metrics_after.loss,ganancia` |
| Caso reservado | SIM-42-0000132; Toyota Corolla 2002; 242,689 km | mismos primeros `k × batch_size` autos de seed42, `MarketSimulator` + `collect` + `split_holdout` |
| Prima v0 / sucesor / revertida / costo | 14,664 / 19,372 / 14,664 / 20,100 MXN | `var/video/evidence.json → case`; `quote_df` ejecutado con YAML de Git |
| Pérdida del caso antes / después / revertida | 8,154 / 1,092 / 8,154 MXN | `objective.loss` sobre las cotizaciones anteriores |
| Padre / sucesor | `bcb94c8` / `833455e` | `configs/rsi/.git`; `versions.jsonl` |
| Posteriors y lecciones | generaciones 1–20 | `meta.jsonl → arms,lecciones,tasa_aceptacion` |
| Robustez cuatro semillas | 25.9–29.2% | tabla T-23 de `RELEVO.md`; cifras originales redondeadas, no precisión inventada |
| Exceso final sobre oráculo / aceptación final | 13.6% / 0.0% | `summary.json → exceso_final_vs_oraculo.rsi, tasa_aceptacion_rsi.ultima` |
| Meta 40% / convergencia | no alcanzadas | `summary.json → gate2,convergencia_polizas`; diseño T-23 |
| Primer commit | `d576d77|2026-11-09T14:29:38-06:00|T-00: scaffold, contratos, stubs, backlog y protocolo multi-sesión` | `git log --reverse` |
| Contribuciones Codex | T-10, T-13, T-15, T-24, T-29; revisiones T-04, T-06, T-11, T-21, T-28 | `origin/tasks-state:T-XX/owner` y `/reviewer`; trabajos posteriores en `RELEVO.md`/Git |


La cifra pública mexicana se verificó en [Animal Político, AMIS, 27 julio 2026](https://grupoanimal.mx/hablemos-de/mexico-mas-vehiculos-pocos-seguros-qualitas-record).
Se refiere a vehículos, no solo automóviles particulares; no procede del simulador.
La función objetivo y los umbrales se leen de `autoguard/evaluator/objective.py`; no se alteraron.
Los casos individuales no estaban serializados en el summary: se reconstruyen con la misma semilla,
orden de lotes, tamaño y partición hash del experimento, y se cotejan las pérdidas exactas con el parche.
`evidence.json` conserva hashes SHA-256 de los cinco artefactos y los IDs completos.

## Atribución y rúbrica

- Impacto: falla v0, comparación medida y límites; no prometemos resultados actuariales reales.
- Aplicación de Codex: propietario/revisor en tasks-state, más commits y relevo posteriores. Codex hizo
  linaje, loop original y tableros; T-23 fue trabajo de Claude Code, y Cursor participó en otras entregas.
- Uso creativo de habilidades: agentes documental/visual, optimización, evaluación congelada, linaje y
  meta-mejorador; Playwright + ElevenLabs + Remotion en la producción. No se afirma haber usado un
  SKILL.md personalizado inexistente ni que el LLM modifique código durante el experimento mock.
- Demostración: mismo caso antes/después/reversión, holdout y control solo parámetros.

No hay material previo al primer commit visible del repo: d576d77|2026-11-09T14:29:38-06:00|T-00: scaffold, contratos, stubs, backlog y protocolo multi-sesión.
Los commits muestran la historia disponible; no atribuir a Codex el trabajo de las cuatro sesiones.

## Verificación y reproducción

`video/verify.py` exige 1920×1080, H.264, 180 s, audio solo en demo, narración sin solaparse,
últimos dos segundos libres, hashes de artefactos iguales y diferencia visual baja entre primer/último
fotograma del fondo. `var/video/qa/` contiene fotogramas de todas las escenas para revisión visual.
`var/video/tomas/capture-report.json` registra URLs y errores de página (debe estar vacío por toma).

La revisión de fotogramas no sustituye escuchar el archivo completo con las bocinas del evento.
Revisar ambos archivos antes del envío. Ningún video se sube automáticamente.

Referencias técnicas: [Remotion, renderMedia](https://www.remotion.dev/docs/renderer/render-media),
[licencia para personas/equipos de hasta tres personas](https://www.remotion.dev/docs/license/pricing),
[ElevenLabs, conversión de texto a voz](https://elevenlabs.io/docs/api-reference/text-to-speech/convert).
El equipo humano indicado en el repo tiene dos personas (cuatro sesiones de IA); se usa render local.
