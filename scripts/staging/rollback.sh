#!/usr/bin/env bash
# Purpose: controlled rollback of the staging application to a previous release image.
# Behavior: rolls back the APPLICATION image/tag only. It NEVER downgrades database migrations and
#   NEVER restores/drops data — database recovery is a deliberate, separately-approved step using a
#   tested backup. Prints the plan and performs only the safe, reversible image swap when confirmed.
#
# Required: PREV_TAG (previous release image tag to roll back to).
# Optional: COMPOSE_FILE, CONFIRM=yes (required to actually apply the image swap).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$REPO_ROOT/docker-compose.prod.example.yml}"
: "${PREV_TAG:?set PREV_TAG to the previous release image tag}"

cat <<PLAN
== controlled rollback plan ==
  1. Stop the new deployment (do not delete volumes).
  2. Preserve the database and shipped logs (no destructive action here).
  3. Roll the API AND both workers back to image tag: $PREV_TAG
     (workers must match the application version).
  4. Do NOT downgrade database migrations. If schema recovery is required, restore the database
     from a tested backup under a separate, approved procedure.
  5. Re-run: scripts/staging/verify_runtime.sh
  6. Record the incident and the release decision in docs/checklists/StagingVerification.md.
PLAN

if [ "${CONFIRM:-no}" != "yes" ]; then
  echo
  echo "Dry run. Re-run with CONFIRM=yes to apply the image swap (data is never touched)."
  exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker CLI unavailable; perform the image swap on the target host." >&2
  exit 1
fi

echo "Applying image rollback to $PREV_TAG (API + workers)…"
# Image reference is provided via the environment the Compose file interpolates; this only redeploys
# the services with the pinned previous tag. Volumes and the database are left untouched.
DEPLOY_IMAGE_TAG="$PREV_TAG" docker compose -f "$COMPOSE_FILE" up -d \
  api reconstruction-worker lifecycle-cron

echo "Rollback applied. Now run scripts/staging/verify_runtime.sh and record the outcome."
