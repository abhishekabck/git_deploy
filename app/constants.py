import enum
class AppStatus(enum.Enum):
    CREATED = "created"
    RUNNING = "running"
    ERROR = "error"
    PREPARED = "prepared"
