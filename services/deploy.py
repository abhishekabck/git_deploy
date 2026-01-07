import subprocess
import requests
from urllib.parse import urlparse
from pathlib import Path



def validate_github_repo(repo_url: str) -> None:
    if not repo_url.startswith("https://github.com/"):
        raise ValueError("Only GitHub repositories are supported")

    parsed = urlparse(repo_url)
    parts = parsed.path.strip("/").split("/")

    if len(parts) < 2:
        raise ValueError("Invalid GitHub repository URL")

    owner, repo = parts[0], parts[1].replace(".git", "")

    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    response = requests.get(api_url, timeout=5)

    if response.status_code == 404:
        raise PermissionError("Repository does not exist or is private")

    if response.status_code != 200:
        raise RuntimeError("Failed to fetch repository metadata")

    if response.json().get("private"):
        raise PermissionError("Private repositories are not supported")




def clone_or_pull_repo(repo_url: str, app_dir: Path) -> None:
    git_dir = app_dir / ".git"

    validate_github_repo(repo_url)

    if not git_dir.exists():
        result = subprocess.run(
            ["git", "clone", repo_url, "."],
            cwd=app_dir,
            capture_output=True,
            text=True
        )
    else:
        result = subprocess.run(
            ["git", "pull"],
            cwd=app_dir,
            capture_output=True,
            text=True
        )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
