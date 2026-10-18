
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models import User
from app.schemas.auth import UserCreate


class AuthService:

    @staticmethod
    def register(db: Session, data: UserCreate) -> User:
        email = str(data.email).lower()

        existing = db.scalar(
            select(User).where(
                or_(
                    User.email == email,
                    User.username == data.username,
                )
            )
        )

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email or username already registered",
            )

        user = User(
            username=data.username,
            email=email,
            password_hash=hash_password(data.password),
            role="operator",
            is_active=True,
        )

        db.add(user)

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email or username already registered",
            )

        db.refresh(user)
        return user

    @staticmethod
    def login(
        db: Session,
        identifier: str,
        password: str,
    ) -> str:
        identifier = identifier.strip().lower()
        user = db.scalar(
            select(User).where(
                or_(
                    User.email == identifier,
                    User.username == identifier,
                )
            )
        )

        if (
            user is None
            or not verify_password(
                password,
                user.password_hash,
            )
            or not user.is_active
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user.last_login_at = datetime.now(timezone.utc)
        db.commit()

        return create_access_token(user.id)
