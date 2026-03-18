import re
from pydantic import BaseModel, Field, field_validator

_SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9._\-/]+$")
_BRANCH_RE = re.compile(r"^[a-zA-Z0-9._\-/]+$")


class AppCreateRequestModel(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    repo_url: str = Field(description="Repository URL")
    container_port: int = Field(gt=0, lt=65536, description="Port used by the Application for running")
    branch: str = Field(default="main", description="Branch to be deployed")
    source_dir: str = Field(default=".", description="Path to the source directory")
    dockerfile_path: str = Field(default="Dockerfile", description="Path to the Dockerfile")
    env: dict = Field(default_factory=dict, description="Environment variables for the application")

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, v: str) -> str:
        if not _BRANCH_RE.match(v) or ".." in v:
            raise ValueError("Invalid branch name")
        return v

    @field_validator("source_dir", "dockerfile_path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        if ".." in v or v.startswith("/") or not _SAFE_PATH_RE.match(v):
            raise ValueError("Invalid path: must be relative, no '..' allowed")
        return v

    @field_validator("env")
    @classmethod
    def validate_env(cls, v: dict) -> dict:
        for key, val in v.items():
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
                raise ValueError(f"Invalid env var name: {key}")
            if "\n" in str(val) or "\r" in str(val):
                raise ValueError(f"Env var value for {key} contains newlines")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "My App",
                "repo_url": "https://github.com/username/repo_name.git",
                "container_port": 8000,
                "branch": "main",
                "source_dir": ".",
                "dockerfile_path": "Dockerfile",
                "env": {"ENV_VAR_1": "value1", "ENV_VAR_2": "value2"}
            }
        }
    }
