#!/usr/bin/env bash
#
# End-to-end verification for the three trials. Local-first: runs without a Microsoft 365 tenant.
# Tenant-dependent checks report PENDING until a tenant is configured (see verify.md).
#
# Usage:
#   scripts/verify.sh
#
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"

PASS=0
FAIL=0
PENDING=0

pass()    { printf '  \033[32mPASS\033[0m    %s\n' "$1"; PASS=$((PASS + 1)); }
fail()    { printf '  \033[31mFAIL\033[0m    %s\n' "$1"; FAIL=$((FAIL + 1)); }
pending() { printf '  \033[33mPENDING\033[0m %s\n' "$1"; PENDING=$((PENDING + 1)); }
section() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# Run a backend command (via uv); pass/fail on its exit code.
backend() { (cd "$BACKEND" && uv run "$@" >/dev/null 2>&1); }

check() {  # check "label" <command...>
  local label="$1"; shift
  if "$@"; then pass "$label"; else fail "$label"; fi
}

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found — install it (winget install astral-sh.uv) to run the backend checks." >&2
fi

section "Preconditions"
check "backend app imports and boots" backend python -c "from app.main import create_app; create_app()"

section "The three trials (fully mocked, dry-run + verdict)"
check "Reschedule trial (feasible + conflict alternative)" backend pytest -q tests/test_trial_launch_slip.py
check "Meeting Actions trial (requester authority)" backend pytest -q tests/test_trial_meeting_actions.py
check "Weekly Report trial (aggregate + post)" backend pytest -q tests/test_trial_weekly_report.py
check "golden fixtures match" backend pytest -q tests/test_golden_trials.py

section "Safety & audit"
check "hallucination guard + partial-failure containment" backend pytest -q tests/test_failure_and_guard.py
check "verdict idempotency + auto-resume" backend pytest -q tests/test_court_service.py
check "durable verdict interrupt resumes from checkpoint" backend pytest -q tests/test_court_graph.py

section "MCP surface"
check "MCP tools + resources + OAuth verifier" backend pytest -q \
  tests/test_mcp_server.py tests/test_mcp_tools.py tests/test_mcp_resources.py tests/test_mcp_security.py

section "Quality gates"
check "ruff clean" backend ruff check
check "mypy clean" backend mypy
check "pytest green + coverage ≥80% (full suite)" backend pytest --cov=app

# Shipped docs must not reference the competition.
section "Docs"
if grep -rinE "hackathon|agents league|competition|bonus|judg|rubric|submission|prize|deadline" \
     --exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=__pycache__ \
     --exclude-dir=.mypy_cache --exclude-dir=.ruff_cache --exclude-dir=.pytest_cache \
     --exclude-dir=data \
     "$ROOT/README.md" "$ROOT/roadmap.md" "$ROOT/verify.md" "$ROOT/docs" "$ROOT/m365" >/dev/null 2>&1; then
  fail "competition references found in shipped docs"
else
  pass "no competition references in shipped docs"
fi

section "Pending tenant (Microsoft 365)"
pending "declarative agent runs in Copilot Chat over OAuth2"
pending "Change Court Adaptive Card renders and verdict actions resume the run"
pending "real Microsoft Graph writes replace mocks"

printf '\n\033[1mSummary:\033[0m %d passed, %d failed, %d pending\n' "$PASS" "$FAIL" "$PENDING"
[ "$FAIL" -eq 0 ]
