import enum
class AppStatus(enum.Enum):
    CREATED = "created"
    RUNNING = "running"
    ERROR = "error"
    PREPARED = "prepared"

class BillingType(enum.Enum):
    FREE = "free"
    PAID = "paid"

class UserRoles(enum.Enum):
    USER = "user"
    ADMIN = "admin"