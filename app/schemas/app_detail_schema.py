from .app_list_item import AppListItem
from datetime import datetime
from typing import Optional


class AppDetail(AppListItem):
    internal_port: Optional[int] = None
    dockerfile_path: str
    created_at: datetime
    updated_at: datetime
    env: dict