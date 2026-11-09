"""Cliente LLM único del proyecto. [STUB — tarea T-01]

Contrato: si no hay ANTHROPIC_API_KEY o LLM_PROVIDER=mock, NO se llama a la red y se devuelve
`fallback()`; así todo el sistema (y los tests) corre sin llaves y de forma reproducible.
"""
from __future__ import annotations

from typing import Any, Callable, Optional


def is_mock() -> bool:
    """True si el LLM está en modo mock (sin llave o LLM_PROVIDER=mock)."""
    import os

    return os.getenv("LLM_PROVIDER", "auto") == "mock" or not os.getenv("ANTHROPIC_API_KEY")


def complete_json(
    system: str,
    user: str,
    *,
    images: Optional[list[bytes]] = None,
    schema: Optional[dict[str, Any]] = None,
    fallback: Callable[[], dict[str, Any]],
    max_tokens: int = 2000,
) -> dict[str, Any]:
    """Pide al LLM una respuesta JSON (validada contra `schema` si se da). En modo mock o ante
    error de red/parseo, devuelve `fallback()`. T-01 implementa la llamada real."""
    return fallback()
