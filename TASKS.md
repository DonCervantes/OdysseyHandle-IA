# TASKS — KAVAK AUTOGUARD AI

Backlog ejecutable derivado de `KAVAK_AUTOGUARD_AI_Plan_de_trabajo.md`. El **estado** (quién la tiene,
si está en revisión, hecha) NO se escribe aquí: vive en `scripts/tasks.sh list`. Este archivo solo
define las tareas. Protocolo completo en `AGENTS.md`.

Formato: cada tarea tiene `tipo` (`claude` = la hace un agente; `humano` = requiere a una persona o una
cuenta externa), `deps` (tareas que deben estar `done`), `rutas` (archivos que la tarea POSEE: no toques
rutas de otras tareas) y `aceptación` (lo que el revisor verifica).

Reglas comunes de aceptación para TODA tarea `claude`:
- `.venv/bin/python -m pytest` pasa completo en el worktree tras `git merge main`.
- No cambia firmas públicas de los stubs ni `autoguard/contracts.py` / `config_schema.py` / `segments.py`
  / `evaluator/objective.py` (si hace falta, se documenta en el commit y lo aprueba el revisor).
- Corre sin llaves de API (modo mock del LLM) y con semilla fija es reproducible.
- No agrega dependencias fuera de `pyproject.toml` sin justificarlo en el commit.
- Datos simulados etiquetados como SIMULADOS.

---

## Sprint 1 · Cimientos

### T-00 · Scaffold, contratos, stubs y protocolo de coordinación
- **tipo:** claude
- **deps:** —
- **rutas:** todo el esqueleto inicial
- **aceptación:** hecho por la sesión coordinadora.

### T-01 · Cliente LLM con modo mock
- **tipo:** claude
- **deps:** T-00
- **rutas:** `autoguard/llm.py`, `tests/test_llm.py`
- **qué:** implementar `complete_json` con el SDK `anthropic` (carga primero el skill `claude-api`).
  Modelo por `LLM_MODEL` (default `claude-opus-5-5`), imágenes como bloques base64, extracción robusta del
  JSON, validación opcional contra `schema` (jsonschema-lite o Pydantic), reintento 1 vez, y `fallback()`
  ante modo mock o cualquier error. Cache opcional en disco (`var/llm_cache/`) por hash de la petición.
- **aceptación:** tests sin red (mock y cliente falso inyectado); nunca loguea la llave.

### T-02 · Capa de datos: 8 tablas + repositorio
- **tipo:** claude
- **deps:** T-00
- **rutas:** `autoguard/db/`, `db/migrations/001_init.sql`, `tests/test_db.py`
- **qué:** modelos SQLAlchemy 2.0 de `vehicles, documents, predictions, outcomes, errors, agent_versions,
  patches, meta_strategy` (TRD). `session.py` lee `DATABASE_URL` (default `sqlite:///var/autoguard.db`).
  `repo.py` con funciones que reciben/devuelven contratos Pydantic: `save_vehicle`, `save_prediction(s)`
  (bulk), `save_outcome(s)`, `save_errors(df)`, `save_patch`, `save_agent_version`, `save_meta_strategy`,
  `list_patches`, `predictions_df`, etc. SQL equivalente para Supabase (Postgres) en la migración.
- **aceptación:** tests en SQLite en memoria; insertar 10k predicciones en bulk < 3 s.

### T-03 · Simulador de mercado con riesgo oculto
- **tipo:** claude
- **deps:** T-00
- **rutas:** `autoguard/sim/`, `tests/test_sim.py`
- **qué:** implementar `MarketSimulator` (ver stub). Población: marca/modelo realistas MX, año 1985–2026,
  km correlacionado con antigüedad, siniestros previos, uso, zona, danos_costo. **Riesgo oculto**:
  costo esperado = base × factores reales × interacciones; los factores reales DEBEN diferir de
  `configs/agents/cotizador.yaml` de forma que el RSI tenga qué descubrir: (a) factores mal calibrados
  (p.ej. app_transporte real 1.45), (b) al menos 2 interacciones (p.ej. autos >30 años con 1 siniestro
  cuestan MENOS; app_transporte en CDMX cuesta más), (c) una variable que el cotizador base no usa
  (`marca` o `danos_costo`). Ruido lognormal moderado (σ≈0.15–0.25) para que la convergencia se vea.
  Demanda: disposición a pagar ≈ costo esperado × lognormal; compra si prima < disposición.
- **aceptación:** misma semilla ⇒ mismos lotes y mismos costos; `costo_real` no depende de las primas;
  el cotizador base (cuando exista) tiene sesgos por segmento claramente detectables (test con
  `oracle_expected_cost` mostrando ≥3 segmentos con sesgo > 10%). Un lote de 1 000 autos < 50 ms.

### T-04 · Cotizador base explicable
- **tipo:** claude
- **deps:** T-00
- **rutas:** `autoguard/agents/cotizador.py`, `configs/agents/cotizador.yaml` (solo valores), `tests/test_cotizador.py`
- **qué:** `quote`, `quote_df` (vectorizado, numpy) y `predict` según stubs. Factor numérico: valor del
  último bin con límite ≤ x. `antiguedad` = `segments.ANIO_REFERENCIA - anio`. Reglas multiplican si
  `segments.matches`. Intervalo = prima × (1 ± intervalo_rel × (2 - cobertura_verificacion)).
  `factores` en la salida = cada multiplicador ≠ 1 aplicado (incluye `regla:<id>`). Un factor sobre una
  columna ausente usa `default`.
- **aceptación:** `quote` y `quote_df` coinciden en 1 000 perfiles; 100k cotizaciones vectorizadas < 1 s.

### T-05 · Agente documental + muestras simuladas
- **tipo:** claude
- **deps:** T-00
- **rutas:** `autoguard/agents/documental.py`, `data/samples/docs/`, `tests/test_documental.py`
- **qué:** stubs de `documental.py`. Generar 3 expedientes de ejemplo SIMULADOS (factura, tarjeta de
  circulación, póliza anterior) como PNG/PDF (Pillow) + `ground_truth.json`; uno con VIN que no coincide
  y uno con tarjeta vencida. `cross_check` 100% determinístico (incluye dígito verificador VIN ISO 3779).
  En mock, `extract` lee `ground_truth.json` por `documento_id`.
- **aceptación:** precisión de extracción en mock = 100% y script `python -m autoguard.agents.documental
  --eval` que reporta precisión por campo (con llave real debe apuntar a ≥90%).

### T-06 · Recolector de resultados
- **tipo:** claude
- **deps:** T-00
- **rutas:** `autoguard/rsi/recolector.py`, `tests/test_recolector.py`
- **aceptación:** cumple el stub; usa `objective.loss`; maneja outcomes duplicados o faltantes sin romper.

### T-07 · Analista de errores por segmento
- **tipo:** claude
- **deps:** T-00
- **rutas:** `autoguard/rsi/analista.py`, `tests/test_analista.py`
- **qué:** segmentos candidatos: bins de antigüedad, km, siniestros, uso, zona, marca, y pares de ellos.
  Sesgo medio de `error_rel`, t-test (scipy), impacto = suma de loss del segmento × |sesgo|. Texto de la
  hipótesis determinístico (LLM opcional solo para redactar). Evitar hipótesis redundantes (segmento hijo
  de otro ya elegido con mismo signo).
- **aceptación:** sobre datos sintéticos con un sesgo plantado en un segmento, lo recupera en el top 1.

### T-08 · Mejorador: propone parches
- **tipo:** claude
- **deps:** T-00
- **rutas:** `autoguard/rsi/mejorador.py`, `autoguard/rsi/prompts/`, `tests/test_mejorador.py`
- **qué:** por brazo: `ajuste_factor` (set de un multiplicador existente), `cambio_regla` (add_rule con
  multiplicador = 1/(1+sesgo) acotado para el segmento), `nueva_variable` (add_factor sobre una variable
  permitida no usada, p.ej. marca/danos_costo), `cambio_prompt` (reescribe `prompt_estrategia`; ganancia
  ~0, sirve de control). LLM con prompt que incluye `lecciones`; fallback heurístico determinístico.
  Todo parche debe pasar `apply_patch` antes de devolverse (si no, se marca `invalido`).
- **aceptación:** con las hipótesis del test de T-07, el fallback produce parches válidos que reducen el
  sesgo del segmento en datos de entrenamiento.

### T-09 · Evaluador congelado
- **tipo:** claude
- **deps:** T-04
- **rutas:** `autoguard/evaluator/evaluator.py`, `tests/test_evaluator.py`
- **qué:** stub de `evaluator.py` usando `objective.py` y `cotizador.quote_df`. Test que verifica por AST
  que nada en `autoguard/rsi/` importa ni escribe en `autoguard/evaluator/` salvo `objective.loss`/`split_holdout`/`evaluate` (solo lectura).
- **aceptación:** rechaza parche que empeora un segmento > ε aunque mejore el total; rechaza variable
  prohibida; parche inválido no consume holdout.

### T-10 · Linaje de versiones en Git
- **tipo:** claude
- **deps:** T-00
- **rutas:** `autoguard/rsi/lineage.py`, `tests/test_lineage.py`
- **qué:** stub con GitPython en repo propio (tmp en tests). Mensaje de commit incluye patch_id, tipo,
  hipótesis y métricas. `history` marca campeón (HEAD) y retirados.
- **aceptación:** commit → revert_to → la config vuelve exactamente; historial conserva todo.

### T-11 · Meta-mejorador (bandido Thompson)
- **tipo:** claude
- **deps:** T-00
- **rutas:** `autoguard/rsi/meta.py`, `tests/test_meta.py`
- **aceptación:** con recompensas sintéticas donde un brazo es mejor, tras 30 generaciones ese brazo se
  elige > 60% de las veces; la reversión de estrategia ocurre cuando la ganancia media cae (test).

## Sprint 2 · Ciclo RSI

### T-12 · Agente visual de daños
- **tipo:** claude
- **deps:** T-00
- **rutas:** `autoguard/agents/visual.py`, `data/samples/fotos/`, `data/costos_reparacion.yaml`, `tests/test_visual.py`
- **qué:** tabla de costos MXN por zona×tipo (SIMULADA), set pequeño de fotos de prueba (pueden ser
  imágenes generadas/esquemáticas con etiqueta SIMULADO) + ground truth; `--eval` reporta recall.
- **aceptación:** recall 100% en mock; con LLM real apunta a ≥80%.

### T-13 · Ciclo RSI + experimento de 3 variantes (Gate 2)
- **tipo:** claude
- **deps:** T-03, T-04, T-06, T-07, T-08, T-09, T-10, T-11
- **rutas:** `autoguard/rsi/loop.py`, `autoguard/rsi/graph.py`, `tests/test_loop.py`
- **qué:** grafo LangGraph (recolector → analista → mejorador → evaluador → linaje → meta). Variantes:
  `estatico` (nunca cambia), `parametros` (solo brazo ajuste_factor, sin meta), `rsi` (todos los brazos +
  meta). Las 3 ven la MISMA secuencia de autos (misma semilla). Cada K lotes corre una generación.
  Regret R(N) con `objective.loss` sobre TODAS las pólizas cotizadas usando `costo_real` del simulador
  (benchmark); el RSI solo aprende de las vendidas (train), el evaluador usa el holdout. Salida en
  `var/runs/<run_id>/` (ver stub) y opcionalmente a BD vía T-02 si `DATABASE_URL` está configurada.
- **aceptación:** `python -m autoguard.rsi.loop --seed 42` en modo mock termina < 3 min, una generación
  < 1 min, y `summary.json` reporta regret RSI vs estático. **Gate 2: RSI ≥40% menos regret que estático y
  converge en menos pólizas que `parametros`.** Si no se logra, documentarlo en el commit con números y
  proponer ajustes (no maquillar el simulador para que el resultado sea trivial).
- **notas de integración:** copiar en cada Patch `metrics_before["loss"]`, `metrics_after["loss"]` y
  `metrics_after["ganancia"]` del Verdict antes de `MetaImprover.update` (si no, el bandido nunca premia).
  Parches con `veredicto="invalido"` (T-08) se registran pero no se evalúan. `vehicle_id` del simulador es
  `SIM-{seed}-{n}`; helpers `profiles_df`/`input_hash` en `agents/cotizador.py`; `db.repo.predictions_df`/
  `outcomes_df` ya tienen el formato de `recolector.collect`.

### T-14 · API FastAPI
- **tipo:** claude
- **deps:** T-02, T-04, T-05
- **rutas:** `autoguard/api/`, `tests/test_api.py`
- **qué:** `POST /expedientes` (multipart docs+fotos → perfil + cotización + alertas; usa visual/valuación
  si existen, si no los omite), `GET /vehicles/{id}`, `POST /quote`, `POST /outcomes` (ingestión n8n),
  `POST /rsi/run`, `GET /patches`, `POST /patches/{id}/approve|reject`, `POST /versions/{agent}/revert/{sha}`,
  `GET /runs/latest`. Auth simple por header `X-API-Key` (env). CORS para el frontend.
- **aceptación:** tests con TestClient; expediente de muestra responde < 2 min (mock < 2 s).

### T-15 · Tablero Streamlit
- **tipo:** claude
- **deps:** T-13
- **rutas:** `dashboard/`, `.streamlit/`
- **qué:** lee `var/runs/<run_id>/` (y BD si existe). Curvas de error vs pólizas de las 3 variantes, área
  de regret sombreada, % de mejora, linaje de versiones, bitácora de parches con antes/después y veredicto,
  evolución de brazos del bandido, botón de reversión (llama a la API o a `lineage`). Modo "demo en vivo":
  reproduce la corrida generación por generación.
- **aceptación:** `streamlit run dashboard/app.py` funciona con una corrida mock; capturas en `docs/`.

## Sprint 3 · Producto y demo

### T-16 · Workflows n8n (JSON en repo)
- **tipo:** claude
- **deps:** T-14
- **rutas:** `n8n/`
- **qué:** JSON importables: (1) webhook de carga de expediente → API, (2) ingestión de resultados →
  `POST /outcomes`, (3) disparo programado del ciclo RSI, (4) correo de aprobación al actuario con
  aprobar/rechazar → API. Sin llaves en texto plano (credenciales de n8n). README de importación.
- **aceptación:** JSON válidos; el revisor verifica que no haya secretos.

### T-17 · Valuación con comparables (con caché)
- **tipo:** claude
- **deps:** T-00
- **rutas:** `autoguard/agents/valuacion.py`, `data/cache/comparables/`, `tests/test_valuacion.py`
- **qué:** Tavily (búsqueda) + Firecrawl (estructurar anuncio) vía HTTP con llaves en env; caché en disco
  obligatoria; mock con comparables SIMULADOS. Mediana robusta, ajuste por km y daños.
- **aceptación:** sin llaves funciona con mock; nunca llama a la red en tests.

### T-18 · Sandbox para parches de nivel código
- **tipo:** claude
- **deps:** T-09
- **rutas:** `autoguard/evaluator/sandbox.py`, `tests/test_sandbox.py`
- **qué:** ejecutar código de parches en Docker sin red con límites; Docker no está instalado en la Mac
  del coordinador: implementar fallback con `subprocess` + `resource` (CPU/mem/tiempo) y sin red
  declarada como limitación. Deseable, no bloquea la demo.

### T-19 · Especificación y prompt de Lovable
- **tipo:** claude
- **deps:** T-14
- **rutas:** `docs/lovable_prompt.md`
- **qué:** UN prompt inicial muy detallado (pantallas carga + expediente, contrato de la API, estilos,
  conectar GitHub) para gastar pocos créditos; lista de ≤10 iteraciones previstas.

### T-20 · README, guion de demo y semilla de demo
- **tipo:** claude
- **deps:** T-13, T-14
- **rutas:** `README.md`, `docs/demo.md`, `scripts/demo.sh`
- **qué:** instalación, cómo correr API/tablero/experimento, guion de la demo de 40 s alineado al pitch,
  semilla elegida y resultados esperados, plan B (video).

### T-21 · Revisión de seguridad y equidad final
- **tipo:** claude
- **deps:** T-13, T-14
- **rutas:** `docs/auditoria.md` (+ fixes pequeños vía la tarea dueña)
- **qué:** verificar lista blanca, que el RSI no puede tocar evaluador/objetivo, que no hay llaves en el
  repo, URLs firmadas/almacenamiento privado documentado, trazabilidad predicción→versión.

## Tareas humanas (no las reclama un agente; se marcan con `mark-done`)

### T-90 · Conectar Linear con GitHub y crear 3 ciclos
- **tipo:** humano
- **deps:** —

### T-91 · Event storming y arquitectura en Miro
- **tipo:** humano
- **deps:** —

### T-92 · Crear proyecto Supabase y aplicar migración
- **tipo:** humano
- **deps:** T-02

### T-93 · Ejecutar el prompt en Lovable y conectar GitHub
- **tipo:** humano
- **deps:** T-19

### T-94 · Importar workflows en n8n Cloud y configurar credenciales
- **tipo:** humano
- **deps:** T-16

### T-95 · Desplegar backend (Railway/Render) y tablero (Streamlit Cloud)
- **tipo:** humano
- **deps:** T-14, T-15

### T-96 · Grabar video de respaldo y ensayar pitch 3 veces
- **tipo:** humano
- **deps:** T-20

### T-97 · Cancelar Lovable Pro antes de la renovación
- **tipo:** humano
- **deps:** T-93
