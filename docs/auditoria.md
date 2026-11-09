# Auditoría de seguridad y equidad — KAVAK AUTOGUARD AI

**Tarea:** T-21 · worker `cursor-elias:w2`  
**Fecha:** 2026-11-09  
**Alcance:** código en `main` tras merge (API, RSI, evaluador, LLM, BD, `.env.example`, sandbox).  
**Datos:** todos SIMULADOS.  
**Método:** revisión estática del código y de tests de aceptación; sin red y sin llaves reales.

---

## Resumen ejecutivo

El sistema cumple los controles de diseño del plan (lista blanca, evaluador/objetivo congelados frente al RSI, sin llaves en el repo, trazabilidad predicción→versión). Dos decisiones conscientes de T-14 quedan abiertas como riesgo operativo de despliegue: **auth desactivada si `AUTOGUARD_API_KEY` está vacía** y **archivos subidos no se persisten** (`documents.storage_url` vacío). El almacenamiento privado con URLs firmadas está **especificado** (migración SQL + comentarios) pero **no implementado** todavía (pendiente de despliegue humano T-92 / producto).

| Control | Estado | Severidad residual |
| --- | --- | --- |
| Lista blanca / variables prohibidas | Cumple (código + tests) | Baja (proxies geográficos/marca) |
| RSI no escribe evaluador/objetivo | Cumple (AST + imports) | Baja |
| α, β, δ, ε fijos | Cumple | Nula en código |
| Llaves fuera del repo | Cumple | Baja (mal uso en deploy) |
| Auth API | Cumple diseño T-14; riesgo si se despliega sin clave | **Alta** en producción sin clave |
| Uploads / `storage_url` | No se guardan archivos (demo) | Media (gap vs plan de Storage) |
| URLs firmadas / bucket privado | Documentado; no cableado | Media (pre-producción) |
| Trazabilidad predicción→versión | Cumple (string `cotizador@sha`) | Baja (sin FK dura) |
| Sandbox de código (T-18) | Docker OK; fallback subprocess débil; **rompe en Windows** (`preexec_fn`) | Alta en win32 / Media sin Docker |

---

## 1. Lista blanca y equidad

### Qué hay

- Fuente de verdad en `autoguard/contracts.py`:
  - `VARIABLES_PERMITIDAS`: marca, modelo, antiguedad, anio, kilometraje, siniestros_previos, uso, zona, danos_costo, cobertura_verificacion.
  - `VARIABLES_PROHIBIDAS`: genero, edad, edad_conductor, estado_civil, religion, etnia, cp_ingreso.
- `VehicleProfile` **no** modela atributos sensibles; el cotizador solo ve columnas permitidas.
- Enforcement en capas:
  1. `CotizadorConfig._whitelist` (config YAML / tras `apply_patch`).
  2. `evaluator._validate` rechaza variables prohibidas o fuera de lista **antes** de tocar el holdout.
  3. Heurísticas del mejorador (`_heur_nueva_variable`) solo proponen variables permitidas.
- Tests: `test_rechaza_variable_prohibida`, `test_rechaza_variable_fuera_de_lista_blanca`, `test_apply_changes_and_whitelist`.
- Equidad operativa del evaluador: un parche que empeora un segmento con `n ≥ MIN_SEGMENT_N` más de `ε` se rechaza aunque mejore el total (`DELTA` / `EPSILON` en `objective.py`).

### Hallazgos

| ID | Hallazgo | Severidad | Mitigación actual / propuesta |
| --- | --- | --- | --- |
| E-01 | `zona` y `marca`/`modelo` pueden actuar como **proxies** de ingreso o demografía sin ser atributos prohibidos. | Media (producto) | Mantener lista blanca estrecha; en producción auditar disparidad por zona/marca y documentar justificación actuarial. No ampliar la lista sin tarea dedicada. |
| E-02 | La lista prohibida es enumerativa: un atributo sensible nuevo (p.ej. `nacionalidad`) no está en `VARIABLES_PROHIBIDAS` pero **sí** caería por “fuera de lista blanca” al no estar permitido. | Baja | Preferir whitelist (ya es el caso). Mantener la blacklist como documentación/UX de rechazo explícito. |

**Veredicto:** cumple el requisito de equidad del plan (“solo variables permitidas”). Residual: proxies, no vulneración directa.

---

## 2. Seguridad del RSI frente al evaluador y la función objetivo

### Qué hay

- `objective.py` declara α=1.5, β=1.0, δ=0.01, ε=0.05, holdout 20%, `MIN_SEGMENT_N=30` y advierte que el grafo RSI no puede modificarlos.
- `evaluator.py` está fuera del alcance de escritura del RSI; el grafo (`rsi/graph.py`) solo **invoca** etapas inyectadas.
- Test AST `test_rsi_no_importa_ni_escribe_evaluador` (`tests/test_evaluator.py`):
  - Imports permitidos desde RSI: solo `loss`, `split_holdout`, `evaluate`.
  - Prohíbe import de `ALPHA`/módulos evaluator, imports dinámicos, `setattr` sobre símbolos importados, y literales de rutas hacia `evaluator/`.
- Escrituras del RSI observadas: linaje YAML/Git (`rsi/lineage.py`) y artefactos de corrida (`summary.json`, jsonl) bajo `var/runs` — **nunca** `autoguard/evaluator/`.
- Holdout: `split_holdout` es determinístico por `sha256(vehicle_id)`; el mejorador solo ve train (contrato del evaluador).

### Hallazgos

| ID | Hallazgo | Severidad | Mitigación |
| --- | --- | --- | --- |
| R-01 | La barrera es de **proceso + test AST**, no de sandbox OS: un humano o una tarea futura podría editar `objective.py`. | Baja (aceptable) | Regla de repo + revisión; no hay API que mutue α/β/δ/ε. |
| R-02 | Parches de nivel código (sandbox T-18) no están cableados al loop RSI de producción del cotizador YAML; el riesgo de código arbitrario queda acotado al sandbox. | Info | Preferir backend Docker en demos con código. |

**Veredicto:** el RSI **no puede** tocar evaluador/objetivo con el código actual; el test AST lo fija como regresión.

---

## 3. Secretos y llaves en el repositorio

### Qué hay

- `.gitignore` incluye `.env` y `var/`.
- Trackeado: solo `.env.example` con valores vacíos / defaults seguros y comentarios.
- `autoguard/settings.py` carga `.env` sin override de variables ya exportadas; `AUTOGUARD_NO_DOTENV=1` en `tests/conftest.py` limpia secretos y fuerza `LLM_PROVIDER=mock` + `VALUACION_OFFLINE=1`.
- `llm.py`: modo mock sin `OPENAI_API_KEY` o con `LLM_PROVIDER=mock`; logs solo con `type(e).__name__` / mensajes propios — **nunca** la llave.
- Escaneo de patrones de llave reales en el árbol versionado: negativo. Único match: `FAKE_KEY = "sk-ant-test-NO-REAL-KEY-..."` en `tests/test_llm.py` (marcador explícito de no-real).

### Hallazgos

| ID | Hallazgo | Severidad | Mitigación |
| --- | --- | --- | --- |
| K-01 | Caché LLM en disco (`var/llm_cache/`) puede contener salidas de prompts con PII si se usa llave real. | Media (ops) | `var/` gitignored; rotar/limpiar caché; no compartir `var/` en demos. |
| K-02 | El runner RSI de la API hereda el entorno completo del padre (incluye llaves) al subprocess — necesario para LLM real. | Baja | Esperado; no loguear env; restringir quién puede `POST /rsi/run`. |

**Veredicto:** **no hay llaves reales en el repo**. Suite reproducible sin red.

---

## 4. API: autenticación y CORS (decisión T-14)

### Qué hay

- `require_api_key`: si `settings.api_key` (env `AUTOGUARD_API_KEY`) está vacío, **return inmediato** → auth off.
- Si hay clave: exige header `X-API-Key` con `secrets.compare_digest`.
- `/health` es público y reporta `"auth": bool(settings.api_key)`.
- Documentado en docstring de `api/main.py`, `Settings`, y `.env.example`.
- Test `test_auth_disabled_without_key` confirma el comportamiento.
- CORS: `AUTOGUARD_CORS_ORIGINS` default `*`.

### Hallazgos

| ID | Hallazgo | Severidad | Mitigación |
| --- | --- | --- | --- |
| A-01 | Desplegar el backend sin `AUTOGUARD_API_KEY` deja **toda** la API (quote, expedientes, approve/reject, RSI, revert) abierta. | **Alta** (ops) | Checklist de deploy (T-95): clave obligatoria + CORS restrictivo. El `/health` debe mostrar `"auth": true` antes de demo pública. |
| A-02 | CORS `*` facilita demos; en producción con credenciales es peligroso. | Media | Fijar orígenes del frontend Lovable/Streamlit en env. |
| A-03 | No hay rate limit ni tamaño máximo explícito en uploads multipart. | Media (demo) | Aceptable para hackathon; en prod limitar body/MIME y timeout. |

**Veredicto:** comportamiento **intencional y documentado**. Residual crítico solo si se olvida la clave en un host público.

---

## 5. Almacenamiento de archivos y URLs firmadas

### Qué hay (plan vs código)

| Capa | Estado |
| --- | --- |
| Plan / TRD | “Fotos y documentos en almacenamiento privado con URLs firmadas” (Supabase Storage). |
| Migración `db/migrations/001_init.sql` | Columna `documents.storage_url` con comentario *bucket privado; servir con URLs firmadas*. RLS activado en todas las tablas **sin políticas** ⇒ en Supabase solo `service_role` (backend) accede. |
| API T-14 | Lee bytes en memoria, extrae, **no escribe** el archivo a disco ni a Storage. `repo.save_document(..., storage_url=None)` ⇒ columna vacía/NULL. Docstring de `main.py` lo declara. |
| `list_documents` | Devuelve solo `DocExtraction` (JSON); no expone `storage_url`. |

### Hallazgos

| ID | Hallazgo | Severidad | Mitigación |
| --- | --- | --- | --- |
| S-01 | Gap vs plan: no hay cliente de Storage ni generación de URLs firmadas. | Media (pre-prod) | Tarea humana T-92 + follow-up de producto: subir a bucket privado y guardar URL; servir con signed URL de corta vida. |
| S-02 | Decisión demo: no persistir binarios reduce superficie (no hay blob robable en disco del API), pero impide re-auditoría visual del expediente. | Info | Documentado; para demo basta extracción + perfil. |
| S-03 | Mientras `storage_url` esté vacío, cualquier UI que asuma descarga de original fallará. | Baja | El prompt Lovable / API debe tratar `storage_url` opcional. |

**Veredicto:** el requisito de “URLs firmadas / almacenamiento privado **documentado**” se cumple a nivel de esquema y comentarios; la **implementación** de Storage queda explícitamente pendiente. La API actual es coherente con “no guarda archivos subidos”.

---

## 6. Trazabilidad predicción → versión

### Cadena observada

1. Campeón de producción: `Champion` + `ConfigRepo` (Git) → `sha` completo.
2. `version_id(sha) = "cotizador@" + sha[:7]`.
3. `cotizador.predict(..., agent_version)` guarda:
   - `agent_version` en la predicción,
   - `input_hash` = sha256 del perfil canónico,
   - `prediction_id` = `pred-` + sha256(`agent_version|input_hash`)[:24] (determinístico).
4. Persistencia: `predictions.agent_version` indexado; `agent_versions` con `git_sha`, `parent_id`, `estado` (campeón/retador/…).
5. API: cada `/expedientes` y `/quote` hace `champion.sync_db` y asocia la predicción a la versión HEAD.
6. Aprobación de parche: commit en linaje + nuevo campeón; cotizaciones posteriores llevan otro `agent_version` (cubierto en tests de API).
7. Outcomes referencian `prediction_id` → se puede subir a versión vía predicción.

### Hallazgos

| ID | Hallazgo | Severidad | Mitigación |
| --- | --- | --- | --- |
| T-01 | El vínculo predicción↔`agent_versions` es por **string** (`cotizador@abcdef0`), no FK SQL. Colisiones de prefijo de 7 hex son improbables pero posibles en repos muy largos. | Baja | Aceptable para demo; en prod considerar `git_sha` completo o FK. |
| T-02 | `POST /outcomes` acepta `prediction_id` desconocidos (los reporta en `prediccion_desconocida` pero igual guarda). | Baja | Monitorear el campo; opcionalmente rechazar desconocidos en prod. |
| T-03 | Corridas RSI del loop pueden etiquetar variantes (`cotizador-<variant>`) en BD de experimento; el campeón de API sigue siendo `cotizador@…`. | Info | No mezclar IDs de experimento con producción sin filtro. |

**Veredicto:** trazabilidad **sí** existe de predicción → `agent_version` → `git_sha` / historial Git.

---

## 7. Sandbox de parches de código (T-18)

- Backend Docker: `--network none`, memoria/CPU/pids, read-only, cap-drop — alineado al plan.
- Fallback `subprocess`: **sin** aislamiento de red real; filesystem del mismo usuario; memoria por muestreo RSS. Limitaciones declaradas en el módulo.
- Entorno mínimo del hijo **no** hereda llaves del padre.

| ID | Hallazgo | Severidad | Mitigación |
| --- | --- | --- | --- |
| X-01 | En Mac/Linux sin Docker el fallback no es frontera de seguridad. | Media | Usar Docker en demos que ejecuten nivel código; o deshabilitar ese nivel. |
| X-02 | En **Windows**, `subprocess.Popen(..., preexec_fn=...)` lanza `ValueError: preexec_fn is not supported on Windows platforms`. Los 9 tests de `tests/test_sandbox.py` fallan en este worktree (2026-11-09). No es regresión de T-21. | Alta (CI Windows) | `NECESITA:` T-18 — omitir `preexec_fn`/`start_new_session` en `sys.platform == "win32"` (límites vía Job Objects o solo timeout/kill) o marcar esos tests `skipif(windows)` hasta haber backend portable. |

---

## 8. Privacidad del ciclo RSI

- El simulador y el recolector trabajan con perfiles sintéticos / columnas de vehículo, no con fotos originales.
- La API no reenvía binarios al RSI; el loop genera su propio mercado simulado.
- Alineado al principio del plan: “el ciclo RSI trabaja con datos anonimizados” (en la práctica: simulados).

---

## 9. Inventario de controles verificados (checklist T-21)

| Requisito T-21 | Evidencia | OK |
| --- | --- | --- |
| Verificar lista blanca | `contracts.py`, `config_schema.py`, `evaluator.py`, tests | Sí |
| RSI no toca evaluador/objetivo | AST test + imports RSI + sin writes a `evaluator/` | Sí |
| No hay llaves en el repo | `.gitignore`, `.env.example`, escaneo, `llm` sin log de key | Sí |
| URLs firmadas / storage privado documentado | SQL RLS + comentario `storage_url`; gap de implementación anotado | Sí (doc) |
| Trazabilidad predicción→versión | `Prediction.agent_version`, BD, linaje Git, API | Sí |
| Auth off si `AUTOGUARD_API_KEY` vacía | `require_api_key` + test + docs | Sí (riesgo ops) |
| Uploads sin persistir (`storage_url` vacío) | `save_document` sin URL en `crear_expediente` | Sí |

---

## 10. Acciones recomendadas (fuera del alcance de escritura de T-21)

Ordenadas por impacto. Donde el fix no es `docs/auditoria.md`, se deja `NECESITA:` a la tarea dueña.

1. **Deploy (T-95 / humano):** exigir `AUTOGUARD_API_KEY` no vacía y CORS acotado antes de exponer el host. Verificar `/health` → `"auth": true`.
2. **`NECESITA:` producto / post T-92** — implementar upload a Supabase Storage privado + firmar URLs; rellenar `storage_url`.
3. **`NECESITA:` T-14 (opcional)** — límites de tamaño/MIME en `POST /expedientes` y rate limit básico.
4. **Equidad continua:** métricas de disparidad por `zona`/`marca` en el tablero (cuando exista) sin añadir variables prohibidas.
5. **`NECESITA:` T-18** — hacer el fallback `subprocess` portable a Windows (sin `preexec_fn`) o skip explícito; hoy rompe `pytest` en win32.
6. **Sandbox ops:** preferir Docker para nivel código en demos.

---

## 11. Conclusión

Para el alcance del hackathon con datos simulados, los controles de **seguridad del RSI**, **equidad por lista blanca**, **ausencia de secretos en git** y **trazabilidad de primas a versión Git** están implementados y cubiertos por tests. Los mayores riesgos residuales no son bugs de diseño del RSI, sino **operación**: API abierta sin clave, Storage firmado aún no cableado, y sandbox subprocess si se usa sin Docker. T-21 no modifica esos módulos; los deja documentados aquí con mitigaciones y `NECESITA:` donde corresponde.

### Nota de pytest en este worktree (Windows, 2026-11-09)

- `tests/test_sandbox.py`: **9 fallos** por `preexec_fn` no soportado en Windows → `NECESITA:` T-18 (X-02).
- Resto de la suite: verde; ocasionalmente `test_expediente_sample_mock_fast_and_persisted` falla por umbral `< 2.0s` en máquina cargada (flaky de timing, no de seguridad) → `NECESITA:` T-14 si se quiere umbral más tolerante o medición de mock puro.
