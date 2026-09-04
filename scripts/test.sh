#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

internal_base_url="${TEST_INTERNAL_BASE_URL:-http://nginx}"

restore_redis() {
    docker compose start redis >/dev/null 2>&1 || true
}

trap restore_redis EXIT

docker compose up -d --build --scale app=2 --wait

app_count="$(docker compose ps --status running -q app | awk 'NF {count++} END {print count+0}')"
if [[ "$app_count" -ne 2 ]]; then
    echo "Expected two running app instances, found $app_count" >&2
    exit 1
fi

docker compose run --rm --no-deps \
    -e TEST_BASE_URL="$internal_base_url" \
    app python -m pytest -q -m "not redis_outage"

app_ids_before="$(docker compose ps --status running -q app | sort)"

docker compose stop redis
docker compose run --rm --no-deps \
    -e TEST_BASE_URL="$internal_base_url" \
    -e EXPECTED_REDIS_STATE=unavailable \
    app python -m pytest -q tests/test_redis_outage.py

docker compose start redis
for _ in $(seq 1 30); do
    if docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
        break
    fi
    sleep 1
done
docker compose exec -T redis redis-cli ping | grep -q PONG

docker compose run --rm --no-deps \
    -e TEST_BASE_URL="$internal_base_url" \
    -e EXPECTED_REDIS_STATE=available \
    app python -m pytest -q tests/test_redis_outage.py

app_ids_after="$(docker compose ps --status running -q app | sort)"
if [[ "$app_ids_before" != "$app_ids_after" ]]; then
    echo "App instances restarted during the Redis outage test" >&2
    exit 1
fi

trap - EXIT
