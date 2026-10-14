
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash

from app.core.config import settings


password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    return password_hasher.verify(
        plain_password,
        hashed_password,
    )


def create_access_token(user_id: UUID) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": str(user_id),
        "exp": expires_at,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> UUID:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={
                "require": ["sub", "exp", "iat", "type"]
            },
        )

        if payload.get("type") != "access":
            raise ValueError("Invalid token type")

        return UUID(payload["sub"])

    except (
        InvalidTokenError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        raise ValueError("Invalid or expired token") from exc
