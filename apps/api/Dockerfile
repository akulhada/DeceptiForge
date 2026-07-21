# Purpose: package the API service for a non-root, production-safe runtime.
# Responsibilities: install the backend, run as an unprivileged user, and start the server WITHOUT
#   auto-running migrations. Migrations are a separate, documented release step (see docs/Deployment).
# Pinned by immutable digest so a rebuild cannot silently pull different base contents.
# Human-readable tag: python:3.12-slim (update the digest and this comment together).
FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dependencies come from a hash-verified lockfile, installed before the source for layer caching.
# --require-hashes makes pip refuse any artifact whose hash is not listed, so a compromised or
# substituted wheel fails the build instead of shipping. Regenerate with:
#   make lock            (see apps/api/README or docs/Development.md)
# The build context is the monorepo root so the API image can package the shared analysis fixtures.
COPY apps/api/requirements.lock.txt ./requirements.lock.txt
COPY apps/api/pyproject.toml ./pyproject.toml
COPY apps/api/app ./app
COPY apps/api/migrations ./migrations
COPY apps/api/alembic.ini ./
COPY packages/contracts/fixtures/analysis ./fixtures/analysis

RUN pip install --no-cache-dir --require-hashes -r requirements.lock.txt \
    && pip install --no-cache-dir --no-deps . \
    && adduser --disabled-password --gecos "" --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Liveness probe via the standard library (no extra packages, no shell curl).
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

# Production command: serve only. Run `alembic upgrade head` as a separate release step.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
