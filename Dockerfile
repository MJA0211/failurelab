FROM node:26-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm AS application
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/opt/browsers
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.12.6 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev && uv run playwright install --with-deps chromium
COPY --from=frontend /build/dist ./frontend/dist
RUN useradd --create-home --uid 10001 app && mkdir -p /app/var && chown -R app:app /app/var /opt/browsers
USER app
ENV FAILURELAB_HOST=0.0.0.0 FAILURELAB_PORT=8787 FAILURELAB_DATA_DIR=/app/var
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/healthz', timeout=3)"]
CMD ["/app/.venv/bin/failurelab", "serve"]
