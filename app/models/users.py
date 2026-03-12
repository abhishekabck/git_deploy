from app.database import Base
from sqlalchemy import Column, String, Integer, Enum, DateTime
from app.constants import BillingType, UserRoles
from app.models.timestatus_mixin import TimeStatusMixin



class Users(Base, TimeStatusMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key = True, index = True, nullable = False, autoincrement = True)
    username = Column(String, unique = True, index = True, nullable = False)
    hashed_password = Column(String, nullable = False)
    email = Column(String, unique = True, index = True, nullable = False)
    billing_type = Column(Enum(BillingType), nullable = False, default = BillingType.FREE)
    role = Column(Enum(UserRoles), nullable=False, default=UserRoles.USER)