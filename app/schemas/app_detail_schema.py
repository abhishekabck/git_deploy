from .app_list_item import AppListItem
from datetime import datetime

class AppDetail(AppListItem):
    id: int
    repo_url: str
    internal_port: int
    container_port: int
    subdomain: str
    branch: str
    build_path: str
    dockerfile_path: str
    status: str
    created_at: datetime
    updated_at: datetime