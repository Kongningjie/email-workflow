FROM node:24-alpine AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
RUN pip install --no-cache-dir uv==0.11.31
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY migrations/ migrations/
COPY config/ config/
COPY src/ src/
RUN uv sync --frozen --no-dev
COPY --from=frontend-builder /build/frontend/dist frontend/dist/
RUN mkdir -p /app/data
EXPOSE 8000 8001
CMD ["uvicorn", "email_workflow.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
