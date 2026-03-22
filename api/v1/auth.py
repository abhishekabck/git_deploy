import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.constants import BillingType, UserRoles
from app.dependencies import get_db
from app.models.users import Users
from app.schemas.auth_schemas import ForgotPasswordRequest, LoginRequest, RegisterRequest, ResendOtpRequest, ResetPasswordRequest, TokenResponse, UpdatePasswordRequest, UserResponse, VerifyOtpRequest
from app.services.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
)
from app.utils import hash_password, verify_password
from app.services.otp_manager import OTPManager
from app.services.redis_service import redis_delete, redis_get, redis_set
from app.services.CommunicationBuilder import CommunicationBuilder, PasswordResetTemplate
from app.config import Config

_otp_manager = OTPManager()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_COOKIE = "refresh_token"
_REFRESH_COOKIE_PATH = "/api/v1/auth/refresh"
_REFRESH_MAX_AGE = 7 * 24 * 60 * 60  # 7 days in seconds


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    logger.info("Register attempt for username=%s email=%s", data.username, data.email)

    result = await db.execute(
        select(Users).where(or_(Users.email == data.email, Users.username == data.username))
    )
    conflict = result.scalar_one_or_none()
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
    await db.commit()
    await db.refresh(user)
    logger.info("User %s registered successfully (id=%s)", user.username, user.id)

    await _otp_manager.send_otp(email=user.email, username=user.username)

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role.value,
        "billing_type": user.billing_type.value,
    }


@router.post("/login", status_code=status.HTTP_200_OK, response_model=TokenResponse)
async def login(data: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    logger.info("Login attempt for email=%s", data.email)

    user = await authenticate_user(data.email, data.password, db)
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Email not verified. Please check your inbox for the OTP.")
    logger.info("User %s authenticated (id=%s)", user.username, user.id)

    token_data = {"sub": str(user.id), "username": user.username, "role": user.role.value}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token({"sub": str(user.id)})

    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=_REFRESH_MAX_AGE,
        path=_REFRESH_COOKIE_PATH,
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/refresh", status_code=status.HTTP_200_OK, response_model=TokenResponse)
async def refresh(request: Request, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get(_REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Refresh token missing")

    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("sub")
    result = await db.execute(select(Users).where(Users.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    token_data = {"sub": str(user.id), "username": user.username, "role": user.role.value}
    access_token = create_access_token(token_data)
    logger.info("Access token refreshed for user_id=%s", user_id)

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(response: Response):
    response.delete_cookie(key=_REFRESH_COOKIE, path=_REFRESH_COOKIE_PATH)
    return {"message": "Logged out successfully"}


@router.get("/me", status_code=status.HTTP_200_OK, response_model=UserResponse)
async def me(current_user: Users = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role.value,
        "billing_type": current_user.billing_type.value,
    }


@router.put("/me/password", status_code=status.HTTP_200_OK)
async def update_password(
    data: UpdatePasswordRequest,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if data.current_password == data.new_password:
        raise HTTPException(status_code=400, detail="New password must differ from current password")

    current_user.hashed_password = hash_password(data.new_password)
    await db.commit()
    logger.info("Password updated for user %s", current_user.username)
    return {"message": "Password updated successfully"}


@router.post("/verify-otp", status_code=status.HTTP_200_OK)
async def verify_otp(data: VerifyOtpRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Users).where(Users.email == data.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_verified:
        return {"message": "Email already verified"}

    await _otp_manager.verify_otp(email=data.email, otp=data.otp)

    user.is_verified = True
    await db.commit()
    logger.info("User %s email verified", user.username)
    return {"message": "Email verified successfully"}


@router.post("/resend-otp", status_code=status.HTTP_200_OK)
async def resend_otp(data: ResendOtpRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Users).where(Users.email == data.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_verified:
        raise HTTPException(status_code=400, detail="Email already verified")

    await _otp_manager.send_otp(email=user.email, username=user.username)
    return {"message": "OTP sent successfully"}


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(data: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    # Always return 200 to avoid leaking which emails are registered
    result = await db.execute(select(Users).where(Users.email == data.email))
    user = result.scalar_one_or_none()
    if not user:
        return {"message": "If that email is registered, a reset link has been sent"}

    import secrets
    token = secrets.token_urlsafe(32)
    await redis_set(f"pwd_reset:{token}", user.email, ex=15 * 60)  # 15 min TTL

    reset_link = f"{Config.FRONTEND_URL}/reset-password?token={token}"
    builder = CommunicationBuilder(
        recipient=user.email,
        template=PasswordResetTemplate(),
        data={"reset_link": reset_link, "username": user.username},
    )
    builder.send()
    logger.info("Password reset link sent to %s", user.email)
    return {"message": "If that email is registered, a reset link has been sent"}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    email = await redis_get(f"pwd_reset:{data.token}")
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    result = await db.execute(select(Users).where(Users.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = hash_password(data.new_password)
    await db.commit()
    await redis_delete(f"pwd_reset:{data.token}")
    logger.info("Password reset for user %s", user.username)
    return {"message": "Password reset successfully"}
