from datetime import datetime, timedelta, timezone
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from jose import JWTError, jwt

from app.config import get_settings


password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return password_hasher.verify(hashed, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(admin_id: int) -> str:
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_minutes)
    return jwt.encode({"sub": str(admin_id), "exp": expires, "jti": secrets.token_urlsafe(16)}, settings.jwt_secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int | None:
    try:
        subject = jwt.decode(token, get_settings().jwt_secret_key, algorithms=[ALGORITHM]).get("sub")
        return int(subject) if subject is not None else None
    except (JWTError, TypeError, ValueError):
        return None

