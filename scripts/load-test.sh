#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

internal_base_url="${LOAD_TEST_INTERNAL_BASE_URL:-http://nginx}"
duration_seconds="${LOAD_TEST_DURATION_SECONDS:-30}"
virtual_users="${LOAD_TEST_VUS:-50}"
clients_per_vu="${LOAD_TEST_CLIENTS_PER_VU:-100}"
warmup_seconds="${LOAD_TEST_WARMUP_SECONDS:-5}"
k6_image="${K6_IMAGE:-grafana/k6:0.57.0}"

docker compose up -d --build --scale app=2 --wait

app_count="$(docker compose ps --status running -q app | awk 'NF {count++} END {print count+0}')"
if [[ "$app_count" -ne 2 ]]; then
    echo "Expected two running app instances, found $app_count" >&2
    exit 1
fi

docker run --rm \
    --network a2data_task1_frontend \
    --volume "$project_dir/load:/scripts:ro" \
    -e BASE_URL="$internal_base_url" \
    -e DURATION="${duration_seconds}s" \
    -e VUS="$virtual_users" \
    -e CLIENTS_PER_VU="$clients_per_vu" \
    -e WARMUP_DURATION="${warmup_seconds}s" \
    -e RUN_ID="$(date +%s)" \
    "$k6_image" run /scripts/rate_limiter.js
