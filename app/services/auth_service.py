
from fastapi import HTTPException, status
from sqlalchemy import select
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
            select(User).where(User.email == email)
        )

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        user = User(
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
                detail="Email already registered",
            )

        db.refresh(user)
        return user

    @staticmethod
    def login(
        db: Session,
        email: str,
        password: str,
    ) -> str:
        user = db.scalar(
            select(User).where(
                User.email == email.lower()
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

        return create_access_token(user.id)
