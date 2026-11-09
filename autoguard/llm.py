"""Cliente LLM único del proyecto (T-01).

Contrato: si no hay ANTHROPIC_API_KEY o LLM_PROVIDER=mock, NO se llama a la red y se devuelve
`fallback()`; así todo el sistema (y los tests) corre sin llaves y de forma reproducible.

Variables de entorno:
- `LLM_PROVIDER`: "auto" (default) | "mock".
- `ANTHROPIC_API_KEY`: llave (solo en `.env`; NUNCA se loguea).
- `LLM_MODEL`: modelo (default `claude-opus-5-5`).
- `LLM_EFFORT`: low | medium | high | xhigh | max (default `low`: tareas cortas de extracción/redacción).
- `LLM_CACHE`: "1" activa caché en disco por hash de la petición.
- `LLM_CACHE_DIR`: directorio de caché (default `var/llm_cache/`).

Tests: `set_client(fake)` inyecta un cliente falso (cualquier objeto con `.beta.messages.create(**kw)`)
y evita la red; `set_client(None)` lo quita. El modo mock (sin llave o LLM_PROVIDER=mock) manda siempre:
ni un cliente inyectado se usa sin ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "low"
DEFAULT_CACHE_DIR = "var/llm_cache"
MAX_ATTEMPTS = 2  # 1 intento + 1 reintento

# Modelos que aceptan el fallback del lado del servidor ante `refusal`.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_FALLBACK_MODELS = {"claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}

_client: Any = None  # cliente inyectado (tests) o creado perezosamente


class LLMError(RuntimeError):
    """Error de llamada/parseo/validación; siempre termina en `fallback()`."""


def is_mock() -> bool:
    """True si el LLM está en modo mock (sin llave o LLM_PROVIDER=mock)."""
    return os.getenv("LLM_PROVIDER", "auto") == "mock" or not os.getenv("ANTHROPIC_API_KEY")


def set_client(client: Any) -> None:
    """Inyecta un cliente (p.ej. falso en tests). `None` vuelve al cliente real perezoso."""
    global _client
    _client = client


def _get_client() -> Any:
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic(max_retries=2, timeout=120.0)
    return _client


# ---------------------------------------------------------------- contenido
def _media_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF"):
        return "application/pdf"
    raise LLMError("formato de imagen no soportado (png/jpeg/gif/webp/pdf)")


def _content_blocks(user: str, images: Optional[list[bytes]], schema: Optional[dict[str, Any]]) -> list[dict]:
    blocks: list[dict] = []
    for img in images or []:
        mt = _media_type(img)
        src = {"type": "base64", "media_type": mt, "data": base64.standard_b64encode(img).decode("ascii")}
        blocks.append({"type": "document" if mt == "application/pdf" else "image", "source": src})
    text = user
    if schema:
        text += (
            "\n\nResponde SOLO con un objeto JSON válido (sin texto adicional) que cumpla este JSON Schema:\n"
            + json.dumps(schema, ensure_ascii=False, sort_keys=True)
        )
    else:
        text += "\n\nResponde SOLO con un objeto JSON válido, sin texto adicional."
    blocks.append({"type": "text", "text": text})
    return blocks


# ---------------------------------------------------------------- parseo
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> dict[str, Any]:
    """Extrae el primer objeto JSON de `text` (tolera ```json fences y texto alrededor)."""
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    dec = json.JSONDecoder()
    for cand in candidates:
        cand = cand.strip()
        for i, ch in enumerate(cand):
            if ch != "{":
                continue
            try:
                obj, _ = dec.raw_decode(cand, i)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                return obj
    raise LLMError("la respuesta no contiene un objeto JSON")


# ---------------------------------------------------------------- validación (jsonschema-lite)
_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,), "array": (list,), "string": (str,), "boolean": (bool,),
    "integer": (int,), "number": (int, float), "null": (type(None),),
}


def validate(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Validador mínimo de JSON Schema: type, enum, const, required, properties,
    additionalProperties=false, items, minimum/maximum, minLength/maxLength, minItems/maxItems.
    Devuelve la lista de errores (vacía = válido)."""
    errs: list[str] = []
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        ok = False
        for tt in types:
            py = _TYPES.get(tt)
            if py is None:
                continue
            if isinstance(value, bool) and tt in ("integer", "number"):
                continue
            if isinstance(value, py) or (tt == "integer" and isinstance(value, float) and value.is_integer()):
                ok = True
                break
        if not ok:
            return [f"{path}: se esperaba {t}, llegó {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: {value!r} no está en {schema['enum']}")
    if "const" in schema and value != schema["const"]:
        errs.append(f"{path}: se esperaba {schema['const']!r}")
    if isinstance(value, dict):
        for k in schema.get("required", []):
            if k not in value:
                errs.append(f"{path}: falta '{k}'")
        props = schema.get("properties", {})
        for k, v in value.items():
            if k in props:
                errs += validate(v, props[k], f"{path}.{k}")
            elif schema.get("additionalProperties") is False:
                errs.append(f"{path}: propiedad no permitida '{k}'")
    if isinstance(value, list):
        if "items" in schema:
            for i, v in enumerate(value):
                errs += validate(v, schema["items"], f"{path}[{i}]")
        if "minItems" in schema and len(value) < schema["minItems"]:
            errs.append(f"{path}: menos de {schema['minItems']} elementos")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append(f"{path}: más de {schema['maxItems']} elementos")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append(f"{path}: {value} < {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errs.append(f"{path}: {value} > {schema['maximum']}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errs.append(f"{path}: longitud < {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errs.append(f"{path}: longitud > {schema['maxLength']}")
    return errs


# ---------------------------------------------------------------- caché
def _cache_enabled() -> bool:
    return os.getenv("LLM_CACHE", "0").lower() in ("1", "true", "yes")


def _cache_key(model: str, system: str, user: str, images: Optional[list[bytes]],
               schema: Optional[dict[str, Any]], max_tokens: int) -> str:
    h = hashlib.sha256()
    payload = {
        "model": model, "system": system, "user": user, "schema": schema, "max_tokens": max_tokens,
        "effort": os.getenv("LLM_EFFORT", DEFAULT_EFFORT),
        "images": [hashlib.sha256(i).hexdigest() for i in images or []],
    }
    h.update(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode())
    return h.hexdigest()


def _cache_path(key: str) -> Path:
    return Path(os.getenv("LLM_CACHE_DIR", DEFAULT_CACHE_DIR)) / f"{key}.json"


def _cache_get(key: str) -> Optional[dict[str, Any]]:
    p = _cache_path(key)
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except (OSError, json.JSONDecodeError):
        return None


def _cache_put(key: str, value: dict[str, Any]) -> None:
    p = _cache_path(key)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value, ensure_ascii=False))
    except OSError as e:  # la caché es opcional
        log.warning("no se pudo escribir caché LLM: %s", type(e).__name__)


# ---------------------------------------------------------------- llamada
def _response_text(resp: Any) -> str:
    stop = getattr(resp, "stop_reason", None)
    if stop == "refusal":
        raise LLMError("el modelo rechazó la petición (refusal)")
    if stop == "max_tokens":
        raise LLMError("respuesta truncada (max_tokens)")
    parts = [getattr(b, "text", "") for b in getattr(resp, "content", []) or [] if getattr(b, "type", None) == "text"]
    text = "".join(parts).strip()
    if not text:
        raise LLMError("respuesta sin texto")
    return text


def _call(client: Any, model: str, system: str, content: list[dict], max_tokens: int) -> str:
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": content}],
        "output_config": {"effort": os.getenv("LLM_EFFORT", DEFAULT_EFFORT)},
    }
    if model in _FALLBACK_MODELS:
        kwargs["betas"] = [_FALLBACK_BETA]
        kwargs["fallbacks"] = "default"
    return _response_text(client.beta.messages.create(**kwargs))


def _non_retryable(exc: Exception) -> bool:
    try:
        import anthropic
    except ImportError:  # pragma: no cover
        return False
    return isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError,
                            anthropic.NotFoundError, anthropic.BadRequestError))


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
    error de red/parseo/validación (tras 1 reintento), devuelve `fallback()`."""
    # Siempre se respeta el modo mock, aunque haya un cliente (real o inyectado) retenido.
    if is_mock():
        return fallback()

    model = os.getenv("LLM_MODEL", DEFAULT_MODEL)
    use_cache = _cache_enabled()
    key = _cache_key(model, system, user, images, schema, max_tokens) if use_cache else ""
    if use_cache:
        cached = _cache_get(key)
        if cached is not None and not (schema and validate(cached, schema)):
            return cached

    try:
        content = _content_blocks(user, images, schema)
        client = _get_client()
    except Exception as e:  # noqa: BLE001 — cualquier fallo de preparación → fallback
        log.warning("LLM no disponible (%s); usando fallback", type(e).__name__)
        return fallback()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            data = extract_json(_call(client, model, system, content, max_tokens))
            if schema:
                errs = validate(data, schema)
                if errs:
                    raise LLMError("JSON no cumple el schema: " + "; ".join(errs[:5]))
            if use_cache:
                _cache_put(key, data)
            return data
        except Exception as e:  # noqa: BLE001
            # Solo el tipo y un mensaje propio: nunca se loguean cabeceras ni la llave.
            msg = str(e) if isinstance(e, LLMError) else type(e).__name__
            log.warning("LLM intento %d/%d falló: %s", attempt, MAX_ATTEMPTS, msg)
            if _non_retryable(e):
                break
    return fallback()
