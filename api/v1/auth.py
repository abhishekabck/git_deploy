import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from starlette import status

from app.constants import BillingType, UserRoles
from app.dependencies import get_db
from app.models.users import Users
from app.schemas.auth_schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
)
from app.utils import hash_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_COOKIE = "refresh_token"
_REFRESH_COOKIE_PATH = "/api/v1/auth/refresh"
_REFRESH_MAX_AGE = 7 * 24 * 60 * 60  # 7 days in seconds


# ── Register ──────────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    logger.info("Register attempt for username=%s email=%s", data.username, data.email)

    conflict = (
        db.query(Users)
        .filter((Users.email == data.email) | (Users.username == data.username))
        .first()
    )
    if conflict:
        field = "Email" if conflict.email == data.email else "Username"
        logger.warning("Registration conflict: %s already exists", field)
        raise HTTPException(status_code=409, detail=f"{field} already registered")

    user = Users(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
        role=UserRoles.USER,
        billing_type=BillingType.FREE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("User %s registered successfully (id=%s)", user.username, user.id)

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role.value,
        "billing_type": user.billing_type.value,
    }


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/login", status_code=status.HTTP_200_OK, response_model=TokenResponse)
def login(data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    logger.info("Login attempt for email=%s", data.email)

    user = authenticate_user(data.email, data.password, db)
    logger.info("User %s authenticated (id=%s)", user.username, user.id)

    token_data = {"sub": str(user.id), "username": user.username, "role": user.role.value}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token({"sub": str(user.id)})

    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=False,       # set True in production (HTTPS)
        samesite="lax",
        max_age=_REFRESH_MAX_AGE,
        path=_REFRESH_COOKIE_PATH,
    )

    return {"access_token": access_token, "token_type": "bearer"}


# ── Refresh ───────────────────────────────────────────────────────────────────

@router.post("/refresh", status_code=status.HTTP_200_OK, response_model=TokenResponse)
def refresh(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(_REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Refresh token missing")

    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("sub")
    user = db.query(Users).filter(Users.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    token_data = {"sub": str(user.id), "username": user.username, "role": user.role.value}
    access_token = create_access_token(token_data)
    logger.info("Access token refreshed for user_id=%s", user_id)

    return {"access_token": access_token, "token_type": "bearer"}


# ── Logout ────────────────────────────────────────────────────────────────────

@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(response: Response):
    response.delete_cookie(key=_REFRESH_COOKIE, path=_REFRESH_COOKIE_PATH)
    return {"message": "Logged out successfully"}


# ── Current user ──────────────────────────────────────────────────────────────

@router.get("/me", status_code=status.HTTP_200_OK, response_model=UserResponse)
def me(current_user: Users = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role.value,
        "billing_type": current_user.billing_type.value,
    }
