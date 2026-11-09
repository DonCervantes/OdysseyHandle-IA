# Prompt de Lovable — frontend de usuario (T-19)

Presupuesto: **100 créditos de Lovable Pro**. Estrategia: un solo prompt inicial muy detallado (abajo),
máximo ~10 iteraciones grandes y ajustes menores directamente en código vía GitHub.
El frontend de Lovable cubre al **valuador**, al **cliente** y al **actuario** (historias 1–4 y 6 del plan).
El tablero de curvas RSI para los jueces (historia 5) **vive en Streamlit**, no en Lovable.

Contrato copiado de `autoguard/api/main.py`, `autoguard/api/services.py` y `autoguard/contracts.py`
(origin/main, merge de T-14). Si la API cambia, actualiza la sección "CONTRATO DE LA API" antes de pegar.

## 1. Checklist previa (antes de gastar el primer crédito)

- [ ] **Conectar GitHub primero**: crear el proyecto vacío en Lovable → Settings → GitHub → conectar y
      crear repo propio (p. ej. `autoguard-frontend`). Así todo cambio queda versionado y el plan B es posible.
- [ ] Backend accesible por HTTPS (T-95: Railway/Render) y `GET /health` responde `{"ok": true, ...}`.
- [ ] En el backend: `AUTOGUARD_CORS_ORIGINS` incluye el dominio de preview y el publicado de Lovable
      (`https://<proyecto>.lovable.app`, y el de preview `*.lovableproject.com` si aplica).
- [ ] `AUTOGUARD_API_KEY` definido en el backend (si está vacío la auth se desactiva: solo desarrollo local).
- [ ] Variables del frontend en Lovable (Project settings → Environment / o `.env` en el repo, nunca commiteado):
      `VITE_API_URL`, `VITE_API_KEY`, `VITE_DASHBOARD_URL` (URL pública de Streamlit Cloud).
      Nota: toda variable `VITE_*` termina en el bundle del navegador; la API key del front debe ser una
      llave de demo, rotada después del hackathon (ver `docs/auditoria.md`, T-21).
- [ ] Tener a mano archivos de prueba: `data/samples/docs/EXP-001-FAC.png`, `EXP-001-TC.png`,
      `EXP-001-POL.png` y `data/samples/fotos/FOTO-001.png` (todos SIMULADOS).
- [ ] Ya hay parches para el actuario: correr una vez `python -m autoguard.rsi.loop` (o `POST /rsi/run`)
      para que exista `var/runs/<run>/patches.jsonl`.
- [ ] Usar **plan mode / chat** (no consume edición) para dudas; solo mandar mensajes de edición con objetivo claro.

## 2. Prompt inicial (pegar tal cual)

```text
Construye el frontend web de "AutoGuard AI", una herramienta interna para revisar autos seminuevos antes de comprarlos y asegurarlos. TODOS LOS DATOS SON SIMULADOS (demo de hackathon). Idioma de la interfaz: español de México. Stack: React + Vite + TypeScript + Tailwind + shadcn/ui + React Router + TanStack Query. NO uses Supabase, autenticación de usuarios ni base de datos propia: toda la información viene de una API REST externa ya existente (FastAPI). No inventes endpoints ni campos: usa exactamente el contrato de abajo.

=== CONFIGURACIÓN ===
- Lee la URL base de import.meta.env.VITE_API_URL y la llave de import.meta.env.VITE_API_KEY. NUNCA escribas una URL o llave real en el código; si falta VITE_API_URL muestra una pantalla de configuración con el mensaje "Falta VITE_API_URL" en lugar de romper.
- Enlace al tablero de datos: import.meta.env.VITE_DASHBOARD_URL (tablero de curvas RSI en Streamlit, se abre en pestaña nueva). Si no está definida, oculta el enlace.
- Crea un único cliente src/lib/api.ts con fetch que: antepone VITE_API_URL, agrega el header "X-API-Key" con VITE_API_KEY en TODAS las llamadas excepto GET /health (si la variable está vacía no mandes el header), y convierte errores en mensajes legibles: 401 → "Llave de API inválida o ausente"; 404/409/422 → mostrar el campo "detail" del JSON de FastAPI (puede ser string o una lista de objetos {loc, msg}: une los msg); error de red → "No se pudo conectar con la API". Todos los tipos TypeScript de abajo van en src/lib/types.ts.

=== IDENTIDAD VISUAL ===
- Marca propia "AutoGuard AI" (NO uses logotipos, colores ni tipografías de Kavak ni de ninguna otra empresa). Logotipo: un escudo simple en SVG + texto.
- Estilo sobrio y profesional tipo herramienta de análisis: fondo gris muy claro, tarjetas blancas con borde sutil, color primario azul petróleo (#0F4C5C), acento ámbar (#E0A100) solo para llamar la atención. Fuente Inter. Modo oscuro opcional vía la clase de shadcn.
- Severidades: "alta" = rojo, "media" = ámbar, "info" = gris azulado; siempre con texto además del color (accesible).
- Montos en pesos mexicanos con Intl.NumberFormat("es-MX", {style:"currency", currency:"MXN"}). Porcentajes con 0–1 decimales. Fechas en es-MX.
- Responsive: en móvil las tablas se vuelven tarjetas apiladas y la navegación se colapsa en un menú.
- En el encabezado SIEMPRE visible una insignia "Datos simulados" (badge ámbar), además del enlace "Tablero RSI (Streamlit)" y un indicador del estado de la API (punto verde/rojo usando GET /health; muestra "LLM: mock" o "LLM: real").

=== PANTALLAS ===
Navegación superior: "Nuevo expediente" (/), "Bitácora de parches" (/parches), "Versiones del cotizador" (/versiones), "Tablero RSI" (enlace externo).

1) NUEVO EXPEDIENTE (/)  — usuario: valuador.
- Zona de arrastrar y soltar "Documentos" (obligatoria, al menos 1; PNG, JPG o PDF): factura, tarjeta de circulación, póliza anterior. Por cada documento un select de tipo con opciones: "Inferir del nombre" (default), factura, tarjeta_circulacion, poliza_anterior, otro. Explica en texto pequeño que el nombre del archivo ayuda a inferir el tipo (FAC, TC, POL).
- Zona "Fotos del vehículo" (opcional; PNG/JPG) con miniaturas y botón quitar.
- Formulario "Datos declarados" (opcionales): kilometraje (entero ≥0), siniestros previos (entero ≥0), uso (particular | app_transporte | comercial), zona (CDMX | EDOMEX | JAL | NL | PUE | OTRA), y campo opcional "ID de vehículo".
- Botón "Analizar expediente". Mientras se envía: botón deshabilitado, spinner y pasos animados ("Leyendo documentos… Verificando datos… Revisando fotos… Cotizando…"). Al terminar navega a /expediente/:vehicle_id pasando la respuesta completa en el estado de navegación (y guárdala en sessionStorage con llave "expediente:<vehicle_id>" para poder recargar).
- Construcción del multipart (FormData) EXACTA:
    - por cada documento: formData.append("docs", file)
    - por cada foto: formData.append("fotos", file)
    - "tipos": SOLO si el usuario eligió tipo para TODOS los documentos, agrega un "tipos" por documento en el mismo orden (formData.append("tipos", tipo)); si alguno quedó en "Inferir", NO mandes "tipos" en absoluto (la API exige que tenga el mismo largo que docs).
    - "datos": formData.append("datos", JSON.stringify({kilometraje, siniestros_previos, uso, zona})) omitiendo las llaves vacías; si no hay ninguna manda "{}".
    - "vehicle_id": solo si el usuario lo escribió.
    - NO pongas el header Content-Type manualmente (el navegador agrega el boundary).

2) EXPEDIENTE (/expediente/:vehicleId) — usuarios: valuador y cliente.
- Fuente de datos: la respuesta de POST /expedientes si está en el estado de navegación o sessionStorage; si no (p. ej. al abrir el enlace directo), llama GET /vehicles/{vehicle_id} y muestra lo disponible (perfil, documentos y la predicción más reciente; la valuación solo existe en la respuesta de POST, en ese caso muestra "Valuación no disponible en esta vista").
- Encabezado: "Marca Modelo Año", chips con VIN y placas (o "—"), id del vehículo, tiempo de análisis (tiempo_ms) y la insignia "Datos simulados".
- Tarjeta "Perfil": kilometraje, siniestros previos, uso, zona y una barra "Cobertura de verificación" (cobertura_verificacion 0–1 como %; explica: fracción de campos confirmados por ≥2 documentos).
- Tarjeta "Alertas": lista ordenada por severidad (alta → media → info) con badge de severidad, código (monoespaciado), detalle y fuentes (documento_id). Resumen arriba: "N altas · N medias · N info". Si no hay alertas: estado vacío verde "Sin discrepancias detectadas".
- Tarjeta "Daños detectados en fotos": tabla zona, tipo, costo estimado (MXN), confianza (%), y total de reacondicionamiento (suma de costo_est). Si "visual" aparece en "omitidos", muestra un aviso gris con el motivo. Si no hay daños: "Sin daños detectados".
- Tarjeta "Valuación": precio_estimado grande, rango [min, max], precio_mercado, descuento_danos, n_comparables, fuente (badge: mock/cache/tavily) y una tabla colapsable de comparables (titulo, precio, precio_ajustado, anio, kilometraje, url como enlace si existe; marca las filas con atipico=true con badge "Atípico"). Si valuacion es null, muestra el motivo de omitidos.valuacion.
- Tarjeta "Prima del seguro" (la más destacada): output.prima grande en MXN/año, intervalo [lo, hi] como barra con la prima marcada, confianza como %, y la tabla "Factores que explican la prima": cada entrada de output.factores (nombre → multiplicador). Muestra el multiplicador con 2 decimales y una pequeña barra horizontal centrada en 1.00 (verde <1 abarata, rojo >1 encarece). Debajo, en texto pequeño: agent_version (p. ej. "cotizador@a1b2c3d"), prediction_id y created_at. Texto aclaratorio: "Solo se usan variables permitidas del vehículo; nunca género, edad ni datos personales."
- Tarjeta colapsable "Documentos procesados": por documento: documento_id, tipo, vin, placas, marca, modelo, anio, vigencia, confianza.
- Botones: "Nuevo expediente" y "Descargar JSON" (descarga la respuesta completa).

3) BITÁCORA DE PARCHES (/parches) — usuario: actuario.
- GET /patches con filtros arriba: veredicto (Todos | pendiente | aceptado | rechazado | invalido) y generación (número). Muestra la "fuente" de la respuesta ("db" o "run") como badge.
- Lista de tarjetas, una por parche: patch_id, generation, tipo (ajuste_factor | nueva_variable | cambio_regla | cambio_prompt), nivel, badge de veredicto (null → "Pendiente"), hipótesis en lenguaje natural, segmento (chips clave=valor), diff en bloque monoespaciado, metrica_objetivo, y una tabla "Métricas antes / después" uniendo las llaves de metrics_before y metrics_after con la diferencia (verde si baja la pérdida). Muestra razon si existe.
- Botones "Aprobar" y "Rechazar" solo en parches pendientes (veredicto null). Ambos abren un diálogo con textarea opcional "Razón" y confirmación. Aprobar → POST /patches/{patch_id}/approve con body {"razon": "..."}; Rechazar → POST /patches/{patch_id}/reject con body {"razon": "..."}. Al aprobar muestra un toast con la nueva versión del cotizador (version.id). Tras cualquier acción invalida las consultas de parches y versiones. Si la API responde 409/422 muestra el detail en un toast de error (p. ej. "el parche no aplica al campeón actual").
- Estado vacío: "Aún no hay parches. Ejecuta el ciclo RSI y vuelve a cargar."

4) VERSIONES DEL COTIZADOR (/versiones) — usuario: analista/actuario.
- GET /versions/cotizador. Línea de tiempo vertical (la primera es la actual): id, badge de estado ("campeon" → "En producción", "retirado" → "Retirada"), git_sha corto (7), parent_id, created_at y métricas (dict nombre → número).
- En cada versión que NO es la campeona, botón "Revertir a esta versión" con diálogo de confirmación ("Las nuevas cotizaciones usarán esta configuración. La reversión queda registrada en el linaje.") → POST /versions/cotizador/revert/{git_sha} (usa el git_sha completo). Al terminar, toast con la nueva versión y recarga la lista.

=== ESTADOS GENERALES ===
- Cada consulta con skeletons de carga, mensaje de error con botón "Reintentar" y estado vacío.
- Nunca muestres la llave de API en pantalla ni en consola.
- Pie de página: "AutoGuard AI · prototipo de hackathon · Datos simulados · las primas no son una oferta real".

=== CONTRATO DE LA API (exacto) ===
Auth: header "X-API-Key: <VITE_API_KEY>" en todo excepto /health. Errores FastAPI: {"detail": string | [{loc, msg, type}]}.

GET /health → {"ok": boolean, "auth": boolean, "llm": "mock" | "real"}

POST /expedientes  (multipart/form-data)
  docs: File[] (obligatorio, ≥1), fotos: File[] (opcional), tipos: string[] (opcional; si viene, mismo número que docs; valores factura | tarjeta_circulacion | poliza_anterior | otro), datos: string JSON (default "{}"), vehicle_id: string (opcional)
  → 200 {
    "vehicle_id": string,
    "perfil": VehicleProfile,
    "alertas": Alerta[],
    "documentos": DocExtraction[],
    "cotizacion": Prediction,
    "valuacion": Valuacion | null,
    "omitidos": {"visual"?: string, "valuacion"?: string},
    "tiempo_ms": number,
    "nota": "Datos SIMULADOS"
  }
  422 si no hay documentos, "datos" no es JSON objeto, o "tipos" es inválido.

GET /vehicles/{vehicle_id} → {"perfil": VehicleProfile, "documentos": DocExtraction[], "predicciones": Prediction[]}   (404 si no existe)

GET /patches?veredicto=&generation=&limit=&fuente=auto|db|run → {"fuente": "db" | "run", "patches": Patch[]}
  veredicto acepta "pendiente" (sin veredicto), "aceptado", "rechazado", "invalido".
POST /patches/{patch_id}/approve  body {"razon": string} (opcional) → {"patch": Patch, "version": AgentVersion}   (409 si es inválido, 422 si no aplica al campeón, 404 si no existe)
POST /patches/{patch_id}/reject   body {"razon": string} (opcional) → {"patch": Patch}

GET /versions/cotizador → {"agent": "cotizador", "versions": AgentVersion[]}   (la más reciente primero)
POST /versions/cotizador/revert/{sha} → {"version": AgentVersion}   (404 si el sha no existe)

Tipos:
type Severidad = "info" | "media" | "alta";
interface Alerta { codigo: string; severidad: Severidad; detalle: string; fuentes: string[] }
  // códigos posibles: VIN_FORMATO_INVALIDO, VIN_DIGITO_VERIFICADOR, VIN_NO_COINCIDE, PLACAS_NO_COINCIDEN, MARCA_NO_COINCIDE, MODELO_NO_COINCIDE, ANIO_NO_COINCIDE, VIGENCIA_ILEGIBLE, DOCUMENTO_VENCIDO, DOCUMENTO_FALTANTE, BAJA_CONFIANZA, DATO_DECLARADO_NO_COINCIDE, DATOS_INCOMPLETOS (trata cualquier otro como texto)
interface Dano { zona: string; tipo: string; costo_est: number; confianza: number }  // confianza 0–1
interface VehicleProfile { id: string; marca: string; modelo: string; anio: number; kilometraje: number; siniestros_previos: number; uso: "particular" | "app_transporte" | "comercial"; zona: "CDMX" | "EDOMEX" | "JAL" | "NL" | "PUE" | "OTRA"; danos: Dano[]; alertas: Alerta[]; cobertura_verificacion: number; vin: string | null; placas: string | null }
interface DocExtraction { documento_id: string; tipo: "factura" | "tarjeta_circulacion" | "poliza_anterior" | "otro"; vin: string | null; placas: string | null; marca: string | null; modelo: string | null; anio: number | null; vigencia: string | null; campos_extra: Record<string, unknown>; confianza: number }
interface QuoteOutput { prima: number; intervalo: [number, number]; factores: Record<string, number>; confianza: number }
interface Prediction { prediction_id: string; vehicle_id: string; agent: string; agent_version: string; input_hash: string; output: QuoteOutput; created_at: string }
interface Comparable { titulo?: string; precio: number; precio_ajustado: number; atipico: boolean; anio?: number; kilometraje?: number; url?: string; [k: string]: unknown }
interface Valuacion { precio_estimado: number; rango: [number, number]; comparables: Comparable[]; fuente: "mock" | "cache" | "tavily"; precio_mercado: number; descuento_danos: number; n_comparables: number; simulado: boolean }
interface ConfigChange { op: "set" | "add_rule" | "remove_rule" | "add_factor"; path: string; value: unknown }
interface Patch { patch_id: string; generation: number; agent: string; tipo: "ajuste_factor" | "nueva_variable" | "cambio_regla" | "cambio_prompt"; nivel: "parametros" | "estructura" | "codigo"; hipotesis: string; segmento: Record<string, unknown>; cambios: ConfigChange[]; diff: string; metrica_objetivo: string; veredicto: "aceptado" | "rechazado" | "invalido" | null; metrics_before: Record<string, number>; metrics_after: Record<string, number>; razon: string }
interface AgentVersion { id: string; agent: string; parent_id: string | null; git_sha: string; estado: "campeon" | "retador" | "sombra" | "retirado"; metrics: Record<string, number>; created_at: string }

Entrega en este primer paso las 4 pantallas funcionando contra la API, con el cliente api.ts, los tipos y un README corto que explique las variables VITE_API_URL, VITE_API_KEY y VITE_DASHBOARD_URL.
```

## 3. Iteraciones previstas (≤10, en este orden; saltar las que no hagan falta)

Cada una es un mensaje corto. Antes de mandarla, revisar si se arregla más barato editando en GitHub.

| # | Objetivo | Prompt corto |
| --- | --- | --- |
| 1 | Conexión real | "Prueba el flujo con la API real: si alguna llamada falla por CORS, nombre de campo o formato del multipart, corrígelo respetando el contrato del prompt inicial. No cambies el diseño." |
| 2 | Multipart y tipos | "Al enviar 3 documentos con tipo elegido, la API debe recibir 3 campos 'tipos' en el mismo orden; si alguno es 'Inferir', no mandes 'tipos'. Verifícalo y muestra el detail de un 422 en el formulario." |
| 3 | Expediente pulido | "En /expediente, prioriza visualmente: alertas altas arriba, luego Prima, Valuación y Daños. Haz que la prima y su intervalo se lean en 3 segundos." |
| 4 | Factores explicables | "En 'Factores que explican la prima', traduce los nombres técnicos a etiquetas legibles (uso → 'Uso del vehículo', siniestros_previos → 'Siniestros previos', etc.) y ordénalos por impacto |multiplicador−1|." |
| 5 | Bitácora del actuario | "En /parches, agrega una vista compacta de tabla en escritorio, conserva tarjetas en móvil y resalta en verde/rojo la diferencia de métricas antes/después." |
| 6 | Reversión | "En /versiones, tras revertir muestra cuál versión quedó en producción y un botón 'Probar cotización' que lleve a Nuevo expediente." |
| 7 | Responsive | "Revisa todas las pantallas a 375 px de ancho: sin scroll horizontal, tablas como tarjetas, botones al alcance del pulgar." |
| 8 | Demo de 40 s | "Agrega en Nuevo expediente un botón 'Cargar ejemplo' que explique qué archivos de muestra usar (EXP-001-FAC/TC/POL y FOTO-001) sin incluir archivos en el código." |
| 9 | Errores y vacíos | "Revisa estados de carga, error y vacío en las 4 pantallas; los errores deben decir qué hacer (reintentar, revisar llave, revisar API)." |
| 10 | Reserva | Guardar para un bug de último momento antes del pitch. |

## 4. Plan B si se acaban los créditos

1. **Editar en código**: el repo de GitHub conectado es la fuente de verdad. Clonar, `npm i && npm run dev`
   con un `.env.local` (`VITE_API_URL`, `VITE_API_KEY`, `VITE_DASHBOARD_URL`), corregir y hacer push: Lovable
   sincroniza solo. Los cambios pequeños (textos, colores, campos) siempre van por aquí, no por créditos.
2. **Desplegar fuera de Lovable**: el mismo repo es un proyecto Vite estático; se publica en Vercel/Netlify/
   GitHub Pages con las mismas variables. Agregar ese dominio a `AUTOGUARD_CORS_ORIGINS`.
3. **Llevar el frontend a Streamlit**: si Lovable vence o falla, agregar al tablero de T-15 una página
   "Expediente" (`st.file_uploader` múltiple → `POST /expedientes` con `requests`, mostrar perfil, alertas,
   daños, valuación y prima con `st.metric`/`st.dataframe`) y una página "Parches/Versiones" con botones de
   aprobar, rechazar y revertir. La API ya cubre todo; no hay que tocar backend.
4. **Último recurso para el pitch**: demo con `curl` / Swagger (`/docs` de FastAPI) y el video de respaldo (T-96).


## Alineación visual con el laboratorio RSI (T-30)

Usar una sola familia sans serif, fondo #f8faf9, paneles #eef2f1, texto #172b35 y acento #007f73.
Sin gradientes decorativos, emojis en títulos ni transparencias. Titular con el resultado real de la corrida;
mostrar «No alcanzada» cuando convergencia sea null. Etiqueta permanente «Datos simulados».
Variantes: Reglas fijas #64748b, Solo parámetros #b7791f, RSI completo #007f73.
Mantener estos nombres y colores en todas las gráficas. MXN con separador de miles, porcentajes con un decimal.
Orden: resultado RSI → curvas y parches aceptados → ciclo → historia de cambios → aprendizaje del bandido
→ garantías y versiones. Reversión exige confirmar versión y variante. Diseñar para proyector 1280×720.
