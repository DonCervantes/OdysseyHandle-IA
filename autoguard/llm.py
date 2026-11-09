"""Cliente LLM único del proyecto (T-01; proveedor OpenAI desde T-31).

Contrato: si no hay OPENAI_API_KEY o LLM_PROVIDER=mock, NO se llama a la red y se devuelve
`fallback()`; así todo el sistema (y los tests) corre sin llaves y de forma reproducible.

Proveedor: OpenAI Responses API (`client.responses.create`). Modelo por defecto `gpt-6.1-sol`
(recomendado por OpenAI como balance calidad/costo; entrada de texto e imagen, salidas estructuradas y
esfuerzo de razonamiento). Los PDF se envían como `input_file` en base64 (modelos con visión).
Fuente: https://developers.openai.com/api/docs/models y /api/docs/quickstart (consultadas 2026-11-09).

Variables de entorno:
- `LLM_PROVIDER`: "auto" (default) | "mock".
- `OPENAI_API_KEY`: llave (solo en `.env`; NUNCA se loguea).
- `LLM_MODEL`: modelo (default `gpt-6.1-sol`).
- `LLM_EFFORT`: esfuerzo de razonamiento low | medium | high (default `low`: extracción/redacción corta).
- `LLM_CACHE`: "1" activa caché en disco por hash de la petición.
- `LLM_CACHE_DIR`: directorio de caché (default `var/llm_cache/`).

Tests: `set_client(fake)` inyecta un cliente falso (cualquier objeto con `.responses.create(**kw)`)
y evita la red; `set_client(None)` lo quita. El modo mock (sin llave o LLM_PROVIDER=mock) manda siempre:
ni un cliente inyectado se usa sin OPENAI_API_KEY.
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

DEFAULT_MODEL = "gpt-6.1-sol"
DEFAULT_EFFORT = "low"
DEFAULT_CACHE_DIR = "var/llm_cache"
MAX_ATTEMPTS = 2  # 1 intento + 1 reintento
# Los tokens de razonamiento cuentan contra `max_output_tokens`: se suma holgura para que el JSON no se trunque.
REASONING_HEADROOM = 2000
KEY_ENV = "OPENAI_API_KEY"

_client: Any = None  # cliente inyectado (tests) o creado perezosamente


class LLMError(RuntimeError):
    """Error de llamada/parseo/validación; siempre termina en `fallback()`."""


def is_mock() -> bool:
    """True si el LLM está en modo mock (sin llave o LLM_PROVIDER=mock)."""
    return os.getenv("LLM_PROVIDER", "auto") == "mock" or not os.getenv(KEY_ENV)


def set_client(client: Any) -> None:
    """Inyecta un cliente (p.ej. falso en tests). `None` vuelve al cliente real perezoso."""
    global _client
    _client = client


def _get_client() -> Any:
    global _client
    if _client is None:
        import openai

        _client = openai.OpenAI(max_retries=2, timeout=120.0)
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
    """Contenido del mensaje de usuario en formato Responses API: imágenes como `input_image` (data URL),
    PDF como `input_file` (data URL) y al final el texto con la instrucción de responder en JSON."""
    blocks: list[dict] = []
    for i, img in enumerate(images or []):
        mt = _media_type(img)
        url = f"data:{mt};base64," + base64.standard_b64encode(img).decode("ascii")
        if mt == "application/pdf":
            blocks.append({"type": "input_file", "filename": f"documento_{i + 1}.pdf", "file_data": url})
        else:
            blocks.append({"type": "input_image", "image_url": url})
    text = user
    if schema:
        text += (
            "\n\nResponde SOLO con un objeto JSON válido (sin texto adicional) que cumpla este JSON Schema:\n"
            + json.dumps(schema, ensure_ascii=False, sort_keys=True)
        )
    else:
        text += "\n\nResponde SOLO con un objeto JSON válido, sin texto adicional."
    blocks.append({"type": "input_text", "text": text})
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
        "provider": "openai", "model": model, "system": system, "user": user, "schema": schema,
        "max_tokens": max_tokens,
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
    """Texto de una respuesta de la Responses API; error si está incompleta, rechazada o vacía."""
    if getattr(resp, "status", None) == "incomplete":
        reason = getattr(getattr(resp, "incomplete_details", None), "reason", None)
        raise LLMError(f"respuesta incompleta ({reason or 'sin motivo'})")
    parts: list[str] = []
    for item in getattr(resp, "output", None) or []:
        for c in getattr(item, "content", None) or []:
            ctype = getattr(c, "type", None)
            if ctype == "refusal":
                raise LLMError("el modelo rechazó la petición (refusal)")
            if ctype == "output_text":
                parts.append(getattr(c, "text", "") or "")
    text = (getattr(resp, "output_text", None) or "".join(parts)).strip()
    if not text:
        raise LLMError("respuesta sin texto")
    return text


def build_request(model: str, system: str, content: list[dict], max_tokens: int) -> dict[str, Any]:
    """Argumentos de `client.responses.create`. JSON mode (`json_object`) y validación local contra el
    schema: los schemas del proyecto no siempre cumplen el modo `strict` de Structured Outputs."""
    return {
        "model": model,
        "instructions": system,
        "input": [{"role": "user", "content": content}],
        "max_output_tokens": max_tokens + REASONING_HEADROOM,
        "reasoning": {"effort": os.getenv("LLM_EFFORT", DEFAULT_EFFORT)},
        "text": {"format": {"type": "json_object"}},
    }


def _call(client: Any, model: str, system: str, content: list[dict], max_tokens: int) -> str:
    return _response_text(client.responses.create(**build_request(model, system, content, max_tokens)))


def _non_retryable(exc: Exception) -> bool:
    try:
        import openai
    except ImportError:  # pragma: no cover
        return False
    return isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError,
                            openai.NotFoundError, openai.BadRequestError))


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
