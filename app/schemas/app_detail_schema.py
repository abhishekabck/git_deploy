from .app_list_item import AppListItem
from datetime import datetime

class AppDetail(AppListItem):
    internal_port: int
    dockerfile_path: str
    created_at: datetime
    updated_at: datetime
    env: dict