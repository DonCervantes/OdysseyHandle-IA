"""T-16: los workflows de n8n en `n8n/` son JSON importables, consistentes con la API y sin secretos.
Sin red: solo se inspeccionan los archivos y las rutas registradas en `create_app`."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from autoguard.api.main import create_app
from autoguard.api.services import Settings

N8N = Path(__file__).resolve().parents[1] / "n8n"
FILES = sorted(N8N.glob("*.json"))
BASE = "={{ $env.AUTOGUARD_API_URL }}"

SECRET_PATTERNS = [
    re.compile(r"sk-(ant-)?[A-Za-z0-9_\-]{16,}"),          # Anthropic / OpenAI
    re.compile(r"tvly-[A-Za-z0-9]{16,}"),                  # Tavily
    re.compile(r"fc-[A-Za-z0-9]{16,}"),                    # Firecrawl
    re.compile(r"AKIA[0-9A-Z]{16}"),                       # AWS
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),             # GitHub
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),          # Slack
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),                # Google
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\."),  # JWT
    re.compile(r"https?://[^\s\"/]+:[^\s\"@/]+@"),        # credenciales en URL
]
SECRET_KEYS = re.compile(r"(api[_-]?key|x-api-key|password|secret|token|authorization)", re.I)


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _walk(x, key=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _walk(v, k)
    elif isinstance(x, list):
        for v in x:
            yield from _walk(v, key)
    else:
        yield key, x


@pytest.fixture(scope="module")
def routes(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("n8n")
    app = create_app(Settings(api_key="x", database_url=f"sqlite:///{tmp / 'a.db'}",
                              lineage_dir=tmp / "lin", runs_dir=tmp / "runs"), rsi_runner=lambda p: p)
    out = []
    for ruta, ops in app.openapi()["paths"].items():
        rx = re.compile("^" + re.sub(r"\\\{[^/]+?\\\}", "[^/]+", re.escape(ruta)) + "$")
        out += [(m.upper(), rx) for m in ops]
    return out


def test_hay_cuatro_workflows():
    assert len(FILES) == 4, [f.name for f in FILES]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_estructura_y_conexiones(path):
    wf = _load(path)
    assert wf["name"] and isinstance(wf["nodes"], list) and isinstance(wf["connections"], dict)
    names = [n["name"] for n in wf["nodes"]]
    ids = [n["id"] for n in wf["nodes"]]
    assert len(set(names)) == len(names) and len(set(ids)) == len(ids)
    for n in wf["nodes"]:
        assert {"id", "name", "type", "typeVersion", "position", "parameters"} <= n.keys(), n.get("name")
        assert n["type"].startswith("n8n-nodes-base.")
        assert len(n["position"]) == 2
    for src, outs in wf["connections"].items():
        assert src in names, f"conexión desde nodo inexistente: {src}"
        for branch in outs["main"]:
            for c in branch:
                assert c["node"] in names, f"{src} -> nodo inexistente {c['node']}"
    # todo nodo que no sea trigger tiene una entrada
    destinos = {c["node"] for o in wf["connections"].values() for b in o["main"] for c in b}
    for n in wf["nodes"]:
        if not n["type"].endswith(("webhook", "scheduleTrigger")):
            assert n["name"] in destinos, f"nodo huérfano: {n['name']}"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_rutas_existen_en_api_y_usan_credencial(path, routes):
    wf = _load(path)
    http = [n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.httpRequest"]
    assert http
    for n in http:
        p = n["parameters"]
        assert p["url"].startswith(BASE), f"{n['name']}: la URL base debe venir de $env.AUTOGUARD_API_URL"
        ruta = re.sub(r"\{\{.*?\}\}", "X", p["url"][len(BASE):])
        metodo = p.get("method", "GET")
        assert any(m == metodo and rx.match(ruta) for m, rx in routes), f"{metodo} {ruta} no existe en la API"
        assert p["authentication"] == "genericCredentialType" and p["genericAuthType"] == "httpHeaderAuth"
        assert "httpHeaderAuth" in n["credentials"]
        assert not p.get("sendHeaders"), "la API key va en la credencial Header Auth, no en headers"


def test_aprobacion_cubre_approve_y_reject():
    wf = _load(N8N / "04_aprobacion_actuario.json")
    urls = [n["parameters"].get("url", "") for n in wf["nodes"]]
    assert any(u.endswith("/approve") for u in urls) and any(u.endswith("/reject") for u in urls)
    tipos = {n["type"] for n in wf["nodes"]}
    assert {"n8n-nodes-base.wait", "n8n-nodes-base.emailSend", "n8n-nodes-base.if"} <= tipos
    wait = next(n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.wait")
    assert wait["parameters"]["resume"] == "webhook"


@pytest.mark.parametrize("path", [*FILES, N8N / "README.md"], ids=lambda p: p.name)
def test_sin_secretos(path):
    txt = path.read_text(encoding="utf-8")
    for rx in SECRET_PATTERNS:
        assert not rx.search(txt), f"posible secreto en {path.name}: {rx.pattern}"
    if path.suffix == ".json":
        for key, val in _walk(_load(path)):
            if SECRET_KEYS.search(str(key)) and isinstance(val, str) and val:
                assert val.startswith("={{"), f"{path.name}: valor literal en campo sensible {key!r}"
