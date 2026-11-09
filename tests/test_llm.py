"""Tests de autoguard/llm.py — sin red: modo mock y cliente falso inyectado."""
from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from autoguard import llm

FAKE_KEY = "sk-ant-test-NO-REAL-KEY-123456"
SCHEMA = {
    "type": "object",
    "required": ["vin", "anio"],
    "properties": {"vin": {"type": "string", "minLength": 17, "maxLength": 17},
                   "anio": {"type": "integer", "minimum": 1985}},
}
GOOD = '{"vin": "3VWFE21C04M000001", "anio": 2004}'
FB = {"fuente": "fallback"}


def _fallback():
    return dict(FB)


def _msg(text, stop="end_turn", extra_blocks=()):
    blocks = list(extra_blocks) + [SimpleNamespace(type="text", text=text)]
    return SimpleNamespace(content=blocks, stop_reason=stop)


class FakeClient:
    """Imita `client.beta.messages.create` con respuestas en cola."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    for v in ("LLM_PROVIDER", "ANTHROPIC_API_KEY", "LLM_MODEL", "LLM_EFFORT", "LLM_CACHE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "cache"))
    llm.set_client(None)
    yield
    llm.set_client(None)


def _inject(monkeypatch, *responses):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    fake = FakeClient(*responses)
    llm.set_client(fake)
    return fake


# ---------------------------------------------------------------- modo mock
def test_is_mock_without_key():
    assert llm.is_mock()


def test_is_mock_provider_flag(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    assert not llm.is_mock()
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    assert llm.is_mock()


def test_mock_returns_fallback_without_network(monkeypatch):
    def boom():
        raise AssertionError("no debe crear cliente en mock")

    monkeypatch.setattr(llm, "_get_client", boom)
    assert llm.complete_json("s", "u", fallback=_fallback) == FB


def test_mock_provider_ignores_injected_client(monkeypatch):
    fake = _inject(monkeypatch, _msg(GOOD))
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    assert llm.complete_json("s", "u", fallback=_fallback) == FB
    assert fake.calls == []


# ---------------------------------------------------------------- cliente falso
def test_success_with_schema_and_request_shape(monkeypatch):
    thinking = SimpleNamespace(type="thinking", thinking="")
    fake = _inject(monkeypatch, _msg("Claro:\n```json\n" + GOOD + "\n```", extra_blocks=[thinking]))
    out = llm.complete_json("sistema", "extrae", schema=SCHEMA, fallback=_fallback, max_tokens=1234)
    assert out == {"vin": "3VWFE21C04M000001", "anio": 2004}
    kw = fake.calls[0]
    assert kw["model"] == "claude-opus-5-5"
    assert kw["max_tokens"] == 1234 and kw["system"] == "sistema"
    assert kw["fallbacks"] == "default" and kw["betas"] == ["server-side-fallback-2026-07-01"]
    assert "thinking" not in kw and "temperature" not in kw
    assert "JSON Schema" in kw["messages"][0]["content"][-1]["text"]


def test_model_from_env_without_server_fallback(monkeypatch):
    fake = _inject(monkeypatch, _msg(GOOD))
    monkeypatch.setenv("LLM_MODEL", "claude-haiku-5-5")
    llm.complete_json("s", "u", fallback=_fallback)
    assert fake.calls[0]["model"] == "claude-haiku-5-5"
    assert "fallbacks" not in fake.calls[0] and "betas" not in fake.calls[0]


def test_images_as_base64_blocks(monkeypatch):
    fake = _inject(monkeypatch, _msg(GOOD))
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 10
    jpg = b"\xff\xd8\xff\xe0" + b"\x00" * 10
    pdf = b"%PDF-1.4 ..."
    llm.complete_json("s", "u", images=[png, jpg, pdf], fallback=_fallback)
    content = fake.calls[0]["messages"][0]["content"]
    assert [b["type"] for b in content] == ["image", "image", "document", "text"]
    assert content[0]["source"]["media_type"] == "image/png"
    assert content[1]["source"]["media_type"] == "image/jpeg"
    assert content[2]["source"]["media_type"] == "application/pdf"
    import base64

    assert base64.standard_b64decode(content[0]["source"]["data"]) == png


def test_unsupported_image_falls_back(monkeypatch):
    fake = _inject(monkeypatch, _msg(GOOD))
    assert llm.complete_json("s", "u", images=[b"garbage"], fallback=_fallback) == FB
    assert fake.calls == []


def test_retry_once_on_bad_json_then_ok(monkeypatch):
    fake = _inject(monkeypatch, _msg("no hay json aquí"), _msg(GOOD))
    assert llm.complete_json("s", "u", schema=SCHEMA, fallback=_fallback)["anio"] == 2004
    assert len(fake.calls) == 2


def test_schema_violation_twice_returns_fallback(monkeypatch):
    bad = '{"vin": "CORTO", "anio": 1900}'
    fake = _inject(monkeypatch, _msg(bad), _msg(bad), _msg(GOOD))
    assert llm.complete_json("s", "u", schema=SCHEMA, fallback=_fallback) == FB
    assert len(fake.calls) == 2  # 1 intento + 1 reintento, nunca más


def test_network_error_returns_fallback(monkeypatch):
    fake = _inject(monkeypatch, ConnectionError("down"), ConnectionError("down"))
    assert llm.complete_json("s", "u", fallback=_fallback) == FB
    assert len(fake.calls) == 2


def test_non_retryable_api_error_no_retry(monkeypatch):
    import anthropic
    import httpx2 as httpx

    req = httpx.Request("POST", "https://example.invalid/v1/messages")
    err = anthropic.AuthenticationError("bad key", response=httpx.Response(401, request=req), body=None)
    fake = _inject(monkeypatch, err, _msg(GOOD))
    assert llm.complete_json("s", "u", fallback=_fallback) == FB
    assert len(fake.calls) == 1


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_refusal_or_truncation_falls_back(monkeypatch, stop):
    _inject(monkeypatch, _msg(GOOD, stop=stop), _msg(GOOD, stop=stop))
    assert llm.complete_json("s", "u", fallback=_fallback) == FB


def test_never_logs_key(monkeypatch, caplog):
    _inject(monkeypatch, RuntimeError(f"auth header x-api-key: {FAKE_KEY}"), _msg("nada"))
    with caplog.at_level(logging.DEBUG, logger="autoguard.llm"):
        assert llm.complete_json("s", "u", fallback=_fallback) == FB
    assert caplog.records  # sí registró los fallos...
    assert FAKE_KEY not in caplog.text  # ...pero nunca la llave


# ---------------------------------------------------------------- caché
def test_disk_cache_hits_without_second_call(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_CACHE", "1")
    fake = _inject(monkeypatch, _msg(GOOD))
    a = llm.complete_json("s", "u", schema=SCHEMA, fallback=_fallback)
    b = llm.complete_json("s", "u", schema=SCHEMA, fallback=_fallback)
    assert a == b and len(fake.calls) == 1
    files = list((tmp_path / "cache").glob("*.json"))
    assert len(files) == 1 and FAKE_KEY not in files[0].read_text()


def test_cache_key_depends_on_request(monkeypatch):
    monkeypatch.setenv("LLM_CACHE", "1")
    fake = _inject(monkeypatch, _msg(GOOD), _msg(GOOD))
    llm.complete_json("s", "u1", fallback=_fallback)
    llm.complete_json("s", "u2", fallback=_fallback)
    assert len(fake.calls) == 2


def test_fallback_not_cached(monkeypatch):
    monkeypatch.setenv("LLM_CACHE", "1")
    fake = _inject(monkeypatch, _msg("x"), _msg("x"), _msg(GOOD))
    assert llm.complete_json("s", "u", fallback=_fallback) == FB
    assert llm.complete_json("s", "u", fallback=_fallback) == {"vin": "3VWFE21C04M000001", "anio": 2004}
    assert len(fake.calls) == 3


# ---------------------------------------------------------------- utilidades
def test_extract_json_variants():
    assert llm.extract_json('{"a": 1}') == {"a": 1}
    assert llm.extract_json('texto {"a": {"b": [1, 2]}} más') == {"a": {"b": [1, 2]}}
    assert llm.extract_json("```json\n{\"a\": 2}\n```") == {"a": 2}
    assert llm.extract_json('{ roto } y luego {"ok": true}') == {"ok": True}
    with pytest.raises(llm.LLMError):
        llm.extract_json("[1, 2]")


def test_validate_mini_schema():
    s = {"type": "object", "required": ["x"], "additionalProperties": False,
         "properties": {"x": {"type": "number"}, "t": {"enum": ["a", "b"]},
                        "l": {"type": "array", "items": {"type": "integer"}, "minItems": 1}}}
    assert llm.validate({"x": 1.5, "t": "a", "l": [1]}, s) == []
    assert llm.validate({"x": True}, s)  # bool no es number
    assert llm.validate({"t": "c"}, s)
    assert llm.validate({"x": 1, "l": ["a"]}, s)
    assert llm.validate({"x": 1, "zz": 0}, s)
