import re
from pydantic import BaseModel, field_validator
from typing import Optional

_SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9._\-/]+$")
_BRANCH_RE = re.compile(r"^[a-zA-Z0-9._\-/]+$")


class AppDeployRequestModel(BaseModel):
    branch: Optional[str] = None
    source_dir: Optional[str] = None
    dockerfile_path: Optional[str] = None
    env: Optional[dict] = None
    force_rebuild: Optional[bool] = False
    build_args: Optional[dict] = None
    clear_cache: Optional[bool] = False

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and (not _BRANCH_RE.match(v) or ".." in v):
            raise ValueError("Invalid branch name")
        return v

    @field_validator("source_dir", "dockerfile_path")
    @classmethod
    def validate_path(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and (".." in v or v.startswith("/") or not _SAFE_PATH_RE.match(v)):
            raise ValueError("Invalid path: must be relative, no '..' allowed")
        return v

    @field_validator("env")
    @classmethod
    def validate_env(cls, v: Optional[dict]) -> Optional[dict]:
        if v is not None:
            for key, val in v.items():
                if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
                    raise ValueError(f"Invalid env var name: {key}")
                if "\n" in str(val) or "\r" in str(val):
                    raise ValueError(f"Env var value for {key} contains newlines")
        return v