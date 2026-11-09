# Frontend de AutoGuard AI (local)

Sitio y app web de AutoGuard AI. Corre **solo en local** contra la API FastAPI del repo. Datos SIMULADOS.

## Correr

```bash
# 1) backend: API en :8000 (y tablero Streamlit en :8501), en modo simulado y sin llaves
bash scripts/demo.sh --start

# 2) frontend en :5173
cd frontend
npm install
npm run dev
```

Abre http://localhost:5173 (landing) y http://localhost:5173/app (la app).

Variables opcionales (archivo `frontend/.env.local`, nunca se sube):

| Variable | Default | Para qué |
| --- | --- | --- |
| `VITE_API_URL` | `http://localhost:8000` | URL de la API local |
| `VITE_API_KEY` | vacía | Solo si la API tiene `AUTOGUARD_API_KEY` (se manda como `X-API-Key`) |

`npm run build` compila y verifica tipos.

## Rutas

| Ruta | Pantalla | API |
| --- | --- | --- |
| `/` | Landing con la narrativa para México | — |
| `/app` | Resumen: estado de la API, última corrida RSI, actividad | `/health`, `/runs/latest`, `/patches` |
| `/app/expediente/nuevo` | Subir documentos y fotos de un auto | `POST /expedientes` |
| `/app/expediente/:id` | Perfil, alertas, daños, valuación y prima explicada | respuesta de `POST /expedientes` o `GET /vehicles/{id}` |
| `/app/siniestro` | Dictamen preliminar de un siniestro | `POST /dictamen/expediente` |
| `/app/laboratorio` | Curvas de regret de las 3 variantes y resumen del experimento | `GET /runs/latest?incluir_curva=true`, `POST /rsi/run` |
| `/app/parches` | Bitácora de parches con aprobar/rechazar | `GET /patches`, `POST /patches/{id}/approve|reject` |
| `/app/versiones` | Linaje del cotizador con reversión | `GET /versions/cotizador`, `POST /versions/cotizador/revert/{sha}` |

## Convenciones

- **Sistema de diseño:** tokens en `src/index.css` (tripletes RGB) y `tailwind.config.js`. Clases base: `btn-primary`,
  `btn-ghost`, `card`, `card-cream`, `eyebrow`, `chip`, `num`, `input`, `label`, `text-gradient`, `wrap`.
  Estilo claro y cálido: papel crema, tinta casi negra, acento taupe→arena. Tipografía Outfit (+ JetBrains Mono para cifras).
- **Componentes compartidos:** `src/components/ui.tsx` (Logo, SimBadge, SeverityBadge, Dot, PageHeader, Stat,
  Skeleton, ErrorState, EmptyState, useAsync, useToast, ConfirmDialog, Source).
- **API:** todo pasa por `src/lib/api.ts`; tipos en `src/lib/types.ts`; formatos es-MX en `src/lib/format.ts`.
- **Cifras de México:** solo en `src/data/mexico.ts`, cada una con fuente y fecha. Nada de cifras sin fuente.
- Toda pantalla muestra estados de carga, error (con "Reintentar") y vacío. Montos en MXN con `fmtMXN`.
- La marca es **AutoGuard AI** (propia). No usar logos, colores ni tipografías de Kavak u otras empresas.
