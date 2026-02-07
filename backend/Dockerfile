FROM python:3.14-slim AS builder
WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential python3-dev \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel --wheel-dir=/wheels -r requirements.txt

FROM python:3.14-slim AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN groupadd -r nonroot && useradd -r -g nonroot nonroot
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-compile /wheels/*.whl && rm -rf /wheels
COPY --chown=nonroot:nonroot app/ ./app/
COPY --chown=nonroot:nonroot migrations/ ./migrations/
COPY --chown=nonroot:nonroot alembic.ini ./alembic.ini
USER nonroot:nonroot
EXPOSE 8080
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8080"]
