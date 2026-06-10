# Coding style

## Python (backend)

- Python 3.11+. Full type hints on public functions; checked with **mypy**.
- Lint/format with **ruff**. No unused imports, no dead code.
- Small, focused modules — one clear responsibility per file. Prefer composition over inheritance
  except for the documented template-method base classes.
- Pydantic models for all I/O boundaries (REST DTOs, MCP tool args, LLM structured output).
- Validate and sanitize all external input at the boundary; never trust LLM output — constrain it
  to registered capability schemas.
- No hardcoded secrets or magic values — read from `config.py` (pydantic-settings, env-driven).
- Errors are typed (`domain/errors.py`); don't leak adapter/SDK exceptions past the adapter layer.
- Tests: `pytest` + `pytest-asyncio`. Unit-test nodes, policy, and adapters in isolation with fakes;
  record real GitHub calls with `respx`/`vcrpy`.

## Other surfaces

- There is no frontend build. The Teams Adaptive Card is the decision UI — card templates are data
  in `m365/adaptive-cards/` — and the read-only run page is a static file the backend serves.
- The Playground bot (`m365/playground-bot/`) is a small Python (`uv`) project; the Python
  conventions above apply. It talks only to the backend REST API, and no surface embeds secrets.

## Documentation in code

- Docstrings and comments explain **function and architecture only**. Never mention the
  competition, scoring, or bonus points — see [docs.md](./docs.md).
- Comment the *why*, not the *what*. Match the density and idiom of surrounding code.
