from pydantic import BaseModel, Field
from typing import Optional

class AppRequestModel(BaseModel):
    repo_url: str = Field(description="Repository URL")
    branch: Optional[str] = Field(default="main", description="Branch to checkout")
    build_path: Optional[str] = Field(default=".", description="Path to build project from")
    dockerfile_path: Optional[str] = Field(default="Dockerfile", description="Dockerfile path")
    container_port: int = Field(gt=1023, lt=65536, description="Project Port")

    model_config = {
        "json_schema_extra": {
            "example": {
                "repo_url": "https://github.com/{username}/{repo_name}.git",
                "branch": "main",
                "build_path": ".",
                "dockerfile_path": "Dockerfile",
                "container_port": 8000,
            }
        }
    }
