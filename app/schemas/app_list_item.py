from pydantic import BaseModel

class AppListItem(BaseModel):
    id: int
    subdomain: str
    internal_port: int
    status: str
    build_path: str
    repo_url: str