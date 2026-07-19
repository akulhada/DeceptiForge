#!/usr/bin/env bash
# Purpose: run database migrations as a SEPARATE release step (never from API startup).
# Behavior: reports current revision, applies `alembic upgrade head`, verifies the head matches the
#   latest migration on disk, and exits non-zero on failure. Does NOT start the API.
#
# BACKUP/ROLLBACK EXPECTATIONS (read before running):
#   - Take a verified database backup first. This script does NOT back up for you.
#   - Migrations are forward-only in practice. Downgrades are validated in CI for the most recent
#     revision, but destructive downgrades are NOT auto-applied here. To roll back, restore from the
#     tested backup (see scripts/staging/rollback.sh) rather than blindly downgrading.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
API_DIR="$REPO_ROOT/apps/api"

: "${DATABASE_URL:?DATABASE_URL must be set to the staging database}"

cd "$API_DIR"

echo "== migration (separate release step) =="
echo "-- current revision --"
alembic current

# Expected head = highest-numbered migration id on disk (revision equals filename stem).
expected_head="$(find migrations/versions -name '*.py' -exec basename {} .py \; | sort | tail -n1)"
echo "expected head: $expected_head"

echo "-- upgrade head --"
alembic upgrade head

echo "-- verify head applied --"
current="$(alembic current 2>/dev/null | awk '{print $1}' | tail -n1)"
if [ "$current" != "$expected_head" ]; then
  echo "MIGRATION: FAIL — applied head '$current' != expected '$expected_head'"
  exit 1
fi

echo "MIGRATION: OK — at $current (API not started; start it as a separate step)"
