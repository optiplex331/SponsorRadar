# One image for the web server and the collector.
FROM node:24-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
# uv is mounted only while installing, so it does not ship in the image.
RUN --mount=from=ghcr.io/astral-sh/uv:0.12,source=/uv,target=/bin/uv \
    uv sync --locked --no-dev --no-install-project
COPY backend/ ./
RUN --mount=from=ghcr.io/astral-sh/uv:0.12,source=/uv,target=/bin/uv \
    uv sync --locked --no-dev
# web.py finds the bundle at <root>/frontend/dist, the same layout as the repo.
COPY --from=frontend /app/frontend/dist /app/frontend/dist
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin radar
USER 10001
ENV PATH="/app/backend/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "sponsor_radar.web:app", "--host", "0.0.0.0", "--port", "8000"]
