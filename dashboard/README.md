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
