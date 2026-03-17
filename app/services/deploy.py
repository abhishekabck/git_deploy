import subprocess
import requests
import logging
from urllib.parse import urlparse
from pathlib import Path
from app.Errors import (InvalidRepoURLError,
                        MalformedRepoURLError,
                        UnexpectedRepoURLFormatError,
                        GitHubAPIConnectionError,
                        RepoNotFoundOrPrivateError,
                        GitHubAPIError,
                        PrivateRepoNotSupportedError,
                        GitCloneError,
                        GitPullError,
                        GitBranchNotFoundError,
                        )

logger = logging.getLogger(__name__)



def validate_github_repo(repo_url: str) -> None:
    logger.debug("Validating GitHub repository URL: %s", repo_url)
    if not repo_url.startswith("https://github.com/"):
        logger.warning("Validation failed: %s is not a GitHub URL", repo_url)
        raise InvalidRepoURLError(context=repo_url)

    parsed = urlparse(repo_url)
    parts = parsed.path.strip("/").split("/")

    if len(parts) < 2:
        logger.error("Validation failed: URL path is too short for %s", repo_url)
        raise MalformedRepoURLError(context=repo_url)

    if len(parts) > 2:
        logger.error(f"Validation failed. repo_url: {repo_url} expected: https://github.com/owner/repo.git")
        raise UnexpectedRepoURLFormatError(
            detail=f"Invalid GitHub repository URL expected format: https://github.com/owner/repo.git.\nFound: {repo_url}",
            context=repo_url
        )

    owner, repo = parts[0], parts[1].replace(".git", "")

    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    logger.debug("Checking repository metadata via GitHub API: %s", api_url)
    try:
        response = requests.get(api_url, timeout=5)
    except requests.RequestException as e:
        logger.error("Connection error while calling GitHub API for %s: %s", repo_url, str(e))
        raise GitHubAPIConnectionError(detail=f"Failed to connect to GitHub API: {e}", context=repo_url)

    if response.status_code == 404:
        logger.error("Repository not found or is private: %s", repo_url)
        raise RepoNotFoundOrPrivateError(context=repo_url)

    if response.status_code != 200:
        logger.error("GitHub API returned status code %s for %s", response.status_code, api_url)
        raise GitHubAPIError(context=repo_url)

    repo_info = response.json()
    if repo_info.get("private"):
        logger.warning("Repository %s is marked as private in API response", repo_url)
        raise PrivateRepoNotSupportedError(context=repo_url)
    
    logger.info("GitHub repository %s/%s validated successfully", owner, repo)


def clone_or_pull_repo(repo_url: str, app_dir: Path, **kwargs) -> None:
    git_dir = app_dir / ".git"

    logger.debug("Checking for existing git repository in %s", app_dir)
    validate_github_repo(repo_url)

    if not git_dir.exists():
        logger.info("Executing: git clone %s .", repo_url)
        result = subprocess.run(
            ["git", "clone", repo_url, "."],
            cwd=app_dir,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logger.error("Git clone failed with exit code %s. Error: %s", result.returncode, result.stderr)
            raise GitCloneError(detail=result.stderr.strip(), context=repo_url)
    else:
        logger.info("Executing: git pull in %s", app_dir)
        result = subprocess.run(
            ["git", "pull"],
            cwd=app_dir,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logger.error("Git Pull failed with exit code %s. Error: %s", result.returncode, result.stderr)
            raise GitPullError(detail=result.stderr.strip(), context=repo_url)

    if kwargs.get("env"):
        env_vars = kwargs["env"]
        with open(app_dir / ".env", "w") as env_file:
            for key, value in env_vars.items():
                env_file.write(f"{key}={value}\n")
        logger.info("Env variable written in .env file.")
    logger.info("Git operation finished successfully for %s", repo_url)


def switch_to_branch(branch: str, app_dir: Path) -> None:
    logger.info("Switching to branch %s", branch)
    result = subprocess.run(
        ["git", "checkout", branch],
        cwd=app_dir,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        logger.error("Failed to switch to branch %s: %s", branch, result.stderr)
        raise GitBranchNotFoundError(detail=result.stderr.strip(), context=branch)
    logger.info("Branch %s switched successfully", branch)