# Developer entry points. Backend lives in backend/ and uses uv.
# `make check` is the local pre-PR gate (lint + type-check + tests).

.PHONY: help sync run lint type test check demo demo-all cards cards-all migrate verify setup-demo setup-demo-apply compose-up compose-down bot package

help:
	@echo "Targets:"
	@echo "  sync         provision the backend virtualenv (uv sync)"
	@echo "  run          run the backend with reload (uvicorn)"
	@echo "  lint         ruff check"
	@echo "  type         mypy"
	@echo "  test         pytest with coverage (fails under 80%)"
	@echo "  check        lint + type + test (local pre-PR gate)"
	@echo "  demo         run the headline demo end-to-end (Informed Approval) and print each Change Court"
	@echo "  demo-all     demo + the additional capabilities the engine handles (not recorded)"
	@echo "  cards        export the headline Change Court Adaptive Card JSON (m365/adaptive-cards/generated)"
	@echo "  cards-all    export cards for every capability, not just the headline"
	@echo "  migrate      apply database migrations (alembic upgrade head)"
	@echo "  verify       run the end-to-end trial checklist (scripts/verify.sh)"
	@echo "  setup-demo   audit whether the demo's real resources exist (read-only; needs creds)"
	@echo "  setup-demo-apply  create the missing demo resources (idempotent)"
	@echo "  compose-up   run the backend in Docker (fully mocked)"
	@echo "  bot          run the Change Court Playground bot (tenant-free; see m365/playground-bot)"
	@echo "  package      build the M365 app package (m365/build/appPackage.zip)"

sync:
	cd backend && uv sync

run:
	cd backend && uv run uvicorn app.main:app --reload

lint:
	cd backend && uv run ruff check

type:
	cd backend && uv run mypy

test:
	cd backend && uv run pytest --cov=app

check: lint type test

demo:
	cd backend && uv run python -m scripts.demo

demo-all:
	cd backend && uv run python -m scripts.demo --all

cards:
	cd backend && uv run python -m scripts.export_cards

cards-all:
	cd backend && uv run python -m scripts.export_cards --all

migrate:
	cd backend && uv run alembic upgrade head

verify:
	scripts/verify.sh

setup-demo:
	cd backend && uv run python -m scripts.setup_demo

setup-demo-apply:
	cd backend && uv run python -m scripts.setup_demo --apply

compose-up:
	docker compose up --build

compose-down:
	docker compose down

bot:
	cd m365/playground-bot && uv run python -m courtbot.server

package:
	python m365/package.py
