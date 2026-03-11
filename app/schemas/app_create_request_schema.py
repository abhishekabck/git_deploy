from pydantic import BaseModel, Field

class AppCreateRequestModel(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    repo_url: str = Field(description="Repository URL")
    container_port: int = Field(description="Port used by the Application for running")
    branch: str = Field(default="main", description="Branch to be deployed")
    source_dir: str = Field(default=".", description="Path to the source directory")
    dockerfile_path: str = Field(default="Dockerfile", description="Path to the Dockerfile")
    env: dict = Field(default_factory=dict, description="Environment variables for the application")

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
