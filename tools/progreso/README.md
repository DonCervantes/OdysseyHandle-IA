# Progreso de sesiones

Desde la raíz del repositorio:

```bash
.venv/bin/streamlit run tools/progreso/app.py --server.port 8502
```

Abrir http://localhost:8502. En un worktree usar el ejecutable `.venv` del checkout principal.
Lee exclusivamente `bash scripts/tasks.sh tsv`, cada 30 segundos y al pulsar actualizar.
Necesita acceso Git al remoto; ante errores conserva el último tablero y su hora de lectura.
El porcentaje incluye solo tareas `claude`; las tareas humanas se presentan aparte.
“Revisadas” cuenta veredictos actuales done/changes_requested, no el historial completo de revisiones.
Todos los datos del producto son SIMULADOS. Este tablero muestra estado real de coordinación.
