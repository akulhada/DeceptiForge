#!/usr/bin/env bash
# Purpose: regenerate the hash-verified Python lockfiles.
# Responsibilities: resolve dependencies on the SAME interpreter and platform the runtime image uses,
#   so environment markers cannot resolve differently in CI or production than they did on a
#   developer machine. Never hand-edit the generated files.
#
# Usage:  bash scripts/lock_python_dependencies.sh
# Then:   review the diff and commit both lockfiles with the pyproject change that caused it.
set -euo pipefail

# Must match the digest pinned in apps/api/Dockerfile (human-readable tag: python:3.12-slim).
BASE_IMAGE='python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de'

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

docker run --rm -v "$repo_root/apps/api:/w" -w /w "$BASE_IMAGE" sh -c '
  set -eu
  pip install --quiet pip-tools
  pip-compile --quiet --generate-hashes \
    --output-file requirements.lock.txt pyproject.toml
  pip-compile --quiet --generate-hashes --extra dev \
    --output-file requirements-dev.lock.txt pyproject.toml
'

echo "Regenerated:"
echo "  apps/api/requirements.lock.txt       (runtime — installed into the production image)"
echo "  apps/api/requirements-dev.lock.txt   (runtime + dev — used by CI and local development)"
