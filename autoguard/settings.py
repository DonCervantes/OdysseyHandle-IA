"""Carga de `.env` (T-22).

`import autoguard` llama a `load_env()`, así que la API, el loop RSI, el tablero y los scripts ven las
variables de `.env` de la raíz del repo sin hacer nada más. Las variables ya exportadas en el entorno
**ganan** (no se sobreescriben). Las llaves viven solo en `.env` (gitignored); este módulo nunca las
imprime ni las registra.

`AUTOGUARD_NO_DOTENV=1` desactiva la carga (lo usa `tests/conftest.py` para que la suite nunca vea
una llave real aunque exista `.env`).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
DOTENV_PATH = REPO_ROOT / ".env"

# Todas las variables de entorno que lee el código (mantener en sync con `.env.example`).
ENV_VARS: tuple[str, ...] = (
    # LLM (autoguard/llm.py)
    "OPENAI_API_KEY",
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_EFFORT",
    "LLM_CACHE",
    "LLM_CACHE_DIR",
    # Persistencia (autoguard/db/session.py, api, rsi/loop.py)
    "DATABASE_URL",
    # API (autoguard/api/services.py)
    "AUTOGUARD_API_KEY",
    "AUTOGUARD_CORS_ORIGINS",
    "AUTOGUARD_LINEAGE_DIR",
    "AUTOGUARD_RUNS_DIR",
    "AUTOGUARD_BASE_CONFIG",
    # Valuación de mercado (autoguard/agents/valuacion.py)
    "TAVILY_API_KEY",
    "FIRECRAWL_API_KEY",
    "VALUACION_OFFLINE",
    "VALUACION_CACHE_DIR",
)

# Variables con secretos o que habilitan red/BD externa: los tests las limpian.
SECRET_VARS: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",  # legado: se sigue limpiando por si quedó en un .env viejo
    "TAVILY_API_KEY",
    "FIRECRAWL_API_KEY",
    "AUTOGUARD_API_KEY",
    "DATABASE_URL",
)


def load_env(path: Optional[Path | str] = None) -> bool:
    """Carga `path` (por defecto `<repo>/.env`) sin sobreescribir variables ya exportadas.

    Devuelve True si se cargó un archivo. No hace nada si `AUTOGUARD_NO_DOTENV=1` o si el archivo no
    existe.
    """
    if os.getenv("AUTOGUARD_NO_DOTENV", "0").lower() in ("1", "true", "yes"):
        return False
    p = Path(path) if path is not None else DOTENV_PATH
    if not p.is_file():
        return False
    load_dotenv(p, override=False)
    return True
