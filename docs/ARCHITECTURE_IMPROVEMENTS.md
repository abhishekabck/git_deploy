# gitDeploy v2 — Architecture Improvements & New Features
**What to add, why it matters, and how to think about it in interviews**
Date: 2026-04-29

---

## Table of Contents
1. [What Was Wrong With v1](#1-what-was-wrong-with-v1)
2. [Should You Switch to Django?](#2-should-you-switch-to-django)
3. [Database Architecture: RDBMS + NoSQL](#3-database-architecture-rdbms--nosql)
4. [Proper Logging System](#4-proper-logging-system)
5. [Async Task Queue — Celery](#5-async-task-queue--celery)
6. [Per-Container Resource Monitoring](#6-per-container-resource-monitoring)
7. [Custom Subdomain System](#7-custom-subdomain-system)
8. [Scalability Patterns to Apply](#8-scalability-patterns-to-apply)
9. [System Design Concepts You Implemented](#9-system-design-concepts-you-implemented)
10. [New Features Roadmap](#10-new-features-roadmap)
11. [Interview Talking Points](#11-interview-talking-points)

---

## 1. What Was Wrong With v1

Before improving, understand exactly what v1 lacked. Each issue is a direct interview talking point.

### Issue 1: SQLite in production
**Problem:** SQLite serializes all writes. When a Celery worker writes a deployment log while the API writes an app status update, one of them blocks until the other finishes. With concurrent users this becomes a bottleneck, and you'll see `database is locked` errors.
**Fix:** PostgreSQL with asyncpg. Row-level MVCC means multiple writers never block each other (unless they touch the exact same row).

### Issue 2: Deploy runs inline in the API route
**Problem:** The deploy pipeline (`git clone` → `docker build` → `docker run`) can take 2–10 minutes. Running this inside an async route means:
- If the API server restarts during a deploy (OOM kill, deploy), the deploy is silently dropped. App is stuck in `RUNNING` or `PREPARED` with no recovery.
- `asyncio.to_thread` runs it in a thread pool, but doesn't give you retry, persistence, or visibility.

**Fix:** Celery task chain. The broker (Redis) stores the task. If the worker crashes mid-task, the task is re-queued. You get retries, monitoring, and independent scaling.

### Issue 3: WebSocket holds the subprocess
**Problem:** In v1, the WS handler might directly run `subprocess.Popen` and stream output. This means:
- The WebSocket connection must stay alive for the whole build — if the browser tab closes, the build might stop.
- You can't reconnect and pick up a running build.
- Multiple tabs can't watch the same build.

**Fix:** Redis Pub/Sub fan-out. Celery worker holds the subprocess; broadcasts each line to Redis. WS handler subscribes to Redis. Reconnecting just re-subscribes — same stream, no state lost.

### Issue 4: No structured logging
**Problem:** `print()` statements and ad-hoc `logging.info()` calls with no consistent format. No correlation IDs. Can't trace a single request through multiple services.
**Fix:** JSON formatter + `ContextVar`-based request_id propagation.

### Issue 5: Port allocation has a race condition
**Problem:** Current allocation scans used ports from DB, then checks OS. Between the scan and the actual allocation, another concurrent request could claim the same port.
**Fix:** `SELECT FOR UPDATE` in PostgreSQL serializes concurrent allocators.

### Issue 6: No test suite
**Problem:** The project was AI-generated; no tests means you can't safely refactor. Every change is a bet.
**Fix:** pytest-asyncio + httpx AsyncClient fixtures. Test services in isolation (mock Docker/git), test routes with in-memory DB.

---

## 2. Should You Switch to Django?

**Short answer: No. Keep FastAPI.**

### The Comparison
| Concern | FastAPI | Django |
|---------|---------|--------|
| WebSocket | Native async, first-class | Needs Django Channels + separate ASGI worker |
| Async ORM | SQLAlchemy 2.0 async | Django ORM is sync (async support is partial workaround) |
| API-first | Designed for it | Designed for server-rendered HTML; REST is bolted on |
| Pydantic | Native v2 integration | External, manual wiring |
| Performance | ~3x faster on I/O-bound workloads | Slower due to sync defaults |
| Admin panel | Roll your own or FastAPI-Admin | Built-in, polished |
| Auth | Roll your own (you already did) | `django-allauth` is powerful |

### When Django Would Be Better
- If you needed a polished admin panel out of the box.
- If the team was primarily Django-experienced.
- If the app was content-heavy with complex ORM relationships.
- If you needed django-allauth's OAuth/social login ecosystem.

### For gitDeploy
gitDeploy is an API-only service that requires: WebSocket connections held open for minutes, concurrent async I/O (DB + Redis + subprocess), and real-time push. FastAPI is the right tool.

**Interview phrasing:** "I chose FastAPI because the core requirement is async I/O — WebSocket streaming during deploys, concurrent Docker and Git operations, and real-time metrics push. Django's synchronous-first design would require Channels and careful async workarounds for this use case. FastAPI's native async, Pydantic integration, and OpenAPI auto-docs made it the right fit."

---

## 3. Database Architecture: RDBMS + NoSQL

### The Split

| Data | Database | Why |
|------|----------|-----|
| Users, apps, deployment event logs | PostgreSQL | Relational, ACID, queryable with JOINs, consistent |
| Container log lines (raw stdout/stderr) | MongoDB | Append-only, variable-length, time-series, TTL index |
| Container metric snapshots | MongoDB | Same as logs — time-series, TTL, no fixed schema |
| OTP tokens, rate limits, pub/sub, blacklist | Redis | Ephemeral, TTL-based, pub/sub native |

### Why Not All PostgreSQL?
You technically could. But:
- A 2-minute build easily generates 5,000 log lines. Over 100 users deploying daily, that's 500K rows/day in a table that only needs time-range queries.
- PostgreSQL full-text search on `TEXT` columns is slower than MongoDB's index-based lookup.
- MongoDB's TTL index auto-deletes old documents — no cron job, no manual `DELETE WHERE timestamp < ?`.
- Keeping noisy, append-only log data separate from your relational data also keeps your PostgreSQL query planner statistics clean and vacuum less burdensome.

### Why Not All MongoDB?
Users, apps, deployment steps — these have FK relationships and require transactional consistency. If you're updating `app.status` and writing a `deployment_log` row, you want them in the same ACID transaction. MongoDB multi-document transactions exist but are slower and less ergonomic.

### PostgreSQL Schema Principle: JSONB for Env Vars
```sql
env JSONB DEFAULT '{}'
```
Why JSONB over VARCHAR? You can index specific keys (`CREATE INDEX ON apps ((env->>'NODE_ENV'))`), query them (`WHERE env->>'PORT' = '3000'`), and update individual keys (`jsonb_set(env, '{NODE_ENV}', '"production"')`). You get flexibility without losing queryability.

### MongoDB Indexing Strategy
```javascript
// container_logs
db.container_logs.createIndex({ app_id: 1, timestamp: -1 })
db.container_logs.createIndex({ timestamp: 1 }, { expireAfterSeconds: 2592000 })

// container_metrics
db.container_metrics.createIndex({ app_id: 1, timestamp: -1 })
db.container_metrics.createIndex({ timestamp: 1 }, { expireAfterSeconds: 604800 })
```

The compound index `{ app_id: 1, timestamp: -1 }` satisfies the most common query: "get logs for app X, newest first, in time window T1–T2".

---

## 4. Proper Logging System

v1 has ad-hoc `logger.info()` calls with inconsistent fields. v2 needs structured, queryable, correlated logs.

### Layer 1 — Application Logs (JSON to stdout)

Install: `pip install python-json-logger`

```python
# core/logging.py
from contextvars import ContextVar
from pythonjsonlogger import jsonlogger
import logging

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get("-")
        return True

def setup_logging():
    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(request_id)s %(message)s"
    )
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)
```

Every `logger.info("message")` call now produces:
```json
{"asctime": "2026-04-29T10:00:00.123Z", "levelname": "INFO", "name": "app.services.deploy", "request_id": "uuid-here", "message": "Deploy triggered", "app_id": 7}
```

### Layer 2 — Correlation IDs via ContextVar

```python
# core/middleware.py
from uuid import uuid4
from core.logging import request_id_var

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = str(uuid4())
        request_id_var.set(rid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response
```

The `ContextVar` is tied to the async task context — each request gets its own value. Log calls in services/ automatically pick it up via the `RequestIdFilter`. No need to pass `request_id` as a parameter through your call stack.

### Layer 3 — Access Logs

```python
class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000)
        logger.info(
            "HTTP request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "client_ip": request.client.host,
            }
        )
        return response
```

### Layer 4 — Deployment Event Logs (PostgreSQL)

```python
# Each pipeline step writes:
await log_service.write_step(
    db=db,
    app_id=app_id,
    deploy_number=deploy_number,
    step="docker_build",
    status="started"
)
# ... do the work ...
await log_service.write_step(
    db=db,
    app_id=app_id,
    deploy_number=deploy_number,
    step="docker_build",
    status="success",
    duration_ms=elapsed_ms
)
```

### Layer 5 — Container Runtime Logs (MongoDB)

```python
# In log_tail_task (Celery):
async for line in tail_docker_logs(container_id):
    doc = {
        "app_id": app_id,
        "deploy_number": deploy_number,
        "container_id": container_id,
        "timestamp": datetime.utcnow(),
        "stream": line.stream,   # "stdout" or "stderr"
        "message": line.text
    }
    await mongo.container_logs.insert_one(doc)
    redis.publish(f"pubsub:logs:{app_id}", json.dumps(doc))
```

### What This Gives You
- Grep all logs for a specific `request_id` to trace a single user request through 5 service calls.
- Query MongoDB for "all stderr lines from app 42 in the last hour".
- View "which step of deployment #7 failed and what was the error message" in PostgreSQL.
- Set up Grafana Loki on stdout JSON to visualize error rates over time.

---

## 5. Async Task Queue — Celery

### Why Celery Over asyncio.to_thread

| | asyncio.to_thread | Celery Task |
|--|-------------------|-------------|
| Survives server restart | No | Yes (stored in broker) |
| Retryable | No | Yes (configurable policy) |
| Monitorable | No | Yes (Flower dashboard) |
| Independently scalable | No | Yes (add more worker processes) |
| Distributed (multiple machines) | No | Yes |

### Task Chain for Deploy

```python
# workers/deploy_tasks.py
from celery import chain
from workers.celery_app import celery_app

@celery_app.task(bind=True, max_retries=2, default_retry_delay=5)
def clone_or_pull_task(self, app_id: int):
    # call services.git_service.clone_or_pull(...)
    ...

@celery_app.task(bind=True, max_retries=1)
def docker_build_task(self, app_id: int):
    # call services.docker_service.build(...)
    ...

@celery_app.task(bind=True, max_retries=0)
def docker_run_task(self, app_id: int):
    # call services.docker_service.run(...)
    ...

@celery_app.task
def nginx_setup_task(app_id: int):
    # call services.nginx_service.write_conf(...)
    ...

def trigger_deploy(app_id: int) -> str:
    task = chain(
        clone_or_pull_task.s(app_id),
        docker_build_task.s(app_id),
        docker_run_task.s(app_id),
        nginx_setup_task.s(app_id),
    ).apply_async()
    return task.id
```

### Celery Beat Schedule

```python
# workers/celery_app.py
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    "purge-old-logs": {
        "task": "workers.maintenance_tasks.purge_old_logs_task",
        "schedule": crontab(hour=2, minute=0),  # 2am daily
    },
    "snapshot-metrics": {
        "task": "workers.maintenance_tasks.snapshot_metrics_task",
        "schedule": 60.0,  # every 60 seconds
    },
}
```

### Monitoring Celery
Run `pip install flower` and `celery -A workers.celery_app flower` — you get a web UI showing queued tasks, active workers, and task history. This is how you debug "why is this deploy stuck".

---

## 6. Per-Container Resource Monitoring

v1 monitors the host. v2 monitors each deployed container individually.

### Source: docker stats
```bash
docker stats --no-stream --format '{{json .}}' {container_id}
```
Returns: CPU %, memory usage/limit, network I/O, block I/O.

### Flow

```
Celery Beat: snapshot_metrics_task runs every 60s
  → for each RUNNING app:
      → docker stats --no-stream {container_id}
      → write to MongoDB container_metrics
      → redis.publish("pubsub:metrics:{app_id}", json_payload)

FastAPI WS /ws/apps/{id}/metrics:
  → subscribe to Redis pubsub:metrics:{app_id}
  → relay each message to connected browser
```

### What to Expose in the Dashboard
For each running app:
- CPU: live gauge + 1-hour line chart (from MongoDB history)
- Memory: live gauge + 1-hour line chart
- Network: cumulative sent/received since container start
- Uptime: `docker inspect --format '{{.State.StartedAt}}'` → calculate duration

This is the "environmental usage" feature you specified.

---

## 7. Custom Subdomain System

### Availability Check Flow
```
GET /subdomains/check?name=myapp
→ validate format (regex)
→ check not reserved
→ SELECT 1 FROM apps WHERE subdomain = 'myapp' LIMIT 1
→ return { "available": true/false }
```

### Change Flow (safe, atomic)
```
PATCH /apps/{id}/subdomain { "subdomain": "myapp" }
→ validate format
→ not reserved check
→ SELECT FOR UPDATE on apps WHERE id={id}  ← prevents concurrent changes to same app
→ uniqueness check (exclude self)
→ status check (must be STOPPED or CREATED)
→ BEGIN TRANSACTION:
    UPDATE apps SET subdomain='myapp' WHERE id={id}
→ COMMIT
→ os.remove(old_conf_file)
→ write_new_conf_file
→ nginx -s reload
```

Why the transaction + separate file ops? The DB update is atomic; if Nginx reload fails, the DB already has the new subdomain and you can retry the nginx step without DB inconsistency.

### Reserved Subdomain List
Keep this in config, not hardcoded in validation:
```python
# core/config.py
RESERVED_SUBDOMAINS: set[str] = {
    "www", "api", "admin", "mail", "ftp", "smtp",
    "static", "assets", "docs", "status", "dashboard"
}
```

---

## 8. Scalability Patterns to Apply

These are system design patterns you've implemented (or will implement) — know them by name.

### Pattern 1: Stateless API + External State
**What:** API servers hold no in-memory state. All state is in PostgreSQL (durable) or Redis (ephemeral).
**Why:** You can run 2, 4, or 10 API server instances behind a load balancer. Any instance can handle any request.
**In gitDeploy:** JWT auth is stateless (signature-verified). Sessions are not stored in API memory. Deploy tasks live in Celery broker, not in API memory.

### Pattern 2: Message Broker (Task Queue)
**What:** API server publishes a task to Redis (broker). Celery worker picks it up and executes it.
**Why:** Decouples request handling from long-running work. API returns immediately (202 Accepted). Worker does the work. This is how every deploy pipeline system works (GitHub Actions, Railway, Render).
**In gitDeploy:** `POST /apps/{id}/deploy` → queues Celery task → returns `{ task_id }`. Client polls or watches WS for status.

### Pattern 3: Fan-Out via Pub/Sub
**What:** One producer publishes to a channel. N consumers each receive the message independently.
**Why:** Allows multiple WebSocket clients to watch the same log stream without the producer knowing how many clients are connected.
**In gitDeploy:** Celery worker publishes log lines to Redis `pubsub:logs:{app_id}`. Each connected browser WebSocket handler subscribes independently.

### Pattern 4: Read-Through Cache
**What:** On read: check Redis first. If miss, query DB, store in Redis with TTL, return result.
**Why:** Reduces DB load for frequently-read data.
**Where to apply in gitDeploy:** App detail endpoint — cache `app:detail:{id}` for 5s. Host metrics snapshot — cache for 3s to serve multiple simultaneous WS subscribers from one psutil call.

### Pattern 5: Separate Read and Write Models (CQRS-lite)
**What:** Different DB optimized for different access patterns.
**In gitDeploy:** PostgreSQL is your write-optimized relational store. MongoDB is your read-optimized append store for logs. Redis is your read-optimized ephemeral cache. Three databases, each for what it's best at.

### Pattern 6: Rate Limiting via Sliding Window
```python
# Redis INCR + EXPIRE pattern
async def check_rate_limit(redis, key: str, limit: int, window_seconds: int) -> bool:
    current = await redis.incr(key)
    if current == 1:
        await redis.expire(key, window_seconds)
    return current <= limit
```
Apply at login (5/min/IP), register (3/min/IP), OTP verify (5/min/user).

### Pattern 7: Idempotent Operations
**What:** Running the same operation twice produces the same result as running it once.
**In gitDeploy:** `git pull` is idempotent. `docker build` with the same Dockerfile produces the same image. Port allocation is idempotent — if the app already has a port, reuse it. Nginx config write is idempotent — overwrite if exists.

### Pattern 8: Dead Letter Queue (Future)
**What:** Tasks that fail after all retries go to a "dead letter" queue for manual inspection.
**Why:** Silent failures are worse than visible failures.
**Add this:** Configure Celery `task_reject_on_worker_lost = True` and a `CELERY_TASK_ROUTES` with a dedicated error queue. Set up an alert when tasks land there.

---

## 9. System Design Concepts You Implemented

Use these when asked "what system design concepts does this project demonstrate?"

### 1. Horizontal Scalability (Stateless Service)
You separated application state from service state. The API can scale horizontally. This is the foundation of every cloud-native service.

### 2. Async I/O at Every Layer
FastAPI → asyncpg (PostgreSQL) → Motor (MongoDB) → aioredis (Redis). No blocking calls on the event loop. This is what allows one Python process to handle hundreds of concurrent connections.

### 3. Event-Driven Architecture (Lightweight)
Deploy trigger → task event → broker → worker → status update events. The API doesn't know when the deploy finishes; it's event-driven. The worker publishes status changes. This is how all modern CI/CD systems work.

### 4. Port Allocation with Distributed Locking
DB-level `SELECT FOR UPDATE` + Redis `SETNX` + OS socket check. This is a real distributed systems problem: how do you allocate a unique resource (port) when multiple processes compete concurrently? Defense in depth: three independent checks.

### 5. Real-Time Push via WebSocket + Pub/Sub
Pure server-push model — no polling. WebSocket kept alive by server sending data. This is the architecture Slack, Discord, and Grafana use for live dashboards.

### 6. Nginx as Dynamic Reverse Proxy
Most people think Nginx config is static. You're generating config files programmatically and hot-reloading (`nginx -s reload`) without downtime. This is how platforms like Heroku and Vercel expose user apps at custom subdomains.

### 7. Polyglot Persistence
Using the right database for each access pattern. PostgreSQL for relational ACID data. MongoDB for time-series log data. Redis for ephemeral/cache/pub-sub data. This is a mature architecture pattern discussed in every system design interview.

### 8. Containerized Application Management
You're using Docker as a runtime, not just as a packaging tool. You manage the container lifecycle (build, run, stop, remove) programmatically. You read `docker stats` for runtime metrics. This is what Kubernetes does at scale.

---

## 10. New Features Roadmap

Here are features to add, in priority order. Build them after the core v2 is stable.

### High Priority

**GitHub Webhook Auto-Deploy**
Users register a webhook URL in their GitHub repo settings. On push to the configured branch, GitHub POSTs to `/api/v1/apps/{id}/webhook`. You trigger the deploy automatically.
- Requires: webhook secret verification (`X-Hub-Signature-256` header HMAC check)
- System design concept: Event-driven deployment, webhook security

**Deploy Status Polling Endpoint**
```
GET /apps/{id}/deploys/latest  → { task_id, status, progress_percent, current_step }
```
Some clients can't use WebSocket. Give them a REST polling alternative.

**Environment Variable Encryption**
Currently env vars are stored as plaintext JSONB. Use `cryptography.fernet` to encrypt values at rest. Decrypt only when passing to `docker run`.
- System design concept: Encryption at rest, key management

**Health Check per App**
After deploy, hit `{subdomain}.gitdeploy.online/health` (or user-configured path) every 30s. If it fails 3 times, set status = UNHEALTHY and notify.
- Celery beat task + status enum expansion
- System design concept: Active health checking, circuit breaker

### Medium Priority

**Rollback**
Keep the last 3 Docker images for each app. On rollback, `docker run` the previous image. No re-build needed.
- Requires: track image tags in DB, image retention policy

**Resource Quotas Enforcement**
Use Docker `--memory` and `--cpus` flags on `docker run` based on user's billing tier. Prevents one user's app from consuming the entire host.
- System design concept: Resource isolation, multi-tenancy

**App Logs Download**
`GET /apps/{id}/logs/export?from=&to=` returns a streaming `.txt` file.
- FastAPI `StreamingResponse` with `media_type="text/plain"`
- System design concept: Streaming large responses

**Uptime Tracking**
Record when each app transitions to RUNNING and when it stops. Calculate uptime percentage over last 30 days.
- Add `uptime_events` table: `{ app_id, event: 'up'|'down', timestamp }`
- System design concept: SLA tracking, event sourcing (lightweight)

### Lower Priority (Post-interview)

**Multi-Region Support**
Sidecar agents on multiple servers. Central API dispatches deploys to the nearest/least-loaded sidecar. Classic distributed systems problem.

**Private Repo Support**
OAuth flow with GitHub. Store encrypted access token per user. Pass token to git clone via `https://{token}@github.com/...`.

**Custom Domain (BYOD)**
User provides their own domain. You issue Let's Encrypt cert via certbot. More complex Nginx management.

**Billing**
Stripe integration. `billing_type: paid` unlocks quotas. Metered billing on compute-hours.

---

## 11. Interview Talking Points

When interviewers ask about gitDeploy, here are the precise talking points mapped to common questions.

### "Walk me through how a deploy works."
"When a user calls POST /apps/{id}/deploy, the API validates ownership, then enqueues a Celery task chain into Redis. The API returns immediately with a task ID. The Celery worker picks up the chain: first it clones or pulls the GitHub repo, then builds the Docker image, allocates a free port using a database-level SELECT FOR UPDATE lock plus a socket bind check, runs the container, and writes the Nginx config. Each step publishes its stdout/stderr to a Redis Pub/Sub channel. The user's browser WebSocket connection subscribes to that channel and receives real-time log lines. Each step also writes an audit row to deployment_logs in PostgreSQL, so the user can see the complete step-by-step history later."

### "How do you handle concurrent deployments safely?"
"Port allocation is a distributed resource allocation problem. I use three layers: first, a PostgreSQL SELECT FOR UPDATE on existing port assignments — this serializes concurrent DB reads so two workers can't both see the same 'free' port. Second, a Redis SETNX lock with a 10-second TTL as a secondary guard for the window between the DB read and the OS bind. Third, an actual socket.bind() call to verify the OS hasn't assigned the port through some other mechanism. Three independent checks — defense in depth."

### "Why WebSocket instead of polling?"
"Polling has a tradeoff: short interval wastes bandwidth on empty responses; long interval means stale data. For a deployment log stream that can have hundreds of lines per second, polling is unusable. WebSocket gives you a persistent full-duplex connection — the server pushes data exactly when it's available, with no client overhead between messages. The specific pattern here is that the WebSocket handler doesn't hold the subprocess — it subscribes to a Redis Pub/Sub channel. The Celery worker holds the subprocess and publishes each line. This decouples the log producer from the log consumer and allows multiple browser tabs to watch the same build."

### "How would you scale this to 10,000 users?"
"The architecture is already horizontally scalable. The API servers are stateless — all shared state is in PostgreSQL and Redis. I'd put 3–5 API instances behind an Nginx load balancer. Celery workers scale independently — I'd add more worker processes or machines as deploy throughput grows. The single-machine Nginx config management becomes the bottleneck: at scale, I'd move to a Kubernetes Ingress controller that generates routing config from a CRD, eliminating the nginx file-write coupling. The databases would need read replicas for PostgreSQL and a MongoDB replica set. Redis would need Sentinel or Cluster for HA."

### "What would you do differently?"
"A few things. First, I'd encrypt env vars at rest from the start — it's a security gap that's painful to retrofit. Second, I'd design the pipeline steps as idempotent from the beginning — so that retrying a failed deploy from step N doesn't re-clone or re-build. Third, I'd add contract tests (pact) between the API and frontend early — schema drift is a time sink. Fourth, I wouldn't use SQLite at all — the locking issues with concurrent writers should have been obvious from the design phase."

### "What is your logging strategy?"
"Three layers. First, application logs — structured JSON to stdout using python-json-logger, with a ContextVar-based request_id that automatically propagates through every log call in a request's async context. Second, deployment audit logs — one PostgreSQL row per pipeline step per deploy, queryable by users to debug their build failures. Third, container runtime logs — MongoDB, one document per log line, indexed by app_id and timestamp, with a TTL index that auto-purges after 30 days. The three layers serve different consumers: ops team reads JSON logs via Loki, users query deployment history via API, developers tail their app logs via WebSocket."
