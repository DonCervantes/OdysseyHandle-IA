# Laboratorio RSI

```bash
LLM_PROVIDER=mock .venv/bin/python -m autoguard.rsi.loop --seed 42
.venv/bin/streamlit run dashboard/app.py --server.port 8501
```

En worktrees usar el `.venv` del checkout principal. El selector busca las corridas del checkout
principal por defecto; acepta cualquier directorio con subdirectorios `var/runs/<run_id>/`.
Lee curve.csv, summary.json, patches.jsonl, versions.jsonl y meta.jsonl cada vez que se recarga.
No fija resultados: los cambios de T-23 se reflejan al elegir la corrida nueva.
La demo avanza generación por generación, con el mismo corte de pólizas para las tres variantes.
La reversión actúa exclusivamente en el repo Git de la variante seleccionada; crea un commit y no
reescribe curvas históricas. El historial actual se consulta desde Git al abrir la sección.
La consulta opcional de BD es de solo lectura y muestra datos compartidos, identificados como tales.

## Demo de 40 segundos (T-29)

Activa reproducción y pulsa **▶ Play**. **Ⅱ Pausa** conserva la generación; **↺ Inicio** vuelve
al comienzo y pausa. Mover el deslizador de generación también pausa. Velocidad 1× distribuye
las generaciones en unos 40 s; 0.5×/2×/4× permiten adaptar la narración. Al terminar se pausa;
pulsar Play de nuevo reinicia. Cada parche aceptado se resalta al aparecer su generación y su
explicación se expande en la bitácora. No se aprueban parches ni se ejecuta el ciclo al reproducir.

Plan B: el directorio principal puede ser `var/runs/` o una corrida directa. Si no contiene
corridas con `curve.csv`, se busca `data/demo_run/` automáticamente. También puedes elegir otra
carpeta en **Corrida de respaldo (plan B)**, tanto una corrida directa como un contenedor de ellas.
Prepara una copia de una corrida REAL ya ejecutada con sus archivos `curve.csv`, `summary.json`,
`patches.jsonl`, `versions.jsonl` y `meta.jsonl`. No hace falta copiar repositorios Git para reproducir.
La UI identifica el respaldo y conserva sus números originales; no genera ni simula resultados.
