#!/usr/bin/env bash
#
# End-to-end verification for the Launch Change Commander scenario.
#
# This is a skeleton: each check is a stub that prints PASS / FAIL / PENDING. Fill the stubs in as
# the corresponding milestones land (see roadmap.md). The script is local-first and must run without
# a Microsoft 365 tenant; tenant-dependent checks report PENDING until a tenant is configured.
#
# Usage:
#   scripts/verify.sh            # run all available checks
#   API_BASE=http://localhost:8000 scripts/verify.sh
#
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000}"
DASHBOARD_BASE="${DASHBOARD_BASE:-http://localhost:3000}"

PASS=0
FAIL=0
PENDING=0

pass()    { printf '  \033[32mPASS\033[0m    %s\n' "$1"; PASS=$((PASS + 1)); }
fail()    { printf '  \033[31mFAIL\033[0m    %s\n' "$1"; FAIL=$((FAIL + 1)); }
pending() { printf '  \033[33mPENDING\033[0m %s\n' "$1"; PENDING=$((PENDING + 1)); }
section() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# Helper: mark a not-yet-implemented check as pending so the script stays green pre-implementation.
todo() { pending "$1 (not implemented yet)"; }

section "Preconditions"
# TODO(M0): curl -fsS "$API_BASE/api/health" and assert healthy.
todo "backend /api/health is healthy"
# TODO(M7): assert dashboard responds at $DASHBOARD_BASE.
todo "frontend dashboard responds"
# TODO(M3): assert GitHub adapter mode is 'real' (or FORCE_ALL_MOCK is set).
todo "integration mode configured (GitHub real, others mock)"

section "Core flow (dry-run)"
# TODO(M2/M5): seed the launch-slip decision in dry-run; assert a plan is returned.
todo "dry-run produces an execution plan"
# TODO(M2): assert every plan step maps to a registered capability.
todo "all plan steps reference registered capabilities"
# TODO(M2): assert policy sets status AWAITING_APPROVAL.
todo "policy flags approval required"
# TODO(M3): assert no external mutation occurred in dry-run.
todo "dry-run mutates nothing external"

section "Approval & execution (live)"
# TODO(M5): submit live; approve via REST; assert graph resumes and reaches DONE.
todo "approve via REST resumes and executes"
# TODO(M6): approve via MCP tool approve_plan; assert parity.
todo "approve via MCP tool resumes and executes"
# TODO(M3): assert real GitHub milestone/issue change in the test repo.
todo "real GitHub write succeeds"

section "Safety & audit"
# TODO(M4): assert audit record has before/after + rollback hints.
todo "audit log records before/after + rollback hints"
# TODO(M5/M6): re-approve an already-resumed decision; assert no double execution.
todo "approval is idempotent (no double execution)"

section "Dashboard"
todo "run + audit trail visible in dashboard (manual)"

section "Quality gates"
if command -v ruff >/dev/null 2>&1 && [ -d backend ]; then
  if (cd backend && ruff check . >/dev/null 2>&1); then pass "ruff clean"; else fail "ruff reported issues"; fi
else
  pending "ruff not available / backend not scaffolded yet"
fi

if command -v mypy >/dev/null 2>&1 && [ -d backend ]; then
  if (cd backend && mypy app >/dev/null 2>&1); then pass "mypy clean"; else fail "mypy reported issues"; fi
else
  pending "mypy not available / backend not scaffolded yet"
fi

if command -v pytest >/dev/null 2>&1 && [ -d backend/tests ]; then
  if (cd backend && pytest -q >/dev/null 2>&1); then pass "pytest green"; else fail "pytest failing"; fi
else
  pending "pytest not available / no tests yet"
fi

# Shipped docs must not reference the competition.
if grep -rinE "hackathon|agents league|competition|bonus|judg|rubric|submission|prize|deadline" \
     README.md roadmap.md verify.md docs/ >/dev/null 2>&1; then
  fail "competition references found in shipped docs"
else
  pass "no competition references in shipped docs"
fi

section "Pending tenant (Microsoft 365)"
pending "declarative agent runs in Copilot Chat over OAuth2"
pending "approval Adaptive Card renders and resumes the run"
pending "real Microsoft Graph writes replace mocks"

printf '\n\033[1mSummary:\033[0m %d passed, %d failed, %d pending\n' "$PASS" "$FAIL" "$PENDING"
[ "$FAIL" -eq 0 ]
