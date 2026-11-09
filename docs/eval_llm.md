# Evaluación con LLM real (T-28)

Script CLI para medir, **con llave de OpenAI**, la precisión de extracción documental y el recall de daños sobre muestras **SIMULADAS**. No forma parte de `pytest` (la suite nunca llama a la red).

## Metas

| Métrica | Meta | Fuente |
| --- | --- | --- |
| Precisión de extracción documental (campos VIN, placas, marca, modelo, año, vigencia) | ≥ 90 % | plan de trabajo |
| Recall de daños `(zona, tipo)` en fotos | ≥ 80 % | plan de trabajo |

## Datos

Todos los casos están etiquetados como **SIMULADOS** (no son personas ni autos reales):

- Existentes: `data/samples/docs/`, `data/samples/fotos/`
- Extra T-28: `data/eval/docs/`, `data/eval/fotos/` (+ `data/eval/manifest.json`)

Regenerar solo el set extra:

```bash
python scripts/eval_llm.py --generate
```

(`--generate` no exige llave.)

## Cómo correr

### Sin llave

```bash
python scripts/eval_llm.py
```

Sale con código **2** y un mensaje claro pidiendo `OPENAI_API_KEY` (vía `.env` o el entorno). No inventa métricas en mock.

### Con llave

```bash
# .env en la raíz del repo (gitignored), o:
# export OPENAI_API_KEY=...
python scripts/eval_llm.py
```

El script:

1. Activa `LLM_CACHE=1` (caché en `var/llm_cache/` o `LLM_CACHE_DIR`).
2. Evalúa documentos de `data/samples/docs` + `data/eval/docs` con `autoguard.agents.documental.extract`.
3. Evalúa fotos de `data/samples/fotos` + `data/eval/fotos` con `autoguard.agents.visual.inspect` **sin hints** (un fallo del LLM no cae al ground truth).
4. Reporta precisión global, recall, tokens (API + cache hits) y **costo USD estimado**.
5. Código de salida: **0** si cumple ambas metas, **1** si no, **2** sin llave.

JSON completo:

```bash
python scripts/eval_llm.py --json
```

### Costo estimado

- Si la API devuelve `usage`, se usan `input_tokens` / `output_tokens` reales.
- Si no, se estima (~4 chars/token de texto + ~1600 tok/imagen).
- Precio de referencia (USD / millón de tokens): `LLM_PRICE_IN` (default 2) y `LLM_PRICE_OUT` (default 10), tarifas publicadas de `gpt-6.1-sol` al 2026-11-09. Es una estimación de laboratorio, no una factura.

## Tests y red

- `tests/conftest.py` fuerza `LLM_PROVIDER=mock`, limpia `OPENAI_API_KEY` y pone `AUTOGUARD_NO_DOTENV=1`.
- Este script **no** se importa desde tests; es solo CLI manual/demo.
- Los agentes documental/visual ya tienen `--eval` en mock (100 %); este script es el chequeo con LLM real + set ampliado.

## Resultado medido (2026-11-10, LLM real)

Primera corrida con OpenAI `gpt-6.1-sol` (effort `low`, `LLM_CACHE=1`), 24 llamadas reales a la API, sin
aciertos de caché; tokens reportados por la API (no estimados).

| Métrica | Resultado | Meta |
| --- | --- | --- |
| Precisión de extracción documental (15 docs, 80 campos: VIN, placas, marca, modelo, año, vigencia) | **100.0%** | ≥ 90% |
| Recall de daños en fotos (9 fotos; tp=15, fn=0, fp=0) | **100.0%** (precisión 100.0%) | ≥ 80% |
| Tokens | 20,882 entrada · 2,427 salida | — |
| Costo estimado | **USD 0.066** | — |
| Tiempo | ~73 s | — |

**Límite honesto:** las muestras son imágenes SIMULADAS generadas por código (documentos renderizados limpios y
fotos esquemáticas), mucho más fáciles que fotos y escaneos reales. El resultado prueba que la integración con el
LLM real funciona de punta a punta y cumple las metas en este set; no es una estimación del desempeño con
documentos reales. Repetir la corrida es gratis mientras exista la caché en `var/llm_cache/`.
