"""Write reviewable demo guides with values pulled from the same evidence as the videos."""
import json,subprocess,re
from pathlib import Path
ROOT=Path(subprocess.check_output(['git','rev-parse','--path-format=absolute','--git-common-dir'],text=True).strip()).parent
HERE=Path(__file__).resolve().parent.parent
OUT=ROOT/'var/video';e=json.loads((OUT/'evidence.json').read_text());n=json.loads((OUT/'narration.json').read_text());s=e['summary'];c=e['case'];p=e['patch'];h=e['hypothesis']
m=lambda x:f'{x:,.0f}'
pct=lambda x:f'{100*x:.1f}%'
time=lambda x:f'{int(x)//60:02d}:{int(x)%60:02d}'
rows='\n'.join(f'| {v} | {m(r)} | {pct(1-r/s["regret"]["estatico"])} |' for v,r in s['regret'].items())
seeds='\n'.join(f'| {r["seed"]} | {r["mejora"]:.1f}% |' for r in e['seeds'])
sources=f'''| Cifra / evidencia | Valor utilizado | Fuente exacta |
| --- | --- | --- |
| Regret fijo / parámetros / RSI | {m(s['regret']['estatico'])} / {m(s['regret']['parametros'])} / {m(s['regret']['rsi'])} MXN | `var/runs/demo-seed42/summary.json → regret` |
| Mejora RSI / solo parámetros | {pct(s['mejora_rsi'])} / {pct(1-s['regret']['parametros']/s['regret']['estatico'])} | `summary.json → mejora_rsi`; `1 − regret.parametros / regret.estatico` |
| Pólizas / generaciones / parches RSI aceptados | {s['batches']*s['batch_size']:,} / {s['batches']//s['k']} / {e['accepted_count']} | `summary.json → batches,batch_size,k`; contar `patches.jsonl` por variante/veredicto |
| Curvas originales | {len(e['curves'])} filas | `curve.csv → variant,polizas,loss,regret` |
| Hipótesis elegida | n={h['n']}, sesgo={pct(h['sesgo_medio'])}, p={h['p_value']:.3g} | `patches.jsonl → {p['patch_id']}`; reconstrucción exacta con `video/evidence.py` |
| Holdout antes / después | {m(p['metrics_before']['loss'])} / {m(p['metrics_after']['loss'])} MXN; {pct(p['metrics_after']['ganancia'])} | mismo parche → `metrics_before.loss`, `metrics_after.loss,ganancia` |
| Caso reservado | {c['vehicle_id']}; {c['marca']} {c['modelo']} {c['anio']}; {m(c['kilometraje'])} km | mismos primeros `k × batch_size` autos de seed42, `MarketSimulator` + `collect` + `split_holdout` |
| Prima v0 / sucesor / revertida / costo | {m(c['quotes']['v0'])} / {m(c['quotes']['sucesor'])} / {m(c['quotes']['reversion'])} / {m(c['costo_real'])} MXN | `var/video/evidence.json → case`; `quote_df` ejecutado con YAML de Git |
| Pérdida del caso antes / después / revertida | {m(c['losses']['v0'])} / {m(c['losses']['sucesor'])} / {m(c['losses']['reversion'])} MXN | `objective.loss` sobre las cotizaciones anteriores |
| Padre / sucesor | `{e['parent_sha'][:7]}` / `{e['successor_sha'][:7]}` | `configs/rsi/.git`; `versions.jsonl` |
| Posteriors y lecciones | generaciones 1–{len(e['meta'])} | `meta.jsonl → arms,lecciones,tasa_aceptacion` |
| Robustez cuatro semillas | {min(r['mejora'] for r in e['seeds'])}–{max(r['mejora'] for r in e['seeds'])}% | tabla T-23 de `RELEVO.md`; cifras originales redondeadas, no precisión inventada |
| Exceso final sobre oráculo / aceptación final | {pct(s['exceso_final_vs_oraculo']['rsi'])} / {pct(s['tasa_aceptacion_rsi']['ultima'])} | `summary.json → exceso_final_vs_oraculo.rsi, tasa_aceptacion_rsi.ultima` |
| Meta 40% / convergencia | no alcanzadas | `summary.json → gate2,convergencia_polizas`; diseño T-23 |
| Primer commit | `{e['inventory']['first_commit']}` | `git log --reverse` |
| Contribuciones Codex | {', '.join(e['inventory']['owned'])}; revisiones {', '.join(e['inventory']['reviewed'])} | `origin/tasks-state:T-XX/owner` y `/reviewer`; trabajos posteriores en `RELEVO.md`/Git |
'''
intro='''# Demo RSI Hackathon · KAVAK AUTOGUARD AI

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

'''
demo=intro+f'''## Ejecución y caso listos

Corrida `demo-seed42`: seed={s['seed']}, batches={s['batches']}, batch_size={s['batch_size']}, k={s['k']}.
Caso **{c['vehicle_id']}**, {c['marca']} {c['modelo']} {c['anio']}, {m(c['kilometraje'])} km, {c['zona']}, uso {c['uso']}.
Se seleccionó por la mediana de costo/prima del segmento diagnosticado en el holdout, no por máxima ganancia.
El mejorador recibió {e['train_n']} casos de train; el evaluador reservó {e['holdout_n']}.

El parche **{p['patch_id']}** cambia los factores de kilometraje. Padre `cotizador@{e['parent_sha'][:7]}`,
sucesor `cotizador@{e['successor_sha'][:7]}`. El caso pasa de **${m(c['quotes']['v0'])} a ${m(c['quotes']['sucesor'])}**,
con costo simulado **${m(c['costo_real'])}**. En el holdout completo, pérdida media
**${m(p['metrics_before']['loss'])} → ${m(p['metrics_after']['loss'])}**.

La reversión se EJECUTA sobre un clon temporal detenido en ese primer sucesor: restaura el YAML del padre
y se vuelve a cotizar. Prima y pérdida regresan exactamente a sus valores iniciales. El linaje original
no se modifica. Esto aísla **esa lección**; no mide la aportación de la lección dentro del campeón final ni
atribuye toda la mejora global a un único parche.

| Variante | Regret acumulado MXN | Reducción vs reglas fijas |
| --- | ---: | ---: |
{rows}

Aquí «regret» es el nombre del artefacto para **pérdida asimétrica acumulada**, no exceso acumulado sobre
un oráculo. No presentarlo como utilidad financiera ni ahorro comercial. Los tres modelos cotizan los
mismos autos y costos; las ventas y los datos disponibles para aprender pueden diferir por sus primas.

| Semilla | Mejora RSI reportada |
| --- | ---: |
{seeds}

## Ensayo automatizado y límites

Playwright recorre landing, parche aceptado, revisión humana, curvas, posteriors y linaje en las apps
reales; conserva los WEBM y PNG originales en `var/video/tomas/`. No cambia el frontend ni sus respuestas.
La revisión humana usa una copia persistida explícitamente como **ENSAYO**, pendiente en `var/demo.db`.
El botón Aprobar es real pero **no se pulsa**; el parche original conserva su veredicto del evaluador.
El revisor humano en producción es una propuesta de operación, no un paso ejecutado por esta corrida.

El holdout no entra al mejorador; sus métricas sí retroalimentan el proceso, y se reutiliza entre
propuestas. No llamarlo un test externo nuevo nunca consultado. El ejemplo reservado que empeora
permanece en la tabla: una mejora agregada no garantiza mejora para todos los autos.

Gate 2 no alcanzado: {pct(s['mejora_rsi'])} < 40%, convergencia estricta null; exceso final sobre el
oráculo {pct(s['exceso_final_vs_oraculo']['rsi'])}, aceptación final {pct(s['tasa_aceptacion_rsi']['ultima'])}.
La interacción ≥30 años con exactamente un siniestro sigue sin aprenderse (diagnóstico T-23).
La demo es mock: no confundir la optimización determinística de tarifas con una llamada al LLM real.
La evaluación de OpenAI está medida por separado en [eval_llm.md](eval_llm.md), sobre imágenes simuladas.

## Plan B y preguntas

Reproducir `demo_3min.mp4` desde el inicio; llevar copia local y USB. Si hay voz en vivo, usar únicamente
`fondo_pitch.mp4`, sin pista de audio y en loop. No depender de internet durante la presentación.
Preparar los dos minutos con [preguntas.md](preguntas.md). Narración y fuentes en [video_respaldo.md](video_respaldo.md).
'''
(HERE/'docs/demo.md').write_text(demo)
voice='\n\n'.join(f'### {time(x["start"])}–{time(x["end"])} · {x["title"]}\n\n{x["text"]}\n\nAudio original: {x["raw_duration"]:.2f} s; ajuste de tempo: {x["tempo"]:.3f}×; colocación desde {x["start"]} s.' for x in n)
video=f'''# Videos de respaldo y fondo · producción reproducible

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
{voice}

## Cifras y trazabilidad

{sources}

La cifra pública mexicana se verificó en [Animal Político, AMIS, 27 julio 2026]({e['external_context']['url']}).
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

No hay material previo al primer commit visible del repo: {e['inventory']['first_commit']}.
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
'''
(HERE/'docs/video_respaldo.md').write_text(video)
eval_text=(ROOT/'docs/eval_llm.md').read_text();eval_measured=eval_text.split('## Resultado medido',1)[1].split('**Límite honesto:**',1)[0]
questions=f'''# Preguntas del jurado · respuestas para dos minutos

Mantener abierta `demo-seed42` y `var/video/evidence.json`. Seis respuestas de unos veinte segundos.

**0:00–0:20 · ¿Qué ejecución podemos inspeccionar?**
Seed {s['seed']}, {s['batches']} lotes de {s['batch_size']} autos, generaciones cada {s['k']} lotes.
Mismos autos/costos para las tres variantes. Regret fijo {m(s['regret']['estatico'])}, parámetros
{m(s['regret']['parametros'])}, RSI {m(s['regret']['rsi'])} MXN: reducción {pct(s['mejora_rsi'])}.
Es pérdida asimétrica acumulada de datos simulados, no ahorro de clientes.

**0:20–0:40 · ¿Qué lección salió?**
`{p['patch_id']}`: reajustar kilometraje. El analista encontró {h['n']} casos de train con
sesgo {pct(h['sesgo_medio'])}, p={h['p_value']:.3g}. El evaluador congelado midió pérdida
{m(p['metrics_before']['loss'])} → {m(p['metrics_after']['loss'])} en {e['holdout_n']} casos reservados
({pct(p['metrics_after']['ganancia'])}). El signo del ajuste viene de la pérdida asimétrica, no de la media.

**0:40–1:00 · ¿Qué heredó el sucesor?**
El YAML del cotizador, confirmado en `{e['successor_sha']}` con padre `{e['parent_sha']}`.
El {c['marca']} {c['modelo']} {c['vehicle_id']} pasa de ${m(c['quotes']['v0'])} a
${m(c['quotes']['sucesor'])}, frente a costo ${m(c['costo_real'])}. Hereda factores concretos y
historia, no solo una respuesta textual. Las siguientes generaciones reciben lecciones y posteriors.

**1:00–1:20 · ¿Cómo aislaron el efecto?**
Misma semilla y mismos autos/costos, holdout por hash fuera del train y variante solo parámetros como control.
En copia del linaje, retiramos la primera lección y recotizamos: vuelve exactamente la prima inicial
${m(c['quotes']['reversion'])} y pérdida ${m(c['losses']['reversion'])}. Ablación local, no atribución
de toda la ventaja final. El holdout se reutiliza; sus métricas retroalimentan propuestas.

**1:20–1:40 · ¿Qué haría fallar la última versión?**
Cambios de distribución, interacciones no descubiertas y segmentos escasos. Ya falta la interacción
≥30 años con un siniestro; queda {pct(s['exceso_final_vs_oraculo']['rsi'])} sobre el oráculo y
aceptación final {pct(s['tasa_aceptacion_rsi']['ultima'])}. No se logró 40% ni convergencia estricta.
Validar después en datos reales, un test externo nuevo y supervisión actuarial; no vender esta tarifa como lista.

**1:40–2:00 · ¿Qué hicieron Codex, el equipo y el sistema?**
Codex implementó linaje, loop inicial y tableros, y revisó tareas (lista exacta en evidence.json).
Claude Code y Cursor también participaron. Equipo fijó simulador/objetivo/lista blanca; sistema
propuso y evaluó YAML automáticamente. En producción, el actuario aprobaría. La demo mock no usa el LLM;
la integración real OpenAI se midió separadamente sobre documentos sintéticos.

## Respaldo si preguntan por OpenAI

Resultado copiado del informe medido, no de los tests mock:

{eval_measured}

Fuente: [eval_llm.md](eval_llm.md). Son imágenes sintéticas limpias: no extrapolar a fotos/documentos reales.
La mezcla de datos y evaluación repetida puede sobreajustar; un nuevo conjunto externo es parte del siguiente paso.

## Evidencia abierta en la máquina

- Frontend `http://localhost:5173/app/parches`: filtrar generación 1, RSI, aceptado; abrir el parche indicado.
- Tablero `http://localhost:8501`: versiones, lecciones, posteriors y «No cumple» del Gate 2.
- `var/video/evidence.json`: caso, SHA completo, YAML diff, comparación y selección reproducible.
- [video_respaldo.md](video_respaldo.md): tabla de cada cifra y su fuente.
'''
(HERE/'docs/preguntas.md').write_text(questions)
print('Guiones y preguntas generados desde evidence.json y narration.json.')
