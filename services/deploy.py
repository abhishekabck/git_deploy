import subprocess
import requests
import logging
from urllib.parse import urlparse
from pathlib import Path

logger = logging.getLogger(__name__)



def validate_github_repo(repo_url: str) -> None:
    logger.debug("Validating GitHub repository URL: %s", repo_url)
    if not repo_url.startswith("https://github.com/"):
        logger.warning("Validation failed: %s is not a GitHub URL", repo_url)
        raise ValueError("Only GitHub repositories are supported")

    parsed = urlparse(repo_url)
    parts = parsed.path.strip("/").split("/")

    if len(parts) < 2:
        logger.warning("Validation failed: URL path is too short for %s", repo_url)
        raise ValueError("Invalid GitHub repository URL")

    owner, repo = parts[0], parts[1].replace(".git", "")

    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    logger.debug("Checking repository metadata via GitHub API: %s", api_url)
    try:
        response = requests.get(api_url, timeout=5)
    except requests.RequestException as e:
        logger.error("Connection error while calling GitHub API for %s: %s", repo_url, str(e))
        raise RuntimeError(f"Failed to connect to GitHub API: {e}")

    if response.status_code == 404:
        logger.error("Repository not found or is private: %s", repo_url)
        raise PermissionError("Repository does not exist or is private")

    if response.status_code != 200:
        logger.error("GitHub API returned status code %s for %s", response.status_code, api_url)
        raise RuntimeError("Failed to fetch repository metadata")

    repo_info = response.json()
    if repo_info.get("private"):
        logger.warning("Repository %s is marked as private in API response", repo_url)
        raise PermissionError("Private repositories are not supported")
    
    logger.info("GitHub repository %s/%s validated successfully", owner, repo)


def clone_or_pull_repo(repo_url: str, app_dir: Path) -> None:
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
    else:
        logger.info("Executing: git pull in %s", app_dir)
        result = subprocess.run(
            ["git", "pull"],
            cwd=app_dir,
            capture_output=True,
            text=True
        )

    if result.returncode != 0:
        logger.error("Git command failed with exit code %s. Error: %s", result.returncode, result.stderr)
        raise RuntimeError(result.stderr.strip())
    
    logger.info("Git operation finished successfully for %s", repo_url)
