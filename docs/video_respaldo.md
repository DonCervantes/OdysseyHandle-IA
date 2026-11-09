# Video de respaldo · AUTOGUARD AI · 3 minutos

Datos SIMULADOS. Narración lista para ElevenLabs; copiar solamente los párrafos de voz.
Pronunciar «RSI» como «erre ese i», «AI» como «a i» y «Kavak» como «cávac».
Grabar a 1280×720 o 1920×1080; dejar visible «Datos simulados». Sin llaves, terminales con secretos ni .env.
El tiempo es una pauta de edición: medir la locución generada y ajustar silencios, no acelerar cifras.

## Preparación

Ejecutar `bash scripts/demo.sh --start`. Elegir demo-seed42. Verificar en summary.json:
regret estático 51,312,336 MXN; parámetros 44,014,125 MXN; RSI 36,727,792 MXN;
reducción 28.4%, 12,000 pólizas por variante, 20 generaciones. Gate 2 false, convergencia estricta null.
Si cambian artefactos, actualizar locución y rótulos antes de grabar. No superponer cifras antiguas.
EXP-002 + FOTO-002 muestran discrepancia de VIN y daños. Preparar la carga antes de empezar a grabar.

## Guion de tomas y voz

### 0:00–0:25 · El problema

**Toma:** expediente simulado, documentos y fotos; después prima con factores. Si Lovable no está
operativo, usar Swagger /expedientes y recortar a los campos legibles, sin fingir que existe un frontend.

**Voz:**
Comprar un auto seminuevo implica revisar documentos, detectar daños y estimar su riesgo.
Pero automatizar una cotización no basta. Si sus reglas se equivocan, repetirlas más rápido también
repite el error. Autoguard conecta la revisión del vehículo con un sistema que aprende de sus resultados.
Esta demostración utiliza datos simulados.

### 0:25–0:55 · Cómo funciona

**Toma:** alertas, daños, prima explicable y diagrama del ciclo en el tablero.

**Voz:**
Los agentes revisan documentos y fotografías. El cotizador explica qué factores modifican la prima.
Después, el ciclo erre ese i observa resultados, identifica segmentos con errores y propone cambios.
Un evaluador congelado compara cada propuesta con la versión actual. Solo admite mejoras que cumplen
sus criterios y controles por segmento. Cada cambio aceptado queda registrado como una nueva versión.

### 0:55–1:35 · Demo de 40 segundos

**Toma y acciones:** seguir docs/demo.md. En 0–8 s cargar EXP-002; en 8–12 s pasar al tablero;
reproducir a 2×; señalar las curvas y marcadores; abrir un parche aceptado; apagar reproducción;
abrir «Versiones y garantías», seleccionar el padre del campeón, marcar confirmación y revertir.
La reversión conserva las curvas originales. Para repetir la toma, regenerar la corrida o trabajar con una copia.

**Voz:**
Este expediente muestra una discrepancia entre documentos y daños visibles.
Aquí comparamos tres cotizadores sobre los mismos autos: reglas fijas, solo parámetros y erre ese i completo.
La pérdida fluctúa, pero el sistema completo acumula menos regret.
En doce mil cotizaciones, lo reduce un veintiocho coma cuatro por ciento frente a reglas fijas.
Cada marcador corresponde a un cambio aceptado. Podemos abrir su hipótesis, sus métricas y su motivo.
Y podemos restaurar una versión anterior sin borrar la historia.

### 1:35–2:05 · Aprende a mejorar

**Toma:** pestaña «Aprende a mejorar»: posteriors por brazo, tasa de aceptación y lecciones.

**Voz:**
El sistema también aprende qué cambios conviene intentar. El meta-mejorador actualiza su preferencia
por ajustar factores, incorporar variables o cambiar reglas según los resultados observados.
Esta gráfica muestra sus posteriors, no una garantía de éxito. La bitácora incluye rechazos: una propuesta
que parece prometedora puede fallar en el conjunto reservado. Esa evidencia alimenta la siguiente generación.

### 2:05–2:35 · Resultados y límites

**Toma:** resultado de la corrida, Gate 2 «No cumple», tabla de cuatro semillas en README.

**Voz:**
Probamos cuatro semillas y observamos reducciones de regret entre veinticinco coma nueve y veintinueve
coma dos por ciento. No alcanzamos la meta original del cuarenta por ciento ni la convergencia estricta.
El ruido del simulador y los controles del evaluador limitan la mejora. Son resultados de laboratorio,
no tarifas para clientes. La extracción con modelos reales todavía necesita su evaluación independiente.

### 2:35–3:00 · Garantías y siguiente paso

**Toma:** garantías, historial Git y cierre con nombre del proyecto. Dejar 2–3 s finales sin voz.

**Voz:**
El evaluador mantiene sus reglas. El mejorador no ve el conjunto reservado y solo usa variables permitidas.
Las versiones permiten rastrear y revertir cada cambio. El siguiente paso es validar este mecanismo con
información real y supervisión experta. Autoguard demuestra una idea concreta: un sistema que mejora sus
cotizaciones y aprende de la evidencia qué mejoras vale la pena intentar.

## Archivos y plan B

- Grabar: expediente, resultado RSI, reproducción completa, parche aceptado, reversión, bandido y garantías.
- Exportar MP4 H.264, audio AAC; subtítulos en español y copia local/USB/teléfono.
- El bloque de demo empieza en **00:55**. Verificar ese marcador en el montaje final.
- Para respaldo sin ejecutar RSI, copiar los cinco artefactos CSV/JSON/JSONL de una corrida real a
  data/demo_run/. Sin configs Git, narrar el historial y usar la toma grabada de reversión.
- Este archivo entrega guion y narración. Generar audio, grabar y ensayar corresponde a T-96/humano;
  no se ha producido un video ni se ha enviado texto a ElevenLabs.
