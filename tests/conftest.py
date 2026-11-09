"""Aislamiento del entorno para toda la suite (T-22).

Se ejecuta antes de que cualquier test importe `autoguard`: desactiva la carga de `.env` y limpia llaves
y URLs exportadas, de modo que los tests corren en modo mock y nunca llaman a la red aunque exista un
`.env` con llaves reales. Los tests que necesitan una variable la ponen con `monkeypatch.setenv`.
"""

import os

os.environ["AUTOGUARD_NO_DOTENV"] = "1"
for _var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "TAVILY_API_KEY", "FIRECRAWL_API_KEY", "AUTOGUARD_API_KEY",
             "DATABASE_URL", "LLM_CACHE"):
    os.environ.pop(_var, None)
os.environ["LLM_PROVIDER"] = "mock"
os.environ["VALUACION_OFFLINE"] = "1"
