
# 🛠️ Custom Error System — gitDeploy

## Purpose

Create a centralized custom error framework for the entire codebase.
Each error has a **unique integer code** and an **HTTP status code**, so instead of storing full error strings on every failure, we store only the compact `error_code` + `status_code` in an `ErrorLog` table.

This lets us:

- **Understand which error occurred** by looking up the code.
- **Know when it occurred** via the timestamp.
- **Drastically reduce storage** — an integer instead of a long string.
- **Query and filter** errors by code, app, or date range.

---

## 📋 Error Code Catalog

| Code     | Name                              | HTTP Status | Source File  | Scenario                                                    |
| -------- | --------------------------------- | ----------- | ------------ | ----------------------------------------------------------- |
| **1000** | `INVALID_REPO_URL`                | 400         | `deploy.py`  | Repo URL doesn't start with `https://github.com/`          |
| **1001** | `MALFORMED_REPO_URL`              | 400         | `deploy.py`  | URL path too short (less than 2 parts)                      |
| **1002** | `UNEXPECTED_REPO_URL_FORMAT`      | 400         | `deploy.py`  | URL has more than 2 path parts                              |
| **1003** | `GITHUB_API_CONNECTION_FAILED`    | 502         | `deploy.py`  | `requests.RequestException` when calling GitHub API         |
| **1004** | `REPO_NOT_FOUND_OR_PRIVATE`       | 404         | `deploy.py`  | GitHub API returns 404                                      |
| **1005** | `GITHUB_API_ERROR`                | 502         | `deploy.py`  | GitHub API returns non-200 status                           |
| **1006** | `PRIVATE_REPO_NOT_SUPPORTED`      | 403         | `deploy.py`  | Repo JSON says `private: true`                              |
| **1007** | `GIT_CLONE_FAILED`                | 500         | `deploy.py`  | `git clone` returns non-zero exit code                      |
| **1008** | `GIT_PULL_FAILED`                 | 500         | `deploy.py`  | `git pull` returns non-zero exit code                       |
| **2000** | `DOCKERFILE_NOT_FOUND`            | 400         | `docker.py`  | Dockerfile not found at expected path                       |
| **2001** | `DOCKER_IMAGE_REMOVAL_FAILED`     | 500         | `docker.py`  | `docker rmi` fails                                         |
| **2002** | `DOCKER_BUILD_FAILED`             | 500         | `docker.py`  | `docker build` exits with non-zero code                     |
| **2003** | `DOCKER_IMAGE_NOT_FOUND`          | 500         | `docker.py`  | Image doesn't exist when trying to `docker run`             |
| **2004** | `DOCKER_CONTAINER_REMOVAL_FAILED` | 500         | `docker.py`  | Error removing existing container                           |
| **2005** | `DOCKER_RUN_FAILED`               | 500         | `docker.py`  | `docker run` returns non-zero exit code                     |
| **3000** | `APP_NOT_FOUND`                   | 404         | `apps.py`    | App ID doesn't exist in DB                                  |
| **3001** | `APP_CREATION_FAILED`             | 500         | `apps.py`    | DB error during app creation                                |
| **3002** | `DEPLOY_GIT_PERMISSION_DENIED`    | 403         | `apps.py`    | PermissionError during deploy git step                      |
| **3003** | `DEPLOY_GIT_VALIDATION_FAILED`    | 400         | `apps.py`    | ValueError/RuntimeError during deploy git step              |
| **3004** | `DEPLOY_DOCKER_BUILD_ERROR`       | 500         | `apps.py`    | RuntimeError during docker build                            |
| **3005** | `DEPLOY_DOCKER_RUN_ERROR`         | 500         | `apps.py`    | Any exception during docker run                             |
| **4000** | `DATABASE_CONNECTION_FAILED`      | 500         | `database.py`| Engine/session creation failure                             |
| **5000** | `INTERNAL_SERVER_ERROR`           | 500         | —            | Catch-all for unexpected errors                             |

---

## 🔢 Code Range Convention

| Range       | Category                    |
| ----------- | --------------------------- |
| `1000–1999` | Git / Repository Validation |
| `2000–2999` | Docker Operations           |
| `3000–3999` | App / Route-level Logic     |
| `4000–4999` | Database / Infrastructure   |
| `5000–5999` | Catch-all / Internal        |

> New errors should be added in the appropriate range to maintain consistency.

---

## 📁 Folder Structure

```text
Errors/
├── __init__.py              # Re-exports all error classes + log_error
├── app_errors.py            # AppBaseError + all 20 custom error classes
├── error_logger.py          # log_error() utility
└── exception_handler.py     # FastAPI global exception handler
```

---

## 📦 Error Model (SQLAlchemy)

Add to `models.py`:
```python
class ErrorLog(Base):
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    error_code = Column(Integer, nullable=False, index=True)
    status_code = Column(Integer, nullable=False)
    app_id = Column(Integer, nullable=True, index=True)
    context = Column(Text, nullable=True)  # optional short context, e.g. repo_url or container name
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
```


> Instead of storing the full error string every time, you store only the `error_code`
> (e.g. `1004`) and `status_code` (e.g. `404`). The error code maps back to a
> well-known error name and message via the error class. The optional `context` field
> lets you store a small identifier (like `app_id` or `repo_url`) without the full traceback.

---

## 🧱 Base Exception & All Custom Error Classes

**File: `Errors/app_errors.py`**

```python
"""
Custom Error System for gitDeploy
──────────────────────────────────
Each error has:
  • error_code  – unique integer, used for storage & lookup
  • message     – human-readable default message
  • status_code – suggested HTTP status code
"""


class AppBaseError(Exception):
    """Base class for all custom application errors."""
    error_code: int = 5000
    message: str = "An unexpected internal error occurred."
    status_code: int = 500

    def __init__(self, detail: str | None = None, context: str | None = None):
        self.detail = detail or self.message
        self.context = context  # e.g. repo_url, app_id, container_name
        super().__init__(self.detail)

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "status_code": self.status_code,
            "message": self.detail,
        }


# ──────────────────────────────────────────────
#  1xxx  –  Git / Repository Validation Errors
# ──────────────────────────────────────────────

class InvalidRepoURLError(AppBaseError):
    error_code = 1000
    message = "Only GitHub repositories are supported."
    status_code = 400


class MalformedRepoURLError(AppBaseError):
    error_code = 1001
    message = "Invalid GitHub repository URL — path too short."
    status_code = 400


class UnexpectedRepoURLFormatError(AppBaseError):
    error_code = 1002
    message = "Invalid GitHub repository URL — expected format: https://github.com/owner/repo.git"
    status_code = 400


class GitHubAPIConnectionError(AppBaseError):
    error_code = 1003
    message = "Failed to connect to GitHub API."
    status_code = 502


class RepoNotFoundOrPrivateError(AppBaseError):
    error_code = 1004
    message = "Repository

**File: `Errors/error_logger.py`**
```

python """ Utility to persist error occurrences into the ErrorLog table. """
import logging from sqlalchemy.orm import Session from models import ErrorLog from Errors.app_errors import AppBaseError
logger = logging.getLogger(name)
def log_error(db: Session, error: AppBaseError, app_id: int | None = None) -> ErrorLog: """ Persist an AppBaseError instance to the error_logs table.
Args:
    db: Active SQLAlchemy session.
    error: The custom error instance.
    app_id: Optional related application ID.

Returns:
    The created ErrorLog record.
"""
entry = ErrorLog(
    error_code=error.error_code,
    status_code=error.status_code,
    app_id=app_id,
    context=error.context,
)
db.add(entry)
db.commit()
db.refresh(entry)
logger.info(
    "ErrorLog #%s recorded — code=%s status=%s app_id=%s",
    entry.id,
    entry.error_code,
    entry.status_code,
    app_id,
)
return entry``` 

---

## 📦 Package Init

**File: `Errors/__init__.py`**
```

python from Errors.app_errors import ( AppBaseError, InvalidRepoURLError, MalformedRepoURLError, UnexpectedRepoURLFormatError, GitHubAPIConnectionError, RepoNotFoundOrPrivateError, GitHubAPIError, PrivateRepoNotSupportedError, GitCloneError, GitPullError, DockerfileNotFoundError, DockerImageRemovalError, DockerBuildError, DockerImageNotFoundError, DockerContainerRemovalError, DockerRunError, AppNotFoundError, AppCreationError, DeployGitPermissionDeniedError, DeployGitValidationError, DeployDockerBuildError, DeployDockerRunError, DatabaseConnectionError, InternalServerError, )
from Errors.error_logger import log_error``` 

---

## 🌐 FastAPI Global Exception Handler

**File: `Errors/exception_handler.py`**
```

python """ FastAPI global exception handler for AppBaseError. """
import logging from fastapi import Request from fastapi.responses import JSONResponse from Errors.app_errors import AppBaseError from Errors.error_logger import log_error from database import SessionLocal
logger = logging.getLogger(name)
async def app_error_handler(request: Request, exc: AppBaseError) -> JSONResponse: """ Catches any AppBaseError raised anywhere in the app, logs it to the DB, and returns a structured JSON response. """ # Attempt to extract app_id from path params (e.g. /apps/{app_id}/deploy) app_id = request.path_params.get("app_id")
db = SessionLocal()
try:
    log_error(db, exc, app_id=int(app_id) if app_id else None)
except Exception as log_exc:
    logger.error("Failed to persist error log: %s", log_exc)
finally:
    db.close()

return JSONResponse(
    status_code=exc.status_code,
    content={
        "error_code": exc.error_code,
        "message": exc.detail,
    },
)``` 

---

## 🔌 Register Handler in `main.py`
```

python from fastapi import FastAPI from routes import apps from Errors.app_errors import AppBaseError from Errors.exception_handler import app_error_handler
app = FastAPI() app.include_router(apps.router) app.add_exception_handler(AppBaseError, app_error_handler)
... rest of main.py ...``` 

---

## 🔄 Usage Example — `services/deploy.py`
```

python from Errors import ( InvalidRepoURLError, MalformedRepoURLError, UnexpectedRepoURLFormatError, GitHubAPIConnectionError, RepoNotFoundOrPrivateError, GitHubAPIError, PrivateRepoNotSupportedError, GitCloneError, GitPullError, )
def validate_github_repo(repo_url: str) -> None: if not repo_url.startswith("https://github.com/"): raise InvalidRepoURLError(context=repo_url)
# ... parse URL ...

if len(parts) < 2:
    raise MalformedRepoURLError(context=repo_url)

if len(parts) > 2:
    raise UnexpectedRepoURLFormatError(
        detail=f"Expected: https://github.com/owner/repo.git. Found: {repo_url}",
        context=repo_url,
    )

try:
    response = requests.get(api_url, timeout=5)
except requests.RequestException as e:
    raise GitHubAPIConnectionError(detail=str(e), context=repo_url)

if response.status_code == 404:
    raise RepoNotFoundOrPrivateError(context=repo_url)

if response.status_code != 200:
    raise GitHubAPIError(context=repo_url)

if repo_info.get("private"):
    raise PrivateRepoNotSupportedError(context=repo_url)``` 

---

## ✅ Before vs After

| Before                                         | After                                                     |
| ---------------------------------------------- | --------------------------------------------------------- |
| Full error strings stored/returned             | Compact `error_code` (int) + `status_code` in `ErrorLog` |
| Scattered `HTTPException` with ad-hoc messages | Centralized error classes with consistent codes           |
| No error audit trail                           | Every error logged in `error_logs` table with timestamp   |
| Hard to search/filter errors                   | Query by `error_code`, `app_id`, or date range            |
| Inconsistent HTTP status codes                 | Each error class owns its `status_code`                   |
```

