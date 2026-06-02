# Developer entry points. Backend lives in backend/ and uses uv.
# `make check` is the local pre-PR gate (lint + type-check + tests).

.PHONY: help sync run lint type test check verify compose-up compose-down

help:
	@echo "Targets:"
	@echo "  sync         provision the backend virtualenv (uv sync)"
	@echo "  run          run the backend with reload (uvicorn)"
	@echo "  lint         ruff check"
	@echo "  type         mypy"
	@echo "  test         pytest"
	@echo "  check        lint + type + test (local pre-PR gate)"
	@echo "  demo         run the three trials end-to-end and print each Change Court"
	@echo "  migrate      apply database migrations (alembic upgrade head)"
	@echo "  verify       run the end-to-end trial checklist (scripts/verify.sh)"
	@echo "  compose-up   run the backend in Docker (fully mocked)"

sync:
	cd backend && uv sync

run:
	cd backend && uv run uvicorn app.main:app --reload

lint:
	cd backend && uv run ruff check

type:
	cd backend && uv run mypy

test:
	cd backend && uv run pytest

check: lint type test

demo:
	cd backend && uv run python -m scripts.demo

migrate:
	cd backend && uv run alembic upgrade head

verify:
	scripts/verify.sh

compose-up:
	docker compose up --build

compose-down:
	docker compose down
