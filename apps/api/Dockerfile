# Purpose: package the API service. Responsibilities: install the backend and start it in a container. Future modules: add a non-root runtime user and production dependency lock when deployment is introduced.
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
