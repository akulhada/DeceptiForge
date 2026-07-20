#!/usr/bin/env bash
# Purpose: run application-level restore-integrity verification against the isolated recovery
#   database and produce a machine-readable, checksummed report (no secrets). A backup is not
#   considered valid until this passes.
# Env: DF_TARGET_ENV=recovery, DF_RECOVERY_DATABASE_URL, DF_BACKUP_IDENTIFIER, DF_RECOVERY_POINT.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
df_require_env recovery
: "${DF_RECOVERY_DATABASE_URL:?}"; : "${DF_BACKUP_IDENTIFIER:?}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT/apps/api"
# Reuse the deterministic verifier against the recovery DB. Enable restore drills for this run only.
DATABASE_URL="$DF_RECOVERY_DATABASE_URL" APP_ENV=development RESTORE_DRILL_ENABLED=true \
  python - "$DF_BACKUP_IDENTIFIER" <<'PY'
import sys, json
from app.config.settings import get_settings
from app.database.session import get_sessionmaker
from app.services.reliability import restore_verify, objectives
from app.repositories.reliability import current_migration_head
s = get_sessionmaker()()
settings = get_settings()
head = current_migration_head()
checks = restore_verify.verify(s, settings, expected_migration=head)
passed = all(c.passed for c in checks)
print(json.dumps({"backup": sys.argv[1], "passed": passed,
                  "checks": [{"name": c.name, "passed": c.passed} for c in checks]}))
sys.exit(0 if passed else 1)
PY
rc=$?
[[ $rc -eq 0 ]] && df_result verify_restore ok || df_result verify_restore fail
exit $rc
