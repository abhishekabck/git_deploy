from pydantic import BaseModel
from typing import Optional

class AppDeployRequestModel(BaseModel):
    branch: Optional[str] = None
    source_dir: Optional[str] = None
    dockerfile_path: Optional[str] = None
    env: Optional[dict] = None
    force_rebuild: Optional[bool] = False
    build_args: Optional[dict] = None
    clear_cache: Optional[bool] = False