# Git Deploy Implementation Plan (Current vs Next)

## 1) What is already done (brief)
- FastAPI app is initialized and router is wired (`/apps`).
- Database layer exists using SQLAlchemy + SQLite.
- App model includes deployment metadata (repo URL, ports, status, timestamps).
- Core app APIs exist:
  - Create app
  - List apps
  - Get app details
  - Trigger deployment
- Deployment service can:
  - Validate GitHub repository URL
  - Check repo visibility via GitHub API
  - Clone or pull repository
- Docker service can:
  - Build image from Dockerfile
  - Remove old conflicting image/container
  - Start container with internal:container port mapping
- Logging exists across routes and services for operational visibility.

## 2) What needs to be done (brief)
- Authentication/authorization for deployment endpoints.
- Proper lifecycle transition coverage (use `PREPARED` stage in actual flow).
- Branch/build-context support promised in README but not implemented.
- Automated tests (unit + API integration with mocked external dependencies).
- CI workflow for lint/test checks.
- Reverse proxy/routing for multiple deployed apps (e.g., Nginx-based).
- Operational hardening:
  - Better retry/backoff around GitHub/network failures
  - Safer cleanup/rollback behavior on partial deployment failures
  - Structured logs + correlation IDs
- Optional management UI and Cloudflare tunnel integration (roadmap items).

## 3) Practical improvement plan for current code

### Phase A — Reliability & correctness (highest priority)
1. **Lifecycle consistency**
   - Set status to `PREPARED` after successful clone/pull and before docker build.
   - Keep clear transitions: `CREATED -> PREPARED -> RUNNING` and `-> ERROR` on failure.
2. **Branch support**
   - Add `branch` in create/deploy request model.
   - Update clone/pull command to checkout target branch.
3. **Error mapping cleanup**
   - Normalize HTTP status mapping (e.g., 400 validation, 403 private repo, 500 infra/runtime).
4. **Port safety checks**
   - Validate that selected internal ports are free before running containers.

### Phase B — Testability
1. Add unit tests for:
   - `validate_github_repo`
   - docker image/container existence helpers
2. Add API tests for:
   - app create/list/detail
   - deploy failure paths (missing Dockerfile, private repo, bad repo URL)
3. Mock external systems (`requests`, `subprocess`) to keep tests deterministic.

### Phase C — Security & operations
1. Add API key/JWT auth for write operations (`POST /apps`, `POST /apps/{id}/deploy`).
2. Introduce rate limiting/basic abuse protection for deployment endpoint.
3. Add audit-style deployment history table (who, when, result, logs pointer).
4. Add CI pipeline to run lint + tests on every push/PR.

### Phase D — Platform features
1. Add reverse-proxy routing for subdomains.
2. Add optional web dashboard for app/deployment status.
3. Add Cloudflare tunnel integration for public exposure.

## 4) Quick code-level improvement suggestions
- `verify_app.py` currently posts only `repo_url`; it should include required `container_port` to match API schema.
- Consider replacing deprecated `sqlalchemy.ext.declarative.declarative_base` import path with modern SQLAlchemy 2 style import from `sqlalchemy.orm`.
- Add request/response schemas for deployment trigger endpoint for clearer API docs.
- Move hardcoded paths/config (`/opt/apps`, DB URL) into environment-configurable settings.

## 5) Suggested milestone tracking
- **Milestone 1 (MVP hardening):** Phase A + basic tests from Phase B
- **Milestone 2 (production baseline):** full Phase B + Phase C
- **Milestone 3 (platform expansion):** Phase D
