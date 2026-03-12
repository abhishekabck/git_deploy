from pydantic import BaseModel, Field, field_validator
import re


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(description="User email address")
    password: str = Field(min_length=8, description="Password (min 8 chars)")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not re.match(pattern, v):
            raise ValueError("Invalid email address")
        return v.lower()

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username may only contain letters, numbers, and underscores")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "username": "alice",
                "email": "alice@example.com",
                "password": "SecurePass1",
            }
        }
    }


class LoginRequest(BaseModel):
    email: str
    password: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "alice@example.com",
                "password": "SecurePass1",
            }
        }
    }


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    billing_type: str
