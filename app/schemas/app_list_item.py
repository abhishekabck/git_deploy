from pydantic import BaseModel

class AppListItem(BaseModel):
    id: int
    name: str
    subdomain: str
    container_port: int
    status: str
    build_path: str
    branch: str
    repo_url: str