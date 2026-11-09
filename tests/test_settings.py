"""T-22: carga de `.env` y aislamiento de la suite."""

import os
import re
from pathlib import Path

import autoguard
from autoguard import llm, settings

REPO = Path(__file__).resolve().parents[1]


def _env_file(tmp_path: Path) -> Path:
    p = tmp_path / ".env"
    p.write_text("T22_DESDE_DOTENV=archivo\nT22_EXPORTADA=archivo\n", encoding="utf-8")
    return p


def test_carga_dotenv_y_exportada_gana(tmp_path, monkeypatch):
    monkeypatch.delenv("AUTOGUARD_NO_DOTENV", raising=False)
    monkeypatch.delenv("T22_DESDE_DOTENV", raising=False)
    monkeypatch.setenv("T22_EXPORTADA", "shell")
    try:
        assert settings.load_env(_env_file(tmp_path)) is True
        assert os.environ["T22_DESDE_DOTENV"] == "archivo"
        assert os.environ["T22_EXPORTADA"] == "shell"  # no se sobreescribe
    finally:
        os.environ.pop("T22_DESDE_DOTENV", None)


def test_no_dotenv_desactiva_carga(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOGUARD_NO_DOTENV", "1")
    monkeypatch.delenv("T22_DESDE_DOTENV", raising=False)
    assert settings.load_env(_env_file(tmp_path)) is False
    assert "T22_DESDE_DOTENV" not in os.environ


def test_archivo_inexistente(tmp_path, monkeypatch):
    monkeypatch.delenv("AUTOGUARD_NO_DOTENV", raising=False)
    assert settings.load_env(tmp_path / "no-existe.env") is False


def test_default_es_raiz_del_repo():
    assert settings.DOTENV_PATH == REPO / ".env"
    assert Path(autoguard.__file__).resolve().parent.parent == REPO


def test_suite_en_modo_mock_aunque_haya_dotenv():
    # conftest.py: sin .env, sin llaves, LLM forzado a mock y valuación offline.
    assert os.environ.get("AUTOGUARD_NO_DOTENV") == "1"
    assert os.environ.get("LLM_PROVIDER") == "mock"
    assert not os.environ.get("ANTHROPIC_API_KEY")
    assert not os.environ.get("TAVILY_API_KEY")
    assert llm.is_mock()


def test_env_example_lista_todas_las_variables():
    texto = (REPO / ".env.example").read_text(encoding="utf-8")
    declaradas = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", texto, flags=re.M))
    assert declaradas == set(settings.ENV_VARS)
    assert not re.search(r"^(ANTHROPIC|TAVILY|FIRECRAWL)_API_KEY=.+", texto, flags=re.M)  # sin llaves


def test_env_vars_cubre_lo_que_lee_el_codigo():
    patron = re.compile(r"""(?:os\.getenv|os\.environ\.get|os\.environ\[|\bp)\(?\s*['"]([A-Z][A-Z0-9_]+)['"]""")
    leidas: set[str] = set()
    for f in (REPO / "autoguard").rglob("*.py"):
        leidas |= set(patron.findall(f.read_text(encoding="utf-8")))
    leidas -= {"PATH", "HOME", "PYTHONPATH", "AUTOGUARD_NO_DOTENV"}
    faltan = leidas - set(settings.ENV_VARS)
    assert not faltan, f"variables leídas pero no documentadas en .env.example: {sorted(faltan)}"
