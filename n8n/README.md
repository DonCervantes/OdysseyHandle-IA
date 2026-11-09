# Workflows n8n — KAVAK AUTOGUARD AI (T-16)

Datos SIMULADOS. Cuatro workflows importables que orquestan la API FastAPI (`autoguard/api/main.py`).
Ningún JSON contiene URLs privadas, llaves ni correos: todo sale de **variables de entorno** de n8n
(`$env`) y de **credenciales** de n8n.

| Archivo | Disparador | Llama a |
| --- | --- | --- |
| `01_carga_expediente.json` | Webhook `POST /webhook/autoguard/expediente` (multipart) | `POST /expedientes` |
| `02_ingesta_outcomes.json` | Webhook `POST /webhook/autoguard/outcomes` (JSON) | `POST /outcomes` |
| `03_rsi_programado.json` | Schedule, cron `0 2 * * *` | `POST /rsi/run` |
| `04_aprobacion_actuario.json` | Schedule, cron `0 9 * * *` | `GET /patches?veredicto=pendiente&limit=1` → correo → Wait → `POST /patches/{id}/approve` o `/reject` |

## 1. Variables de entorno de n8n

Defínelas en el entorno del proceso de n8n (docker-compose, Railway, `.env` de n8n…), nunca en el JSON:

| Variable | Ejemplo | Uso |
| --- | --- | --- |
| `AUTOGUARD_API_URL` | `https://autoguard-api.example.com` (sin `/` final) | URL base de la API |
| `AUTOGUARD_ACTUARIO_EMAIL` | `actuario@example.com` | destinatario del correo de aprobación |
| `AUTOGUARD_MAIL_FROM` | `autoguard@example.com` | remitente |
| `N8N_BLOCK_ENV_ACCESS_IN_NODE` | `false` | permite leer `$env` en expresiones (en versiones recientes viene en `true`) |
| `WEBHOOK_URL` | `https://n8n.example.com/` | URL pública de n8n: de ella sale `$execution.resumeUrl` de los links del correo |

## 2. Credenciales (Settings → Credentials → Add credential)

1. **Header Auth** llamada `AutoGuard API Key`: *Name* = `X-API-Key`, *Value* = el valor de
   `AUTOGUARD_API_KEY` que usa la API. Se referencia desde todos los nodos HTTP Request.
2. **SMTP** llamada `AutoGuard SMTP` (host, puerto, usuario y contraseña de tu proveedor) para el nodo
   *Send Email*. Si prefieres Gmail, reemplaza ese nodo por *Gmail → Send* con credencial OAuth2 y
   el mismo asunto/HTML.

## 3. Importar

1. n8n → *Workflows* → *Import from File* → elige cada `n8n/0X_*.json`.
2. En cada nodo HTTP Request / Send Email, si n8n marca la credencial en rojo, selecciona la creada en
   el paso 2 (los ids del JSON son marcadores; n8n los re-vincula por nombre o a mano).
3. Guarda y **activa** los workflows (los webhooks de producción y los schedules solo corren activos).

## 4. Uso

**Carga de expediente** (campos multipart: `factura`, `tarjeta`, `poliza` como archivos; `datos` como
JSON en texto):

```bash
curl -X POST "$N8N/webhook/autoguard/expediente" \
  -F factura=@data/samples/docs/EXP-001-FAC.png \
  -F tarjeta=@data/samples/docs/EXP-001-TC.png \
  -F poliza=@data/samples/docs/EXP-001-POL.png \
  -F 'datos={"kilometraje":85000,"siniestros_previos":1,"uso":"particular","zona":"CDMX"}'
```
Devuelve la respuesta de `POST /expedientes` (perfil, alertas, documentos, cotización).

**Ingesta de resultados**: `POST $N8N/webhook/autoguard/outcomes` con un `Outcome` o una lista
(mismo cuerpo que `POST /outcomes`; es idempotente por `outcome_id`).

**RSI programado**: cada noche dispara `POST /rsi/run` (`seed=42, batches=60, batch_size=200, k=3`;
edita el JSON del nodo para cambiarlo). Si ya hay una corrida en curso la API responde 409 y la
ejecución falla sin efectos.

**Aprobación del actuario**: cada mañana toma el primer parche pendiente, envía un correo con la
hipótesis, el diff y las métricas, y dos links (`?decision=aprobar` / `?decision=rechazar`) al
`resumeUrl` del nodo *Wait*. Al hacer clic la ejecución continúa y llama a
`POST /patches/{id}/approve` o `/reject` (con `razon`). Sin respuesta en 48 h la ejecución termina y
el parche sigue pendiente (se vuelve a enviar al día siguiente).

## 5. Validación

`tests/test_n8n_workflows.py` verifica que cada JSON parsea, que las conexiones apuntan a nodos
existentes, que cada ruta usada existe en `create_app()` con su método, que todos los HTTP Request usan la
credencial Header Auth y que no hay secretos (regex de llaves).
