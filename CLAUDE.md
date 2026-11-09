@AGENTS.md

## Notas específicas de Claude Code

- Si lanzas subagentes, cada uno sigue el ciclo de AGENTS.md con su propio nombre `<sesion>:wN` / `<sesion>:rN`.
- Al implementar `autoguard/llm.py` o cualquier llamada a Claude, carga primero el skill `claude-api`.
