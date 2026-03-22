import logging
import random
import string

from fastapi import HTTPException

from app.services.redis_service import redis_delete, redis_get, redis_set
from app.services.CommunicationBuilder import CommunicationBuilder, OtpTemplate

logger = logging.getLogger(__name__)

_OTP_TTL = 10 * 60       # 10 minutes
_RESEND_COOLDOWN = 60    # 1 minute between resends


class OTPManager:
    def __init__(self, otp_length: int = 6):
        self.otp_length = otp_length

    def _generate(self) -> str:
        return "".join(random.choices(string.digits, k=self.otp_length))

    @staticmethod
    def _otp_key(email: str) -> str:
        return f"otp:{email}"

    @staticmethod
    def _cooldown_key(email: str) -> str:
        return f"otp_cooldown:{email}"

    async def send_otp(self, email: str, username: str = "there") -> None:
        cooldown = await redis_get(self._cooldown_key(email))
        if cooldown:
            raise HTTPException(429, "Please wait before requesting another OTP")

        otp = self._generate()
        await redis_set(self._otp_key(email), otp, ex=_OTP_TTL)
        await redis_set(self._cooldown_key(email), "1", ex=_RESEND_COOLDOWN)

        builder = CommunicationBuilder(
            recipient=email,
            template=OtpTemplate(),
            data={"otp": otp, "username": username},
        )
        builder.send()
        logger.info("OTP sent to %s", email)

    async def verify_otp(self, email: str, otp: str) -> None:
        stored = await redis_get(self._otp_key(email))
        if not stored:
            raise HTTPException(400, "OTP expired or not found")
        if stored != otp:
            raise HTTPException(400, "Invalid OTP")

        await redis_delete(self._otp_key(email))
        await redis_delete(self._cooldown_key(email))