# Distributed Rate Limiter

A fixed-window rate limiter built with FastAPI and Redis. Nginx distributes
requests between application instances, while Redis is the only source of
rate-limit state. The default policy allows 100 requests per `client_id` in a
60-second window.

## Architecture

```text
client -> Nginx -> FastAPI instance 1 --+
                -> FastAPI instance 2 --+-> Redis
```

- The FastAPI instances are stateless.
- Every check executes one Lua script in Redis.
- Each client key expires automatically after its window.
- The Redis client and its connection pool are created during application
  startup and closed during shutdown.

## Running the service

Requirements: Docker with Docker Compose. No local Python installation is
needed.

```bash
docker compose up -d --build
```

The clean-checkout default is `http://localhost:8000`. To run the same two-app
topology used by the acceptance and load tests:

```bash
docker compose up -d --build --scale app=2
```

Check that the service is ready:

```bash
curl http://localhost:8000/health
```

Stop it with:

```bash
docker compose down
```

### Configuration

An `.env` file is optional and intentionally ignored by Git. Compose has safe
non-secret defaults, so a fresh checkout starts without copying any files.
Copy `.env.example` to `.env` only when local overrides are needed.

| Variable | Default | Purpose |
| --- | ---: | --- |
| `REDIS_HOST` | `redis` | Redis hostname visible to the app |
| `REDIS_PORT` | `6379` | Redis port |
| `RATE_LIMIT` | `100` | Requests allowed per window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Window duration |
| `NGINX_HOST_PORT` | `8000` | Port exposed on the host |

When `.env` changes `NGINX_HOST_PORT`, use that port instead of `8000` in the
examples below.

## API

### `POST /check`

```bash
curl -X POST http://localhost:8000/check \
  -H 'Content-Type: application/json' \
  -d '{"client_id":"user_123"}'
```

Example response:

```json
{"allowed":true,"remaining":99,"reset_at":1720000000}
```

This endpoint always returns HTTP 200 for a valid request. Whether the caller
may continue is communicated by `allowed`.

### Middleware-protected endpoint

```bash
curl http://localhost:8000/demo -H 'X-Client-ID: user_123'
```

Allowed responses include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and
`X-RateLimit-Reset`. Once the quota is exhausted, `/demo` returns HTTP 429 and
also includes `Retry-After`. A missing `X-Client-ID` returns HTTP 400.

## Tests

Run the complete suite with one command:

```bash
make test
```

The runner builds the stack, starts two app instances, and tests:

- exactly 100 allowed results from 500 concurrent requests;
- isolation between different clients;
- quota restoration after the real 60-second expiry;
- middleware status codes and headers;
- connection and timeout errors under the fail-open policy;
- a real Redis outage and recovery without restarting either app instance.

Last verified on 2026-09-05: seven core tests passed, followed by the live
Redis-outage and Redis-recovery checks.

## Load test

The load test uses the pinned `grafana/k6:0.57.0` Docker image and starts two
app instances automatically:

```bash
make load-test
```

Defaults are a 5-second warm-up followed by a 30-second measurement with 50
virtual users and 100 client IDs per virtual user. The client pool keeps each
client below the quota, so the measurement represents the allowed-request path.
The response schema is checked on every request.

The profile can be changed without editing files:

```bash
LOAD_TEST_DURATION_SECONDS=60 LOAD_TEST_VUS=100 make load-test
```

### Measured result

Measurement date: 2026-09-05.

- Host: MacBook Air, Apple M1, 8 CPU cores, 8 GB RAM.
- Docker Desktop memory available to containers: approximately 3.8 GiB.
- Service: two single-process Uvicorn app containers, Redis 8.8.1, and Nginx
  1.31.3; no `--reload`.
- Generator: k6 0.57.0 in a separate container on the internal Docker network.
- Dataset: 5,000 measured client IDs with Redis initially available.
- Warm-up: 5 seconds with 10 virtual users.
- Measurement: 30 seconds with 50 virtual users.

| Metric | Result |
| --- | ---: |
| Requests | 78,609 |
| Throughput | 2,245.56 requests/s |
| HTTP or schema failures | 0 |
| p50 latency | 15.96 ms |
| p95 latency | 43.83 ms |
| p99 latency | 90.14 ms |
| Maximum latency | 214.89 ms |

During the measured phase, one CPU snapshot showed approximately 105% and
109% CPU for the two app containers, 37% for Nginx, 12% for Redis, and 84% for
k6. In Docker's reporting, about 100% represents one fully used CPU core. The
two single-process application workers were therefore the observed bottleneck;
Redis and the load generator still had headroom. More app instances or multiple
Uvicorn workers should increase throughput until Redis or Nginx becomes the
next limit. This is a local single-machine result, not a production capacity
guarantee.

## Design decisions

### Fixed window and Redis state

The implementation uses a fixed window beginning with a client's first request.
It needs one counter and one TTL per active client, making it simple and O(1)
in Redis memory per client. The cost is a boundary burst: traffic is less smooth
than with a sliding window or token bucket.

No counters are held in application memory. An in-process limiter was rejected
because separate instances would make independent decisions and collectively
allow more than the configured limit.

### Atomicity

One Redis Lua script performs the complete decision:

1. `INCR` the client's counter.
2. If it is the first request, attach the window TTL with `EXPIRE`.
3. Read `PTTL` and Redis server time to calculate `reset_at`.
4. Calculate `allowed` and `remaining` and return all three values.

Redis runs a Lua script atomically. Other commands cannot execute between these
steps, so concurrent app instances cannot both observe and spend the same final
quota slot. Lua was preferred over `WATCH`/`MULTI` because it avoids optimistic
retry loops and performs the check in one network round trip.

### Redis connection lifecycle

The `redis.asyncio.Redis` client is created in the FastAPI lifespan handler.
That client owns a reusable connection pool and is stored in `app.state`, so a
new client is not created for every request. Connect and command timeouts are
both 0.5 seconds to bound degradation when Redis is unavailable.

### Redis failure policy

The service fails open on Redis connection and timeout errors. `/check` still
returns HTTP 200 with `allowed: true`; `/demo` lets the request continue. This
keeps the public API available during a Redis outage, at the explicit cost of
temporarily allowing unbounded traffic. Fail-closed was considered but rejected
because it turns Redis into a complete availability dependency. No retries are
performed in the request path because retries would extend tail latency during
an outage. Normal limiting resumes automatically when Redis returns.

### PostgreSQL interpretation

PostgreSQL is intentionally omitted. This task defines no relational entities,
migrations, or durable records and explicitly requires all limiter state to live
only in Redis. Adding an idle PostgreSQL service would not participate in the
solution or test any meaningful behavior. If durable audit history or stored
per-client policies were later required, PostgreSQL would be appropriate for
that data while the live counters would remain in Redis.

## Answers to the assignment questions

1. **What makes the check atomic?** The increment, first-request expiry, TTL
   read, and decision all happen inside one Redis Lua execution. Redis does not
   interleave another command while the script is running.
2. **What is the fixed-window worst case?** Up to 200 requests can pass in an
   arbitrary 60-second interval: 100 immediately before one window expires and
   another 100 immediately after the next window starts.
3. **What happens during a 30-second Redis outage?** Clients continue receiving
   allowed responses because the service fails open. This protects API
   availability, while accepting that quotas cannot be enforced until Redis
   returns.

## Alternatives considered

- Sliding window: smoother enforcement, but more Redis operations or stored
  timestamps and greater implementation complexity.
- Token bucket: supports controlled bursts well, but requires additional state
  and arithmetic not needed for the specified fixed limit.
- Fail-closed: protects downstream capacity, but makes every Redis outage an API
  outage.
- PostgreSQL-backed counters: rejected because row locking adds latency and the
  task requires shared limiter state in Redis.

## Not implemented

The optional extensions from the assignment were left out: sliding-window
limiting, different limits per client, and Prometheus metrics. Authentication
and UI were also not added because they are outside the requested scope.
