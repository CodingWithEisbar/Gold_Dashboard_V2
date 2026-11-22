#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if (( $# > 1 )) || [[ $# == 1 && $1 != --build ]]; then
    echo "Cách dùng: ./start.sh [--build]" >&2
    exit 2
fi

if [[ ! -f .env ]]; then
    python3 infra/init-local-env.py
fi

docker compose -f compose.yaml -f compose.local.yaml up -d --wait "$@"

url=http://127.0.0.1:8080
for path in / /api/v1/health/ready; do
    curl --noproxy '*' --fail --silent --show-error --max-time 5 \
        --retry 5 --retry-connrefused --retry-delay 1 --output /dev/null "$url$path"
done

echo "Dashboard đã sẵn sàng trên máy chạy Docker: $url"
