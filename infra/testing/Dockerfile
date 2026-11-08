FROM python:3.15.2-alpine
WORKDIR /workspace
COPY backend/requirements-dev.lock /tmp/requirements-dev.lock
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements-dev.lock \
    && apk add --no-cache postgresql18-client \
    && addgroup -g 10002 verifier && adduser -D -H -u 10002 -G verifier verifier
ENV PYTHONPATH=/workspace/backend PYTHONDONTWRITEBYTECODE=1 APP_ENV=test
USER 10002:10002
CMD ["python", "infra/linux_tests.py"]
