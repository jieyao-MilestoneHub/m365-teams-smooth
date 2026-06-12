# backend

FastAPI process for AI Change Court. Layered as `domain/ · ports/ · adapters/ · agent/ ·
services/ · api/ · mcp/` per [`.claude/rules/architecture.md`](../.claude/rules/architecture.md).

## Develop

```bash
cd backend
uv sync                              # provision the virtualenv
uv run uvicorn app.main:app --reload # run (http://localhost:8000)
uv run ruff check                    # lint
uv run mypy                          # type-check
uv run pytest                        # tests
```

Copy `../.env.example` to `../.env` and adjust as needed. `FORCE_ALL_MOCK=true` runs every
integration as a mock with zero external credentials — the verification mode used by CI and the
scenario reproduction; the product path runs with a real LLM provider (ADR-0016).
