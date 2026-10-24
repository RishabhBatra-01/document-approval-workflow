#!/usr/bin/env bash
#
# One command to run every required suite. Exits non-zero if any part fails.
#
#   ./scripts/test.sh
#
# These tests use the REAL Supabase project configured in backend/.env: real
# Auth sign-ins, real uploads to the private bucket, real PostgreSQL. Nothing
# is mocked, stubbed or intercepted, so the suite needs network access and will
# take a couple of minutes. If required configuration is missing it fails
# loudly — it never silently skips an integration or falls back to a mock.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

say() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }

# --- preconditions ---------------------------------------------------------

if [[ ! -f "$BACKEND/.env" ]]; then
  echo "ERROR: backend/.env is missing. Copy backend/.env.example and fill it in." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source "$BACKEND/.env"
set +a

for required in SUPABASE_URL SUPABASE_SECRET_KEY SUPABASE_PUBLISHABLE_KEY \
                SUPABASE_TEST_PROJECT_REF DB_HOST DB_NAME DB_USER DB_PASSWORD; do
  if [[ -z "${!required:-}" ]]; then
    echo "ERROR: $required is not set in backend/.env. Integration tests cannot run." >&2
    exit 1
  fi
done

# The guard the brief requires: never run destructive setup against anything
# but the explicitly declared test project.
CONFIGURED_REF="$(printf '%s' "$SUPABASE_URL" | sed -E 's#https://([a-z0-9]+)\.supabase\.co.*#\1#')"
if [[ "$CONFIGURED_REF" != "$SUPABASE_TEST_PROJECT_REF" ]]; then
  echo "ERROR: refusing to run." >&2
  echo "  SUPABASE_URL points at project '$CONFIGURED_REF'" >&2
  echo "  SUPABASE_TEST_PROJECT_REF is     '$SUPABASE_TEST_PROJECT_REF'" >&2
  exit 1
fi
if [[ -n "${SUPABASE_DEPLOYMENT_PROJECT_REF:-}" && "$SUPABASE_DEPLOYMENT_PROJECT_REF" == "$CONFIGURED_REF" ]]; then
  echo "ERROR: '$CONFIGURED_REF' is the declared deployment project. Refusing to run tests against it." >&2
  exit 1
fi

# --- backend ---------------------------------------------------------------

say "Backend checks"
cd "$BACKEND"
./.venv/bin/python manage.py check

say "Backend tests (real Supabase Auth, Storage and PostgreSQL)"
# --keepdb: the Supabase session pooler holds a connection open, so DROP
# DATABASE is refused at teardown. Reusing the test database is the supported
# approach on managed, pooled PostgreSQL.
./.venv/bin/python manage.py test tests --keepdb

# --- frontend --------------------------------------------------------------

say "Frontend type check"
cd "$FRONTEND"
./node_modules/.bin/tsc --noEmit

say "Frontend tests"
npm run test --silent

say "Frontend production build"
npm run build --silent

say "Secret leakage check on the built bundle"
# Matches the actual configured values, not just their prefixes: supabase-js
# legitimately contains the literal string "sb_secret_" for its own key
# detection, so a prefix match would be a false alarm.
leaked=0
for value in "${SUPABASE_SECRET_KEY:-}" "${DB_PASSWORD:-}" "${DJANGO_SECRET_KEY:-}" "${DB_HOST:-}"; do
  [[ -z "$value" ]] && continue
  if grep -rqF -- "$value" dist/ 2>/dev/null; then
    echo "FAIL: a backend secret was found in the production bundle." >&2
    leaked=1
  fi
done
if [[ "$leaked" -ne 0 ]]; then exit 1; fi
echo "No backend secret found in dist/."

say "All suites passed"
