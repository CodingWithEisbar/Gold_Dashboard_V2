FROM python:3.15.2-alpine AS dependencies
WORKDIR /build
COPY backend/requirements.lock ./requirements.lock
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir --require-hashes -r requirements.lock \
    && /opt/venv/bin/pip uninstall --yes pip

FROM python:3.15.2-alpine AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY --from=dependencies /opt/venv /opt/venv
RUN apk upgrade --no-cache \
    && addgroup -g 10001 gold && adduser -D -H -u 10001 -G gold gold \
    && /usr/local/bin/python -c "import shutil; shutil.rmtree('/usr/local/lib/python3.15/site-packages')"
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./alembic.ini
USER 10001:10001
ENTRYPOINT ["python", "-m", "app.jobs.container_entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers", "--no-access-log", "--limit-concurrency", "64", "--timeout-keep-alive", "5"]
