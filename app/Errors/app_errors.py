"""
Custom Error System for gitDeploy
──────────────────────────────────
Each error has:
  • error_code  – unique integer, used for storage & lookup
  • message     – human-readable default message
  • status_code – suggested HTTP status code
"""
from __future__ import annotations


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
    message = "Repository does not exist or is private."
    status_code = 404


class GitHubAPIError(AppBaseError):
    error_code = 1005
    message = "Failed to fetch repository metadata from GitHub."
    status_code = 502


class PrivateRepoNotSupportedError(AppBaseError):
    error_code = 1006
    message = "Private repositories are not supported."
    status_code = 403


class GitCloneError(AppBaseError):
    error_code = 1007
    message = "Git clone operation failed."
    status_code = 500


class GitPullError(AppBaseError):
    error_code = 1008
    message = "Git pull operation failed."
    status_code = 500


# ──────────────────────────────────────────────
#  2xxx  –  Docker Errors
# ──────────────────────────────────────────────

class DockerfileNotFoundError(AppBaseError):
    error_code = 2000
    message = "Dockerfile not found at the specified path."
    status_code = 400


class DockerImageRemovalError(AppBaseError):
    error_code = 2001
    message = "Failed to remove existing Docker image."
    status_code = 500


class DockerBuildError(AppBaseError):
    error_code = 2002
    message = "Docker build failed."
    status_code = 500


class DockerImageNotFoundError(AppBaseError):
    error_code = 2003
    message = "Docker image does not exist."
    status_code = 500


class DockerContainerRemovalError(AppBaseError):
    error_code = 2004
    message = "Failed to remove existing Docker container."
    status_code = 500


class DockerRunError(AppBaseError):
    error_code = 2005
    message = "Failed to start Docker container."
    status_code = 500


# ──────────────────────────────────────────────
#  3xxx  –  App / Route-level Errors
# ──────────────────────────────────────────────

class AppNotFoundError(AppBaseError):
    error_code = 3000
    message = "App not found."
    status_code = 404


class AppCreationError(AppBaseError):
    error_code = 3001
    message = "Failed to create application record."
    status_code = 500


class DeployGitPermissionDeniedError(AppBaseError):
    error_code = 3002
    message = "Permission denied during Git operation for deployment."
    status_code = 403


class DeployGitValidationError(AppBaseError):
    error_code = 3003
    message = "Git validation failed during deployment."
    status_code = 400


class DeployDockerBuildError(AppBaseError):
    error_code = 3004
    message = "Docker build step failed during deployment."
    status_code = 500


class DeployDockerRunError(AppBaseError):
    error_code = 3005
    message = "Docker run step failed during deployment."
    status_code = 500


# ──────────────────────────────────────────────
#  4xxx  –  Database / Infrastructure Errors
# ──────────────────────────────────────────────

class DatabaseConnectionError(AppBaseError):
    error_code = 4000
    message = "Failed to connect to the database."
    status_code = 500


# ──────────────────────────────────────────────
#  5xxx  –  Catch-all
# ──────────────────────────────────────────────

class InternalServerError(AppBaseError):
    error_code = 5000
    message = "An unexpected internal error occurred."
    status_code = 500