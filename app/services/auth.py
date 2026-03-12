from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import Config
from app.dependencies import get_db
from app.models.users import Users
from app.utils import verify_password

oauth2_bearer = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ── Token creation ────────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    payload = {
        **data,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=Config.ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm=Config.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    payload = {
        **data,
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + timedelta(days=Config.REFRESH_TOKEN_EXPIRE_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm=Config.JWT_ALGORITHM)


# ── Token decoding ────────────────────────────────────────────────────────────

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, Config.JWT_SECRET, algorithms=[Config.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ── User lookup from credentials ──────────────────────────────────────────────

def authenticate_user(email: str, password: str, db: Session) -> Users:
    user = db.query(Users).filter(Users.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return user


# ── FastAPI dependency: current user from Bearer token ────────────────────────

def get_current_user(
    token: str = Depends(oauth2_bearer),
    db: Session = Depends(get_db),
) -> Users:
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id: str = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.query(Users).filter(Users.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user
